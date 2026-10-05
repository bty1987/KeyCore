"""本地 DRC: 对 geometry.json 跑间距(0.0889mm)+连接性检查.
输出: drc_report.json  {clearance:[...], connectivity:[...]}
几何: track=胶囊, via=圆, pad=旋转矩形/圆/长圆. 同 net 免检, 同封装 pad-pad 免检.
"""
import json, math, sys
from collections import defaultdict

GEO = json.load(open('/tmp/eprj_probe/geometry.json'))
CLEAR = 0.0889          # 3.5mil 全矩阵
PAD_TOL = 0.05          # 判连通时的容差

TRACKS = GEO['tracks']
VIAS = GEO['vias']
PADS = [p for p in GEO['pads'] if p['net'] or p['hole_t']]  # 有网或通孔
LAYER_MM = {1: 0, 2: 3, 15: 1, 16: 2}   # 统一层号: 0=F,1=In1,2=In2,3=B


def seg_seg_dist(a, b):
    """两线段最小距离"""
    def d_pt_seg(px, py, x1, y1, x2, y2):
        dx, dy = x2-x1, y2-y1
        L2 = dx*dx + dy*dy
        if L2 == 0:
            return math.hypot(px-x1, py-y1)
        t = max(0, min(1, ((px-x1)*dx + (py-y1)*dy)/L2))
        return math.hypot(px-(x1+t*dx), py-(y1+t*dy))
    d1 = d_pt_seg(a[0], a[1], *b)
    d2 = d_pt_seg(b[0], b[1], *a)
    d3 = d_pt_seg(a[2], a[3], *b)
    d4 = d_pt_seg(b[2], b[3], *a)
    return min(d1, d2, d3, d4)


def seg_pt_dist(px, py, seg):
    return seg_seg_dist((px, py, px, py), seg)


class Shape:
    """凸形状: 胶囊/圆/旋转矩形, 支持形状-形状距离"""
    def __init__(self, kind, data, layer, net, tag):
        self.kind, self.d, self.layer, self.net, self.tag = kind, data, layer, net, tag

    def bbox(self):
        if self.kind == 'capsule':
            (x1, y1, x2, y2), r = self.d
            return (min(x1, x2)-r, min(y1, y2)-r, max(x1, x2)+r, max(y1, y2)+r)
        if self.kind == 'circle':
            (x, y), r = self.d
            return (x-r, y-r, x+r, y+r)
        pts = self.d  # 旋转矩形 4 角
        xs = [p[0] for p in pts]; ys = [p[1] for p in pts]
        return (min(xs), min(ys), max(xs), max(ys))


def dist_shapes(a, b):
    if a.kind == 'circle' and b.kind == 'circle':
        return math.hypot(a.d[0][0]-b.d[0][0], a.d[0][1]-b.d[0][1]) - a.d[1] - b.d[1]
    if a.kind == 'circle':
        return dist_shapes(b, a)
    if a.kind == 'circle':  # unreachable
        pass
    if b.kind == 'circle':
        cx, cy, r = b.d[0][0], b.d[0][1], b.d[1]
        if a.kind == 'capsule':
            return seg_pt_dist(cx, cy, a.d[0]) - r
        # rect-circle: 点到 4 边最小距离
        pts = a.d
        best = 1e9
        for i in range(4):
            best = min(best, seg_pt_dist(cx, cy, (pts[i][0], pts[i][1], pts[(i+1) % 4][0], pts[(i+1) % 4][1])))
        return best - r
    if a.kind == 'capsule' and b.kind == 'capsule':
        return seg_seg_dist(a.d[0], b.d[0]) - a.d[1] - b.d[1]
    if a.kind == 'capsule':
        a, b = b, a
    if b.kind == 'capsule':
        # rect vs 胶囊: 胶囊轴到 4 边的最小距离
        (x1, y1, x2, y2), r = b.d
        pts = a.d
        best = 1e9
        for i in range(4):
            best = min(best, seg_seg_dist((x1, y1, x2, y2),
                                          (pts[i][0], pts[i][1], pts[(i+1) % 4][0], pts[(i+1) % 4][1])))
        return best - r
    # rect-rect(凸多边形): 顶点对边的最小距离
    def poly_poly(pA, pB):
        m = 1e9
        for poly1, poly2 in ((pA, pB), (pB, pA)):
            for i in range(len(poly1)):
                p1, p2 = poly1[i], poly1[(i+1) % len(poly1)]
                for q in poly2:
                    m = min(m, seg_pt_dist(q[0], q[1], (p1[0], p1[1], p2[0], p2[1])))
        return m
    return poly_poly(a.d, b.d)


def build_shapes():
    shapes = []
    for t in TRACKS:
        if abs(t['w'] - 0.256) < 0.002:
            continue  # 飞线, 非铜, 不参与 DRC
        lay = LAYER_MM.get(t['layer'])
        if lay is None:
            continue
        shapes.append(Shape('capsule', ((t['x1'], t['y1'], t['x2'], t['y2']), t['w']/2),
                            lay, t['net'], dict(kind='track', net=t['net'], seg=(t['x1'], t['y1'], t['x2'], t['y2']))))
    for v in VIAS:
        shapes.append(Shape('circle', ((v['x'], v['y']), v['dia']/2), 'ALL', v['net'],
                            dict(kind='via', net=v['net'], x=v['x'], y=v['y'], id=v['id'], dia=v['dia'], drill=v['drill'])))
    for p in PADS:
        thru = p['hole_t'] and p['hole_t'] != 'NONE'
        lays = [0, 1, 2, 3] if thru else [LAYER_MM.get(p['layer'], 0)]
        if p['shape'] == 'CIRCLE':
            for lay in lays:
                shapes.append(Shape('circle', ((p['x'], p['y']), p['w']/2), lay, p['net'],
                                    dict(kind='pad', net=p['net'], ref=p['ref'], num=p['num'], x=p['x'], y=p['y'])))
        elif p['shape'] == 'OVAL':
            # 长圆按胶囊近似: 长轴方向为 w>h ? x : y
            L, W = max(p['w'], p['h']), min(p['w'], p['h'])
            ang = math.radians(p['angle'] if p['w'] >= p['h'] else p['angle']+90)
            dx, dy = math.cos(ang)*(L-W)/2, math.sin(ang)*(L-W)/2
            for lay in lays:
                shapes.append(Shape('capsule', ((p['x']-dx, p['y']-dy, p['x']+dx, p['y']+dy), W/2), lay, p['net'],
                                    dict(kind='pad', net=p['net'], ref=p['ref'], num=p['num'], x=p['x'], y=p['y'])))
        else:  # RECT
            ang = math.radians(p['angle'])
            ca, sa = math.cos(ang), math.sin(ang)
            hw, hh = p['w']/2, p['h']/2
            pts = []
            for lx, ly in ((-hw, -hh), (hw, -hh), (hw, hh), (-hw, hh)):
                pts.append((p['x']+lx*ca-ly*sa, p['y']+lx*sa+ly*ca))
            for lay in lays:
                shapes.append(Shape('rect', pts, lay, p['net'],
                                    dict(kind='pad', net=p['net'], ref=p['ref'], num=p['num'], x=p['x'], y=p['y'])))
    return shapes


def run_clearance(shapes):
    """网格加速的同层间距检查"""
    cell = 2.0
    grid = defaultdict(list)
    for i, s in enumerate(shapes):
        x1, y1, x2, y2 = s.bbox()
        for gx in range(int(x1//cell), int(x2//cell)+1):
            for gy in range(int(y1//cell), int(y2//cell)+1):
                grid[(gx, gy)].append(i)
    seen = set()
    viols = []
    for i, s in enumerate(shapes):
        x1, y1, x2, y2 = s.bbox()
        for gx in range(int(x1//cell), int(x2//cell)+1):
            for gy in range(int(y1//cell), int(y2//cell)+1):
                for j in grid[(gx, gy)]:
                    if j <= i:
                        continue
                    o = shapes[j]
                    if s.layer != 'ALL' and o.layer != 'ALL' and s.layer != o.layer:
                        continue
                    if s.net == o.net:
                        continue
                    if s.tag['kind'] == 'pad' and o.tag['kind'] == 'pad' and s.tag['ref'] == o.tag['ref']:
                        continue  # 同封装
                    key = (i, j)
                    if key in seen:
                        continue
                    # bbox 预筛
                    bx1, by1, bx2, by2 = o.bbox()
                    if x1 > bx2+CLEAR or bx1 > x2+CLEAR or y1 > by2+CLEAR or by1 > y2+CLEAR:
                        continue
                    seen.add(key)
                    d = dist_shapes(s, o)
                    if d < CLEAR:
                        viols.append(dict(gap=round(d, 4), a=s.tag, b=o.tag))
    return viols


def run_connectivity():
    """每 net 建图, 找断开的 pad 群 (ratline 排除; pad/track/via 统一并查集)"""
    net_pads = defaultdict(list)
    for i, p in enumerate(PADS):
        if p['net']:
            net_pads[p['net']].append(i)
    def real(t):
        return abs(t['w'] - 0.256) > 0.002
    tr_by_net = defaultdict(list)
    for t in TRACKS:
        if t['net'] and real(t):
            tr_by_net[t['net']].append(t)
    via_by_net = defaultdict(list)
    for v in VIAS:
        if v['net']:
            via_by_net[v['net']].append(v)
    problems = []
    for net, plist in net_pads.items():
        trs = tr_by_net[net]
        vs = via_by_net[net]
        # 元素: ('T', idx) / ('V', idx) / ('P', plist 中的 pi)
        parent = {}
        def find(x):
            parent.setdefault(x, x)
            while parent[x] != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x
        def union(a, b):
            ra, rb = find(a), find(b)
            if ra != rb:
                parent[ra] = rb
        for i in range(len(trs)):
            find(('T', i))
        for i in range(len(vs)):
            find(('V', i))
        for pi in plist:
            find(('P', pi))
        # track-track: 端点重合
        egrid = defaultdict(list)
        for i, t in enumerate(trs):
            for ex, ey in ((t['x1'], t['y1']), (t['x2'], t['y2'])):
                egrid[(round(ex, 2), round(ey, 2))].append(i)
        for ids in egrid.values():
            for a in ids:
                for b in ids:
                    if a != b:
                        union(('T', a), ('T', b))
        # track-track: T 型分叉
        for i, t in enumerate(trs):
            for ex, ey in ((t['x1'], t['y1']), (t['x2'], t['y2'])):
                for j, t2 in enumerate(trs):
                    if i == j:
                        continue
                    if seg_pt_dist(ex, ey, (t2['x1'], t2['y1'], t2['x2'], t2['y2'])) <= t2['w']/2 + 0.02:
                        union(('T', i), ('T', j))
        # via-track / via-via
        for vi, v in enumerate(vs):
            for i, t in enumerate(trs):
                if seg_pt_dist(v['x'], v['y'], (t['x1'], t['y1'], t['x2'], t['y2'])) <= v['dia']/2 + 0.02:
                    union(('V', vi), ('T', i))
            for vj in range(vi+1, len(vs)):
                v2 = vs[vj]
                if math.hypot(v['x']-v2['x'], v['y']-v2['y']) <= (v['dia']+v2['dia'])/2 + 0.02:
                    union(('V', vi), ('V', vj))
        # pad-track / pad-via
        for pi in plist:
            p = PADS[pi]
            r = max(p['w'], p['h'])/2 + PAD_TOL
            for i, t in enumerate(trs):
                if seg_pt_dist(p['x'], p['y'], (t['x1'], t['y1'], t['x2'], t['y2'])) <= r:
                    union(('P', pi), ('T', i))
            thru = bool(p['hole_t'] and p['hole_t'] != 'NONE')
            for vi, v in enumerate(vs):
                d = math.hypot(p['x']-v['x'], p['y']-v['y'])
                # 通孔 pad: 孔与过孔同位即通; 贴片: 焊盘压到过孔环
                lim = (v['dia']/2 + PAD_TOL) if thru else (max(p['w'], p['h'])/2 + v['dia']/2 + PAD_TOL)
                if d <= lim:
                    union(('P', pi), ('V', vi))
        groups = defaultdict(list)
        for pi in plist:
            groups[find(('P', pi))].append(pi)
        if len(groups) > 1:
            gs = sorted(groups.values(), key=len, reverse=True)
            problems.append(dict(net=net, groups=[
                [dict(ref=PADS[pi]['ref'], num=PADS[pi]['num'],
                      x=round(PADS[pi]['x'], 2), y=round(PADS[pi]['y'], 2)) for pi in g]
                for g in gs]))
    return problems

def main():
    shapes = build_shapes()
    print(f"shapes: {len(shapes)} (capsule {sum(1 for s in shapes if s.kind=='capsule')}, "
          f"circle {sum(1 for s in shapes if s.kind=='circle')}, rect {sum(1 for s in shapes if s.kind=='rect')})")
    from collections import Counter
    viols = run_clearance(shapes)
    kinds = Counter()
    for v in viols:
        kinds[tuple(sorted([v['a']['kind'], v['b']['kind']]))] += 1
    print(f"间距违规: {len(viols)}")
    for k, c in kinds.most_common():
        print(f"  {k[0]}-{k[1]}: {c}")
    probs = run_connectivity()
    tot = sum(len(p['groups'])-1 for p in probs)
    print(f"连接性问题: {len(probs)} 个 net, {tot} 处断开")
    for p in probs:
        print(f"  {p['net']}: {len(p['groups'])} 群: " + " | ".join(
            f"{len(g)}pad[{','.join(x['ref']+ '.' +str(x['num']) for x in g[:4])}{'...' if len(g)>4 else ''}]" for g in p['groups']))
    json.dump(dict(clearance=viols, connectivity=probs), open('/tmp/eprj_probe/drc_report.json', 'w'), ensure_ascii=False, indent=1)
    print("saved drc_report.json")


if __name__ == '__main__':
    main()
