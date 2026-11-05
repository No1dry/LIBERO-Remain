# 033 R3：统一v6接入与原证据复用交付

身份：X。日期：2026-11-02。按工单沿用 [PR #14](https://github.com/No1dry/LIBERO-Remain/pull/14)，不新开重复PR、不自动合并。**实现commit：`65e0509d0fc713130110f0fcce158e619b49c744`**。先fetch main `3d23eb6dbee850c3decf4ae9cba115ab62c0493a`，读取R3工单、审查、RGB证据JSON及00完成记录；在原隔离PR14工作树同步main后实现，审查差异基线 `b1c56ff8bb4ed6c7b2dd727d557400e9b4138eaf`。

**软件及定向CPU/fake检查已交付，待Codex审查。** 没有真实仿真、回放、模型或训练；没有部署/热改aedfe169，也没有重跑或重算00、旧六任务或旧五条ready。抽屉几何与微波炉收敛算法保持已验收R2实现；只接入新比较profile及必要元数据/读写路径。原v5只读提案与原结果保留为历史，不将其诊断授权字段翻转成通过。

## 1. 统一规则已经可执行

明确ID：`named-uint8-rgb-one-level-v6`。在既有状态对应检查后，每个同名、原shape/dtype匹配的uint8 RGB相机按充分精度计算最大通道绝对差，≤1可接受；变化面积仅诊断。任意面积差1、单像素差2及0↔255分别有CPU用例，不存在uint8溢出。相机、state、hash、dtype/shape或非RGB原规则不满足仍失败。

非RGB保持原规则：初态/reset byte-exact，动态绝对限1e-8；不因新的RGB规则把动态临时加严为exact。物理速度0.01、位置/穿透/机器人、native In/Open/Turnon、150构造及2×150正式回放均不放宽。不会修改策略图像、滤波、重采样、平均图片或增加控制路径render/step。此为统一8-bit数值一致性定义，不声称GL误差已校准或模型对扰动不变。

完整接线：`validation.compare_observations/validate_candidate` → `build._audit_state` → `selected_build` audit/episode/manifest/report → `ReplayAuditEnv` formal reset和`selected_replay` → scoped/source acceptance reader。新增显式 `observation_profile` 参数及CLI `--observation-profile`；R3组合入口自动固定v6。旧v4常量、缺省调用和旧工件解释保持原样，新常量不使旧ready失效。v6相机诊断另存shape/dtype及原/fresh byte hash，原aggregate hash仍保留。

`LiberoGoalEnv.reset` 本身没有跨render RGB比较；该比较位于 `ReplayAuditEnv.restore_candidate`，已接通v6，因此没有改正式策略env/control路径。native v6的normal00初态reader也保持原initial-only/0步语义，仅CPU验证该兼容接口；旧00派生入口仍拒绝，未重跑或重算已完成00。

## 2. 派生证书与旧证据复用

新增 `headless.rgb_revalidation`。`derive_source(task,index,origin,output,protocol='nine-mask10')` 仅读原文件，写独立 `derivation_report.json`；有完整构造证据时另写 `certificate.json`。schema为 `remaining-source-rgb-recorded-revalidation-v6`，原manifest/replay/state/typed初态/审计hash、原v4结果、新判断、范围与限制明确绑定，记录：

- `recorded_diagnostics_revalidated=true`；
- `new_native_steps=0`；
- `raw_rgb_recomputed=false`。

完整接受必须逐帧检查初态＋150步的原构造、两次独立回放、物理值/门槛/语义、非步进刷新事实、原检查与aggregate自洽、初态/reset typed数据及hash链。未保存的fresh像素不被伪造或声称重算，精简证据/代表帧不能替代完整窗口。原report和failed bool不修改。

证书显式加入origin的 `rgb_certificate` 与必需 `rgb_certificate_sha256`。完整source证书绑定原replay；仅construction证书不能释放旧失败replay，只能与显式v6且绑定同证书SHA的新完整回放组合。归档/离线快照同时带证书和原依赖，可重新验证；缺帧、缺hash、其他物理失败、未知或不一致profile均拒绝通过。

## 3. 固定30来源的分流与真实状态

新增 `headless.repair033_v6`，复用R2原报告身份核验，自动生成来源hash和组合清单；不让用户手填hash。原报告固定SHA为 `cfe54054a85148e36e39a88dacd5658ef367f526a0970f7079d7a2586661d01e`。

| 来源 | R3动作 | 本轮真实状态/必要控制步 |
|---|---|---|
| two_pots 1/3/4/5/6 | 固定 `reuse_only`，保留原引用及v4 | 审查已有5ready；不执行native |
| drawer 0..9、microwave 0..9 | 已验收R2构造方法＋v6 | 20条待用户必要补建，算法不返工 |
| two_pots 0/2/8 | 完整原工件有效时 `derived_ready` | 文件派生0新native步；本机未取得服务器原工件，未冒报已派生成功 |
| two_pots 7 | 保留构造与已完成第一次原回放；第二窗缺失则 `replay` | 现有成对入口2×150＝300步，不重建、不伪造第二窗 |
| two_pots 9 | 按实际manifest/state/typed审计可复用程度分路 | 缺必要构造工件才 `build`，否则可只补回放或纯文件复用 |

因此**本机没有新的真实30来源ready计数**；已知原记录仍为5ready/25缺口。若0/2/8原完整工件全部复验通过，计划会记录8个无需native的来源，另20物理修复＋7回放＋9按缺口处理；这只是条件分路，不是已执行结果。实际计数、blocked/reuse问题由文件级plan输出。source9两个已读候选不外推为全部24候选通过。

`prepare`只派发计划中的repair/replay/build；0/2/8已派生、旧5、旧六、00不进native。source7使用现有成对回放最小入口，保留旧第一次证据，并明确多执行一次150步的代价，没有为省150步重构框架。source9缺工件不靠诊断补造。

每来源独立输出和实计账本，continue不自动重试已失败/running/中断操作。父层已派发但子报告未落盘时保留interrupted/unknown；尚未尝试的其余来源继续。计划后证书字节或依赖漂移在任何native前失败，不能先回放后发现绑定失效。旧ready丢文件只报告问题，不重建或整包作废。

## 4. 受影响CPU/fake验证

最终在本机 `C:/ProgramData/anaconda3/python.exe` 运行下列组合，**234 passed，52.97s，exit0**：

```bash
python -m pytest \
  tests/test_task033_r3_profile.py \
  tests/test_task033_r3_live_profile.py \
  tests/test_task033_r3_evidence.py \
  tests/test_task033_r3_queue.py \
  tests/test_task033_r3_review.py \
  tests/test_remaining_validation.py \
  tests/test_remaining_replay_candidates.py \
  tests/test_selected_producers.py \
  tests/test_selected_preparation.py \
  tests/test_headless_source_acceptance.py \
  tests/test_headless_scoped_sources.py \
  -q --tb=short --basetemp=.work/r3-final-targeted
git diff --check
```

只选本轮受影响的RGB/profile、producer/reset、reader/archive与队列测试；没有重跑R2的280项全组、全库、跨平台、图像标定或模型测试。R2物理软件验收直接复用。旧replay fake中一处构造器未接受此前已存在的 `task_semantics` 参数，本轮仅补test double签名，不改物理逻辑。

独立复核最终5个R3文件 **53 passed、0 skip、18.04s**，与234重叠，不相加；16个独立回归纳入 `test_task033_r3_review.py`。复核发现并关闭typed相机hash/shape绑定、嵌套profile一致性、外部证书SHA及计划后漂移、外层dispatch中断四类问题。实际selected_replay搭配CPU物理double完成“构造证书→300次fake控制调用→正式reader→archive/快照复验”闭环，原文件字节未改。当前无未关闭软件阻断；fake结果不是物理来源或模型效果。

## 5. 完整CLI与配置

详细规则、路径、分流及预算见[R3运行手册](../../docs/task033_r3_v6_runbook.md)。以下供Codex审查后隔离部署、填写实际三个路径变量，再由用户启动必要物理步骤。本轮未执行这些真实命令；不在aedfe169内pull/改代码，不升级原环境或改变模型runtime。

```bash
cd /path/to/isolated/LIBERO-Remain-task033-r3
export PY=/path/to/original/libero-simulator-env/bin/python
export OLD_RUN_ROOT=/path/to/original/task033-run-root
export R3_OUT=/path/to/new/task033-r3

# FILE ONLY：绑定原报告；派生可复用证据；列真实剩余缺口。
"$PY" -m benchmark.remaining_goals.headless.repair033_v6 plan \
  --inventory "$OLD_RUN_ROOT/preparation/mask10/sources.json" \
  --preparation-report "$OLD_RUN_ROOT/preparation/mask10/preparation_report.json" \
  --out "$R3_OUT/plan"

# USER STARTED NATIVE：只做上一步明确必要的repair/replay/build，统一v6。
"$PY" -m benchmark.remaining_goals.headless.repair033_v6 prepare \
  --plan "$R3_OUT/plan/repair_plan.json" \
  --out "$R3_OUT/preparation"

# 仅需续跑时执行；不重试已失败/中断操作。
"$PY" -m benchmark.remaining_goals.headless.repair033_v6 prepare \
  --plan "$R3_OUT/plan/repair_plan.json" \
  --out "$R3_OUT/preparation" --continue

# FILE ONLY：完整组合来源盘点，有缺口exit2如实保留。
"$PY" -m benchmark.remaining_goals.headless.selected_preparation \
  --inventory "$R3_OUT/preparation/sources.json" \
  --output "$R3_OUT/inspect-mask10" --protocol nine-mask10 --mode inspect
```

新结果仍保留每条件90的expected，组合文件含旧来源引用及新证书/新准备产物。未完成10不会通过allow-missing转成模型run；后续Codex读取真实plan和用户补建报告后再验收全部新30条10。

修改归属：比较与live接线在 `validation.py/build.py/selected_build.py/replay_candidates.py/selected_replay.py`；证据在新 `headless/rgb_revalidation.py` 和两个source reader；编排在新 `headless/repair033_v6.py`、`selected_preparation.py`、`nine_planning.py`。`construction.py`、R2settle算法、`libero_env.py`、评分与模型路径未改。README及R2手册已指向本R3当前执行入口，R2回复及原v5提案保留不倒改。

下一步Codex集中审查后隔离部署并给实际路径命令；用户启动必要补建。033整体仍open，没有自动merge、Eval发布、历史清理或新的真实结果声明。
