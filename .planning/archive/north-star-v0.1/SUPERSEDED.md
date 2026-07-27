# SUPERSEDED — 北极星 v0.1 治理协议（冻结归档）

**状态**：SUPERSEDED，冻结，不删不维护
**归档于**：2026-07-27
**取代者**：[.planning/NORTH-STAR.md](../../NORTH-STAR.md)

本目录内所有文件**不再是任何 gate、判据或工作源**。它们不消耗 loop 预算，
不进入任何 backlog，不作为任何声明的依据。保留仅供追溯。

## 废弃原因（三条，均为文件自述事实）

1. **终点吊在一个不存在的人身上。** 全套体系以资深光学设计师的 `[EXPERT]` 签字为终点。
   项目从立项（2026-07-03）到废弃（2026-07-27）从未有过这个人，`[EXPERT]` 一次都没被填过。
   Gate D 因此不是"还没做"，而是定义上不可关闭；连带 holdout 密封、盲法、rater 名单、
   角色分离机制全部失去对象——没有人可供分离。

2. **发布链吊在 GitHub 不提供的 API 原语上。** `X-00A` 要求一个
   `acquisition→snapshot→admission→terminal` 的 provider-side merge lease，覆盖全部
   policy-administration 与 `refs/heads/main` 更新面。契约自述：该原语不可得则 v0.1 永久
   `BLOCKED_WAIT_EXTERNAL`。GitHub 公开 API 无此能力。

3. **代价可测量。** 13 棵固定 commit/tree 连续被独立只读审查拒绝，最近数轮拒绝理由已是
   "某 hash 路径同时承载两种对象类型"这类协议自身自洽性问题，与光学、与产品能力无关。
   同期全仓 `.py` 文件中 `north_star` 零命中——**24 天内未落地过一行实现代码**，
   全部工作量用于撰写契约与修补其自洽性。

## 仍然有效、需要重新引入的部分

`backlog.md` 的 **M-01 ~ M-06**（CODE V 单实例锁、启动面收口、冲突监控、receipt）
反映的是**真实工程需求**——并发跑 CODE V 会真出事，这一点与 v0.1 的治理架构无关。

重新引入时的要求：**降级为普通工程 backlog 项，剥离其密码学签名链、外部证明者、
attester allowlist 与 CAS 收据链**。需要的是一把可靠的锁，不是一套可证明的锁。

## 数值真相（归档时刻，仅供追溯）

- 北极星 gate `A–F` 全部 `false`
- `[EXPERT]` 与两个专家率 unavailable
- 人类选择项 109 个，全部 `null`
- P18：50 targets，29 succeeded / 21 degraded / 0 failed（exploratory）
- Stage B：8/8 unique accepted，`expert_verdict=null`
- Stage C：48 receipts，2 delivered / 46 blocked，6/48 run metrics usable
- 全链跑通的 exact target：1 个（`US9304295B2`）

这些数字在 v2 体系下**不自动继承任何含义**，重新计量须按 NORTH-STAR.md 的判据口径。
