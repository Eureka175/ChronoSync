# Offset 符号约定（项目级 API 规范）

**ChronoSync 全项目唯一的 offset 定义：**

```text
d = t_target - t_reference
```

**语义：**

* `d > 0`：同一事件在 `target` 中出现得**更晚**（target 滞后）。
* `d < 0`：同一事件在 `target` 中出现得**更早**（target 提前）。
* `d = 0`：两者对齐。

**单位：** 内部统一使用**规范采样率 48 kHz 下的样本数**（`samples`），
需要物理时间时除以 48000 得到秒（`seconds`）。所有 API 同时给出
`*_samples` 与 `*_seconds` 字段时，二者必须满足
`seconds = samples / 48000`。

## 与 GCC-PHAT 数学定义的关系

本项目的 GCC 实现计算（详见 ADR-004 / docs/algorithms.md）：

```text
gcc[j] = IFFT( conj(FFT(reference)) · FFT(target) )[j] ≈ Σ_n ref[n] · tgt[n + j]
```

若 `tgt[n] = ref[n - N]`（target 滞后 N 个样本），`gcc` 在 `j = +N` 处取峰值，
因此 `delay_samples = +N`，与上述约定一致。

注意：`scipy.signal.correlate(a, v)` 的内部方向与本项目相反——
其峰值出现在 `-d` 处（测试 `test_matches_plain_cross_correlation_on_broadband_signal`
明确验证了这一点）。

## 各层含义

| 层 | 对象 | 字段 | 方向 |
| --- | --- | --- | --- |
| 粗匹配 | `MatchResult` | `offset_samples` | `t_target - t_reference` |
| 精对齐 | `GCCResult` | `delay_samples` | `t_target - t_reference` |
| Drift | `DriftModel` | `d(t) = alpha_ppm·1e-6·t + beta_samples` | `t_target - t_reference` |
| 图 | `AlignmentEdge` | `offset_samples` | `t_target - t_source` |
| 全局 | `TrackAlignment` | `offset_samples` | 相对图参考轨（参考轨恒为 0） |
| 时间映射 | `TimeMap` | `T_global = f(T_local)` | 本地 → 全局 |

## 符号一致性的强制手段

* 所有模型 docstring 均引用 ADR-003；
* 所有 JSON / CSV / CLI 输出直接复用模型字段，不另行定义方向；
* 测试显式断言方向（如 `test_sign_antisymmetry`：
  `gcc(ref, tgt).delay ≈ -gcc(tgt, ref).delay`）；
* 合成数据框架的 `delay_samples(x, n)` 语义为
  `y[n+k] = x[k]`（n > 0 时内容更晚出现），与约定严格一致。

**任何新模块都不得自行定义 offset 方向；如发现定义冲突，以本文档为准并
修复冲突模块。**
