"""SES (Specctra Session, FreeRouting 输出) → KiCad 轨迹/过孔列表.

坐标系: DSN/SES 与 EDA 帧一致 (原点左下, y 向上, 单位 = mil×1000).
输出: tracks = [(x1,y1,x2,y2,width_mm,layer,net)] EDA 帧 mm;
      vias   = [(x,y,size_mm,drill_mm,net)] EDA 帧 mm.
"""
import re

LAYER_MAP = {
    'TopLayer': 'F.Cu',
    'Inner1': 'In1.Cu',
    'Inner2': 'In2.Cu',
    'BottomLayer': 'B.Cu',
}
VIA_MAP = {  # DSN padstack → (pad外径mm, 钻径mm)
    'via0': (0.7, 0.35),
    'via1': (0.8, 0.4),
    'via2': (0.6, 0.3),
    'via3': (0.6, 0.3),
}
U2MM = 25.4 / 1e6  # DSN 单位 = mil×1000 → mm (1 mil = 0.0254mm, 故 ÷39370.1)


def parse(ses_path, board_h_mm):
    s = open(ses_path, encoding='utf-8').read()
    tracks, vias, seen_via = [], [], set()
    # 逐 net 块
    for nm in re.finditer(r'\(net "([^"]+)"([\s\S]*?)(?=\n\s*\(net "|\Z)', s):
        net, body = nm.group(1), nm.group(2)
        for pm in re.finditer(r'\(path (\w+) (\d+)([\d\s]+?)\)', body):
            layer, w, pts = LAYER_MAP[pm.group(1)], int(pm.group(2)), pm.group(3)
            vals = [int(v) for v in pts.split()]
            xs, ys = vals[0::2], vals[1::2]
            wmm = w * U2MM
            for i in range(len(xs) - 1):
                x1, y1 = xs[i] * U2MM, ys[i] * U2MM
                x2, y2 = xs[i + 1] * U2MM, ys[i + 1] * U2MM
                if abs(x1 - x2) < 0.0005 and abs(y1 - y2) < 0.0005:
                    continue  # 网格碎屑
                tracks.append((x1, board_h_mm - y1, x2, board_h_mm - y2,
                               round(wmm, 4), layer, net))
        for vm in re.finditer(r'\(via (via\d) (\d+) (\d+)', body):
            size, drill = VIA_MAP[vm.group(1)]
            x, y = int(vm.group(2)) * U2MM, int(vm.group(3)) * U2MM
            key = (round(x, 2), round(y, 2), size)
            if key in seen_via:
                continue
            seen_via.add(key)
            vias.append((x, board_h_mm - y, size, drill, net))
    return tracks, vias
