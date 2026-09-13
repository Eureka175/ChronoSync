# ADR-005：TimeMap 时间映射抽象

**状态：** Accepted（2025，Phase 1，模型先行）
**影响面：** models/timemap.py、drift/（Phase 4）、export/（Phase 9）、全部业务代码

## 决策

每条录音不是 offset，而是映射：

```text
T_global = f_i(T_i)      # 单位：秒（双侧）
```

* `identity`：T_global = T_local
* `constant_offset`：T_global = T_local + offset_seconds
* `linear`：T_global = scale·T_local + offset_seconds（scale = 1 + ppm·1e-6）
* `piecewise_linear`：按 (t_local, t_global) 结点分段线性，端外线性外推

业务代码依赖 `TimeMap` 接口（to_global / to_local / to_dict / from_dict /
is_identity），**不得**直接操作 offset / alpha / beta。

## 动机

固定 offset、clock drift、局部断点（CLOCK_DISCONTINUITY）、分段漂移是同一
类事物的不同复杂度形态。把它们统一为 TimeMap 后，drift 估计、图求解、
导出、校正渲染全部只面对一个抽象。

## 细节

* 样本 ↔ 秒转换只在边界进行（`to_global_samples` / `to_local_samples`，
  规范采样率 48 kHz）；
* piecewise 结点必须 t_local 严格递增且 t_global 单调不减（保证可逆）；
* 序列化 `to_dict`/`from_dict` 支撑 JSON 导出与缓存；
* `DriftModel`（d(t) = alpha_ppm·1e-6·t + beta_samples）是测量层模型，
  可无损转换为 `LinearTimeMap(scale=1+alpha_ppm·1e-6, offset=beta/sr)`；
* 分段漂移/断点不强行塞进线性模型——模型种类（linear vs piecewise）由
  Phase 4 估计器根据残差结构决定。

## 后果

* 未来新增映射类型（如样条）只需实现接口 + 扩展 from_dict 分派；
* DAW 导出输出的是 TimeMap/segments 的非破坏性时间线（Phase 9）；
* 渲染校正（可选功能）以 TimeMap 驱动高质量异步重采样，默认不用
  phase vocoder。
