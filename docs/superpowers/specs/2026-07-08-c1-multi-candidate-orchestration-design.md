# C1 多产编排 + 良品率 Scorecard — 设计文档

- **日期**：2026-07-08
- **状态**：设计定稿（attended 四段认可，待主公复审 → 转实施）
- **里程碑**：Phase 10 探路阶 · 第一里程碑
- **北极星语境**：量产设计产出引擎（生成-验证分工）——AI 批量产候选，资深设计师快速筛判"哪些合格/可用"；良品率 = go/no-go 闸。**可信度不可失守**：AI 只多产不越权定夺，良品率判断权在资深（[EXPERT] 红线）。
- **基线仓库版本**：origin/main = `000ef97`（案例库 343；含 PR#43 长焦 404 修复=multi-tier classify；分支 `data/09efg-353-intake`=353 待 rebase 合）

---

## 1. 背景与动机

产品当前本质是"手机主摄智能选型 + 专业呈现引擎"（检索 + 呈现），不是"设计引擎"。北极星转向后，C1 = **给定客户需求 → 用现有引擎批量产 N 个候选 + 量化 scorecard**，为资深筛判备料。

**核心张力（③优化落地未解）**：真正"朝客户 target 收敛的优化"（③）尚未落地，且是 CODE V 硬依赖的引擎级活（6 接缝，见 §10），由主公另开专门 attended session 啃。因此 C1 **不能碰 ③**，只能把"候选生成"做成**可插拔**，并对每颗候选**诚实标注生成模式**——绝不把检索来的 seed 伪装成"优化到 target 的设计"。

**决定 C1 可现在建的事实**（探子代码核实，§11）：
- 检索侧已内部产 4 个角色分化候选（`case_library.py:1511-1545`），只差暴露成 list；
- scorecard 原料大半已真算（MTF/点列/波前/场曲/畸变）；
- 缺 RI（补 compute，非新引擎）。

## 2. 本次 attended 定的决策

| 决策点 | 结论 |
|---|---|
| **范围** | 可插拔编排 harness（**Mode1 现建**；Mode2 第一里程碑不实现，见 §6.3；Mode3 留插槽给 ③）。良品率先作 baseline floor，③ 落地后 Mode3 插入触发真 go/no-go。C1 与 ③ 并行不阻塞。 |
| **判定边界** | AI 只出**量化 scorecard + 建议排序**，**不下"合格/良品"判定**。良品率由资深看报告人工判（[EXPERT] 红线）。 |
| **架构** | 方案 A：独立编排模块 `app/core/orchestration/` + 离线 batch 报告优先，API/Web 后置（避免 ahead-of-consumer）。 |

## 3. 目标与非目标

**目标**：
- 给定需求 → N 个角色分化候选 + 每颗量化 scorecard + 诚实 provenance + 建议排序。
- 离线 batch 脚本产 scorecard 报告（Markdown + JSON）供资深离线筛。
- 补 RI 计算（三铲之一）。
- 为 ③（Mode3）留清晰接口锚。

**非目标（YAGNI）**：
- ❌ 不做 ③优化落地（主公专门 session）。
- ❌ 不做真公差良率（C2 = CODE V TOR，数周工程，仅 proxy 占位）。
- ❌ 不做 API/Web 界面（等资深用过报告反馈再定）。
- ❌ 不下良品合格判定（红线）。
- ❌ **不实现 Mode2 且不预留 `SEED_REFINED` 枚举**（现有 `protected_efl_refinement` 是"仅 EFL 维朝 target"，与全局 `converged_toward_target` 模型矛盾；将来若需 Mode2 须先设计 per-field 收敛表，见 §6.3，codex 轮3）。
- ❌ 不重复长焦 404 修复（已由 **PR#43** 合入 main = multi-tier classify；telephoto 现可路由 → Mode1 检索**利好**，`case_library.py` 分类锚以最新代码为准）。

## 4. 架构总览与模块布局

```
app/core/orchestration/
  __init__.py
  candidate.py      # GeneratedCandidate / ScoredCandidate / CandidateSet / ScorecardRow（Pydantic）
  generators.py     # CandidateGenerator 抽象 + Retrieval / TargetConverged(空插槽)（Mode2 不实现）
  scorecard.py      # 纯函数 score_candidate(generated, target) -> ScorecardRow
  orchestrator.py   # orchestrate(spec, target, *, n, modes) -> CandidateSet
app/core/relative_illumination.py   # RI 补算（供 scorecard 调）
scripts/c1_orchestrate.py           # 离线 batch：需求集 → CandidateSet → scorecard 报告(MD+JSON)
tests/test_orchestration_candidate.py
tests/test_orchestration_generators.py
tests/test_orchestration_scorecard.py
tests/test_orchestration_orchestrator.py
tests/test_relative_illumination.py
```

**数据流**：

```
spec(客户需求) + target(EFL/FOV/F#/IMH/TTL…)
  → orchestrator.orchestrate(spec, target, n, modes)
      ├─ RetrievalGenerator(Mode1)      ──复用──▶ rank_seeds 共享 ranking helper(§6.2)
      └─ TargetConvergedGenerator(Mode3) ─空插槽▶ ③落地后填
      （Mode2/SeedRefineGenerator 不在 registry/枚举/数据流出现；仅 §6.3 记为未来议题）
      每 generator 产 GeneratedCandidate（无 scorecard）
      → score_candidate(generated, target) 产 ScorecardRow（纯量化，无 pass/fail）
      → 组装 ScoredCandidate（generated+scorecard）+ 建议排序(可用维加权，可解释)
  → CandidateSet{ candidates: list[ScoredCandidate], modes_present(派生), honesty_banner(派生), summary }
  → scripts/c1_orchestrate.py 渲染离线 scorecard 报告(Markdown + JSON)
```

**deep-module 原则**：每 generator 一个清晰接口、隔离可独立测试；`scorecard` 纯函数无副作用可复用；`RetrievalGenerator` **复用不重写** `case_library`（唯一真相源，避免双份候选逻辑 drift）。

## 5. 数据模型 + provenance 诚实不变量

### 5.1 GenerationMode（provenance 核心，每颗候选必带）

```python
class GenerationMode(StrEnum):
    RETRIEVED        = "retrieved"         # Mode1 检索现成 seed，零优化
    TARGET_CONVERGED = "target-converged"  # Mode3 ③落地后真朝客户 target 收敛
    # 注（codex 轮3）：不预留 SEED_REFINED。现有 protected_efl_refinement 是"仅 EFL 维朝 target"，
    #   与全局 converged_toward_target(bool) 矛盾（逼后续实现失败或撒谎）。将来若需 Mode2，
    #   须先把 converged 改 per-field 策略表再引入枚举——见 §6.3，届时另设计，不在此预埋矛盾。
```

### 5.2 GeneratedCandidate → ScoredCandidate（两阶段 · codex 轮2 修正）

**codex 轮2 修正**：原 `Candidate` 把 `scorecard` 设必填、但 scorecard 是对候选打分才产生的——契约**成环**（无法构造有效 Candidate）。拆两阶段打破环：

```python
# 阶段一：generator 输出（无 scorecard）
class GeneratedCandidate(BaseModel):
    candidate_id: str
    mode: GenerationMode          # 必填，由 generator 构造时钉死
    source_case_id: str | None    # 检索来源 seed
    payload: OpticalSampleData    # 复用现有统一 payload（光路/MTF/点列/波前/…）
    optical_extras: OpticalExtras # generator 阶段用 optic 算的、payload 缺失的量（RI 等）
    generation_notes: list[str]   # 诚实注记，如 "检索最近邻 seed，未朝 target 优化"

    @property
    def is_target_converged(self) -> bool:   # 派生只读，不可单独伪造
        return self.mode is GenerationMode.TARGET_CONVERGED

# 每个 mode 实际朝 target 优化/收敛的 field 集合（per-field provenance · codex 轮5）
CONVERGED_FIELDS: dict[GenerationMode, frozenset[str]] = {
    GenerationMode.RETRIEVED:        frozenset(),                               # 检索不优化任何维
    GenerationMode.TARGET_CONVERGED: frozenset({"efl", "fnum", "imh", "fov"}),  # = §10 Mode3 六接缝优化维；TTL 不在接缝
}

# 阶段二：打分后的最终候选（CandidateSet 消费此型）
class ScoredCandidate(BaseModel):
    generated: GeneratedCandidate
    scorecard: ScorecardRow

    @model_validator(mode="after")
    def _enforce_consistency(self):          # raise 非 assert
        if self.scorecard.mode is not self.generated.mode:
            raise ValueError("scorecard.mode != generated.mode")
        conv = CONVERGED_FIELDS[self.generated.mode]     # per-field，非全局 bool
        for dev in self.scorecard.target_deviations:
            if dev.converged_toward_target != (dev.field in conv):
                raise ValueError(
                    f"{dev.field} converged 与 mode {self.generated.mode} 优化维不一致"
                )
        return self

    @property
    def mode(self) -> GenerationMode:
        return self.generated.mode
```

> `OpticalExtras` 承载 generator 阶段（有 optic）算出、但现有 `OpticalSampleData` payload 里没有的量（首要是 RI；见 §7-D）。`score_candidate(generated, target)` 纯函数只消费 `generated.payload + generated.optical_extras`，不自行触碰 optic。

### 5.3 ScorecardRow（纯量化，无 pass/fail 字段）

```python
class TargetDeviation(BaseModel):
    field: str                        # efl/fov/fnum/imh/ttl
    constraint_kind: Literal["exact", "ceiling", "floor", "unconstrained"]
    target: float | None              # exact=目标值 / ceiling=上限 / floor=下限 / unconstrained=None
    achieved: float
    violation: float                  # exact:|a-t| ; ceiling:max(0,a-limit) ; floor:max(0,limit-a) ; unconstr:0
    rel_violation: float | None       # violation/|target|（unconstrained=None）
    converged_toward_target: bool     # per-field：field ∈ CONVERGED_FIELDS[mode]（§5.2）

class ScorecardRow(BaseModel):
    candidate_id: str
    mode: GenerationMode              # 每行都带 provenance
    target_deviations: list[TargetDeviation]   # EFL/FOV/F#/IMH/TTL
    image_quality: ImageQualityMetrics
    manufacturability: ManufacturabilityProxy
    rank: RankResult                  # 带 coverage 的排序结果（非裸 float，codex 轮3）
    rank_explanation: str
    # ↑ 无 verdict / 合格 / passed 字段

class RankResult(BaseModel):
    score: float | None               # coverage 不足 → None（withheld）
    status: Literal["ranked", "withheld"]
    coverage_pct: float               # 可用必需维 / 必需维总数
    missing_metrics: list[str]        # 缺失维名（报告透明）
```

> **codex 轮1+2+5 修正**：一致性校验（`scorecard.mode == generated.mode`、每个 `converged_toward_target == (field ∈ CONVERGED_FIELDS[mode])` per-field）在 §5.2 `ScoredCandidate` validator 做（`raise` 非 `assert`）。`TargetDeviation` 带 `constraint_kind`——**TTL/mass 是 ceiling**（低于上限 `violation=0` 不罚，`case_library.py:1466-1471`），EFL/FOV/F#/IMH 是 exact，避免"短 TTL 被当偏离扣分"。像质每 metric 用 `MetricValue{value, status}`，RI 缺失 → unavailable（fail closed，§7-D/E）。

### 5.4 CandidateSet

```python
NO_TARGET_CONVERGED_BANNER = (
    "本批候选均未朝客户 target 收敛（③/Mode3 未接），scorecard 偏差为检索基线，"
    "非量产设计引擎真实产能，良品率仅供参考基线。"
)

class CandidateSet(BaseModel):
    target: TargetSpec
    candidates: list[ScoredCandidate] # 已按 rank 排序
    summary: CandidateSetSummary

    @computed_field   # 派生，不接受外部传入 —— 调用方无法塞 TARGET_CONVERGED 跳过 banner
    @property
    def modes_present(self) -> set[GenerationMode]:
        return {c.mode for c in self.candidates}

    @computed_field   # 派生固定文本，不可伪造
    @property
    def honesty_banner(self) -> str | None:
        if GenerationMode.TARGET_CONVERGED not in self.modes_present:
            return NO_TARGET_CONVERGED_BANNER
        return None
```

> **codex 轮1 修正**：`modes_present`/`honesty_banner` 从 `candidates` **派生**（`computed_field`），不再是外部可传字段——堵死"调用方塞 `TARGET_CONVERGED` 跳过 banner"的绕过口子。

### 5.5 诚实不变量（类型/校验层钉死，不靠人自觉 · codex 轮1 加固）

1. **mode 钉死于 generator（运行时不可绕过）**：`generate` 是基类模板方法，标 `@final`（静态检查）**且** `__init_subclass__` 在子类 `__dict__` 出现 `generate` 时 `raise TypeError`（运行时防覆盖——Python 无真 final，仅约定不够）；`generate` 返回前用显式 `raise ValueError` 校验每颗 `mode == cls.mode`（非 `assert`）。只有 Mode3 generator 能产 `TARGET_CONVERGED`。检索 seed 无法被标成"优化到 target"。
2. **无 pass/fail 字段**：`ScorecardRow` 无合格判定字段，AI 越权代判也无处可写。良品判断只能是资深人工动作。
3. **honesty_banner 派生强制**：`CandidateSet.modes_present` 与 `honesty_banner` 均为 `computed_field`（从 `candidates` 派生、调用方不可传入）；整批不含 `TARGET_CONVERGED` 时 `honesty_banner` 自动返回固定常量 `NO_TARGET_CONVERGED_BANNER`。
4. **mode 一致校验（per-field · codex 轮5）**：`scorecard.mode == generated.mode`、每个 `converged_toward_target == (field ∈ CONVERGED_FIELDS[mode])` 由 §5.2 `ScoredCandidate` validator `raise` 校验（TARGET_CONVERGED 只对实际优化维标收敛，TTL 等未优化维恒 false）。

## 6. Generator 契约

### 6.1 抽象基类

```python
from typing import final

class CandidateGenerator(ABC):
    mode: ClassVar[GenerationMode]

    def __init_subclass__(cls, **kw):        # 运行时防覆盖 generate（Python 无真 final）
        super().__init_subclass__(**kw)
        if "generate" in cls.__dict__:
            raise TypeError(f"{cls.__name__} 不得覆盖 final 方法 generate；请实现 _generate")

    @abstractmethod
    def _generate(self, spec, target, *, n) -> list[GeneratedCandidate]: ...   # 子类只实现这个

    @final                                    # 静态检查器拦覆盖
    def generate(self, spec, target, *, n) -> list[GeneratedCandidate]:
        candidates = self._generate(spec, target, n=n)
        for c in candidates:
            if c.mode is not type(self).mode:                    # 显式 raise，-O 下不消失
                raise ValueError(
                    f"{type(self).__name__} 产出 mode={c.mode} != 声明 {type(self).mode}"
                )
        return candidates
```

> **codex 轮1+2 修正**：`generate` 返回 `GeneratedCandidate`（无 scorecard，打破契约成环，见 §5.2）；`@final`（静态检查）**加** `__init_subclass__`（运行时拦子类覆盖）双保险——Python 普通方法无运行时 final 语义，仅注释拦不住覆盖绕过；mode 校验用 `raise ValueError` 非 `assert`。

### 6.2 RetrievalGenerator（Mode1，第一里程碑主力）

**codex 轮2 修正**：现有排序/距离/role 选择嵌在 `match_case` 局部逻辑里、候选被 `selected_candidates[:4]` 硬截断——"加薄只读入口"太乐观（会在"复制排序=drift"与"抓 4 副产品=无法 N>4"间二选一）。正确做法：

- **先抽共享 ranking helper**：把 `match_case` 内排序/距离/role 选择抽成纯函数 `rank_seeds(spec) -> list[RankedCase(case_id, distance, score, role, distance_parts)]`（返回**全部** ranked、不截断）；`match_case` 与 `RetrievalGenerator` **同消费**它（唯一真相源，杜绝双份 drift）。
- `RetrievalGenerator` 取 `rank_seeds(spec)[:n]`，对每 case_id 组装 `GeneratedCandidate(mode=RETRIEVED)`。
- 角色语义沿用：best_match / cost_variant / thin_variant / performance_variant / nearby_alternative_N。
- **测试断言**：top-4 与现有 `candidate_comparison` 一致（重构不改行为）；N>4 有稳定 `nearby_alternative_N`。
- **无 CODE V 依赖**（检索 + Optiland）。

### 6.3 SeedRefineGenerator（Mode2）——**第一里程碑不实现，不预留枚举**

**codex 轮1 亲验**：仓库实际函数是 `protected_efl_refinement`（`local_optimizer.py:3974`），operand `f2 target=target_efl_mm`（`:4072-4077`）、调用传用户 `efl_mm`（`case_library.py:3907-3911`）、docstring "improves the target miss"——即 **仅 EFL 一维、radius ±5% 受保护微调、朝客户 target 收敛**（seed payload 不 mutate，`applied_to_payload=False`），语义**介于检索与 target-converged 之间**（部分朝 target：只 EFL）。

**决定（codex 轮3 收紧）**：第一里程碑**不实现** SeedRefineGenerator，且**不预留 `SEED_REFINED` 枚举**——它的"仅 EFL 维朝 target"与全局 `converged_toward_target`(bool) 模型**矛盾**（会逼后续实现要么失败要么撒谎）。harness M1 = **Mode1（RetrievalGenerator）+ Mode3 空插槽**，`GenerationMode` 只有 `RETRIEVED` 与 `TARGET_CONVERGED`，无矛盾。

> 将来若需 Mode2：**先**把 `converged_toward_target` 改成 **per-field 收敛策略表**（RETRIEVED 全 false、SEED_REFINED 仅 efl true、TARGET_CONVERGED 按实际优化维），**再**引入枚举——届时另设计，不在本 spec 预埋矛盾锚。

### 6.4 TargetConvergedGenerator（Mode3，空插槽 = ③ 接口锚）

- 第一里程碑：`_generate` 返回 `[]` + 记录 `"Mode3 未接：需 ③优化落地"`，orchestrator 跳过 → 触发 honesty_banner。
- **docstring 写死 ③ 接入契约**（= §10 六接缝），作主公 ③ session 的接口锚。
- **③ 依赖 CODE V（硬）**，未接时跳过——不破坏无 CODE V 降级。

## 7. Scorecard 度量口径

`score_candidate(candidate, target) -> ScorecardRow` 是**纯函数**，只从 `candidate.payload` 与 `candidate.optical_extras`（generator 预算的 RI 等）消费，不自行触碰 optic/ZMX。

**A. Target 偏差**（5 维）：从 payload 提 achieved（EFL/F#/TTL ← `paraxial`；IMH ← `metadata`；FOV ← 优先 `metadata.fov_deg`（`optical_sample.py:32`），缺则由 EFL+IMH 反算）。按 `constraint_kind` 算 `violation`：**exact**（EFL/FOV/F#/IMH）`|achieved−target|`；**ceiling**（TTL/mass）`max(0, achieved−上限)`——低于上限 `violation=0` 不罚（`case_library.py:1466-1471`）；**unconstrained**（target=None）不计入。`converged_toward_target` 由 `field ∈ CONVERGED_FIELDS[mode]` **per-field** 派生（§5.2）。

**B. 像质摘要 `ImageQualityMetrics`**（全取现有真算度量）：
- MTF：代表频率点（复用 `MTFResult` 频率栅格）× 视场 {0, 0.5, 0.8, 1.0} 的 sag/tan + 衍射截止 lp/mm
- RMS 点列 per-field（max & mean, µm）
- 波前：min Strehl / RMS OPD(waves)
- 场曲：tangential/sagittal 峰值 delta
- 畸变：最大畸变 %
- RI：见 D

**C. 可制造性 proxy `ManufacturabilityProxy`**（`is_proxy=True` 硬标）：TTL / 片数 / 玻璃类型(普通 vs 特殊高折射) / 非球面复杂度(项数·面数) / CRA(主光线角·传感器匹配，几何可算)。强制 `note="非真公差良率(无 Monte-Carlo/补偿器/TOR，C2=CODE V 未接)，仅几何+材料 proxy"`。

**D. RI（相对照度）**（`app/core/relative_illumination.py`）：`RI(field) = cos⁴θ × 边缘光束渐晕因子`。**codex 轮1 修正**：payload/`RayTraceResult` 只有 `has_vignetting` bool（`lens_system.py:240`）、**无持久化渐晕系数**——RI 须在 **generator 阶段用 optic 对象**（复用/重建 optic 光追）计算，存入 `candidate.optical_extras.ri`，`score_candidate` 纯函数从此消费。能力仍是现有渐晕+光追（**非新引擎**），只是 compute 位置在有 optic 的 generator、不是 payload 纯提取。缺 optic/算不出时 **fail closed**（`ri=None` + 标 `unavailable`，不猜、不静默降级）。

**E. 排序 `RankResult`（建议排序 ≠ 合格判定 · codex 轮2+3 精化）**：
- 每 metric 用 `MetricValue{value, status: available|unavailable}`；unavailable 不参与加权、不填默认值。
- **必需维 + coverage gate（codex 轮3+4 fail-closed）**：必需维 = 像质的 {MTF}（恒必需）+ **受约束的** target 维中的 {EFL, FOV}（`target=None` 的维**不算必需、不进 denominator**——闭合 target=None 语义）。`coverage_pct = 可用必需维 / 必需维总数`。**应有却 unavailable 的必需维存在 或 coverage_pct < 阈值(默认 0.8) → `status="withheld"`、`score=None`**（杜绝稀疏数据高分假象）；`missing_metrics` 列缺失维。（例：EFL `target=None` 但 FOV+MTF 可用 → `ranked`；MTF unavailable → `withheld`。）
- **target 偏差归一化**：每维 `norm = min(rel_violation / tol_field, 1.0)`（tol：EFL/FOV/IMH/TTL 5% · F# 8%，可配）；ceiling 维低于上限 `rel_violation=0 → norm=0`（**不罚短 TTL**）；`target=None`/unconstrained 维不计入。
- 达 coverage 时 `score = w_dev·(1−mean(可用 norm)) + w_iq·mean(可用像质归一)`（默认 w 各 0.5；分母只计 available）。
- **RI 缺失**：`ri.status=unavailable` → 不入 w_iq、报告标 "RI unavailable(N/M)"；整批 RI 全缺 → 报告级醒目告警。
- 报告对每候选输出 `score`(或 withheld) + `coverage_pct` + `missing_metrics`。**独立于**检索距离。排第一 ≠ 合格。

## 8. 降级能力（CLAUDE.md 硬约束）

第一里程碑 = **Mode1（RetrievalGenerator）only**（Mode2 不实现，见 §6.3），**全程无 CODE V 依赖，CI 绿**。Mode3/CODE V 是 ③ 落地后增强；缺失时 harness 照常出检索基线 scorecard + honesty_banner。

## 9. 测试策略

- **单测**：每 generator、scorecard 纯函数、orchestrator、RI 计算。
- **诚实不变量测试**（可信度承重）：
  - `_generate` 产 `mode=TARGET_CONVERGED` → `generate` `raise ValueError`（并验证 `python -O` 下仍 raise）；
  - **子类定义 `generate` → `__init_subclass__` `raise TypeError`**（覆盖绕过路径，轮2 补）；
  - `CandidateSet` 全 `RETRIEVED` → `honesty_banner` 自动为 `NO_TARGET_CONVERGED_BANNER`（派生、无法置空）；
  - `ScoredCandidate` 中 `scorecard.mode != generated.mode` → validator `raise`；
  - `ScorecardRow` 无合格字段（结构断言）。
- **rank helper 一致性**（轮2 补）：`rank_seeds` top-4 == 现有 `candidate_comparison`（重构不改行为）；N>4 稳定。
- **约束方向 + rank 覆盖/RI 边界**（轮2-5 补）：**TTL ceiling**（短 TTL `violation=0` 不罚、超上限才罚）；**per-field converged**（RETRIEVED 全维 false；TARGET_CONVERGED 仅 efl/fov/fnum/imh=true 而 **ttl=false** → §5.2 validator 校验）；应有必需维 unavailable → `withheld`；EFL `target=None` 但 FOV+MTF 可用 → `ranked`；MTF unavailable → `withheld`；RI 缺失、极端偏差、整批 RI 全缺（报告告警）等路径。
- **降级测试**：无 CODE V 跑通 Mode1，全链路绿。
- **RI 数值锚**：已知渐晕系数 seed → RI 边缘值交叉验证（防假绿）。
- **@accept 锚**（夜车切片用）：每切片挂确定性验收命令，如 `test -f <report> && pytest tests/test_orchestration_*.py`。

## 10. Mode3 接口锚（③ 六接缝 · file:line）

接入 Mode3 需 ③ 落地（`codev_optimize.py`，主公专门 session）：

> **Mode3 优化维 = `{EFL, F#, IMH, FOV}`**（下列 1-3 接缝对应；**TTL 不在接缝** → per-field converged 对 TTL=false，见 §5.2 `CONVERGED_FIELDS`）。将来若加 TTL 优化接缝，同步扩 `CONVERGED_FIELDS[TARGET_CONVERGED]`。

1. **EFL 解锁朝 target**：`codev_optimize.py:230` `EFL = ^baseline_efl_y_mm` → `EFL = {target_efl_mm}`
2. **玻璃可变**：`codev_optimize.py:257` `glass-not-varied` → varied；AUT 块加 `CHG GL`
3. **merit 加客户操作数**：`codev_optimize.py:200-236` 加 F#/IMH/FOV 操作数（现仅横向色差 + RMS 点列）
4. **applied_to_payload 真置 True**：`local_optimizer.py`（~9 处硬编码 False）
5. **verification checklist → 自动 apply**：`case_library.py:7080` + `:7139`（现 "not applied to delivered payload"）
6. **payload delivery 落地**：`case_library.py:14053` `delivered_candidate_id` / `:14054` `delivered_payload` 状态机

## 11. 事实锚（探子代码核实 · file:line）

**候选产出/评分**：
- `/match` 端点单候选返回：`app/api/optical.py:686-720`
- 匹配核心 `match_case`：`app/core/case_library.py:1294` 起
- 候选选择/`selected_candidates[:4]` 硬截断：`~1504-1549`；`candidate_comparison` 生成：`3790-3819`（**两锚拆开**——抽 `rank_seeds` 共享 helper 时勿按错误范围取码，§6.2）
- 权重（FOV 0.46 / IMH 0.30 / quality 0.24-0.45 …）：`app/core/case_library.py:1430-1447`
- 统一 payload `OpticalSampleData`：`app/core/optical_sample.py:1337-1352`；`CaseMetadata.fov_deg`：`optical_sample.py:32`
- 真算度量：MTF `aberration.py:121-180`、场曲/畸变 `field_analysis.py:79-150`、波前 `wavefront_metrics.py:1-150`、点列 `compute_spot_diagram spot_diagram.py:131-233`
- **RI 缺失**：payload 无渐晕系数（`RayTraceResult.has_vignetting` bool，`lens_system.py:240`），仅 checklist 文案提及（`case_library.py:4963,5200,9274,9277,9278`）→ RI 须 generator 阶段用 optic 算（§7-D）
- 长焦分类**已修**（PR#43 multi-tier classify，取代原 `case_library.py:384` FOV≥85° 二分）→ telephoto 可路由，Mode1 覆盖 telephoto scenario

**③ blocker**：见 §10。CODE V 硬依赖：`codev_optimize.py:317` `run_codev_optimize`；`codev_batch.py:19` `D:/CODEV115/codev.exe`。Optiland-only 精修（**仅 EFL 朝 target**）：`protected_efl_refinement` `local_optimizer.py:3974`（operand `f2 target=target_efl_mm` `:4072`；调用传用户 `efl_mm` `case_library.py:3907-3911`）。

## 12. 红线合规映射

| 红线 | 本设计合规点 |
|---|---|
| [EXPERT] 良品判断权在资深 | ScorecardRow 无 pass/fail 字段（不变量 2）+ 良品率人工判 |
| LLM 禁碰坐标 | 所有 generator 纯确定性（检索/Optiland/CODE V），零 LLM 参与数值 |
| 无 CODE V 全链路降级 | 第一里程碑 Mode1 only 无 CODE V，CI 绿（§8） |
| 可信度不可失守 | provenance 诚实三不变量 + honesty_banner（§5.5） |
| 不 ahead-of-consumer | 离线报告优先，Web/API 后置等资深反馈 |

## 13. 交付形态与后续路径

- **交付**：`scripts/c1_orchestrate.py` 离线 batch → scorecard 报告（MD+JSON），供资深离线筛。
- **后续实施路径**（待主公复审时定）：C1 实施是"夜车擅长、可机判"的确定性铺路，可切成 gsd-loop 夜车 backlog 切片（每切片带 @accept 锚），或 attended 逐步执行。
- **良品率 go/no-go**：Mode3（③）落地后，用同一 harness 产 target-converged 候选，请资深实测筛一遍——那时的良品率才是北极星真 go/no-go 数（[EXPERT] 红线）。

## 14. 对抗审查修订记录

**轮 1（codex adversarial-review · 2026-07-08 · verdict: needs-attention）**——4 findings，亲验代码确认后**全采纳**：
1. `[blocker]` 诚实不变量可绕过 → §5.4/§5.5/§6.1 加固：`generate` 改 concrete final 模板方法 + 只开放 `_generate`；`raise ValueError` 替 `assert`；`modes_present`/`honesty_banner` 改 `computed_field` 派生；加 `scorecard.mode==candidate.mode` 一致 validator。
2. `[major]` Mode2 语义反（实为 `protected_efl_refinement` `local_optimizer.py:3974` 朝 `target_efl_mm`）→ §6.3 第一里程碑不实现 Mode2，`SEED_REFINED` 枚举保留扩展点。
3. `[major]` scorecard 输入契约不匹配 payload → §5.2 加 `optical_extras`；§7-D RI 移 generator 阶段用 optic 算 + fail closed；FOV 字段改 `metadata.fov_deg`。
4. `[minor]` §10/§11 事实锚不准 → 全部改精确 symbol:line（`protected_efl_refinement:3974`/`fov_deg:32`/`compute_spot_diagram:131-233`/`delivered_candidate_id:14042`/RI checklist +9263/9266/9267）。

**轮 2（codex adversarial-review · 2026-07-08 · verdict: needs-attention）**——5 findings（2 blocker+2 major+1 minor），亲验后**全采纳**：
1. `[blocker]` Candidate/Scorecard 契约成环 → §5.2 拆两阶段 `GeneratedCandidate`→`score_candidate`→`ScoredCandidate`（一致性 validator 在 ScoredCandidate）。
2. `[blocker]` `generate` 可被子类覆盖（Python 无运行时 final）→ §6.1 加 `__init_subclass__` 运行时拦覆盖 + `@final` 静态；§9 补覆盖绕过测试。
3. `[major]` Mode2 残留矛盾 → §2/§5.1/§9/§12 全文清为 Mode1 only，`SEED_REFINED` 注释改。
4. `[major]` `rank_cases` 非薄入口（排序嵌 match_case + 硬截断 `[:4]`）→ §6.2 改为先抽共享 `rank_seeds` helper，match_case 与 RetrievalGenerator 同消费。
5. `[minor]` rank_score/RI fail-closed 边界未定义 → §5.3/§7-E 加 `MetricValue.status`、归一化容差、RI 缺失处理（整批缺 → 报告告警防假绿）。

**轮 3（codex adversarial-review 终审 · 2026-07-08 · 分支已 rebase 到 000ef97 · verdict: needs-attention）**——3 findings（2 major+1 minor），亲验后**全采纳**：
1. `[major]` `SEED_REFINED` 扩展点与全局 `converged_toward_target` 互锁（无法表达"仅 EFL 维收敛"）→ §5.1/§6.3/§3 **删除 SEED_REFINED 枚举**，`GenerationMode` 只留 `RETRIEVED`+`TARGET_CONVERGED`；将来 Mode2 须先设计 per-field 收敛表。
2. `[major]` rank_score 排除 unavailable 会给稀疏数据高分（非真 fail-closed）→ §5.3/§7-E 改 `RankResult{score, status, coverage_pct, missing_metrics}`：缺必需维/coverage<0.8 → `withheld`。
3. `[minor]` §10/§11 锚随 000ef97 漂移 → 按 codex 复核的实际行号更新（match_case:1294 / 权重:1430-1447 / has_vignetting:240 / delivered:14053-14054 / RI checklist:4963,5200,9274,9277,9278 / efl_mm 调用:3907-3911）。

**轮 4（codex adversarial-review · 2026-07-08 · verdict: needs-attention）**——3 findings（2 major+1 minor），均为轮3 修订的收尾残留（非新深层问题），**全采纳**：
1. `[major]` §4 数据流仍残留 SeedRefineGenerator(Mode2)"枚举保留扩展点" → 从数据流删除，明确 Mode2 不在 registry/枚举/数据流出现（仅 §6.3 记为未来议题）。
2. `[major]` RankResult coverage gate 对 `target=None` 不闭合 → §7-E 精化：必需维 = MTF + **受约束的** EFL/FOV（target=None 维不进 denominator）；§9 加 target=None ranked/withheld oracle。
3. `[minor]` §7-D RI 锚 stale（`lens_system.py:203` 实为 n_surfaces）→ 改 `:240`。

**轮 5（codex adversarial-review · 2026-07-08 · verdict: needs-attention · 1 major 新问题）**——亲验代码后**采纳**（根因修复，主公裁定）：
1. `[major]` TargetDeviation 把 TTL 当对称 target（短 TTL 被扣分）+ converged 全局 bool（Mode3 会把没优化的 TTL 标已收敛）→ **根因修复**：§5.3 `TargetDeviation` 加 `constraint_kind`(exact/ceiling/floor/unconstrained)，TTL/mass=ceiling 低于上限不罚（`case_library.py:1466-1471`）；§5.2 加 `CONVERGED_FIELDS[mode]` **per-field convergence**（TARGET_CONVERGED 只 efl/fnum/imh/fov=true，TTL=false）；§7-A/§7-E 用 `violation`/`rel_violation`；§9/§10 补 oracle 与 Mode3 优化维。一次覆盖 TTL + 未来 F#/IMH 同类。
