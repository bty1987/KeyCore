// ============================================================
// KeyCore 收板自检固件 (bring-up) · 2026-10-14
// 目的: PCB (订单 Y4, 10-14 到货) 上电第一支固件——
//       验证主控 / 8MB Octal PSRAM / LED1 / 67 路霍尔采样链是否全通
//
// 烧录: pio run -t upload -e bringup && pio run -t monitor -e bringup
//       (USB-C 即 USB-Serial-JTAG; 进不去下载模式时按住 BOOT=SW1 再插 USB)
//
// 串口判定 (115200):
//   芯片    = ESP32-S3
//   Flash   = 4 MB
//   PSRAM   = 8388608 bytes (8MB, OPI) + 读写 OK   ← 认不到就是 memory_type 没开 qio_opi
//   LED1    = 红光, 每 0.5s 闪 (硬件带 y155~172, USB 口旁)
//   扫描    = 每轮 9×8=72 通道: ok 格 ≈1650mV 上下 (HAL49ESO 零场 ≈ VCC/2)
//             其中 ≥67 格在 1290~2100mV 内; 空通道(72-67=5 个)数值不定属正常
//   磁铁测试: 逐键靠近键位 → 串口弹 ALERT 行 (Δ>60mV), mV 单向变化 = 采样链全通
//   基线    = 上电静置取均值; 串口发任意字符重取 (比如拿磁铁扫完一圈后)
//
// 引脚出处: 设计说明-KeyCore总装 §功能引脚分配 + 03-固件/README 定稿备忘
//   ADC = IO4 ✅已核实: U1 typed 网络表 pad4 = "Z_F"(9×4051 Z 汇聚→RC→ADC1)
//   MUX_A/B/C = IO5/6/7; EN_1..EN_9 = IO8~16 顺序对应 ✅(U1 网络表+41 脚表交叉推导自洽:
//   pad8=IO15=EN_8, pad9=IO16=EN_9, pad12=IO8=EN_1 … pad22=IO14=EN_7)
//   IO21 = ONE_WIRE (J2 未装排针 → 不碰, 禁死等); IO35/36/37 = PSRAM 保留, 禁用; IO1/IO2 板上接 GND
// ============================================================

#include <Arduino.h>
#include <esp_flash.h>

static const int PIN_ADC    = 4;
static const int PIN_MUX_A  = 5;
static const int PIN_MUX_B  = 6;
static const int PIN_MUX_C  = 7;
static const int PIN_EN[9]  = {8, 9, 10, 11, 12, 13, 14, 15, 16};  // EN_1..EN_9, 低有效
static const int PIN_LED1   = 38;

static const long MV_MIN_OK = 1290;   // 零场 ≈1650mV; 低于此=对地短路/未供
static const long MV_MAX_OK = 2100;   // 高于此=悬空/对电源短路
static const long MV_DELTA_ALERT = 60; // 与基线差超此值 → ALERT (P0 实测噪声 ±4mV, 60 足够安全)

static long base_mv[9][8];
static long last_mv[9][8];

static long read_adc_mv() {
  analogReadMilliVolts(PIN_ADC);        // 换通道首样弃掉 (100Ω+100nF RC 建立)
  delayMicroseconds(300);
  long s = 0;
  for (int i = 0; i < 8; i++) { s += analogReadMilliVolts(PIN_ADC); delayMicroseconds(50); }
  return s / 8;
}

static void all_en_off() { for (int i = 0; i < 9; i++) digitalWrite(PIN_EN[i], HIGH); }

static void select_ch(int mux, int ch) {
  all_en_off();
  digitalWrite(PIN_MUX_A, ch & 1 ? HIGH : LOW);
  digitalWrite(PIN_MUX_B, ch & 2 ? HIGH : LOW);
  digitalWrite(PIN_MUX_C, ch & 4 ? HIGH : LOW);
  digitalWrite(PIN_EN[mux], LOW);       // 低有效, 只开当前这一片
}

static void sweep(long out[9][8]) {
  for (int m = 0; m < 9; m++)
    for (int c = 0; c < 8; c++) { select_ch(m, c); out[m][c] = read_adc_mv(); }
  all_en_off();
}

static void take_baseline() {
  sweep(last_mv);                        // 首扫弃掉 (MUX/RC 稳定)
  for (int r = 0; r < 4; r++) {          // 4 轮均值当基线
    sweep(last_mv);
    for (int m = 0; m < 9; m++)
      for (int c = 0; c < 8; c++) base_mv[m][c] = (r == 0) ? last_mv[m][c]
                                              : (base_mv[m][c] + last_mv[m][c]) / 2;
  }
}

void setup() {
  pinMode(PIN_LED1, OUTPUT);
  for (int i = 0; i < 9; i++) { pinMode(PIN_EN[i], OUTPUT); digitalWrite(PIN_EN[i], HIGH); }
  pinMode(PIN_MUX_A, OUTPUT); pinMode(PIN_MUX_B, OUTPUT); pinMode(PIN_MUX_C, OUTPUT);

  Serial.begin(115200);
  delay(2000);                           // 电源/RC 静置
  Serial.println();
  Serial.println("======== KeyCore 收板自检 ========");

  Serial.printf("芯片   : %s rev%d @ %u MHz\n",
                ESP.getChipModel(), ESP.getChipRevision(), ESP.getCpuFreqMHz());

  uint32_t flash_kb = 0;
  esp_flash_get_size(NULL, &flash_kb);
  Serial.printf("Flash  : %u KB  (期望 4096 = 4MB)\n", flash_kb);

  bool ps = psramInit();
  Serial.printf("PSRAM  : %s, %u bytes  (期望 8388608 = 8MB OPI; 认不到查 qio_opi)\n",
                ps ? "OK" : "FAIL", ESP.getPsramSize());
  if (ps && ESP.getPsramSize() > 0) {
    uint8_t *buf = (uint8_t *)ps_malloc(4096);
    bool rw = (buf != nullptr);
    if (rw) {
      memset(buf, 0xA5, 4096);
      rw = (buf[0] == 0xA5) && (buf[4095] == 0xA5);
      free(buf);
    }
    Serial.printf("PSRAM 读写: %s\n", rw ? "OK" : "FAIL");
  }

  Serial.printf("ADC 引脚: IO%d (ADC1, 网络 Z_F) —— 若矩阵全 0/全 4095, 优先查采样链供电\n", PIN_ADC);
  Serial.println("LED1 (IO38) 将每 0.5s 闪烁; 串口发任意字符 = 重新取基线");

  take_baseline();
  Serial.println("======== 基线取好, 开始扫描 ========");
}

void loop() {
  static uint32_t sweep_n = 0;

  if (Serial.available()) {
    while (Serial.available()) Serial.read();
    take_baseline();
    Serial.println(">> 基线已更新");
  }

  sweep(last_mv);
  sweep_n++;

  int ok = 0, alerts = 0;
  for (int m = 0; m < 9; m++)
    for (int c = 0; c < 8; c++) {
      long v = last_mv[m][c];
      if (v >= MV_MIN_OK && v <= MV_MAX_OK) ok++;
      long d = v - base_mv[m][c];
      if (abs(d) > MV_DELTA_ALERT) { alerts++; Serial.printf("ALERT EN%d ch%d = %ldmV (Δ%+ld)\n", m + 1, c, v, d); }
    }
  Serial.printf("sweep#%u  ok=%d/72  alert=%d\n", sweep_n, ok, alerts);

  if (sweep_n % 8 == 0) {               // ~每 5s 打一轮完整矩阵
    Serial.println("-- 通道矩阵 mV (EN行 × ch列) --");
    for (int m = 0; m < 9; m++) {
      Serial.printf("EN%d:", m + 1);
      for (int c = 0; c < 8; c++) Serial.printf(" %4ld", last_mv[m][c]);
      Serial.println();
    }
  }

  digitalWrite(PIN_LED1, (sweep_n & 1) ? HIGH : LOW);   // 心跳: LED 每 0.5s 翻转
  delay(440);
}
