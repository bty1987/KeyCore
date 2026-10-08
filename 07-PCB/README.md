# 07-PCB · PCB 工作目录

> **⚠ 2026-10-08 更新**：KiCad 程序化生成管线（tools/ 下的 emit_v4x 等）为历史方案，**现行流程 = 立创EDA 专业版 + easyeda-agent CLI**（FreeRouting 全局布线）。KiCad 管线退役存档于 git 历史。

## 现行状态

- **工程**：KeyCore-v43b-3c（立创EDA，4 层 300×192mm）
- **已下单**：订单 Y4 / SMT2610080582（¥1235.19，5 片全贴，2026-10-13 发货）
- **Gerber**：`output/gerber_3c/KeyCore-v43b-3c-JLC-Order.zip`（18 文件，唯一有效下单包）
- **打板清单**：`output/打板清单-KeyCore-v43b-3c-20261008.md`
- **全程经验**：`output/画线总结-过程与经验-20261008.md`（SOP/踩坑/费用实测）

## 目录

- `footprints/` — KiCad 封装库（早期 KiCad 管线产物，留作参考）
- `tools/` — 退役的 KiCad/SES 处理脚本（git 历史有效，本地可删）
- `output/` — 全部交付物（Gerber/清单/图纸/总结）

## 坐标权威

**EDA live 霍尔位 = 唯一权威**（CSV v5.2 的 x/y 已过时，仅 w_u 键宽列可用）。孔心=霍尔位（2026-10-07 拍板，+4 预放偏置弃用）。
