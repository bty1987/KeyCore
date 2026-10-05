# 07-PCB · 程序化 KiCad 生成管线（v5.1-prelim 口径）

> 2026-10-03：按 v5.1-prelim CSV 重新生成（霍尔=键中心偏上+4mm）。**放置/母线/丝印完成；底层信号布线未收敛（route_report.json 列明剩余网络）——收尾在立创EDA/KiCad 手工或迭代 router。**

## 用法

```bash
venv/bin/python tools/design.py    # 读 02-结构图纸/pcb-hall-positions.csv → 生成 output/KeyCore.kicad_pcb + route_report.json
venv/bin/python tools/render.py    # 输出 output/preview_top.png / preview_bot.png
```

- `tools/design.py`：布局参数（RAILS/MUX_XS/GROUPS/主控条）都在此文件顶部，改布局先改这里
- 坐标系：EDA 帧（左下原点，+y 朝 Esc），发射时翻转为 KiCad 帧
- 数据源：`../02-结构图纸/pcb-hall-positions.csv`（**禁止手填坐标**，改 CSV 后重跑）

## 迭代验证结论（2026-10-03，三轮完整迭代后）

**判定：当前 `KeyCore.kicad_pcb` = 合格的"放置骨架"，还不是可下单的成品板。**

- ✅ 放置层全部验证通过：67 霍尔 == CSV 逐键断言、主控条、顶层 3V3 行母线、安装孔、兜底丝印；`hole 0 / clearance 0`（无电气违规）
- ⚠️ 底层信号自动布线收敛停滞：三轮不同策略（重试/拆线重布/恢复式 rip-up）分别停在 72 / 62(含隐性丟网) / **78** 未通网，`route_report.json` 有完整清单与历史曲线——剩余全是跨板长线（霍尔 OUT→4051、EN、USB 等），随机 rip-up 撞拓扑天花板，需要**通道有序布线**或人工收线
- ⚠️ 67 条 `rep` 告警 = 兜底粘接丝印圈与霍尔焊盘相切（新摆位下两者仅距 4mm），丝印厂会自动裁掉，电气无影响，已知化妆性问题

**对 P0′ 实测无阻碍**：单帽测试只需 1 路霍尔 + ESP32 + USB——收板后手工飞线 1~2 根即可开测，不必等全板布线完成。

## 当前状态（2026-10-03）

| 项 | 状态 |
|---|---|
| 67 霍尔放置 | ✅ 与 CSV 逐键一致（管线内建断言） |
| 顶层 3V3 行母线 + 右干线 | ✅ |
| 主控条（ESP32-S3 + 阻容 + USB-C） | ✅ 已放置 |
| 底层信号布线 | ⚠ 三轮迭代收敛于 78 网未通（历史曲线在 route_report.json）→ 建议 KiCad/立创EDA 人工收线（约一晚）|
| 磁铁位 | ✅ 已按用户指示移除（2026-10-03）：磁铁在键帽侧壁+亚克力孔底，PCB 无磁铁位；兜底三磁的底心磁铁同样贴亚克力孔底 |

## 下单前必做

1. EDA 里完成剩余布线 + DRC 清零；
2. 霍尔点位按 P0′ 实测微调（如点位变化 → 改 CSV → 重跑管线）；
3. 嘉立创下单参数：2 层 / 1.6mm / 300×146 / 黑色阻焊白字 / 无铅喷锡 / 5 片 + SMT 顶部贴片。
