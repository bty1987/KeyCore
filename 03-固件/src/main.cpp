// ============================================================
// 透明屏幕键盘 · P0 单键验证固件
// 目的：验证磁铁隔着「屏体+夹层」的行程信号是否干净（全案物理前提）
//
// 接线（3 根线）：
//   49E 霍尔  VCC -> 3V3
//           GND -> GND
//           OUT -> GPIO4
//
// 读数说明：
//   49E 是 ratiometric 线性霍尔：0 磁场时输出 ≈ VCC/2 ≈ 1650mV
//   磁铁 N 极朝向霍尔 → 输出升高；S 极朝向 → 降低（正式设计 N 朝下=升高）
//   曲线单调、无跳变即为合格；Δ≥80mV 过全案验收线
//
// 串口输出两列：raw_mv, delta_mv（delta = raw - 开机基线）
//   Arduino IDE 2.x → 工具→串口绘图器 直接看曲线
// ============================================================

#include <Arduino.h>

const int HALL_PIN = 4;

long baseline_mv = 0;

static long read_mv_avg(int n = 16) {
  analogReadMilliVolts(HALL_PIN);      // 切换后首样弃掉
  delayMicroseconds(200);
  long sum = 0;
  for (int i = 0; i < n; i++) {
    sum += analogReadMilliVolts(HALL_PIN);
    delayMicroseconds(100);
  }
  return sum / n;
}

void setup() {
  Serial.begin(115200);
  analogReadResolution(12);
  pinMode(HALL_PIN, INPUT);

  // 基线：上电静置 2 秒后取均值（周围别放磁铁）
  delay(2000);
  long s = 0;
  for (int i = 0; i < 64; i++) { s += read_mv_avg(8); delay(5); }
  baseline_mv = s / 64;

  Serial.println("raw_mv,delta_mv");
}

void loop() {
  long mv = read_mv_avg();
  Serial.printf("%ld,%ld\n", mv, mv - baseline_mv);
  delay(10);   // ~90Hz 输出，绘图器曲线顺滑
}
