# 真实案例：MP4 无线麦克风通道延迟（20260903_Cxxxx 系列）

## 现场事实（实测）

素材：`textvid/20260903_C1159..C1177.MP4`（19 片，4K HEVC + 4×mono PCM24
@48 kHz，CH1/2=无线麦、CH3/4=有线）。

| 结论 | 实测 |
|---|---|
| 片内延迟恒定 | drift 判定 constant_offset（α ≈ ±1.5 ppm 噪声级）——同容器同时钟，纯固定 latency |
| **跨文件不恒定** | CH1 延迟 19.7–29.5 ms 不等 → 必须逐文件测量 |
| 有线对可作参考 | CH3 vs CH4 = 0.004 ms |
| 两无线通道独立 | CH1 与 CH2 相差 ~1.9 ms |
| 示例（C1171） | CH1 = +25.473 ms（+1222.7 样本）、CH2 = +27.341 ms（+1312.3 样本） |

## ChronoSync 侧实现

* 库：`chronosync.mp4sync`（ffprobe/ffmpeg 抽取 + GCC/drift 测量 +
  `fix_channels` 样本级修正 + remux 复检）；
* CLI：`chronosync mp4-sync <files|--folder> [--reference-stream 2]
  [--fix] [--remux] [--json P] [--csv P]`——全文件夹 19 片已实测跑通；
* 测试：`tests/unit/test_mp4sync.py`（纯算法）+ `tests/integration/
  test_mp4sync_ffmpeg.py`（ffmpeg 合成 4×mono MP4 全闭环：测量 1223/1350
  样本精确、修正后复检 < 0.05 ms）。

## 交付给外部工程（1KeyTranscoder）的纯算法包

`handoff/mp4_channel_sync/`：`mp4_channel_sync.py`（numpy+scipy，无 ffmpeg
依赖）+ 独立自测（16 项，`python test_mp4_channel_sync.py`）+ 完整文档
（算法原理/API/集成指南/验收标准）。与 ChronoSync 实现交叉验证一致
（1223.000 vs 1223.000 样本）。
