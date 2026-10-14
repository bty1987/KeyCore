# 03-固件

> **2026-10-14 更新**：**PCB 已到货**（订单 Y4，5 片全贴）。收板自检固件 **env `bringup`**（src/main.cpp）就绪：PSRAM/Flash 容量与读写、LED1 心跳、9×8 全通道扫描 + 磁铁 ALERT。上电清单见 `06-测试记录/收板上电自检-20261014.md`。
> P0 单键验证固件（已完成使命，PASS 见 `06-测试记录/P0-验证报告.md`）保留在 env `p0-single-key`（src/p0_single_key.cpp）。

## 正式固件要点（定稿备忘）

- **平台**：ESP32-S3-WROOM-1-**N4R8**（4MB Flash + 8MB **Octal PSRAM**）——必须开 OPI PSRAM 配置
- **烧录**：USB-C（芯片内置 USB-Serial-JTAG），无需外部串口；BOOT=SW1 / EN=SW2
- **输入链**：67× HAL49ESO（SOT-23）→ 9× 74HC4051（地址 MUX_A/B/C=IO5/6/7，使能 EN_1..9=IO8~16）→ ADC
- **注意事项**：
  - K53 绑定 EN_6 组 U106.4（扫描表按此同步）
  - PSRAM 保留脚 IO35/36/37（pad28~30）不得使用
  - LED1 = IO38（软件可控，高电平经 1K 限流）
  - ONE_WIRE = IO21（J2 未装排针 → 1-Wire 搜索为空时静默跳过，禁死等）
  - USB 差分对等长差 0.8mm 已接受（FS 速率无影响）
- **平台建议**：PlatformIO + arduino-esp32 或 ESP-IDF（platformio.ini 已建骨架）
