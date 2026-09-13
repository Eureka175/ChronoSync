# ADR-011：多轨全局图求解

**状态：** Accepted（2025，Phase 6）
**影响面：** global_alignment/、pipeline.py、export/

## 决策

```text
tracks = nodes; measurements = weighted directed edges (ADR-003)
min Σ w_ij (t_i - t_j - d_ij)^2,  reference track pinned at 0
```

* 参考轨：显式指定或自动选择"最连接"轨道（Σ 入射边置信度最大）；
* **连通分量独立求解**：与参考轨不连通的组件各自锚定并**大声警告**
  ——求解器绝不静默混用不相关时间线；
* 每条边输出残差；|残差| > 3×robust sigma（MAD 尺度）的边标记为离群；
* 每轨置信度 = 入射边（置信度加权的）一致性：`agreement =
  1 - |residual|/(3σ)`，参考轨恒为 1；
* 可选 **IRLS**（`irls_iterations > 0`）：Huber 式重加权迭代，离群边
  失去影响力；实测离群边污染下 IRLS 解显著优于普通 WLS。
  Huber/IRLS 之外（RANSAC 等）刻意推迟——第一版不过度复杂。

## 关键实现决策

* 正规方程按分量构建：自由节点 A·t = b，参考轨项移入 RHS；奇异系统
  回退最小二乘并警告；
* 无测量边的轨道**不出现在图中**——由 pipeline 显式报告
  （"matched nothing; excluded"），绝不静默放置；
* 未直接与参考轨测量的轨道用求解常数 offset 放置并警告（跨未测量对的
  TimeMap 复合是文档化的未来工作）。

## 后果

* 边方向/符号沿用 ADR-003，求解器不做任何方向推断；
* benchmark：50 轨 / 1225 边 WLS 求解 ~12 ms——多轨规模不是瓶颈；
* 残差与每轨置信度直接进入 Phase 7 证据链与 JSON/CSV 导出。
