# Task012：只读复用既有 mask10 状态与回放

本页对应[任务012](../collaboration/tasks/012_mask10_scoped_acceptance.md)，补充[十任务 headless runbook](headless_ten_task_baseline_runbook.md)。新增入口只改变本轮**来源验收范围**：由选中的 mask10 证据决定是否就绪。已有 00/01/11 失败仍保留，不能解释为它们通过，也不是 VLA 评测结果。

默认省略新配置项时，仍使用原来的全 mask 验收。显式启用方式是在独立的 batch JSON 顶层增加：

```json
"source_acceptance": "remaining-headless-mask10-source-acceptance-v1"
```

这不是 CLI flag，也不改变 batch 的 `schema_version`。十任务、每任务官方索引 0..9、mask10、固定 100 条模型分母及 policy seed 7 均不变；H520、K4（5 个相邻观测）、chunk8、目标确认端点、物理事件、TCP 路径和模型动作沿用任务011。没有新增模型 smoke、重跑、校准或训练。

## 复用边界

将审阅后的 task012 代码部署到**独立 checkout**，在该目录运行下面命令。现有 prepare 可以继续运行；不要修改它的源码、配置、状态包、回放报告或 `preparation.json`，也不要停止或重启它。本页不包含 prepare、build 或 replay 命令。

新配置只读引用已有完整 manifest、已有 mask10 状态和已有独立回放。某任务完整证据已写完即可参与规划，不要求其它任务或整个 prepare 进程结束。缺失、写入未完成或实际失败的必要 mask10 证据仍记为未就绪；不换初态、不补造报告，不重复生成已经有效的状态或回放。

新验收仍核对所选来源身份、实际初态、状态文件、构造审计和独立回放，不能只信报告里缓存的 true。原完整 manifest/replay 及其失败事实原样保留，后续离线读取按记录的验收范围复核。旧 `preparation_error` 与新 `mask10_ready` 可以并存：前者描述旧的全 mask 结果，后者仅描述本次选择。

## 从既有配置创建独立配置

以下为 Linux Bash。先进入**新 checkout 根目录**，复用原仿真解释器和既有 LIBERO/GL 设置；`SIM_PY` 保留原解释器路径，不用 `readlink -f` 改成 base Python。具体设置见[启动方式](headless_ten_task_baseline_runbook.md#启动方式)。

```bash
SIM_PY=/absolute/path/to/existing/simulation/env/bin/python
OLD_BATCH=/absolute/path/to/existing/stage05_batch.local.json
NEW_BATCH=configs/remaining_goals/local/task012_mask10.local.json

"$SIM_PY" - "$OLD_BATCH" "$NEW_BATCH" <<'PY'
import json
import sys
from pathlib import Path

source = Path(sys.argv[1]).expanduser().resolve()
target = Path(sys.argv[2]).expanduser().resolve()
config = json.loads(source.read_text(encoding="utf-8-sig"))

def source_relative(value):
    path = Path(value).expanduser()
    return str((path if path.is_absolute() else source.parent / path).resolve())

# Batch paths are relative to the OLD batch directory, not the new checkout.
config["runtime_config"] = source_relative(config["runtime_config"])
for task_source in config["sources"].values():
    for field in ("manifest", "candidate_replay"):
        task_source[field] = source_relative(task_source[field])
config["source_acceptance"] = "remaining-headless-mask10-source-acceptance-v1"
target.parent.mkdir(parents=True, exist_ok=True)
with target.open("x", encoding="utf-8") as stream:
    stream.write(json.dumps(config, ensure_ascii=False, indent=2, allow_nan=False) + "\n")
print(target)
PY
```

脚本只新写一份 batch 配置；目标已存在会拒绝覆盖。`sources` 和 `runtime_config` 按**旧 batch 所在目录**解析成绝对路径，避免复制后误指向另一个状态包。它不修改被引用的 runtime JSON：runtime 内部的模型、官方源码等相对路径仍沿用**仓库工作目录**语义，不能改成相对 runtime JSON 目录。部署者须保证这些路径在新 checkout 中仍指向原冻结资源；若需要调整，只调整独立 runtime 副本并让新 batch 引用它，不能修改运行中 prepare 使用的文件。

## 文件规划

```bash
"$SIM_PY" -m benchmark.remaining_goals.headless.cli dry-plan \
  --config "$NEW_BATCH" --out reports/task012_mask10_plan_001
```

这是文件读取，不创建仿真或加载模型；输出目录必须是新目录。检查 `plan.json` 的固定 100 条计划、每任务状态和 `ready_episodes`，不要把命令退出成功当成所有任务都已就绪。ready 任务的 `plan.json.tasks[].source_acceptance` 保存下列证据；开始评测后，同一证据保存在任务 `task_run.json` 的 `source_plan.source_acceptance` 中：

| 字段 | 含义 |
|---|---|
| `schema_version` | `remaining-headless-mask10-source-acceptance-v1` |
| `status` / `acceptance_scope` | `mask10_ready` / `mask10`；任务行本身仍使用 `status=ready` |
| `selection` / `selection_sha256` | task、`mask=[true,false]`、固定 indices 0..9、episode IDs 及选择摘要 |
| `selected_episode_ids` / `episodes` | 实际选中的十条及各自构造、重复回放验收结果 |
| `source_manifest_sha256` / `source_replay_sha256` | 原完整 manifest/replay 字节身份；另保留 `source_content_hash` |
| `selected_files` | 必要证据的来源根、相对路径与 SHA；归档后由 reader 核对 |
| `global_report_diagnostic` | 原报告的 `technical_acceptance` 和 `error`，不改成全局通过 |
| `unselected_failures` / `unselected_record_count` | 原未选失败行和未选记录数量 |
| `evidence_sha256` | 本次范围验收证据摘要 |

每条 raw 的 `source_acceptance` 记录版本、`acceptance_scope`、`selection_sha256` 和 `selected_episode_ids`，并绑定执行证据。`summary.json` 的 `source_acceptance_version` 标明启用的版本，`source_acceptance` 按任务保留完整验收证据；没有执行或未就绪的条目仍通过固定计划及错误账本显示。

只有十个固定来源的必要 mask10 证据齐全且通过，任务才可就绪。某条 10 实际不通过时保留具体错误，不能用“异常来自其它 mask”替它放行；尚未完成的任务仍留在固定分母内。

## 用户启动已有 headless 评测

确认部署与规划结果后，由用户运行原来的 CLI。为新验收身份使用独立批次目录；两轨共享这个新目录，不复用旧验收身份的模型批次，不借换目录重复已经执行的模型 episode。

```bash
"$SIM_PY" -m benchmark.remaining_goals.headless.cli run \
  --config "$NEW_BATCH" --out reports/task012_mask10_baseline --track primary
```

扩展轨使用同一配置与批次根：

```bash
"$SIM_PY" -m benchmark.remaining_goals.headless.cli run \
  --config "$NEW_BATCH" --out reports/task012_mask10_baseline --track extension
```

未就绪任务不创建模型。技术错误暂停受影响任务并保留原记录，已登记任务不会自动重跑；其余任务按既有规则独立执行。需要更新未尝试任务的就绪情况时，仍使用同一冻结代码、配置和批次根。这里没有追加准备、回放或模型预算。

## 离线核验

```bash
"$SIM_PY" -m benchmark.remaining_goals.headless.cli inspect \
  --run reports/task012_mask10_baseline
```

需要另存汇总时，写到原批次外的新目录：

```bash
"$SIM_PY" -m benchmark.remaining_goals.headless.cli summarize \
  --run reports/task012_mask10_baseline --out reports/task012_mask10_summary_001
```

离线 reader 使用记录的验收范围、源与选择身份核验已有工件，不调用模型或仿真。原完整报告仍在 `tasks/<task>/source/manifest.json` 与 `replay_report.json`；新增 `source/manifest_files/` 和 `source/replay_files/` 保留各自原报告 basename 及必要已选证据的相对路径。离线复核使用这些快照，不依赖正在运行的旧准备目录。

保存的初始图像/本体观测可从实际数组复核；动态 RGB 使用原已记录的固定界限诊断，不声称重新生成所有历史帧。模型 trace、视频、原始动作和指标保持任务011协议。`mask10_ready` 只证明这一来源选择通过所声明的技术验收，不证明全 mask 通过、候选语义合法或模型任务成功。
