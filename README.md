# ChronoSync

**v0.1.0-beta** · MIT · Python 3.12+

> 面向独立录音设备、多机位现场录音和长时间录音的多轨音频**时间基准估计**、
> **自动对齐**与**时钟漂移校正**系统。

ChronoSync 不是"又一个自动同步 WAV 的工具"。它的核心对象不是 offset，
而是 **TimeMap**：

```text
T_global = f_i(T_i)
```

每条录音都是从设备本地时间到统一参考时间的映射：最简单是
`T = a·t + b`（a = clock scale/drift，b = 固定偏移），复杂情况允许
piecewise-linear（分段漂移、局部断点）。固定 offset、clock drift、
CLOCK_DISCONTINUITY 全部统一为一个抽象。

```text
多个独立录音设备 → 识别共同内容/重叠 → 粗定位 → 局部高精度对齐
→ 估计 clock drift → 每条轨道的时间映射 → 多轨全局约束求解
→ 异常/断点/不可靠测量检测 → 验证 → 统一时间轴 → DAW 工程导出
```

## 状态：Phase 5-7（当前）

已完成：Phase 1（骨架/GCC/CLI）+ Phase 3（特征/缓存/粗匹配级联）+
Phase 4（drift 估计/TimeMap/校正）+ **Adobe Audition SESX 导出** +
**Phase 5（Overlap/Segment）+ Phase 6（多轨图求解）+ Phase 7（验证/置信度）**
+ JSON/CSV 导出 + CLI `batch` 多轨批处理。

| 组件 | 状态 |
| --- | --- |
| 技术调研（AudioAlign/Aurio/audalign/alignaudio/WhisperSync/音频栈/SESX） | ✅ `docs/research/` |
| 核心数据模型（AudioTrack/MatchResult/GCCResult/DriftModel/TimeMap/AlignmentEdge/AlignmentGraph/TrackAlignment） | ✅ `src/chronosync/models/` |
| I/O（probe / 解码 / SoXR 重采样 / 流式分块） | ✅ `src/chronosync/io/` |
| Synthetic Framework（seed 化） | ✅ `synthetic/` |
| GCC-PHAT（正则化白化、峰值策略、prior、亚样本、**反相感知**、可解释 confidence） | ✅ `src/chronosync/fine/` |
| 特征层 + 特征缓存（ADR-006） | ✅ `features/` + `cache/` |
| 粗匹配级联（ADR-008） | ✅ `src/chronosync/coarse/` |
| Drift 估计 + SoXR 校正（ADR-009） | ✅ `src/chronosync/drift/` |
| Overlap / Segment 检测（录音间隙 → 多段） | ✅ `src/chronosync/overlap/` |
| 多轨图求解（WLS/IRLS、连通分量、残差、每轨置信度，ADR-011） | ✅ `src/chronosync/global_alignment/` |
| 验证层（残差 GCC/coherence/polarity/置信度聚合，ADR-012） | ✅ `src/chronosync/validation/` |
| 导出：SESX（ADR-010）+ JSON + CSV | ✅ `src/chronosync/export/` |
| 多轨编排（batch_align：全对配对→图求解→导出） | ✅ `src/chronosync/pipeline.py` |
| 单元/集成测试（**191 项**） | ✅ `tests/` |
| Benchmark（gcc/features/drift/solve） | ✅ `benchmarks/` |
| CLI（info / gcc / align / **batch** / test-gcc / benchmark / --json） | ✅ `chronosync` |
| Reaper RPP 导出 / 真实录音基准 | ⏳ Phase 8-9 |

## 安装

```bash
pip install -e ".[io,dev]"     # Python 3.12+
```

依赖：numpy、scipy（必需）；soundfile + soxr（io 可选但推荐）；
pytest、psutil（dev/benchmark）。

## 快速开始

```bash
# 生成验收音频对（target = reference 延迟 12345 样本）
python scripts/generate_demo_pair.py demo

# 元数据 / 局部 GCC
chronosync info demo/reference.wav
chronosync gcc demo/reference.wav demo/target.wav

# 两轨完整流水线：粗匹配 → drift 估计 → TimeMap → SESX（可选）
chronosync align demo/reference.wav demo/target.wav --json
chronosync align demo/reference.wav demo/target.wav --sesx session.sesx

# 多轨批处理：全对配对 → 图求解 → JSON/CSV/SESX
chronosync batch a.wav b.wav c.wav --json --csv align.csv --sesx session.sesx

# 自检与基准
chronosync test-gcc
chronosync benchmark --suite all        # gcc / features / drift / solve
```

多轨输出示例：

```text
Status:     success
Reference:  a.wav
  a.wav                 offset        0.0 samples  conf 1.000  map identity
  b.wav                 offset     2003.4 samples  conf 0.961  map linear
  c.wav                 offset    -2998.1 samples  conf 0.940  map constant_offset
```

## 项目约定（必须遵守）

* **Offset 方向（ADR-003）**：`d = t_target - t_reference`；`d > 0` ⇔
  target 中事件更晚。所有 docstring/JSON/CSV/测试/CLI 一致。
* **规范音频格式（ADR-002）**：48 kHz / float32 / 质量加权 mono_mix
  （left/right 保留）；重采样只用 SoXR（禁止 `np.interp`）。
* **GCC 峰策略（ADR-004）**：绝不"全局最大 = 答案"；置信度来自可解释
  证据（峰高/峰比/峰 prominence），阈值全部可配置。
* **TimeMap（ADR-005）**：业务代码依赖映射接口，不直接操作 offset/alpha。
* 测试原则：先定义数学行为 → 写测试 → 实现 → benchmark；禁止改测试掩盖问题。

## 文档

| 文档 | 内容 |
| --- | --- |
| `docs/architecture.md` | 分层架构、数据流、包结构、依赖策略 |
| `docs/algorithms.md` | GCC-PHAT、峰值策略、置信度、粗匹配级联、drift 估计、SESX、Overlap、图求解、验证 |
| `docs/offset_convention.md` | 全项目 offset 符号规范 |
| `docs/research/existing_projects.md` | 现有项目调研 + 技术差异矩阵 + 复用决策 |
| `docs/research/notes/sesx_format.md` | SESX 格式逆向调研（时间单位=整数样本等） |
| `docs/adr/` | 001-007 基础决策 + 008-coarse / 009-drift / 010-sesx / 011-graph-solver / 012-validation |

## Roadmap

```text
Phase 0  现有项目调研                        ✅
Phase 1  骨架 + 模型 + Synthetic + GCC + 测试 ✅
Phase 2  GCC-PHAT 精化 + benchmark           ✅（并入 Phase 1）
Phase 3  特征提取 + 缓存 + 粗匹配级联        ✅
Phase 4  Drift 估计 + SoXR 校正              ✅
Phase 5  Overlap / Segment 检测              ✅
Phase 6  多轨图求解（WLS/IRLS + 连通性 + 残差）✅
Phase 7  验证 / 置信度（残差/coherence/polarity）✅
SESX 导出（Adobe Audition，非破坏性时间线）  ✅（ADR-010）
JSON/CSV 导出 + 多轨 batch CLI               ✅
Phase 8  真实录音 benchmark
Phase 9  Reaper RPP 导出 + TimeMap 复合
Phase 10 GUI
```

## License

MIT（见 `LICENSE`）。
