# P13 freeze 序列未解谜团：预编译定义 + 优化候选导入 = row-qualifier cascade（2026-07-11 真机档案）

> 状态：**OPEN**。本档记录已排除项与逃生门方向，供下一真机窗脚本化二分。
> 全部结论来自 orchestrator 真机窗逐一实验（探针留档 scratchpad p13matrix-real/probe_fct/，
> 关键 .lis 摘录见下）。

## 现象

freeze 序列（含 FCT 定义或顶层 LCL 声明）+ `ZEMAXOS_TO_CV` 导入**优化候选 ZMX** →
数千至 23 万条 `ERROR - Zero or negative value for row qualifier`，BUF EXP 无产物，
偶发 `option CHA` critical error（流搓坏时的表象）。

## 实验矩阵（全部真机）

| 组合 | 结果 |
|---|---|
| 无定义 + 候选导入（readout 宏） | ✅ 干净（LF 修复后 3 波长+色散 vd） |
| 无定义 + seed 导入 | ✅ 干净 |
| FCT（我们的 @p13wfe/@p13wfeok）+ 候选，FCT 在 import 前/后 | ❌ cascade（两种顺序都炸） |
| FCT 改纯字母短名（@pwfe/@pwok） | ❌ cascade（排除函数名长度/数字） |
| **codev_optimize 已验证 FCT 块逐字节照搬** + 候选 | ❌ cascade（排除我们 FCT 块本身） |
| 同一 FCT 块 + seed 导入 | ✅ 干净 |
| 顶层 `LCL NUM ^rwe(10,26) ...`（无 FCT）+ 候选 | ❌ cascade（定义=触发编译模式即中招） |
| 候选=LF、24 槽 WAVM（e0226f94 同 hash 三处校验） | 上述所有候选实验均用此文件 |

**净结论**：任何「预编译定义（FCT/LCL）导致命令流进入编译执行模式」×「此优化候选文件
内容」的组合都炸；seed 文件在两种模式都干净。候选与 seed 的内容差异（极简 header/
EVENASPH 系数精度/…）中某项在编译模式下令导入宏 buffer 迭代出 0 行号——具体是哪项未定位。

## 已排除

FCT 名长度/数字、FCT 块内容（照搬已验证块仍炸）、FCT 位置（前/后都炸）、seq 行尾
（工作/失败 seq 均 CRLF）、候选行尾（LF 修复后仍炸）、WAVM 槽数（24 槽仍炸）、
路径长度（同长路径 readout 干净）。

## 逃生门方向（下窗验证，探针已写好未跑完）

**两段执行解耦**：段1（无任何定义）`IN CV_MACRO:ZEMAXOS_TO_CV` + `SAV lens.len`；
段2（带 FCT/LCL）`RES lens.len` + 快照/AUT/BUF EXP。彻底避免定义与导入共流。
probe_fct/run19.seq（导入+SAV）与 run20.seq（FCT+RES+RMSWE+导出）已备，因窗口移交
Stage B 未跑完。**若两段皆净 → glass_snap_matrix 驱动改两段串行批跑（builder 拆两个
sequence builder），矩阵重跑。**

## 运维教训（本窗实锤）

直接 `codev.exe /B` 探针每次留一对 codev/codevm 孤儿进程（7 对堆积后新批任务静默排队
挂死）——探针一律走 `run_codev_batch`/`run_codev_process`（超时+kill-tree 纪律），
杀孤儿后 `Get-Process codev,codevm` 必须归零再继续。
