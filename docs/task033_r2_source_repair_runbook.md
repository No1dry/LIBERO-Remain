# 033 R2：只补失败来源，冻结00与已通过来源

本轮原始证据为aedfe169：00共30/30 ready；10共5/30 ready，尚有25缺口。旧5条10是two_pots index1/3/4/5/6；旧六任务结果继续只读复用。**00在原冻结目录按已交命令继续正式评测，无需等待R2，不重做00来源。** 以下是新目录部署后供用户执行的命令，本次X未启动native/model。

本R2实现抽屉容积修复、微波炉有界收敛、venv路径修复和25缺口的精确编排。双壶5缺口的现有RGB检查准确执行了旧规则；没有发现可证实的漏同步错误，因此保留v4准入并提交[只读诊断及最小v5提案](task033_r2_rgb_proposal.md)供Codex裁决。**当前可执行补建是抽屉10+微波炉10；RGB的0/2/7/8/9保持review_blocked，不因诊断改ready，也不重复物理尝试碰通过。** 这一区别是R2工单明确的裁决边界，不是把25缺口改成20或宣称剩余5已解决。

## 新目录与原配置

Codex审查后从R2接受commit部署到新目录，不能在 `LIBERO-Remain-task033-aedfe169` 或正在跑00的checkout内pull/改代码。以下变量由Codex替换为服务器实际绝对路径；来源SHA自动计算并绑定，无需用户填写hash。

```bash
cd /path/to/isolated/LIBERO-Remain-task033-r2
export PY=/path/to/original/libero-simulator-env/bin/python
export OLD_RUN_ROOT=/path/to/original/task033-run-root
export R2_OUT=/path/to/new/task033-r2

"$PY" -m benchmark.remaining_goals.headless.repair033_sources --help
"$PY" -m benchmark.remaining_goals.headless.rgb_diagnostic --help
```

复用原已经跑通的仿真环境、LIBERO路径、HOLD与原OFT runtime，不升级依赖、不换权重、不更换归一化或推理路径。本轮便利工具 `nine_cli runtime-config` 已改用不解引用的绝对解释器路径，保留venv别名；当前正确冻结runtime不因此需要重新生成。旧00、新10仍原SOG10、seed7/chunk8/H520。

## 1. 文件盘点与25缺口冻结计划

```bash
"$PY" -m benchmark.remaining_goals.headless.repair033_sources plan \
  --inventory "$OLD_RUN_ROOT/preparation/mask10/sources.json" \
  --preparation-report "$OLD_RUN_ROOT/preparation/mask10/preparation_report.json" \
  --out "$R2_OUT/plan"
```

本命令只读取文件，输出 `repair_plan.json`、自动路径/hash的 `sources.json`，并逐字节复制原报告/原sources用于追溯。原准备报告必须匹配R2审查公布的 `cfe54054a85148e36e39a88dacd5658ef367f526a0970f7079d7a2586661d01e`；不读取或改写00。来源JSON必须指向该原报告的同一origin。没有把未提供的服务器raw冒充本机已核验。

固定输出计数：`reviewed_failures=25`、`repair_executable=20`、`rgb_review_blocked=5`、`reuse_only=5`。组合来源保留每条件90个expected；旧六的结果复用仍由原reuse.json负责，永不进此准备队列。五个旧ready执行文件级重验，原manifest/replay引用保留；若缺文件只列reuse_issues，不将其变成补建目标或否定其余证据。输出不得与任何历史报告/来源根重叠。

RGB只读诊断完整命令在[提案文档](task033_r2_rgb_proposal.md)，可立即根据原保存audit运行；诊断不启动render/step，不改bool，不具备来源放行能力。

## 2. 用户启动已实现的20条物理修复

Codex软件审查后，由用户执行：

```bash
"$PY" -m benchmark.remaining_goals.headless.repair033_sources prepare \
  --plan "$R2_OUT/plan/repair_plan.json" \
  --out "$R2_OUT/preparation/mask10"
```

默认精确选择drawer0..9、microwave0..9，不允许额外tasks/index参数，也不触发two_pots的build/replay。使用显式构造方法 `selected_A_only_bounded_settle_component_transplant_v2`；不是把旧failed布尔值改true。每条新操作在新attempt目录、原失败与报告保留。

抽屉：`oriented_in_volume_world_gravity_v1`区分有向In容积与On支撑面；原site pose/父体保留，floor取真实collision box向上宽面，保持原5°物理支撑限制，拒绝竖直墙帽。世界重力下完整footprint及原有向容积约束一起检查；最终仍需native In/Open、接触、速度与原150审计，不靠旋转官方site/XML骗过。当前floor类型限pinned白柜已有box；无法识别的mesh-only支撑明确失败。

微波炉：官方base仍原80步；A候选实际HOLD至少80、最多400步，只有连续20次实测全qvel≤0.01、active10/Open/invariant正确、目标xyz跨度≤0.005m才复制实际完整pose/quaternion/velocity。超预算或物理异常保留失败与逐步收敛证据，不移植/导出该候选。继承几何种子在真正restore前恢复实测base qvel，禁止清零以获得稳定。最终还做原150构造审计和2×150正式adapter回放；阈值未放宽。

每来源最多24候选；微波炉候选settle最多9600控制调用，另计base80及最多24×150审计，成功后独立回放300。抽屉仍每候选80+150。账本记录实际执行数而不是按上限填数；抛异常的control call标partial_unknown。所有这些是来源准备步数，不是模型episode，也不额外消耗VLA probe。

## 3. 中断恢复与组合结果

同一R2输出显式续跑：

```bash
"$PY" -m benchmark.remaining_goals.headless.repair033_sources prepare \
  --plan "$R2_OUT/plan/repair_plan.json" \
  --out "$R2_OUT/preparation/mask10" --continue
```

此命令只首次替换尚未尝试的原失败来源，并可完成已有成功构造尚缺的必要回放；不重新尝试R2已有failed/running/中断操作。首次执行若第1条中断，后19条仍能各首次执行一次；第1条不会自动重试。方法、原inventory/report和计划hash均锁定，不能同目录换设置。R2自身失败需要明确新输出及后续证据裁决；不能删除目录假装未尝试，不能用全局retry标志偷偷翻转旧ready失效保护。

新 `preparation/mask10/sources.json` 自动组合20条修复结果与旧two_pots原引用，五个已通过来源没有物理操作；RGB五条仍引用原失败。可只读查看完整30条新任务的当前来源状态：

```bash
"$PY" -m benchmark.remaining_goals.headless.selected_preparation \
  --inventory "$R2_OUT/preparation/mask10/sources.json" \
  --output "$R2_OUT/inspect-mask10" --protocol nine-mask10 --mode inspect
```

此盘点expected90、选择新三30，输出exit2表示仍有失败/缺口，不是模型0%。**目前不提供部分10模型run或隐式allow-missing命令。** Codex读真实新报告、裁决RGB提案并提供对应完整版本的剩余5来源新验收安排后，才形成全部30来源可执行清单。由于v5当前未被授权，本R2没有可启用v5的build/replay flag；不得把原v4回放命令重复运行称为RGB修复。

## 证据与旧版本兼容

旧v1/normal00默认构造、v4RGB、评分/worker/模型路径不变。R2仅显式method启用；旧5ready的code SHA不同不会触发重跑。原失败保留，新的通过必须来自真实新state/audit/replay。新构造报告为 `selected_mask10_candidate_construction_v2`；微波炉收敛证据schema `remaining-selected-component-settle-v2`，含每步速度/pose/goal facts、停止原因和实际计数，最后完整state hash。新来源仍通过原正式source reader的150/2×150验证。

本次只交软件和CPU/fake证据。没有宣称20个新物理来源已通过、25缺口已清零，或GL误差已获得独立校准；00不等待本修复。Eval发布、模型评测、训练、自动merge及历史清理都未执行。
