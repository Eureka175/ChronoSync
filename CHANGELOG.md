# Changelog

本项目的所有重要变更都记录在此文件。
版本号遵循 [PEP 440](https://peps.python.org/pep-0440/)（`0.1.0b0` = 发布名 `v0.1.0-beta`）。

## [v0.1.0-beta] — 2026-09-03

首个公开 beta：从技术调研到 Phase 1–7 全链路实现，含真实素材验证的
无线麦通道同步专线。

### 新增 — 核心算法

* **Layer 0 · I/O**：`probe` / 规范化解码（48 kHz float32、削波加权声道混音）/
  SoXR 重采样 / 流式分块 `/ cli`
* **Layer 1 · 特征与缓存**：RMS 包络、谱通量+瞬态、星座指纹（分块==单次、
  绝对 dB 标定、增益不变）；SQLite 索引 + `.npy` 文件型特征缓存（ADR-006）
* **Layer 2 · 粗匹配级联**：metadata(prior) → fingerprint → envelope →
  transient 短路级联，输出完整 `MatchResult`（ADR-008）
* **Layer 3 · 精对齐**：GCC-PHAT（正则化白化、峰值策略、prior、抛物线亚样本、
  **反相感知**）、可解释 confidence（ADR-004 / ADR-012）
* **Layer 4 · Drift**：窗口 GCC（自适应收缩 30 s→0.5 s）→ 鲁棒加权回归 →
  变点检测/分类（clock_drift / constant_offset / piecewise_drift /
  discontinuity / no_overlap）→ TimeMap + SoXR 校正渲染（ADR-009）
* **Layer 5 · 多轨**：Overlap/Segment 检测（录音间隙 → 多段）；
  全局图求解 WLS/IRLS（参考轨=0、连通分量独立、边残差、每轨置信度，ADR-011）
* **Layer 6 · 验证**：残差 GCC、coherence、polarity（MSC 低 ≠ 反相）、
  加权证据聚合置信度（ADR-012）
* **Layer 7 · 导出**：Adobe Audition **SESX**（整数样本时间单位、阶梯近似、
  非破坏性，ADR-010）、JSON、CSV

### 新增 — 工具与交付

* CLI：`info` / `gcc` / `align` / `batch` / `mp4-sync` / `test-gcc` / `benchmark`
* `chronosync.mp4sync`：多流 MP4 无线麦延迟测量 + 样本级修正 + 重封装复检
* **`handoff/mp4_channel_sync/`**：面向外部工程（1KeyTranscoder）的纯算法包
  （仅 numpy+scipy）+ 完整文档 + 独立自测
* Synthetic Framework：seed 化合成数据（延迟/漂移/回声/混响/噪声/瞬态/
  伪语音 + 15 个场景）
* Benchmark：GCC / 特征 / drift / 图求解（wall / CPU / 峰值内存 + 精度）

### 测试

* **202 项 pytest**（单元 + 集成）全绿；交付包另有 16 项独立自测
* 真实素材验证：19 片 4K MP4（4×mono PCM），逐片测量无线麦延迟
  （19.7–29.5 ms，片内恒定），修正后复检残差 < 0.05 ms

### 文档

* `docs/architecture.md` / `docs/algorithms.md` / `docs/offset_convention.md`
* `docs/research/`：现有项目差异矩阵 + 6 份带引用的调研笔记（AudioAlign、
  Aurio、audalign、alignaudio、WhisperSync、音频栈、SESX 格式）
* `docs/adr/001`–`012`：Python-first、规范音频格式、offset 符号约定、
  GCC-PHAT、TimeMap、缓存、现有项目分析、粗匹配、drift、SESX、
  图求解、验证与置信度
* `docs/mp4_wireless_delay_case.md`：真实无线麦延迟案例

### 已知限制

* 未直接测量的轨道间尚未做 TimeMap 复合（用求解常数 offset 并警告）
* Reaper RPP 导出未实现（SESX 无法表达变速时间线）
* 真实录音大规模 benchmark（Phase 8）待做
