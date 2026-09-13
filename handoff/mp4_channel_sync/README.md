# mp4_channel_sync — 无线麦克风通道延迟同步算法包

> 面向 1KeyTranscoder（或任何需要处理多流 MP4 的宿主程序）的**纯算法交付包**：
> 测量无线麦通道（CH1/CH2）相对有线通道（CH3/CH4）的固定微延迟并逐样本修正。
> **依赖仅 numpy + scipy**，不含 ffmpeg / 文件 I/O —— 容器解复用与重封装由宿主程序
> 负责，本包只吃 float32 mono 数组、只吐数组与结构化测量结果。

---

## 目录

1. [背景与实测数据](#1-背景与实测数据)
2. [交付内容](#2-交付内容)
3. [依赖与许可证](#3-依赖与许可证)
4. [算法原理](#4-算法原理)
5. [API 完整参考](#5-api-完整参考)
6. [集成指南（宿主程序侧）](#6-集成指南宿主程序侧)
7. [测试与验收标准](#7-测试与验收标准)
8. [边界情况与失败处理](#8-边界情况与失败处理)
9. [已知限制](#9-已知限制)
10. [常见问题](#10-常见问题)

---

## 1. 背景与实测数据

### 1.1 问题

多机位/多麦克风录制中，无线麦克风（CH1/CH2）经数字无线链路传输，相比有线
通道（CH3/CH4）存在**持续微延迟**（毫秒级），导致后期对轨时人声与画面/环境声
错位。

### 1.2 实测事实（真实素材：20260903_C1159 … C1177，19 片 4K HEVC + 4×mono PCM24 MP4）

| # | 事实 | 实测值 | 含义 |
|---|------|--------|------|
| 1 | **片内延迟恒定** | drift 判定 `constant_offset`，α ≈ ±1.5 ppm 噪声级 | 同容器 = 同一时钟，无线延迟是纯固定 latency，**不存在流间漂移** |
| 2 | **跨文件不恒定** | CH1 延迟 19.72–29.46 ms（5 片抽查），全 19 片 19.7–27.3 ms | 无线系统每次同步的 latency 不同 → **必须逐文件测量**，不能用一个常数套全部文件 |
| 3 | 有线对互相对齐 | CH3 vs CH4 = 0.004 ms | 有线通道可直接作参考 |
| 4 | 两个无线通道各自独立 | CH1 与 CH2 相差约 1.9 ms | 每通道独立测量、独立修正 |
| 5 | 测量精度 | 整数延迟实测误差 0.000 样本；分数延迟 ±0.15 样本内 | 48 kHz 下 ±0.1 样本 ≈ ±2 µs，远超实际需求 |

**结论**：每个文件执行一次"测量 → 修正 → 复检"，全自动，无需人工。

---

## 2. 交付内容

```
mp4_channel_sync/
├── mp4_channel_sync.py   算法模块（唯一需要导入的文件，约 380 行）
├── test_mp4_channel_sync.py   独立自测（python test_mp4_channel_sync.py，16 项断言）
└── README.md             本文档
```

使用方式：把 `mp4_channel_sync.py` 放进宿主项目任意可导入位置：

```python
from mp4_channel_sync import measure_channels, fix_channels, verify_channels
```

---

## 3. 依赖与许可证

| 项 | 说明 |
|---|---|
| 运行依赖 | `numpy`、`scipy>=1.9`（`scipy.fft` / `scipy.signal`）。无其它依赖 |
| Python | ≥ 3.9（类型注解用 `from __future__ import annotations`） |
| 许可证 | **MIT**。与宿主项目 LGPL-3.0-or-later **兼容**（MIT 代码可并入 LGPL 项目，保留版权声明即可） |
| 运行时 | 纯 CPU；120 s 素材测量 < 1 s，修正 < 0.1 s |

---

## 4. 算法原理

### 4.1 测量：GCC-PHAT（广义互相关-相位变换）

对参考通道 `r` 与目标通道 `t`：

```text
nfft = next_fast_len(len(r) + len(t) - 1)          # 零填充 → 线性相关（非循环）
R = rfft(r, nfft);  T = rfft(t, nfft)              # 实 FFT，内存减半
G[k] = conj(R[k])·T[k] / (|R[k]|·|T[k]| + ε)        # PHAT 白化：只保留相位
gcc = irfft(G, nfft)                                # gcc[j] ≈ Σ r[n]·t[n+j]
delay = argmax(gcc)  →  抛物线亚样本插值
```

要点（全部在实现中）：

| 机制 | 说明 |
|---|---|
| **正则化白化** | `ε = 1e-3·max|G| + 1e-12`。纯绝对下限会把窄带信号的频谱泄漏白化成噪声；相对下限让宽带信号峰高只损失约 1% |
| **输入归一** | 去均值 + 单位 RMS：增益差/电平差不影响测量（PHAT 本身增益不变） |
| **亚样本** | 峰点三邻居抛物线：`delta = 0.5(y₋−y₊)/(y₋−2y₀+y₊)`，裁剪到 ±0.5 样本 |
| **反相感知** | 反相对的相关峰为**负值**。负峰幅度 > 正峰×1.2 时自动翻转相关面继续分析，返回 `polarity=-1`（延迟照常测出，反相由宿主另行处理或忽略） |
| **峰值策略** | 绝不"全局最大=答案"：候选峰（距离≥2、严格双侧极大、-inf 补边检测边界峰）→ 主峰/次峰（间距≥8 样本）→ 置信度 = 0.3·峰高 + 0.5·峰比 + 0.2·突出度 |

### 4.2 恒定判定（片内 latency vs 真实漂移）

测量不只看一个数：全长 GCC 得主延迟 `d0` 后，在素材 **1/4、1/2、3/4** 处各取
16 s 窗口复测局部偏移（搜索范围 d0 ± 1 s）：

```text
constant = (窗口偏移极差 ≤ 2 样本) 且 (线性拟合斜率 |ppm| < 20)
drift_ppm = 斜率 × 1e6
```

同一容器内的流共享时钟，实测恒为 constant。若出现非恒定（极差大或 ppm 大），
`DelayResult.constant=False` 并带警告——宿主应记录该文件为异常而非强行用
单一延迟修正。

### 4.3 修正：带限分数移位

对每个通道执行**整体前移**（delay > 0 的通道提前 delay 样本）：

```text
y[n] ≈ x[n + delay]         # 等价于 y[n] ≈ x[n − (−delay)]
```

实现 = 窗 sinc 分数延迟 FIR（**65 taps，奇数**——偶数核 `np.convolve(mode='same')`
会引入 taps/2 样本的系统偏移，实测坑）+ 整数部分切片移位：

* 分数部分精度 ≈ 窗 sinc 设计精度（测试实测修正后残差 0.000 ms）；
* 边界（首/尾 taps/2 样本）近似，中间精确；
* 所有通道裁剪到共同对齐长度；电平不做任何改动；
* 无法测量的通道（`delay=nan`）**原样保留**（绝不静音或乱移）。

### 4.4 复检（验证闭环）

修正后对每个通道重新执行 GCC（搜索范围 ±0.1 s）：

```text
|residual_ms| < 0.05  → 通过
```

这是把"测对了"与"改对了"分开验证的唯一可靠方式。

---

## 5. API 完整参考

### 5.1 `DelayResult`（dataclass）

| 字段 | 类型 | 说明 |
|---|---|---|
| `channel` | int | 通道序号（输入列表下标，0=CH1 …） |
| `delay_samples` | float | **delay = t_channel − t_reference**；正=该通道到达更晚；nan=无法测量 |
| `delay_ms` | float | 同上，毫秒（= samples×1000/48000） |
| `confidence` | float | [0,1]；< 0.3 建议按失败处理 |
| `peak` | float | 白化相关峰高（≈1 为干净匹配） |
| `polarity` | int | +1 正常 / −1 反相 |
| `drift_ppm` | float | 三窗口线性拟合斜率；≈0 即纯固定延迟 |
| `constant` | bool | 片内恒定（见 4.2） |
| `warnings` | list[str] | 人类可读警告（反相/非恒定/窗口失败等） |

### 5.2 `measure_channels(channels, sample_rate=48000, reference_index=2, max_lag_seconds=1.0, min_confidence=0.3) -> list[DelayResult]`

逐通道测量相对参考通道的延迟。

* `channels`：`list[np.ndarray]`，每个为 mono float32/float64，**同采样率**；
* `reference_index`：参考通道下标（默认 2 = CH3）。参考通道自身返回 0、conf=1；
* 返回列表与输入等长，`result.channel = 下标`。

```python
results = measure_channels([ch1, ch2, ch3, ch4], reference_index=2)
for r in results:
    print(f"CH{r.channel+1}: {r.delay_ms:+.4f} ms  conf={r.confidence:.2f}")
```

### 5.3 `measure_delay(reference, target, sample_rate=48000, n_windows=3, max_lag_seconds=1.0, min_confidence=0.3) -> DelayResult`

单对信号测量（内部函数，供需要单独测两通道时使用）。`channel` 字段此时为 0。

### 5.4 `fix_channels(channels, delays_samples, sample_rate=48000) -> np.ndarray`

按测量结果修正。返回 float32 `(n_channels, n_aligned)`，`n_aligned` 为各通道
前移后的共同长度。`delays_samples` 为与 `channels` 等长的延迟样本数列表
（直接用 `[r.delay_samples for r in results]`）。nan 通道原样保留。

```python
fixed = fix_channels([ch1, ch2, ch3, ch4], [r.delay_samples for r in results])
```

### 5.5 `verify_channels(channels, sample_rate=48000, reference_index=2, window_seconds=8.0) -> list[float]`

复检：返回各通道相对参考的残差（毫秒）。参考通道为 0.0；`|residual| < 0.05 ms`
视为通过；nan = 该通道复检失败。

### 5.6 `gcc_phat(reference, target, sample_rate=48000, search_min=None, search_max=None, eps_rel=1e-3, eps_abs=1e-12) -> _GccResult`

底层 GCC-PHAT（内部类型 `_GccResult`：`delay_samples/peak/second_peak/prominence/
confidence/polarity/success`）。需要定制搜索区间或直接拿峰值信息时使用。

---

## 6. 集成指南（宿主程序侧）

### 6.1 数据获取：解码到 float32 mono @ 48 kHz

本包不碰容器。宿主侧（1KeyTranscoder 已有 ffmpeg 9.0.1）用管线解码即可：

```powershell
# 逐流解码为 float32 原始 PCM（无重封装，最快路径）
# ⚠️ -ignore_editlist 1 必须加，原因见下方说明
ffmpeg -v error -ignore_editlist 1 -i in.MP4 -map 0:a:0 -f f32le -ac 1 -ar 48000 pipe:1 > ch0.f32
ffmpeg -v error -ignore_editlist 1 -i in.MP4 -map 0:a:1 -f f32le -ac 1 -ar 48000 pipe:1 > ch1.f32
```

> ⚠️ **务必忽略 edit list（`-ignore_editlist 1`）——这不是可选项。**
> MP4 的 edit list（部分 muxer 用来把音频对齐到视频帧）在**部分 ffmpeg
> 版本上会裁掉流的头部样本**：实测同一份 4 流 MP4，Linux ffmpeg 6 解码时
> ch0 被裁掉 305 样本（测得延迟从 1223 变成 918），Windows ffmpeg 8 不裁。
> 只有取原始样本流，测量结果才等于内容真值且跨平台稳定；容器 `start_time`
> 仅作信息记录，**不要**叠加到延迟上（会双重计数）。若宿主因故无法忽略
> edit list，则必须自行把 `(start_stream − start_reference)` 补偿进测量值。

```python
import numpy as np
def read_f32(path_or_pipe, frames):          # 宿主自己的读取方式
    return np.fromfile(path_or_pipe, dtype=np.float32)[:frames]
```

要求：

* **48 kHz**：源即 48 kHz（实测素材 pcm_s24be@48000），无需重采样；若宿主内部
  使用其它采样率，请先用自己的工具链重采样到 48 kHz（或把 `sample_rate`
  参数传成实际值——本包所有函数均接受任意采样率，毫秒换算与窗长按此缩放）；
* **float32/float64**：其它位深先转浮点（÷2^15 / ÷2^23，或直接用 ffmpeg
  `f32le` 输出，零转换成本）；
* **测量窗口**：把前 60–120 s 喂给测量即可（默认窗 16 s，素材足够长时
  结果与全长一致）；极短素材（< 8 s）见 §8。

### 6.2 推荐调用流程（逐文件）

```python
from mp4_channel_sync import measure_channels, fix_channels, verify_channels

def sync_one_file(channels: list[np.ndarray]) -> dict:
    """channels = [ch1, ch2, ch3, ch4]，均为 float32 mono @48kHz"""
    results = measure_channels(channels, reference_index=2)

    # 质量门：任何无线通道无法测量时，该文件标记为需要人工/重测
    failed = [r for r in results if r.channel not in (2,) and (
        r.delay_samples != r.delay_samples or r.confidence < 0.3)]  # nan 检查
    if failed:
        return {"status": "measure_failed", "channels": results}

    fixed = fix_channels(channels, [r.delay_samples for r in results])
    residuals = verify_channels(fixed, reference_index=2)
    ok = all(abs(v) < 0.05 for v in residuals if v == v)  # nan 跳过

    return {
        "status": "ok" if ok else "verify_failed",
        "delays_ms": [r.delay_ms for r in results],
        "fixed": fixed,          # 回写/重封装用
        "residuals_ms": residuals,
    }
```

### 6.3 回写

修正后的 `fixed`（4×n float32）按宿主现有管线回写：转回 PCM24 → 各通道单独
成流 → 与原视频一起重封装（1KeyTranscoder 的 MP4Box/GPAC 路径），
**保持 4×mono 流布局**（部分下游工具按流号取通道）。

### 6.4 与既有转码管线的位置关系

建议把"测量+修正"放在**解复用之后、编码之前**：本包只产生数组层面的时间轴
修正，不改变任何编码器/元数据行为；Sony/DJI 元数据保留管线不受影响
（本包不接触容器与元数据）。

### 6.5 报告字段（给下游/日志用）

```json
{
  "file": "20260903_C1171.MP4",
  "reference_stream": 2,
  "channels": [
    {"stream": 0, "delay_ms": 25.473, "delay_samples": 1222.7, "confidence": 0.80, "drift": "constant_offset"},
    {"stream": 1, "delay_ms": 27.341, "delay_samples": 1312.3, "confidence": 0.53, "drift": "constant_offset"},
    {"stream": 2, "delay_ms": 0.0, "confidence": 1.0, "drift": "reference"},
    {"stream": 3, "delay_ms": -0.004, "delay_samples": -0.2, "confidence": 0.85, "drift": "constant_offset"}
  ]
}
```

---

## 7. 测试与验收标准

```bash
python test_mp4_channel_sync.py     # 16 项断言，秒级，零外部依赖，退出码 0 = 全过
```

| 组 | 覆盖 | 验收标准 |
|---|---|---|
| 整数延迟测量 | 1223 / 1350 样本 | 误差 < 0.5 样本（实测 0.000） |
| 分数延迟测量 | 1223.4 样本 | 误差 < 0.15 样本（实测 0.013） |
| 修正+复检 | 两无线通道修正后复检 | 残差 < 0.05 ms（实测 0.000） |
| 反相 | 反相对 | polarity=−1 且延迟仍正确 |
| 静音/失败 | 静音通道 | delay=nan 且修正时原样保留 |
| 方向约定 | 晚到通道 | delay > 0 |

另建议宿主侧在真实素材上做一次人工抽检（对修正后的文件听/看 3 个时间点），
因为合成测试不能覆盖真实无线链路的全部特性。

---

## 8. 边界情况与失败处理

| 情况 | 行为 | 宿主建议 |
|---|---|---|
| 通道为静音/无有效内容 | `delay=nan`，warnings 说明 | 标记文件重测/人工；修正时该通道原样保留 |
| 素材极短（< 8 s） | 跳过三窗口恒定判定，仍返回全长 GCC 结果 + 警告 | 短素材置信度偏低属正常，人工确认 |
| 反相 | 延迟正常测出 + `polarity=-1` + 警告 | 记录；如宿主有极性处理则应用，否则仅记录 |
| 窗口偏移不一致（极差>2 样本或 \|ppm\|≥20） | `constant=False` + 警告 | 该文件疑似异常（非纯固定延迟），不要强行单一延迟修正 |
| 置信度 < 0.3 | 仍返回结果但 confidence 低 | 按失败处理（见 6.2 的质量门） |
| 采样率非 48 kHz | 传 `sample_rate` 参数即可（毫秒换算/窗长按此缩放） | 建议统一 48 kHz 以复用全部默认参数 |
| **容器 edit list 裁头**（MP4 常见） | 解码未加 `-ignore_editlist 1` 时，部分 ffmpeg 版本会裁掉流头部样本 → 延迟系统性偏差（实测 305 样本） | 解码时强制 `-ignore_editlist 1`；否则自行补偿 `start_time` 差值 |
| 有损编码流（AAC/MP3…） | 编码器 priming 会引入固定偏移 | 本包面向 PCM 多流素材；有损素材需先确认 priming 已被容器正确裁除 |

---

## 9. 已知限制

1. **只处理恒定延迟**：本包假设片内延迟恒定（同容器同时钟成立）。跨段变速/
   真实时钟漂移不在范围内（那是 ChronoSync 主项目 drift 估计器的职责）。
2. **不处理跨文件复用常数**：实测延迟跨文件变化（§1.2），每次运行请重新测量。
3. **修正丢弃尾部**：前移 delay 后，各通道裁剪到共同长度（尾部 ≤ delay 的
   内容被丢弃）；如需保留全长可在宿主侧补零尾部。
4. **边界近似**：窗 sinc 的首/尾 32 样本为近似值（不影响对轨）。
5. **多通道 > 4**：`measure_channels` 支持任意通道数，参考通道可任意指定。

---

## 10. 常见问题

**Q：为什么用 GCC-PHAT 而不是普通互相关？**
普通互相关对频谱形状敏感（能量大的频段主导），PHAT 白化后每个频段等权投票，
对语音/音乐/噪声都更稳，峰更尖（亚样本插值误差更小）。

**Q：测量需要多长素材？**
60–120 s 足够（实测 50 s 与全长结果一致）。> 5 分钟素材也只需前 120 s。

**Q：能直接给出"毫秒"给剪辑软件手动对轨吗？**
可以——`delay_ms` 即该通道需要在时间线上**前移**的毫秒数（正=前移）。
48 kHz 下 1 样本 = 0.020833 ms，报告保留 4 位小数。

**Q：与 ChronoSync 的关系？**
本包是 ChronoSync（F:\ChronoSync）GCC-PHAT 与修正算法的**精简移植**
（MIT）。ChronoSync 侧另有完整管线（`chronosync.mp4sync` + CLI
`chronosync mp4-sync`，含 ffmpeg 抽取/重封装/批量报告）可作交叉验证：
两者对同一素材的测量值一致（实测 1223.000 vs 1223.000 样本）。
