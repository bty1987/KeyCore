"""KeyCore P2 PCB generator — core board model.

Coordinate conventions:
  * EDA frame  : 立创EDA 顶视图, origin = PCB(300x146) 左下角, +y 向后(Esc/宏行侧) —— 与
                 pcb-hall-positions.csv、structure.scad 同一套坐标系。
  * KiCad frame: y 翻转 (ky = 146 - ey)。所有发射到 .kicad_pcb 的几何都先转 KiCad 帧。
  * 设计逻辑（走线深度、上下左右）一律用 EDA 帧描述, 在 EmittedTrack 等发射时统一变换。
"""
import math
import csv as csvmod
from sexpr import parse, emit, find, find_all, pad_at, pad_size, pad_shape, pad_layers, set_net

BOARD_W, BOARD_H = 300.0, 172.0   # v4: +26 加深在宏行侧 (硬件带)
FOOTPRINT_DIR = __file__.rsplit('/', 1)[0] + '/../footprints'

F_CU, B_CU = 'F.Cu', 'B.Cu'


def kx(x): return round(x, 6)
def ky(ey): return round(BOARD_H - ey, 6)


class Track:
    def __init__(self, x1, y1, x2, y2, width, layer, net, eda_frame=True):
        self.eda = eda_frame
        self.p = (x1, y1, x2, y2)
        self.width = width
        self.layer = layer
        self.net = net

    def kpts(self):
        x1, y1, x2, y2 = self.p
        if self.eda:
            return (kx(x1), ky(y1), kx(x2), ky(y2))
        return (kx(x1), kx(y1), kx(x2), kx(y2))


class Via:
    def __init__(self, x, y, net, size=0.6, drill=0.3, eda_frame=True):
        self.x, self.y, self.net = x, y, net
        self.size, self.drill = size, drill
        self.eda = eda_frame

    def kpos(self):
        if self.eda:
            return kx(self.x), ky(self.y)
        return kx(self.x), kx(self.y)


class FootprintLib:
    def __init__(self):
        self.cache = {}

    def load(self, name):
        if name in self.cache:
            return self.cache[name]
        path = f"{FOOTPRINT_DIR}/{name}.kicad_mod"
        with open(path) as f:
            node = parse(f.read())
        self.cache[name] = node
        return node


class Component:
    _seq = 0

    def __init__(self, ref, lib, value, x, y, rot=0, nets=None, eda_frame=True,
                 ref_silk=True, fields=None):
        """nets: {pad_number: net_name}; rot in degrees (EDA frame, CCW positive)."""
        self.ref, self.lib, self.value = ref, lib, value
        self.x, self.y, self.rot = x, y, rot
        self.nets = nets or {}
        self.eda = eda_frame
        self.ref_silk = ref_silk
        self.fields = fields or {}   # extra footprint fields e.g. JLC fn
        self.node = None             # footprint sexpr (filled by Board)
        self.abs_pads = []           # [(number, kx, ky, w, h, rot_k, net)]


class Board:
    def __init__(self):
        self.lib = FootprintLib()
        self.components = []
        self.tracks = []   # Track
        self.vias = []     # Via
        self.holes = []    # (x, y, dia) NPTH, EDA frame
        self.texts = []    # (x, y, text, size, layer, eda_frame)
        self.circles = []  # (x, y, r, layer, width, eda_frame)
        self.lines = []    # (x1,y1,x2,y2, layer, width, eda_frame)
        self.nets = {}     # name -> num
        self.net_order = []

    def net(self, name):
        if name not in self.nets:
            self.nets[name] = len(self.nets) + 1
            self.net_order.append(name)
        return self.nets[name]

    # ---------------- placement ----------------
    def place(self, comp):
        """Resolve footprint, compute absolute pad positions (KiCad frame)."""
        node = self.lib.load(comp.lib)
        import copy
        node = copy.deepcopy(node)
        # KiCad rotation: board uses y-down; an EDA-frame CCW rot r maps to KiCad rot (-r)
        rot_k = (-comp.rot) % 360 if comp.eda else comp.rot
        px = kx(comp.x)
        py = ky(comp.y) if comp.eda else kx(comp.y)
        # set footprint at
        fat = find(node, 'at')
        if fat is None:
            fat = ['at', '0', '0']
            # insert right after (layer ...)
            li = next(i for i, c in enumerate(node) if isinstance(c, list) and c[0] == 'layer')
            node.insert(li + 1, fat)
        fat[1], fat[2] = f"{px}", f"{py}"
        if len(fat) > 3:
            fat[3] = f"{rot_k}"
        else:
            fat.append(f"{rot_k}")
        # layer
        fl = find(node, 'layer')
        if fl:
            fl[1] = 'F.Cu'
        a = find(node, 'attr')
        if a:
            a[1] = 'smd'
            if 'board_only' in comp.fields.values():
                a.append('board_only')
        # reference silk
        rt = None
        for t in find_all(node, 'fp_text'):
            if t[1] == 'reference':
                rt = t
        if rt is None:
            # 封装库无 reference 行: 补一个 (立创导入要求位号唯一, v3 事后脚本的同款格式)
            rt = ['fp_text', 'reference', comp.ref, ['at', '0', '-2.2'],
                  ['layer', 'F.SilkS'],
                  ['effects', ['font', ['size', '0.8', '0.8'], ['thickness', '0.15']]],
                  ['tstamp', '00000000-0000-0000-0000-000000000000']]
            li = next(i for i, c in enumerate(node) if isinstance(c, list) and c[0] == 'layer')
            node.insert(li + 2, rt)
        if rt is not None:
            # fp_text 结构: ['fp_text','reference','REF**',['at',..],..] — 位号在 [2], 不在 [1]
            rt[2] = comp.ref
            if not comp.ref_silk and isinstance(rt[3], list) and rt[3][0] == 'at':
                rt[3][1], rt[3][2] = f"{px + 500}", f"{py}"  # park off-board (hidden ref)
        vt = None
        for t in find_all(node, 'fp_text'):
            if t[1] == 'value':
                vt = t
        if vt is not None:
            vt[2] = comp.value
            vt[3] = f"{px + 500}"
        # remove 3D model refs (stale KISYS3DMOD paths)
        for m in find_all(node, 'model'):
            node.remove(m)
        # net assignment + abs pad geometry
        thetas = [0, 90, 180, 270]
        comp.node = node
        comp.abs_pads = []
        for pad in find_all(node, 'pad'):
            num = pad[1]
            lx, ly, lr = pad_at(pad)
            # KiCad local->world with rotation rot_k (y-down frame, CCW visual = standard math on (x,-y))
            if rot_k == 0:
                wx, wy, wr = lx, ly, lr
            elif rot_k == 90:
                wx, wy, wr = -ly, lx, (lr + 90) % 360
            elif rot_k == 180:
                wx, wy, wr = -lx, -ly, (lr + 180) % 360
            else:  # 270
                wx, wy, wr = ly, -lx, (lr + 270) % 360
            w, h = pad_size(pad)
            netname = comp.nets.get(num, '')
            nnum = self.net(netname) if netname else 0
            set_net(pad, nnum, netname)
            comp.abs_pads.append({
                'num': num, 'x': round(px + wx, 6), 'y': round(py + wy, 6),
                'w': w, 'h': h, 'rot': wr % 180, 'net': netname,
                'shape': pad_shape(pad), 'layers': pad_layers(pad), 'pad': pad,
            })
        self.components.append(comp)
        return comp

    def pad(self, comp_ref, pad_num):
        for c in self.components:
            if c.ref == comp_ref:
                for p in c.abs_pads:
                    if p['num'] == pad_num:
                        return p
        raise KeyError(f"{comp_ref}.{pad_num}")

    def add_track(self, *args, **kw):
        t = Track(*args, **kw)
        self.tracks.append(t)
        return t

    def add_via(self, *args, **kw):
        v = Via(*args, **kw)
        self.vias.append(v)
        return v

    def poly_track(self, pts, width, layer, net, eda_frame=True):
        """Route a polyline; returns list of segments."""
        segs = []
        for a, b in zip(pts, pts[1:]):
            segs.append(self.add_track(a[0], a[1], b[0], b[1], width, layer, net,
                                       eda_frame=eda_frame))
        return segs

    # ---------------- emission ----------------
    def emit_kicad_pcb(self, path, title="KeyCore P2", zones=None):
        out = []
        out.append(['version', '20230121'])
        out.append(['generator', 'keycore_gen'])
        out.append(['generator_version', '1.0'])
        # v4: 四层板声明 (立创导入即建 4 层工程; In1=GND 平面, In2=3V3 平面, 布线 F/B)
        out.append(['layers',
                    ['0', 'F.Cu', 'signal'],
                    ['1', 'In1.Cu', 'signal'],
                    ['2', 'In2.Cu', 'signal'],
                    ['31', 'B.Cu', 'signal'],
                    ['32', 'B.Adhes', 'user'], ['33', 'F.Adhes', 'user'],
                    ['34', 'B.Paste', 'user'], ['35', 'F.Paste', 'user'],
                    ['36', 'B.SilkS', 'user', 'B.Silkscreen'],
                    ['37', 'F.SilkS', 'user', 'F.Silkscreen'],
                    ['38', 'B.Mask', 'user'], ['39', 'F.Mask', 'user'],
                    ['40', 'Dwgs.User', 'user'], ['41', 'Cmts.User', 'user'],
                    ['44', 'Edge.Cuts', 'user'], ['45', 'Margin', 'user']])
        out.append(['setup', ['stackup', ['layer', '0', 'F.Cu', ['type', 'copper'],
                                          ['thickness', '0.035']],
                              ['layer', '1', 'In1.Cu', ['type', 'copper'],
                                          ['thickness', '0.0175']],
                              ['layer', '2', 'In2.Cu', ['type', 'copper'],
                                          ['thickness', '0.0175']],
                              ['layer', '31', 'B.Cu', ['type', 'copper'],
                                          ['thickness', '0.035']]]])
        # nets
        for name in self.net_order:
            out.append(['net', self.nets[name], name])
        # zones (铺铜区): [(net_name, layer, [(x,y)...板框多边形 KiCad 帧])] — v4 内层 GND/3V3 平面
        for znet, zlayer, pts in (zones or []):
            out.append(['zone',
                        ['net', self.nets.get(znet, 0)],
                        ['net_name', znet],
                        ['layer', zlayer],
                        ['tstamp', self._uuid(f"zone-{znet}-{zlayer}")],
                        ['hatch', 'edge', '0.5'],
                        ['connect_pads', ['clearance', '0.25']],
                        ['min_thickness', '0.25'],
                        ['fill', 'yes',
                         ['thermal_gap', '0.5'], ['thermal_bridge_width', '0.5']],
                        ['polygon', ['pts'] + [['xy', f"{x}", f"{y}"] for x, y in pts]]])
        # footprints
        for c in self.components:
            n = c.node
            # pad pad number_uuid? KiCad 7 uses (tstamp) on footprint; add uuid-ish
            if find(n, 'tstamp') is None:
                n.append(['tstamp', self._uuid(f"fp-{c.ref}")])
            for pad in find_all(n, 'pad'):
                if find(pad, 'tstamp') is None:
                    pad.append(['tstamp', self._uuid(f"pad-{c.ref}-{pad[1]}")])
            out.append(n)
        # zones / keepouts: none (LCEDA pours GND)
        # segments
        for t in self.tracks:
            x1, y1, x2, y2 = t.kpts()
            out.append(['segment',
                        ['start', f"{x1}", f"{y1}"],
                        ['end', f"{x2}", f"{y2}"],
                        ['width', f"{t.width}"],
                        ['layer', t.layer],
                        ['net', self.nets.get(t.net, 0)],
                        ['tstamp', self._uuid(f"seg{x1}{y1}{x2}{y2}{t.net}{t.layer}")]])
        for v in self.vias:
            x, y = v.kpos()
            out.append(['via',
                        ['at', f"{x}", f"{y}"],
                        ['size', f"{v.size}"],
                        ['drill', f"{v.drill}"],
                        ['layers', 'F.Cu', 'B.Cu'],
                        ['net', self.nets.get(v.net, 0)],
                        ['tstamp', self._uuid(f"via{x}{y}{v.net}")]])
        # mounting holes as footprints (simple)
        for i, (hx, hy, dia) in enumerate(self.holes):
            kx_, ky_ = kx(hx), ky(hy)
            fp = ['footprint', 'MountingHole:MountingHole_2.7mm',
                  ['layer', 'F.Cu'],
                  ['at', f"{kx_}", f"{ky_}"],
                  ['descr', f"PCB 安装孔 M2.5 (结构支撑柱 #{i+1})"],
                  ['attr', 'board_only', 'exclude_from_pos_files', 'exclude_from_bom'],
                  ['fp_text', 'reference', f"H{i+1}", ['at', '0', '-2.6'],
                   ['layer', 'F.SilkS'], ['effects', ['font', ['size', '0.8', '0.8'], ['thickness', '0.15']]]],
                  ['fp_text', 'value', 'MountingHole_2.7mm', ['at', '0', '2.6'],
                   ['layer', 'F.Fab'], ['effects', ['font', ['size', '0.8', '0.8'], ['thickness', '0.15']]]],
                  ['pad', '""', 'np_thru_hole', 'circle',
                   ['at', '0', '0'], ['size', f"{dia}", f"{dia}"],
                   ['drill', f"{dia}"], ['layers', '*.Cu', '*.Mask'],
                   ['tstamp', self._uuid(f"hole{i}")]],
                  ['tstamp', self._uuid(f"holefp{i}")]]
            out.append(fp)
        # graphics: board outline + silk
        for (x1, y1, x2, y2, layer, width, eda) in self.lines:
            X1, Y1 = (kx(x1), ky(y1)) if eda else (kx(x1), kx(y1))
            X2, Y2 = (kx(x2), ky(y2)) if eda else (kx(x2), kx(y2))
            out.append(['gr_line',
                        ['start', f"{X1}", f"{Y1}"], ['end', f"{X2}", f"{Y2}"],
                        ['layer', layer], ['width', f"{width}"],
                        ['tstamp', self._uuid(f"gl{X1}{Y1}{X2}{Y2}{layer}")]])
        for (cx, cy, r, layer, width, eda) in self.circles:
            X, Y = (kx(cx), ky(cy)) if eda else (kx(cx), kx(cy))
            out.append(['gr_circle',
                        ['center', f"{X}", f"{Y}"], ['end', f"{X + r}", f"{Y}"],
                        ['layer', layer], ['width', f"{width}"],
                        ['tstamp', self._uuid(f"gc{X}{Y}{r}{layer}")]])
        for (tx, ty, text, size, layer, eda) in self.texts:
            X, Y = (kx(tx), ky(ty)) if eda else (kx(tx), kx(ty))
            out.append(['gr_text', text,
                        ['at', f"{X}", f"{Y}"], ['layer', layer],
                        ['effects', ['font', ['size', f"{size}", f"{size}"],
                                     ['thickness', f"{round(size * 0.16, 3)}"]]],
                        ['tstamp', self._uuid(f"gt{X}{Y}{text[:12]}{layer}")]])
        out.append(['embed_fonts', 'false'])
        with open(path, 'w') as f:
            f.write('(kicad_pcb ')
            f.write(' '.join(emit(x) for x in out))
            f.write(')\n')

    @staticmethod
    def _uuid(seed):
        import hashlib
        h = hashlib.md5(seed.encode()).hexdigest()
        s = f"{h[0:8]}-{h[8:12]}-4{h[13:16]}-a{h[17:20]}-{h[20:32]}"
        return s

    # ---------------- geometry queries ----------------
    def pads_flat(self):
        for c in self.components:
            for p in c.abs_pads:
                yield c, p
