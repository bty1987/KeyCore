// ============================================================
// KeyCore 键帽 · v5.3 侧壁竖磁键帽 · 参数化全型
//   来源: thickplate-v4.scad keycap_block() 参数化扩展 (2026-10-17)
//   磁路 v5.3: 2×N52 4×2 圆盘竖立, 嵌帽左右侧壁, 外侧壁水平开口横插
//   材质建议: 树脂打印(强度/手感) 或 PETG; 顶面贴键帽字符片
// 用法:
//   单件: keycap(wu=1)            // 1u
//         keycap(wu=2.75)         // 2.75u
//   全套预览: all_caps_67();      // 67 键按 thickplate-v4 frame_holes 排布
// 变体表 (封板 5c 实配 67 键): 1u×52, 1.25u×7, 1.5u×2, 1.75u×1,
//   2u×1, 2.25u×2, 2.75u×1, 6.25u×1 (空格)
// ============================================================

pitch    = 19.05;
cap_h    = 7.5;      // 块高
cap_d    = 17.0;     // 块深
clear    = 2.0;      // 帽间总间隙(单边 1.0)
top_r    = 2.0;      // 顶面圆角
band_r   = 1.2;      // 下段圆角
band_h   = 6.5;      // 下段高(上 1.0 为顶带)
mag_d    = 4.1;      // 磁腔直径(磁铁 4×2 +0.1)
mag_z    = 2.05;     // 磁腔轴心高(竖立: 腔跨 z 0~4.1)
wall_t   = 0.5;      // 极面外壁
mag_len  = 5.0;      // 磁铁长(横插, 含 1.1 过切)

module keycap(wu = 1) {
  cap_w = wu*pitch - clear;
  mag_off = wu*pitch/2 - 2.0 - wall_t;
  difference() {
    union() {
      linear_extrude(band_h)
        offset(r = band_r) offset(delta = -band_r)
          square([cap_w, cap_d], center = true);
      translate([0, 0, band_h]) linear_extrude(1.0)
        hull() for (sx = [-1,1], sy = [-1,1])
          translate([sx*(cap_w/2 - top_r), sy*(cap_d/2 - top_r)])
            circle(r = top_r, $fn = 40);
    }
    for (s = [-1, 1])
      translate([s*(cap_w/2 + 0.55), 0, mag_z])
        rotate([0, -s*90, 0])
          cylinder(d = mag_d, h = mag_len, $fn = 40);
  }
  // 磁铁占位提示(打印时注释掉): 两颗 4×2 N52 竖放, N 极同向朝邻缝
}

// 8 变体单件(打印排板示例, 间距 22mm)
module all_variants() {
  wus = [1, 1.25, 1.5, 1.75, 2, 2.25, 2.75, 6.25];
  for (i = [0 : len(wus) - 1])
    translate([i*22, 0, 0]) keycap(wus[i]);
}

// 67 键整板预览: 需与 thickplate-v4.scad 同目录 use <> 后调用, 或粘贴 frame_holes
module all_caps_67() {
  // frame_holes 与 thickplate-v4.scad 同源(67 孔 x,y,wu)
  echo("请 use <thickplate-v4.scad> 后调用, 或从 v4 复制 frame_holes 数组");
}

keycap(wu = 1);
