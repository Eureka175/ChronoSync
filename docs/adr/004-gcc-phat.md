# ADR-004：GCC-PHAT 为局部精对齐核心

**状态：** Accepted（2025，Phase 1）
**影响面：** fine/、drift/（Phase 4）、validation/（Phase 7）

## 决策

局部高精度对齐的核心工具为 GCC-PHAT：

```text
G[k] = conj(R[k])·T[k] / ( |R[k]|·|T[k]| + ε )
gcc  = irfft(G)
```

* 零填充（nfft ≥ len(ref)+len(tgt)-1）保证**线性**相关；
* 搜索区间可配置并裁剪到有效 lag；峰值策略（height/prominence/second
  peak/ratio/prior）见 docs/algorithms.md §2；
* 亚样本：抛物线插值（数值估计，不承诺绝对物理精度）；
* `GCCResult` 返回 delay/peak/second_peak/prominence/confidence/search_range
  /success/warnings，绝不只返回一个 float。

## 关键参数（全部可配置、可测试、有出处）

| 参数 | 默认 | 说明 |
| --- | --- | --- |
| `epsilon_rel` | 1e-3 | 相对白化下限（×max|G|），压制窄带信号泄漏白化 |
| `epsilon_abs` | 1e-12 | 绝对除零保护 |
| `_MIN_PEAK_FLOOR_RATIO` | 2.0 | success = 峰高 ≥ 2×噪声底 √(2·ln nfft)/√nfft |
| confidence 权重 | 0.3/0.5/0.2 | height / ratio / prominence（歧义权重最大） |
| `exclusion_samples` | 8 | second peak 与 primary 的最小间距 |
| `prior_tolerance` | 0.2 | prior 重排的高度容差 |

## 实测发现（固化为测试）

1. `scipy.signal.find_peaks` **不报告数组边缘的峰**——搜索边界恰为真峰时
   会漏检；实现中补 `-inf` 后再发现、严格双侧比较去伪峰。
2. 纯绝对 epsilon 使纯正弦的 GCC 被截断泄漏主导（峰 0.34、位置错）；
   相对 epsilon 1e-3 后宽带信号峰高仅损 ~1%，正弦行为正确退化
   （success=False、位置模周期正确、低置信度）。
3. 周期信号谱稀疏，PHAT 每频点等权投票 ⇒ 峰高天然 ≈ 占用频点数/nfft。
   GCC 的诚实行为是**报告歧义与低置信度**而非假装成功；prior 可给出
   精确位置但不提高置信度。
4. 白噪声 + 200 ppm 漂移时全长 GCC 失明（漂移使频谱去相关）；
   drift 层必须用短窗（Phase 4）。

## 后果

* drift/ 与 validation/ 复用同一 GCC 内核与 `GCCResult`；
* 阈值不得散落为魔法常量——一律走 `PeakSelectionConfig` / 具名常量；
* 修改置信度公式或峰值策略 = 修改本 ADR + docs/algorithms.md + 重跑
  benchmark。
