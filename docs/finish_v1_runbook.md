# Stage04 FINISH-v1 用户运行手册

版本：2026-10-13；任务 [007](../collaboration/tasks/007_finish_protocol_and_stop_calibration.md)，研究依据 [Plan4](experiment_plans/stage04_finish_protocol.md)。这是 X 的候选运行手册。Codex 验收并上传冻结代码后，须把下面的绝对路径、SHA、解释器和已安装资产填写为服务器实值。**本次交付没有运行真实 MuJoCo、真实数据恢复、真实 VLA 前向、真实数据训练、校准或模型评测。** CPU/fake 通过只说明软件合同，不代表真实停止能力。

每个命令独立执行并查看产物后再进行下一步。没有自动训练→评测流程、后台排队或自动补样。全部真实实验由用户启动、运行、暂停和监督；X 交代码与软件测试，Codex 审查、部署及填写最终机器命令。

## 1. 范围、指标与证据

仅 `libero_10` 的 basket 双目标任务，保持官方完整指令；使用现有官方 SOG10 OFT checkpoint。动作网络、LoRA、L1 action head 和 projectors 冻结。新增头只读**同一次原 forward 中 L1 实际使用的 `(B,56,D)` action-token hidden**，在 56 个位置均值池化；不含 EOS/prompt/patch，不增加动作 forward，不接收 goal/mask/source/step/H 等 evaluator metadata。

头为 FP32 `LayerNorm(D) → Linear(128) → GELU → Linear(1)`，无 dropout。默认 seed7、AdamW、lr0.001、wd0.0001、batch128、最多50epochs。训练 BCE 的正类权重只用 train 的 `Nneg/Npos`；按普通 validation BCE 最低选 epoch，同分选最早。只更新小头。安全 NPZ 记录权重、架构、输入特征版本、实际 base 文件/参数/代码身份、数据/split/标签合同、超参数和所选 epoch。

| 项目 | FINISH-v1 定义 |
|---|---|
| H / W / chunk | 所有 mask 都为 H520 / 退出后 W150 实际控制步 / chunk8 |
| 查询时刻 | t0；已接纳 chunk 消耗完；H 时仍有一次实际查询 |
| active | `p >= threshold` 应用 FINISH；H 时 FINISH 优先，否则 TIMEOUT；退出 query 候选动作执行0步 |
| shadow | 记录 head_decision，但继续原候选动作至 H；H 应用 TIMEOUT；不把预测 FINISH 当成真实退出 |
| 保持 | FINISH 和 TIMEOUT 都恰好150步，无再次 predict，无冻结仿真，无 GT 开爪修复 |
| 主项 | 合规 FINISH 成功百分比和 n/N，N 为完整预定集合；technical/unknown/missing 另报覆盖率 |
| 不支持 FINISH / shadow | 新主项 N/A，不记0%；旧无FINISH模型仅历史参照 |
| 成功条件 | 决策 f 当下全目标满足且目标物体释放；初始成果在0..f+W始终保持；全目标在f..f+W保持；无禁止投放 |
| 禁止投放 | 初始篮外的非目标可移动物体入篮、释放并保持K=4个控制间隔；事件一旦确认即保留 |
| 排除 | 篮子/桌面/固定物体、初始篮内额外物体、短暂经过、纯接触 |
| 稳定计数 | K 个实际控制间隔对应 K+1 个连续状态；支持离线K=1/4/8敏感性分析 |
| 多标签失败 | premature_finish、no_finish_timeout、unfinished_goal、goal_regression、forbidden_placement、unstable_after_exit |
| 延迟 | 首个全目标满足且释放的稳定区间起点 τ；有效11的τ=0；报告f−τ及覆盖，timeout/early/no_tau/unknown单列 |

新主项不是旧 JSR/UIR，也不证明全过程没有冗余尝试。允许预算内无破坏的重复尝试仍可能成功。旧11策略窗口与新H520不同，禁止混分/覆盖旧结果。head 分组隔离仅约束新增头；没有证据时不得声称官方 SOG10 动作网络从未见过这些 LIBERO 来源。

每个 run 保存 `run.json`、`raw/*.json`、`evidence/*/execution.json`、实际初始观测、每个 query 的原始预处理张量与两路实际 crop PNG、`videos/*.mp4`、`summary.json`、`report.md`。query 记录候选/接纳/执行动作、logit/p/阈值/头身份、head_decision/applied_decision；hold 单列 finish/timeout 原因。录像复用已有观测，不额外 render/reset/step。录像、头、概率、关键证据或保持接口失败会暂停余下集合，保留 partial 和 missing；普通策略失败继续。

## 2. 已有环境与资产

复用已验收的仿真环境和 OFT 模型环境，不升级原模型依赖来救分。源码需要 Python3.10–3.12。仿真侧需该项目固定 LIBERO/robosuite/MuJoCo、NumPy、HDF5读取包 h5py、录像包 imageio/imageio-ffmpeg；读取 `.pruned_init` 优先 `torch.load(weights_only=True)`，官方旧NumPy序列格式使用严格NumPy白名单的受限Unpickler回退，拒绝任意代码global。也支持无pickle的二维 `.npy`。头训练可用模型 Python 的现有 PyTorch。特征与 parity 在 OFT worker 内运行，父进程不导入模型库。

官方来源：

- [LIBERO 源码、资源与数据说明](https://github.com/Lifelong-Robot-Learning/LIBERO)。需要 basket 原始 normal00 demonstration HDF5、对应官方 `.pruned_init` 和 BDDL。HDF5 必须有 `data/*/states` 及相应 model XML；不能拿图像-only数据冒充可恢复状态。
- [OpenVLA-OFT 官方源码](https://github.com/moojink/openvla-oft)，沿用仓库配置固定 revision `e4287e94541f459edc4feabc4e181f537cd569a8`。
- [官方 SOG10 checkpoint](https://huggingface.co/moojink/openvla-7b-oft-finetuned-libero-spatial-object-goal-10/tree/638918f3d1c2e43a39a8a20772bdb8b91835e4b7)，沿用已有 snapshot；不是新增或替换六模型评测权重。
- 现有 basket 来源0..4的 Remain 状态包与通过的独立 replay 报告。候选包继续 `legal=false`；不伪造正式发布审批。

先按第3节定义解释器和工作目录，再由用户按实际需要安装轻量补充项；不会自动启动实验：

```bash
"$SIM_PY" -m pip install -e '.[video,finish-data]'
"$MODEL_PY" -m pip install -e . --no-deps
```

如果只是软件测试，`.[test,video,finish-data]` 加现有 CPU PyTorch 即可；测试只生成 tiny 合成数据和 fake 环境。不要执行历史 `bootstrap ... --phase all` 作为本阶段测试，它会真实构建/回放环境。

## 3. 工作目录与私有配置

下面为 Linux Bash 示例。**先把 `/ABS/...` 改成实际路径；变量定义本身不启动实验。** 已记录的服务器工作根为 `/HUBU-AI096/zp/ICML`，旧资产参考checkout为 `/HUBU-AI096/zp/ICML/LIBERO-Remain-stage03-pilot-04508dc`；历史launcher使用 `/root/anaconda3/envs/peft-openvla/bin/python` 与checkout内 `.runtime/remaining_libero/venv/bin/python`。这些是历史路径线索，不冒充本次已部署/核验的新路径。Codex应在该工作根部署新的stage04冻结checkout，并从旧私有runtime核对模型Python/源码/checkpoint后填入下列变量。不要将凭据或模型权重提交到 GitHub。每个 `--out` 必须是全新目录；日志同样用新的文件名。

```bash
REPO=/ABS/ACCEPTED_LIBERO_REMAIN
SIM_PY=/ABS/SIM_ENV/bin/python
MODEL_PY=/ABS/OFT_ENV/bin/python
CFG=/ABS/PRIVATE_CONFIG/task007
OUT=/ABS/NEW_RESULTS/task007_run01
LOG=/ABS/NEW_LOGS/task007_run01
cd "$REPO"
mkdir -p "$CFG" "$OUT" "$LOG"
set -o pipefail
git rev-parse HEAD
"$SIM_PY" -m benchmark.remaining_goals.finish.cli --help
```

在Windows用对应 `Scripts/python.exe` 与 PowerShell 路径/引号；不要直接粘贴 Bash 的 `set -o pipefail`。所有命令的cwd均为 `$REPO`；模型worker也固定在该checkout启动。

将以下模板复制到 `$CFG` 后手工填写绝对路径：

| 私有文件 | 模板／填写规则 |
|---|---|
| `oft_sog10.json` | [`runtime/openvla_oft_sog10.json`](../configs/remaining_goals/runtime/openvla_oft_sog10.json)：runtime.python_executable=`$MODEL_PY`，adapter_options.repo_path/checkpoint为已验收真实路径，保留suite/revision/seed/chunk8/crop |
| `data.json` | [`finish/data.example.json`](../configs/remaining_goals/finish/data.example.json)：实际HDF5/init/BDDL、官方原指令，显式state_stride；不要猜trajectory_source_map |
| `validation_shadow.json` | [`validation_shadow.example.json`](../configs/remaining_goals/finish/validation_shadow.example.json)：normal_bank、runtime、训练出的head目录 |
| `normal_active.json` | [`normal_active.example.json`](../configs/remaining_goals/finish/normal_active.example.json)：同头、normal_bank、冻结calibration |
| `remain_active.json` | [`remain_active.example.json`](../configs/remaining_goals/finish/remain_active.example.json)：现有Remain manifest/replay、同头、冻结calibration |
| `remain_shadow.json` | [`remain_shadow.example.json`](../configs/remaining_goals/finish/remain_shadow.example.json)：可选15条诊断，主项N/A |
| `preflight_source.json` | [`preflight_source.example.json`](../configs/remaining_goals/finish/preflight_source.example.json)：真实已有源包，填写一个实际episode_id |

统一入口为 `python -m benchmark.remaining_goals.finish.cli`；安装后等价console命令为 `libero-remain-finish`。`libero-remain`/`libero-pab`等旧入口仍沿用原协议。

## 4. 文件计划与来源审计

先做不读入真实dataset、不创建仿真、不加载权重的计划：

```bash
"$SIM_PY" -m benchmark.remaining_goals.finish.cli budget-plan 2>&1 | tee "$LOG/00_budget.log"
"$SIM_PY" -m benchmark.remaining_goals.finish.cli plan-data --config "$CFG/data.json" --out "$OUT/data_plan" 2>&1 | tee "$LOG/01_data_plan.log"
```

默认 rollout预算5条validation shadow+10条normal active+15条Remain active=30条，最大20100物理步；可选Remain shadow另15条/10050步。数据恢复/4步标签分支、normal准备、特征forward及parity费用另计；没有承诺其耗时。`data_plan/data_plan.json` 显示实际文件存在性、分组、采样stride和来源证据要求。缺文件只表示不足，不能据此宣称可训练。

默认 head 分组：train5..34、validation35..39、独立normal_test40..49、remain_test0..4以及这些来源的全部编辑变体。按 source/trajectory整组，不按单帧切分。

真实审计命令（用户运行）：

```bash
"$SIM_PY" -m benchmark.remaining_goals.finish.cli audit-data --config "$CFG/data.json" --out "$OUT/audit" 2>&1 | tee "$LOG/02_audit.log"
```

查看 `audit/audit.json`：只有 `status=ready_for_feature_export` 且无关键issues可继续。实现先读取states并检查来源映射/分组/资产；来源不足时不会创建仿真。唯一精确初态匹配可自动建立对应；**demo_35不代表init35**。演示第一状态因真实采集流程不等于官方初态时，必须提供真实采集追溯记录，而不能放宽哈希凑映射。`collection_provenance`条目需source_index、method，以及本次审计报告给出的HDF5/init文件hash、source_state hash、trajectory_initial_state hash、trajectory_id、`manually_confirmed:true`、`collection_record_source`、`reviewer`、`confirmation_reason`。文件hash在 `assets.*.sha256`，状态摘要在 `source_inventory.official_initial_states` 与 `source_inventory.demonstrations`；inventory本身不证明来源对应。这是用户确认真实来源记录，不是模型假定。缺资料保持unmapped；不声称官方公开数据一定具有足够来源对应。

若实际覆盖不支持默认分组，报告给出确定性候选或明确not_proposable；由用户与Codex确认独立替代分组后，把同一个 `split` 与 `alternative_confirmation` 加入数据和各job配置，重做新目录审计。`split`有train/validation/normal_test/remain_test四个整数组，remain_test仍固定[0,1,2,3,4]；确认格式为 `{"confirmed":true,"reviewer":"实际确认人","reason":"实际来源不足及替代依据"}`。候选算法保留已有held-out来源，缺val/test时优先从原train的高编号补齐，绝不把原test挪入train，也不会自动采用。禁止挑容易成功的替代源。原数据、审计不覆盖。

标签来自每个采样 saved state 的当前全目标+实际释放状态，正类还需从该状态按同一hold协议推进4步确认。先保存合法当前输入，再做被动分支，结束恢复原状态；未来示范任务动作不产生正/负标签。partial/unreleased/不满足为负；缺几何/释放/稳定证据为unknown且说明原因。cache验证重新从evaluator/hold证据推标签，不信任缓存里的label列。仅成功示范缺少失败/停滞负例会披露，不自动采额外rollout。

## 5. 特征导出与小头训练

```bash
"$SIM_PY" -m benchmark.remaining_goals.finish.cli export-features --audit "$OUT/audit" --runtime-config "$CFG/oft_sog10.json" --out "$OUT/features" 2>&1 | tee "$LOG/03_features.log"
```

查看 `features/feature_export.json` 和 `features/cache/cache.json`。只导出审计确认的train/validation已知标签，模型worker收到已存合法观测与原指令；不输入source/split/label。每个输入一次原OFT forward，同时捕获原L1输入、实际预处理张量与crop。缓存绑定raw/input/label/feature/base/code/split，拒绝非有限值、错误维度、缺类别、跨组或篡改。

独立启动小头训练（默认CPU；若用户修改device也记入artifact）：

```bash
"$MODEL_PY" -m benchmark.remaining_goals.finish.cli train --cache "$OUT/features/cache" --training-config "$REPO/configs/remaining_goals/finish/train.json" --out "$OUT/train" 2>&1 | tee "$LOG/04_train.log"
```

读取 `train/training.json`、`train/head/head.json` 与 `train/head/head.npz`。缺train任一类不训练；不借validation/test算pos_weight。这里没有加载/优化动作网络，base身份来自只读导出，CPUfake另验证冻结/梯度/参数hash。训练效果差属于研究结果，不自动调参或换checkpoint。把三个job中的head_artifact填写为这个新目录。

## 6. 环境与动作一致性预检

普通00验证与独立测试初态单独准备，不改既有Remain包。固定80步settle+150步稳定审计用于**初态准备**；执行退出hold使用另一个按当前EE姿态锁定的控制器，不能把准备时常量开爪动作当成退出hold。

```bash
"$SIM_PY" -m benchmark.remaining_goals.finish.cli prepare-normal --indices 35 36 37 38 39 40 41 42 43 44 45 46 47 48 49 --out "$OUT/normal_bank" 2>&1 | tee "$LOG/05_normal_bank.log"
```

检查 `normal_bank/normal_bank.json` status=prepared、15个固定来源、各自preparation.json、保存的settled base/初始观测及150步technical audit。这一步没有生成独立repeat-replay，也不伪称完整配对benchmark。遇技术失败保留剩余未完成来源，不替换来源。若使用已确认替代split，这里相应显式列出validation+normal_test来源，不改变Remain测试组。

真实释放/保持预检（将实际episode_id填入，建议检查11和未释放的代表状态；不自动增加模型rollout）：

```bash
"$SIM_PY" -m benchmark.remaining_goals.finish.cli preflight --source-config "$CFG/preflight_source.json" --episode-id basket_s000_11 --out "$OUT/environment_preflight" 2>&1 | tee "$LOG/06_environment_preflight.log"
```

具体ID以manifest为准；命令不会猜ID。输出初始观测、0..4真实hold trace、释放/接触/几何证据与hold_contract。退出控制限于已支持固定impedance delta OSC/Panda：锁定当前末端位置/朝向，用proprio误差逆缩放纠偏，gripper输入0保持已有finger目标；不按GT强制开爪。释放检测结合官方双指夹持、全gripper contact和碰撞几何到指间包络的保守距离。双指夹持→未释放；单指接触、仍在夹缝或几何缺失→unknown；仅无接触且几何清晰分离才released=true。unknown不会默认为释放。真实覆盖率/正确性必须检查本命令证据；CPU不证明仿真物理判定可靠。

独立32输入动作parity（不建仿真，仍是真实VLA前向）：

```bash
"$SIM_PY" -m benchmark.remaining_goals.finish.cli parity --audit "$OUT/audit" --runtime-config "$CFG/oft_sog10.json" --head-artifact "$OUT/train/head" --atol 0 --rtol 0 --out "$OUT/parity" 2>&1 | tee "$LOG/07_parity.log"
```

检查 `parity/inputs.json` 固定validation选集、去重与hash，`parity/parity.json` 32个逐输入原动作/shadow动作一致、max_abs_error、容差与worker RNG证明。原/新增分支在**同一模型worker**内恢复Python/NumPy/Torch/CUDA RNG；不能只重置父进程。共32×2次forward，不是32rollout。若GPU数值非确定性要求非零容差，必须在运行前明确设定并记录；不得事后放宽容差救通过。少于32个独立合法validation输入则不足，禁止抽test凑数。

## 7. Validation shadow 与冻结阈值

把normal_bank路径填入validation_shadow.json，再做文件级完整计划，然后独立启动运行：

```bash
"$SIM_PY" -m benchmark.remaining_goals.finish.cli dry-plan --config "$CFG/validation_shadow.json" --out "$OUT/validation_plan" 2>&1 | tee "$LOG/08_validation_plan.log"
"$SIM_PY" -m benchmark.remaining_goals.finish.cli run --config "$CFG/validation_shadow.json" --out "$OUT/validation_shadow" 2>&1 | tee "$LOG/09_validation_shadow.log"
"$SIM_PY" -m benchmark.remaining_goals.finish.cli inspect --run "$OUT/validation_shadow" 2>&1 | tee "$LOG/10_validation_inspect.log"
```

dry-plan核验现有source/head文件身份、固定5条、配置、录像及上限3350物理步；不会初始化仿真或反序列化模型。shadow记录的0.5仅为头判定占位阈值，实际applied_decision不受其影响。

离线阈值搜索是另一个用户命令：

```bash
"$SIM_PY" -m benchmark.remaining_goals.finish.cli calibrate --run "$OUT/validation_shadow" --out "$OUT/calibration" 2>&1 | tee "$LOG/11_calibration.log"
```

候选 `.05,.10,…,.95,.99`，每条轨迹按实际query先后只取首次越阈；要求观察到premature=0，再最大化τ后24步内正确FINISH比例，同分更高阈值。分母固定5条；不触发/未完成为未命中，未知/缺失/技术错使校准证据不完整。全部不FINISH、及时率0即使premature0也报告 `capability_not_established`，不能假称stop-capable。`calibrated`只表示完整validation证据得到有用候选，不证明独立normal active能力。shadow未来动作也不是反事实退出保持证明。

产物 `calibration/calibration.json` 绑定本head、源run和全部候选细节。只有完整有用候选才允许后续active配置通过；研究失败保存候选/原因，不自动用test改阈值。把normal_active、remain_active的calibration路径填写为此文件。

## 8. 独立普通停止能力与 Remain

先独立normal00 active10条：

```bash
"$SIM_PY" -m benchmark.remaining_goals.finish.cli dry-plan --config "$CFG/normal_active.json" --out "$OUT/normal_plan" 2>&1 | tee "$LOG/12_normal_plan.log"
"$SIM_PY" -m benchmark.remaining_goals.finish.cli run --config "$CFG/normal_active.json" --out "$OUT/normal_active" 2>&1 | tee "$LOG/13_normal_active.log"
"$SIM_PY" -m benchmark.remaining_goals.finish.cli inspect --run "$OUT/normal_active" 2>&1 | tee "$LOG/14_normal_inspect.log"
```

查看普通停止成功n/10、失败原因、完整覆盖和视频。Plan4建议的90%/10%仅是pilot沟通阈值，不是总体保证或软件验收标准。能力不足要先如实报告；用户/Codex决定是否仍执行冻结设计的Remain诊断，代码不自动启动。

Remain active15条（固定来源0..4×10/01/11；全H520，不跑00混入主分母）：

```bash
"$SIM_PY" -m benchmark.remaining_goals.finish.cli dry-plan --config "$CFG/remain_active.json" --out "$OUT/remain_plan" 2>&1 | tee "$LOG/15_remain_plan.log"
"$SIM_PY" -m benchmark.remaining_goals.finish.cli run --config "$CFG/remain_active.json" --out "$OUT/remain_active" 2>&1 | tee "$LOG/16_remain_active.log"
"$SIM_PY" -m benchmark.remaining_goals.finish.cli inspect --run "$OUT/remain_active" 2>&1 | tee "$LOG/17_remain_inspect.log"
```

可选Remain shadow是单独15条诊断，用户确认需要时自行执行：

```bash
"$SIM_PY" -m benchmark.remaining_goals.finish.cli dry-plan --config "$CFG/remain_shadow.json" --out "$OUT/remain_shadow_plan" 2>&1 | tee "$LOG/18_shadow_plan.log"
"$SIM_PY" -m benchmark.remaining_goals.finish.cli run --config "$CFG/remain_shadow.json" --out "$OUT/remain_shadow" 2>&1 | tee "$LOG/19_remain_shadow.log"
```

## 9. 只读重评分与交回结果

```bash
"$SIM_PY" -m benchmark.remaining_goals.finish.cli rescore --run "$OUT/remain_active" --stable-steps 4 --out "$OUT/rescore_k4" 2>&1 | tee "$LOG/20_rescore_k4.log"
"$SIM_PY" -m benchmark.remaining_goals.finish.cli rescore --run "$OUT/remain_active" --stable-steps 1 --out "$OUT/rescore_k1" 2>&1 | tee "$LOG/21_rescore_k1.log"
"$SIM_PY" -m benchmark.remaining_goals.finish.cli rescore --run "$OUT/remain_active" --stable-steps 8 --out "$OUT/rescore_k8" 2>&1 | tee "$LOG/22_rescore_k8.log"
```

重评分先验证run/episode/输入ledger/录像hash和协议，直接从trace/queries复算。源raw、旧scores、旧JSR/UIR全字节不变；禁止新旧schema混读。新目录保存summary/report，附source run hash。报告包含每task/mask百分比+n/N、technical/unknown/missing、τ/延迟覆盖与多标签失败，不能只截成功均值。

所有命令 `--help` 展示实际支持参数。成功退出通常0；技术错误/不足/校准能力未建立/parity失败为2；顶层用户中断为130，支持partial的stage也可能以2并写中断原因。每次检查日志退出码和产物status，不能仅凭文件存在或0退出推科研结论。已有out拒绝覆盖；当前不自动resume。中断后保留目录，交Codex检查再显式使用新out重跑同一冻结集合，不能删除失败或补容易来源。

交回：冻结代码SHA、私有配置脱敏副本、全部命令/日志/退出码、audit/cache/head/calibration/parity身份、normal与Remain原始run/evidence/video、重评分结果及missing。真实资产可留服务器，GitHub只放可审阅摘要与路径/hash。无真实GPU结果时明确未运行；不拿CPU synthetic训练或toy录像填充主成绩。
