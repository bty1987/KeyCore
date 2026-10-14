// ============================================================
// 透明屏幕键盘 · P0 单键验证固件 (已完成使命, 保留备查)
// 2026-09 P0 验证 PASS (06-测试记录/P0-验证报告.md, 隔屏 Δ+1023mV)
// 用法: pio run -t upload -e p0-single-key
// 面包板 rig 接线: 49E 霍尔 VCC->3V3 GND->GND OUT->GPIO4
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
