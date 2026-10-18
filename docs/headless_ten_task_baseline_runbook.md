# Stage05：十任务、100条原始OFT基线

对应[Plan5](experiment_plans/stage05_ten_task_baseline.md)与[011](../collaboration/tasks/011_headless_ten_task_baseline.md)。本入口使用独立协议 `remaining-headless-goal-endpoint-v1`。代码验收后由Codex填写服务器路径、部署；**用户亲自启动所有真实状态构造、独立回放和模型评测**。本次软件交付只执行CPU/fake测试。

**Task012 可选范围验收**：已有 mask10 状态与回放齐全时，可在独立 checkout 中只读复用，显式启用 mask10 验收，避免被未选 00/01/11 失败阻塞。见[配置复制与运行说明](task012_mask10_scoped_acceptance.md)；不要因此重做 prepare/replay 或修改运行中的旧准备。省略新配置项仍保留本页默认的全 mask 验收。

## 固定范围

每任务官方初态索引 `0..9`，仅 `mask10`，policy seed 7，共100条。不是同一个状态重复10次。basket 0..4 已用于开发，记录 `development_source=true`，不声明全体未见测试。

| 轨道 | 任务 | 模型episode |
|---|---|---:|
| LIBERO-10 primary | basket、stove、basket_cheese_butter、basket_soup_cheese、dual_mugs、mug_pudding | 60 |
| LIBERO-90 zero-shot extension | frypan_stove3、frypan_stove9、cabinet_close_top_bowl、cabinet_close_bottom_open_top | 40 |

不额外运行模型smoke、probe、00、01、11、校准或失败重跑。完整配对状态的离线构造/回放仍复用已有程序，物理控制步和耗时单列，不计入100条模型预算。已有basket五来源不足以冒充十来源完整包；其余任务须实际准备和核验。

## 环境与模型配置

复用已经部署好的仿真Python与OFT模型Python，不升级依赖、不重装权重。仿真Python负责LIBERO、MuJoCo、状态、指标和视频；独立worker用 `runtime.python_executable` 加载OFT。使用解释器原路径，包括venv符号链接，不用 `readlink -f` 将其改成base Python。

固定源码[OpenVLA-OFT e4287e9](https://github.com/moojink/openvla-oft/tree/e4287e94541f459edc4feabc4e181f537cd569a8)，固定已有官方[SOG10 checkpoint 638918f](https://huggingface.co/moojink/openvla-7b-oft-finetuned-libero-spatial-object-goal-10/tree/638918f3d1c2e43a39a8a20772bdb8b91835e4b7)。本轮无需另下载90权重或FINISH头；既有完整本地snapshot包含VLA/LoRA配置、action head、proprio projector、dataset statistics。模型仍走官方原始动作解码、center crop、双图像、proprio、L1、chunk8。

复制[运行时模板](../configs/remaining_goals/runtime/openvla_oft_sog10.json)与[批次模板](../configs/remaining_goals/headless/batch.example.json)，只在忽略的local目录填写真实路径。以下为Linux Bash；先在仓库根目录执行文件准备：

```bash
mkdir -p configs/remaining_goals/local
cp configs/remaining_goals/runtime/openvla_oft_sog10.json configs/remaining_goals/local/stage05_oft.local.json
cp configs/remaining_goals/headless/batch.example.json configs/remaining_goals/local/stage05_batch.local.json
```

编辑 `stage05_oft.local.json`：`runtime.python_executable` 为既有OFT conda/venv Python绝对路径，`adapter_options.repo_path` 为固定OFT checkout，`checkpoint` 为固定snapshot，按服务器填写 `cuda_visible_devices`。保留suite10、revision、checkpoint_source、seed7、chunk8、center_crop=true和非量化设置；无 `finish` 字段。编辑 `stage05_batch.local.json` 的 `runtime_config` 为 `stage05_oft.local.json`；检查全部十组 `manifest`/`candidate_replay` 路径。批次层相对路径以批次JSON目录为基准；runtime内部模型路径沿用原约定，以仓库工作目录为基准，因此推荐绝对路径。

模板保留明确的 `extension_transfer`：SOG10训练域为 spatial/object/goal/10，normalization suite为10，actual key为 `libero_10_no_noops`，evaluation track为 `libero_90_zero_shot`。程序派生的90运行时顶层和adapter suite始终是90。仅该固定来源/模型组合允许显式迁移，其他配置不获得跨suite回退。

实际加载后、任何动作前验证并在批次内比较：checkpoint路径及声明来源、实际stats文件SHA/所用统计内容SHA、实际key、官方推理文件SHA、action/proprio组件SHA、推理配置和准备后的checkpoint代码SHA。每条raw与执行证据绑定完整worker metadata。**这些不等于全部大模型权重字节校验**，`checkpoint_bytes_verified=false` 保留；部署者仍应冻结已有权重文件和来源清单。

## 启动方式

两种方式择一，均需从冻结checkout根目录运行。以下所有路径由Codex在部署时填成实际值，不含机器私有路径。

1. 已有本checkout的 `.runtime/remaining_libero/runtime.json` 时：

```bash
python scripts/remaining_libero.py headless --help
python scripts/remaining_libero.py headless budget-plan
```

launcher复用runtime.json中的仿真解释器、LIBERO配置及GL设置。`headless` 后参数原样转发。

2. 直接使用既有仿真conda/venv解释器。Linux EGL示例：

```bash
SIM_PY=/absolute/path/to/simulation/env/bin/python
export LIBERO_CONFIG_PATH=/absolute/path/to/existing/libero/config_directory
export MUJOCO_GL=egl
export PYOPENGL_PLATFORM=egl
"$SIM_PY" -m benchmark.remaining_goals.headless.cli --help
"$SIM_PY" -m benchmark.remaining_goals.headless.cli budget-plan
```

`LIBERO_CONFIG_PATH` 是已有 `config.yaml` 所在目录。使用已验收的GL设置；Windows用现有GLFW环境，PowerShell调用形式为 `& $SimPython -m benchmark.remaining_goals.headless.cli ...`。无需激活另一个模型conda环境；worker会调用配置指定的模型Python。编码依赖复用仿真环境中已安装的 `imageio`/`imageio-ffmpeg`；缺失时由部署者在该解释器补齐仓库 `[video]` 可选依赖，再交用户命令，不把安装或CPU示例当成额外模型smoke。

下面统一用直接解释器形式；使用launcher时将 `"$SIM_PY" -m benchmark.remaining_goals.headless.cli` 替换为 `python scripts/remaining_libero.py headless` 即可。

## 真实状态准备：用户启动

每个任务独立目录，全套旧构造器生成00/10/01/11并独立回放，目标固定为索引0..9。构造与回放某任务失败时保留失败文件，继续其他任务，不替换来源。两个根目录第一次运行须不存在且互不包含。

```bash
"$SIM_PY" -m benchmark.remaining_goals.headless.cli prepare \
  --data data/stage05_headless --reports reports/stage05_preparation --track primary
"$SIM_PY" -m benchmark.remaining_goals.headless.cli prepare \
  --data data/stage05_headless --reports reports/stage05_preparation --track extension
```

也支持 `--track all`。输出 `reports/stage05_preparation/preparation.json`，每任务两份命令日志、`00.control_steps.json`（build）、`01.control_steps.json`（replay），以及 `replay/replay_report.json`。计数范围是原构造/回放主动发出的控制step，不是MuJoCo积分子步；不含reset内部forward。记录attempted/completed/异常调用数、elapsed、ledger SHA。异常调用可能已推进仿真时实际总数为null/partial_unknown；缺失或未finalize的ledger为unknown，不冒称零。计数包装不添加step、query或RNG调用。

相同准备根再次执行只跳过已登记任务，包括失败任务；不存在自动retry。退出码2表示有任务未ready，其他任务的完整产物仍保留。原始候选仍保留 `construction.legal=false` 等事实；物理回放通过不证明语义合法性或剩余任务可达。不要编辑XML/state SHA绕过校验。

## 文件检查与冻结

只读文件规划不创建仿真、不加载权重，可在已就绪部分任务存在时运行：

```bash
"$SIM_PY" -m benchmark.remaining_goals.headless.cli dry-plan \
  --config configs/remaining_goals/local/stage05_batch.local.json \
  --out reports/stage05_plan_001
```

`plan.json` 永远保留预定100条；`ready_episodes` 与各task错误明确列出。每个ready task要求完整十个mask10来源、原始完整配对bank、真实state SHA及独立回放证据，不把未就绪任务从分母移除。Codex读取并冻结状态清单后交用户启动命令。输出目录必须新建；此命令成功退出只表示报告生成成功，不表示所有任务已ready。

## 真实模型批次：用户启动

```bash
"$SIM_PY" -m benchmark.remaining_goals.headless.cli run \
  --config configs/remaining_goals/local/stage05_batch.local.json \
  --out reports/stage05_baseline --track primary
"$SIM_PY" -m benchmark.remaining_goals.headless.cli run \
  --config configs/remaining_goals/local/stage05_batch.local.json \
  --out reports/stage05_baseline --track extension
```

两轨共享同一个批次根及固定100分母，仍逐任务执行。未准备任务不创建模型；其他ready任务可继续。每条执行前登记attempt，技术失败暂停该任务剩余条目，继续其他任务。完成任务读取证据后跳过，已失败/不完整任务也不会重新运行。之前尚未尝试的任务可在准备完成后用原配置、原代码、原批次根启动；运行后勿修改配置/源码，身份变化会拒绝继续。不要用新输出目录绕过失败账本额外补跑。

`H=520`、20Hz、K=4（5个相邻观测）、chunk8。全部官方目标真且相关可移动目标已释放，确认后在该控制步结束，chunk剩余动作丢弃，不再query，不追加W150/开爪/归位。关节目标无释放要求。端点是评价器GT截断，不是模型STOP；模型只有原完整指令和原图像/proprio。意外STOP为技术错误。已确认违规不会提前结束轨迹，仍到同一目标端点或H。

## 离线核验、汇总与产物

```bash
"$SIM_PY" -m benchmark.remaining_goals.headless.cli inspect --run reports/stage05_baseline
"$SIM_PY" -m benchmark.remaining_goals.headless.cli summarize \
  --run reports/stage05_baseline --out reports/stage05_summary_001
```

inspect/summarize不调用模型或仿真。summarize必须写到原批次外的新目录。自动及派生报告均有 `summary.json`、`report.md`、`episodes.csv`。单条损坏明确显示为未验证工件，保留同任务其余已验证结果；整个任务的源manifest或模型身份损坏才隔离全任务。明确的录制失败raw保留technical_error/partial_evidence，不重写原始结果或偷偷纳入成功；所有预定条目始终保留。

批次目录包括：

```text
batch.json                         固定100列表、配置/源码、实际共享模型身份、任务状态
plans/000.json                     每次启动的不可覆盖就绪清单及hash
tasks/<task>/task_run.json          attempts、错误阶段、missing、raw引用和hash
tasks/<task>/source/                原manifest和独立replay报告字节快照
tasks/<task>/raw/<episode>.json     逐控制步trace、真实动作/query/chunk、GT、事件、TCP及L
tasks/<task>/evidence/<episode>/    实际step0/query白名单观测NPZ及execution.json
tasks/<task>/videos/<episode>.mp4   原观测双相机拼接、20fps、stride1、含step0
summary.json / report.md / episodes.csv
```

所有已完成模型episode必须有完整双相机视频；编码失败为技术故障，保留已执行trace。t0不符合10直接记invalid_initial_state，不自动修复。按步保存同一native `eef_site_id`/gripper `grip_site` 的world xyz，缺步、换site、NaN拒绝有效路径；L为所有相邻控制步欧氏增量之和，含确认步，不回溯裁短。

每任务主表只报合规成功率 `% (n/10)`、成功条件平均L（米）及覆盖 `n/10`。无成功为N/A。分别汇总6任务主轨和4任务扩展轨，成功率按任务等权；路径先每任务平均，再在有成功任务间等权，同时显示任务覆盖。100条混合汇总仅描述性。诊断另报未合规过滤的官方目标事实、步数、失败原因、technical/unknown/missing及有效覆盖；不把缺失算作正常策略失败。

## 自动事件边界

A官方谓词任一步回退即sticky失败。无关可移动物体的双pad夹持与初态上抬至少2cm同时持续K4才算wrong_grasp。wrong_placement使用该任务官方In/On容器/支撑关系：初态不存在的新关系、释放、持续K4；初态已有关系不要求清理。目标及有任务作用的容器/支撑/关节部件不列为普通干扰物。

table_drop检查初态确有工作台支撑的**非目标可移动物体**（包括相关篮子/盘子）：整个collision世界z上界低于原工作台支撑面2cm且持续K4。工作台支撑用初态真实顶面contact和水平box collision面证明，不把body中心距离当支撑；无直接接触的间接支撑尚未建立支撑图，明确unknown。倾斜/轻碰/普通位移只记录，不临时加罚。所有事件确认后sticky，移回不抹除。

复用010 PR #7中只读保守几何证书的纯函数副本（代码注明来源），未合并010，也不改变旧FINISH/runner默认。未知collision形状、接触过滤覆盖或不可用的官方关系/释放证据保留unknown，不当作无违规；机器人/TCP/角色身份不一致为技术错误。本版只检测这些有明确物理证据的事件，不能识别所有语义冗余或场景损坏；没有新几何校准、VLM裁判、FINISH训练或真实性能证明。
