# Phase 16 Stage C — 离线实现边界（2026-07-11）

本铲只建立可审计的离线 seam，不调用、连接或探测 CODE V。

## 已实现

- `ResolvedFieldTarget`：要求有限正 EFL；IMH-only/FOV-only 按一阶关系互相派生；两者同时提供时按严格数学一致性检查，冲突输出裸偏差，未发明产品容差。
- 临时 ZMX 重建：只接受 FTYP0、XFLN 全零、完整零渐晕 profile；保留任意场数及归一化 fractions，将 edge 钉到 target IMH，输出 FTYP3、LF；源 SHA-256 前后相同。
- `StageCFieldEvidence`：四条件 closed schema；IMH 仅在 constructed-verified + 真实 chief-ray + RSI 证据齐全时可 achieved；FOV 只允许 derived/measured/unavailable。
- 离线 manifest：至少 8 seed，每颗 native + 两个 target 三臂；所有真机结果为空、状态 blocked、`[EXPERT]` 留白。
- 候选/metadata/export seam：payload 的 nominal IMH 与 derived FOV 可从同一个 resolver 注入；Stage C evidence typed 持久化；Stage B reproduction.seq 不得冒充 Stage C replay。

## 明确未验证

- CODE V ANG→IMG 命令、增删场语法；
- RSI、WRX/WRY、真实主光线读取与验真；
- 非零 VDX/VDY/VCX/VCY 的场重映射/重解；
- 真机前四条件不得全 True，FOV 不进入 `CONVERGED_FIELDS`；
- 量产可用性与良品判定仍由资深设计师 `[EXPERT]` 背书，本铲不代填。
