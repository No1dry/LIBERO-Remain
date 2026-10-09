# 单任务官方 / Remain 00 能力回归

此入口属于 [任务 003](../collaboration/tasks/003_normal00_regression_entry.md)：先检查同一模型在正常、尚未完成的任务上能否工作，再解释部分完成状态的表现。首轮范围固定为同一份 SOG10 OpenVLA-OFT checkpoint、`basket`、官方初态索引 `0 1 2 3 4`、policy seed `7`。它是 capability regression，不是完整的 `00/10/01/11` benchmark，也不扩展到六模型矩阵。

本轮交付代码和 CPU/fake-policy 验证；尚未执行这批真实 GPU 回归，没有新的官方成功率或 Remain 成功率。后续真实执行须使用经过 Codex 审查的版本和明确命令。已有单来源失败不能据此解释为普遍能力不足或剩余目标选择缺陷。

## 两种协议

| 项目 | `official` | `remain` |
|---|---|---|
| 环境解释器 | 模型配置的 `runtime.python_executable`，创建官方原生 LIBERO 环境 | 当前独立 LIBERO 仿真解释器；模型仍在隔离 worker 中 |
| 初态来源 | 官方任务的 `initial_states[index]` | 同一官方 index，走新的独立 00 准备流程 |
| 环境随机种子 | 官方 `get_libero_env()` 的 `env.seed(0)` | 现有构造口径：`env_seed=index` |
| 准备与等待 | 恢复官方初态后执行 10 步官方 dummy action | 80 步 HOLD settle，再做静态检查及 150 步 HOLD 技术验收；执行时恢复验收前保存的状态 |
| 策略预算 | 最多 `H=520` 个策略动作 | `H=520`，之后继续 `W=150` 步，完整窗口为 670 步 |
| 成功后行为 | 评测器按官方成功终止规则结束 episode | success 不让模型提前停车，继续到窗口结束 |
| 模型主动 STOP | 评测器成功终止不算模型 STOP；当前 OFT 没有 STOP 输出 | 保持既有 runner 契约，不根据目标真值伪造 STOP |
| 原生分数 | 官方成功终止口径单列 | 既有 remaining / preservation / stable / joint 等分数保留 |

本入口每个 task/index/protocol 使用独立子进程，每个 episode 的 `SubprocessPolicy` 重置 policy seed 为 7、清空 harness 动作队列。**官方原脚本在评测开始时设置一次 seed；本入口逐 episode 重置 seed，不是同一随机流安排。** 该差异与实际解释器、LIBERO/robosuite/MuJoCo 版本、源码 revision、观测时序和机器人初态一起记录。

同一初态 index 只保证来源可对应，不保证等待、settle 后的物理状态或机器人姿态相同。官方原生观测缓存与 Remain 的刷新/恢复规则也有差异。两协议的分差不能仅归因于模型、等待步数或某一个接口修复。

OFT 预处理、归一化和动作转换复用现有官方 API 适配器。该适配器已输出环境坐标下的 `(8, 7)` 动作块；驱动不能再次调用夹爪归一化或符号翻转。模型仅收到原始完整指令、白名单图像与本体观测，不接收完成 mask、目标谓词或对象真值。官方函数依据见本文末尾的固定源码链接。

## 配置与 dry-run

先按 [六模型指南](remaining_goals_six_model_evaluation.md)准备实际可用的 OFT 配置。下面的 local JSON 必须指向本轮冻结的 SOG10 checkpoint、完整统计量和正确的模型解释器；不能直接用示例权重路径替代实际实验身份。保留 `execution.random_seed=7` 与 `execution.max_chunk_steps=8`，记录 checkpoint、代码和归一化身份。

```bash
mkdir -p configs/remaining_goals/local
cp configs/remaining_goals/runtime/openvla_oft_sog10.json configs/remaining_goals/local/openvla_oft.json
```

在该副本中填写 `runtime.python_executable`、`adapter_options.repo_path`、`adapter_options.checkpoint` 的绝对路径。模型来源冻结为 [SOG10 snapshot](https://huggingface.co/moojink/openvla-7b-oft-finetuned-libero-spatial-object-goal-10/tree/638918f3d1c2e43a39a8a20772bdb8b91835e4b7)，OFT 源码冻结为 `e4287e94541f459edc4feabc4e181f537cd569a8`。配置里的来源声明不等于逐字节验证本地权重；实际加载身份与统计量摘要进入每条 episode 的 provenance。

官方子进程使用模型 Python 中**已经配置好**的原生 LIBERO（上游依赖要求 robosuite 1.4.1）；Remain 使用本库安装的仿真 Python（robosuite 1.4.0）。官方子进程不继承 launcher 的 `LIBERO_CONFIG_PATH`，默认使用原生 `~/.libero/config.yaml`。若原模型已有自定义配置目录，可在 runtime 中增加 `"official_libero_config_path": "/absolute/existing/libero-config"`，指向已存在的 `config.yaml` 所在目录；此项仅传给官方子进程。配置缺失时直接记录错误，不触发上游交互初始化。入口不安装依赖、不改官方配置、权重或既有环境。真实执行前确认该模型解释器可以在原工作流中创建 LIBERO 环境。两种原生环境中都要有录像编码依赖才能保存对应协议视频；缺失编码器会独立记错。dry-run 不检查这些资源。

```bash
python scripts/remaining_libero.py regression \
  --config configs/remaining_goals/local/openvla_oft.json \
  --task basket --indices 0 1 2 3 4 --protocol both \
  --out reports/basket_normal00_regression_001 \
  --dry-run --plan-out reports/basket_normal00_plan_001.json \
  --save-video --video-fps 20 --video-camera both --video-stride 1
```

`--protocol` 可选 `official`、`remain` 或 `both`。首轮 `both` 的计划必须恰有 5 条 official 与 5 条 Remain 00；每个 index 在每个协议中只出现一次。索引列表显式指定，不自动改为“前五个可成功运行的初态”，不补跑其他 task 或 partial mask。

dry-run 只生成计划，不加载模型、不创建仿真、不下载权重，也不创建 `--out`。可选 `--plan-out` 写入另一个尚不存在的 JSON 文件；后续实际运行可以使用同一个尚不存在的 `--out`。计划应显示准确 task name、suite、indices、protocol、checkpoint/seed、各阶段预算和总 episode 数；资源或模型尚未实查时不能把计划当作已验证的运行结果。

代码验收后的实际执行命令去掉 `--dry-run` 和 `--plan-out`：

```bash
python scripts/remaining_libero.py regression \
  --config configs/remaining_goals/local/openvla_oft.json \
  --task basket --indices 0 1 2 3 4 --protocol both \
  --out reports/basket_normal00_regression_001 \
  --save-video --video-fps 20 --video-camera both --video-stride 1
```

输出必须是全新路径，不能覆盖历史实验。录像默认关闭；这里建议启用两路相机、每步采集。fps 是播放帧率；增大 stride 但保持 fps 会快放。录像错误独立记录，不改变策略分数；录像、step0 观测和首动作是排查接口差异的证据，不能当作已经完成人工 UIR 审核。

输出中的 `plan.json` 保存固定计划，`model_config.json` 保存解析后的本地路径，`run.json` 保存逐条尝试日志，`summary.json` 分协议汇总。`requests/0000.json` 与 `logs/0000.log` 对应 `cases/0000/episode.json`；编号顺序是 index 外层、协议内层。每个 case 保存 step0 NPZ、可选 `videos/episode.mp4`；Remain 另有 `preparation/preparation.json`、状态和原技术验收证据。所有路径属于本次新输出。可用 `--case-timeout-seconds` 限定单条总耗时；默认上限含模型启动、最多 84 次推理超时和 600 秒准备余量，属于故障限时而非性能预测。

## 独立 00 状态的身份

本入口新建 00 状态，不复用旧 state bank，也不为此强制构造另外三个 mask。准备产物使用独立 schema `remaining-goals-capability-statebank-v1`，目的为 `normal00-capability-regression`，明确 `complete_paired_benchmark=false`。它不能伪装成通过完整配对验证的标准 benchmark manifest。

Remain 准备在该 case 的 `preparation/` 新目录中进行：恢复指定来源、80 步 HOLD settle、核对目标均为 false、保存验收前状态与机器人参考姿态，再执行既有静态及 150 步动态技术验收。正式 rollout 用新的 `LiberoGoalEnv` 恢复该保存状态，不从技术验收最后一步继续，也不额外增加 10 步 official wait。

记录官方 init 文件及选中数组的 SHA-256、保存状态 SHA、BDDL/XML、环境身份及冻结源码哈希。准备失败单列为 `preparation_error`，不更换 index、不创建策略后再按其成功与否筛状态。技术稳定仍不自动证明任务的语义可见性或剩余可执行性。

## 计分与失败分母

共同可比较字段是**预算内 all-goals-ever success**；截至策略动作 H（含 H）曾同时满足全部目标。Remain 的稳定保持与 joint success 另外报告，不把它们直接等同于官方原生成功率。等待/settle、策略步骤和保持步骤分别计数；不能把等待动作吃进 520 步预算，也不能重复等待。

official 在第一个策略动作后成功时，实际策略步数为 1；不能用原脚本 break 前尚未递增的循环计数推成 0。官方成功短轨迹是该协议的正常终止，不补造后续轨迹，也不送进要求完整 670 步的 Remain 指标函数。Remain 在第 520 步后首次成功不算预算内成功；在保持窗口失败则按既有指标记录。

汇总分别列出 official 与 Remain 的 expected、attempted、完整协议执行数、准备错误、加载/运行错误和 missing。完整执行包括“预算耗尽但任务未成功”，不等于任务成功。固定计划保留全部 10 条身份；异常不从 expected 分母消失，未尝试的条目不伪装成已经尝试。

`prepared` 与 `policy_started` 单独计数。编排器捕获子进程异常并生成错误记录时，若无法确认这两个阶段是否发生，则记为未知（null），汇总另外列 unknown 数量。全局中断尚未生成结果的 case 保留在 attempted 与 missing 中，不凭空生成阶段状态；未进入的后续 case 只保留在 expected 与 missing 中。部分证据不计入有效完整记录。

有效完整 episode 的成功比例与以 expected 为分母的保守覆盖分数应明确区分。错误短轨迹即使记录了曾经满足目标，也只能保留为观察证据，不能冒充一次有效完整成功。共享启动失败、进程异常退出、结果文件缺失都必须显式留下状态或缺失清单；不得默认为 false 后声称都是策略失败。

每条至少保留 task name、suite、准确 index、环境与策略 seed、模型/代码/归一化身份、原指令、实际准备/等待步数、step0 观测、首动作、结束原因、控制步数、trace、视频状态和耗时。相同状态与同 seed 的确定性重复不增加独立样本数。当前回归不自动产生 UIR 标签。

## 预算与当前验证范围

5+5 条均走满预算时：

- official：`5 × 520 = 2600` 个模型动作，另有 `5 × 10 = 50` 个等待动作。
- Remain：`5 × (520 + 150) = 3350` 个模型动作，另有 `5 × (80 + 150) = 1150` 个准备/技术验收动作。
- 模型动作与 official 等待共 6000 个控制步；加上上述 Remain 准备/验收为 7150 个控制步。成功早停或错误会减少实际执行数，报告以实际记录为准。

每 case 独立加载一次模型，十条完整运行通常需要十次加载；准备提前失败的 case 不加载模型。不能把控制步数除以控制频率当作墙钟时间：模型加载、推理、渲染与状态验收均有开销。墙钟耗时尚未测量，此处没有 GPU 性能承诺。

当前代码验证应覆盖索引精确映射、队列重置、等待不重复、预算边界、不同终止语义、完整计划覆盖、失败/缺失分母、输出不可覆盖、历史结果只读及模型输入不含真值。fake-policy 或 synthetic 测试证明软件契约，不证明官方模型分数已复现。正式执行和解释结果仍等待 Codex 审查。

## 固定源码依据

- [官方 OFT 评测入口](https://github.com/moojink/openvla-oft/blob/e4287e94541f459edc4feabc4e181f537cd569a8/experiments/robot/libero/run_libero_eval.py)：配置、520 步预算、10 步 wait、逐 episode 动作队列与成功终止。原生循环会捕获异常，回归入口须额外保留错误身份。
- [官方 LIBERO 工具](https://github.com/moojink/openvla-oft/blob/e4287e94541f459edc4feabc4e181f537cd569a8/experiments/robot/libero/libero_utils.py)：环境构造、env seed 0、dummy action 及相机方向。
- [本库 OFT 适配器](../benchmark/remaining_goals/adapters/openvla_oft.py)与[公共动作转换](../benchmark/remaining_goals/adapters/openvla.py)：官方模型 API、统计量选择及已经完成的动作映射。
- [Remain 协议](remaining_goals_benchmark.md)与[人工 UIR 边界](remaining_goals_uir.md)。
