# 009：init35 释放可测性诊断运行手册

本手册对应[009任务](../collaboration/tasks/009_release_observability_replay.md)。这是独立的 evaluator-side 测量诊断：从原 bank 已 settle 的初态，顺序重执行 `basket_s035_00` 的原动作前缀，解释 step280 的保守包络为何返回 unknown。它不修改 release 判据、标签、阈值、校准或 benchmark 指标，也不建立新的停止成功率。

Codex负责审查、纯文件准备、冻结版本和服务器路径核对；真实 native 作业由用户亲自启动。下面没有自动串联实验。软件 CPU/fake 测试通过不代表真实轨迹、几何或物理释放已得到验证。

## 固定输入与预算

| 输入 | 固定值 |
|---|---|
| 原 source run | `/HUBU-AI096/zp/ICML/stage04_finish_3433f48/results/run01/validation_shadow` |
| run ID | `65c8ef90d9d7495ebc8234cb814e3b5a` |
| 唯一 episode | `basket_s035_00`，official-init index35 对应的原已 settle bank 状态 |
| 原 normal-bank | `/HUBU-AI096/zp/ICML/stage04_finish_2cb1428/results/run01/normal_bank/normal_bank.json` |
| 保存状态 | `sources/035/states/basket_s035_00.npy` |
| 动作预算 | 原 `executed_actions` 的 step1..292，float64 原值与字节顺序 |
| 快照预算 | step0 加执行后 step1..292，最多293个 |
| 原 query 对照 | 0、8、…、288，共37个边界；仅比原 raw observation hash，不调用模型 |

step292 属于原 query37（观测 step288）的 `chunk_index=3`，**step292 没有 query**。诊断不执行293..296，不进入 FINISH 或 hold，不做 W150，也不追加 init37 或任何其他轨迹。292个20Hz控制步不等于292次底层 `mj_step`；原 reset、restore 和控制步内部的必要 native 调用分别记录。

CLI校验允许 `--max-action-steps` 为1..292的整数前缀，默认292；本次部署仍固定292。失败后不自动改为较短前缀重试，不因此产生另一项用户已启动作业。

源身份严格绑定下列 SHA，plan/run 不提供替换这些约束的 CLI 参数：

| 文件／模型 | SHA-256 |
|---|---|
| source `run.json` | `0c0fa4803d1e7a8a9b1a3a1ab2fe15f55c7b2e35a66436117d2fddd60283fb9b` |
| source `raw/0000.json` | `049ac123d348402177c30c9b2915b88e9573ea3bed18663c0f1fcc3eb6af3e78` |
| `normal_bank.json` | `084e55537c25e515153e48624d807483b3348f9cee67db77425f69d5eaa6080c` |
| 已 settle 保存状态 | `e1d42bfb1aa9c21e52615e95e8f834eedbf361592c259d654e5a807423ba408f` |
| 原模型 XML | `dad2437d1c2f8cbff26232c252f241978ce7de02cc6e34da0267fc94f4607163` |
| basket BDDL | `2e661058917f683a25bce480015197f0a2c1911bcbc2b9dd9d947199069c9618` |

原结果仍属于其生产版本 `3433f487d38efe0a08e4c814e87412aad5aba9fe`。新诊断实现有独立版本，不要求旧 artifact 的 implementation hash 改成新代码；不得重写旧 run、bank、head、cache、calibration 或失败记录。

## 纯文件 plan：由 Codex 准备

实际入口与帮助：

```bash
"$SIM_PY" -m benchmark.remaining_goals.finish.release_audit --help
"$SIM_PY" -m benchmark.remaining_goals.finish.release_audit plan --help
"$SIM_PY" -m benchmark.remaining_goals.finish.release_audit run --help
```

`--help` 与 plan 不创建 native 环境、不加载研究 head/VLA。plan 验证已有文件和 ledger，原 `calibrated=false` 不阻止只读诊断计划。

以下 `$REPO`、`$DIAG_ROOT` 是 Codex 部署时必须填齐的绝对路径占位，不能当成已部署位置。`$DIAG_ROOT` 应处于本次新诊断目录，并在所有旧 source/run/bank 目录之外。沿用原仿真解释器，不升级依赖：

```bash
SIM_PY=/HUBU-AI096/zp/ICML/LIBERO-Remain-normal00-stage02/.runtime/remaining_libero/venv/bin/python
REPO='<Codex填写：009验收SHA的新源码目录>'
DIAG_ROOT='<Codex填写：本次全新诊断目录>'
SOURCE_RUN=/HUBU-AI096/zp/ICML/stage04_finish_3433f48/results/run01/validation_shadow
cd "$REPO"
mkdir -p "$DIAG_ROOT/logs"
PLAN_LOG="$DIAG_ROOT/logs/01_plan.log"
( set -o noclobber; : > "$PLAN_LOG" ) || { printf '日志已存在，停止；保留原文件。\n' >&2; exit 2; }
set -o pipefail
"$SIM_PY" -m benchmark.remaining_goals.finish.release_audit plan \
  --source-run "$SOURCE_RUN" \
  --episode-id basket_s035_00 \
  --max-action-steps 292 \
  --out "$DIAG_ROOT/plan" \
  2>&1 | tee -a "$PLAN_LOG"
PLAN_RC=("${PIPESTATUS[@]}")
printf 'command_exit=%s tee_exit=%s\n' "${PLAN_RC[0]}" "${PLAN_RC[1]}" | tee -a "$PLAN_LOG"
test "${PLAN_RC[0]}" -eq 0 && test "${PLAN_RC[1]}" -eq 0
```

`plan` 输出冻结的 `plan.json` 和 typed `actions.npz`，并记录来源文件 SHA 与预算。计划输出目录必须不存在，不能覆盖旧计划。计划就绪只表示纯文件核对通过，不表示 native 初始化或重执行已通过。Codex核对计划和原始来源后，再交用户下一条独立命令。

## 用户单独启动 run

用户确认源码、计划和路径后亲自运行；`$DIAG_ROOT/run` 必须是全新目录：

```bash
cd "$REPO"
RUN_LOG="$DIAG_ROOT/logs/02_run.log"
( set -o noclobber; : > "$RUN_LOG" ) || { printf '日志已存在，停止；保留原文件。\n' >&2; exit 2; }
set -o pipefail
"$SIM_PY" -m benchmark.remaining_goals.finish.release_audit run \
  --plan "$DIAG_ROOT/plan/plan.json" \
  --out "$DIAG_ROOT/run" \
  2>&1 | tee -a "$RUN_LOG"
RUN_RC=("${PIPESTATUS[@]}")
printf 'command_exit=%s tee_exit=%s\n' "${RUN_RC[0]}" "${RUN_RC[1]}" | tee -a "$RUN_LOG"
test "${RUN_RC[0]}" -eq 0 && test "${RUN_RC[1]}" -eq 0
```

run 重新核对冻结计划及所有来源文件后，才创建唯一 `FinishLiberoEnv`，沿用原 reset/step 与观测同步语义。动作不重采样、不裁剪、不修改 gripper。记录器只读取既有 native 数组，不新增诊断 step、forward、render 或 controller update；VLA forward、head inference、processor 调用均为0。

禁止自动 resume、重试或扩预算。来源文件变化、原观测／truth／动作／phase 首个不一致或技术异常都应停止，保留 partial，并由 Codex只读分析。关闭资源不通过额外 step、开爪或恢复动作来“收尾”。不使用输出侧录触发 GT 停车。

## 核查输出与解释范围

计划自身另有 `plan/manifest.json`，绑定 `plan.json` 和 `actions.npz`。如果运行清单写入失败，`summary.json` 会记录 `technical_error`（中断则为 `interrupted`）、`phase=manifest`、`manifest=null`，不得把残留文件当作完整交付。

检查 `plan/plan.json`、`run/summary.json`、冻结计划副本 `run/source_plan.json` 与逐文件 SHA 清单 `run/manifest.json`。报告应明确区分 `plan_ready`、`diagnostic_completed`、`replay_mismatch`、`technical_error` 和 `interrupted`，保留首个差异、请求／完成控制步、快照数、原 query 对照、native 调用分期、初始化／动作期时间及清理错误。`diagnostic_completed` 只表示授权前缀执行和一致性检查完成。CLI的0表示计划或诊断按约完成，2表示不匹配或技术错误，130表示中断；必须同时记录 command 和 tee 两个退出码，不能用 tee 的0掩盖命令失败。

每帧 JSON 记录 step、实际动作阶段、所属原动作／chunk、当前是否原 query 边界、原判据 truth 和 native typed 文件引用。最后一帧应为 `frames/0292.json`，所属动作 query37/chunk3，当前 `query_reference=null`；不得出现 step293。typed NPZ 使用数值数组，不使用 pickle。

侧录保存静态模型、相关 collision geom/mesh 与名字→ID映射，以及逐帧 INTEGRATION state、ctrl、OSC/gripper 状态、geom 位姿、contact 和原包络计算证据。记录器前后 state/controller/gripper/RNG 指纹应一致；读取缺失、非法形状或非有限值属于诊断技术错误，不能变成物理 unknown。若保存接触力，应明确坐标系和时刻，力本身不是释放证明。

固定依赖不提供本任务可直接使用的 `mj_geomDistance`；本次没有授权实现精确距离、更紧外包体或新标签。外包球重叠不证明真实接触，无 contact 也不单独证明 release=True。视频或关键帧只辅助查看，不覆盖物理判据；本任务不要求额外 MP4 或额外 native render。

即使所有对照匹配，只能称“从原保存初态重执行同动作前缀，可观测证据匹配”。旧 run 没有每步完整 native checkpoint，因此不能宣称精确恢复了旧 step280 全部不可见 solver/controller 状态。新快照属于此次诊断，不是通用恢复系统，也不调用 `mj_setState` 恢复中间帧。

旧 `calibrated=false`、`selected_threshold=null` 及保守 unknown 全部保留。0.99仍只是原诊断网格点。当前292步预算不重证τ292之后的K4；追加至296、W150、init37或协议修改，都需要新的明确授权。

native 计数只覆盖监测列表中的 Python API 入口，内部 C 调用不另行计数，XML 序列化的 `mj_saveLastXML` 也不在该列表。当前二进制、robosuite 源码和资产 SHA 描述此次运行；旧产物未记录的历史摘要不能被倒推为逐字节相同。LIBERO 源码／资产则由原环境的实时内容 fingerprint 与冻结 bank 强制匹配，并保留于 `source_plan.json`。只读指纹覆盖已声明的 integration、ctrl、OSC、gripper 和已发现的 Python/NumPy RNG 字段，不声称覆盖所有潜在 Python 隐状态。
