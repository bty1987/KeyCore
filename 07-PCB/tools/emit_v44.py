"""合成 v4.4: v4.3 放置 + SES 全铜 + 末段引出路由 + GND 缝合 + K53 绑定 + B.Cu GND 铺铜区.

全部铜皮走 kicad_pcb 文件承载 (EDA 只有用文件加载的铜皮才注册 DRC 连接).

用法: python emit_v44.py [ses_path]
输出: ../output/KeyCore-v44.kicad_pcb
"""
import os
import sys
import math

sys.path.insert(0, os.path.dirname(__file__))
import design
from board import Track, BOARD_W, BOARD_H
import sexpr
import ses2kicad

DEBUG = os.environ.get('V44_DEBUG') == '1'
SES_PATH = os.environ.get('V44_SES', r'D:\tmp\v43b-clean.ses')
CLEAR = 0.13        # 障碍判定间隙 mm (规则 0.1016, 留裕量)
VIA_D, VIA_H = 0.7, 0.35     # 对齐 DSN via0 (0.7/0.35)
STUB_W = 0.254      # 10mil 短桩
ESC_W = 0.254       # 引出线宽


def seg_len(s):
    return math.hypot(s[2] - s[0], s[3] - s[1])


def seg_seg_dist(a, b):
    """线段-线段最小距离 (标准 clamping 算法)."""
    def dot(u, v):
        return u[0] * v[0] + u[1] * v[1]
    def sub(u, v):
        return (u[0] - v[0], u[1] - v[1])
    def norm(u):
        return math.hypot(*u)
    p1, q1, p2, q2 = (a[0], a[1]), (a[2], a[3]), (b[0], b[1]), (b[2], b[3])
    r, s = sub(q1, p1), sub(q2, p2)
    denom = r[0] * s[1] - r[1] * s[0]
    if abs(denom) < 1e-12:
        return min(seg_pt_dist(p1[0], p1[1], b), seg_pt_dist(q1[0], q1[1], b),
                   seg_pt_dist(p2[0], p2[1], a), seg_pt_dist(q2[0], q2[1], a))
    t = ((p2[0] - p1[0]) * s[1] - (p2[1] - p1[1]) * s[0]) / denom
    u = ((p2[0] - p1[0]) * r[1] - (p2[1] - p1[1]) * r[0]) / denom
    if 0 <= t <= 1 and 0 <= u <= 1:
        return 0.0
    return min(seg_pt_dist(p1[0], p1[1], b), seg_pt_dist(q1[0], q1[1], b),
               seg_pt_dist(p2[0], p2[1], a), seg_pt_dist(q2[0], q2[1], a))


def seg_pt_dist(px, py, seg):
    ax, ay, bx, by = seg
    abx, aby = bx - ax, by - ay
    L2 = abx * abx + aby * aby
    if L2 < 1e-12:
        return math.hypot(px - ax, py - ay)
    t = max(0.0, min(1.0, ((px - ax) * abx + (py - ay) * aby) / L2))
    return math.hypot(px - (ax + t * abx), py - (ay + t * aby))


class Obstacles:
    """同层铜障碍索引: 段(胶囊) + 焊盘(圆近似) + 过孔(圆)."""

    def __init__(self):
        self.segs = []   # (layer, x1,y1,x2,y2, halfw, net, tag)
        self.circles = []  # (layer_or_'ALL', x, y, r, net, tag)

    def add_seg(self, layer, x1, y1, x2, y2, w, net, tag=''):
        self.segs.append((layer, x1, y1, x2, y2, w / 2.0, net, tag))

    def add_circle(self, layer, x, y, r, net, tag=''):
        self.circles.append((layer, x, y, r, net, tag))

    def blocked(self, layer, x1, y1, x2, y2, w, net, clear=CLEAR):
        """候选线段是否撞障碍 (跨层过孔视为全层)."""
        hw = w / 2.0
        for (L, sx1, sy1, sx2, sy2, shw, snet, tag) in self.segs:
            if snet == net or L != layer:
                continue
            if seg_seg_dist((x1, y1, x2, y2), (sx1, sy1, sx2, sy2)) < clear + hw + shw:
                return ('seg', tag)
        for (L, cx, cy, r, cnet, tag) in self.circles:
            if cnet == net:
                continue
            if L not in (layer, 'ALL'):
                continue
            if seg_pt_dist(cx, cy, (x1, y1, x2, y2)) < clear + hw + r:
                return ('circ', tag)
        return None

    def via_blocked(self, x, y, r, net, clear=CLEAR):
        for (L, sx1, sy1, sx2, sy2, shw, snet, tag) in self.segs:
            if snet == net:
                continue
            if seg_pt_dist(x, y, (sx1, sy1, sx2, sy2)) < clear + r + shw:
                return ('seg', tag)
        for (L, cx, cy, cr, cnet, tag) in self.circles:
            if cnet == net:
                continue
            if math.hypot(x - cx, y - cy) < clear + r + cr:
                return ('circ', tag)
        return None


def write_v3_dsn(added, src=r'D:\tmp\v43b-clean.dsn', dst=r'D:\tmp\v43b-v3.dsn'):
    """把新增铜皮以 protected wiring 注入 placement-only DSN, 附 keepout + 电源加宽."""
    import re
    s = open(src, encoding='utf-8', errors='replace').read()
    # keepout (ESP32 天线净空, 四层)
    MM2U = 1000.0 / 25.4
    x1, y1, x2, y2 = 266.5 * MM2U, 159.2 * MM2U, 295.5 * MM2U, 171.6 * MM2U
    layers = ['TopLayer', 'Inner1', 'Inner2', 'BottomLayer']
    rects = '\n'.join(f'      (rect {L} {x1:.2f} {y1:.2f} {x2:.2f} {y2:.2f})' for L in layers)
    anchor = s.find('(structure')
    ins = s.find('\n', anchor) + 1
    s = s[:ins] + f'\n    (keepout\n{rects}\n    )' + s[ins:]
    # 电源类加宽
    for net in ('3V3', 'VBUS', 'GND'):
        s = re.sub(r"(class %s '%s'[\s\S]{0,200}?\(rule \s*\n\s*\(width )10" % (net, net),
                   r'\g<1>20', s)
    # 新增铜皮 → protected wiring
    LM = {1: 'TopLayer', 15: 'Inner1', 16: 'Inner2', 2: 'BottomLayer'}
    wires = []
    for item in added:
        if item[0] == 'track':
            _, L, ax, ay, bx, by, w, net, tag = item
            wm = w / 0.0254
            wires.append(f'(wire(path {LM[L]} {wm:.2f} {ax*MM2U:.0f} {ay*MM2U:.0f} '
                         f'{bx*MM2U:.0f} {by*MM2U:.0f} )\n      (net {net})\n      (type protect)\n    )')
        else:
            _, x, y, size, drill, net, tag = item
            wires.append(f'(via via0 {x*MM2U:.0f} {y*MM2U:.0f}\n      (net {net})\n      (type protect)\n    )')
    wiring = '\n  (wiring\n    ' + '\n    '.join(wires) + '\n  )\n'
    s = s.rstrip()[:-1].rstrip() + '\n' + wiring + ')'
    open(dst, 'w', encoding='utf-8').write(s)
    print(f'v3 DSN 写出: {dst} ({len(wires)} 条注入铜, {len(s)} bytes)')


def main():
    b, keys, mux_of, pu = design.build()

    # ---- K53 修复 ----
    p = b.pad('U106', '4')
    p['net'] = 'HO_K53'
    sexpr.set_net(p['pad'], b.net('HO_K53'), 'HO_K53')

    # 预放基础设施(母线/短桩/逃生孔)丢弃 — SES 为唯一铜来源 (emit_v43 口径)
    b.tracks.clear()
    b.vias.clear()

    # ---- SES 铜皮 ----
    tracks, vias = ses2kicad.parse(SES_PATH, BOARD_H)
    print(f'SES → 段 {len(tracks)}, 孔 {len(vias)}')
    for (x1, y1, x2, y2, w, layer, net) in tracks:
        b.tracks.append(Track(x1, y1, x2, y2, w, layer, net, eda_frame=True))
    for (x, y, size, drill, net) in vias:
        b.add_via(x, y, net, size, drill)

    obs = Obstacles()
    pad_list = []   # (ref_num, x, y, rw, rh, net)
    for c in b.components:
        for pd in c.abs_pads:
            r = max(pd['w'], pd['h']) / 2.0
            pad_list.append((f"{c.ref}_{pd['num']}", pd['x'], pd['y'], pd['w'] / 2.0, pd['h'] / 2.0, pd['net']))
            obs.add_circle(1, pd['x'], pd['y'], r * 0.72, pd['net'],
                           tag=f"pad:{c.ref}_{pd['num']}")  # 0.72≈矩形内切保守

    for (x1, y1, x2, y2, w, layer, net) in tracks:
        L = {'F.Cu': 1, 'In1.Cu': 15, 'In2.Cu': 16, 'B.Cu': 2}[layer]
        obs.add_seg(L, x1, y1, x2, y2, w, net, tag='ses')
    for (x, y, size, drill, net) in vias:
        obs.add_circle('ALL', x, y, size / 2.0, net, tag='sesvia')

    # ---- 末段引出路由 ----
    # 每网建端点目标表
    ends = {}
    for (x1, y1, x2, y2, w, layer, net) in tracks:
        L = {'F.Cu': 1, 'In1.Cu': 15, 'In2.Cu': 16, 'B.Cu': 2}[layer]
        ends.setdefault(net, []).append((x1, y1, L), )
        ends[net].append((x2, y2, L))
    for (x, y, size, drill, net) in vias:
        ends.setdefault(net, []).append((x, y, 'V'))

    def near_targets(net, px, py, k=6):
        cands = []
        for (ex, ey, L) in ends.get(net, []):
            cands.append((math.hypot(px - ex, py - ey), ex, ey, L))
        cands.sort(key=lambda c: c[0])
        return cands[:k]

    def try_path(net, px, py, tx, ty, tl, width, diag=False):
        """返回可行路径段列表 or (None, 原因)."""
        cands = []
        if abs(px - tx) < 0.01 or abs(py - ty) < 0.01 or abs(abs(px - tx) - abs(py - ty)) < 0.01:
            cands.append(('直连', [(px, py), (tx, ty)]))
        cands.append(('L竖先', [(px, py), (px, ty), (tx, ty)]))
        cands.append(('L横先', [(px, py), (tx, py), (tx, ty)]))
        if diag:
            sgnx = 1 if tx > px else -1
            sgny = 1 if ty > py else -1
            d = min(abs(tx - px), abs(ty - py))
            cands.append(('45折', [(px, py), (px + sgnx * d, py + sgny * d), (tx, ty)]))
        for name, path in cands:
            segs = list(zip(path[:-1], path[1:]))
            for (a, bpt) in segs:
                hit = obs.blocked(1, a[0], a[1], bpt[0], bpt[1], width, net)
                if hit:
                    if DEBUG:
                        print(f'    {name} 撞 {hit} @ ({a[0]:.2f},{a[1]:.2f})->({bpt[0]:.2f},{bpt[1]:.2f})')
                    break
            else:
                return segs, name
        return None, '全部候选被阻'

    added = []
    orphans = find_orphans(b, tracks, vias)
    print(f'孤立焊盘 {len(orphans)} (信号类, 不含 GND)')

    # 按网建迷宫 (自网铜不设障 — 允许并入主干)
    import maze_esc
    INF = 0.13 + ESC_W / 2.0
    maze_cache = {}

    def maze_for(net, layer=1):
        key = (net, layer)
        if key not in maze_cache:
            m = maze_esc.Maze(BOARD_W, BOARD_H)
            for (L, sx1, sy1, sx2, sy2, shw, snet, tag) in obs.segs:
                if L == layer and snet != net:
                    m.add_seg(sx1, sy1, sx2, sy2, shw, INF)
            for (L, cx, cy, cr, cnet, tag) in obs.circles:
                if L in (layer, 'ALL') and cnet != net:
                    m.add_circle(cx, cy, cr, INF)
            if layer == 1:
                # 焊盘只在 L1 (内层无焊盘障碍)
                for c in b.components:
                    for pd in c.abs_pads:
                        if pd['net'] == net:
                            continue
                        hw, hh = pd['w'] / 2.0, pd['h'] / 2.0
                        if abs(pd['rot'] % 180 - 90) < 45:
                            hw, hh = hh, hw
                        m.add_rect(pd['x'], pd['y'], hw, hh, INF)
            maze_cache[key] = m
        return maze_cache[key]

    def point_blocked(net):
        def f(x, y):
            return bool(obs.blocked(1, x, y, x + 0.004, y + 0.002, ESC_W, net))
        return f

    # 近目标优先
    order = []
    for (ref, px, py, net) in orphans:
        ts = near_targets(net, px, py)
        if ts:
            order.append((ts[0][0], ref, px, py, net, ts))
    order.sort()
    fixed, failed = 0, []
    stage = {'via_far': 0, 'via_blk': 0, 'L_ok': 0, 'inner': 0, 'nopath': 0, 'nofree': 0}
    for (dist0, ref, px, py, net, ts) in order:
        done = False
        maze = maze_for(net)
        for (d, tx, ty, tl) in ts:
            if tl == 'V':
                # 过孔目标: 焊盘→T 短桩 + T 处过孔
                segs = [(px, py), (tx, ty)]
                if math.hypot(px - tx, py - ty) > 6.0:
                    stage['via_far'] += 1
                    continue
                if not obs.blocked(1, px, py, tx, ty, STUB_W, net) and \
                   not obs.via_blocked(tx, ty, VIA_D / 2.0, net):
                    added.append(('track', 1, px, py, tx, ty, STUB_W, net, f'esc:{ref}'))
                    obs.add_seg(1, px, py, tx, ty, STUB_W, net, tag=f'esc:{ref}')
                    added.append(('via', tx, ty, VIA_D, VIA_H, net, f'esc:{ref}'))
                    obs.add_circle('ALL', tx, ty, VIA_D / 2.0, net, tag=f'escvia:{ref}')
                    stage['L_ok'] += 1
                    done = True
                    break
                stage['via_blk'] += 1
            elif tl == 1:
                segs, why = try_path(net, px, py, tx, ty, tl, ESC_W, diag=DEBUG)
                if segs:
                    stage['L_ok'] += 1
                if not segs:
                    # 迷宫升级
                    gs = maze.nearest_free(maze_esc.mm2g(px), maze_esc.mm2g(py))
                    gt = maze.nearest_free(maze_esc.mm2g(tx), maze_esc.mm2g(ty))
                    if gs is None or gt is None:
                        stage['nofree'] += 1
                    if gs and gt:
                        gpath = maze.astar(gs, gt)
                        if not gpath:
                            # 双过孔逃生: 盘内孔 → 内层迷宫 → 目标旁 0.5mm 孔 → 短桩→T
                            mi = maze_for(net, 16)
                            gs2 = mi.nearest_free(maze_esc.mm2g(px), maze_esc.mm2g(py))
                            gt2 = mi.nearest_free(maze_esc.mm2g(tx - 0.5 if tx > px else tx + 0.5),
                                                  maze_esc.mm2g(ty))
                            ok2 = False
                            if gs2 and gt2:
                                gp2 = mi.astar(gs2, gt2)
                                if gp2:
                                    pts = [(maze_esc.g2mm(gx), maze_esc.g2mm(gy)) for gx, gy in gp2]
                                    pts = mi.simplify(pts, net, 16, ESC_W,
                                                      (lambda lay: (lambda x, y: bool(obs.blocked(lay, x, y, x + 0.004, y + 0.002, ESC_W, net))))(16))
                                    pts = [(px, py)] + pts + [(tx, ty)]
                                    segs = list(zip(pts[:-1], pts[1:]))
                                    added.append(('via', px, py, VIA_D, VIA_H, net, f'esc:{ref}'))
                                    obs.add_circle('ALL', px, py, VIA_D / 2.0, net, tag=f'escvia:{ref}')
                                    added.append(('via', tx + (0.5 if tx > px else -0.5), ty, VIA_D, VIA_H, net, f'esc:{ref}'))
                                    obs.add_circle('ALL', tx + (0.5 if tx > px else -0.5), ty, VIA_D / 2.0, net, tag=f'escvia:{ref}')
                                    for (m_net, m_layer), m in maze_cache.items():
                                        if m_net != net:
                                            for (a, b2) in segs:
                                                m.add_seg(a[0], a[1], b2[0], b2[1], ESC_W / 2.0, 0.0)
                                    stage['L_ok'] += 1
                                    done = True
                                    ok2 = True
                            if not ok2:
                                stage['nopath'] += 1
                        if gpath:
                            pts = [(maze_esc.g2mm(gx), maze_esc.g2mm(gy)) for gx, gy in gpath]
                            pts = maze.simplify(pts, net, 1, ESC_W, point_blocked(net))
                            # 首尾闭合: 焊盘中心 → 首格, 末格 → 目标端点
                            pts = [(px, py)] + pts + [(tx, ty)]
                            segs = list(zip(pts[:-1], pts[1:]))
                            why = f'迷宫({len(pts)}点)'
                if segs:
                    for (a, bpt) in segs:
                        if math.hypot(a[0] - bpt[0], a[1] - bpt[1]) < 0.05:
                            continue
                        added.append(('track', 1, a[0], a[1], bpt[0], bpt[1], ESC_W, net, f'esc:{ref}'))
                        obs.add_seg(1, a[0], a[1], bpt[0], bpt[1], ESC_W, net, tag=f'esc:{ref}')
                        # 同步进其他网的同层缓存迷宫
                        for (m_net, m_layer), m in maze_cache.items():
                            if m_net != net and m_layer == 1:
                                m.add_seg(a[0], a[1], bpt[0], bpt[1], ESC_W / 2.0, 0.0)
                    done = True
                    break
                elif DEBUG:
                    print(f'  {ref} 目标@{d:.2f}mm({tx:.2f},{ty:.2f}): {why}')
            elif tl in (15, 16, 2):
                # 内层目标: 焊盘→短桩→旁孔→内层线→T
                placed = False
                for dist in (0.0, 0.5, 0.8, 1.0, 1.3, 1.7, 2.2):
                    for dx, dy in ((0, 0) if dist == 0.0 else (0, 1), (0, -1), (1, 0), (-1, 0),
                                   (0.707, 0.707), (-0.707, 0.707), (0.707, -0.707), (-0.707, -0.707)):
                        vx, vy = px + dx * dist, py + dy * dist
                        if obs.via_blocked(vx, vy, VIA_D / 2.0, net):
                            continue
                        if dist > 0 and obs.blocked(1, px, py, vx, vy, STUB_W, net):
                            continue
                        inner_ok = None
                        for path in ([(vx, vy), (vx, ty), (tx, ty)],
                                     [(vx, vy), (tx, vy), (tx, ty)],
                                     [(vx, vy), (tx, ty)]):
                            ss = list(zip(path[:-1], path[1:]))
                            if not any(obs.blocked(tl, a[0], a[1], b2[0], b2[1], ESC_W, net)
                                       for a, b2 in ss):
                                inner_ok = ss
                                break
                        if inner_ok is None:
                            # 内层迷宫: M→T 绕行
                            mi = maze_for(net, tl)
                            gs = mi.nearest_free(maze_esc.mm2g(vx), maze_esc.mm2g(vy))
                            gt = mi.nearest_free(maze_esc.mm2g(tx), maze_esc.mm2g(ty))
                            if not gs or not gt:
                                continue
                            gpath = mi.astar(gs, gt)
                            if not gpath:
                                continue
                            pts = [(maze_esc.g2mm(gx), maze_esc.g2mm(gy)) for gx, gy in gpath]
                            pts = mi.simplify(pts, net, tl, ESC_W,
                                              (lambda layer: (lambda x, y: bool(obs.blocked(layer, x, y, x + 0.004, y + 0.002, ESC_W, net))))(tl))
                            pts = [(vx, vy)] + pts + [(tx, ty)]
                            inner_ok = list(zip(pts[:-1], pts[1:]))
                        if dist > 0:
                            added.append(('track', 1, px, py, vx, vy, STUB_W, net, f'esc:{ref}'))
                            obs.add_seg(1, px, py, vx, vy, STUB_W, net, tag=f'esc:{ref}')
                        added.append(('via', vx, vy, VIA_D, VIA_H, net, f'esc:{ref}'))
                        obs.add_circle('ALL', vx, vy, VIA_D / 2.0, net, tag=f'escvia:{ref}')
                        for (a, b2) in inner_ok:
                            if math.hypot(a[0] - b2[0], a[1] - b2[1]) < 0.05:
                                continue
                            added.append(('track', tl, a[0], a[1], b2[0], b2[1], ESC_W, net, f'esc:{ref}'))
                            obs.add_seg(tl, a[0], a[1], b2[0], b2[1], ESC_W, net, tag=f'esc:{ref}')
                            for (m_net, m_layer), m in maze_cache.items():
                                if m_net != net and m_layer == tl:
                                    m.add_seg(a[0], a[1], b2[0], b2[1], ESC_W / 2.0, 0.0)
                        stage['L_ok'] += 1
                        placed = True
                        break
                    if placed:
                        break
                if placed:
                    done = True
                    break
                stage['inner'] += 1
            elif tl not in (1, 'V'):
                stage['inner'] += 1
        if done:
            fixed += 1
        else:
            failed.append(ref)
    print(f'引出路由: 成功 {fixed}, 失败 {len(failed)}, 阶段={stage}')
    if failed:
        print('  失败清单:', failed)

    # ---- GND 缝合: 每个孤立 GND 焊盘 → 短桩 + 旁孔 ----
    gnd_pads = [(ref, x, y) for (ref, x, y, rw, rh, net) in pad_list if net == 'GND']
    # 只缝孤立 GND 焊盘 (有铜皮直连的不需要)
    gnd_orphans = set()
    for net, lst in [(n, l) for n, l in find_orphans_all(b, tracks, vias).items()]:
        if net == 'GND':
            gnd_orphans = set(lst)
    stitched = 0
    for (ref, px, py) in gnd_pads:
        if ref not in gnd_orphans:
            continue
        placed = False
        for dist in (0.9, 1.1, 1.4, 1.8, 2.3):
            for dx, dy in ((0, 1), (0, -1), (1, 0), (-1, 0),
                           (0.707, 0.707), (-0.707, 0.707), (0.707, -0.707), (-0.707, -0.707)):
                vx, vy = px + dx * dist, py + dy * dist
                if obs.via_blocked(vx, vy, VIA_D / 2.0 + 0.02, 'GND'):
                    continue
                if obs.blocked(1, px, py, vx, vy, STUB_W, 'GND'):
                    continue
                added.append(('track', 1, px, py, vx, vy, STUB_W, 'GND', f'gnd:{ref}'))
                obs.add_seg(1, px, py, vx, vy, STUB_W, 'GND', tag=f'gnd:{ref}')
                added.append(('via', vx, vy, VIA_D, VIA_H, 'GND', f'gnd:{ref}'))
                obs.add_circle('ALL', vx, vy, VIA_D / 2.0, 'GND', tag=f'gndvia:{ref}')
                placed = True
                break
            if placed:
                break
        stitched += placed
    print(f'GND 缝合: {stitched}/{len(gnd_orphans)}')

    # ---- v3 DSN (给 FreeRouting 收尾) ----
    if os.environ.get('V44_DSN', '1') == '1':
        write_v3_dsn(added)

    # ---- 发射 ----
    for item in added:
        if item[0] == 'track':
            _, L, x1, y1, x2, y2, w, net, tag = item
            layer = {1: 'F.Cu', 15: 'In1.Cu', 16: 'In2.Cu', 2: 'B.Cu'}[L]
            b.tracks.append(Track(x1, y1, x2, y2, w, layer, net, eda_frame=True))
        else:
            _, x, y, size, drill, net, tag = item
            b.add_via(x, y, net, size, drill)

    from collections import Counter
    print('最终层分布:', dict(Counter(t.layer for t in b.tracks)))
    print('最终过孔:', len(b.vias))

    outdir = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'output')
    rect = [(0, 0), (BOARD_W, 0), (BOARD_W, BOARD_H), (0, BOARD_H)]
    out = os.path.join(outdir, 'KeyCore-v44.kicad_pcb')
    b.emit_kicad_pcb(out, zones=[('GND', 'B.Cu', rect)])
    print(f'已发射 {out}')


def find_orphans(b, tracks, vias):
    """信号网孤立焊盘 (不含 GND — GND 走缝合)."""
    all_orphans = find_orphans_all(b, tracks, vias)
    out = []
    for net, lst in all_orphans.items():
        if net == 'GND':
            continue
        for ref in lst:
            for c in b.components:
                if c.ref == ref.rsplit('_', 1)[0]:
                    for pd in c.abs_pads:
                        if f"{c.ref}_{pd['num']}" == ref:
                            out.append((ref, pd['x'], pd['y'], net))
    return out


def find_orphans_all(b, tracks, vias):
    """全部孤立焊盘 (端点吸附 + 过段检测, 不含层检查 — SES 同网跨层都算同道)."""
    EPS = 0.03
    result = {}
    import json as _json
    # 复用 find_opens2 逻辑 (保持一致)
    pads_by_net = {}
    for c in b.components:
        for pd in c.abs_pads:
            if pd['net']:
                pads_by_net.setdefault(pd['net'], []).append((f"{c.ref}_{pd['num']}", (pd['x'], pd['y'])))
    tl_by_net, vl_by_net = {}, {}
    for (x1, y1, x2, y2, w, layer, net) in tracks:
        tl_by_net.setdefault(net, []).append((x1, y1, x2, y2))
    for (x, y, size, drill, net) in vias:
        vl_by_net.setdefault(net, []).append((x, y))

    def on_seg(pt, a, b_, tol=0.03):
        if not (min(a[0], b_[0]) - tol <= pt[0] <= max(a[0], b_[0]) + tol):
            return False
        if not (min(a[1], b_[1]) - tol <= pt[1] <= max(a[1], b_[1]) + tol):
            return False
        cross = (b_[0] - a[0]) * (pt[1] - a[1]) - (b_[1] - a[1]) * (pt[0] - a[0])
        return abs(cross) < tol * max(1.0, math.hypot(b_[0] - a[0], b_[1] - a[1]))

    for net, pads in pads_by_net.items():
        if len(pads) < 2:
            continue
        tl = tl_by_net.get(net, [])
        vl = vl_by_net.get(net, [])
        n = len(pads) + len(tl) + len(vl)
        adj = {i: [] for i in range(n)}

        def link(i, j):
            adj[i].append(j)
            adj[j].append(i)
        for i, (ref, xy) in enumerate(pads):
            for j, seg in enumerate(tl):
                k = len(pads) + j
                if any(math.hypot(xy[0] - ex, xy[1] - ey) < EPS for ex, ey in ((seg[0], seg[1]), (seg[2], seg[3]))):
                    link(i, k)
                elif on_seg(xy, (seg[0], seg[1]), (seg[2], seg[3])):
                    link(i, k)
        for j, seg in enumerate(tl):
            k = len(pads) + j
            for vj, (vx, vy) in enumerate(vl):
                vvi = len(pads) + len(tl) + vj
                if any(math.hypot(vx - ex, vy - ey) < EPS for ex, ey in ((seg[0], seg[1]), (seg[2], seg[3]))):
                    link(k, vvi)
                elif on_seg((vx, vy), (seg[0], seg[1]), (seg[2], seg[3])):
                    link(k, vvi)
        for j in range(len(tl)):
            for k in range(j + 1, len(tl)):
                s1, s2 = tl[j], tl[k]
                i1, i2 = len(pads) + j, len(pads) + k
                e1 = ((s1[0], s1[1]), (s1[2], s1[3]))
                e2 = ((s2[0], s2[1]), (s2[2], s2[3]))
                if any(math.hypot(a[0] - c[0], a[1] - c[1]) < EPS for a in e1 for c in e2):
                    link(i1, i2)
                elif seg_seg_dist(s1, s2) < EPS:
                    link(i1, i2)
        seen = {}
        for start in range(n):
            if start in seen:
                continue
            cid = len(set(seen.values()))
            stack = [start]
            while stack:
                u = stack.pop()
                if u in seen:
                    continue
                seen[u] = cid
                stack += adj[u]
        comp_size = {}
        for i in range(n):
            comp_size[seen[i]] = comp_size.get(seen[i], 0) + 1
        biggest = max(comp_size, key=comp_size.get)
        orphans = [pads[i][0] for i in range(len(pads)) if seen[i] != biggest]
        if orphans:
            result[net] = orphans
    return result


if __name__ == '__main__':
    main()
