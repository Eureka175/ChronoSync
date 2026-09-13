# ADR-001：Python-first 技术路线

**状态：** Accepted（2025，Phase 1）
**影响面：** 全项目语言与性能策略

## 决策

第一阶段（及默认路线）只写 Python：

```text
Python 3.12+ + NumPy + SciPy + 成熟 native 音频库
```

* FFT：`scipy.fft`（rfft/irfft，`next_fast_len`）
* 信号处理：`scipy.signal`（find_peaks / peak_prominences / lfilter）
* 解码：`soundfile`（libsndfile：WAV/BWF/RF64/FLAC，分块读取）
* 重采样：`soxr`（SoXR polyphase）；fallback `scipy.signal.resample_poly` + 警告
* 缓存：SQLite + `.npy/.npz` 文件型数组

## 动机

音频对齐系统的瓶颈在 DSP 内核（FFT/互相关），NumPy/SciPy 已把这些内核
委托给成熟 C/Fortran 实现；纯 Python 胶水层的开销在 Phase 1 实测中不构成
瓶颈（60 s 全长 GCC 4.5 s，其中 FFT 主导）。

## 后果

* **禁止**提前引入 Numba / pybind11 / C++；只有当 profiling 证明纯 Python
  胶水层成为瓶颈时才考虑（优先 Numba，其次 C 扩展）。
* 性能结论必须以 benchmark 为准（wall/CPU/峰值内存 + 精度），见
  `benchmarks/benchmark_gcc.py`。
* 已有 benchmark 数据点：10 s 全长 GCC 0.58 s / 223 MB；60 s 4.5 s / 867 MB
  （本机，2025-07 初测）。单次全长 GCC 内存 ≈ 16 B/样本 × 多缓冲，
  分钟级以上必须窗口化（Phase 4 drift 模式）。
