# ADR-008：粗匹配级联

**状态：** Accepted（2025，Phase 3）
**影响面：** coarse/、features/、cache/

## 决策

粗匹配采用短路级联：metadata（prior）→ fingerprint → envelope →
transient → No Match；每阶段返回 `MatchResult`（matched/offset/confidence/
method/overlap_estimate/evidence/warnings），任何阶段达到
`accept_confidence` 即返回；全部失败时返回最佳证据且 matched=False。

## 关键实现决策

1. **指纹绝对 dB 标定**：输入单位 RMS 归一 + 谱幅度除以窗能量 →
   完整能量帧 ≈ 0 dB。取代"分段最大值相对归一"——后者导致分块指纹与
   单次计算不一致（各 chunk 阈值基准不同，实测丢失/多出边界锚点）。
   绝对标定同时保证跨文件增益不变性。
2. **分块 == 单次**：峰检测需要 ±5 帧真实上下文（`maximum_filter`
   补零在段边界产生伪峰/丢峰，实测修复）；块间重叠 delta_max+2 帧
   覆盖锚点伙伴区。测试固化 `np.array_equal`。
3. **投票置信度**：0.7·投票占比分 + 0.3·峰比分，再乘
   `min(1, votes/5)` 投票门限——3 票/10 哈希碰撞不是匹配。
4. **envelope 方向**：`scipy.signal.correlate(ref, tgt)` 峰值 = −d
   （与 GCC 交叉验证固化）。
5. **metadata 永不 matched**：无时间码解析时 mtime prior 是搜索提示，
   不是证据。

## 后果

* 粗匹配精度 ±0.5 帧（~23 ms @ 11025 Hz）是设计内行为；drift 层精化；
* 缓存键含 algo/feat 版本（ADR-006），指纹算法变更自动失效；
* 专利提示（ADR-007）：星座思想为 clean-room 实现，商用另行评估。
