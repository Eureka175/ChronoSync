# ADR-009：Drift 估计方法

**状态：** Accepted（2025，Phase 4）
**影响面：** drift/、models/timemap.py

## 决策

```text
窗口 GCC（target 窗按粗 offset 放置 → 测残差，prior 解歧义）
→ OffsetMeasurement 序列（记录完整 d(t) = 残差 + d0）
→ 鲁棒加权回归（MAD 离群剔除）
→ 变点检测 → 分类 → TimeMap
```

## 关键实现决策

1. **窗口放置与残差测量**：target 窗口放在 `center + d0`，GCC 测残差
   （数值更稳）；`OffsetMeasurement.offset_samples` 记录**完整** d(t)
   （内部实现细节不外泄）。
2. **自适应窗口收缩**：PHAT 每频点等权投票——噪声类内容在窗口内漂移
   超过 ~1 个相干长度时长窗 GCC 失明（实测 60 s 白噪声 @150 ppm 单窗
   完全失效）。默认 30 s 起，不足 12 个可用窗口则半衰收缩至 0.5 s 下限。
3. **变点检测 = 加权 SSE 改进 + 效应量门限**：两段拟合的 SSE 改进
   ≥ 25% 且（台阶 ≥ 100 样本 或 斜率变化 ≥ 4 ppm）才切分。纯 SSE 判据
   在 50% 重叠窗口的相关噪声下假分裂（实测常数偏移对被切成 3 段）。
   台阶与斜率变化统一检测：CLOCK_DISCONTINUITY（台阶）vs
   piecewise_drift（斜率变化）。
4. **符号与单位**：`d(t) = α·t + β`（ADR-003，β 为样本）；
   `T_global = τ/(1+α) − β/(sr(1+α))`；constant 情形 offset_seconds =
   −β/sr（实测修复过符号）。
5. **断点 TimeMap 建模**：断点处两段映射到同一全局时刻 → 平段（drop 的
   空隙或 insert 的重复区间），校正时输出静音/跳过；负向局部跳变
   （内容丢失）显式警告。
6. **校正 = SoXR 异步重采样**（ADR-002 的变速率能力），非 phase vocoder；
   全局 0 之前的内容丢弃并警告。

## 后果

* `correct_track` 是可选渲染；默认输出仍是 TimeMap（非破坏性）；
* 分类结果（no_overlap/constant/clock_drift/piecewise/discontinuity）
  进入置信度证据链（Phase 7）；
* 白噪声类内容的短窗需求是物理约束，测试用显式 config 固化。
