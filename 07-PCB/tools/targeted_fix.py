"""26 项真违规的定点修复 (基于 fix_drc 的验证机械)
动作清单:
  1. 3V3 横干线下线 (8,-14.6)->(291,-14.6): 绕 J2.2 / J3.2
  2. 3V3 横干线上线 (68,-13.2)->(291,-13.2): 绕 U2.3 / J3.1 / U1.1 / U1.40
  3. via HO_K60 (170.42,-26.92) 下移 (躲 U106.9/.10)
  4. via HO_K61 (162.64,-26.38) 右移 (躲 U106.16/.15)
  5. via HO_K30 / HO_K31 分离
  6. via HO_K04 (80.22,-126.25) 左移 (躲 H44.1)
  7. via HO_K10 / HO_K11 分离
  8. 3V3 垂线 (139.09) 端点收到 -25.4 (不再穿 U105 引脚排)
  9. 3V3 垂线 (258.16) 平移 x 躲 SW1
  10. HO_K22 手拉线端 (138.63,-148) 收缩躲 H57.1
"""
import json, math, sys
sys.path.insert(0, '/Users/Admin/ZCodeProject/KeyCore/07-PCB/tools')
from drc_local import build_shapes, LAYER_MM, GEO
from fix_drc import (violating_pairs, build_grid, check_seg, check_via,
                     rebuild_shapes, nearby)
from drc_local import dist_shapes, seg_pt_dist, Shape

TRACKS = GEO['tracks']
VIAS = GEO['vias']
edits = {'weave': [], 'via_moves': [], 'end_moves': [], 'manual': []}


def find_track(x1, y1, x2, y2, net=None, w=None, tol=0.02):
    for t in TRACKS:
        if net and t['net'] != net:
            continue
        if w and abs(t['w']-w) > 0.005:
            continue
        if (abs(t['x1']-x1) < tol and abs(t['y1']-y1) < tol and
                abs(t['x2']-x2) < tol and abs(t['y2']-y2) < tol):
            return t
        if (abs(t['x1']-x2) < tol and abs(t['y1']-y2) < tol and
                abs(t['x2']-x1) < tol and abs(t['y2']-y1) < tol):
            return t
    return None


def find_via(x, y, tol=0.02):
    for v in VIAS:
        if abs(v['x']-x) < tol and abs(v['y']-y) < tol:
            return v
    return None


def weave_horizontal(t, shapes, grid):
    """水平线绕行: 逐组阻挡 pad, 优先从与相邻 pad 的缝隙中间穿过, 否则绕远端"""
    x1, y1, x2, y2 = t['x1'], t['y1'], t['x2'], t['y2']
    ly = y1
    lo, hi = min(x1, x2), max(x1, x2)
    intr = []
    for p in GEO['pads']:
        if not (p['net'] or p['hole_t']) or p['net'] == t['net']:
            continue
        a = math.radians(p['angle'])
        ca, sa = abs(math.cos(a)), abs(math.sin(a))
        ex = p['w']/2*ca + p['h']/2*sa
        ey = p['w']/2*sa + p['h']/2*ca
        if lo-0.5 < p['x'] < hi+0.5 and abs(p['y']-ly) < ey + t['w']/2 + 0.12:
            intr.append([p['x'], p['y'], ex, ey])
    if not intr:
        return None
    intr.sort()
    # x 重叠的 pad 合并为一组 (同位置多 pad)
    groups = []
    for it in intr:
        if groups and it[0]-it[2]-t['w']/2-0.02 <= groups[-1][-1][0]+groups[-1][-1][2]+t['w']/2:
            groups[-1].append(it)
        else:
            groups.append([it])
    pts = [(x1, y1)]
    prev_end = x1
    for g in groups:
        px_mid = sum(q[0] for q in g)/len(g)
        b0 = min(q[0]-q[2] for q in g) - t['w']/2 - 0.10
        b1 = max(q[0]+q[2] for q in g) + t['w']/2 + 0.10
        # 候选通道线: 组内 pad 之间缝隙中点 + 组上/下远方
        cands = []
        pads = sorted(g, key=lambda q: q[1])
        for i in range(len(pads)-1):
            gap_hi = pads[i][1] + pads[i][3]
            gap_lo = pads[i+1][1] - pads[i+1][3]
            if gap_lo - gap_hi >= t['w'] + 0.18:
                cands.append((gap_hi + gap_lo)/2)
        top_edge = max(q[1]+q[3] for q in g)
        bot_edge = min(q[1]-q[3] for q in g)
        cands += [bot_edge - t['w']/2 - 0.12, top_edge + t['w']/2 + 0.12]
        chosen = None
        dbg = []
        for go in cands:
            trial = [(prev_end if not pts else pts[-1][0], pts[-1][1]), (b0, pts[-1][1]),
                     (b0, go), (b1, go), (b1, pts[-1][1])]
            ok = True
            for i in range(1, len(trial)-1):
                seg = (trial[i][0], trial[i][1], trial[i+1][0], trial[i+1][1])
                if not check_seg(seg, t['w'], t['layer'], t['net'], shapes, grid, 0.09):
                    ok = False
                    dbg.append(('seg_fail', round(go, 2), [round(v, 2) for v in seg]))
                    break
            if ok:
                chosen = go
                break
        if chosen is None:
            print(f"  织纬失败 @x={px_mid:.1f}: cands={[round(c,2) for c in cands]} dbg={dbg[:3]}")
            return None
        pts += [(b0, pts[-1][1]), (b0, chosen), (b1, chosen), (b1, pts[-1][1])]
        prev_end = b1
    pts += [(x2, y2)]
    for i in range(len(pts)-1):
        seg = (pts[i][0], pts[i][1], pts[i+1][0], pts[i+1][1])
        if not check_seg(seg, t['w'], t['layer'], t['net'], shapes, grid, 0.09):
            print(f"  织纬终验失败 seg{i}: {tuple(round(v, 2) for v in seg)}")
            return None
    return pts


def weave_vertical(t, shapes, grid):
    x1, y1, x2, y2 = t['x1'], t['y1'], t['x2'], t['y2']
    lx = x1
    lo, hi = min(y1, y2), max(y1, y2)
    intr = []
    for p in GEO['pads']:
        if not (p['net'] or p['hole_t']) or p['net'] == t['net']:
            continue
        a = math.radians(p['angle'])
        ca, sa = abs(math.cos(a)), abs(math.sin(a))
        ex = p['w']/2*ca + p['h']/2*sa
        ey = p['w']/2*sa + p['h']/2*ca
        if lo-0.5 < p['y'] < hi+0.5 and abs(p['x']-lx) < ex + t['w']/2 + 0.02:
            intr.append((p['y'], p['x'], ex, ey))
    if not intr:
        return None
    intr.sort()
    pts = [(x1, y1)]
    prev_end = y1
    for (py, px, ex, ey) in intr:
        b0, b1 = py-ey-t['w']/2-0.12, py+ey+t['w']/2+0.12
        need = ex + t['w']/2 + 0.12
        go = lx + (abs(px-lx) + need) * (1 if px > lx else -1)
        if abs(px-lx) <= 0.1:
            n_r = sum(1 for (qy, qx, qe, qh2) in intr if qx > lx and abs(qy-py) < 6)
            go = lx - need if n_r else lx + need
        if b0 > prev_end + 0.005:
            pts += [(lx, b0)]
        pts += [(go, b0), (go, b1)]
        prev_end = b1
    pts += [(x2, y2)]
    for i in range(len(pts)-1):
        seg = (pts[i][0], pts[i][1], pts[i+1][0], pts[i+1][1])
        if not check_seg(seg, t['w'], t['layer'], t['net'], shapes, grid, 0.09):
            print(f"  织纬终验失败 seg{i}: {tuple(round(v, 2) for v in seg)}")
            return None
    return pts


WEAVE_INFO = []   # (net, ly, [(b0,b1,go)]) 供织纬后重连


def apply_pts(t, pts):
    orig = [t['x1'], t['y1'], t['x2'], t['y2']]
    t['x2'], t['y2'] = pts[1]
    for i in range(1, len(pts)-1):
        TRACKS.append(dict(layer=t['layer'], net=t['net'],
                           x1=pts[i][0], y1=pts[i][1], x2=pts[i+1][0], y2=pts[i+1][1],
                           w=t['w'], _new=True))
    edits['weave'].append(dict(net=t['net'], pts=[[round(a, 3), round(b, 3)] for a, b in pts], w=t['w'],
                               layer=t['layer'], orig=[round(v, 4) for v in orig]))
    # 解析绕行区间: 相邻点 y != ly 的平台段
    ly = pts[0][1]
    horiz = abs(pts[0][1] - pts[-1][1]) < 0.01
    if horiz and abs(pts[0][0]-pts[-1][0]) > abs(pts[0][1]-pts[-1][1]):
        groups = []
        i = 1
        while i < len(pts)-3:
            if abs(pts[i][1]-ly) > 0.01 and abs(pts[i+1][1]-ly) > 0.01:
                groups.append((pts[i][0], pts[i+1][0], pts[i][1]))
                i += 3
            else:
                i += 1
        WEAVE_INFO.append((t['net'], ly, groups))


def move_via(v, dx, dy, shapes, grid, target=0.1):
    """定向挪移: 先试 (dx,dy), 再螺旋"""
    tset = TRACKS
    def attempt(nx, ny):
        if not check_via(nx, ny, v['dia'], v['net'], shapes, grid, target):
            return False
        for t in tset:
            if abs(t['w']-0.256) < 0.002 or not t['net']:
                continue
            for which in (0, 1):
                ex = (t['x1'], t['y1']) if which == 0 else (t['x2'], t['y2'])
                if abs(ex[0]-v['x']) < 0.02 and abs(ex[1]-v['y']) < 0.02:
                    ns = (nx, ny, t['x2'], t['y2']) if which == 0 else (t['x1'], t['y1'], nx, ny)
                    if not check_seg(ns, t['w'], t['layer'], t['net'], shapes, grid, target):
                        return False
        return True
    old = (v['x'], v['y'])
    cands = [(old[0]+dx, old[1]+dy)]
    for rad in [0.05*i for i in range(1, 60)]:
        for k in range(24):
            a = 2*math.pi*k/24
            cands.append((old[0]+rad*math.cos(a), old[1]+rad*math.sin(a)))
    for nx, ny in cands:
        if attempt(nx, ny):
            for t in tset:
                if abs(t['w']-0.256) < 0.002 or not t['net']:
                    continue
                for which in (0, 1):
                    ex = (t['x1'], t['y1']) if which == 0 else (t['x2'], t['y2'])
                    if abs(ex[0]-old[0]) < 0.02 and abs(ex[1]-old[1]) < 0.02:
                        if which == 0:
                            t['x1'], t['y1'] = nx, ny
                        else:
                            t['x2'], t['y2'] = nx, ny
            v['x'], v['y'] = nx, ny
            edits['via_moves'].append(dict(net=v['net'], old=[round(old[0], 3), round(old[1], 3)],
                                           new=[round(nx, 3), round(ny, 3)]))
            return True
    return False


def main():
    shapes = rebuild_shapes()
    grid = build_grid(shapes)

    # 1/2: 两根横干线绕行 (坐标定位, 宽度不预设)
    for seg in ((8, -14.6, 291, -14.6), (68, -13.2, 291, -13.2)):
        t = find_track(*seg, net='3V3', tol=0.1)
        if t is None:
            edits['manual'].append(dict(kind='trunk_not_found', seg=list(seg)))
            print(f"横干线 {seg[1]}: 没找到!")
            continue
        pts = weave_horizontal(t, shapes, grid)
        if pts:
            apply_pts(t, pts)
            print(f"横干线 {seg[1]}(w{t['w']:.2f}): 绕行 {len(pts)} 段")
        else:
            edits['manual'].append(dict(kind='trunk_weave_failed', seg=list(seg)))
            print(f"横干线 {seg[1]}: 织纬失败")

    # 7.5: 织纬后重连 —— 落在绕行区间内的同 net 线头, 补垂直短段
    shapes = rebuild_shapes()
    grid = build_grid(shapes)
    for (wnet, ly, groups) in WEAVE_INFO:
        ends = []
        for t in TRACKS:
            if t['net'] != wnet or abs(t['w']-0.256) < 0.002:
                continue
            for which, (ex, ey) in enumerate(((t['x1'], t['y1']), (t['x2'], t['y2']))):
                ends.append((t, which, ex, ey))
        for (t, which, ex, ey) in ends:
            if abs(ey - ly) > 0.3:
                continue
            grp = next((g for g in groups if g[0]-0.02 <= ex <= g[1]+0.02), None)
            if grp is None:
                continue
            b0, b1, go = grp
            # 该端点现在还接得上同 net 铜吗
            still = False
            for t2 in TRACKS:
                if t2 is t or t2['net'] != wnet:
                    continue
                if seg_pt_dist(ex, ey, (t2['x1'], t2['y1'], t2['x2'], t2['y2'])) <= t2['w']/2 + 0.02:
                    still = True
                    break
            if still:
                continue
            for v in VIAS:
                if v['net'] == wnet and math.hypot(v['x']-ex, v['y']-ey) <= v['dia']/2 + 0.02:
                    still = True
                    break
            if still:
                continue
            # 补垂直接线到平台线 go
            seg = (ex, ey, ex, go)
            if check_seg(seg, min(t['w'], 0.25), t['layer'], wnet, shapes, grid, 0.09):
                TRACKS.append(dict(layer=t['layer'], net=wnet, x1=ex, y1=ey, x2=ex, y2=go,
                                   w=min(t['w'], 0.25), _new=True))
                edits['weave'].append(dict(kind='reconnect', net=wnet, at=[round(ex, 3), round(ey, 3)], to_go=go,
                                           layer=t['layer'], w=min(t['w'], 0.25)))
                print(f"  重连 {wnet} 线头 ({ex:.2f},{ey:.2f}) -> 平台 y={go:.2f}")

    # 8: 3V3 垂线 (139.09) 收端
    t = find_track(139.09, -26.68, 139.09, -14.6, net="3V3", tol=0.1)
    if t:
        t['y1'] = -25.35   # 上端收到 pad 排上方 (pad 尖 -25.55)
        edits['end_moves'].append(dict(net='3V3', kind='endpoint', old=[139.09, -26.68], new=[139.09, -25.35],
                                       why='U105 pin row', orig=[round(t['x1'],4), -25.35, round(t['x2'],4), round(t['y2'],4)]))
        print("3V3 垂线 139.09 收端")

    # 9: 3V3 垂线 (258.16, w0.3) 折线绕 SW1 + MUX_B 斜线, x 候选扫描
    t = find_track(258.16, -26.68, 258.16, -14.6, net="3V3", tol=0.1)
    if t:
        done = False
        for xj in (258.85, 258.95, 259.05, 259.2, 259.35, 258.75):
            for yturn in (-14.7, -15.0, -15.3):
                pts = [(258.16, -14.6), (258.16, yturn), (xj, yturn), (xj, -26.0)]
                ok = True
                for i in range(len(pts)-1):
                    seg = (pts[i][0], pts[i][1], pts[i+1][0], pts[i+1][1])
                    if not check_seg(seg, t['w'], t['layer'], t['net'], shapes, grid, 0.09):
                        ok = False
                        break
                if ok:
                    # t 实际方向: (x1,y1)=下端(-26.675), (x2,y2)=上端(-14.6) —— 收掉下端到转折点
                    if abs(t['y2'] - (-14.6)) < 0.15 and abs(t['y1'] - (-26.68)) < 0.15:
                        t['y1'] = yturn
                    else:
                        t['y2'] = yturn
                    for i in range(1, len(pts)-1):
                        TRACKS.append(dict(layer=t['layer'], net=t['net'],
                                           x1=pts[i][0], y1=pts[i][1], x2=pts[i+1][0], y2=pts[i+1][1],
                                           w=t['w'], _new=True))
                    edits['end_moves'].append(dict(net='3V3', kind='reroute_sw1',
                                                   pts=[[round(a, 3), round(b, 3)] for a, b in pts],
                                                   orig=[round(t['x1'],4), round(t['y1'],4), round(t['x2'],4), round(t['y2'],4)],
                                                   w=t['w'], layer=t['layer']))
                    print(f"3V3 垂线 258.16 折线绕行 (x={xj}, y={yturn})")
                    done = True
                    break
            if done:
                break
        if not done:
            edits['manual'].append(dict(kind='vert3v3_sw1', at=[258.16, -20]))
            print("3V3 垂线 258.16: 所有候选失败")

    # 10: HO_K22 手拉端收缩 (pad 0.9x0.8 外接半径 0.602 + 线半宽 0.125 + 0.09)
    t = find_track(138.63, -145.47, 138.63, -148.0, net="HO_K22", tol=0.1)
    if t is None:
        t = find_track(138.63, -148.0, 138.63, -145.47, net="HO_K22", tol=0.1)
    if t:
        px, py = 139.09, -145.32
        keep = 0.83
        for w_end in (0, 1):
            ex = (t['x1'], t['y1']) if w_end == 0 else (t['x2'], t['y2'])
            if abs(ex[1] - (-145.47)) < 0.05:   # 靠近 H57 的那端
                dx, dy = ex[0]-px, ex[1]-py
                L = math.hypot(dx, dy)
                nx, ny = px+dx/L*keep, py+dy/L*keep
                if w_end == 0:
                    t['x1'], t['y1'] = nx, ny
                else:
                    t['x2'], t['y2'] = nx, ny
                edits['end_moves'].append(dict(net='HO_K22', kind='endpoint', old=list(ex), new=[round(nx, 3), round(ny, 3)],
                                               why='H57.1', orig=[round(t['x1'],4), round(t['y1'],4), round(t['x2'],4), round(t['y2'],4)]))
                print("HO_K22 端收缩")
                break

    # 3-7: 过孔挪位
    via_jobs = [
        ((170.42, -26.92), 0.0, -1.2),   # HO_K60 下移
        ((162.64, -26.38), 1.4, 0.0),    # HO_K61 右移
        ((80.22, -126.25), -1.0, 0.0),   # HO_K04 左移
    ]
    for (x, y), dx, dy in via_jobs:
        v = find_via(x, y)
        if v:
            if not move_via(v, dx, dy, rebuild_shapes(), build_grid(rebuild_shapes())):
                edits['manual'].append(dict(kind='via_stuck', at=[x, y], net=v['net']))
                print(f"via {v['net']} @({x},{y}) 挪不动!")
            else:
                print(f"via {v['net']} @({x},{y}) -> ({v['x']:.2f},{v['y']:.2f})")
        else:
            edits['manual'].append(dict(kind='via_not_found', at=[x, y]))
    # 成对分离: HO_K30/HO_K31, HO_K10/HO_K11, HO_K20/HO_K18
    for (a_xy, b_xy) in (((167.18, -64.49), (167.33, -64.02)), ((119.85, -105.64), (119.93, -106.23)),
                         ((120.59, -85.95), (121.07, -85.46))):
        va, vb = find_via(*a_xy), find_via(*b_xy)
        if va and vb:
            ok = move_via(va, -0.5, -0.35, rebuild_shapes(), build_grid(rebuild_shapes()))
            if not ok:
                ok = move_via(vb, 0.5, 0.35, rebuild_shapes(), build_grid(rebuild_shapes()))
            print(f"对分离 {va['net']}/{vb['net']}: {'ok' if ok else '失败'}")
            if not ok:
                edits['manual'].append(dict(kind='pair_stuck', a=a_xy, b=b_xy))

    # 终检
    shapes = rebuild_shapes()
    viols = sorted(violating_pairs(shapes), key=lambda v: v['gap'])
    print(f"\n修复后违规: {len(viols)}")
    def f(t):
        if t['kind'] == 'pad':
            return f"pad {t['ref']}.{t['num']}({t['net'] or 'NC'})@({t['x']:.2f},{t['y']:.2f})"
        if t['kind'] == 'via':
            return f"via({t['net']})@({t['x']:.2f},{t['y']:.2f})"
        s = t['seg']
        return f"track({t['net']})({s[0]:.2f},{s[1]:.2f})->({s[2]:.2f},{s[3]:.2f})"
    for v in viols:
        tag = '必修' if v['gap'] < 0.05 else '容忍'
        print(f"  [{tag}] {v['gap']:+.3f} {f(v['a'])} × {f(v['b'])}")
        if v['gap'] < 0.05:
            edits['manual'].append(dict(kind='residual', gap=v['gap'], a=f(v['a']), b=f(v['b'])))

    json.dump(dict(tracks=TRACKS, vias=VIAS, pads=GEO['pads'], pours=GEO['pours'], comps=GEO['comps']),
              open('/tmp/eprj_probe/geometry_fixed.json', 'w'))
    json.dump(edits, open('/tmp/eprj_probe/fix_plan.json', 'w'), ensure_ascii=False, indent=1)
    print(f"\nweave={len(edits['weave'])} via_moves={len(edits['via_moves'])} "
          f"end_moves={len(edits['end_moves'])} manual={len(edits['manual'])}")


if __name__ == '__main__':
    main()
