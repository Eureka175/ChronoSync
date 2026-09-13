"""mp4_channel_sync 独立测试 — 运行: python test_mp4_channel_sync.py

纯 numpy/scipy，无 pytest 依赖，确定性（固定 seed）。退出码 0 = 全过。
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

import numpy as np
from scipy import signal

sys.path.insert(0, str(Path(__file__).resolve().parent))

from mp4_channel_sync import (  # noqa: E402
    fix_channels,
    measure_channels,
    measure_delay,
    verify_channels,
)

SR = 48_000
FAILURES: list[str] = []


def check(name: str, condition: bool, detail: str = "") -> None:
    status = "PASS" if condition else "FAIL"
    print(f"[{status}] {name}" + (f"  ({detail})" if detail else ""))
    if not condition:
        FAILURES.append(name)


# ------------------------------------------------------- 合成测试素材


def _speech_like(n: int, seed: int = 0) -> np.ndarray:
    """自带伪语音生成器：带限噪声 × 随机音节包络（确定性）。"""
    rng = np.random.default_rng(seed)
    sos = signal.butter(4, [100.0, 4000.0], btype="band", fs=SR, output="sos")
    carrier = signal.sosfilt(sos, rng.standard_normal(n))
    carrier /= np.max(np.abs(carrier)) + 1e-12
    envelope = np.zeros(n)
    t = 0.0
    while t < n / SR:
        start = int(t * SR)
        dur = rng.uniform(0.08, 0.4)
        m = int(dur * SR)
        if start < n and m > 0:
            k = np.arange(min(m, n - start))
            env = rng.uniform(0.4, 1.0) * np.exp(-k / (dur * SR / 3.0))
            envelope[start : start + len(k)] += env
        t += rng.uniform(0.15, 0.6) + dur
    out = carrier * np.minimum(envelope, 1.0)
    return (out / (np.max(np.abs(out)) + 1e-12)).astype(np.float32)


def _delay_int(x: np.ndarray, n: int) -> np.ndarray:
    """整数延迟（内容后移 n 样本，头部补零）——与包内实现无关。"""
    y = np.zeros_like(x)
    if n >= 0:
        if n < x.size:
            y[n:] = x[: x.size - n]
    else:
        m = -n
        if m < x.size:
            y[: x.size - m] = x[m:]
    return y


def _delay_frac(x: np.ndarray, delay: float, taps: int = 97) -> np.ndarray:
    """分数延迟（独立实现：97 taps 窗 sinc + 整数移位）。"""
    i0 = int(np.floor(delay))
    frac = delay - i0
    m = np.arange(-(taps // 2), taps // 2 + 1)
    h = np.sinc(m - frac) * np.hanning(taps)
    h /= h.sum()
    y = np.convolve(x, h, mode="same")
    return _delay_int(y, i0)


# ---------------------------------------------------------------- 测试


def test_measure_integer_delays() -> None:
    base = _speech_like(15 * SR, seed=1)
    channels = [_delay_int(base, 1223), _delay_int(base, 1350), base, base]
    results = measure_channels(channels, reference_index=2)
    d = {r.channel: r.delay_samples for r in results}
    check("CH1 整数延迟 1223 样本", abs(d[0] - 1223.0) < 0.5, f"measured {d[0]:.2f}")
    check("CH2 整数延迟 1350 样本", abs(d[1] - 1350.0) < 0.5, f"measured {d[1]:.2f}")
    check("CH3 参考通道 = 0", d[2] == 0.0)
    check("CH4 有线通道 ≈ 0", abs(d[3]) < 0.5, f"measured {d[3]:.2f}")
    check("CH1 判定 constant（片内恒定）", results[0].constant)
    check("CH1 置信度 > 0.5", results[0].confidence > 0.5)


def test_measure_fractional_delay() -> None:
    base = _speech_like(10 * SR, seed=2)
    channels = [_delay_frac(base, 1223.4), base]
    r = measure_channels(channels, reference_index=1)[0]
    check("分数延迟 1223.4 样本（±0.15）", abs(r.delay_samples - 1223.4) < 0.15,
          f"measured {r.delay_samples:.3f}")


def test_fix_and_verify() -> None:
    base = _speech_like(15 * SR, seed=3)
    channels = [_delay_int(base, 1223), _delay_int(base, 1350), base, base]
    results = measure_channels(channels, reference_index=2)
    delays = [r.delay_samples for r in results]
    fixed = fix_channels(channels, delays)
    check("修正后长度一致", fixed.shape[0] == 4)
    residuals = verify_channels(fixed, reference_index=2)
    check("CH1 修正后残差 < 0.05 ms", abs(residuals[0]) < 0.05,
          f"{residuals[0]:.4f} ms")
    check("CH2 修正后残差 < 0.05 ms", abs(residuals[1]) < 0.05,
          f"{residuals[1]:.4f} ms")
    check("CH4 修正后残差 < 0.05 ms", abs(residuals[3]) < 0.05,
          f"{residuals[3]:.4f} ms")


def test_polarity_inversion_detected() -> None:
    base = _speech_like(10 * SR, seed=4)
    r = measure_delay(base, -_delay_int(base, 500))
    check("反相检测 polarity=-1", r.polarity == -1)
    check("反相仍测出正确延迟", abs(r.delay_samples - 500.0) < 0.5,
          f"measured {r.delay_samples:.2f}")


def test_silence_returns_nan_and_fix_keeps_channel() -> None:
    base = _speech_like(8 * SR, seed=5)
    silence = np.zeros_like(base)
    results = measure_channels([silence, base], reference_index=1)
    check("静音通道 delay = nan", math.isnan(results[0].delay_samples))
    fixed = fix_channels([silence, base], [results[0].delay_samples, 0.0])
    check("nan 延迟通道原样保留", np.array_equal(fixed[0], silence[: fixed.shape[1]]))


def test_direction_semantics() -> None:
    # delay > 0 表示到达更晚：晚到的通道测量值为正
    base = _speech_like(8 * SR, seed=6)
    r = measure_delay(base, _delay_int(base, 800))
    check("晚到通道 delay > 0（方向约定）", r.delay_samples > 790.0,
          f"measured {r.delay_samples:.2f}")


if __name__ == "__main__":
    for fn in (
        test_measure_integer_delays,
        test_measure_fractional_delay,
        test_fix_and_verify,
        test_polarity_inversion_detected,
        test_silence_returns_nan_and_fix_keeps_channel,
        test_direction_semantics,
    ):
        fn()
    print()
    if FAILURES:
        print(f"{len(FAILURES)} FAILED: {FAILURES}")
        sys.exit(1)
    print("ALL PASS")
