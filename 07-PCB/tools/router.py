"""Bottom-layer (B.Cu) grid A* router for KeyCore PCB. Grid 0.25mm, 4-directional."""
import heapq

CELL = 0.125


class BottomRouter:
    def __init__(self, board):
        self.b = board
        self.nx = int(300 / CELL)
        self.ny = int(146 / CELL)
        self.blocked = bytearray(self.nx * self.ny)   # 静态: 焊盘/过孔/孔/边界
        self.dyn = bytearray(self.nx * self.ny)       # 动态: 已布导线
        self.routes = []                               # (net, pts, width)
        self._scatter_static()

    # ---------- coordinate helpers (EDA frame) ----------
    def cell_of(self, x, y):
        return int(x / CELL), int(y / CELL)

    def center_of(self, i, j):
        return i * CELL + CELL / 2, j * CELL + CELL / 2

    def _fill_disc(self, x, y, r, target=None):
        tgt = self.blocked if target is None else target
        i0, i1 = int(max(0, (x - r) / CELL)), int(min(self.nx - 1, (x + r) / CELL))
        j0, j1 = int(max(0, (y - r) / CELL)), int(min(self.ny - 1, (y + r) / CELL))
        r2 = r * r
        for i in range(i0, i1 + 1):
            dx2 = (i * CELL + CELL / 2 - x) ** 2
            for j in range(j0, j1 + 1):
                dy = j * CELL + CELL / 2 - y
                if dx2 + dy * dy <= r2:
                    tgt[j * self.nx + i] = 1

    def _fill_thick_seg(self, x1, y1, x2, y2, half, target=None):
        import math
        tgt = self.blocked if target is None else target
        L = math.hypot(x2 - x1, y2 - y1)
        if L < 1e-9:
            self._fill_disc(x1, y1, half, tgt)
            return
        ux, uy = (x2 - x1) / L, (y2 - y1) / L
        steps = int(L / (CELL / 2)) + 1
        for s in range(steps + 1):
            t = min(1.0, s / steps)
            self._fill_disc(x1 + ux * L * t, y1 + uy * L * t, half, tgt)

    def _scatter_static(self):
        """Obstacles that exist before any routing (EDA frame)."""
        W = 0.125 + 0.25  # trace half-width + clearance
        # board boundary margin
        for i in range(self.nx):
            for j in range(self.ny):
                x, y = self.center_of(i, j)
                if x < 0.5 or x > 299.5 or y < 0.5 or y > 145.5:
                    self.blocked[j * self.nx + i] = 1
        # pads as exact rects (pad rot is multiple of 90 after placement)
        for c, p in self.b.pads_flat():
            self._fill_rect(p['x'], 146 - p['y'], p['w'], p['h'], p['rot'])
        # vias
        for v in self.b.vias:
            self._fill_disc(v.x, v.y, v.size / 2 + 0.375)
        # mounting holes
        for hx, hy, dia in self.b.holes:
            self._fill_disc(hx, hy, dia / 2 + 0.4)

    def _fill_rect(self, x, y, w, h, rot):
        """Exact rotated-rect obstacle (pad rot is 0/90 after placement)."""
        if rot % 180 == 90:
            w, h = h, w
        hw, hh = w / 2 + 0.375, h / 2 + 0.375
        i0, i1 = int(max(0, (x - hw) / CELL)), int(min(self.nx - 1, (x + hw) / CELL))
        j0, j1 = int(max(0, (y - hh) / CELL)), int(min(self.ny - 1, (y + hh) / CELL))
        for i in range(i0, i1 + 1):
            if abs(i * CELL + CELL / 2 - x) > hw:
                continue
            for j in range(j0, j1 + 1):
                if abs(j * CELL + CELL / 2 - y) <= hh:
                    self.blocked[j * self.nx + i] = 1

    def mark_routed(self, pts, width=0.25):
        for a, b in zip(pts, pts[1:]):
            self._fill_thick_seg(a[0], a[1], b[0], b[1], width / 2 + 0.375, target=self.dyn)

    # ---- 已布路线台账 + 违规检测 / 拆除 ----
    def remember(self, net, pts, width):
        self.routes.append((net, pts, width))

    def rebuild_dyn(self):
        self.dyn = bytearray(self.nx * self.ny)
        for net, pts, width in self.routes:
            self.mark_routed(pts, width)

    def route_relaxed(self, start, goal, esc_s=(0, 0), esc_g=(0, 0)):
        saved = self.dyn
        self.dyn = bytearray(self.nx * self.ny)
        pts = self.route(start, goal, esc_s=esc_s, esc_g=esc_g)
        self.dyn = saved
        return pts

    def blockers(self, net, pts, width, clear=0.2):
        from checks import seg_seg_dist, pt_seg_dist
        segs = list(zip(pts, pts[1:]))
        out = set()
        for onet, opts, ow in self.routes:
            if onet == net:
                continue
            for (a1, a2) in segs:
                for (b1, b2) in zip(opts, opts[1:]):
                    if seg_seg_dist(a1, a2, b1, b2) - width / 2 - ow / 2 < clear - 1e-6:
                        out.add(onet)
        for v in self.b.vias:
            if v.net and v.net != net:
                for (a, b) in segs:
                    if pt_seg_dist((v.x, v.y), a, b) - width / 2 - v.size / 2 < clear - 1e-6:
                        out.add(('__via__', v.x, v.y))
        return out

    def remove_route(self, target):
        self.routes = [r for r in self.routes if r[0] != target]
        # 从 board 移除该网 tracks
        self.b.tracks = [t for t in self.b.tracks if not (t.layer == 'B.Cu' and t.net == target)]
        self.rebuild_dyn()

    def violation(self, net, pts, width, clear=0.2):
        # 新路线 vs 已布路线 / 静态过孔 / 安装孔 (异网) 的间距检查
        from checks import seg_seg_dist, pt_seg_dist
        segs = list(zip(pts, pts[1:]))

        def seg_point_dist(a, b, p):
            return pt_seg_dist(p, a, b)

        for onet, opts, ow in self.routes:
            if onet == net:
                continue
            for (a1, a2) in segs:
                for (b1, b2) in zip(opts, opts[1:]):
                    d = seg_seg_dist(a1, a2, b1, b2) - width / 2 - ow / 2
                    if d < clear - 1e-6:
                        return True
        # 静态过孔 (EDA 帧)
        for v in self.b.vias:
            if v.net == net or not v.net:
                continue
            for (a, b) in segs:
                d = seg_point_dist(a, b, (v.x, v.y)) - width / 2 - v.size / 2
                if d < clear - 1e-6:
                    return True
        # 安装孔
        for hx, hy, dia in self.b.holes:
            for (a, b) in segs:
                d = seg_point_dist(a, b, (hx, hy)) - width / 2 - dia / 2
                if d < 0.3 - 1e-6:
                    return True
        return False

    def remove(self, net, pts):
        self.routes = [r for r in self.routes if r[1] != pts]
        self.rebuild_dyn()

    # ---------- A* ----------
    def route(self, start, goal, extra_free=(), esc_s=(0, 0), esc_g=(0, 0)):
        """start/goal (x,y) EDA frame. esc_*: 焊盘长轴逃生方向 (EDA 单位向量).
        解冻 = 自身 1.2mm 盘 + 沿逃生轴 1.8mm 走廊 (只覆盖自身焊盘, 不触 1.27 邻脚)."""
        si, sj = self.cell_of(*start)
        gi, gj = self.cell_of(*goal)
        free = set()

        def free_disc(x, y, r2=23, rng=5):
            ci, cj = self.cell_of(x, y)
            for di in range(-rng, rng + 1):
                for dj in range(-rng, rng + 1):
                    if di * di + dj * dj <= r2:
                        free.add((ci + di, cj + dj))

        def free_corridor(x, y, dx, dy):
            ex, ey = x + dx * 3.6, y + dy * 3.6
            for st in range(11):
                t = st / 10
                free_disc(x + (ex - x) * t, y + (ey - y) * t, r2=3, rng=2)

        free_disc(*start)
        free_disc(*goal)
        if esc_s != (0, 0):
            free_corridor(start[0], start[1], esc_s[0], esc_s[1])
        if esc_g != (0, 0):
            free_corridor(goal[0], goal[1], esc_g[0], esc_g[1])
        for (fx, fy) in tuple(extra_free):
            free_disc(fx, fy)
        nx, ny = self.nx, self.ny
        stat, dyn = self.blocked, self.dyn
        INF = float('inf')

        def passable(i, j):
            k = j * nx + i
            return not stat[k] or (i, j) in free

        def h(i, j):
            return abs(i - gi) + abs(j - gj)

        startk = (si, sj)
        pq = [(h(si, sj), 0.0, startk, -1)]
        dist = {startk: 0.0}
        parent = {startk: None}
        parentdir = {startk: -1}
        found = None
        while pq:
            f, g, node, pdir = heapq.heappop(pq)
            if g > dist.get(node, INF) + 1e-12:
                continue
            if node == (gi, gj):
                found = node
                break
            i, j = node
            for d, (di, dj) in enumerate(((1, 0), (-1, 0), (0, 1), (0, -1))):
                ni, nj = i + di, j + dj
                if ni < 0 or nj < 0 or ni >= nx or nj >= ny:
                    continue
                if not passable(ni, nj):
                    continue
                if dyn[nj * nx + ni] and (ni, nj) not in free:
                    continue
                ng = g + 1.0 + (0.35 if d != pdir else 0.0)
                nxt = (ni, nj)
                if ng < dist.get(nxt, INF) - 1e-12:
                    dist[nxt] = ng
                    parent[nxt] = node
                    parentdir[nxt] = d
                    heapq.heappush(pq, (ng + h(ni, nj), ng, nxt, d))
        if found is None:
            return None
        # reconstruct
        cells = []
        node = found
        while node is not None:
            cells.append(node)
            node = parent[node]
        cells.reverse()
        # simplify collinear runs, then snap ends to exact pin coordinates
        pts = [self.center_of(*cells[0])]
        for idx in range(1, len(cells) - 1):
            i, j = cells[idx]
            pi, pj = cells[idx - 1]
            ni, nj = cells[idx + 1]
            if (i - pi, j - pj) != (ni - i, nj - j):
                pts.append(self.center_of(i, j))
        pts.append(self.center_of(*cells[-1]))
        # 端点吸附到精确焊盘/过孔坐标 (首尾短段保持近直)
        if (abs(pts[0][0] - start[0]) + abs(pts[0][1] - start[1])) > 0.01:
            pts.insert(0, (float(start[0]), float(start[1])))
        if (abs(pts[-1][0] - goal[0]) + abs(pts[-1][1] - goal[1])) > 0.01:
            pts.append((float(goal[0]), float(goal[1])))
        return pts
