# ADR-007：现有项目分析与复用决策

**状态：** Accepted（2025，Phase 0/1）
**影响面：** 全部后续阶段的组件选型
**依据：** docs/research/existing_projects.md 及 notes/ 下的四份调研子报告

## 决策

1. **不移植任何现有对齐项目**（AudioAlign/Aurio 为 C#/AGPL；
   alignaudio 为 C/GPL；WhisperSync 类无公开实现）。
2. **可复用对象**：audalign（MIT，pip）作为粗匹配对照实现与基准；
   numpy/scipy 承担全部 DSP；soundfile + soxr + PyAV 承担 I/O 与重采样。
3. **自研清单**（现有项目缺失或不足）：GCC-PHAT + 峰值策略 + 亚样本；
   drift 估计器（窗口 GCC → 回归 → 漂移/断点/坏测量分类）；多轨图求解
   （WLS + 连通性 + 残差）；可解释置信度；Overlap/Segment；DAW 时间线导出。
4. **设计借鉴（只抄概念）**：AudioAlign 的 Match{Similarity,Source} 溯源、
   TimeWarpCollection 分段线性 + 变速率重采样、ConvertToIntervals 断点切分、
   锁定参考轨；alignaudio 的分块偏移 → 最小二乘 ppm 拟合流水线；
   podsync 的双窗交叉印证。
5. **Whisper 定位**：可选语音锚点证据源（Phase 8+），信号路径
   （VAD + GCC + 漂移回归）必须独立可用——ChronoSync 不做 WhisperSync clone。

## 许可证红线

* 并入/链接的库必须 MIT/BSD/ISC 或 LGPL（动态链接 + 保留声明）；
* **禁止**并入 GPL/AGPL 组件（aeneas、anchor-sub-sync、find_delay、
  AudioAlign/Aurio/alignaudio 的代码）；
* 指纹算法（Haitsma-Kalker/Wang/Echoprint）有专利风险——Phase 3 选型时
  单独评估，优先无专利风险的实现；
* libsoxr 为 LGPL-2.1（非 BSD）——README/许可证声明必须如实标注。

## 后果

* Phase 3 粗匹配以 audalign 为对照、非依赖；
* Phase 4 drift 校正以 soxr.ResampleStream（变速率）实现，不用
  alignaudio 式丢样本；
* 所有自研模块的 API 遵循本项目 ADR-001..006（Python-first、规范格式、
  offset 约定、GCC 策略、TimeMap、缓存）。
