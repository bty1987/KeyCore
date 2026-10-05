"""DRC 批量修复器 v2
口径 (对齐 2026-10-04 进度文档): 0.05~0.089 区间 = 原型板容忍带, 不强修;
主攻 <0.05 的挤压与全部重叠 (<0). 过孔挪动目标 0.1 (安全裕量).
策略:
  B. 粗干线 (3V3/GND w>=0.5) 横穿焊盘: 上下双方向 × 幅度递增绕行, 全量验证后落地
  A. 过孔违规: 刚体平移 (孔+相连线自由端), 螺旋搜索, 目标 0.1
  T. 自由短段 (两端皆悬空) 重叠: 整段平移
  C. 悬空线端压焊盘: 沿线回缩
迭代 3 轮至收敛; 输出 fix_plan.json / geometry_fixed.json / 手工清单
"""
import json, math, sys
sys.path.insert(0, '/Users/Admin/ZCodeProject/KeyCore/07-PCB/tools')
from drc_local import (build_shapes, run_clearance, dist_shapes, seg_pt_dist,
                       Shape, LAYER_MM, GEO)

TOL_BAND = 0.050       # < 此值必须修
RULE = 0.0889
TARGET_VIA = 0.10
MAX_R = 3.0
ACCEPT_FALLBACK = 0.06


def kof(t):
    if t['kind'] == 'track':
        return ('track', tuple(round(c, 3) for c in t['seg']))
    return (t['kind'], round(t['x'], 3), round(t['y'], 3), t.get('ref', ''), t.get('num', ''))


def violating_pairs(shapes):
    viols = run_clearance(shapes)
    uniq = {}
    for v in viols:
        key = tuple(sorted([kof(v['a']), kof(v['b'])]))
        uniq.setdefault(key, v)
    return list(uniq.values())


def build_grid(shapes, cell=2.0):
    grid = {}
    for i, s in enumerate(shapes):
        x1, y1, x2, y2 = s.bbox()
        for gx in range(int(x1//cell), int(x2//cell)+1):
            for gy in range(int(y1//cell), int(y2//cell)+1):
                grid.setdefault((gx, gy), []).append(i)
    return grid


def nearby(shapes, grid, x, y, pad_mm=4.0, cell=2.0):
    out = set()
    R = int(pad_mm//cell) + 1
    gx, gy = int(x//cell), int(y//cell)
    for dx in range(-R, R+1):
        for dy in range(-R, R+1):
            out.update(grid.get((gx+dx, gy+dy), ()))
    return [shapes[i] for i in out]


def rebuild_shapes():
    return build_shapes()


def check_seg(seg, w, layer, net, shapes, grid, target):
    """新线段 vs 全部异 net 铜 >= target (仅同层 + 通孔焊盘/安装孔)"""
    slay = LAYER_MM.get(layer, 0)
    s = Shape('capsule', (seg, w/2), slay, net,
              dict(kind='track', net=net, seg=seg))
    mx, my = (seg[0]+seg[2])/2, (seg[1]+seg[3])/2
    span = max(abs(seg[2]-seg[0]), abs(seg[3]-seg[1]))/2 + w/2 + 3.0
    for o in nearby(shapes, grid, mx, my, pad_mm=span):
        if o.net == net:
            continue
        if o.layer != 'ALL' and o.layer != slay:
            continue
        if dist_shapes(s, o) < target:
            return False
    return True


def check_via(x, y, dia, net, shapes, grid, target):
    s = Shape('circle', ((x, y), dia/2), 'ALL', net,
              dict(kind='via', net=net, x=x, y=y))
    for o in nearby(shapes, grid, x, y, pad_mm=dia/2+4.0):
        if o.net == net:
            continue
        if dist_shapes(s, o) < target:
            return False
    return True


# ---------- B: 粗干线绕行 ----------
def detour_trunk(t, shapes, grid):
    x1, y1, x2, y2 = t['x1'], t['y1'], t['x2'], t['y2']
    horiz = abs(y1-y2) < 0.01
    vert = abs(x1-x2) < 0.01
    if not (horiz or vert):
        return None
    line = y1 if horiz else x1
    lo, hi = (min(x1, x2), max(x1, x2)) if horiz else (min(y1, y2), max(y1, y2))
    # 收集沿线阻挡 pad (异 net, 线穿入其外接圆)
    blockers = []
    for p in GEO['pads']:
        if not (p['net'] or p['hole_t']) or p['net'] == t['net']:
            continue
        R = max(p['w'], p['h'])/2
        c = p['y'] if horiz else p['x']
        s_ = p['x'] if horiz else p['y']
        if abs(c-line) < R + t['w']/2 + 0.02 and lo-0.3 < s_ < hi+0.3:
            blockers.append((s_-R-t['w']/2-0.09, s_+R+t['w']/2+0.09, c, R+t['w']/2+0.09))
    if not blockers:
        return None
    blockers.sort()
    merged = []
    for b in blockers:
        if merged and b[0] <= merged[-1][1] + 0.01:
            m = merged[-1]
            merged[-1] = (m[0], max(m[1], b[1]), b[2], max(m[3], b[3]))
        else:
            merged.append(b)
    base_amp = merged[0][3] + abs(merged[0][2]-line)
    for side in (1, -1):
        for amp in (base_amp, base_amp+0.5, base_amp+1.0):
            pts = [(x1, y1)]
            for b in merged:
                b0, b1, cross, _ = b
                go = line + side*amp
                if horiz:
                    pts += [(b0, line), (b0, go), (b1, go), (b1, line)]
                else:
                    pts += [(line, b0), (go, b0), (go, b1), (line, b1)]
            pts += [(x2, y2)]
            # 去共线
            cleaned = [pts[0]]
            for q in pts[1:]:
                if abs(q[0]-cleaned[-1][0]) > 1e-6 or abs(q[1]-cleaned[-1][1]) > 1e-6:
                    cleaned.append(q)
            pts = cleaned
            ok = True
            for i in range(len(pts)-1):
                seg = (pts[i][0], pts[i][1], pts[i+1][0], pts[i+1][1])
                if not check_seg(seg, t['w'], t['layer'], t['net'], shapes, grid, 0.09):
                    ok = False
                    break
            if ok:
                return pts
    return None


def apply_detour(t, pts, edits):
    t['x2'], t['y2'] = pts[1]
    for i in range(1, len(pts)-1):
        GEO['tracks'].append(dict(layer=t['layer'], net=t['net'],
                                  x1=pts[i][0], y1=pts[i][1],
                                  x2=pts[i+1][0], y2=pts[i+1][1], w=t['w'], _new=True))
    edits['detours'].append(dict(net=t['net'], via_pts=[[round(a, 3), round(b, 3)] for a, b in pts], w=t['w']))


# ---------- A: 过孔平移 ----------
def via_attached(via, tracks):
    out = []
    for i, t in enumerate(tracks):
        if abs(t['w']-0.256) < 0.002 or not t['net']:
            continue
        if abs(t['x1']-via['x']) < 0.02 and abs(t['y1']-via['y']) < 0.02:
            out.append((i, 0))
        elif abs(t['x2']-via['x']) < 0.02 and abs(t['y2']-via['y']) < 0.02:
            out.append((i, 1))
    return out


def try_move_via(via, tracks, shapes, grid, used):
    r = via['dia']/2
    att = via_attached(via, tracks)
    best = None
    for rad in [0.05*i for i in range(1, int(MAX_R/0.05)+1)]:
        for k in range(24):
            a = 2*math.pi*k/24
            nx, ny = via['x']+rad*math.cos(a), via['y']+rad*math.sin(a)
            if (round(nx, 2), round(ny, 2)) in used:
                continue
            if not check_via(nx, ny, via['dia'], via['net'], shapes, grid, TARGET_VIA):
                continue
            ok = True
            for i, which in att:
                t = tracks[i]
                ns = (nx, ny, t['x2'], t['y2']) if which == 0 else (t['x1'], t['y1'], nx, ny)
                if not check_seg(ns, t['w'], t['layer'], t['net'], shapes, grid, TARGET_VIA):
                    ok = False
                    break
            if ok and best is None:
                best = (nx, ny)
        if best:
            break
    if best is None:
        # 降级: 接受 >=0.06
        for rad in [0.05*i for i in range(1, int(MAX_R/0.05)+1)]:
            for k in range(24):
                a = 2*math.pi*k/24
                nx, ny = via['x']+rad*math.cos(a), via['y']+rad*math.sin(a)
                if (round(nx, 2), round(ny, 2)) in used:
                    continue
                if not check_via(nx, ny, via['dia'], via['net'], shapes, grid, ACCEPT_FALLBACK):
                    continue
                ok = True
                for i, which in att:
                    t = tracks[i]
                    ns = (nx, ny, t['x2'], t['y2']) if which == 0 else (t['x1'], t['y1'], nx, ny)
                    if not check_seg(ns, t['w'], t['layer'], t['net'], shapes, grid, ACCEPT_FALLBACK):
                        ok = False
                        break
                if ok:
                    best = (nx, ny)
                    break
            if best:
                break
    if best:
        nx, ny = best
        for i, which in att:
            t = tracks[i]
            if which == 0:
                t['x1'], t['y1'] = nx, ny
            else:
                t['x2'], t['y2'] = nx, ny
        via['x'], via['y'] = nx, ny
    return best


# ---------- 悬空端判定 ----------
def dangling_ends(tracks, vias, pads):
    def touching(x, y, t_self):
        for t2 in tracks:
            if t2 is t_self or not t2['net']:
                continue
            if t2['net'] != t_self['net']:
                continue
            if seg_pt_dist(x, y, (t2['x1'], t2['y1'], t2['x2'], t2['y2'])) <= t2['w']/2 + 0.02:
                return True
        for v in vias:
            if v['net'] == t_self['net'] and math.hypot(v['x']-x, v['y']-y) <= v['dia']/2 + 0.02:
                return True
        for p in pads:
            if p['net'] == t_self['net'] and math.hypot(p['x']-x, p['y']-y) <= max(p['w'], p['h'])/2 + 0.05:
                return True
        return False
    out = set()
    for idx, t in enumerate(tracks):
        if abs(t['w']-0.256) < 0.002 or not t['net']:
            continue
        if not touching(t['x1'], t['y1'], t):
            out.add((idx, 0))
        if not touching(t['x2'], t['y2'], t):
            out.add((idx, 1))
    return out


def main():
    pads = [p for p in GEO['pads'] if p['net'] or p['hole_t']]
    tracks = GEO['tracks']
    vias = GEO['vias']
    edits = dict(via_moves=[], seg_moves=[], detours=[], manual=[])

    for rnd in range(3):
        shapes = rebuild_shapes()
        grid = build_grid(shapes)
        viols = violating_pairs(shapes)
        must = [v for v in viols if v['gap'] < TOL_BAND]
        band = [v for v in viols if TOL_BAND <= v['gap'] < RULE]
        print(f"第{rnd}轮: 总违规 {len(viols)}, 待修(<0.05) {len(must)}, 容忍带(0.05~0.089) {len(band)}")
        if not must:
            break
        n0 = len(edits['detours']) + len(edits['via_moves']) + len(edits['seg_moves'])
        # B: 干线绕行
        done_seg = set()
        for v in must:
            for tt, pt in ((v['a'], v['b']), (v['b'], v['a'])):
                if tt['kind'] == 'track' and pt['kind'] == 'pad' and tt['net'] in ('3V3', 'GND'):
                    seg = tuple(round(c, 4) for c in tt['seg'])
                    if seg in done_seg:
                        continue
                    for t in tracks:
                        k = (round(t['x1'], 4), round(t['y1'], 4), round(t['x2'], 4), round(t['y2'], 4))
                        if k == seg and t['w'] >= 0.5:
                            pts = detour_trunk(t, shapes, grid)
                            if pts:
                                apply_detour(t, pts, edits)
                                done_seg.add(seg)
                            break
        # A: 过孔
        used = set()
        for v in must:
            for tt in (v['a'], v['b']):
                if tt['kind'] == 'via':
                    via = next((vv for vv in vias if abs(vv['x']-tt['x']) < 0.01 and abs(vv['y']-tt['y']) < 0.01), None)
                    if via is None:
                        continue
                    cur = (round(via['x'], 2), round(via['y'], 2))
                    if cur in used:
                        continue
                    r = try_move_via(via, tracks, rebuild_shapes(), build_grid(rebuild_shapes()), used)
                    if r:
                        used.add((round(r[0], 2), round(r[1], 2)))
                        edits['via_moves'].append(dict(net=via['net'], old=[tt['x'], tt['y']],
                                                       new=[round(r[0], 3), round(r[1], 3)], gap=round(v['gap'], 3)))
                    else:
                        edits['manual'].append(dict(kind='via_stuck', net=via['net'],
                                                    at=[round(via['x'], 3), round(via['y'], 3)], gap=round(v['gap'], 3)))
        # T+C: 自由段平移 / 悬空端回缩
        dang = dangling_ends(tracks, vias, pads)
        shapes2 = rebuild_shapes()
        grid2 = build_grid(shapes2)
        for v in [x for x in violating_pairs(shapes2) if x['gap'] < TOL_BAND]:
            a, b = v['a'], v['b']
            # C: track(悬空端) × pad
            for tt, ot in ((a, b), (b, a)):
                if tt['kind'] == 'track' and ot['kind'] == 'pad':
                    seg = tuple(round(c, 4) for c in tt['seg'])
                    for idx, t in enumerate(tracks):
                        k = (round(t['x1'], 4), round(t['y1'], 4), round(t['x2'], 4), round(t['y2'], 4))
                        if k != seg:
                            continue
                        for w_end in (0, 1):
                            if (idx, w_end) not in dang:
                                continue
                            ex, ey = (t['x1'], t['y1']) if w_end == 0 else (t['x2'], t['y2'])
                            px, py = ot['x'], ot['y']
                            dx, dy = ex-px, ey-py
                            L = math.hypot(dx, dy)
                            keep = max(ot.get('w', 0.6), 0.6)/2 + 0.09 + 0.02
                            if L <= keep:
                                continue
                            nx, ny = px+dx/L*keep, py+dy/L*keep
                            ns = (nx, ny, t['x2'], t['y2']) if w_end == 0 else (t['x1'], t['y1'], nx, ny)
                            if check_seg(ns, t['w'], t['layer'], t['net'], shapes2, grid2, 0.09):
                                if w_end == 0:
                                    t['x1'], t['y1'] = nx, ny
                                else:
                                    t['x2'], t['y2'] = nx, ny
                                edits['seg_moves'].append(dict(kind='shrink', net=t['net'],
                                                               old=[round(ex, 3), round(ey, 3)],
                                                               new=[round(nx, 3), round(ny, 3)]))
                            break
            # T: 自由段整体平移 (track × track / track × pad 未解的)
            if a['kind'] == 'track' and b['kind'] == 'track':
                sa = tuple(round(c, 4) for c in a['seg'])
                for idx, t in enumerate(tracks):
                    k = (round(t['x1'], 4), round(t['y1'], 4), round(t['x2'], 4), round(t['y2'], 4))
                    if k != sa:
                        continue
                    ends_free = all((idx, w) in dang for w in (0, 1))
                    if not ends_free:
                        continue
                    ax1, ay1, ax2, ay2 = t['x1'], t['y1'], t['x2'], t['y2']
                    horiz = abs(ay1-ay2) < 0.01
                    moved = False
                    for step in [0.1*i for i in range(1, 26)]:
                        for sgn in (1, -1):
                            dxy = (0, sgn*step) if horiz else (sgn*step, 0)
                            ns = (ax1+dxy[0], ay1+dxy[1], ax2+dxy[0], ay2+dxy[1])
                            if check_seg(ns, t['w'], t['layer'], t['net'], shapes2, grid2, 0.09):
                                t['x1'], t['y1'], t['x2'], t['y2'] = ns
                                edits['seg_moves'].append(dict(kind='translate', net=t['net'],
                                                               old=[ax1, ay1, ax2, ay2],
                                                               new=[round(v, 3) for v in ns]))
                                moved = True
                                break
                        if moved:
                            break
        n1 = len(edits['detours']) + len(edits['via_moves']) + len(edits['seg_moves'])
        print(f"   本轮修复动作: {n1-n0}")
        if n1 == n0:
            print("   无新动作, 收敛退出")
            break

    shapes = rebuild_shapes()
    viols = violating_pairs(shapes)
    must = [v for v in viols if v['gap'] < TOL_BAND]
    band = [v for v in viols if TOL_BAND <= v['gap'] < RULE]
    print(f"终态: 待修 {len(must)}, 容忍带 {len(band)}")
    def f(t):
        if t['kind'] == 'pad':
            return f"pad {t['ref']}.{t['num']}({t['net'] or 'NC'})@({t['x']:.1f},{t['y']:.1f})"
        if t['kind'] == 'via':
            return f"via({t['net']})@({t['x']:.2f},{t['y']:.2f})"
        s = t['seg']
        return f"track({t['net']})({s[0]:.1f},{s[1]:.1f})->({s[2]:.1f},{s[3]:.1f})"
    for v in sorted(must, key=lambda x: x['gap'])[:20]:
        edits['manual'].append(dict(kind='residual_must', gap=round(v['gap'], 3), a=f(v['a']), b=f(v['b'])))
        print(f"   必修残留 {v['gap']:+.3f} {f(v['a'])} × {f(v['b'])}")
    json.dump(dict(tracks=GEO['tracks'], vias=GEO['vias'], pads=GEO['pads'],
                   pours=GEO['pours'], comps=GEO['comps']),
              open('/tmp/eprj_probe/geometry_fixed.json', 'w'))
    json.dump(edits, open('/tmp/eprj_probe/fix_plan.json', 'w'), ensure_ascii=False, indent=1)
    print(f"via_moves={len(edits['via_moves'])} seg_moves={len(edits['seg_moves'])} "
          f"detours={len(edits['detours'])} manual={len(edits['manual'])}")


if __name__ == '__main__':
    main()
