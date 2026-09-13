# ADR-012：验证与可解释置信度

**状态：** Accepted（2025，Phase 7）
**影响面：** validation/、fine/gcc_phat.py

## 决策

验证四件套 + 证据聚合：

1. **残差 GCC**：校正后再次 GCC，理论接近 0 样本；静音窗口跳过
   （GCC 无法测量静音），GCC 失败跳过——绝不把 NaN 当证据；
2. **coherence（MSC）**：Welch 平均周期图，80-8000 Hz 均值；
3. **polarity**：`corr(x,y)` 与 `corr(x,-y)` 对比，反相仅在反相关系数
   **明显更高**（margin 0.1）时判定——**MSC 低 ≠ 反相**（实测固化：
   无关内容 MSC<0.05 但 polarity=0）；
4. **置信度 = 加权证据**（coarse 0.25 / drift R² 0.20 / 残差 0.25 /
   coherence 0.15 / polarity 0.15），缺失证据剔除并重归一化 + 警告。

## 关键实现决策

* **GCC 反相感知**（Phase 7 前置，改在 fine/gcc_phat.py）：
  反相对的相关峰为**负**——当负峰 |值| > 正峰×1.2 时翻转相关面分析，
  返回 `polarity=-1` + 警告。没有它，反相对的 drift 估计整体失效
  （粗匹配是幅度指纹所以能过，drift 全部窗口失败——实测）。
* **验证在"校正后"信号上进行**：漂移未去除的原始对 coherence 天然
  崩溃（120 ppm/30 s 时 >277 Hz 全去相关，实测 MSC≈0.026）——漂移抹平
  不是失配证据。validate_pair 内部先用 correct_track（SoXR）渲染再
  测量，证据语义正确。

## 后果

* 证据字典随报告输出（JSON 可序列化），无魔法数字式 confidence；
* 反相被 drift/验证两层发现：GCC 警告 → 验证报告 POLARITY INVERSION；
* 修正渲染的 coherence/polarity 检查同时覆盖线性/分段映射（平段输出
  静音，coherence 自然反映）。
