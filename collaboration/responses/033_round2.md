# 033 R2交付：10失败来源构造修复及RGB版本提案

身份：X。日期：2026-11-02。**软件实现与定向CPU/fake检查已完成，待Codex审查；未执行真实仿真、回放、模型或训练。00的30条已通过来源及正式评测不等待本修复。**

已提交独立 [PR #14](https://github.com/No1dry/LIBERO-Remain/pull/14)，open且未合并；GitHub提交与tree已核对本地一致。

本轮先fetch最新main `6e43f0106b1a73d6e60e3c26add4c8c6b0186674`，读取033 R2工单、关联R1/R2审查、精简原始证据和真实制备阶段记录。在独立工作树、分支 `x/task033-r2-sources` 上继承已审R1 `aedfe1692004d46488dd7544353ba4f58b60d51d` 并合入最新main。**R2实现commit为 `e850ae6a2494d08a7314c39e7783d4a70f94765a`**；aedfe169工作树保持原HEAD、干净，未热改。新PR继承PR #13已有实现，未合并或改动该PR。

## 交付结果与边界

| 原失败来源 | 本轮交付 | 当前能否宣布来源ready |
|---|---|---|
| drawer index0..9，共10 | 有向In容积、真实容器floor和世界重力候选生成 | 不能；待用户运行新版本物理制备 |
| microwave index0..9，共10 | 版本化有界稳定收敛，复制实际完整pose/velocity | 不能；待用户运行新版本物理制备 |
| two_pots index0/2/7/8/9，共5 | 源码同步链核对、原audit只读诊断、明确待裁决v5提案 | 不能；保持原失败，等待Codex裁决 |

25缺口全部进入固定修复计划：20条 `repair_executable`，5条 `rgb_review_blocked`。旧two_pots index1/3/4/5/6为5条 `reuse_only`，原manifest/replay直接引用；旧六任务、30条00均不进入准备队列。没有把25改成20的科学结论，也没有宣称物理补建已成功。

RGB没有直接放宽，是落实[033 R2工单C节](../tasks/033_round2_source_construction_fixes.md)的明确边界：“集中给出最小版本化观测容差/证书修订提案……交Codex裁决”以及“本工单未授权直接将五条失败改ready”。本次已交齐该提案与只读工具，不靠重复旧v4尝试碰通过，也不存在可暗中启用v5的flag。

## A. 抽屉容积坐标系

`construction.py` 新增显式 `in_volume` 路径，仅R2的drawer bottom region启用。原On和旧默认In保持原规则。原site姿态/父体、官方XML与BDDL不修改；容积的局部z不再被误作世界支撑法向。

候选仍在原site OBB内检查完整物体边界，使用编译后的site父体及其后代实际collision box寻找物理floor。只有薄box的最薄轴近似世界向上、宽面覆盖物体footprint才可承托，保持原5°要求；竖直墙帽不能作为floor。候选沿世界重力定位，保留物体方向与速度，检查其他容器碰撞。无法识别的mesh-only支撑明确失败，不凭空用mesh AABB制造地板。最终仍通过native In/Open、接触/稳定及原观测审计。

方法标识：`oriented_in_volume_world_gravity_v1`。CPU几何例覆盖90°region、移动父体、真实floor轴、墙面拒绝、footprint/容积约束与旧On拒绝语义。另只读核对本机pinned LIBERO `8f1084e3132a39270c3a13ebe37270a43ece2a01` 的白柜XML：bottom region属于移动的cabinet_bottom，floor薄轴与region局部z不同。XML SHA256为 `b8ebf670ad0d5533d9fedbfdd7909d263792fc6725d4ca5d4df987660cee264a`。这些不是服务器实际姿态或物理通过证据。

## B. 微波炉真实稳定后移植

显式构造方法：`selected_A_only_bounded_settle_component_transplant_v2`。旧v1/normal00默认不变，官方base仍原80步；几何种子在真正restore前恢复实测base qvel，绝不以清零速度获得稳定。

微波炉每候选至少80、最多400次真实HOLD调用。仅在连续20次采样同时满足下列条件后，复制实际完整pose/quaternion/qvel到固定base的A白名单分量：

- 实测全部qvel最大绝对值≤0.01，state有限；
- active goals为 `[true,false]`，Open及既有保持条件正确；
- 20次目标xyz的包围盒对角跨度≤0.005m。

上限耗尽、异常或未收敛均保留失败，不能导出该候选ready。收敛后仍执行原150步构造审计及2×150正式adapter回放；机器人/B和最终验收不放宽。双壶Turnon保持条件未移除。

证据schema：`remaining-selected-component-settle-v2`，含每步速度、选中pose/qvel、goal facts、稳定计数、xyz跨度、停止原因和最终完整state hash。新构造报告kind为 `selected_mask10_candidate_construction_v2`。每来源最多24候选，微波炉候选settle上界9600控制调用，另计base80、最多24×150审计及成功后的300回放。账本保存实际调用数；抛异常的调用记partial_unknown，不伪记0或按预算上限填写。无模型episode或probe。

## C. 双壶RGB诊断与提案

已核对 `build._step`、`fresh_observation`、`CandidateAuditEnv.validation_snapshot`、正式env step/reset的刷新与复制链；没有找到足以认定的漏刷新或同对象自比较缺口。已记录的同状态/非RGB一致、腕图7–9像素差1与量化差异一致，但尚不能证明GL完整成因或全部未读帧均如此。

v4在256×256时允许最多6像素差1，当前失败是旧规则准确执行。**v4准入源码、旧失败bool及旧ready验收不改。** 新增 `headless.rgb_diagnostic` 仅读取原audit，校验记录一致性并输出原文件hash、原技术结果、候选提案判断及证据限制；始终 `acceptance_authorized=false`，不能改变source状态，也不调用render/step。

最小提案为仅two_pots mask10双256×256相机使用0.00015比例（9像素），通道误差仍≤1，同时state与非RGB每次均bit-exact。10像素、误差2、缺相机/hash、状态不明等均拒绝。该数值是针对已读样例的事后工程提案，不冒充已校准误差界。若接受，需要统一版本化construction静态/动态、replay静态/动态、formal reset、manifest/profile及离线reader；必须继续按旧profile读取旧5条ready。

详见[RGB证据、限制与完整诊断命令](../../docs/task033_r2_rgb_proposal.md)。本机只读取仓库精简服务器证据和pinned源码/XML，未获得或重新逐帧核验全部服务器raw。工具报告明确区分记录完整与新像素核验，不用代表帧替代完整150步证明。

## 编排、续跑与解释器修复

新增 `headless.repair033_sources`：自动绑定原inventory/report路径及hash；原报告必须匹配公布SHA `cfe54054a85148e36e39a88dacd5658ef367f526a0970f7079d7a2586661d01e`；固定原30来源身份、25失败和5ready。逐字节复制原报告到新计划目录，不改旧文件。输出目录不得与历史工件重叠。

当前prepare精确选择drawer/microwave各0..9，自动组合新结果与原two_pots引用，不触发旧5ready或RGB5的物理操作。旧ready若文件缺失，仅列reuse_issues，不将其加入补建或整包作废。全局source/worker SHA不同不触发旧六/00/旧5重跑。

独立审查发现并复现了一个续跑边界：首条中断后，剩余19个从未尝试的原failed被普通失败保护跳过。已分开“首次替换原失败来源”与“重试R2操作”：continue只首次执行未尝试来源；已有failed/running/中断操作不自动重试；第三次continue也不会重复这20个首次尝试。正常旧ready失效保护保持不变。

R1的解释器P2一并修复：`nine_cli runtime-config` 用不解引用的absolute路径保留venv入口。Windows定向用例在不能创建symlink时采用Path.resolve边界复现；未声称本机运行了Linux模型venv。既有正确冻结runtime无需重新生成。

## 定向验证

最终合并范围命令（仓库根目录；只运行CPU/fake）：

```bash
python -m pytest \
  tests/test_task033_r2_drawer.py \
  tests/test_task033_r2_settle.py \
  tests/test_task033_r2_rgb_diagnostic.py \
  tests/test_task033_r2_repair_plan.py \
  tests/test_task033_r2_integration.py \
  tests/test_task033_r2_review.py \
  tests/test_remaining_construction.py \
  tests/test_remaining_drawer_construction.py \
  tests/test_selected_producers.py \
  tests/test_selected_preparation.py \
  tests/test_nine_source_semantics.py \
  tests/test_headless_nine_integration.py \
  tests/test_remaining_validation.py \
  tests/test_headless_nine_cli.py \
  -q --basetemp=.work/r2-final-targeted
git diff --check
```

本机Python为 `C:/ProgramData/anaconda3/python.exe`，结果 **280 passed，13.86s**；diff检查无错误。独立审查随后强化第三次continue断言并重新执行6个R2文件，**43 passed，1.44s**，无未关闭阻断；此数字与280重叠，不相加。测试验证软件边界，不证明真实来源ready。

## 仅补原失败来源的完整命令

完整说明见[运行手册](../../docs/task033_r2_source_repair_runbook.md)。以下是交给Codex核对实际路径、用户启动的命令，本轮未执行。部署到独立checkout，禁止在aedfe169/正在运行00的目录pull。复用原仿真环境与原HOLD、原OFT runtime，不升级依赖、换权重或改变推理设置。

```bash
cd /path/to/isolated/LIBERO-Remain-task033-r2
export PY=/path/to/original/libero-simulator-env/bin/python
export OLD_RUN_ROOT=/path/to/original/task033-run-root
export R2_OUT=/path/to/new/task033-r2

# 文件级：锁定25原失败，并保留5旧ready与原报告；自动生成hash。
"$PY" -m benchmark.remaining_goals.headless.repair033_sources plan \
  --inventory "$OLD_RUN_ROOT/preparation/mask10/sources.json" \
  --preparation-report "$OLD_RUN_ROOT/preparation/mask10/preparation_report.json" \
  --out "$R2_OUT/plan"

# 用户启动：只补drawer/microwave各10条原失败；不动RGB待裁决5条。
"$PY" -m benchmark.remaining_goals.headless.repair033_sources prepare \
  --plan "$R2_OUT/plan/repair_plan.json" \
  --out "$R2_OUT/preparation/mask10"

# 仅确有中断需续跑时执行，不自动重试R2自身失败/中断的操作。
"$PY" -m benchmark.remaining_goals.headless.repair033_sources prepare \
  --plan "$R2_OUT/plan/repair_plan.json" \
  --out "$R2_OUT/preparation/mask10" --continue

# 文件级组合盘点：仍有缺口时exit2如实保留。
"$PY" -m benchmark.remaining_goals.headless.selected_preparation \
  --inventory "$R2_OUT/preparation/mask10/sources.json" \
  --output "$R2_OUT/inspect-mask10" --protocol nine-mask10 --mode inspect
```

RGB只读诊断命令已在上链接逐条列出source0/2/7/8回放和source9构造原audit路径；工具拒绝覆盖输出，不改变旧报告。实际绝对服务器路径不在本机证据中，由部署方替换上述三个路径变量，无需用户手填hash。

下一步：Codex审查软件、裁决RGB提案并隔离部署；用户启动必要物理补建，Codex读取真实新报告后再形成全部30条10来源验收及评测安排。当前不交部分10模型run或allow-missing，不重跑旧六/00/旧5ready，不自动合并、不更新Eval发布、不清理历史。033整体仍open，25缺口未宣称清零。
