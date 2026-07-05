主公大人，审查结论如下。

**Findings**

- **高** `app/data/optical_cases/index.json:605`：`US10031318B2` 的新 IMH `1.70993` 很可能是假重锚/错读值。仓库同一条记录给出 EFL `4.8143`、FOV `78.4`，一阶像高应为 `4.8143*tan(39.2°)=3.92645`，正好等于旧值 `3.926`；源 ZMX `data/zmx/US10031318B2.zmx:21` 也有 `YFLN 0 39.2 19.6`。当前值像是读到了 `19.6°` 半字段而不是全字段。触发场景：`match_case()` 在 `app/core/case_library.py:1267` 和 `app/core/case_library.py:1303` 把 IMH 用进惩罚/距离，正确 full-field 请求会被错误惩罚，低 IMH 请求反而可能选中这颗物理不一致的 seed。

- **中** `tests/test_seed_routing.py:11`：路由测试是自证循环。它把 `US20170003482A1` 自己的 EFL/F#/FOV/IMH/片数原样喂给 `match_case()`，再在 `tests/test_seed_routing.py:35` 断言同一 seed 返回。只读探针显示 `image_height_mm=None` 时也仍选中 `US20170003482A1`，所以这个测试不能证明排序/距离真的吃了 IMH。触发场景：IMH 权重被删、归一化坏掉或候选 IMH 全为 0，只要其他字段足够贴近，该测试仍可能绿。

- **中** `scripts/e2_golden.py:95`：新增 eval golden 由当前 `match_case()` 生成，`scripts/evaluate_design_agent.py:79` 又拿同一份 generated golden 断言运行时选择；这只能钉住当前行为，不能证明 golden 选择或质量数值来自 CODE V/独立真值。触发场景：如果 `match_case()` 或 index 中已有错误值，重跑 `scripts/e2_golden.py` 会把错误固化进 `tests/data/eval_golden.json`。

- **中** `.planning/loop/seed-eval-rebase-report.md:17`：5 颗 golden 存在覆盖偏倚，且遗漏了本次最异常的 `US10031318B2`。我逐颗 exact brief 探针看到 22 颗里 18 颗可 self-select，但报告只挑 5 颗；pytest 新增用例 `tests/test_eval_golden_seeds.py:28` 实际只跑其中 1 颗，其余主要是 JSON 结构检查。触发场景：其余 reanchored seeds，尤其高 delta/异常 IMH seed，回归不会被 CI 的 pytest 路径挡住。

- **低** `scripts/rebase_seed_imh.py:100`：脚本对 `index.json` 本身同 readout 重跑不会二次累加漂移，但报告不幂等；第二次运行会把已重锚值当 `old_image_height_mm`，`scripts/rebase_seed_imh.py:205` 写出的 delta 变成 0，覆盖原始新旧差异证据。触发场景：后续维护者复跑脚本后，无法从 committed report 追溯第一次重锚的真实 delta。

**查过未发现问题**

- 17 颗带 `_IMH` token 的真实设计：当前 index 值与 token 全部相等，base→head 只改了 22 个 `US*` 专利 seed，未见真实设计行为变化。
- 无 CODE V 环境 CI：workflow 仍是 Ubuntu `uv run pytest -v`；真实 CODE V smoke 有 `skipif(not DEFAULT_CODEV_EXECUTABLE.is_file())`，新增 rebase 测试用 fake runner。未发现新增硬依赖 CODE V。
- 我没有改/建/删文件，没有跑全量 pytest；只做了只读文件审查和 `python -B` 一次性探针。