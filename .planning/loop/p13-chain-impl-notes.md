# Phase 13 铲 2：glass snap chain 实现留痕

## identity 规则依据

- CODE V readout 的 `surface s` 玻璃/厚度解释为 `s → s+1` 介质区间；identity 为 `zoom + 相邻面区间`，不是裸 surface。
- 相邻非空气区间标记 cemented 邻接但维持两个材料 identity；同一区间多份声明必须完全一致。
- 非相邻面、非正厚度、缺 Nd/Vd、NSS、非单 zoom、同一区间不同材料声明均 `withheld`，禁止试写兜底。

## 与设计链逐条对照

1. `material_claims_from_readout` + `build_material_region_identities` 建区间并执行写前硬闸。
2. `propose_material_snaps` 每 identity 调一次离线核，ledger 保留完整 catalog identity、距离、delta、权重和谱线来源；超容差保留 fictitious。
3. `build_glass_freeze_reopt_sequence` 产生三段快照、显式 Nd/Vd/目录注释、玻璃冻结和参数化短 AUT；只构建字符串，不运行 CODE V。
4. `SnapVerification` 用 closed/frozen Pydantic model 和 computed fields 派生双轴 provenance；缺快照不能成为 `catalog-snapped`。
5. `scripts/p13_snap_matrix.py` 为 A-F（四主试验 + no-op + 预算对照）生成 TSV/Markdown 待跑骨架。

## 待真机项（8）

1. 真实 catalog 牌号赋值与 catalog 限定语法。
2. `GLC S... 100` 是否为可靠冻结表达。
3. 显式 Nd:Vd 写入与随后目录牌号 readback 的组合语义。
4. 三快照 per-field × per-wavelength spot/WFE/横轴色差宏与 buffer 拼接。
5. 配置指纹所需 focus/refocus、ray aiming、zoom 数据库项。
6. 短 AUT 的 MXC/MNC/IMP 与 termination/error 轨迹。
7. 默认 snap tolerance/dispersion weight 的分域校准。
8. H-LAK53A 等 Python/CODE V catalog value conflict 的 GLD 实测。

所有默认阈值与短 AUT 周期均标为“未经真机校准，矩阵后 ratify”；mock 仅验证结构，不代表真机测量。
