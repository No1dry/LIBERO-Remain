# 031：normal00 对照与缺失两任务的局部制备

031 的代码属于 LIBERO-Remain。基于已审 `c6dc98de0c54517c976057598b60f4cedf7fa3e5`，新增独立入口；旧 `headless.cli` 的 mask10 默认协议、旧80条 raw／评分v2与原全mask构造入口继续保留。此文是代码交付与命令草稿，**不表示真实来源已齐、不表示两任务物理故障已修复**。真实制备、回放和模型作业由用户启动，Codex先核对服务器路径、隔离部署与完整环境命令。

031 R2仅修制备续跑边界：制备修正版应部署到独立目录。首批80条及后续20条normal00评测继续使用已冻结的 `a23a8116e5e2e2bcd344242b170e787e50535a42` 源码；不热改该评测目录，不因制备小修切换prior-run代码身份或重跑80条。

## 顺序与预算

| 阶段 | 协议／population | 固定来源 | 新模型上限 |
|---|---|---|---:|
| 先跑正常能力对照 | normal00-control / existing-eight | 原八任务各0..9 | 80 |
| 单独补来源 | selected-mask10；另 normal00-control | frypan_stove9、cabinet_close_top_bowl各0..9 | 0 |
| 补正常对照 | normal00-control / missing-two | 上述两任务各0..9 | 20 |
| 补原缺失10 | selected-mask10 / missing-two | 上述两任务各0..9 | 20 |

新增模型总目标120；旧80条10直接保留。新 selected-mask10 入口不允许选择另外八任务。normal00 全分母为100，第一阶段会显示20条未选中；技术缺失、失败、unknown单列，不当模型0%失败。`all`只适用于normal00；已有阶段应通过显式 `--prior-run` 引用，避免重复执行。

## 协议和证据

normal00 使用 `remaining-headless-normal00-control-v1`、独立结果schema与 `remaining-headless-normal00-source-acceptance-v1`。初始已完成集合为空，`goal_regression=null`、`preservation_applicable=false`；A/B均依原任务目标与目的地判定合法操作。严重破坏、错误抓取/放置与释放确认规则不降低。实际恢复必须00，初始状态、速度、接触、机器人参考姿态、观测对应等必要检查仍须通过。

00只验原始t0必要证据，不自动要求编辑银行全mask通过、额外150步hold或独立150步回放。旧audit整体失败位、完整原文件和失败时刻仍保留；不得把旧audit改成passed。原工件必须有实际保存的npy、typed初始观测与绑定audit，只有trace0而无这些文件属于缺证据。旧动态RGB没有完整逐帧像素；文件验收只能重算已保存初始字节、校验记录的fresh比较及数值，不声称重新渲染。

每个00来源还要绑定原 `construction_report.json` 或新 `normal00_initialization_v1`：记录raw official init（等待0）或settled base及真实settle步数。新补建使用固定官方index、原init→settle80→initial-only audit，保存官方init资产身份和新工件；不从旧失败trace伪造原始状态。配对index不等于逐字节相同，也不承诺世界仅A关系不同。

selected10 的新接受范围是 `remaining-headless-selected10-source-acceptance-v1`，执行仍使用旧10结果语义。构造至少150步，正式adapter独立回放至少两次、每次150步。固定HOLD `[0,0,0,0,0,0,-1]`；位置0.005、速度0.01、机器人位移0.002、穿透0.002、观测1e-8，RGB最大差1、changed fraction0.0001；不增加忽略接触。00/01/11失败不连坐有效10，10自己的失败不能放行。

新构造方法 `selected_A_only_settle_component_transplant_v1` 只搜索A候选、沿A的精确状态白名单组合并settle，再移植回原settled base，重新验证实际10。它与旧全目标settle／全mask配对流程不同，因此使用新方法版本、新目录和完整记录，**不称作旧配对银行的原始通过**。没有抬阈值、清零速度或更换index。

## 组合来源格式

`remaining-headless-composite-sources-v1` 包含 `protocol`、完整 `expected`（由budget/template命令生成）、`entries`。每条entry是：

```json
{
  "task_id": "frypan_stove9",
  "initial_state_index": 0,
  "origin": {
    "manifest": "/existing/source/manifest.candidates.json",
    "manifest_sha256": "<原文件字节SHA256>",
    "content_hash": "<原manifest内容hash>",
    "candidate_replay": "/existing/replay/replay_report.json",
    "replay_sha256": "<原回放报告字节SHA256>"
  }
}
```

00的origin把回放字段换成 `initialization`／`initialization_sha256`。缺来源可为null；有构造但缺回放可先只提供manifest三个字段。相对路径相对于组合JSON；runtime配置保持旧仓库根路径解释。manifest内的state、观测、construction audit及replay依赖由验收器逐条读、重算、记录hash，不相信手填ready。模板仅盘点文件，不证明可用。

每个episode运行目录复制自己的完整原manifest／报告与选中依赖到 `source/manifest_files`、`source/replay_files`、`source/initialization_files`。原回放的source hash始终绑定其原manifest，绝不改写以适配混合清单。离线inspect从归档重新验证；不要求旧准备目录继续存在。`--prior-run`明确依赖上一运行目录，需保留该目录和被冻结的batch字节，不能随后改写旧batch。

## 文件检查命令（不创建仿真／加载模型）

在仓库根，沿用已核对的[headless环境与SOG10配置](headless_ten_task_baseline_runbook.md)。下方`python`必须由Codex替换为服务器实际conda环境解释器；示例配置的路径需核对。以下命令在本交付时没有启动真实任务。

```bash
python -m benchmark.remaining_goals.headless.scoped_cli budget-plan --protocol normal00-control --population existing-eight
python -m benchmark.remaining_goals.headless.scoped_cli budget-plan --protocol selected-mask10 --population missing-two

python -m benchmark.remaining_goals.headless.scoped_cli sources-template --legacy-config configs/remaining_goals/headless/batch.example.json --protocol normal00-control --out reports/task031/normal00-sources.json
python -m benchmark.remaining_goals.headless.scoped_cli sources-template --legacy-config configs/remaining_goals/headless/batch.example.json --protocol selected-mask10 --out reports/task031/selected10-sources.json

python -m benchmark.remaining_goals.headless.scoped_cli dry-plan --config configs/remaining_goals/headless/normal00-control.example.json --out reports/task031/normal00-plan
python -m benchmark.remaining_goals.headless.selected_preparation --inventory reports/task031/selected10-sources.json --output reports/task031/selected10-inventory --mode inspect
```

模板在manifest同目录寻找construction_report；若旧报告位于别处，准确填写initialization路径与hash，再dry-plan，不能凭pose_id猜等待步数。旧18个构造来源逐条显示candidate／constructed／replayed／failed／missing；没有独立回放不能写ready。

## 用户启动的真实作业草稿

先启动80条正常00；不需等待缺失两任务。

```bash
python -m benchmark.remaining_goals.headless.scoped_cli run --config configs/remaining_goals/headless/normal00-control.example.json --out reports/task031/normal00-eight
```

单独补10；`prepare-missing`按文件证据决定构造或回放：ready零物理调用、有效构造缺回放只回放原manifest。仅这两任务，可用 `--tasks frypan_stove9 --indices 4`限定一次固定来源尝试。

```bash
python -m benchmark.remaining_goals.headless.selected_preparation --inventory reports/task031/selected10-sources.json --output reports/task031/selected10-prepare --mode prepare-missing
python -m benchmark.remaining_goals.headless.selected_preparation --inventory reports/task031/normal00-sources.json --output reports/task031/normal00-prepare --protocol normal00-control --mode prepare-missing
```

这两条制备命令不启动模型。明确失败的原证据默认不会隐式重试；`--allow-failed-retry`只表示显式新尝试并保留前次记录，不允许绕过真实失败或改变阈值。对真实不稳定的修订必须先交Codex裁定；目前未宣称qvel[12]故障根因或腕相机差异成因已查明。输出已有时必须显式 `--continue`，不会覆盖旧尝试目录。`replay-missing`可单独补回放，`build-missing`可只构造。

**曾ready后失效的来源单独处理**：包括首次从原库存直接验收、`operations=[]` 的来源。依赖丢失或损坏后，原输出中的任何 `--continue` 只重新验收文件并保留missing／failed、旧验收历史、原origin和物理计数；即使带 `--allow-failed-retry` 也不构建／回放。恢复原文件后可再次验收ready，历史与 `ready_origin_invalidated` 标记仍保留。需要新的物理尝试时，由用户显式指定一个尚不存在的 `--output`，保留旧报告和原始工件；若现有证据明确失败，仍须按原规则显式retry，不能改阈值或来源index。CLI报告的 `recovery_action` 会提示这一区别。

待两任务来源证据通过，检查与运行：

```bash
python -m benchmark.remaining_goals.headless.scoped_cli dry-plan --config configs/remaining_goals/headless/normal00-missing-two.example.json --out reports/task031/normal00-two-plan
python -m benchmark.remaining_goals.headless.scoped_cli dry-plan --config configs/remaining_goals/headless/selected-mask10.example.json --out reports/task031/selected10-plan
python -m benchmark.remaining_goals.headless.scoped_cli run --config configs/remaining_goals/headless/normal00-missing-two.example.json --out reports/task031/normal00-two --prior-run reports/task031/normal00-eight
python -m benchmark.remaining_goals.headless.scoped_cli run --config configs/remaining_goals/headless/selected-mask10.example.json --out reports/task031/selected10-two
```

任一选中来源缺证据默认拒绝开始。用户明确接受部分运行时追加 `--allow-missing`，完整分母及原因仍保留。一条技术失败不会阻塞其他有效来源。模型输出已有时必须 `--continue`；已尝试episode目录始终保留、不会自动重跑，补好来源后只开始尚未尝试的固定episode。第一次80、后续20使用不同目录和显式prior引用；旧10的80条不会被本新10入口读取为待执行来源。

## 录像、评分和输出

所有新运行保持原完整指令、同SOG10权重／normalization、白名单camera/proprio、policy seed7、chunk8、H520。全部目标+释放连续5观测作为终点，不添加FINISH、W150、归位或GT策略输入。策略在同suite内复用加载实例，每个来源独立归档和环境；跨suite核对实际模型／统计身份。

运行目录包含 `batch.json`、不可变 `plans/*.json`、逐episode的 `task_run.json`、`raw`、typed `evidence`、全程双相机mp4、`summary.json`／`episodes.csv`／`report.md`。缺录像的completed结果不能认证。summary报每任务合规成功百分比与固定分母、6主轨／4迁移任务分组、技术缺失和native goal诊断；native all-goal不是同一个合规SR。

```bash
python -m benchmark.remaining_goals.headless.scoped_cli inspect --run reports/task031/normal00-eight
python -m benchmark.remaining_goals.headless.scoped_cli summarize --run reports/task031/normal00-two --out reports/task031/normal00-final-summary
python -m benchmark.remaining_goals.headless.scoped_cli summarize --run reports/task031/selected10-two --out reports/task031/selected10-summary
```

旧 `headless.cli rescore`只用于旧10，不可拿来重算00。031不再增加benchmark分数、不自动训练030、不维护第二份Eval导出包。真实00结果、20条10是否补齐、两项物理故障是否解决，均需用户运行后由Codex审查。
