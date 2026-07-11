# P14 真机 TOR 矩阵证据（2026-07-11 · orchestrator 窗亲跑）

- 矩阵：2 seed 族 ×（baseline 阳性对照 + {asphere,both} 优化候选）= 8 格，NTR 100，
  CMP DLZ SI（手册验证），DEF TOL S1..17 / S1..19。
- `matrix_s17_v2.tsv` / `matrix_s19_v2.tsv`：baseline 4 格全 ok（真饱和数 0.997/0.82，
  yield 诚实 unavailable——阈值+饱和门限未 ratify）；优化候选 4 格全 failed:run
  （TOR clear-aperture trace abort，见 `optimized_cell_tor_abort_sample.lis` 尾部
  "Ray tracing errors during clear aperture trace - OPTION TERMINATED"）。
- `pos_control/`：真实设计 5P_F1.9 阳性对照（FRE 50/100），机制全通但 MC 饱和
  0.916/0.858——默认公差表对手机镜头不可用的实证。结论详见
  `../p14-per-semantics-2026-07-11.md` §5。
- 完整逐格证据（staged ZMX/seq/双导出/parse.json/failure.json）在 orchestrator
  scratchpad 留档；本目录为决策级 curation。
- 本目录只有量化数据与机器可判事实；良率阈值/饱和门限/公差表 = 资深 ratify（[EXPERT]）。
