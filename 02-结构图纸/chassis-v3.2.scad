// ============================================================
// 底壳 v3.2 · 形态改版（2026-10-02，配合 PCB v4 300×172 元件带后置）
// 取代 v3.1（其 ledge 注释 19.6/34.6 为 v1.6 死数据；真实层链以公式为准）
//
// 层链（自上而下，z 以壳内底面=0 计；★air 2.0→2.6：ESP32 2.4 需从屏玻璃下通过）：
//   厚板 9mm（盲孔板；底面 ledge_z=13.7）
//     ↕ 悬浮 4mm（静止；行程 3 + 安全 1，块底距屏面按到底 1.0）
//   屏 2.5mm（z 7.2~9.7）+ 空气隙 2.6mm → PCB 1.6mm（z 3~4.6）→ 底壳 base 3
//   磁距：帽内磁心(块底+2.05) → 霍尔(贴 PCB 面) ≈ 10.4mm 静止（air +0.6 使磁距
//         +0.6，v5.0 口径 8.5 系旧层链；P0′ 现场重扫点位时一并校准，不阻塞）
//
// 坐标（chassis 帧）：壳外角为原点；plate 区 = [wall_t, wall_t] 起；
//   plate 帧 = 厚板 scad 帧：y=0 边 = 宏行/背边（硬件带+出线），y=201.4 = 空格排前边
//   PCB 帧(EDA) ↔ plate 帧：plate_x = EDA_x + 7.1；plate_y = 201.405 − EDA_y
//
// v4 硬件带（EDA y 136~172 = plate y 29.4~65.4）：9×4051 一排 + ESP32 + LDO 等，
//   高件预算：屏玻璃(后沿 plate y 36.4=EDA 165)以下限高 2.6（SOIC1.75/ESP2.4/贴片 ✓）；
//   玻璃后带（EDA 165~172）：按键 SW1/SW2、排针 J2/J3（换 6mm 矮针，顶 10.6<13.7 ✓）、
//   USB-C 体 3.26 恰在玻璃沿外（体后沿 EDA 162.85 < 165 沿 → 不入玻璃 ✓）
// 屏（293.7×165.2）：plate y 36.4~201.4（前沿与厚板前缘平齐），左右搁在 x 向
//   两根搁屏条上（PCB 外侧 7mm 边带，不与 PCB 相交）
// USB-C：PCB 边缘 y=172 距背墙内面 25.4mm → 插头经背墙槽 + 板下开敞通道
//   （plate y 4~29.4，z 4.2~8.4，屏不覆盖此区、托圈 z≥10.7 不相扰）
// ============================================================

part = "chassis"; // ["chassis","chassis_section"]

plate_w = 314.2; plate_d = 201.4; plate_t = 9.0;
screen_t = 2.5;  air = 2.6;  pcb_t = 1.6;   // ★v3.2: air 2.0→2.6
base_t = 3.0;    wall_t = 4.0;
shoulder_h = 4.0;                 // 悬浮行程空间（块底→屏面：静止4=行程3+安全1）
ledge_z = base_t + pcb_t + air + screen_t + shoulder_h;  // 厚板底面高度 = 13.7
wall_h  = ledge_z + plate_t;      // 22.7
inner_w = plate_w - 2*wall_t + 2*2;   // 厚板嵌入内腔（左右各卡入2mm）
inner_d = plate_d - 2*wall_t + 2*2;
// 屏搁置（plate 帧 y）：屏后沿 = 硬件带顶（EDA 165）→ plate 36.405；前沿贴板前缘
screen_y_back = 36.4;
// PCB v4 安装孔（EDA）→ chassis 帧中心（+7.1 / 201.405−y + wall_t）
pcb_posts = [[17.1, 199.4], [161.1, 199.4], [305.1, 199.4],   // 前排 (6,6)(150,6)(294,6)
             [17.1, 40.4], [305.1, 40.4], [161.1, 70.4]];     // 背角 (6,165)(294,165) + 中 (150,135)

module chassis() {
  difference() {
    union() {
      // 外壁
      difference() {
        cube([plate_w+2*wall_t, plate_d+2*wall_t, wall_h]);
        translate([wall_t, wall_t, base_t])
          cube([plate_w, plate_d, wall_h-base_t]);
      }
      // 厚板托圈（搭接2mm/边，承托面=ledge_z；背带 plate y1~5 在 USB 通道上方，z 不相扰）
      translate([wall_t+1, wall_t+1, ledge_z-3])
        difference() {
          cube([plate_w-2, plate_d-2, 3]);
          translate([3,3,-0.1]) cube([plate_w-8, plate_d-8, 3.2]);
        }
      // 搁屏条 ×2（PCB 外侧 x 边带；屏底 z=base_t+pcb_t+air）
      for (sx=[wall_t+0.3, wall_t+plate_w-6.6])
        translate([sx, wall_t+screen_y_back+0.5, base_t])
          cube([6.3, plate_d-screen_y_back-1, pcb_t+air]);
      // PCB 支撑柱 ×6（对位 v4 安装孔；M2.5 自攻，柱高=pcb_t）
      for (p=pcb_posts)
        translate([p[0], p[1], base_t]) difference() {
          cylinder(d=7, h=pcb_t, $fn=32);
          translate([0,0,-1]) cylinder(d=2.1, h=pcb_t+2, $fn=24);
        }
      // 四角螺钉柱（合盖）
      for (x=[12, plate_w+wall_t*2-12], y=[12, plate_d+wall_t*2-12])
        translate([x, y, base_t]) difference() {
          cylinder(d=8, h=wall_h-base_t, $fn=32);
          translate([0,0,-1]) cylinder(d=2.4, h=wall_h, $fn=24);
        }
    }
    // USB-C 背墙口（chassis x 154.6~167.6 对位 PCB x=150/EDA；z 4.2~8.4 对位体 4.6~7.86）
    translate([wall_t+150+7.1-6.5, -1, base_t+1.2]) cube([13, wall_t+2, 4.2]);
    // 背墙出线口（HDMI/12V；USB 口东侧 15mm 起；z 顶 10.6 < 托圈底 10.7 不相扰，走 ~6mm 线）
    translate([wall_t+55, -1, base_t+1.5]) cube([80, wall_t+2, 6.1]);
    // 底面散热缝×3
    for (yy=[plate_d*0.3, plate_d*0.55, plate_d*0.8])
      translate([60, yy, -0.1]) cube([180, 4, base_t+0.2]);
  }
}
chassis();
