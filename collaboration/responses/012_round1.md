# 012 Round 1：显式 mask10 来源验收与既有证据复用

日期：2026-10-18。实现：X。状态：submitted，待 Codex 集中审查与独立目录部署。

本轮按[012任务](../tasks/012_mask10_scoped_acceptance.md)修改来源验收范围。011 的软件 accepted 裁决保留；这次不是推翻原实现，也不宣称已经取得真实模型结果。

## 交付身份

- 最新 main：`bc320cbd1a5456e5529b3761de50f1a11c7a08ae`。
- 接入已验收 PR #8：`766ab9603c376b4139ed32a36ed52fe4498425ae`；仅在新的本地分支合并，形成基线 `a428702a6474ea1f7bbc1fadd63a3e611c2b5491`。
- 实现提交：`7f023d580cfe0da2da3c95b01311e4957b5fb0b1`；分支：`x/task012-mask10-acceptance`；独立 [PR #9](https://github.com/No1dry/LIBERO-Remain/pull/9)，open/unmerged，待审查。
- PR #8 尚未合入 main 时，新 PR 的总 diff 会包括其已验收代码。012 自身增量请对上述 `a428702` 基线或012实现提交查看；没有将010分支合入 main。

## 实现与范围

1. `headless/source_acceptance.py` 新增只读 `load_mask10_source` / `validate_mask10_snapshot`。显式配置 `source_acceptance="remaining-headless-mask10-source-acceptance-v1"` 才启用；省略配置仍调用原 `pilot._source` 全 mask 路径。未修改原 validator、构造器、回放器或 prepare。
2. 固定选取每任务官方索引0..9的十条10。核对 manifest/replay 来源身份、状态字节、构造实际初态及完整审计、独立回放覆盖与审计；从保存的原数值重算物理检查，从 typed NPZ 重算初始观测比较。不是只读取缓存的 `true`。所选任一证据缺失、截断、失败或失配，仍记为本任务未就绪。
3. 不读取未选00/01/11的状态/审计/NPZ，不以原报告全局 `technical_acceptance` 为10门槛。完整原 manifest/replay 字节、原 global flag/error 和未选失败行均保留；新证据单独标 `mask10_ready`、范围版本、选择与来源身份。报告声明的所选重复回放必须全部完整通过，至少两次。
4. 规划直接读取每任务证据，不要求总 prepare 结束，也不读取或回写旧 `preparation.json`。因此旧 `preparation_error` 与新 `mask10_ready` 可并存。读取期间文件变化则不将这次不稳定读取认定为就绪。
5. 新运行归档完整原报告与必要已选依赖，环境从归档状态读取；离线 reader 按同一范围复核归档，不依赖原准备目录仍存在。范围与选择身份进入 plan、task metadata、每条 raw 及执行证据绑定，并在 summary 披露。
6. 十任务100条、主轨60/扩展40、H520/K4/chunk8、端点、动作、模型、物理事件、路径长度、计分与视频保持011协议。未就绪和失败保留固定分母；不追加或自动重跑模型 episode。

主要文件：`headless/source_acceptance.py`、`planning.py`、`workflow.py`；`runner.py` 仅在结果封存前写入范围身份，不改控制循环。新增两份范围验收/集成测试，README与原runbook链接到[012命令说明](../../docs/task012_mask10_scoped_acceptance.md)。

## CPU/fake 验证

只运行受影响路径和旧默认行为的小回归，没有全库测试或真实仿真/模型 smoke。以下命令中的 `python` 使用已有 CPU 测试解释器，在本分支根目录执行：

```bash
python -m pytest tests/test_headless_source_acceptance.py -q --basetemp reports/task012_scope_final
python -m pytest tests/test_headless_workflow.py -q --basetemp reports/task012/legacy-workflow
python -m pytest tests/test_headless_mask10_workflow.py -q --basetemp .pytest_task012_mask10_workflow
```

来源读取专项：**22 passed，18.37秒**。旧工作流回归：**13 passed，72.52秒**。最小集成：**2 passed，6.29秒**。合计 **37 passed，0 skipped**，均退出0；`git diff --check`通过。

覆盖：其它 mask 失败而10就绪、旧全 mask 路径仍拒绝；未选文件全部缺失不阻塞；所选状态/初始观测/构造审计/独立回放失配、截断、重复或缺失被拒；物理检查不接受缓存 true；既有 RGB 规则沿用；原文件字节未变；仅归档选中依赖后仍可离线复核。

集成测试使用真实范围读取器及真实 typed 文件，只有 policy/env/video 使用CPU fake；贯穿 dry-plan→run→inspect，验证原全局失败和preparation_error/starting不被改写、basket10就绪而其余90保留missing、归档后移走原测试来源仍可读取、归档所选状态篡改则拒绝计分、raw与范围身份一致。不将fake成功数当作研究成绩。

## 复用命令与后续交接

[完整命令文档](../../docs/task012_mask10_scoped_acceptance.md)给出独立 batch 配置复制脚本，按**旧 batch 所在目录**解析来源和 runtime 路径；保留 runtime 内部原仓库工作目录语义，避免换 checkout 后指错资源。基本入口均已实现：

```bash
python -m benchmark.remaining_goals.headless.cli dry-plan --config PATH_TO_NEW_BATCH --out NEW_PLAN_DIR
python -m benchmark.remaining_goals.headless.cli run --config PATH_TO_NEW_BATCH --out NEW_BATCH_DIR --track primary
python -m benchmark.remaining_goals.headless.cli run --config PATH_TO_NEW_BATCH --out NEW_BATCH_DIR --track extension
python -m benchmark.remaining_goals.headless.cli inspect --run NEW_BATCH_DIR
python -m benchmark.remaining_goals.headless.cli summarize --run NEW_BATCH_DIR --out NEW_DERIVED_DIR
```

Codex审查后在**独立代码目录**部署并填写现有数据、解释器与模型路径；用户启动真实模型评测。当前运行的旧 prepare 源码、配置、工件和进程均未触碰。本轮不运行 prepare/build/replay、不换来源、不追加 episode，不要求补做已有效的四 mask 双回放。

任务012所述四任务20/20次mask10回放以及stove/cheese_butter的未选失败，属于任务文档提供的现场事实，本轮没有访问服务器重新认证。上述测试均为CPU/fake，不能当作真实 mask10 成功率。初始 typed 像素可独立重算；动态 RGB 仍依据原审计保存的界限诊断，不声称恢复未保存的全部历史图像。`mask10_ready` 不是全mask验收、语义合法性审定或模型成功结论。
