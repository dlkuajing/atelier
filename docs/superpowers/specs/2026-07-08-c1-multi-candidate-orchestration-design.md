# C1 多产编排 + 良品率 Scorecard — 设计文档

- **日期**：2026-07-08
- **状态**：设计定稿（attended 四段认可，待主公复审 → 转实施）
- **里程碑**：Phase 10 探路阶 · 第一里程碑
- **北极星语境**：量产设计产出引擎（生成-验证分工）——AI 批量产候选，资深设计师快速筛判"哪些合格/可用"；良品率 = go/no-go 闸。**可信度不可失守**：AI 只多产不越权定夺，良品率判断权在资深（[EXPERT] 红线）。
- **基线仓库版本**：origin/main = `cba8f89`（案例库 343；分支 `data/09efg-353-intake`=353 待合）

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
| **范围** | 可插拔编排 harness（Mode1/2 现建，Mode3 留插槽给 ③）。良品率先作 baseline floor，③ 落地后 Mode3 插入触发真 go/no-go。C1 与 ③ 并行不阻塞。 |
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
- ❌ **第一里程碑不实现 Mode2** SeedRefineGenerator（现有 `protected_efl_refinement` 语义是"仅 EFL 朝 target"，纳入会复杂化 provenance 诚实模型；枚举保留作扩展点，见 §6.3）。
- ❌ 不碰长焦 404 分类 bug（`case_library.py:384`，另一 session owns）。

## 4. 架构总览与模块布局

```
app/core/orchestration/
  __init__.py
  candidate.py      # Candidate / CandidateSet / ScorecardRow 等数据模型（Pydantic）
  generators.py     # CandidateGenerator 抽象 + Retrieval / SeedRefine / TargetConverged
  scorecard.py      # 纯函数 score_candidate(candidate, target) -> ScorecardRow
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
      ├─ RetrievalGenerator(Mode1)      ──复用──▶ case_library 排序逻辑(薄只读入口 rank_cases)
      ├─ SeedRefineGenerator(Mode2)       ─未实现▶ 第一里程碑不做（枚举保留扩展点，见 §6.3）
      └─ TargetConvergedGenerator(Mode3) ─空插槽▶ ③落地后填
      → scorecard.score_candidate(每颗, target)     # 纯量化，无 pass/fail
      → 建议排序(target偏差 + 像质加权，可解释)
  → CandidateSet{ candidates[], modes_present, honesty_banner, summary }
  → scripts/c1_orchestrate.py 渲染离线 scorecard 报告(Markdown + JSON)
```

**deep-module 原则**：每 generator 一个清晰接口、隔离可独立测试；`scorecard` 纯函数无副作用可复用；`RetrievalGenerator` **复用不重写** `case_library`（唯一真相源，避免双份候选逻辑 drift）。

## 5. 数据模型 + provenance 诚实不变量

### 5.1 GenerationMode（provenance 核心，每颗候选必带）

```python
class GenerationMode(StrEnum):
    RETRIEVED        = "retrieved"         # Mode1 检索现成 seed，零优化
    SEED_REFINED     = "seed-refined"      # Mode2 seed 离线精修（EFL锁自身·玻璃不变·非target收敛）
    TARGET_CONVERGED = "target-converged"  # Mode3 ③落地后真朝客户 target 收敛
```

### 5.2 Candidate

```python
class Candidate(BaseModel):
    candidate_id: str
    mode: GenerationMode          # 必填，由 generator 构造时钉死
    source_case_id: str | None    # 检索来源 seed
    payload: OpticalSampleData    # 复用现有统一 payload（光路/MTF/点列/波前/…）
    optical_extras: OpticalExtras # generator 阶段用 optic 算的、payload 缺失的量（RI 等）
    scorecard: ScorecardRow
    generation_notes: list[str]   # 诚实注记，如 "检索最近邻 seed，未朝 target 优化"

    @property
    def is_target_converged(self) -> bool:   # 派生只读，不可单独伪造
        return self.mode is GenerationMode.TARGET_CONVERGED
```

> `OpticalExtras` 承载 generator 阶段（有 optic）算出、但现有 `OpticalSampleData` payload 里没有的量（首要是 RI；见 §7-D）。`score_candidate` 纯函数只消费 `payload + optical_extras`，不自行触碰 optic。

### 5.3 ScorecardRow（纯量化，无 pass/fail 字段）

```python
class TargetDeviation(BaseModel):
    field: str                        # efl/fov/fnum/imh/ttl
    target: float | None              # None = 未约束
    achieved: float
    abs_deviation: float
    rel_deviation_pct: float | None
    converged_toward_target: bool     # 由所属 candidate.mode 派生填充，非独立可设

class ScorecardRow(BaseModel):
    candidate_id: str
    mode: GenerationMode              # 每行都带 provenance
    target_deviations: list[TargetDeviation]   # EFL/FOV/F#/IMH/TTL
    image_quality: ImageQualityMetrics
    manufacturability: ManufacturabilityProxy
    rank_score: float                 # 建议排序分（可解释）
    rank_explanation: str
    # ↑ 无 verdict / 合格 / passed 字段
```

> **codex 轮1 修正**：`Candidate` 的 model_validator 校验 `scorecard.mode == self.mode` 且每个 `target_deviations[*].converged_toward_target == self.is_target_converged`（一致性硬校验，`raise` 非 `assert`）。`image_quality.ri` 允许 `None`（RI fail closed，见 §7-D）。

### 5.4 CandidateSet

```python
NO_TARGET_CONVERGED_BANNER = (
    "本批候选均未朝客户 target 收敛（③/Mode3 未接），scorecard 偏差为检索基线，"
    "非量产设计引擎真实产能，良品率仅供参考基线。"
)

class CandidateSet(BaseModel):
    target: TargetSpec
    candidates: list[Candidate]       # 已按 rank 排序
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

1. **mode 钉死于 generator（不可绕过）**：`generate` 是基类 **concrete final 模板方法**、只开放 `_generate`（子类无法覆盖）；返回前用显式 `raise ValueError` 校验每颗 `candidate.mode == cls.mode`（非 `assert`，`-O` 下不消失）。只有 Mode3 generator 能产 `TARGET_CONVERGED`。检索 seed 无法被标成"优化到 target"。
2. **无 pass/fail 字段**：`ScorecardRow` 无合格判定字段，AI 越权代判也无处可写。良品判断只能是资深人工动作。
3. **honesty_banner 派生强制**：`CandidateSet.modes_present` 与 `honesty_banner` 均为 `computed_field`（从 `candidates` 派生、调用方不可传入）；整批不含 `TARGET_CONVERGED` 时 `honesty_banner` 自动返回固定常量 `NO_TARGET_CONVERGED_BANNER`。
4. **mode 一致校验**：`scorecard.mode == candidate.mode`、`converged_toward_target == is_target_converged` 由 `Candidate` validator `raise` 校验（不变量间不自相矛盾）。

## 6. Generator 契约

### 6.1 抽象基类

```python
class CandidateGenerator(ABC):
    mode: ClassVar[GenerationMode]

    @abstractmethod
    def _generate(self, spec, target, *, n) -> list[Candidate]: ...   # 子类只实现这个

    def generate(self, spec, target, *, n) -> list[Candidate]:        # concrete final，子类不覆盖
        candidates = self._generate(spec, target, n=n)
        for c in candidates:
            if c.mode is not type(self).mode:                        # 显式 raise，-O 下不消失
                raise ValueError(
                    f"{type(self).__name__} 产出 mode={c.mode} != 声明 {type(self).mode}"
                )
        return candidates
```

> **codex 轮1 修正**：`generate` 改成基类 **concrete final 模板方法**、只开放 `_generate` abstractmethod（子类无法覆盖 `generate` 绕过 mode 校验）；mode 校验用显式 `raise ValueError`（不是 `assert`，`python -O` 下不消失）。

### 6.2 RetrievalGenerator（Mode1，第一里程碑主力）

- **复用不重写**：在 `case_library` 加薄只读入口 `rank_cases(spec, n) -> list[(case_id, distance, role)]`，暴露现有排序（复用 `1426-1436` 权重、`1469-1487` 距离，不碰打分算法）。
- 对每个 ranked case_id 调现有 payload 组装完整 `OpticalSampleData`，包成 `Candidate(mode=RETRIEVED)`。
- 角色语义沿用：best_match / cost_variant / thin_variant / performance_variant / nearby_alternative_N。
- **无 CODE V 依赖**（检索 + Optiland）。

### 6.3 SeedRefineGenerator（Mode2 = `SEED_REFINED`）——**第一里程碑不实现**

**codex 轮1 修正（重定）**：亲验仓库实际函数是 `protected_efl_refinement`（`local_optimizer.py:3974`），其语义与我原设计**相反**——它 operand `f2 target=target_efl_mm`（`:4072-4077`）、调用传用户请求 `efl_mm`（`case_library.py:3899`）、docstring "improves the target miss"，即 **仅 EFL 一维、radius ±5% 受保护微调、朝客户 target 收敛**（seed payload 不 mutate，`applied_to_payload=False`）。

它的语义**介于检索与 target-converged 之间**（部分朝 target：只 EFL，不动玻璃/F#/IMH/FOV/TTL）。把它标 `SEED_REFINED`"非 target 收敛"会**不诚实**（它确实朝 target 优化了 EFL）——直接踩可信度红线。

**决定**：第一里程碑**不实现** SeedRefineGenerator。`GenerationMode.SEED_REFINED` 枚举保留作扩展点（可插拔接口在），但无 generator 实例。harness 第一里程碑 = **Mode1（RetrievalGenerator）+ Mode3 空插槽**，provenance 模型只有 `RETRIEVED` 与（未接）`TARGET_CONVERGED`，最干净、最诚实。

> 将来若纳入 Mode2，必须诚实命名/标注为"**仅 EFL 维朝 target 的受保护微调**（radius ±5%，F#/glass/IMH/FOV/TTL 未优化）"，不得笼统标"seed 精修/非 target"。

### 6.4 TargetConvergedGenerator（Mode3，空插槽 = ③ 接口锚）

- 第一里程碑：`_generate` 返回 `[]` + 记录 `"Mode3 未接：需 ③优化落地"`，orchestrator 跳过 → 触发 honesty_banner。
- **docstring 写死 ③ 接入契约**（= §10 六接缝），作主公 ③ session 的接口锚。
- **③ 依赖 CODE V（硬）**，未接时跳过——不破坏无 CODE V 降级。

## 7. Scorecard 度量口径

`score_candidate(candidate, target) -> ScorecardRow` 是**纯函数**，只从 `candidate.payload` 与 `candidate.optical_extras`（generator 预算的 RI 等）消费，不自行触碰 optic/ZMX。

**A. Target 偏差**（5 维）：从 payload 提 achieved（EFL/F#/TTL ← `paraxial`；IMH ← `metadata`；FOV ← 优先 `metadata.fov_deg`（`optical_sample.py:32`），缺则由 EFL+IMH 反算），算 abs/rel 偏差；`converged_toward_target` 由 `candidate.mode` 派生。target=None → 标"未约束"、不计入排序。

**B. 像质摘要 `ImageQualityMetrics`**（全取现有真算度量）：
- MTF：代表频率点（复用 `MTFResult` 频率栅格）× 视场 {0, 0.5, 0.8, 1.0} 的 sag/tan + 衍射截止 lp/mm
- RMS 点列 per-field（max & mean, µm）
- 波前：min Strehl / RMS OPD(waves)
- 场曲：tangential/sagittal 峰值 delta
- 畸变：最大畸变 %
- RI：见 D

**C. 可制造性 proxy `ManufacturabilityProxy`**（`is_proxy=True` 硬标）：TTL / 片数 / 玻璃类型(普通 vs 特殊高折射) / 非球面复杂度(项数·面数) / CRA(主光线角·传感器匹配，几何可算)。强制 `note="非真公差良率(无 Monte-Carlo/补偿器/TOR，C2=CODE V 未接)，仅几何+材料 proxy"`。

**D. RI（相对照度）**（`app/core/relative_illumination.py`）：`RI(field) = cos⁴θ × 边缘光束渐晕因子`。**codex 轮1 修正**：payload/`RayTraceResult` 只有 `has_vignetting` bool（`lens_system.py:203`）、**无持久化渐晕系数**——RI 须在 **generator 阶段用 optic 对象**（复用/重建 optic 光追）计算，存入 `candidate.optical_extras.ri`，`score_candidate` 纯函数从此消费。能力仍是现有渐晕+光追（**非新引擎**），只是 compute 位置在有 optic 的 generator、不是 payload 纯提取。缺 optic/算不出时 **fail closed**（`ri=None` + 标 `unavailable`，不猜、不静默降级）。

**E. 排序 `rank_score`（建议排序 ≠ 合格判定）**：`rank_score = w_dev·(1−归一化 target 偏差) + w_iq·像质综合`（默认各 0.5，可配）。**独立于**检索距离。`rank_explanation` 文字透明。排第一 ≠ 合格，只是"建议资深优先看"。

## 8. 降级能力（CLAUDE.md 硬约束）

第一里程碑 = **Mode1（RetrievalGenerator）only**（Mode2 不实现，见 §6.3），**全程无 CODE V 依赖，CI 绿**。Mode3/CODE V 是 ③ 落地后增强；缺失时 harness 照常出检索基线 scorecard + honesty_banner。

## 9. 测试策略

- **单测**：每 generator、scorecard 纯函数、orchestrator、RI 计算。
- **诚实不变量测试**（可信度承重）：
  - 让 `RetrievalGenerator._generate` 产 `mode=TARGET_CONVERGED` → `generate` 模板方法 `raise ValueError`（并验证 `python -O` 下仍 raise）；
  - `CandidateSet` 全 `RETRIEVED` → `honesty_banner` 自动为 `NO_TARGET_CONVERGED_BANNER`（派生、无法置空）；
  - `scorecard.mode != candidate.mode` → `Candidate` validator `raise`；
  - `ScorecardRow` 无合格字段（结构断言）。
- **降级测试**：无 CODE V 环境跑通 Mode1（+Mode2 Optiland），全链路绿。
- **RI 数值锚**：已知渐晕系数 seed → RI 边缘值交叉验证（防假绿）。
- **@accept 锚**（夜车切片用）：每切片挂确定性验收命令，如 `test -f <report> && pytest tests/test_orchestration_*.py`。

## 10. Mode3 接口锚（③ 六接缝 · file:line）

接入 Mode3 需 ③ 落地（`codev_optimize.py`，主公专门 session）：

1. **EFL 解锁朝 target**：`codev_optimize.py:230` `EFL = ^baseline_efl_y_mm` → `EFL = {target_efl_mm}`
2. **玻璃可变**：`codev_optimize.py:257` `glass-not-varied` → varied；AUT 块加 `CHG GL`
3. **merit 加客户操作数**：`codev_optimize.py:200-236` 加 F#/IMH/FOV 操作数（现仅横向色差 + RMS 点列）
4. **applied_to_payload 真置 True**：`local_optimizer.py`（~9 处硬编码 False）
5. **verification checklist → 自动 apply**：`case_library.py:7128`（现 "not applied to delivered payload"）
6. **payload delivery 落地**：`case_library.py:14042` `delivered_candidate_id` / `:14043` `delivered_payload` 状态机

## 11. 事实锚（探子代码核实 · file:line）

**候选产出/评分**：
- `/match` 端点单候选返回：`app/api/optical.py:686-720`
- 匹配核心 `match_case`：`app/core/case_library.py:1283-1547`
- 内部已产 4 角色候选（未暴露）：`app/core/case_library.py:1511-1545`
- 权重（FOV 0.46 / IMH 0.30 / quality 0.24-0.45 …）：`app/core/case_library.py:1426-1436`
- 统一 payload `OpticalSampleData`：`app/core/optical_sample.py:1337-1352`；`CaseMetadata.fov_deg`：`optical_sample.py:32`
- 真算度量：MTF `aberration.py:121-180`、场曲/畸变 `field_analysis.py:79-150`、波前 `wavefront_metrics.py:1-150`、点列 `compute_spot_diagram spot_diagram.py:131-233`
- **RI 缺失**：payload 无渐晕系数（`RayTraceResult.has_vignetting` bool，`lens_system.py:203`），仅 checklist 文案提及（`case_library.py:4952,5189,9263,9266,9267`）→ RI 须 generator 阶段用 optic 算（§7-D）
- 长焦分类 bug（不碰）：`case_library.py:384-387`（FOV≥85° 二分）

**③ blocker**：见 §10。CODE V 硬依赖：`codev_optimize.py:317` `run_codev_optimize`；`codev_batch.py:19` `D:/CODEV115/codev.exe`。Optiland-only 精修（**仅 EFL 朝 target**）：`protected_efl_refinement` `local_optimizer.py:3974`（operand `f2 target=target_efl_mm` `:4072`；调用传用户 `efl_mm` `case_library.py:3899`）。

## 12. 红线合规映射

| 红线 | 本设计合规点 |
|---|---|
| [EXPERT] 良品判断权在资深 | ScorecardRow 无 pass/fail 字段（不变量 2）+ 良品率人工判 |
| LLM 禁碰坐标 | 所有 generator 纯确定性（检索/Optiland/CODE V），零 LLM 参与数值 |
| 无 CODE V 全链路降级 | 第一里程碑 Mode1(+Mode2 Optiland) 无 CODE V，CI 绿（§8） |
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
