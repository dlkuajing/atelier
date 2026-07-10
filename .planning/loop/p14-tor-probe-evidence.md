# P14 TOR 真机语法采样证据（2026-07-11 orchestrator 排窗执行）

> 探针：scratch_diag/tor_probe.py（v1/v2，scratch 不入库）；真机=D:\CODEV115 CODE V 11.5。
> seed=data/zmx/US20170003482A1.zmx（ZEMAXOS_TO_CV 导入，S1..17+IMG）。
> 目的=设计文档 §2 的头号「待真机采样」项：WBF PER/MC 导出文件语法。

## 真机实锤（逐条对应设计文档待验证项）

1. **`DEF TOL` 裸命令非法**：真机报错 `DEF TOL not allowed on OBJ or IMG - specify individual tolerances`，
   真语法=`DEF TOL Sk|Si..j [Zk]`（listing 原文）。builder 的 tolerance_table 命令必须带面范围。
2. **`WBF PER` 裸命令非法**：真语法=`WBF Bk|No SEN|DST|PER|ZRN|MC [APP]`（listing 原文）。
3. **单 GO 双 buffer 成立**：`WBF B1 PER` + `WBF B2 MC` → 一次 `GO` → 两个 buffer 各自 `BUF EXP`
   均产出——设计/spike 里「双 GO 待验证」不确定项就此消解，批处理链可简化为单 GO。
4. **进程退出码=1 但导出有效**：与 codev_batch `allow_nonzero_ok_result` 先例一致，
   铲 2 接线时走显式文件契约+允许非零。
5. **成本**：NTR 20 + FRE 100 + CHT N 全链 2.3s（本 seed）——TOR 真机窗成本极低，
   铲 2 可考虑 NTR 100+。

## 导出语法样本（已入 tests/data/codev_tor/，逐字节真机产物）

- `real_sample_per_*.txt`：TSV；头块=日期/镜头名(空)/Fringe wavelength 546.1/三行概率密度
  函数声明（Scalar 1-D Uniform / Decenter 2-D Gaussian 0.135335 / Cylinder 2-D Uniform）；
  表体=每 Eval Zoom×Field 行：Relative Field X/Y、Frequency、Azimuth、Weight、Design、
  Criterion、「Design + tolerances」50.0/84.1/97.7/99.9% 四概率位列、「Changes」同四列。
- `real_sample_mc_*.txt`：TSV；头块同上+`Number of Monte-Carlo samples:\t20` 行；
  表体=`Sample\tZoom\tField\tCriterion\tValue` 逐样本裸数据（20×3 行）。
  **良率可从 MC 裸样本直接计算**（阈值判每样本每场→比例），不依赖 CODE V 侧摘要。

## 待铲 2 钉死的语义项（语法已定，语义未定——诚实边界）

- PER 表数值的单位/口径（Design=0.0699 像 MTF 绝对值，但概率位列出现 5.08/-31/100.9 等
  超 [0,1] 值——疑似百分比变化或其他口径，须对照 Tolerancing.pdf 后由测试钉死，禁猜）。
- MC Value 大量 0/1 饱和的语义（clip？失败哨兵？）；本 seed 是未优化 baseline、
  100lp/mm 下离轴 MTF 本就崩，需换优化后候选复采一组对照。
- 默认补偿器实际用了什么（listing 未显式列，需 Tolerancing.pdf 对照）。
