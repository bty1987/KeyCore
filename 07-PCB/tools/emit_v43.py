"""合成 v4.3: v4.1 放置 + FreeRouting SES 全部铜(走线/过孔) + B.Cu GND 铺铜区.

用法: python3 emit_v42.py  →  ../output/KeyCore.kicad_pcb (v4.3)
"""
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
import design
from board import Track, BOARD_W, BOARD_H
import ses2kicad

SES_PATH = '/Users/Admin/Downloads/KeyCore-v43.ses'


def main():
    b, keys, mux_of, pu = design.build()
    n_tracks0, n_vias0 = len(b.tracks), len(b.vias)
    # 预放基础设施(母线/短桩/逃生孔)已包含在 SES 里 → 丢弃,以 SES 为唯一铜来源
    b.tracks.clear()
    b.vias.clear()

    tracks, vias = ses2kicad.parse(SES_PATH, BOARD_H)
    for x1, y1, x2, y2, w, layer, net in tracks:
        b.tracks.append(Track(x1, y1, x2, y2, w, layer, net, eda_frame=True))
    for x, y, size, drill, net in vias:
        b.add_via(x, y, net, size, drill)
    print(f'SES → 走线 {len(tracks)} (丢弃手布 {n_tracks0}), 过孔 {len(vias)} (丢弃 {n_vias0})')

    # 各层统计
    from collections import Counter
    print('层分布:', dict(Counter(t.layer for t in b.tracks)))

    outdir = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'output')
    rect = [(0, 0), (BOARD_W, 0), (BOARD_W, BOARD_H), (0, BOARD_H)]
    b.emit_kicad_pcb(os.path.join(outdir, 'KeyCore.kicad_pcb'),
                     zones=[('GND', 'B.Cu', rect)])
    print('已发射 KeyCore.kicad_pcb (v4.3: 键场-9mm + FreeRouting 全铜 + B.Cu GND 铺铜区)')


if __name__ == '__main__':
    main()
