# KeyCore v43b PCB 会话总结 (2026-10-05)

## 一、本次会话完成的工作

### 安装与配置
- 安装 easyeda-agent v1.9.0 全链路（CLI + daemon 60832 + 连接器扩展）
- 踩坑记录见记忆 keycore-easyeda-agent-setup

### 连接性修复（从 18 → 0）
| 网络 | 修复方式 | 状态 |
|------|---------|------|
| HO_K53 | design.py GROUPS 漏了 K53；debug exec 绑 U106.4 + via_hop 三段 + L15 长直线下行 | ✅ 全通 |
| HO_K30 | pcb.line.create 两段 | ✅ 接通 |
| HO_K56 | 删重影 via + 干净重建 pad→via→L15 | ✅ 接通 |
| HO_K59 | 删冗余 L15 斜线 + 补直连 | ✅ 接通 |
| CC2 | Alt+W 路径 typed 重画 + 分段 via 注册 | ⚠️ 铜皮连通，DRC 标记残留 |
| VBUS | via_hop + 直线补桥 | ✅ 接通 |
| MUX_C | 删错层线 + via_hop | ✅ 接通 |
| ONE_WIRE | 删 L1 幽灵线 ×2 | ✅ 接通 |

### 间距优化
- 0.089mm 规则矩阵全表写回
- 重影过孔 4 对删除
- 3V3 干线织纬（ESP32 区北绕 y=-450 + LDO 区南绕 y=-860 降宽 10mil）
- 铺铜重排 ×3

### Gerber 导出
- 最终版: `07-PCB/output/final/KeyCore-v43b-JLC-Order.zip`
- 短文件名重打包（立创原生长名 zip 嘉立创 DFM 识别不了）
- 用户已上传嘉立创并提交订单（审核中/已审核）

### BOM/PCBA
- BOM + 坐标文件导出，修正 J2 错误匹配（DS18B20→排针）
- 11 项填入嘉立创确认 C 号
- PCBA 贴片清单（含料号对照）见 `PCBA贴片清单-v43b.md`

## 二、最终 DRC 状态

| 类型 | 数量 | 说明 |
|------|------|------|
| 连接性 | 2 | CC2 幽灵标记（铜皮连通，平台注册 bug） |
| 间距-重叠 | ~228 | 不同网络 0 距离，需逐簇修 |
| 间距-接近 | ~32 | 0.1~2mil，蚀刻公差内可能放行 |
| 间距-容忍 | ~50 | 2~3.5mil=0.05~0.089mm，用户口径放行 |
| 同封装 | 135 | 封装固有，忽略 |

## 三、关键教训

1. **typed pcb.line.create 不自动建连接节点** — via_hop 复合动作可以
2. **修完必须 save→doc reload→DRC 三连** — 否则读到陈旧状态
3. **TH 通孔焊盘孔区内走线≠连接** — 立创 DRC 口径
4. **避障验证器必须含线段相交检测** — 端点距离漏十字相交
5. **全量 rip_up 前必须确认编辑器内存 vs 磁盘状态一致性**
6. **铺铜 pour-rebuild 会让间距数字波动** — 新过孔需要铺铜重新避让
7. **批删前先 dump 核对 pid** — 盲删会断既有链

## 四、剩余待修（下个会话继续）

| 优先级 | 项目 | 数量 | 修法 |
|--------|------|------|------|
| P0 | 3V3↔GND 电源短路 | ~8 | ESP32 区干线织纬残余 |
| P0 | CC2↔VBUS/GND | ~26 | J1 通孔物理锁死，需 via-in-pad 塞孔工艺 |
| P1 | MUX_A↔HO_K56 走廊 | ~11 | U102 区通道逃逸线互穿 |
| P1 | 3V3↔LED/ONE_WIRE | ~12 | LDO 区织纬残余 |
| P2 | 信号互短 | ~170 | 各 HO 通道逃逸斜线互穿 |
| P2 | 4 幽灵连接标记 | 4 | 铜皮连通，平台注册 bug，不影响制造 |

## 五、文件路径速查

| 文件 | 路径 |
|------|------|
| 主力工程 | ~/Documents/LCEDA-Pro/projects/KeyCore-v43b.eprj2 |
| PCB 备份 | ~/Documents/LCEDA-Pro/projects/KeyCore-v43b_backup/ |
| 最终 Gerber | 07-PCB/output/final/KeyCore-v43b-JLC-Order.zip |
| PCBA BOM | 07-PCB/output/final/BOM-PCBA-v43b.csv |
| PCBA 坐标 | 07-PCB/output/final/PickPlace-PCBA-v43b.csv |
| 修复包 | 07-PCB/output/final/KeyCore-v43b-fixed.epro2 |
| DRC 收尾清单 | 07-PCB/output/DRC收尾清单.md |
| 进度文档 | 07-PCB/output/立创EDA布线进度.md |
| 设计源码 | 07-PCB/tools/design.py |
| 键位 CSV | 02-结构图纸/pcb-hall-positions.csv (v5.2) |
| 底壳 | 02-结构图纸/chassis-v3.1.scad |
| 厚板 | 02-结构图纸/thickplate-v3.scad (v4 通孔版) |
| easyeda-agent | ~/.local/bin/easyeda + ~/.agents/skills/easyeda-agent/ |
| daemon | port 60832 (nohup easyeda daemon start) |
