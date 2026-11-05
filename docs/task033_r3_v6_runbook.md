# 033 R3：统一v6与旧来源证据复用

本手册替代R2的“RGB等待裁决、先补20条v4”执行安排。新来源一次使用明确的 `named-uint8-rgb-one-level-v6`；旧v4工件保持原规则、原结果和原hash。代码部署与原aedfe169目录隔离。已完成九任务00共90条、旧六10及two_pots五条ready均不重跑。

本次X只运行CPU/fake。以下真实准备命令由Codex审查、隔离部署并填好实际环境路径后交用户启动，不是本轮已执行记录。完整30条新10在物理补建与证据检查前不能宣布ready，也不提供allow-missing模型run。

## v6规则及版本记录

v6在当前九任务来源构造、回放和formal reset的既有比较处统一使用，与task/mask/index无关：相机身份、原shape/dtype、uint8、hash与状态对应合法时，最大单通道绝对差≤1；变化像素数/比例完整保留，仅作诊断。计算先转充分精度，0与255不会溢出成1。初态/reset非RGB仍精确，动态非RGB仍原1e-8；物理速度0.01、穿透/位置/机器人、In/Open/Turnon、150构造及两次150回放保持。

新audit、manifest、episode、replay均显式记录profile；比较还记录相机shape/dtype和原/fresh相机byte hash。数组不修改、不滤波、不替换策略图像，不增加控制路径render/step。旧接口不指定profile仍是旧行为；本手册的R3组合入口强制v6，不要求用户手动填写该flag。通用数值定义不代表GL成因校准或模型扰动不变性。

派生证书schema为 `remaining-source-rgb-recorded-revalidation-v6`。这是新的独立证据文件，保留原工件hash、旧v4结果、新判断和局限，明确 `recorded_diagnostics_revalidated=true`、`new_native_steps=0`；没有新鲜图像重算。原只读v5诊断 `acceptance_authorized=false` 没有被修改或拿来放行。

## 文件级计划：自动hash与真实缺口分类

在审查通过的独立R3 checkout执行，沿用原已跑通的仿真Python/LIBERO环境。下列三个目录变量由部署方填为实际绝对路径；不升级依赖、不替换checkpoint或模型runtime。

```bash
cd /path/to/isolated/LIBERO-Remain-task033-r3
export PY=/path/to/original/libero-simulator-env/bin/python
export OLD_RUN_ROOT=/path/to/original/task033-run-root
export R3_OUT=/path/to/new/task033-r3

"$PY" -m benchmark.remaining_goals.headless.repair033_v6 plan \
  --inventory "$OLD_RUN_ROOT/preparation/mask10/sources.json" \
  --preparation-report "$OLD_RUN_ROOT/preparation/mask10/preparation_report.json" \
  --out "$R3_OUT/plan"
```

此命令纯文件操作，不导入native producer或创建仿真。必须匹配R2原报告SHA `cfe54054a85148e36e39a88dacd5658ef367f526a0970f7079d7a2586661d01e`，自动解析来源路径和hash。输出：

- `reviewed_v4/`：原五ready/25失败身份计划及逐字节原报告副本；
- `derivations/two_pots_s00|02|07|08|09/derivation_report.json`：每条实际文件检查及具体缺口；可证明时另有 `certificate.json`；
- `repair_plan.json`：新v6计划、精确动作、报告hash、分项计数；
- `sources.json`：保留90条expected的新来源组合；旧六结果仍由原reuse索引复用。

原5条two_pots index1/3/4/5/6固定 `reuse_only`；文件缺失只报告reuse问题，不把它们加入native。20条drawer/microwave固定采用已验收R2方法。其余5条按原证据分路，不按换profile一律重建：

| 原来源 | 完整证据下的分路 | 必要native工作 |
|---|---|---|
| two_pots 0/2/8 | `derived_ready`：原构造和两个回放的完整窗口、物理检查、状态/typed初态/hash都复验通过 | 0步；原failed仍保留 |
| two_pots 7 | `replay`：保留构造及已完成第一次回放；第二窗缺失，不可派生ready | 当前既有成对入口2×150=300控制步；不重建 |
| two_pots 9 | 先读实际已导出manifest/state/typed审计；若足够可复用，否则 `build` | 仅在确缺必要构造工件时，新构造＋成对回放 |

表格是已公布证据对应的预期分路，不是本机读取服务器全部raw后的计数。实际文件缺帧时不会伪造；若构造完备但回放不完整可仅安排回放，缺必要构造工件才安排新构造。hash失配、其他物理失败、数值差>1、未知profile等记录 `blocked`，不自动以重试掩盖。计划有blocked或旧ready引用问题时exit2，JSON保留具体原因。

完整复用要求逐帧读取151个记录（初态＋150步）、其他物理检查、非步进刷新状态、原初态typed数据及原report/manifest引用链。缺第二回放不能靠reset的新解释补满；缺manifest/state不能从两个代表候选补造。文件证据不足与观察到物理失败分开记录。

## 用户启动必要真实准备

Codex确认计划后，由用户执行：

```bash
"$PY" -m benchmark.remaining_goals.headless.repair033_v6 prepare \
  --plan "$R3_OUT/plan/repair_plan.json" \
  --out "$R3_OUT/preparation"
```

入口只执行计划中 `repair/replay/build` 来源，固定v6和R2方法 `selected_A_only_bounded_settle_component_transplant_v2`；不允许通过额外tasks/index参数扩大队列。完整0/2/8、旧5ready、00和旧六不会调用native。每来源独立目录与实际控制账本，最终 `preparation/sources.json` 自动组合原引用、派生证书和新准备结果，`preparation_report.json`列全部30条真实当前状态。

source7已有第一次回放及其失败第二reset原样保留。现有入口的最小执行单位是同一正式adapter中的两次独立恢复；采用300步成对回放，没有为节省150步重构整个框架，也没有把旧第二窗补成完成。新replay显式绑定构造证书及v6，之后原构造＋新replay必须经过完整reader接受。

R2物理预算不变：base80；抽屉/双壶每候选80 settle＋150构造审计，最多24候选；微波炉每候选80..400 bounded settle、连续20样本收敛再150审计，最多24候选。成功后2×150回放。实际控制调用写账本；抛异常或未落账本时为unknown，不按理论上限填数、不清零速度。这里的调用均为来源准备，不是模型episode。

## 续跑及只读盘点

只在确需续跑时执行：

```bash
"$PY" -m benchmark.remaining_goals.headless.repair033_v6 prepare \
  --plan "$R3_OUT/plan/repair_plan.json" \
  --out "$R3_OUT/preparation" --continue

"$PY" -m benchmark.remaining_goals.headless.selected_preparation \
  --inventory "$R3_OUT/preparation/sources.json" \
  --output "$R3_OUT/inspect-mask10" --protocol nine-mask10 --mode inspect
```

续跑绑定原plan/profile/hash；未尝试来源可继续，已有failed/running/中断操作不自动重试。父层已记录派发但子报告缺失时也保留interrupted/unknown，不再派发该源。旧ready的证据丢失只可恢复原文件，不隐式重建。真实R3失败需读证据后另行安排新输出；不能删除报告假装未尝试。只读盘点有缺口exit2，不是模型成功率0%。

需要单条证据排查时可使用纯文件入口；`origin.json`为一条包含原manifest/replay路径及hash的origin对象，组合plan通常已自动准备，无需用户手写：

```bash
"$PY" -m benchmark.remaining_goals.headless.rgb_revalidation \
  --task two_pots --index 0 --origin /path/to/one-origin.json \
  --out /path/to/new/single-source-v6-review
```

本轮不启动模型run、重新评分00、更新Eval发布或合并PR。后续Codex根据实际文件派生和用户补建报告验收全部30条10，再交固定模型评测命令；现有00结果78/90原样保留。
