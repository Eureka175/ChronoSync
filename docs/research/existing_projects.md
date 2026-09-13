# 现有项目技术调研与差异矩阵

> 调研方式：实时 web 检索 + GitHub 源码/API/README 核查（各子报告见
> `docs/research/notes/`，逐条带引用与置信度标记）。
> 规则：无法确认的事实一律写 **Unknown / 需要进一步验证**，不编造。

## 0. 一句话结论

* **AudioAlign / Aurio**（C#，AGPL-3.0）是功能最接近 ChronoSync 目标的研究系统
  （指纹粗匹配 → 归一化互相关精修 → **分段线性时间扭曲 + 变速率重采样**校正漂移
  → 锁定参考轨的多轨图），但只能抄设计，不能抄代码。
* **audalign**（Python，MIT）是唯一可直接 pip 安装复用的完整对齐包，但
  **没有 drift 校正、没有图求解、没有亚样本精修、没有 DAW 工程导出**。
* **alignaudio**（C，GPL-3.0，已停更原型）是唯一有完整漂移校正流水线的项目
  （分块相关 → 最小二乘 ppm 拟合 → 重采样），但 C/GPL/两文件/丢样本重采样；
  只能借鉴算法思想，必须自己用 sinc 重采样重写。
* **WhisperSync 不存在**（该名字下没有匹配本项目描述的公开项目）；
  最接近的公开物是 Rust 的 podsync（无许可证）与 Descript 专利
  （转录锚点 + 线性漂移拟合）。Whisper 对 ChronoSync 是**可选证据源**，
  不是基础依赖。
* 音频栈结论：`soundfile(libsndfile) + soxr(libsoxr) + numpy/scipy`，
  PyAV 兜底解码 MP3/AAC/视频容器；注意 **libsoxr 是 LGPL-2.1 而非 BSD**。

## 1. 技术差异矩阵

符号：✅ 有 / ⚠️ 部分或受限 / ❌ 无 / `U` Unknown（需进一步验证）

| 项目 | 粗定位 | 精对齐 | Drift | 多轨 | 非线性时间映射 | 验证 | DAW |
| --- | --- | --- | --- | --- | --- | --- | --- |
| AudioAlign | ✅ 指纹×4（Haitsma-Kalker/Wang2003/Echoprint/Chromaprint） | ⚠️ 归一化互相关，11050 Hz，1 s 窗 ±25%，**无亚样本插值**（≈90 µs 分辨率） | ✅ **分段线性 TimeWarp + 变速率重采样**（GUI 默认 SoX） | ✅ 两两配对 + 连通分量 + Locked 参考轨 | ✅ 分段线性；可选 DTW/OLTW（谱差特征） | ✅ Similarity + Source 溯源（FP/CC）、滑动窗过滤、ValidateMatches、Analysis 模块 | ⚠️ 仅 Sony Vegas EDL（另有 Sync XML / Matches CSV） |
| Aurio | ✅（上四项指纹的库实现） | ⚠️ 同 AudioAlign | ✅ TimeWarpStream 可变速率 | ✅ 流式管线可组合 | ✅ | ⚠️ | ❌（库） |
| audalign | ✅ 频谱地标指纹（SHA1 星座哈希×4 风格，histogram 投票） | ⚠️ 8 kHz 降采样裸互相关 + find_peaks，**无亚样本插值**（0.125 ms 分辨率） | ❌ **完全无 drift 校正**（grep 确认） | ⚠️ 全配对 + "最多匹配者当参考 + 1 跳"（源码 TODO 自认非图求解） | ❌ 仅常数 offset | ⚠️ heuristic rankings 1-10 + 各 recognizer 置信度（"not definitive proof"） | ❌ 无 RPP；多通道 WAV + 正值偏移供手工摆放 |
| alignaudio | ✅ 三档幅度包络扫描（65536→4096→256 块） | ⚠️ 包络相关 + 抛物线亚块精修 | ✅ **分块局部 offset → 线性最小二乘 ppm 拟合 → 重采样**（丢/补样本，非 sinc） | ❌ 仅两文件 | ❌ 仅线性 | ❌ 无置信度 | ❌ 仅 WAV |
| WhisperSync | U（**公开项目不存在**） | U | U | U | U | U | U |

### 关于 WhisperSync 的说明（不编造）

* 该名称下唯一相关公开物：商业 SaaS "WhisperSync"（Whisper 时间戳强制对齐，
  ~50 ms，字幕用途，非音频同步）；jasalt/WhisperSync（YouTube 字幕，无关）。
* 与描述特征集最接近的公开项目：**kaushikgopal/podsync**（Rust，多轨播客对齐：
  WebRTC VAD + MFCC 互相关 + 漂移测量 + DAW 就绪 WAV；**无许可证**、
  无 GCC、无分段校正）；**ellite/anchor-sub-sync**（AGPL，字幕同步）。
* 描述中的"转录锚点 + 线性漂移拟合"技术见 **Descript 专利**
  US20200126559A1 / US20200126583A1（专利，无公开代码）。
* 构建块：faster-whisper（MIT）、whisperX（BSD-2）、openai-whisper（MIT）、
  whisper.cpp（MIT）均可调用；⚠️ aeneas/anchor-sub-sync（AGPL）、
  find_delay（GPL）不可并入 MIT 项目。

## 2. 复用决策

### 2.1 可直接复用

| 对象 | 用途 | 许可证 |
| --- | --- | --- |
| `audalign`（pip） | 基准/交叉验证实现；粗匹配指纹、preprocess（uniform leveling/noisereduce）可作为参考实现与对照测试 | MIT ✅ |
| numpy / scipy | FFT（rfft/next_fast_len）、correlate、find_peaks、peak_prominences、coherence、resample_poly | BSD-3 ✅ |
| soundfile（libsndfile） | WAV/BWF/RF64/FLAC/OGG 解码、分块读取、dtype 转换 | BSD-3 wrapper + LGPL-2.1 C ✅ |
| soxr（libsoxr） | 高质量重采样 + `ResampleStream` 流式/变速率（drift 校正的关键能力） | BSD-3 wrapper + **LGPL-2.1 C**（注意：不是 BSD）✅ |
| PyAV | MP3/AAC/视频容器兜底解码 | BSD-3 + LGPL FFmpeg ✅ |
| faster-whisper / whisperX（未来可选） | 语音锚点证据（Phase 8+ 可选模块） | MIT / BSD-2 ✅ |

### 2.2 可调用成熟库（替换"自己造"的组件）

* 指纹：Phase 3 粗匹配候选 `audalign` 直接调用（或 pyacoustid/chromaprint/dejavu，
  注意 Haitsma-Kalker/Wang/Echoprint 的**专利警告**，商用需评估）；
* 变速率重采样：`soxr.ResampleStream`（AudioAlign 的 TimeWarpStream 的
  Python 对应物）——ChronoSync 的 drift 校正将构建在它之上；
* VAD（未来语音锚点路径）：WebRTC VAD / Silero VAD（BSD/MIT）。

### 2.3 值得自己实现（现有项目缺失或不够好）

1. **GCC-PHAT + 峰值策略 + 抛物线亚样本**（Phase 1 已完成）——
   AudioAlign 精对齐无亚样本、audalign 无亚样本、均非 GCC-PHAT；
2. **Drift 估计器**：短窗 GCC → 局部 offset(t) → 线性/分段线性拟合 +
   **clock drift vs discontinuity vs 坏测量分类**（alignaudio 只有线性最小
   二乘且自认 "too fuzzy"；audalign 完全没有；AudioAlign 靠人工/DTW）；
3. **多轨图求解**（WLS + 连通性 + 边残差 + 每轨置信度）——
   audalign 是"最多匹配+1跳"启发式，AudioAlign 靠锁定轨+人工；
4. **可解释置信度**（evidence + warnings 组合）——所有现有项目的置信度
   都是启发式数字；
5. **Overlap/Segment 检测**（区分"同一时间线"与"同样时长"）——无人实现；
6. **DAW 工程导出**（Reaper RPP / Adobe Audition SESX，非破坏性时间线）——
   AudioAlign 仅 Vegas EDL；audalign 仅正值偏移 WAV。

### 2.4 ChronoSync 的独特目标（差异点总结）

```text
现有项目：        固定 offset（audalign）/ 人工辅助 warp（AudioAlign）/ 两文件线性（alignaudio）
ChronoSync：      TimeMap 统一抽象（identity/constant/linear/piecewise）
                   + 自动 drift 估计（窗口 GCC + 回归 + 断点分类）
                   + 多轨全局约束求解（图 + WLS + 连通性 + 残差）
                   + 可解释置信度（evidence 溯源）
                   + 非破坏性 DAW 时间线导出
                   + 长文件流式 + 特征缓存
                   + Whisper 作为可选锚点证据（非基础依赖）
```

## 3. 设计借鉴清单（抄设计，不抄代码）

| 来源 | 借鉴的设计 |
| --- | --- |
| AudioAlign/Aurio | Match{Similarity, Source} 证据溯源；TimeWarpCollection 分段线性映射 + 变速率重采样；ConvertToIntervals（偏移跳变阈值切分段，即我们的 discontinuity 检测原型）；WindowFilter（滑窗取最佳匹配）；锁定参考轨语义；可插拔工厂（decoder/resampler/FFT） |
| audalign | 指纹投票直方图取 offset；most-matched 参考轨选择（我们将升级为图求解）；8 kHz 降采样相关作为廉价粗路径 |
| alignaudio | 分块局部 offset → 最小二乘 ppm 拟合 → 重采样校正的完整漂移流水线（我们用 sinc/SoXR 替换丢样本） |
| podsync | 双窗口交叉印证（corroborating region）防周期性内容误锁 |
| Descript 专利 | 转录锚点 → (t_master, t_device) 对 → 线性拟合（仅作技术参考，注意专利） |

## 4. 各项目局限性摘要

* **AudioAlign**：AGPL；Windows GUI；2024-01 起休眠；精对齐无亚样本；
  指纹算法有专利风险；原生后端仅 Windows 二进制。
* **Aurio**：AGPL（可协商双许可）；文档缺失；单人维护。
* **audalign**：无 drift、无图求解、无亚样本、无 DAW 导出；
  依赖硬钉版本（numpy 1.26.4 等，可能与 ChronoSync 冲突）；
  需要系统 ffmpeg；处理路径降 16-bit mono。
* **alignaudio**：C/GPL；两文件；16-bit PCM WAV；丢样本重采样（有混叠）；
  无置信度；0.1.0 原型。
* **WhisperSync 类**：无公开实现；Whisper 原始词级时间戳不可靠（需强制对齐）；
  1-4 小时多轨 CPU 推理成本不可忽略；AGPL/GPL 陷阱多（aeneas、anchor-sub-sync、find_delay）。
* **音频栈**：libsoxr 是 **LGPL-2.1**（常被误认为 BSD）；PyAV wheel 是否内置
  swresample 的 soxr 引擎 `U`；libsoxr 独立 SNR 数据 `U`（引用 SoX 对比数据）。
  —— 对 MIT 项目均可接受（动态链接 + 保留声明），但必须避免 GPL FFmpeg 构建。

## 5. 对 ChronoSync Phase 1 已作出的实际影响

* 精对齐选 **GCC-PHAT**（所有现有项目都未实现）——已实现并测试（ADR-004）；
* 内部格式 48 kHz/float32 + SoXR 重采样（与 AudioAlign 的可变速率 resampler 选择一致）；
* 模型带 `evidence` + `warnings`（对应 Match.Similarity/Source 的升级）；
* `TimeMap` 抽象直接对应 TimeWarpCollection 的分段线性思想（ADR-005）；
* 粗匹配级联（Phase 3）将把 `audalign` 作为对照实现而非替代品。

## 6. 需要进一步验证（明确未决项）

* audalign 是否受 AudioAlign 启发（作者未声明）——`U`；
* audalign 对 Python 3.12+ 的官方支持声明——`U`（requires-python ≥3.8）；
* PyAV 各 cp-tag wheel 与版本映射、wheel 内 soxr 引擎——`U`；
* libsoxr 独立 SNR-in-dB 数据——`U`；
* 是否存在其他实现"分段漂移校正"的公开 Python 项目——`U`（本次检索未发现）。
