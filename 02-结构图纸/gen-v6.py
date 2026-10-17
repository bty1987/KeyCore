# -*- coding: utf-8 -*-
import io, sys, re
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
txt = open('02-结构图纸/thickplate-v4.scad', encoding='utf-8').read()
seg = txt[txt.index('frame_holes'):txt.index('row_ys')]
holes_src = seg[seg.index('['):seg.index(']')+1]
holes = [(float(a), float(b), float(c)) for a, b, c in re.findall(r'\[([\d.]+), ([\d.]+), ([\d.]+)\]', holes_src)]
row_ys = [111.538, 92.488, 73.438, 54.388, 35.338, 16.288]
print('holes:', len(holes))
mags = []
for y in row_ys:
    row = sorted([p for p in holes if p[1] == y], key=lambda p: p[0])
    assert row, '空行 y=%s' % y
    a, b = row[0], row[-1]
    mags.append((round(a[0]-a[2]*9.525, 2), y))
    for i in range(len(row)-1):
        hwa = row[i][2]*19.05-2+0.6; hwb = row[i+1][2]*19.05-2+0.6
        mags.append((round((row[i][0]+hwa/2 + row[i+1][0]-hwb/2)/2, 2), y))
    mags.append((round(b[0]+b[2]*9.525, 2), y))
print('磁位:', len(mags))
mag_arr = ', '.join('[%s, %s]' % m for m in mags)
v6 = '''// ============================================================
// 厚板 v6 · 2026-10-17 终版（用户拍板：无任何贯通开口，磁槽全在底面）
//   取代 v5 的 6 条行磁道 → 改为 底面盲槽 ×73（2.2×4.2，深 4，自底面向上铣）
//   磁铁 N52 4×2 竖放，自底面装入盲槽胶固（M1-M73 独立装填，无贯通）
//     磁心 z2 —— 距 PCB 霍尔更近，感应优于 v4 磁道方案（z5）
//   板 = 300.2×192×9（四角 R4）；67 孔打穿（键帽悬浮位，与封板 5c 霍尔位零偏差）
//   盲槽顶 z4，上方留 5mm 实体；全板无任何对外开口
//   制造：CNC（正面钻 67 孔 + 底面铣 73 盲槽，两面工序）
// 坐标系：scad = EDA 帧映射（y_scad = 192 + EDA_y_mm，y-up）
// ============================================================

// ---- 板 ----
plate_w = 300.2;
plate_d = 192.0;
plate_t = 9.0;
hole_r  = 2.0;

// ---- 67 孔坐标（封板 5c 霍尔位；x,y=孔心，wu=键宽）----
frame_holes = ''' + holes_src + ''';

// ---- 73 磁位（x,y=磁心；键间缝位 + 行两端）----
mag_positions = [''' + mag_arr + '''];
pocket_x = 2.2;    // 盲槽 X 宽（磁厚 2 +0.2）
pocket_y = 4.2;    // 盲槽 Y 长（磁 Ø4 +0.2）
pocket_d = 4.0;    // 盲槽深（自底面向上，磁心 z2）

// 打穿孔（方孔 R2，宽随 wu：键帽宽+0.6 公差）
module through_hole(x, y, wu) {
  hw = wu*19.05 - 2.0 + 0.6;
  translate([x, y, -0.1])
    linear_extrude(plate_t + 0.2)
      hull() for (sx=[-1,1], sy=[-1,1])
        translate([sx*(hw/2-hole_r), sy*(hw/2-hole_r)]) circle(r=hole_r, $fn=48);
}
module all_holes() for (p = frame_holes) through_hole(p[0], p[1], p[2]);

// 底面盲槽 ×73（磁铁 4×2 竖放胶固位）
module mag_pockets() {
  for (m = mag_positions)
    translate([m[0] - pocket_x/2, m[1] - pocket_y/2, -0.1])
      linear_extrude(pocket_d + 0.1)
        offset(r = 0.5) square([pocket_x - 1.0, pocket_y - 1.0], center = true);
}

// 厚板本体（67 打穿孔 + 底面 73 盲槽，全板无贯通开口）
module thick_plate() {
  difference() {
    translate([4, 4, 0]) linear_extrude(plate_t)
      offset(r=4) square([plate_w-8, plate_d-8]);
    all_holes();
    mag_pockets();
  }
}

thick_plate();
'''
open('02-结构图纸/thickplate-v6.scad', 'w', encoding='utf-8').write(v6)
print('thickplate-v6.scad OK')
