# 路由里权重最大的那一维，比的是两种单位（2026-07-29）

**一句话**：`index.json` 的 `fov_deg` **253 颗存半视场、172 颗存全视场**，
而 schema 白纸黑字写的是「Nominal full FOV」；这一维在 `rank_seeds` 里权重
**0.46（全部维度里最大）**，并且是 `_classify_scenario` 的唯一视场输入——
按 ZMX 真值重判，**104/425（24.5%）的 case 场景桶是错的**。

## 口径由代码自己声明，不是我的推断

- `app/core/optical_sample.py`：`fov_deg: float = Field(..., description="Nominal full FOV from the manifest")`
- `app/core/lens_system.py`：「`fov_deg` is the nominal full field angle」

## 测量

对每一颗有角度型（`FTYP 0`）ZMX 的 case，取其外场 `YFLN` 值 `θ`（CODE V 实际追迹的半视场角），
看 `fov_deg / θ`：

| 分组 | 颗数 | `声明像高 / (EFL·tanθ)` 中位数 |
|---|---|---|
| `fov_deg == θ`（存的是**半**视场） | **253** | **0.9957** |
| `fov_deg == 2θ`（存的是**全**视场） | **172** | **1.0004** |
| 其它比值 | **0** | — |
| 非角度型 ZMX（原生 `FTYP 3` 真实设计） | 17（跳过） | — |

比值**只有两个值，没有第三种**——这不是噪声，是两套口径。

## 错的是 manifest，不是 ZMX

第三列是独立的物理自查：直线投影下外场像高 = `EFL·tanθ`。
若 `θ` 是把全视场当半视场写进去的（即真半角只有 `θ/2`），该比值会落在 **0.5 附近**。
**两组的中位数都是 1.00**（0.9957 / 1.0004），所以**两组的 `θ` 都是真半角**，
分歧全在 `fov_deg` 这一列。

## 后果（按权重从大到小）

1. **种子路由**：`rank_seeds` 的权重表里 `fov: 0.46` 是最大的一项（`efl` 只有 0.20），
   另有 `fov_miss > 5°` 的硬惩罚。一颗 40° 半角的 case 与一颗 80° 全视场的 case
   **是同一种镜头**，却被打成 40 与 80、相差 40° 的巨大惩罚；反过来一颗 45° 全视场
   （真半角 22.5°）会被当成 45° 半角控制的好匹配。
2. **场景分桶**：`_classify_scenario(fov_deg, efl_mm)` 用 `fov_deg >= 超广阈` /
   `fov_deg <= 45（长焦上限）` 判桶，而 `cases_for_scenario` 用桶挑种子池。
   按 `2θ` 重判：**104/425 = 24.5% 会换桶**
   （wide→ultrawide 73、telephoto→wide 29、wide→telephoto 2）。
3. 这解释了 P2 那 6 条里为什么会出现 **18.35° 的 seed 配 37.5° / 33.1° 的对照**——
   而消融实测里主导的失败模式恰恰是**视场受限**。

## ⚠️ 更正一处我自己的话

在 `seed-field-rebuild-2026-07-29.md` 初稿里我写过「`rank_seeds` 完全不看视场」。
**那是错的**，它看，而且看得最重。病灶是它读到的那个数的单位。

## 复算

```
uv run python scripts/fov_unit_census.py --json <out.json>
```

`tests/test_fov_unit_census.py` 含负对照（单一口径的语料必须报"不混"）
与"ZMX 错 vs manifest 错"的判别用例。

## 未做

- **没有改数据**。本铲只测量。迁移（把 `fov_deg` 统一重锚到 `2θ`）会改 104 颗的场景桶，
  牵动 `cases_for_scenario` 的种子池与一批测试基线，须单独一铲并跑完整影响面。
- 17 颗原生 `FTYP 3` 的真实设计没有角度可比，未判定。
- 未回查专利原文确认那 253 颗的原始标签是 `HFOV` 还是 `FOV`——
  本铲的结论不依赖它（物理自查已足够定位错在哪一列），但迁移时值得抽样复核。
