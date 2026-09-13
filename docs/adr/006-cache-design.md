# ADR-006：特征缓存设计

**状态：** Accepted（2025，Phase 1，设计先行；Phase 3 实施）
**影响面：** cache/、features/、coarse/、drift/

## 决策

两级缓存：

1. **SQLite** 只存索引元数据；**大数组一律不进 BLOB**；
2. 特征数组存为 **`.npy` / `.npz` 文件**，由 SQLite 记录其路径。

## 索引键

```text
path         源文件路径
size         文件大小（字节）
mtime        修改时间
hash         （可选）内容哈希，用于 mtime 不可靠的场合
algo_version 算法版本（如 "gcc-phat@1"）
feat_version 特征版本（特征定义变更时递增）
```

命中条件：路径 + (size, mtime) 或 hash + algo_version + feat_version 全部
一致。

## 计划缓存的特征

energy envelope、spectral features、MFCC、fingerprint、transient map——
每个特征一条缓存记录，独立失效。

## 动机

1 小时以上录音的特征提取/粗匹配是重复开销大头；SQLite 单文件、可事务、
可跨进程；文件型数组避免 SQLite 大 BLOB 的性能灾难与内存拷贝。

## 后果

* 所有特征提取器必须声明 algo_version / feat_version，否则不得启用缓存；
* 缓存失效策略以 (size, mtime) 为主，hash 为可选强校验；
* 缓存对正确性透明：任何缓存未命中都退化为现算。
