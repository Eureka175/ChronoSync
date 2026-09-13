# 算法说明（Phase 1：GCC-PHAT）

## 1. GCC-PHAT 数学定义

输入两路单声道信号（内部 float64，可选去均值 + RMS 归一化）：

```text
nfft = next_fast_len(len(ref) + len(tgt) - 1)     # 零填充 → 线性相关，非循环
R = rfft(ref, nfft)                               # 实 FFT，内存减半
T = rfft(tgt, nfft)
G[k] = conj(R[k]) · T[k] / ( |R[k]|·|T[k]| + ε )  # PHAT 白化
gcc[j] = irfft(G, nfft)  ≈  Σ_n ref[n] · tgt[n + j]    (j ≤ nfft/2)
```

* 负 lag 环绕：`lag = j - nfft`（j > nfft/2）。
* 有效 lag 区间：`[-(len(tgt)-1), len(ref)-1]`；搜索区间自动裁剪到该区间。
* 方向（ADR-003）：`tgt[n] = ref[n-N]` ⇒ `gcc` 峰值在 `+N`。

### 正则化 PHAT

```text
ε = ε_rel · max|G| + ε_abs       ε_rel = 1e-3, ε_abs = 1e-12（默认，均可配置）
```

纯绝对下限（ε_rel = 0）会把窄带信号的频谱泄漏/近零频点全部白化到单位
幅度，导致纯正弦这类信号的 GCC 完全被泄漏主导（实测峰高 0.34 且位置错误）。
相对下限只白化"信息量足够"的频点，其余频点保留自然幅度：
宽带信号峰高仅损失约 1%（实测 0.90 vs 理论 1.0），纯正弦则退化为其
普通互相关（位置模周期正确、峰高极小、置信度低——正确行为，见 §4）。

## 2. 峰值策略（fine/peak.py）

禁止"全局最大 = 答案"。流程：

1. `scipy.signal.find_peaks` 发现候选（distance=2），窗口两侧补 `-inf`
   **再发现**——scipy 不会报告数组边缘的峰（实测坑，已修）；候选须严格
   大于两侧邻点（消除补边平台伪峰），prominence 在原始窗口上计算。
2. 候选按高度降序；primary/secondary 由 `PeakSelectionConfig` 选择：
   * `exclusion_samples = 8`：second peak 必须距 primary ≥ 8 样本；
   * 可选 **prior**：高度在 `(1 - prior_tolerance)` 之内的候选按与
     prior 的距离重排（用于周期信号等歧义场景；prior 不伪造证据，
     置信度仍如实反映测量质量）。
3. 亚样本：抛物线插值（§3）。

## 3. 亚样本估计（fine/subsample.py）

```text
delta = 0.5·(y[-1] - y[+1]) / (y[-1] - 2·y[0] + y[+1])   ，裁剪到 [-0.5, +0.5]
peak  = y[0] - 0.25·(y[-1] - y[+1])·delta
```

**定位声明**：抛物线插值是数值估计，不等于物理世界绝对时间精度。
基准（10 s/60 s 纯延迟、干净白噪声）实测误差 < 0.001 样本，该数字只对
该具体条件成立；带噪/混响条件下的误差需以 benchmark 为准，文档不承诺
"0.1 sample absolute accuracy"。

## 4. Confidence（可解释证据）

`confidence = 0.3·height + 0.5·ratio + 0.2·prominence`，各项 ∈ [0,1]：

| 证据 | 定义 | 含义 |
| --- | --- | --- |
| height | `log10(v/nf) / log10(1/nf)`，`nf = √(2·ln nfft)/√nfft`（单位幅度随机相位谱的期望峰值） | 峰相对噪声底有多高 |
| ratio | `(r-1)/(r-1+0.5)`，`r = v/second_peak` | 峰是否唯一（歧义性） |
| prominence | `prominence / v` | 峰是否尖锐 |

ratio 权重最大：周期信号 / 回声链造成的**峰歧义是时延估计最危险的失败
模式**。`success = v ≥ 2·nf`。

已知且被测试固化的行为：

* 干净宽带信号：conf ≈ 0.95+，success ✓；
* SNR 0 dB：conf ≈ 0.6，位置仍准；
* 周期信号（稀疏梳状谱）：PHAT 每个频点等权投票 ⇒ 峰高天然极小
  （≈ 占用频点数/nfft），`success=False` + conf < 0.6 + "ambiguous" 警告，
  但位置仍模周期正确；给定 prior 后位置精确（≈ 真值），置信度不变高。
  —— 这是**正确的诚实行为**：GCC 解决不了歧义时不得假装成功，粗匹配
  / 瞬态层会接力。

## 5. Drift 的窗口化测量（Phase 4 预告，已被测试固化）

白噪声 + 200 ppm 漂移时，单次全长 GCC 对漂移**失明**（漂移使频谱
`R[k]` 与 `T[k] = R[k(1+p)]` 去相关，峰高 ≈ 0.007，位置随机）。
这正是 drift 层必须用短窗的原因：窗内漂移 < 2 样本时
`d(n) = ppm·1e-6·n` 可测（测试 `test_drift_ppm_gcc_sees_local_offset_in_short_windows`
实测 8192 样本窗内误差 < 1 样本）。30-60 s 窗 + 50% overlap → 局部
offset(t) → 拟合 → TimeMap 的完整流程在 Phase 4 实现。

## 6. 合成框架的关键语义

* `delay_samples(x, n)`：`y[n+k] = x[k]`，越界内容丢弃、对侧补零
  （"录音开始得更晚"的物理语义）；
* `fractional_delay`：窗 sinc FIR（taps 必须为**奇数**——偶数长度核
  `np.convolve(mode="same")` 会引入 taps/2 样本的偏移，实测坑，已修）
  + 整数移位；边界区近似，仅内部精确；
* `drift_ppm(x, ppm)`：按 `(1+ppm·1e-6)` 高质量重采样（soxr）；
  ppm > 0 ⇒ target 时钟更快 ⇒ `d(n) = ppm·1e-6·n`；
* `piecewise_drift`：各段保持**自然漂移长度**（物理正确），接缝 5 ms 交叉淡化；
* 一切随机均带 seed，全部可复现。

---

## 7. 粗匹配级联（Phase 3，coarse/）

级联顺序与短路策略（每个阶段都返回 `MatchResult`，绝不返回裸 float）：

```text
metadata（只提供 prior，从不声称 matched）
    → fingerprint（星座地标哈希 + 偏移投票直方图）
    → envelope（抽取 RMS 包络 → 100 Hz 抽取 → 归一化互相关）
    → transient（谱通量瞬态事件的偏移投票直方图）
    → No Match
```

* **metadata**：文件 mtime 差作为搜索 prior；时长/采样率作为证据；
  永不 matched=True（BWF 时间码解析留待以后）。
* **fingerprint**（features/fingerprint.py）：STFT（11025 Hz 工作率，
  fft 1024/hop 512）→ **绝对 dB 标定**的对数幅度谱（输入单位 RMS 归一，
  除以窗能量，完整能量帧 ≈ 0 dB——跨 chunk、跨文件可比，增益不变）→
  2-D 局部极大（21×11 邻域，-45 dB 阈值）→ 目标区配对
  (f1, f2, Δt) 哈希 → 偏移投票直方图 + 抛物线亚帧精修。
  * 分块处理与单次计算**逐哈希一致**（块边界 ±5 帧上下文，实测修复）。
  * 置信度 = 0.7·投票占比分 + 0.3·峰比，再乘 min(1, votes/5) 投票门限。
  * 精度：±0.5 帧（@11025 Hz ≈ ±23 ms），是"粗"定位；drift 层负责精化。
* **envelope**：包络抽取到 ~100 Hz（包络已是平滑能量信号，块均值抽取
  不是音频重采样，不违反 ADR-002）→ scipy 归一化互相关
  （**注意方向：scipy correlate 峰值 = −d**，实测固化）→ 抛物线亚样本。
* **transient**：谱通量（STFT 分块，hop 对齐保证分块==单次）→ 峰值
  → 10 ms bin 加权投票直方图。
* 级联契约：任一阶段 `matched 且 confidence ≥ accept_confidence` 即返回；
  全部失败时返回最佳证据 + matched=False（低于接受阈值绝不伪装成功）。

## 8. Drift 估计（Phase 4，drift/）

```text
窗口调度（参考时间线，30-60 s 默认，50% overlap，自适应收缩）
    → 每窗 GCC（target 窗按粗 offset 放置 → 测残差；prior 解歧义）
    → OffsetMeasurement 序列（记录完整 d(t)）
    → 鲁棒加权回归（MAD 离群剔除 = "bad measurement"）
    → 变点检测（两段拟合的加权 SSE 改进 ≥25% 且 台阶≥100 样本 或 斜率变化≥4 ppm）
    → 分类：clock_drift / constant_offset / piecewise_drift /
             discontinuity / no_overlap
    → TimeMap（linear / constant / piecewise，断点处平段建模）
```

**关键物理约束（实测固化）**：PHAT 白化给每个频点等权投票；窗口内漂移
超过约 1 个相干长度时，噪声类信号的频谱 `R[k]` 与 `T[k]=R[k(1+p)]` 去
相关，长窗 GCC 峰被抹平（60 s 白噪声 @150 ppm 单窗完全失明）。因此：
* 白噪声类内容需要 `T < 1/(ppm·f_max)` 的短窗（实测 8192 样本 @150 ppm
  → α 误差 < 1 ppm）；
* 估计器**自适应收缩**窗口（默认 30 s → 半衰 → 下限 0.5 s）直到足够的
  窗口通过置信度门槛；
* 30 s 窗 + 语音类内容（120 ppm）实测 α 误差 < 5 ppm、R² > 0.98。

**漂移 vs 断点 vs 坏测量 vs 无重叠**：偏移随时间变化不自动等于 clock
drift——变点检测区分台阶（CLOCK_DISCONTINUITY，实测跳变量精确到样本）与
斜率变化（piecewise_drift，实测 250/-100 ppm 两段 α 精确到 <1 ppm）；
MAD 离群剔除单独报告坏窗口；窗口数不足 → no_overlap。

**校正（可选渲染）**：`correct_track` 用 SoXR 异步重采样把轨道渲染到
全局时间线（不是 phase vocoder，不是音乐性 time-stretch）；断点平段输出
静音；全局 0 之前的内容丢弃并警告。实测：150 ppm 白噪声对校正后残差
GCC < 2 样本。

## 9. Adobe Audition SESX 导出（Phase 3+，export/sesx.py）

调研结论（docs/research/notes/sesx_format.md，社区逆向 + 双 MIT 生产级
writer 验证）：SESX 是**无校验和的纯 XML**；**所有时间字段为会话采样率
下的整数样本**；clip 通过 `<files>` 表引用外部 WAV（非破坏性）。

保真规则（诚实声明）：

* identity/constant-offset TimeMap → 单个精确 clip（整数样本）；
* 线性 drift → 可配置粒度的阶梯近似 clip（Audition clip **不能变速**；
  每 chunk 的台阶误差 ≤ ppm·chunk_seconds 个样本；精确校正走
  correct_track 渲染）；
* 分段映射（断点）→ 每结点区间一个 clip，平段成为时间线空隙
  （丢失内容不虚构）；
* 负全局起点自动裁剪（clip 从 0 开始，source in-point 前移）。

## 10. Overlap / Segment 检测（Phase 5，overlap/）

轨道内容 = 其 TimeMap 在本地时间轴上的**像集**。关键区分：同一时间线
≠ 同样时长——有录音间隙的轨道建模为 **span 列表**
（每段 = 本地区间 + 仿射映射；间隙无法用单一单调 local→global 函数
表达而不虚构内容）。两轨像集求交 → 重叠 Segment。

* 官方示例（Track A 0-60 min；Track B 录 0-10/20-40/50-60）→ 3 个
  Segment，每段携带双方本地区间（测试固化）；
* 平段（drop）被排除在录制 span 之外；drop 造成的本地空洞不产生全局
  空洞（内容覆盖连续，实测纠正过直觉错误）。

## 11. 多轨全局求解（Phase 6，global_alignment/，ADR-011）

`min Σ w_ij (t_i - t_j - d_ij)²`，参考轨=0；正规方程按连通分量求解；
残差、离群边（>3×robust sigma）、每轨置信度；可选 IRLS（Huber 重加权，
实测离群边污染下显著优于普通 WLS）。50 轨/1225 边求解 ~12 ms。

## 12. 验证与置信度（Phase 7，validation/，ADR-012）

残差 GCC（静音窗跳过）· coherence · polarity（MSC 低 ≠ 反相——
corr(x,y) vs corr(x,-y) 对比）· 加权证据聚合（coarse 0.25 / drift R²
0.20 / 残差 0.25 / coherence 0.15 / polarity 0.15）。

* **GCC 反相感知**（fine/）：反相对的相关峰为负，负峰明显更强
  （>1.2×）时翻转相关面分析并返回 `polarity=-1`——没有它反相对的
  drift 整体失效（实测）；
* **验证在校正后信号上进行**：原始漂移对 coherence 天然崩溃
  （120 ppm/30 s 实测 MSC≈0.026），漂移抹平不是失配证据。

