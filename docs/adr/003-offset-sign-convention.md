# ADR-003：全局 Offset 符号约定

**状态：** Accepted（2025，Phase 1）
**影响面：** 所有模块的 docstring、类型名、JSON、CSV、测试、CLI、文档

## 决策

全项目唯一 offset 定义：

```text
d = t_target - t_reference
```

`d > 0` ⇔ 同一事件在 target 中出现得**更晚**。

## 动机

符号方向是最隐蔽的系统性 bug 来源（对齐结果整体反号、drift 斜率反号、
图求解发散）。集中定义一次，其余模块一律引用。

## 细节

* GCC 实现采用 `gcc[j] = IFFT(conj(R)·T)[j] ≈ Σ ref[n]·tgt[n+j]`，
  使 `delay_samples` 与定义一致（+N ⇔ target 滞后 N）。
  注意 `scipy.signal.correlate(a, v)` 方向相反，测试中已显式固化对照。
* `TimeMap`（ADR-005）用 `T_global = f(T_local)`，秒为单位；样本转换
  只在边界用规范采样率完成。
* 合成框架 `delay_samples(x, n)` 语义 `y[n+k] = x[k]` 与约定严格一致。
* 单元测试固化方向：`gcc(ref,tgt).delay ≈ -gcc(tgt,ref).delay`。

## 后果

* 任何新模块不得自行定义方向；冲突时以本 ADR 为准并修复冲突模块。
* 对外输出（CLI/JSON/CSV）直接复用模型字段，避免二次解释。
