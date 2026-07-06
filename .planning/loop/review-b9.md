主公大人，发现 1 条实质缺陷，其余重点维度未发现问题。

**Finding**

- 中危：`scripts/e2_golden.py:91` / `tests/test_eval_golden_seeds.py:30`
  路由/eval golden 没有覆盖新 67 颗 DATA-06c seed，只覆盖了 3 颗：`US-12416791-B2-e3`、`US-20200003996-A1-e3`、`US-20250383531-A1-e7`。代码在 `case_id.startswith("US-")` 且 first-order IMH 偏差超过 25% 时直接跳过，测试也只断言这 3 颗子集存在。
  触发场景：后续转换器把未覆盖的 64 颗新 seed 的路由特征、IMH、MTF 或 element count 改坏，eval golden 不会报警；尤其是多实施例串表类错误如果落在未 golden 的新 seed 上，只有 ingest/load 类测试兜底，不会锁住实际路由赢家行为。

**数值抽验**

来源：USPTO PPUBS HTML，PDF 链接：
`https://ppubs.uspto.gov/dirsearch-public/print/downloadPdf/US20250035890A1`
`https://ppubs.uspto.gov/dirsearch-public/print/downloadPdf/US20240264412A1`

`US-20250035890-A1-e6` 对应 USPTO 第 6 实施例：`f=0.44, Fno=1.8, HFOV=75.5`。逐面比对 ZMX，r/d/nd/vd 与 K/A4/A6/A8/A10/A12/A14/A16/A18/A20 均匹配；`Plano` 在 ZMX 表现为 `CURV 0`，记作等价。

```text
S01 r -13.8248/-13.8248 d .25/.25 nd/vd 1.545/56.1 coef K..A20 Δ0
S02 r .6784/.6784 d .777/.777 nd/vd - coef K..A20 Δ0
S03 r -7.1412/-7.1412 d .23/.23 nd/vd 1.544/56.0 coef K..A20 Δ0
S04 r 1.1387/1.1387 d .601/.601 nd/vd - coef K..A20 Δ0
S05 Plano/CURV0 d -.043/-.043 nd/vd - coef - Δ0
S06 r 1.0728/1.0728 d .564/.564 nd/vd 1.544/56.0 coef K..A20 Δ0
S07 r -.4897/-.4897 d -.125/-.125 nd/vd - coef K..A20 Δ0
S08 Plano/CURV0 d .2/.2 nd/vd - coef - Δ0
S09 r -2.194/-2.194 d .22/.22 nd/vd 1.669/19.5 coef K..A20 Δ0
S10 r .604/.604 d .035/.035 nd/vd - coef K..A20 Δ0
S11 r .635/.635 d .692/.692 nd/vd 1.544/56.0 coef K..A20 Δ0
S12 r -.4616/-.4616 d .036/.036 nd/vd - coef K..A20 Δ0
S13 r -.441/-.441 d .22/.22 nd/vd 1.669/19.5 coef K..A20 Δ0
S14 r -.8552/-.8552 d .217/.217 nd/vd - coef K..A20 Δ0
S15 Plano/CURV0 d .210/.210 nd/vd 1.517/64.2 coef - Δ0
S16 Plano/CURV0 d .349/.349 nd/vd - coef - Δ0
S17 Plano/CURV0 d 0/0 nd/vd - coef - Δ0
```

`US-20240264412-A1-e4` 对应 USPTO 第 4 实施例：`f=2.50, Fno=1.92, HFOV=60.6`。逐面比对同样无 mismatch。

```text
S01 r -5.657/-5.657 d .300/.300 nd/vd 1.544/55.9 coef K..A20 Δ0
S02 r 2.105/2.105 d .703/.703 nd/vd - coef K..A20 Δ0
S03 r 3.072/3.072 d .553/.553 nd/vd 1.544/55.9 coef K..A20 Δ0
S04 r -2.788/-2.788 d .252/.252 nd/vd - coef K..A20 Δ0
S05 Plano/CURV0 d -.202/-.202 nd/vd - coef - Δ0
S06 r 3.575/3.575 d .942/.942 nd/vd 1.544/55.9 coef K..A20 Δ0
S07 r -2.917/-2.917 d .084/.084 nd/vd - coef K..A20 Δ0
S08 r 17.466/17.466 d .200/.200 nd/vd 1.688/18.7 coef K..A20 Δ0
S09 r 2.348/2.348 d .191/.191 nd/vd - coef K..A20 Δ0
S10 r 1.741/1.741 d .231/.231 nd/vd 1.544/55.9 coef K..A20 Δ0
S11 r 1.817/1.817 d .616/.616 nd/vd - coef K..A20 Δ0
S12 r -6.040/-6.040 d .461/.461 nd/vd 1.544/55.9 coef K..A20 Δ0
S13 r -1.547/-1.547 d .074/.074 nd/vd - coef K..A20 Δ0
S14 r 1.173/1.173 d .300/.300 nd/vd 1.584/28.2 coef K..A20 Δ0
S15 r .711/.711 d .700/.700 nd/vd - coef K..A20 Δ0
S16 Plano/CURV0 d .210/.210 nd/vd 1.517/64.2 coef - Δ0
S17 Plano/CURV0 d .187/.187 nd/vd - coef - Δ0
S18 Plano/CURV0 d 0/0 nd/vd - coef - Δ0
```

**查过为空**

- XASPHERE/XDAT：未发现 A18/A20 槽位错位；`XDAT 3=0, XDAT 4=A4 ... XDAT 12=A20` 与 Optiland `coefficients[0]=r^2`、EVENASPH `PARM 1=0, PARM 2=A4` 一致。
- 入库诚实性：`index.json` 总数 106，DATA-06c 为 67；DATA-06c 没有 `mtf_max_field_frac > 0.5`，audit JSON 记录 `total_seed_count=106`、`accepted_seed_count=0`。
- `seed_imh_overrides.json`：旧 39 颗全覆盖，且与 `origin/main` 的旧 index IMH 完全一致，未发现把旧值改坏。
- `-e` case_id：正常库路径先查 index，再 fallback `_IMH_RE`，新 `-e` seed 可取到 index IMH；未发现兼容性问题。
- 索引重生成：旧 39 当前 index IMH 与 override 完全一致，未破坏批次 7 真 IMH 重锚值。

未跑全量 pytest；本轮只做只读文件检查、USPTO 联网核验和 stdout 比对脚本。

## 2026-07-06 Fix Follow-up

- Golden coverage fixed in `scripts/e2_golden.py`: generated case-anchored golden now covers all 106 records in `app/data/optical_cases/index.json`, not just the 25 patent subset and not just the 3 DATA-06c seeds that happened to pass the old first-order check.
- Physical IMH anchor changed to stored real-ray evidence: for the 67 ZMX files that contain `ATELIER_REAL_IMH_MM`, generation checks `index.image_height_mm` against the ZMX tail comment at <=2%. First-order `f*tan(FOV/2)` is retained only as `first_order_image_height_*` sanity metadata in `tests/data/eval_golden.json`; the 64 DATA-06c seeds with >25% first-order deviation are included.
- `tests/test_eval_golden_seeds.py` now parameterizes over all 106 case golden briefs and asserts the ZMX real-IMH anchor where a tail comment exists.
- `accepted_seed_count=0` was confirmed to mean the strict high-FOV full-field acquisition window is still empty, not that the 67 DATA-06c seeds failed intake. `scripts/audit_seed_intake.py` now emits `full_field_accepted_seed_count=0` and a separate DATA-06c lightweight gate: loaded + finite positive paraxial + IMH > 0 + JSON surface count equals ZMX `SURF` count.
- Audit spot-check result: `total_seed_count=106`, `full_field_seed_count=19`, `high_fov_seed_count=16`, `accepted_seed_count=0`, `lightweight_accepted_seed_count=67/67`.
- Verification run, no full pytest: `$env:PYTHONUTF8='1'; .\.venv\Scripts\python.exe -m pytest tests/test_eval_golden_seeds.py tests/test_seed_intake_audit.py -q` -> 325 passed, 1575 warnings.
