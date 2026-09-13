# 架构（Phase 1）

## 核心理念

ChronoSync 不是"两条 WAV 找 offset 的工具"。系统的核心对象是
**TimeMap**：每条录音是从设备本地时间到统一参考时间的映射

```text
T_global = f_i(T_i)
```

固定 offset、clock drift、局部断点都被统一抽象为 TimeMap
（identity / constant_offset / linear / piecewise_linear）。
业务代码依赖 `TimeMap` 接口，不直接操作 offset / alpha / beta。

## 逻辑分层

```text
Layer 0  Input / Decode / Canonicalization     io/          ✅ Phase 1
Layer 1  Feature Extraction / Cache            features/    ✅ Phase 3
                                                 cache/       ✅ Phase 3 (ADR-006)
Layer 2  Coarse Matching                       coarse/      ✅ Phase 3 (ADR-008)
Layer 3  Fine Alignment (GCC-PHAT)             fine/        ✅ Phase 1 (+反相感知, ADR-012)
Layer 4  Drift / TimeMap Estimation            drift/       ✅ Phase 4 (ADR-009)
Layer 5  Multi-track Global Optimization       global_alignment/ ✅ Phase 6 (ADR-011)
         Overlap / Segmentation                overlap/     ✅ Phase 5
Layer 6  Validation / Confidence / Anomaly     validation/  ✅ Phase 7 (ADR-012)
Layer 7  Export                                export/      ✅ SESX + JSON/CSV (ADR-010); RPP ⏳
```

逻辑层是概念上的；代码以模块边界为准，不为凑"七层"硬拆文件。

## 数据流（已实现部分）

```text
WAV/BWF/RF64/FLAC/...
        │  io.probe (metadata, 不解码)
        ▼
io.read_canonical ──► DecodedAudio          （float32 @ 48 kHz, 声道加权 mono_mix）
        │  长文件: io.iter_chunks 流式分块
        ▼
features/  envelope · spectral flux/transient · constellation fingerprint
        │  cache/  SQLite 索引 + .npy 数组（ADR-006）
        ▼
coarse/   metadata(prior) → fingerprint → envelope → transient 短路级联
        │  MatchResult (matched/offset/confidence/method/overlap/evidence)
        ▼
drift/    窗口 GCC（自适应收缩 30s→0.5s）→ 鲁棒回归 → 变点检测/分类
        │  DriftEstimate → TimeMap (constant/linear/piecewise)
        ▼
pipeline.py  batch_align：全对配对测量 → AlignmentGraph
        ▼
global_alignment/  WLS 求解（参考轨=0、连通分量独立、边残差、每轨置信度、IRLS）
        ▼
overlap/    TrackContent spans → 重叠 Segment（录音间隙 → 多段）
validation/ 残差 GCC · coherence · polarity · 可解释置信度聚合
        ▼
export/sesx.py 非破坏性多轨时间线（整数样本）
export/json.py + csv.py  对齐报告
drift/correct_track  可选渲染（SoXR 异步重采样到全局时间线）
```

## 包结构（src layout）

```text
src/chronosync/
├── models/       数据模型（唯一的数据交换契约）
│   ├── audio.py      AudioTrack / DecodedAudio / 规范格式常量
│   ├── match.py      MatchResult
│   ├── alignment.py  AlignmentEdge / AlignmentGraph / TrackAlignment
│   ├── drift.py      OffsetMeasurement / DriftModel
│   └── timemap.py    TimeMap 家族（核心抽象）
├── io/           Layer 0：probe / decoder / resampler / wav
├── features/     Layer 1：envelope / spectral / fingerprint（版本化）
├── cache/        Layer 1：SQLite 索引 + 文件型数组（ADR-006）
├── coarse/       Layer 2：级联（ADR-008）
├── fine/         Layer 3：gcc_phat（含反相感知）/ peak / subsample
├── drift/        Layer 4：windows / regression / estimator / timemap
├── global_alignment/  Layer 5：solver（WLS/IRLS，ADR-011）+ robust
├── overlap/      Layer 5：segments / detector（ADR 未设，见 algorithms §10）
├── validation/   Layer 6：residual / coherence / polarity / confidence（ADR-012）
├── export/       SESX（ADR-010）+ JSON / CSV
├── pipeline.py   多轨编排（align_pair / batch_align）
└── cli/          命令行入口（info/gcc/align/batch/test-gcc/benchmark）

synthetic/        可复现的合成数据框架（顶级包，seed 化）
benchmarks/       基准（gcc/features/drift/solve，wall/CPU/峰值内存 + 精度）
tests/            unit / integration
docs/             architecture / algorithms / offset_convention / research / adr
```

## 长文件与缓存设计（已实施，ADR-006）

* 短文件：整段载入 RAM（`read_canonical`）；
* 长文件：`iter_chunks` 流式 + SQLite 索引 + `.npy/.npz` 文件型特征缓存
  （大数组禁止进 SQLite BLOB；键含 path/size/mtime/可选 hash/算法版本/特征版本）。
* 单次全长 GCC 是 O(N log N) 且内存 ≈ 16 B/样本 × 多个 FFT 缓冲——
  分钟级以上的文件必须用窗口化 GCC（drift 估计器模式），
  benchmark 已按此设计（见 benchmarks/benchmark_gcc.py）。

## 依赖策略

```text
Python 3.12+            （本项目在 3.14 上开发验证）
numpy / scipy           核心（scipy.fft, scipy.signal）
soundfile / libsndfile  解码（WAV/BWF/RF64/FLAC，分块读取）
soxr                    高质量重采样（fallback: scipy.signal.resample_poly + 警告）
pytest                  测试
psutil                  benchmark 峰值内存
```

* 禁止 `np.interp` 作为音频重采样方案（ADR-002）；
* Numba / pybind11 / C++ 只在 profiling 证明必要后引入（ADR-001）。

## 下一步（Phase 8+）

1. Phase 8：真实录音 benchmark（现场多机位素材端到端评测：精度/时长/内存）；
2. Phase 9：Reaper RPP 导出（承载 SESX 无法表达的变速映射）+ 未直接测量对之间的 TimeMap 复合；
3. Phase 10：GUI。
