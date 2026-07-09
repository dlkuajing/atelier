# CODE V 行为经验探针报告（闸2 Step-0）

- **seed**: `US20170003482A1.zmx`
- **探针**: scratch 动态、不 mutate 交付宏（spec §3）
- **CODE V**: `D:\CODEV115\codev.exe`

| E# | 经验未知 | 跑通 | 实测发现 |
|---|---|---|---|
| E5 | seed 原生场类型 / 场集含 rel-1.0? / 原生渐晕系数(E8-native) | ✅ | field_type=ANG, num_fields=3, aperture_type=FNO, f_number=2.32, EPD=1.56143, image_height_y_mm=3.6863; 原生渐晕系数全0(此seed E8 trivial) |
| E1/native(FNO) | native(FNO) 模式：AUT 拉 EFL 到 target 时 F#/IMH/EPD 漂不漂 | ✅ | EFL 3.6225→4.0557(target 4.0572, 达成偏差0.04%) · F# 2.3200→2.3200(漂0.00%) · EPD 1.5614→1.7481(漂11.96%) · IMH 3.6863→4.1271(漂11.96%) |
| E1/epd | epd 模式：AUT 拉 EFL 到 target 时 F#/IMH/EPD 漂不漂 | ✅ | EFL 3.6225→4.0572(target 4.0572, 达成偏差0.00%) · F# 2.3200→2.5984(漂12.00%) · EPD 1.5614→1.5614(漂0.00%) · IMH 3.6863→4.1287(漂12.00%) |
| E7 | AUT 同 seed 同 target 是否逐位可复现 | ✅ | 两次 after.efy: 4.05566 vs 4.05566 → 逐位一致(确定性) |
| E6 | AUT 有无显式收敛标志 → 天花板臂 RED/INVALID 判据 | ✅ | 极端 target(+200%): EFL 3.623→4.497(target 10.868, 达成偏差 **58.6%**)。CODE V AUT 无 macro 可读显式收敛码 → 用 **EFL-hit 代理**：偏差>>2% 明确区分发散(代理有效, spec E6 fallback 成立) |
| E3 | 畸变 DIX/DIY 有无 err 出口 → distortion 守卫怎么写 | ✅ | DIX/DIY 为 DB accessor 纯读值（轴 DIX=0, max 场 DIX=0/DIY=0.00370921），**无 err 语法**。守卫须用有 err 出口的 trace 原语——SPOTDATA(...) 返回 ^err（现有 @rmssum 已用、真机 optimize 冒烟已证可用）→ distortion 守卫=每场先 SPOTDATA/RSI err 前置，成功才读 DIX/DIY。 |
| E8 | 场 ANG→IMG 重建后渐晕(VUY/VLY)是否需重解 | ✅ | Seed-1 原生渐晕系数**全 0 → E8 对此 seed trivial**（场重建无渐晕可丢）。通用回答需一颗**带渐晕系数的 seed** 复测；Stage C 实现时对带渐晕 seed 须同步重解 VDX/VDY（保守 fail-closed）。 |
