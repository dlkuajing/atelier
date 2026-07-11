# P13 freeze 链真机冒烟发现（2026-07-11 orchestrator 窗）
1. dot-dir 路径炸 ZEMAXOS_TO_CV：.planning 路径导入失败→1 面空系统（listing: "ERROR - Zemax File ..."+"No entrance pupil"+"Index data not defined"）；readout 无声回哑数据；chain 的 identity 闸正确 withheld（fail-closed 真机验证✓）。铲3：输入路径守卫（类 ensure_buf_exp_safe_filename）或复制到安全临时路径。
2. readout vd 解码缺口：优化候选的模型玻璃在 CODE V DB 里是 '546000.401540' 码（nd=1.546, vd=40.154 编码在小数部），codev_readout 只解出 nd、vd=0.0→snap 提议在真机数据上因 vd 无效 fail-closed（正确但零产出）。铲3：补玻璃码 vd 解码（模式 =SEKONIX glass code 同族 6位nd+小数vd）。
3. 冻结序列语法（GLA nd:vd/AUT 块/快照宏）因上述前置未跑到——铲3 修完 1/2 后第一步重跑本冒烟。
探针与产物：scratchpad/p13matrix/（freeze_smoke.py + smoke_out/readout*/listing）
