---
quick_id: 260712-stagec-real-evidence
status: in-progress
owner: Codex
base: b62542114ad79d071cf3cd07bdf5cd5978bbfb4a
---

# Phase 16 Stage C 真机证据与生产同源闭环

## Hard gates

- 全程 CODE V 单实例；每次启动前核验 P18 owner、P18 runner、CODE V/codevm 全归零，统一走 `run_codev_process` 的 timeout/kill/reap 契约。
- `[EXPERT]` 留白；机器只陈述 measured/attested facts，不生成合格、良品率或量产可用 verdict。
- v2 synthetic parser 保持 `parsed-unverified`；只有 runner 在真实进程终止后、从 fresh raw artifacts 原子生成的 v3 receipt 可建立 attestation。
- FOV 仍为 derived/measured，不进入 `CONVERGED_FIELDS`；IMH 是否扩入必须由完整真机矩阵证据支持，不预设答案。
- 新鲜 Stage B 生产输入必须先由共享 `stageb_authority` 写 durable intent，再调用官方 ladder；raw result、唯一 derived result、content-addressed accepted bytes 与 Stage C package 形成可重算闭链。历史 legacy 输入只能显式 retrospective adoption，不能升级为 pre-run-bound。
- 所有工作从 `origin/main@b625421` 的干净 worktree 开始，经独立对抗审查与 PR → CI → merge → main CI。

## A. Official-macro verified probe

1. 固定并哈希 CODE V 11.5 官方宏：FTYP3→RIH、XRI/YRI、四零 `rayrsi` chief、RER/BLS、image X/Y/L/M/N、VUY/VLY/VUX/VLX。
2. 以 native RIH 非零渐晕 seed `5P_F1.9_FOV76.9_EFL3.6_IMH2.9_TTL4.30.zmx` 验证实际字段/四 V/VDY 符号、输出编码与精度。
3. 以 ANG 零渐晕 seed `US20170003482A1.zmx` 做 native、CVTFIELD IMG、CVTFIELD RIH 三路独立重导入，保留 raw stdout/stderr/listing/metrics bytes 与哈希。
4. SPOTDATA(1) 明名 `rms_spot_diameter_um`，不得误叫 radius。

## B. Runner-attested v3

1. 增加 raw-byte CODE V process API，保持现有 text API 兼容。
2. 建立无循环 hash DAG：spec → sequence → launch manifest → process/raw → normalized sidecars → post-run receipt → attested evidence。
3. receipt 只能由内部 runner 写；唯一 run_id/attempt 目录、全局 CODE V lock、raw bytes 永久保留、receipt-last、同卷原子 publish、崩溃 `.inflight` 永不 attested。
4. parser 从逐 sample raw rows派生 attempted/valid/classification；duplicate/missing/unexpected sample、rc/RER/BLS、NaN/Inf、非 RIH、四 V 与重建处方不一致、hash/path/encoding漂移均 fail closed；有限且同源的非零渐晕不得被静默归零。
5. public restore 必须独立重验 CODE V 路径/版本/二进制 hash/size、官方宏 hash、零进程退出码、有限 duration，以及目录中的**全部** entry；额外文件、目录、symlink、junction 一律拒绝。
6. execution plan 只接受闭合 schema：矩阵计划须证明 8 unique seeds × 3 canonical arms × 2 repeats，生产计划须为单一 `production-target` cell；两者均绑定 Stage B manifest bytes、目标、确定性重建 hash 与唯一 cell identity。
7. 本地 HMAC 的诚实边界仅为当前 OS account/profile ACL 下的 Atelier runner；不宣称抵抗同用户任意代码或本机管理员，也不得在导出文案中误称独立数字签名。
8. Stage C package 必须保留并绑定 Stage B raw ladder bytes；restore 从 raw 重新派生 final 语义并反验 accepted artifact，不能只信 manifest/final JSON 的互相自证。

## C. Pilot and matrix

1. ANG/RIH pilot 先验证 reconstructed field、真实 chief ray、EFL、spot/WFE 与 v3 receipt。
2. 从 Stage B accepted artifacts 固定 ≥8 seed，三臂共 24 cells，每 cell 至少独立 repeat 2 次（≥48 real runs）。
3. 同一 canonical bytes 用于 reconstruction、machine evidence、candidate payload 与 export；仅 `target_achieved=true && accepted_final` 才允许进入 production Stage C。
4. 报告每 cell/run 的 delivered/blocked/failed、重复分布、像质代价与机器警告；不推导 `[EXPERT]` verdict。
5. Stage B cache 必须绑定 source bytes、全量 runner source、Python 环境、官方 macro、CODE V executable/version 与全部 ladder 参数；生产调用由 `app/core/engines/stageb_authority.py` 统一持有锁、intent、raw→derived 变换和 accepted 发布。历史 cache 如需接纳，只能显式生成“retrospective current-state adoption”证据，禁止伪称 pre-run attestation。
6. matrix plan 在临时目录完整构建后原子发布；中断产物保全为 orphan。resume 必须先恢复已发布 receipt，再决定是否新跑，禁止 crash window 导致重复真实机调用。
7. matrix/state 使用独立跨进程锁；失败 attempt 保留 duration、error/kill/reap 与 package path，报告按 arm/cell 汇总真实机时间成本及相对 native control 差值。

## D. Production and release

1. 将 v3 runner 接入真实 Mode3/Stage B accepted-final 路径，v2 fixture 永不冒充生产。
2. candidate/scorecard/workbook/bundle 同源并严格 restore raw package；candidate artifact 目录冲突 fail closed，导出只写一次性 byte snapshot，杜绝已验证 evidence 与 `candidate.zmx` 的 TOCTOU 脱钩。
3. 运行离线全套（显式 `-k "not real"`）与受控真机验收；独立只读对抗审查。
4. PR CI success 后 merge，main CI success 收 F。

## Offline checkpoint — 2026-07-13

- legacy Stage B 原件已先行 byte snapshot；本 checkpoint 未运行 adoption、runner 或 CODE V。
- Stage C/Stage B authority 关键统一门为 378 passed；源码冻结后两条互相独立的只读对抗终审均为 PASS，未发现 P0/P1/P2 阻断项。
- 仓库离线全集已分片闭合：`-k 'not real'` 合计 2106 passed、1 skipped；补齐 `real_machine` 隔离后，real-name 但纯离线补集 531 passed。因此 11 个真机项之外的仓库全集为 2637 passed、1 skipped。
- `real_machine` marker 已覆盖 11 个依赖、探测或启动本机 CODE V 的测试；`pytest -m real_machine --collect-only` 仅收集、未执行。独立只读交叉搜索结论 PASS。
- production source 冻结时，changed Python files 的 `ruff check`、`ruff format --check`、`py_compile`、AST/import smoke 与 `git diff --check` 全绿；后续 test-infrastructure marker 变更另经 `ruff check`、collect-only 与 diff-check 复核。
- 诚实事故留痕：首次尝试 real-name 离线补集时，旧真机测试尚未全部标记，命令误启动本机 CODE V；结果为 537 passed、2 skipped、1 failed，失败是既有 roundtrip closure 中 exported wavelength_count=24 与 readout=3 不一致。该运行不属于 Stage C pilot/matrix、不得作为 Stage C 证据。发现后立即停止扩展范围，进程与 CODE V/P18/Stage B owners 均复核归零，并用 marker 修复测试隔离。
- 本离线 checkpoint 落笔时 adoption-only 尚未执行；后续 runtime 真值见下节。legacy 原件、snapshot 与 v2 authority 产物始终严格分离。

## Stage B authority runtime checkpoint — 2026-07-13

- adoption-only 已在进程/四锁全零窗口由 root 亲跑：首次 `created=9, verified=0`，幂等复跑 `created=0, verified=9`。9 份记录均为 `retrospective-current-state-adoption`，`pre_run_bound=false`、`run_time_identity_verified=false`；legacy inventory SHA 仍为 `7ef51a215fd3d54de432c7acff724afda967323205d755266ba7761f8eee24d7`，14 个原件的 SHA/size/mtime 全部不变。
- 首轮受四锁保护的 v2 runner 已跑完 21/21 jobs：12 个新 job 均有 durable intent、raw result 与 derived final，`incomplete_attempts=0`；4 颗新 seed 通过四条件门，加上 2 颗 retrospective seed，`manifest-v2.json` 为 6/8、`complete=false`、SHA256=`50d06387f72bb9ef85901dc84feb7d8f8c93e31500048f9417b55a8fce7d9f34`。结束后 runner/CODE V/codevm/四把 owner 全零，stderr 为空。
- 8 个新失败中，2 个在首 rung 硬超时、无 measured final；其余 6 个均闭合 AUT/F/#/EFL，但真实 ray gate 为 TIR，retry ladder 无 ray-clean edge。不得把近失或建议 F/# 当作成功预测。
- 直接修改原 `p16_stagec_stageb_inputs.py` / `JOBS` 会改变 runner source hash，并可能重跑 12 个已终态 attempt。下一步采用独立 supplemental wrapper：原 21 case 强制 cache-only、任何 miss/drift/damage/duplicate/incomplete 零写入 fail-closed；仅 evidence-ranked 的 8 个 unused seed 可调用原真机路径，且 supplemental identity 额外绑定 wrapper 自身 bytes。wrapper 明确拒绝 adoption 与 recovery CLI；若 supplemental 真实崩溃，必须先实现并审查 supplemental-only recovery。原 runner、`app/core/**`、`pyproject.toml`、`uv.lock` 必须保持首轮 identity 字节不变。
- 第一代 supplemental wrapper 已在进程/四锁全零窗口运行完 29/29 jobs；8 个 supplemental case 均有 durable intent、raw result 与 derived final，`incomplete_attempts=[]`。其中 `US-11906710-B2-e6` 通过 authority 门，累计 accepted 为 7/8；其余 7 个均诚实失败：5 个最终 ray gate 为 TIR，`US-10101561-B2-e3` 为首 rung hard-timeout 且无 measured final，`US-11668898-B2-e6` 为 AUT `unable_to_scale_pupil_field` 且 TIR。最后一颗 `US-12174456-B2-e5` 的 F/#/EFL 已测量，但 AUT `irrecoverable_condition` 且四个 retry edge 全为 TIR。
- 该轮最终 `manifest-v2.json` SHA256=`1c2510a26ad36de54b9cb37a451aa056314dc5f873021eb18062fc8f7c942c45`、`accepted_count=7`、`complete=false`、29 个 unique outcomes、stderr 为空；runner/uv/python/CODE V/codevm 与四把 owner 全零。7 个 accepted 的 source/cache/result/raw/accepted hashes 全部反验通过，5 个 pre-run-bound accepted 均为 content-addressed ZMX；2 个 retrospective adoption 保持 legacy 命名与显式低信任 scope，`expert_verdict=null`。
- legacy snapshot inventory SHA 仍为 `7ef51a215fd3d54de432c7acff724afda967323205d755266ba7761f8eee24d7`；14 个 source 原件逐一复核 SHA/size/mtime 全部不变。因仍缺 1 颗，禁止盲目 resume 第一代 wrapper。下一步必须新建 supplemental2 wrapper：原 21 + 第一代 8 共 29 case 全部 strict cache-only，并按各自原 identity 重算验证；仅全新候选可调用 CODE V。旧 base/first wrapper 及其 identity source bytes 在收齐 8/8 前继续冻结。
- supplemental2 wrapper 已经两轮静态审查和独立终审 PASS；base/first/second wrapper SHA256 分别为 `4f94a0cbc01405a7b3025f6c2ebadf9403282d83d566fe46bad0390b2f79d080`、`9ffcbd381ccb62d8caefd01bd28e3dc7fed57a856d3b8c7a26d92cb7d40cae30`、`279981469cd8a259aba4b309e616afe7465980cc6d60fe0ce7420eefb9e3f41e`。29 条历史 cache-only 预检以预期退出码 2 返回，2422 个输出文件的前后聚合 SHA256 均为 `67ce3cd2608add28096b43241edc7e926466f4336bf03cc216e46cf20a605e93`，运行中未观察到 CODE V/codevm，manifest 仍为 `1c2510…2c45`。
- 唯一 supplemental2 真机 runner 只运行第 30 条 `US-11906710-B2-e5`，并在累计 8/8 后立即停止；31–37 均无 attempt。新 attempt `de768b902c484603906053d06ff6e94d` 的 intent/raw/result/accepted SHA256 分别为 `2b31b44068f417e76b556ebf6e18bb1457535dda2f07789374208b3580bd52b7`、`56dbee5a95756f677f7f25641e6081adaf9b7d09d7fbe844e1edefd33d9b4728`、`c5cf2bcad54e2e2cfa4f2feb570eb6b68ca6ce3d19c71958026567dda3bc6af2`、`4b0d02a997d217774a527d5405ffaf835ef82f08fec44ec84ea9782f8c69ed57`；F/2.28 实测 `2.2799963830598022`，F/# 偏差 `0.0001586377%`、EFL 偏差 `1.521961e-10%`、AUT normal completion、ray `ok`、0 REFL/0 MISS，effective edge `0.5`，账本保留渐晕 pupil 下像质偏乐观的说明。
- 最终 `manifest-v2.json` SHA256=`29384d5d9a10356c8b9bd908c48ab6970977fcafe77ac59a100aaf268350d969`，对应不可变快照字节相等；30 unique outcomes、8 unique accepted、`complete=true`、`incomplete_attempts=[]`、`expert_verdict=null`。历史 29 outcomes 与旧快照逐对象相等，历史 7 accepted 逐对象相等；legacy 14/14 原件 SHA/size/mtime 仍与 inventory 精确一致。三路互相独立的只读审计分别覆盖 manifest/hash DAG、legacy 不变性、runner 停止语义，结论均为 PASS。诚实边界：2 条为 retrospective，e5/e6 为同专利族相关样本，8 条不构成良品率声明。
- cache 门关闭后的定向离线回归为 640 passed、60 deselected；marker 文件最小化后补跑为 139 passed、10 deselected。36 个 changed Python 文件 `ruff check` 与 `py_compile` 全绿；除 7 个仅增加 real-machine marker、历史上并非 formatter-clean 的测试文件外，其余 29 个生产/新测试文件 `ruff format --check` 全绿；生产模块 import smoke 与 `git diff --check` 全绿。
- 诚实事故留痕：曾两次误把“targeted”门扩大为全仓单命令，外层分别在 124 秒与 604 秒超时，未获得 pytest 退出码，故两次都不计作测试证据；第二次遗留离线 pytest 进程树继续跑评估 case 后自然归零，全程无 CODE V。随后一次相对路径 `apply_patch` 误落到禁止使用的旧 `D:\atelier`；立即停止编辑并核验影响范围，只涉及 6 个 tracked 测试文件。六者已按该 worktree 自身 `HEAD@58d743f` 恢复，Git blob hash 逐项完全相等，最终 tracked diff 为零，原有 `.claude/` 与 handoff prompt 两个 untracked 路径未触碰。活动 worktree 的 marker 文件也已恢复为仅 10 行真实语义 diff。

## Official-macro probe 与首个 RIH pilot — 2026-07-13

- 最终 ANG/IMG/RIH 三臂 official-macro probe 已串行完成并经独立只读审计 PASS。三份 receipt SHA256 分别为 `0be678e0f34bd5617fe264885419eca4a7e0ccccb4e66e6788cfe6ea007d0a62`、`78e2b90c55bff0af32df88d64788b980c9e10eb4bf6c840900f2d6bb31a83071`、`b9517ce11950e74f0c77f47b91f3f5d2e614a0becf38461b69900a3e24d311ef`。三臂真实 CODE V return code 均为 1，但 BEGIN/END、24×3 metrics、raw/listing/artifacts 闭包完整；ANG/IMG/RIH 的 spot、WFE、chief ray 与 EFL 在数值容差内同源一致。该结论仅证明 probe 行为，不是 production attestation、光学合格、良率或 `[EXPERT]` 结论；零渐晕 seed 也不能单独证明非零 V 的符号传播。
- matrix plan 已稳定生成：`D:\atelier-stagec-runs\stagec-real-matrix-20260713\matrix-plan.json`，SHA256=`fa7aa3105ff756ca146699467a27224e899dd8aa58e7ef9e1df735e1c25a1ba1`，严格为 8 unique seeds × 3 canonical arms × 2 repeats = 48 runs；此时尚未启动矩阵。
- 首个 RIH pilot 选择 pre-run-bound `US-11906710-B2-e5`，真实 CODE V 仅启动一次。CODE V 已完整写出 16 个 artifact 与 receipt，但 Windows 上 `_fsync_package` 以只读 `rb` handle 调用 `os.fsync`，触发 `OSError [Errno 9] Bad file descriptor`，因此包停留在 `.inflight`；该失败发生在 receipt-last 之后、原子发布之前，不是 CODE V 或 parser 重跑理由。
- fsync 修复将文件 handle 改为 `r+b`，Windows 跳过不受支持的目录 fsync，并增加 `_publish_stagec_inflight`：全文件 fsync → inflight 私有 restore → 同卷原子发布 → final 公开 restore，后验失败则隔离到唯一 quarantine。定向离线测试 `tests/test_stagec_attested.py -k 'not real'` 为 62 passed、15 deselected；独立只读终审结论 PASS。
- root 在 runner/uv/python/CODE V/codevm 与 matrix/P18/CODE V owner 全零后，按 matrix lock → P18 global lock 顺序仅调用 `_publish_stagec_inflight`，没有调用 `run_stagec_attested`、没有再次启动 CODE V。最终包为 `C:\Users\Administrator\.atelier\stagec-runs\stagec_rih_pilot_20260713T034345Z_8426224a`，receipt SHA256=`09e081afb24ee1e1934a0084bc9724e5445544a34f218b4e1442b1aa3ff3994b`；公开 restore 成功，`.inflight` 消失，进程与 owner 仍全零。
- 该 pilot 必须保持 blocked 解释：`image_height_achieved=false`、`all_metrics_valid=false`、`zero_vignetting=false`、`imh_field_valid=false`、`efl_constraint_held=false`、`expert_verdict=null`。实测 process return code=1、duration=`3.3910000000614673` 秒；measured EFL=`1e35`，两个 field 的 SPOTDATA rc 均为 -1、spot sentinel=-1000、RMSWE=-1。第二场四 V 精确保留 `(-0.5, 0.5, -0.5, 0.5)`，但 listing 有 84 条 ERROR，包括 7 个未加引号的数字/private glass catalog 错误与大量 `Ray missed surface 2`。禁止把该包称为 pilot PASS，也禁止在完成只读根因定位前盲目重跑或启动 48-run matrix。
- e5 根因已由 accepted/source/macro/listing 的只读字节链闭合：accepted 的 7 行 `GLAS ___BLANK` 全部丢成 `vd=0`，官方宏按 `floor(1e6*(nd-1)) + vd/100` 生成整数玻璃值，CODE V 将其解释为未加引号的目录玻璃而拒绝。e6 也为 7/7 `vd=0`，不能作为替代 pilot；Stage B 原 source 的 vd 原本为正，说明 Stage B 内存态成功不能证明 emitted accepted artifact 可被 Stage C 重导入。
- 第二个 pilot 使用 pre-run-bound `US9557532B2`，receipt SHA256=`9efdcbbbe59507f4c9abb437392ba70f67ae221528004103e1daef03731c9226`。RIH 三个 chief ray、EFL、目标 IMH 与非零四 V profile 均闭合；但 listing 有边缘 ray miss/TIR，轴上 SPOTDATA=0 而两个非零场 SPOTDATA=-1，三场 RMSWE=-1，故 `image_height_achieved=false`。该结果验证了非零 V 的符号/幅值和 RIH 几何路径，也诚实证明该设计像质读数 blocked。
- 第三个 pilot 使用更简单、零渐晕且 Stage B ray-clean 的 pre-run-bound `US9651759B2`，receipt SHA256=`ffb4366d4aac79484cb717b9153c7307a8d851764ebb596907739b10f506ccf2`。RIH chief ray、EFL、IMH 与零渐晕 profile 均闭合，轴上和半场 SPOTDATA 有效，但全场 SPOTDATA=-1、三场 RMSWE=-1，故仍为 `image_height_achieved=false`。三次 pilot 均为不同 seed 的单次真实调用，不存在同 seed 盲目重跑；每次前后 runner/uv/python/CODE V/codevm 与 matrix/P18/CODE V owner 均归零。

## Stage C 8×3×2 real-machine matrix — 2026-07-13

- 独立 pilot gate 审查结论 PASS，含义仅为执行器、parser 与 receipt 能在 RIH 下诚实记录有效值和 sentinel；三份 pilot 仍全部是光学 blocked。审查认为继续逐颗寻找“全绿 pilot”会造成选择性挑样，固定矩阵才是应保留的分布证据。
- root 在进程/owner 全零后，不带任何 recovery 参数运行冻结 plan；runner exit code=0、stderr 为空，48/48 次均生成独立 attested receipt。首次报告 SHA256=`3eb0e38e44eef5f7223c70f6956c5de0f7d5fe513656a716b2746a05f8440aa4`，后续独立终审发现它把 blocked receipt 的 sentinel 混入统计，故仅保留为 incident evidence、不得发布；`matrix-state.json` SHA256=`dfb5da3779f7f8052a63fa63703e082ca3e902d616475a3047705e892a7e19aa`，stdout SHA256=`1b287fb825eca98fcc1f5cef09542c5b632f2c2f9ac085fdc032b4160fab06f8`，stderr 为标准空文件 SHA256=`e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`。
- 结构闭包为 8 seeds × 3 arms × 2 repeats = 48，failed/incomplete=0/0，Stage B scope 为 6 pre-run-bound + 2 retrospective，`expert_verdict=null`。root 对 48 份 receipt 全部执行公开 restore，HMAC/hash/raw/plan/cache 绑定均通过，报告与 receipt 的 run/cell/repeat/status 一一相等。
- 实测分布为 2 delivered / 46 blocked；不得称为 4.17% 良品率。唯一 delivered cell 是 pre-run-bound `US9304295B2--native-imh-reconstructed-control` 的 repeat 1/2，receipt SHA256 分别为 `f0135dc4af191653228c14e6bb12716d67688bde82217a8a1bef9877c1ba0f75` 与 `d66396f6f42dea2bfaa8ee7c81e3a64da66e41a644f335de8abce6dcce7ab5f4`；两次 spot `[4.0783589555565, 80.396441145456, 6.5485815440727] µm`、WFE `[0.13229745008359, 0.24709682596261, 0.19881714629523] waves`、measured EFL `3.5589570634304 mm` 完全重复，时长分别 `2.265999999945052` 与 `2.25` 秒。
- `US9304295B2` 的 target-low/high 与其余全部 cell 仍诚实 blocked。矩阵只授权把 US930/native 的 EFL=`3.558938281682459`、IMH=`2.91297`、F/2.5 作为 production same-source 的选择依据；矩阵 receipt/schema/8-entry manifest 不能冒充 production-target，生产必须 fresh Stage B pre-run authority 与 fresh 单-cell production receipt。

## Production same-source 与 export — 2026-07-13

- production requirement 固定 smartphone-wide / EFL=`3.558938281682459` / IMH=`2.91297` / F/2.5 / 6 elements；FOV 不硬填 78.6，而由 EFL+IMH 严格派生为 `78.60024620364187°`。显式同时传 78.6 与 IMH 会被 resolver 以 `0.000246203641879°` 冲突 fail-closed，故没有用四舍五入值伪装一致。
- normal C1 `--n 1 --repeat-runs 1` 在全新 `D:\atelier-stagec-runs\stagec-production-20260713` 运行；路由唯一选择 `US9304295B2`，fresh Stage B authority attempt=`6b70df21fd6541cb81ff63301fddec49`，manifest 为 1/1、`complete=true`、scope=`pre-run-bound`、`expert_verdict=null`。intent/raw/derived manifest 继续绑定 official toolchain 与全部参数；fresh accepted ZMX SHA256=`5c438b3e56845888017cf90f600a5c4509b71dddb6619532f113a9d195ab57b9`，F/2.5 四条件与 accepted_final 均闭合。
- 外层 C1 CLI exit code=1，原因仅是 FOV 未显式提供时 Mode1 RetrievalGenerator 按其检索契约报错；该错误被隔离并如实写入 summary note。不得称“全 orchestrator 成功”。独立严格重建报告确认唯一候选实际是 ranked `target-converged` 的 US930，fresh Stage B 与 fresh Stage C 均完成；没有因外层 `[FAIL]` 盲目重跑 CODE V。
- fresh production receipt 为 `C:\Users\Administrator\.atelier\stagec-runs\stagec_20260713T041603Z_47d3b72fd1\post-run-receipt.json`，SHA256=`e7ffd0b7d68741fe3ae4f306cc3f7febd963696f4a3232e5d4cde45cefe10b18`。arm=`production-target`、cache=`pre-run-bound`、`image_height_achieved=true`、三场 ray/metrics/V/IMH/EFL gates 全真、`expert_verdict=null`；reconstructed/delivered candidate SHA256=`3a445ec1d063553a3c8c83675cd75cd54392cd4b20e7b49ce9ae11a88b2e09e8`，spot 与 WFE 与矩阵 native repeat 完全相同。
- 第一版 export 字节链本身通过，但独立终审发现 README 仍声称 chief-ray/RSI “pending machine verification”，与同页 attested-valid 证据矛盾。旧 `exports/` 保留为审查事故证据；源码已改为真实边界：Stage B optimizer replay 未编码 Stage C FTYP3/YFLN，精确已执行 sequence 已保留为 `stagec-evidence/stagec.seq`，因此只 withholding Stage-B-only `reproduction.seq`。对应 export 测试为 31 passed、1 deselected。
- 原始生产报告也保留一项不可改写的 free-text incident：`reports/report_01.json` SHA256=`83d7255f28e15a4e1bf50162ec3e34149ba6ac1f5de203636aca89f434a01564` 与 `report_01.md` SHA256=`f00220dd63d9bd22a47454ce9e4f6d14bde5695ff980ade4f814b92919519d60` 的 generation note 仍写“IMH/FOV Stage C 场重建未落地”，却与同报告的 attested-machine、`image_height_achieved=true` 矛盾。两文件保留为原始运行来源/审查事故，不重写、不重签，也不得作为当前语义发布依据；源码现已改为“IMH 可由 Stage C RIH/receipt 验证 achieved 但不是 Stage B converged；FOV derived/measured-only”，并有回归。publishable `exports-v2` ZIP/XLSX 逐 entry 搜索该旧短语均为 0 hit。
- 修正后的 `exports-v2/export-manifest.json` SHA256=`de2af28a70827d77cea4fddea7ef5f56a7c832febc3aacf7e67be4f9c7199d04`；workbook SHA256=`102994106800eeecc105f242ce8366f3703c351162624b01d1412720f4617351`，Calibri、Summary/Candidates 两页、0 formulas、0 formula-error cells；bundle SHA256=`88197068db356b4cc26f2bda06726989d6d5d5c92de0993c738501f3f0bb0f64`，无 REJECTION，`candidate.zmx` 与 `stagec-evidence/reconstructed.zmx` 字节相等，完整包含 17 项 canonical attested package。该闭环仅证明这一个 exact target 的本机同源证据，不是良品率、qualification、量产可用或 `[EXPERT]` 背书。

## Final P1 hardening 与离线重聚合 — 2026-07-13

- 独立全量 diff 终审识别并修复四项 P1：未证明 reap 的 CODE V child 现在先把 lock owner 单向 handoff 给 stale gate，quarantine 的 JSON/write/fsync/replace 任一点失败均保留原 owner；matrix 对完整 receipt-last `.inflight` 只做安全 publish + public restore，对 final/inflight/quarantine 冲突或不完整证据在任何新调用前 fail-closed；Stage C executable identity 在紧邻 launch 才建立，Windows 用 `CreateFileW(GENERIC_READ, FILE_SHARE_READ)` 的同一 share-deny handle 覆盖 launch→全局锁→Popen→process exit，并由同一 fd 做 pre/post SHA/size、同一路径做精确四段 version，任一 pin/drift 均在 receipt 前 fail-closed；公共 `run_batch()` 对任何需要 CODE V global window 的 engine 在锁/账本前拒绝 `job_timeout_sec`，防止不可停止的 worker 在 window 释放后成为孤儿真机调用。
- Stage C restore 对 retained command/current trusted executable/owner work directory 改用无文件系统访问的 Windows drive+casefold / POSIX 语法路径比较，现有 48 matrix receipts 与 production receipt 全部纯离线 restore：48 unique runs、2 delivered；production `receipt_attested=true`、`image_height_achieved=true`、`expert_verdict=null`。Windows share-deny 负测在本机非 skip，write/unlink/replace 均被 OS 拒绝；重建后替换 exe 的负测证明 runner 0 调用。该补丁后没有再启动真实 CODE V；下一次真机调用仍须从 official gate 开始，任何 loader/version 不兼容只允许 receipt 前 fail-closed。
- matrix SPOTDATA/RMSWE 聚合只接受所有字段 return 成功且数值 finite、positive 的 receipt；sentinel/invalid run 在报告中为 `null/unavailable`，0/1 个有效 repeat 不给 spread，partial/unavailable 不与 native 计算 delta/pct。首次有缺陷的 plan/state/report/md 已逐字节保存在 `D:\atelier-stagec-runs\stagec-real-matrix-20260713\historical-pre-sentinel-stats-fix`；其中旧 report/json SHA256=`3eb0e38e44eef5f7223c70f6956c5de0f7d5fe513656a716b2746a05f8440aa4`、旧 report/md SHA256=`c7b786724e5f1e716452accc1ddcaf9c81f9a9ce6a8a399bd9d0961bade11925`。
- root 在相关 Python/uv、CODE V/codevm 与 owner 全零后，用原冻结命令且不带 recovery 参数做一次离线重聚合；命令只 restore 已存在的 48 份 receipt，4.1 秒结束，未新增 attempt/run、未启动 CODE V。plan SHA256 仍为 `fa7aa3105ff756ca146699467a27224e899dd8aa58e7ef9e1df735e1c25a1ba1`，state SHA256 仍为 `dfb5da3779f7f8052a63fa63703e082ca3e902d616475a3047705e892a7e19aa`，仍是 48 attempts / 48 runs / 48 unique run IDs / 48 unique receipt hashes / failed=0 / incomplete=0。修正后的 publishable `matrix-report.json` SHA256=`36759d97bdd6860a47df39ad494e84774dc1ed7d7200e71b872e6b028c22baf8`，`matrix-report.md` SHA256=`1cda840291168b9f9354def55b858463e2cfc59d0f41ff07af1c13c003d4addb`；2 delivered / 46 blocked 不变，6/48 run 的 spot/WFE 可用，3/24 cell complete，21/24 unavailable，report invariants PASS。
- 最终 current-diff 变更面离线回归为 587 passed / 35 deselected；另完整执行 `test_stagec_attested.py` 88 passed，以及 `test_batch_runner.py + test_orchestration_generators.py + test_p16_stagec_real_matrix.py` 的全部 non-real-machine 节点 122 passed / 1 deselected，覆盖名字含 `real` 但纯离线的回归。机械格式化后再跑受影响四文件为 139 passed / 9 deselected。Ruff check 38 files、Ruff format 32 个应格式化文件、py_compile 38 files、import smoke 15 modules、`git diff --check` 均 PASS。6 个历史 marker/integration 文件仍是 pre-existing format drift，未制造无关重排；export v3 集成夹具的旧 version 常量已改为共享精确 pin并单测通过。额外一次全仓 `pytest -m not real_machine -k not real` 在 304 秒工具上限被终止，未产出成功或失败结论，故不计入 PASS；终止后 pytest/uv/CODE V/codevm 与 owner 全零，完整仓库真值仍由 PR CI 决定。
