# 03-固件

> **2026-10-08 更新**：P0 单键验证固件（src/main.cpp）已完成使命——P0 验证 PASS（见 `06-测试记录/P0-验证报告.md`，隔屏检测/极性/噪声结论被 v5.0 复用）。**正式键盘固件待 PCB（订单 Y4，10-13 发货）到货后开发**。

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
