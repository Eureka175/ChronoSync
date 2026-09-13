# ADR-010：Adobe Audition SESX 导出

**状态：** Accepted（2025，Phase 3+，用户明确要求）
**依据：** docs/research/notes/sesx_format.md、audition_import_paths.md

## 决策

实现**手写 .sesx 导出**（export/sesx.py）。调研裁决（高置信）：

* SESX 是**无校验和/签名的纯 XML**；社区已有两个 MIT 生产级 writer
  （`outhud/audition-ses-to-sesx-converter` 在 Audition 2025 做过
  逐样本渲染验证；`nurdism/audition` 生产 bot 使用）；
* **所有时间字段（startPoint/endPoint/sourceInPoint/sourceOutPoint/
  duration）是会话采样率下的整数样本**（Adobe 官方脚本 API + 三个独立
  代码库 + 真实文件算术四重确认），不是秒、不是 tick；
* 最小结构：`sesx/session(tracks(音频轨+masterTrack)+sessionState)
  + files 表`；component/fade/channelMap/xmp 等全部可省略；
* 保留：`<!DOCTYPE sesx>`、masterTrack、trackOutput→master 路由、
  `mediaHandler="AmioWav"`、`defaultPanModeLogarithmic`（保持居中轨
  单位增益）。

## 保真规则（诚实声明，写入模块 docstring 与测试）

* identity / constant-offset → 单个精确 clip（整数样本）；
* 线性 drift → **阶梯近似** clip（可配置粒度，默认 10 s/块）：Audition
  clip 不支持变速，连续漂移无法在 SESX 内精确表达；每块台阶误差 ≤
  ppm·chunk_seconds 样本。精确校正必须走 `drift.correct_track` 渲染；
* piecewise（断点）→ 每结点区间一个 clip；平段（drop 空隙/insert 重复）
  成为时间线空隙——丢失内容不虚构；
* 负全局起点自动裁剪（clip 从 0 开始，source in-point 前移）。

## 后果

* 导出核心仍是 offsets + TimeMap + segments（非破坏性时间线），音频
  渲染为可选；
* Audition 无法表达变速时间线/变 tempo 映射——未来 Reaper RPP（Phase 9）
  承担更丰富的映射；CSV/JSON 报告始终作为兜底；
* 无官方 schema：格式细节以调研报告 + 两个验证过的 MIT 实现为基准，
  XML 结构由测试固化（元素、单位、ID 链接、转义）。
