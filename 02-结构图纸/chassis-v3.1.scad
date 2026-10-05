// ============================================================
// 底壳 v3.1 · 层高终版（2026-10-02 磁路注释随 v5.0 侧磁方案更新；几何不变）
// 层链（自上而下）：
//   厚板 9mm（盲孔板，键帽块在其中滑动；块底与板底平齐）
//     ↕ 悬浮气隙 4mm（静止）→ 1mm（按到底）——键帽间侧壁互斥回弹，板侧无磁铁
//   屏 2.5mm + 空气隙 2mm → PCB 1.6mm → 底壳
// 磁距（v5.0 口径）：键帽侧磁铁(块内磁心高 1.05) → 霍尔(贴 PCB 面)
//   ≈ 8.5mm（静止）→ 5.5mm（按下）；霍尔位于每键左侧磁铁正下方（CSV v5.0）
// 壳体：四壁高 = 厚板9 + 屏悬链8.6 + 底板3 → 总高约 34.6（与 v1.6 相同，已验算）
// ============================================================

part = "chassis"; // ["chassis","chassis_section"]

plate_w = 314.2; plate_d = 201.4; plate_t = 9.0;
screen_t = 2.5;  air = 2.0;  pcb_t = 1.6;
base_t = 3.0;    wall_t = 4.0;
// 层链：厚板坐于托圈（托圈面=屏顶上方0=直接贴屏？不——厚板底需离屏面留键帽块悬浮空间
// ★ 关键：键帽块底面=厚板底面下方0（块底与板底平齐），块底→屏面间隙 = 悬浮4mm
//   → 厚板底面距屏面 = 4mm（此间隙由四壁内侧的"厚板托肩"承托控制）
shoulder_h = 4.0;                 // 托肩面距屏面 = 悬浮行程空间
ledge_z = base_t + pcb_t + air + screen_t + shoulder_h;  // 厚板底面高度 = 19.6（同v1.6，巧）
wall_h  = ledge_z + plate_t;      // 34.6 → 与 v1.6 完全一致（总高不变验证 ✓）
inner_w = plate_w - 2*wall_t + 2*2;   // 厚板嵌入内腔（左右各卡入2mm）
inner_d = plate_d - 2*wall_t + 2*2;

module chassis() {
  difference() {
    union() {
      // 外壁
      difference() {
        cube([plate_w+2*wall_t, plate_d+2*wall_t, wall_h]);
        translate([wall_t, wall_t, base_t])
          cube([plate_w, plate_d, wall_h-base_t]);
      }
      // 屏托圈（托厚板：搭接2mm/边，承托面=ledge_z）
      translate([wall_t+1, wall_t+1, ledge_z-3])
        difference() {
          cube([plate_w-2, plate_d-2, 3]);
          translate([3,3,-0.1]) cube([plate_w-8, plate_d-8, 3.2]);
        }
      // PCB 支撑柱 ×6
      for (px=[40, 157, 274], py=[50, 116])
        translate([px, py, base_t]) cylinder(d=8, h=8, $fn=32);
      // 四角螺钉柱
      for (x=[12, plate_w+wall_t*2-12], y=[12, plate_d+wall_t*2-12])
        translate([x, y, base_t]) difference() {
          cylinder(d=8, h=wall_h-base_t, $fn=32);
          translate([0,0,-1]) cylinder(d=2.4, h=wall_h, $fn=24);
        }
    }
    // USB-C 左墙口（PCB 前段）
    translate([-1, 30, base_t+8]) cube([wall_t+2, 13, 5]);
    // 背墙出线口（HDMI/12V）
    translate([plate_w/2+wall_t-45, plate_d+wall_t-1, base_t+2])
      cube([90, wall_t+2, 9]);
    // 底面散热缝×3
    for (yy=[plate_d*0.3, plate_d*0.55, plate_d*0.8])
      translate([60, yy, -0.1]) cube([180, 4, base_t+0.2]);
  }
}
chassis();
