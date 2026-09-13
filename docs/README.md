# ChronoSync 文档索引

**版本：v0.1.0-beta**（PEP 440: `0.1.0b0`）

## 核心文档

| 文档 | 内容 |
|---|---|
| [../README.md](../README.md) | 项目定位、安装、快速开始、Roadmap |
| [../CHANGELOG.md](../CHANGELOG.md) | 版本变更记录 |
| [architecture.md](architecture.md) | 分层架构、数据流、包结构、依赖策略 |
| [algorithms.md](algorithms.md) | 全部算法：GCC-PHAT / 峰值策略 / 置信度 / 粗匹配级联 / drift 估计 / SESX / Overlap / 图求解 / 验证 |
| [offset_convention.md](offset_convention.md) | 全项目 offset 符号与单位规范（ADR-003 落地说明） |

## 架构决策记录（ADR）

| ADR | 决策 |
|---|---|
| [001](adr/001-python-first.md) | Python-first 技术路线（不提前引入 C++/Numba） |
| [002](adr/002-canonical-audio-format.md) | 内部规范音频格式 48 kHz / float32 / 加权 mono_mix |
| [003](adr/003-offset-sign-convention.md) | 全局 offset 符号约定 `d = t_target − t_reference` |
| [004](adr/004-gcc-phat.md) | GCC-PHAT 为局部精对齐核心（正则化白化、峰值策略） |
| [005](adr/005-time-map.md) | TimeMap 时间映射抽象（核心对象） |
| [006](adr/006-cache-design.md) | 特征缓存设计（SQLite 索引 + 文件型数组） |
| [007](adr/007-existing-project-analysis.md) | 现有项目分析与复用决策（含许可证红线） |
| [008](adr/008-coarse-cascade.md) | 粗匹配短路级联 |
| [009](adr/009-drift-estimation.md) | Drift 估计方法（窗口收缩、变点检测、分类） |
| [010](adr/010-sesx-export.md) | Adobe Audition SESX 导出 |
| [011](adr/011-graph-solver.md) | 多轨全局图求解（WLS/IRLS） |
| [012](adr/012-validation-confidence.md) | 验证与可解释置信度（含 GCC 反相感知） |

## 调研（Phase 0）

| 文档 | 内容 |
|---|---|
| [research/existing_projects.md](research/existing_projects.md) | 现有项目技术差异矩阵 + 复用/自研决策 |
| [research/notes/audioalign_aurio.md](research/notes/audioalign_aurio.md) | AudioAlign / Aurio（C#，AGPL）|
| [research/notes/audalign_alignaudio.md](research/notes/audalign_alignaudio.md) | audalign（Python, MIT）/ alignaudio（C, GPL）|
| [research/notes/whispersync.md](research/notes/whispersync.md) | WhisperSync 核查（结论：不存在该公开项目）|
| [research/notes/audio_stack.md](research/notes/audio_stack.md) | FFmpeg/PyAV/SoXR/soundfile 与许可证 |
| [research/notes/sesx_format.md](research/notes/sesx_format.md) | SESX 格式逆向（时间单位 = 整数样本）|
| [research/notes/audition_import_paths.md](research/notes/audition_import_paths.md) | Audition 导入路径评估 |

> 第三方参考物料（Adobe API 类型定义、广播台 .sesx 样例）因版权归属外部，
> 未随仓库分发；调研笔记内保留了原始 URL，可按需自行获取。

## 真实案例

| 文档 | 内容 |
|---|---|
| [mp4_wireless_delay_case.md](mp4_wireless_delay_case.md) | 无线麦通道延迟实测案例（19 片 4K MP4）|
| [../handoff/mp4_channel_sync/README.md](../handoff/mp4_channel_sync/README.md) | 外部工程交付包：纯算法（numpy+scipy）+ 集成指南 |

## 目录结构速查

```text
src/chronosync/     io · features · cache · coarse · fine · drift ·
                    overlap · global_alignment · validation · export ·
                    mp4sync · pipeline · cli
synthetic/          可复现合成数据（seed 化，15 个场景）
tests/              unit（单元）/ integration（集成，需 ffmpeg 的用例自动跳过）
benchmarks/         gcc · features · drift · solve（wall/CPU/峰值内存 + 精度）
handoff/            对外交付包（独立自测）
scripts/            演示素材生成
```
