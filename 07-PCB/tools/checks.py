"""Geometry & electrical self-checks for the generated board (EDA frame)."""
import math
from collections import defaultdict

CLEAR = 0.20          # copper clearance (嘉立创工艺线 0.15, 留裕量取 0.2)
EDGE_CLEAR = 0.35     # copper to board edge


def seg_seg_dist(p1, p2, p3, p4):
    def dot(a, b): return a[0] * b[0] + a[1] * b[1]
    def sub(a, b): return (a[0] - b[0], a[1] - b[1])
    def add(a, b): return (a[0] + b[0], a[1] + b[1])
    def mul(a, s): return (a[0] * s, a[1] * s)

    def pt_seg(p, a, b):
        ab = sub(b, a)
        ab2 = dot(ab, ab)
        if ab2 < 1e-12:
            return math.hypot(p[0] - a[0], p[1] - a[1])
        t = max(0.0, min(1.0, dot(sub(p, a), ab) / ab2))
        c = add(a, mul(ab, t))
        return math.hypot(p[0] - c[0], p[1] - c[1])

    (x1, y1), (x2, y2), (x3, y3), (x4, y4) = p1, p2, p3, p4
    d1 = sub(p2, p1); d2 = sub(p4, p3); r = sub(p1, p3)
    a = dot(d1, d1); e = dot(d2, d2); f = dot(d2, r)
    if a < 1e-12 and e < 1e-12:
        return math.hypot(r[0], r[1])
    if a < 1e-12:
        return pt_seg(p1, p3, p4)
    if e < 1e-12:
        return pt_seg(p3, p1, p2)
    c = dot(d1, r); b = dot(d1, d2)
    denom = a * e - b * b
    s = 0.0 if denom < 1e-12 else max(0.0, min(1.0, (b * f - c * e) / denom))
    t = (b * s + f) / e
    if t < 0:
        t = 0.0; s = max(0.0, min(1.0, -c / a))
    elif t > 1:
        t = 1.0; s = max(0.0, min(1.0, (b - c) / a))
    c1 = add(p1, mul(d1, s)); c2 = add(p3, mul(d2, t))
    return math.hypot(c1[0] - c2[0], c1[1] - c2[1])


def pt_seg_dist(p, a, b):
    ab = (b[0] - a[0], b[1] - a[1])
    ab2 = ab[0] * ab[0] + ab[1] * ab[1]
    if ab2 < 1e-12:
        return math.hypot(p[0] - a[0], p[1] - a[1])
    t = max(0.0, min(1.0, ((p[0] - a[0]) * ab[0] + (p[1] - a[1]) * ab[1]) / ab2))
    c = (a[0] + ab[0] * t, a[1] + ab[1] * t)
    return math.hypot(p[0] - c[0], p[1] - c[1])


def rect_corners(x, y, w, h, rot):
    if rot % 180 == 90:
        w, h = h, w
    hw, hh = w / 2, h / 2
    return [(x - hw, y - hh), (x + hw, y - hh), (x + hw, y + hh), (x - hw, y + hh)]


def seg_rect_dist(p1, p2, corners):
    best = min(pt_seg_dist(c, p1, p2) for c in corners)
    # also check segment endpoints/edges crossing inside rect
    for a, b in zip(corners, corners[1:] + corners[:1]):
        best = min(best, seg_seg_dist(p1, p2, a, b))
    # if segment fully inside rect
    xmin = min(c[0] for c in corners); xmax = max(c[0] for c in corners)
    ymin = min(c[1] for c in corners); ymax = max(c[1] for c in corners)
    for p in (p1, p2):
        if xmin <= p[0] <= xmax and ymin <= p[1] <= ymax:
            return 0.0
    # segment crossing rect interior
    for a, b in zip(corners, corners[1:] + corners[:1]):
        if seg_seg_dist(p1, p2, a, b) == 0.0:
            return 0.0
    return best


class Checker:
    def __init__(self, board, rep_circles, edge=(300.0, 146.0)):
        self.b = board
        self.rep = rep_circles  # (x,y,r) EDA frame, F.Cu keepout
        self.W, self.H = edge
        self.items = []  # (kind, layer, net, data)
        self.issues = []

    def add_all(self):
        b = self.b
        for c, p in b.pads_flat():
            for L in ('F', 'B'):
                if f'{L}.Cu' in ''.join(p['layers']):
                    self.items.append(('pad', L, p['net'], (c.ref, p['num'], p['x'], 146 - p['y'],
                                                            p['w'], p['h'], p['rot'])))
        for t in b.tracks:
            x1, y1, x2, y2 = t.kpts()  # KiCad frame
            L = 'F' if t.layer == 'F.Cu' else 'B'
            self.items.append(('trk', L, t.net, (x1, 146 - y1, x2, 146 - y2, t.width)))
        for v in b.vias:
            x, y = v.kpos()
            self.items.append(('via', 'F', v.net, (x, 146 - y, v.size)))
            self.items.append(('via', 'B', v.net, (x, 146 - y, v.size)))

    # spatial hash
    def _bucket(self, x, y, s=4.0):
        return (int(x // s), int(y // s))

    def check_clearance(self):
        grid = defaultdict(list)
        for idx, it in enumerate(self.items):
            cx, cy = self._center(it)
            gx, gy = self._bucket(cx, cy)
            for dx in (-1, 0, 1):
                for dy in (-1, 0, 1):
                    grid[(gx + dx, gy + dy)].append(idx)
        seen = set()
        for idx, it in enumerate(self.items):
            cx, cy = self._center(it)
            gx, gy = self._bucket(cx, cy)
            for dx in (-1, 0, 1):
                for dy in (-1, 0, 1):
                    for jdx in grid.get((gx + dx, gy + dy), ()):
                        if jdx <= idx:
                            continue
                        key = (idx, jdx)
                        if key in seen:
                            continue
                        seen.add(key)
                        self._pair(it, self.items[jdx])

    def _center(self, it):
        kind, L, net, d = it
        if kind == 'pad':
            return d[2], d[3]
        if kind == 'via':
            return d[0], d[1]
        return (d[0] + d[2]) / 2, (d[1] + d[3]) / 2

    def _net(self, it): return it[2]

    def _shape_dist(self, a, b):
        """min distance between two items (already known same layer), items in item-tuple form."""
        def info(it):
            kind, L, net, d = it
            return kind, d
        ka, da = info(a); kb, db = info(b)

        def pad_rect(d):
            _, _, x, y, w, h, rot = d
            return rect_corners(x, y, w, h, rot)

        if ka == 'pad' and kb == 'pad':
            ca, cb = pad_rect(da), pad_rect(db)
            best = 1e9
            for a1, a2 in zip(ca, ca[1:] + ca[:1]):
                for b1, b2 in zip(cb, cb[1:] + cb[:1]):
                    best = min(best, seg_seg_dist(a1, a2, b1, b2))
            # inside checks
            def inside(pt, cs):
                xmin = min(c[0] for c in cs); xmax = max(c[0] for c in cs)
                ymin = min(c[1] for c in cs); ymax = max(c[1] for c in cs)
                return xmin <= pt[0] <= xmax and ymin <= pt[1] <= ymax
            if inside((da[2], da[3]), cb) or inside((db[2], db[3]), ca):
                return 0.0
            return best
        if ka == 'pad' and kb == 'trk':
            return seg_rect_dist((db[0], db[1]), (db[2], db[3]), pad_rect(da))
        if ka == 'trk' and kb == 'pad':
            return seg_rect_dist((da[0], da[1]), (da[2], da[3]), pad_rect(db))
        if ka == 'trk' and kb == 'trk':
            return seg_seg_dist((da[0], da[1]), (da[2], da[3]), (db[0], db[1]), (db[2], db[3]))
        if ka == 'via' and kb == 'via':
            return math.hypot(da[0] - db[0], da[1] - db[1])
        if ka == 'via' and kb == 'pad':
            return min(max(0.0, seg_rect_dist((da[0], da[1]), (da[0], da[1]), pad_rect(db))), 1e9)
        if ka == 'pad' and kb == 'via':
            return min(max(0.0, seg_rect_dist((db[0], db[1]), (db[0], db[1]), pad_rect(da))), 1e9)
        if ka == 'via' and kb == 'trk':
            return pt_seg_dist((da[0], da[1]), (db[0], db[1]), (db[2], db[3]))
        if ka == 'trk' and kb == 'via':
            return pt_seg_dist((db[0], db[1]), (da[0], da[1]), (da[2], da[3]))
        raise ValueError

    def _eff_dist(self, it):
        kind, L, net, d = it
        if kind == 'pad':
            return 0.0
        if kind == 'via':
            return d[2] / 2
        return d[4] / 2

    def _pair(self, a, b):
        L1, net1 = a[1], self._net(a)
        L2, net2 = b[1], self._net(b)
        if L1 != L2:
            return
        same_fp = False
        if a[0] == 'pad' and b[0] == 'pad':
            same_fp = a[3][0] == b[3][0]
        if net1 and net1 == net2:
            return
        if same_fp:
            return
        d = self._shape_dist(a, b) - self._eff_dist(a) - self._eff_dist(b)
        if d < CLEAR - 1e-6:
            self.issues.append(('clear', f"{a} X {b} gap={d:.3f}"))

    def check_edge(self):
        for it in self.items:
            kind, L, net, d = it
            if kind == 'pad':
                x, y, w, h, rot = d[2], d[3], d[4], d[5], d[6]
                if rot % 180 == 90:
                    w, h = h, w
                m = min(x - w / 2, y - h / 2, self.W - (x + w / 2), self.H - (y + h / 2))
                if m < EDGE_CLEAR - 1e-6 and x < self.W - 1:  # allow edge-pads (USB-C) by x<W-1?? no:
                    pass
                if m < EDGE_CLEAR - 1e-6:
                    # edge connectors intentionally reach board edge — flag only if fully outside
                    if x + w / 2 > self.W + 0.01 or y + h / 2 > self.H + 0.01 or x - w / 2 < -0.01 or y - h / 2 < -0.01:
                        self.issues.append(('edge', f"pad {d[0]}.{d[1]} out of board"))
            elif kind == 'via':
                x, y, s = d
                m = min(x - s / 2, y - s / 2, self.W - (x + s / 2), self.H - (y + s / 2))
                if m < EDGE_CLEAR - 1e-6:
                    self.issues.append(('edge', f"via {x},{y} too close to edge {m:.2f}"))
            else:
                for (px, py) in ((d[0], d[1]), (d[2], d[3])):
                    if px < EDGE_CLEAR or py < EDGE_CLEAR or px > self.W - EDGE_CLEAR or py > self.H - EDGE_CLEAR:
                        self.issues.append(('edge', f"track endpoint {px},{py} near edge"))

    def check_holes(self, holes=(), clear=0.3):
        for hx, hy, dia in (holes or getattr(self, '_holes', ())):
            for it in self.items:
                kind, L, net, d = it
                if kind == 'pad':
                    x, y, w, h = d[2], d[3], d[4], d[5]
                    m = max(abs(x - hx) - w / 2, abs(y - hy) - h / 2)
                    if m < dia / 2 + clear:
                        self.issues.append(('hole', f"pad {d[0]}.{d[1]} too close to hole @{hx},{hy}"))
                elif kind == 'via':
                    if math.hypot(d[0] - hx, d[1] - hy) < dia / 2 + clear + d[2] / 2:
                        self.issues.append(('hole', f"via {d[0]},{d[1]} too close to hole"))
                else:
                    dd = pt_seg_dist((hx, hy), (d[0], d[1]), (d[2], d[3])) - d[4] / 2
                    if dd < dia / 2 + clear:
                        self.issues.append(('hole', f"track seg {d[:4]} too close to hole @{hx},{hy}"))

    def check_rep(self):
        """no top copper inside rep circles."""
        for it in self.items:
            if it[1] != 'F':
                continue
            kind, L, net, d = it
            for (cx, cy, r) in self.rep:
                if kind == 'pad':
                    x, y = d[2], d[3]
                    if math.hypot(x - cx, y - cy) < r + max(d[4], d[5]) / 2:
                        self.issues.append(('rep', f"pad {d[0]}.{d[1]} inside rep circle @{cx},{cy}"))
                elif kind == 'via':
                    if math.hypot(d[0] - cx, d[1] - cy) < r + d[2] / 2 + 0.2:
                        self.issues.append(('rep', f"via {d[0]},{d[1]} inside rep circle"))
                else:
                    pass  # 细线允许从胶点下方(阻焊上)穿过; 过孔/焊盘仍禁止

    # ---------- connectivity ----------
    def check_connectivity(self, skip_nets=('', 'GND')):
        dsu = {}

        def find(x):
            while dsu[x] != x:
                dsu[x] = dsu[dsu[x]]
                x = dsu[x]
            return x

        def union(a, b):
            ra, rb = find(a), find(b)
            if ra != rb:
                dsu[ra] = rb

        # nodes: ('pad', ref, num) ('via', i) ('trkpt', i, 0/1)
        nodes = {}
        pads_by_net = defaultdict(list)
        for c, p in self.b.pads_flat():
            if p['net']:
                nodes[('pad', c.ref, p['num'])] = (p['x'], 146 - p['y'])
                pads_by_net[p['net']].append(('pad', c.ref, p['num']))
        vias_by_net = defaultdict(list)
        for i, v in enumerate(self.b.vias):
            nodes[('via', i)] = (v.kpos()[0], v.kpos()[1])
            vias_by_net[v.net].append(('via', i))
        segs_by_net = defaultdict(list)
        for i, t in enumerate(self.b.tracks):
            x1, y1, x2, y2 = t.kpts()
            segs_by_net[t.net].append((i, (x1, 146 - y1), (x2, 146 - y2)))
        all_nodes = set(pads_by_net.keys().__iter__().__next__() if False else [])
        for net, ns in list(pads_by_net.items()) + list(vias_by_net.items()):
            for n in ns:
                dsu[n] = n
        for net, segs in segs_by_net.items():
            for i, a, bb in segs:
                nodes[('seg', i, 0)] = a
                nodes[('seg', i, 1)] = bb
                dsu[('seg', i, 0)] = ('seg', i, 0)
                dsu[('seg', i, 1)] = ('seg', i, 1)
        # union pads+vias+seg endpoints coincident
        # bucket all nodes
        buck = defaultdict(list)
        for n, (x, y) in nodes.items():
            buck[(round(x, 2), round(y, 2))].append(n)
        for k, ns in buck.items():
            for n in ns[1:]:
                union(ns[0], n)
        # endpoint-on-segment joins
        for net, segs in segs_by_net.items():
            for i, a, bb in segs:
                for (pt, an) in ((a, ('seg', i, 0)), (bb, ('seg', i, 1))):
                    for (n, (x, y)) in nodes.items():
                        if abs(x - pt[0]) < 0.05 and abs(y - pt[1]) < 0.05:
                            union(an, n)
                            continue
                    # point on segment interior
                    for j, c, dd in segs:
                        if j == i:
                            continue
                        if pt_seg_dist(pt, c, dd) < 0.05:
                            union(an, ('seg', j, 0))
                            union(an, ('seg', j, 1))
                # pad under segment endpoints handled by bucket
        problems = []
        for net, ns in list(pads_by_net.items()):
            if net in skip_nets:
                continue
            groups = defaultdict(int)
            for n in ns:
                groups[find(n)] += 1
            if len(groups) > 1:
                sizes = sorted(groups.values(), reverse=True)
                problems.append((net, len(groups), sizes))
        return problems
