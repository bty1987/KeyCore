"""KeyCore P2 PCB v4.3 — 300x172 四层板: 67×HAL49E + 9×74HC4051 + ESP32-S3-WROOM-1-N4.

v4.3 (2026-10-04): 键场整体下移 9mm(CSV v5.2 hall_y 已含), 前边框 23.8→14.8mm;
  RAILS/LANE 随之 −9; 硬件带/USB/模组/安装孔不动.

v4 形态改版 (2026-10-02, 用户拍板): 空格排 = 键盘最底边, 元件带全部翻到宏行侧.
  * 板加深 146→172 (+26 在宏行侧); 霍尔/母线/CSV 坐标一根不动.
  * 元件带 (ESP32/USB-C/LDO/4051/按键/阴容) 全部移入 y≈136~172 硬件带;
    USB-C 在顶边 (y=172, x=150) 出线, 嘴朝板外.
  * ESP32 天线朝顶边: 天线禁布区 EDA x 271~289, y 159~169 (无铜/无过孔红线).
  * 布线策略: 放置-only 发射, 立创 EDA 内 4 层 (F/B/In1/In2) + GND/3V3 内层平面,
    自动布线所有网络. 本文件不再做底层 A* 手布 (route_bottom 已删除).

坐标系: EDA 帧 (立创EDA 顶视图, 原点左下角, +y 向 Esc/宏行). 发射时翻转为 KiCad 帧.

区域 (EDA y):
  y 0~23     前缘留空 (安装孔锚 + 3V3 干线 Lane), 对应厚板前 23.8mm 边框
  y 23~137   键区: 67 霍尔 + 行母线 (不动)
  y 136~172  硬件带: 9×4051 一排 (y=143) + 上排器件 + USB-C 顶边 + ESP32 右端
"""
import csv as csvmod
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from board import Board, Component, Track, BOARD_W, BOARD_H
from checks import Checker

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
CSV_PATH = os.path.join(ROOT, '02-结构图纸', 'pcb-hall-positions.csv')

HALL_LIB = 'HAL_SOT-23'
MUX_LIB = 'SOIC-16_3.9x9.9mm_P1.27mm'
# v1.7 (霍尔 y-5.5): 行母线位于本行 rep1 带与上一行 rep2 带之间的空隙
RAILS = {'R1': 90.3, 'R2': 71.25, 'R3': 52.2, 'R4': 33.15, 'R5': 14.6, 'M': 109.35}  # v4.3: 随场 −9
LANE_3V3 = 13.2   # v4.3: 随场 −9
TRUNK_3V3_X = 291.0
# ---- 硬件带 (v4) ----
MUX_Y = 143.0                                    # 4051 排中心
MUX_XS = [26, 54, 82, 110, 138, 166, 194, 222, 250]
STUB_S = 148.0                                   # 南排桩过孔 y
MOUNT_HOLES = [(6, 6), (150, 6), (294, 6),       # 前排 3 锚 (不动)
               (6, 165), (294, 165), (150, 135)]  # 背排: 两角 + 中部 (M 行 OUT 走线均在 x<150)
MOD_X, MOD_Y = 280.0, 150.0   # ESP32-S3 模组中心, rot=0 → 天线朝顶边(+y)
# 天线禁布区: 封装 -y 端 → EDA y MOD_Y+9 ~ MOD_Y+19 → 159~169, x 271~289. ★红线

_pin_lut = {
    1: (-8.5, -8.255), 2: (-8.5, -6.985), 3: (-8.5, -5.715), 4: (-8.5, -4.445),
    5: (-8.5, -3.175), 6: (-8.5, -1.905), 7: (-8.5, -0.635), 8: (-8.5, 0.635),
    9: (-8.5, 1.905), 10: (-8.5, 3.175), 11: (-8.5, 4.445), 12: (-8.5, 5.715),
    13: (-8.5, 6.985), 14: (-8.5, 8.255),
    15: (-6.985, 9.255), 16: (-5.715, 9.255), 17: (-4.445, 9.255), 18: (-3.175, 9.255),
    19: (-1.905, 9.255), 20: (-0.635, 9.255), 21: (0.635, 9.255), 22: (1.905, 9.255),
    23: (3.175, 9.255), 24: (4.445, 9.255), 25: (5.715, 9.255), 26: (6.985, 9.255),
    27: (8.5, 8.255), 28: (8.5, 6.985), 29: (8.5, 5.715), 30: (8.5, 4.445),
    31: (8.5, 3.175), 32: (8.5, 1.905), 33: (8.5, 0.635), 34: (8.5, -0.635),
    35: (8.5, -1.905), 36: (8.5, -3.175), 37: (8.5, -4.445), 38: (8.5, -5.715),
    39: (8.5, -6.985), 40: (8.5, -8.255),
}
GPIO_PIN = {2: 38, 4: 4, 5: 5, 6: 6, 7: 7, 8: 12, 9: 17, 10: 18, 11: 19, 12: 20,
            13: 21, 14: 22, 15: 8, 16: 9, 17: 10, 18: 11, 21: 23, 0: 27}
E_GPIO = {1: 8, 2: 9, 3: 10, 4: 11, 5: 12, 6: 13, 7: 14, 8: 15, 9: 16}


def modp(pin):
    """模组脚 EDA 坐标 (rot=0: footprint (lx,ly) → EDA (MOD_X+lx, MOD_Y−ly), 天线朝+y)."""
    lx, ly = _pin_lut[pin]
    return (MOD_X + lx, MOD_Y - ly)


P = {g: modp(p) for g, p in GPIO_PIN.items()}

MUX_PIN = {  # (焊盘号, EDA dx, EDA dy)  EDA rot270 → KiCad rot90: (lx,ly)->(-ly,lx); dy<0=北桩
    'X0': ('13', 0.635, -2.475), 'X1': ('14', 1.905, -2.475), 'X2': ('15', 3.175, -2.475),
    'X3': ('12', -0.635, -2.475), 'A': ('11', -1.905, -2.475), 'B': ('10', -3.175, -2.475),
    'C': ('9', -4.445, -2.475), 'VDD': ('16', 4.445, -2.475),
    'X4': ('1', 4.445, 2.475), 'X5': ('5', -0.635, 2.475), 'X6': ('2', 3.175, 2.475),
    'X7': ('4', 0.635, 2.475), 'Z': ('3', 1.905, 2.475), 'E': ('6', -1.905, 2.475),
    'VEE': ('7', -3.175, 2.475), 'VSS': ('8', -4.445, 2.475),
}

FIELD_SIGS = ('X0', 'X1', 'X2', 'X3', 'A', 'B', 'C', 'VDD')  # 北排: in-pad 过孔下底层
EDGE_SIGS = ('X4', 'X5', 'X6', 'X7', 'Z', 'E')               # 南排: 短桩向南

RES_C = {'10K': 'C17414', '100R': 'C17408', '1K': 'C17513', '4.7K': 'C17673', '5.1K': 'C27834'}
CAP_C = {'0.1uF': 'C28233', '10uF': 'C15850', '22uF': 'C45783', '22nF': 'C1729'}


def load_keys():
    keys = []
    with open(CSV_PATH, encoding='utf-8') as f:
        rows = [r for r in csvmod.reader(f) if r and not r[0].startswith('#')]
    col = {n: i for i, n in enumerate(rows[0])}
    for r in rows[1:]:
        keys.append({
            'id': r[col['key_id']], 'name': r[col['key_name']], 'row': r[col['row']],
            'x': float(r[col['hall_x']]), 'y': float(r[col['hall_y']]),
            'reps': [(float(r[col[f'rep{i}_x']]), float(r[col[f'rep{i}_y']]))
                     for i in (1, 2, 3, 4)
                     if f'rep{i}_x' in col and r[col[f'rep{i}_x']]],
        })
    return keys


GROUPS = [
    ['K62', 'K63', 'K64', 'K65', 'K66', 'K67', 'K54', 'K55'],
    ['K56', 'K57', 'K58', 'K59', 'K60', 'K61'],
    ['K01', 'K02', 'K03', 'K04', 'K05', 'K06', 'K07', 'K08'],
    ['K09', 'K10', 'K11', 'K12', 'K13', 'K14'],
    ['K15', 'K16', 'K17', 'K18', 'K19', 'K20', 'K21', 'K22'],
    ['K23', 'K24', 'K25', 'K26', 'K27', 'K28'],
    ['K29', 'K30', 'K31', 'K32', 'K33', 'K34', 'K35', 'K36'],
    ['K37', 'K38', 'K39', 'K40', 'K41', 'K50', 'K51', 'K52'],
    ['K42', 'K43', 'K44', 'K45', 'K46', 'K47', 'K48', 'K49'],
]


def build():
    b = Board()
    keys = load_keys()
    by_id = {k['id']: k for k in keys}
    assert len(keys) == 67

    for hx, hy in MOUNT_HOLES:
        b.holes.append((hx, hy, 2.7))
    H = BOARD_H
    for seg in ((0, 0, BOARD_W, 0), (BOARD_W, 0, BOARD_W, H),
                (BOARD_W, H, 0, H), (0, H, 0, 0)):
        b.lines.append((*seg, 'Edge.Cuts', 0.1, True))
    # 基准点丝印 (左/右键区旁 + 硬件带中部)
    for fx, fy in ((7, 100), (293, 100), (150, 155)):
        b.lines.append((fx - 1.5, fy, fx + 1.5, fy, 'F.SilkS', 0.15, True))
        b.lines.append((fx, fy - 1.5, fx, fy + 1.5, 'F.SilkS', 0.15, True))
        b.circles.append((fx, fy, 1.0, 'F.SilkS', 0.2, True))

    def R(ref, x, y, val, n1, n2, rot=90):
        b.place(Component(ref, 'R_0805_2012Metric', val, x, y, rot=rot,
                          nets={'1': n1, '2': n2}))

    def C(ref, x, y, val, n1, n2, rot=90):
        b.place(Component(ref, 'C_0805_2012Metric', val, x, y, rot=rot,
                          nets={'1': n1, '2': n2}))

    def V(x, y, net, size=0.6, drill=0.3):
        return b.add_via(x, y, net, size, drill)

    # ---- 67 霍尔 (rot180: VDD 朝前/母线侧, OUT 朝左, GND 朝后) ----
    for k in keys:
        b.place(Component('H' + k['id'][1:], HALL_LIB, 'HAL49E', k['x'], k['y'], rot=180,
                          nets={'1': '3V3', '2': 'GND', '3': f"HO_{k['id']}"}))
        b.texts.append((k['x'], k['y'] - 3.6, k['name'], 0.7, 'F.SilkS', True))

    # ---- 9 片 4051 + 每脚过孔 (布线交给立创 4 层; 这里只给桩+孔) ----
    mux_of = {}
    for gi, ids in enumerate(GROUPS):
        mx = MUX_XS[gi]
        ref = f'U{101 + gi}'
        mux_of[gi] = (ref, mx)
        nets = {'16': '3V3', '8': 'GND', '7': 'GND', '3': 'Z_COM',
                '11': 'MUX_A', '10': 'MUX_B', '9': 'MUX_C', '6': f'EN_{gi + 1}'}
        gk = sorted((by_id[i] for i in ids), key=lambda k: k['x'])
        for ci, k in enumerate(gk):
            nets[MUX_PIN[f'X{ci}'][0]] = f"HO_{k['id']}"
        b.place(Component(ref, MUX_LIB, '74HC4051', mx, MUX_Y, rot=270, nets=nets))
        for sig, (num, dx, dy) in MUX_PIN.items():
            net = b.pad(ref, num)['net']
            px, py = mx + dx, MUX_Y + dy
            if not net:
                continue
            if sig in ('VSS', 'VEE') or sig in FIELD_SIGS:
                V(px, py, net, 0.7, 0.35)              # 北排/GND: in-pad 过孔
            else:
                b.poly_track([(px, py), (px, STUB_S)], 0.25, 'F.Cu', net)
                V(px, STUB_S, net, 0.7, 0.35)
        V(mx - 2.0, MUX_Y, 'GND', 0.8, 0.4)            # 冗余 GND 孔 (平面缝合)

    # ---- ESP32-S3 模组 (rot=0, 天线朝顶边) ----
    mod_nets = {'1': 'GND', '2': '3V3', '3': 'EN', '4': 'Z_F', '5': 'MUX_A', '6': 'MUX_B',
                '7': 'MUX_C', '10': 'U1TX', '11': 'U1RX', '13': 'USB_DN', '14': 'USB_DP',
                '23': 'ONE_WIRE', '27': 'BOOT', '38': 'LED', '40': 'GND', '41': 'GND'}
    for gi, g in E_GPIO.items():
        mod_nets[str(GPIO_PIN[g])] = f'EN_{gi}'
    b.place(Component('U1', 'ESP32-S3-WROOM-1', 'ESP32-S3-WROOM-1-N4', MOD_X, MOD_Y,
                      rot=0, nets=mod_nets))
    # pad41 大地 pad 锚孔 (in-pad 散热过孔) + 侧边缝合
    for vx, vy in ((274, 150), (280, 150), (286, 150), (266, 148), (266, 158)):
        V(vx, vy, 'GND', 0.8, 0.4)
    # ★ 天线禁布区 x 271~289 / y 159~169: 以上过孔全部在其外 ✓

    # ---- USB-C (顶边出线, x=150) ----
    b.place(Component('J1', 'USB_C_Receptacle_HRO_TYPE-C-31-M-12', 'USB-C 16P',
                      150, 167, rot=0, nets={          # rot=0 → 嘴朝 +y 顶边
                          'A1': 'GND', 'B12': 'GND', 'B1': 'GND', 'A12': 'GND',
                          'A4': 'VBUS', 'B9': 'VBUS', 'A9': 'VBUS', 'B4': 'VBUS',
                          'A5': 'CC1', 'B5': 'CC2', 'A6': 'USB_DP', 'B6': 'USB_DP',
                          'A7': 'USB_DN', 'B7': 'USB_DN', 'S1': 'GND'}))
    # ---- LDO 电源簇 ----
    b.place(Component('U2', 'SOT-223-3_TabPin2', 'AMS1117-3.3', 100, 160, rot=0, nets={
        '1': 'GND', '2': '3V3', '3': 'VBUS'}))
    C('C_V1', 94, 166, '22uF', '3V3', 'GND')
    C('C_V2', 97, 166, '22uF', '3V3', 'GND')
    C('C_IN1', 94, 154, '10uF', 'GND', 'VBUS')
    C('C_IN2', 96.5, 154, '0.1uF', 'GND', 'VBUS')
    # USB CC 5.1k×2
    R('R_CC1', 158, 161, '5.1K', 'CC1', 'GND', rot=0)
    R('R_CC2', 158, 164, '5.1K', 'CC2', 'GND', rot=0)
    # EN 复位簇
    R('R_EN', 241, 158, '10K', 'EN', '3V3')
    C('C_EN', 244, 158, '10uF', 'EN', 'GND')
    b.place(Component('SW2', 'TS-1187A', 'EN', 233, 155, rot=0, nets={
        '1': 'EN', '2': 'EN', '3': 'GND', '4': 'GND'}))
    # BOOT
    b.place(Component('SW1', 'TS-1187A', 'BOOT', 260, 155, rot=0, nets={
        '1': 'BOOT', '2': 'BOOT', '3': 'GND', '4': 'GND'}))
    # LED (GPIO2)
    b.place(Component('LED1', 'LED_0805_2012Metric', 'PWR', 118, 154, rot=90, nets={
        '1': '3V3', '2': 'LED_A'}))
    R('R_LED', 118, 158, '1K', 'LED_A', 'LED')
    # E 上拉 9×10K (一排, 3V3/EN 各自过孔下平面)
    pullup_pos = {}
    for i in range(1, 10):
        x, y = 58 + 4 * (i - 1), 152.0
        pullup_pos[i] = (x, y)
        R(f'R_E{i}', x, y, '10K', f'EN_{i}', '3V3')
        V(x, y - 0.95, f'EN_{i}')
        V(x, y + 1.9, '3V3')
    # 模组退耦
    C('C_M1', 240, 165, '10uF', '3V3', 'GND')
    C('C_M2', 244, 165, '0.1uF', '3V3', 'GND')
    # DS18B20 J2 + 4.7k
    b.place(Component('J2', 'PinHeader_1x03_P2.54mm_Vertical', 'DS18B20', 130, 160,
                      rot=0, nets={'1': '3V3', '2': 'ONE_WIRE', '3': 'GND'}))
    R('R_DQ', 136, 165, '4.7K', 'ONE_WIRE', '3V3', rot=0)
    # UART1 J3
    b.place(Component('J3', 'PinHeader_1x04_P2.54mm_Vertical', 'UART1', 180, 160,
                      rot=0, nets={'1': 'U1TX', '2': 'U1RX', '3': '3V3', '4': 'GND'}))

    # ---- 3V3 行母线 + 67 短桩 + 干线 (键区, 不动) ----
    for ry in RAILS.values():
        b.poly_track([(8, ry), (TRUNK_3V3_X, ry)], 0.5, 'F.Cu', '3V3')
    for k in keys:
        b.poly_track([(k['x'] + 1, k['y'] - 0.95), (k['x'] + 1, RAILS[k['row']])],
                     0.3, 'F.Cu', '3V3')
    b.poly_track([(68, LANE_3V3), (TRUNK_3V3_X, LANE_3V3)], 0.8, 'F.Cu', '3V3')
    b.poly_track([(TRUNK_3V3_X, LANE_3V3), (TRUNK_3V3_X, RAILS['M'])], 0.8, 'F.Cu', '3V3')

    # ---- 霍尔 OUT 过孔 / GND 过孔 ----
    for k in keys:
        b.add_via(k['x'] - 2.2, k['y'], f"HO_{k['id']}")
        b.poly_track([(k['x'] - 1, k['y']), (k['x'] - 2.2, k['y'])], 0.3, 'F.Cu',
                     f"HO_{k['id']}")
        b.add_via(k['x'] + 1, k['y'] + 0.95, 'GND')

    return b, keys, mux_of, pullup_pos


def main():
    b, keys, mux_of, pullup_pos = build()
    print(f'== v4 放置 == 板 {BOARD_W:.0f}x{BOARD_H:.0f}, 器件 {len(b.components)}, '
          f'网络 {len(b.nets)}, 过孔 {len(b.vias)}, 安装孔 {len(b.holes)}')

    # 器件互相不重叠自检 (外框 CrtYd/丝印近似: 用 footprint 尺寸粗查)
    ck = Checker(b, [])
    ck._holes = [(x, y, 2.7) for x, y in MOUNT_HOLES]
    ck.check_edge()
    n0 = len(ck.issues)
    ck.check_holes()
    n_h = len(ck.issues)
    ck.check_clearance()
    n1 = len(ck.issues)
    print(f'== 自检 == edge {n0}, hole {n_h - n0}, clearance {n1 - n_h}')
    for it in ck.issues[:20]:
        print('  !', it)

    for k in keys:
        c = [x for x in b.components if x.ref == 'H' + k['id'][1:]][0]
        assert abs(c.x - k['x']) < 0.01 and abs(c.y - k['y']) < 0.01
    print('霍尔坐标 == CSV ✓')

    # 硬件带重叠粗检: 所有 SMD 器件 bbox
    boxes = []
    for c in b.components:
        if c.ref.startswith('H'):
            continue
        xs = [p['x'] for p in c.abs_pads]
        ys = [p['y'] for p in c.abs_pads]
        boxes.append((c.ref, min(xs) - 1.2, min(ys) - 1.2, max(xs) + 1.2, max(ys) + 1.2))
    bad = []
    for i in range(len(boxes)):
        for j in range(i + 1, len(boxes)):
            a, bb = boxes[i], boxes[j]
            if a[1] < bb[3] and bb[1] < a[3] and a[2] < bb[4] and bb[2] < a[4]:
                bad.append((a[0], bb[0]))
    print('器件 bbox 重叠:', bad if bad else '无 ✓')

    outdir = os.path.join(HERE, '..', 'output')
    os.makedirs(outdir, exist_ok=True)
    # v4.3: 放置-only(内层留给信号; GND 铺铜在 emit_v43 合成时放 B.Cu)
    b.emit_kicad_pcb(os.path.join(outdir, 'KeyCore.kicad_pcb'))
    print('已发射 KeyCore.kicad_pcb (v4.3: 300x172 键场下移 9mm, 放置-only)')


if __name__ == '__main__':
    main()
