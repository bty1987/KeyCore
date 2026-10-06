"""A* 迷宫引出路由器: 0.1mm 栅格, 障碍膨胀, 路径拉直. 供 emit_v44 调用."""
import math
import heapq

CELL = 0.1  # mm


class Maze:
    def __init__(self, w_mm, h_mm, clear=0.13):
        self.w = int(w_mm / CELL) + 2
        self.h = int(h_mm / CELL) + 2
        self.clear = clear
        self.block = bytearray(self.w * self.h)  # 0=free 1=block

    def _disc(self, cx, cy, r, val=1):
        """标记圆盘 (mm 坐标)."""
        x0, x1 = int((cx - r) / CELL), int((cx + r) / CELL) + 1
        y0, y1 = int((cy - r) / CELL), int((cy + r) / CELL) + 1
        r2 = r * r
        for gy in range(max(0, y0), min(self.h, y1 + 1)):
            for gx in range(max(0, x0), min(self.w, x1 + 1)):
                dx, dy = gx * CELL - cx, gy * CELL - cy
                if dx * dx + dy * dy <= r2:
                    self.block[gy * self.w + gx] = val

    def add_seg(self, x1, y1, x2, y2, halfw, inflate):
        """其他网走线段 → 膨胀胶囊."""
        L = math.hypot(x2 - x1, y2 - y1)
        n = max(2, int(L / (CELL * 0.6)))
        r = halfw + inflate
        for i in range(n + 1):
            t = i / n
            self._disc(x1 + (x2 - x1) * t, y1 + (y2 - y1) * t, r)

    def add_circle(self, x, y, r, inflate):
        self._disc(x, y, r + inflate)

    def add_rect(self, cx, cy, hw, hh, inflate):
        """轴对齐矩形 (焊盘), 标记矩形+膨胀."""
        x0 = int((cx - hw - inflate) / CELL)
        x1 = int((cx + hw + inflate) / CELL) + 1
        y0 = int((cy - hh - inflate) / CELL)
        y1 = int((cy + hh + inflate) / CELL) + 1
        for gy in range(max(0, y0), min(self.h, y1 + 1)):
            for gx in range(max(0, x0), min(self.w, x1 + 1)):
                dx = abs(gx * CELL - cx) - hw
                dy = abs(gy * CELL - cy) - hh
                if max(dx, 0) ** 2 + max(dy, 0) ** 2 <= inflate * inflate:
                    self.block[gy * self.w + gx] = 1

    def free(self, gx, gy):
        return 0 <= gx < self.w and 0 <= gy < self.h and not self.block[gy * self.w + gx]

    def nearest_free(self, gx, gy, max_r=60):
        if self.free(gx, gy):
            return gx, gy
        for r in range(1, max_r):
            for dx in range(-r, r + 1):
                for dy in (-r, r):
                    if self.free(gx + dx, gy + dy):
                        return gx + dx, gy + dy
            for dy in range(-r + 1, r):
                for dx in (-r, r):
                    if self.free(gx + dx, gy + dy):
                        return gx + dx, gy + dy
        return None

    def astar(self, start, goal, max_expand=25000):
        """4 邻 A*, 返回栅格路径 or None. max_expand 快速失败."""
        import itertools
        counter = itertools.count()
        openq = [(0, next(counter), start)]
        came, g = {start: None}, {start: 0}
        expand = 0

        def h(p):
            return abs(p[0] - goal[0]) + abs(p[1] - goal[1])
        while openq and expand < max_expand:
            _, _, cur = heapq.heappop(openq)
            expand += 1
            if cur == goal:
                path = []
                while cur is not None:
                    path.append(cur)
                    cur = came[cur]
                return path[::-1]
            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                nxt = (cur[0] + dx, cur[1] + dy)
                if not self.free(*nxt):
                    continue
                ng = g[cur] + 1
                if nxt not in g or ng < g[nxt]:
                    g[nxt] = ng
                    came[nxt] = cur
                    heapq.heappush(openq, (ng + h(nxt), next(counter), nxt))
        return None

    def simplify(self, path_mm, net, layer, width, blocked_fn, tol_checks=3):
        """共线合并 + 拉直试探 (每第3个点试跳)."""
        pts = path_mm[:]
        # 共线合并
        out = [pts[0]]
        for i in range(1, len(pts) - 1):
            a, b, c = out[-1], pts[i], pts[i + 1]
            cross = (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])
            if abs(cross) > 1e-9:
                out.append(b)
        out.append(pts[-1])
        # 拉直
        i = 0
        while i < len(out) - 2:
            best = None
            for j in range(len(out) - 1, i + 1, -1):
                mid_ok = True
                a, bpt = out[i], out[j]
                L = math.hypot(bpt[0] - a[0], bpt[1] - a[1])
                n = max(2, int(L / (CELL * 2)))
                for s in range(n + 1):
                    t = s / n
                    sx, sy = a[0] + (bpt[0] - a[0]) * t, a[1] + (bpt[1] - a[1]) * t
                    if blocked_fn(sx, sy):
                        mid_ok = False
                        break
                if mid_ok:
                    best = j
                    break
            if best:
                out = out[:i + 1] + out[best:]
            i += 1
        return out


def mm2g(v):
    return int(round(v / CELL))


def g2mm(g):
    return g * CELL
