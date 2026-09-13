# ADR-002：内部规范音频格式

**状态：** Accepted（2025，Phase 1）
**影响面：** io/、fine/、features/ 及一切核心 DSP

## 决策

进入核心 DSP 前统一为：

```text
sample rate = 48000 Hz
dtype       = float32
channels    = mono（分析在质量加权 downmix 上进行，左/右声道数组保留）
```

## 动机

统一的内部格式让所有下游模块（GCC、特征、drift）免除对输入采样率/位深
/声道数的分支处理；48 kHz 是现场录音设备的常见时钟，整数到浮点的转换
放在解码边界只做一次。

## 细节与约束

1. **重采样只允许高质量 sinc/polyphase**：默认 SoXR（`soxr` 包，
   quality="HQ"）；未安装时 fallback `scipy.signal.resample_poly` 并发出
   警告（质量低于 SoXR）。
   **`numpy.interp` 被明令禁止**作为音频重采样方案（线性插值，非带限）。
2. **Stereo 处理**：保留 `left` / `right` / `mono_mix`；默认用
   `mono_mix`。声道权重 = `max(1 - clip_fraction, 1e-3)²`：持续削波的
   声道**降权而不删除**（clip 判定：|x| ≥ 0.999 的样本占比）。
3. **长文件**：短文件整段进 RAM（`read_canonical`）；长文件流式
   （`iter_chunks`）。已知限制：分块重采样的边缘瞬态由 Phase 4 drift 层
   缝合，Phase 1 文档如实标注。
4. 输入格式覆盖（Phase 1 已支持）：WAV/BWF/RF64/FLAC 等（libsndfile），
   44.1/48/其他采样率，16/24 bit int 与 32 bit float，mono/stereo/多声道。
5. `DecodedAudio` 始终携带 `source_sample_rate`、每声道 `clip_fraction`
   与解码警告，供上层做质量决策。

## 后果

* 所有以"样本"为单位的 API 都指 48 kHz 规范样本（见 ADR-003）。
* 换 96 kHz 或 float64 内部格式属于架构级变更，需新 ADR 并重跑全部
  benchmark。
