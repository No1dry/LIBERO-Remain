# 031 round1：normal00 与缺失两任务的局部制备交付

日期：2026-11-01。实现：X。状态：**本地软件实现及审查完成，待 GitHub 发布、Codex 审阅部署与用户真实运行**。没有自动合并，没有宣称两任务物理故障已修好或100条来源已齐。

## 固定版本与范围

- 仓库：`No1dry/LIBERO-Remain`；独立分支：`x/task031-normal00`。
- 固定实现 commit：`0a198a18d05d7a893518aa50d42f48e15e8172c2`。
- 已审代码 parent：`c6dc98de0c54517c976057598b60f4cedf7fa3e5`。先同步 main 的031任务/研究文档，形成 `3c4daf7c0ca049d63f7740ee3746443d0700459d`；确认这一同步没有修改 benchmark/scripts/tests/configs/pyproject 代码。
- 本轮实现增量相对 `3c4daf7` 为29文件、3279新增／86删除行，含7个新测试文件、3个配置示例、runbook与计划。相对c6的代码范围可用下述diff单独查看；同步的main历史文档不是新增科研结论。

```bash
git diff c6dc98de0c54517c976057598b60f4cedf7fa3e5 0a198a18d05d7a893518aa50d42f48e15e8172c2 -- benchmark tests configs
git show --stat 0a198a18d05d7a893518aa50d42f48e15e8172c2
```

本轮只做受影响CPU／fake检查，没有真实sim、reset/restore、制备／回放、模型推理／eval、HDF／图像数据作业或训练。未改方法库、未同步Eval第二套实现、未清理旧数据／目录／PR。

## 已实现

1. 显式normal00协议、初始来源验收、环境／runner／schema／evidence／评分。实际t0必须00；保持指标为`null`／N/A，A/B合法性沿用原目标和目的地。其余事件、释放与连续5观测终点、seed7/chunk8/H520、完整原指令和SOG10输入不变。录像缺失不能认证completed。
2. selected-mask10逐来源验收和新构造／正式adapter回放路径，仅两个固定任务、indices0..9。有效构造缺回放只回放；ready零物理调用；00/01/11失败不连坐，但10的150构造与至少2×150独立回放仍必需。固定阈值、HOLD、谓词不放宽。
3. 原manifest／construction／replay／initialization逐来源hash绑定与可归档组合清单；不把旧回放source hash改写成混合manifest，不虚构全mask原银行通过。相同audit或reset工件路径不能重复计为两次独立回放；确定性重复允许不同文件字节相同。
4. 固定normal00全分母100，先existing-eight80、再missing-two20；selected10只允许missing-two20。单来源失败独立记录，`--allow-missing`显式接受部分范围，`--continue`只补尚未尝试来源；保留原始错误／损坏文件，不隐式重跑。
5. `--prior-run`可把两阶段00汇总，冻结原batch字节、递归核对实际模型身份，保留前阶段缺失／技术错误原因。空载模型的中间阶段不会丢失祖先实际模型身份。
6. 制备续盘点会重新验收曾ready的来源，损坏／丢失变为failed/missing，旧通过证据保留为历史；不会自动转成重建／回放。一次已失效来源恢复原文件后，可在新的只读inspect输出重新确认，不因缓存状态触发重试。

## 原证据复用与未解决项

| 范围 | 本轮可据什么确认 | 复用／补齐规则 | 尚未确认 |
|---|---|---|---|
| 原八任务80条10 | 历史阶段摘要 | 原raw、状态、回放、评分v2保留；新入口不重跑 | 本轮没有重新核对服务器完整raw |
| 两任务其他18个来源 | 历史记录“已构造” | 逐来源只读验收有效构造；缺回放才补回放 | 不能预称18条独立回放ready |
| frypan_stove9来源4 | 031原audit数值摘录 | 旧00 step142腕RGB7/65536像素差1、超0.0001规则，保留失败；必要时仅新建固定10 | 未有本地完整原audit；未证实渲染缓存成因／物理恢复 |
| cabinet_close_top_bowl来源5 | 031原audit数值摘录 | 旧00 step7 qvel[12]=0.1636081576、超0.01，保留失败；必要时仅新建固定10 | 未定位关节名称／成因，未证实真实10可用 |
| 原00来源 | 保存npy＋typed初始观测＋原audit＋初始化报告 | 必要t0有效即可单独normal00验收；旧后续hold失败仍披露 | trace0存在不等于原状态/观测已导出；缺文件就缺证据 |
| 缺失两任务00 | 新版本官方固定init→settle80→steps0验收 | 用户独立启动normal00制备；注明settled base／官方资产身份 | 未运行，不能预称20条通过 |

新selected构造方法为 `selected_A_only_settle_component_transplant_v1`，区别于旧全目标settle后配齐所有mask；新00为 `official_fixed_init_settle_initial_only_v1`。改变构造方式明确版本化和新输出；不假装与旧状态逐字节相同、不宣称同index仅A关系不同。若真实10仍不稳定，报告原数值／原因，先交Codex裁定，不加阈值／清速度／换来源。

## 真实可用入口、格式和命令

完整说明、配置结构和可复制命令见[031 runbook](../../docs/task031_normal00_selected_preparation.md)。独立入口：

```bash
python -m benchmark.remaining_goals.headless.scoped_cli --help
python -m benchmark.remaining_goals.headless.selected_preparation --help
```

`scoped_cli`有`budget-plan`、`sources-template`、`dry-plan`、`run`、`inspect`、`summarize`；run有`--config --out --allow-missing --continue --prior-run`。旧`headless.cli`默认10保持；旧rescore不接00。

制备有`--inventory --output --protocol --mode --tasks --indices --continue --allow-failed-retry`，mode为`inspect`（默认只读）／`build-missing`／`replay-missing`／`prepare-missing`。制备与模型eval绝不自动串联。失败重试仅新尝试、同固定规则，不能当改变物理规则的授权。缺失／失败CLI返回2。

组合来源schema为 `remaining-headless-composite-sources-v1`：完整expected列表＋逐task/index的origin（原manifest raw/content hash，原replay hash或normal00初始化报告hash）。每个ready来源重新验证state／观测／audit，运行归档可以离线读；多阶段prior目录需保留。normal00来源schema `remaining-headless-normal00-source-acceptance-v1`，selected10为 `remaining-headless-selected10-source-acceptance-v1`，不冒充旧v1整任务验收。

三个示例配置：`normal00-control.example.json`、`normal00-missing-two.example.json`、`selected-mask10.example.json`，位于 `configs/remaining_goals/headless/`。Codex下一步核对服务器路径与既有SOG10环境，给完整conda/python命令；用户先跑80条00，再独立补来源，再20条00＋20条10。新增模型总目标120，准备物理步数另有ledger，不报告为模型步数。

## 验证与审查

受影响CPU／fake回归 **272 passed / 121.95s**，覆盖新00、新来源、新制备、旧runner／environment／geometry／support v1/v2／workflow／mask10验收／rescore。最后一处跨阶段汇总修正先新增测试复现失败，再跑相关planning＋workflow **9 passed / 10.55s**。未要求整仓、多平台、GPU或全mask发布验收。

独立审查分别覆盖runtime、来源、制备、集成及最后跨模块审查；明确问题均修正并复审通过：重复回放文件计数、跨层prior实际模型身份、续跑错误退出状态、制备ready缓存失真、前阶段技术缺口诊断丢失。审查通过只代表本次软件范围。

本地验证命令（示意，与实际已执行范围一致）：

```bash
python -m pytest tests/test_headless_normal00_runtime.py tests/test_headless_normal00_environment.py tests/test_headless_runner.py tests/test_headless_environment.py tests/test_headless_support_versions.py tests/test_headless_geometry.py tests/test_headless_integration.py tests/test_headless_scoped_sources.py tests/test_headless_source_acceptance.py tests/test_headless_scoped_planning.py tests/test_headless_scoped_workflow.py tests/test_selected_preparation.py tests/test_selected_producers.py tests/test_headless_workflow.py tests/test_headless_mask10_workflow.py tests/test_headless_support_rescore.py -q --basetemp=.work/pytest031-final
python -m pytest tests/test_headless_scoped_planning.py tests/test_headless_scoped_workflow.py -q --basetemp=.work/pytest031-finalfix-green
git diff --check
```

## GitHub交付状态

本轮未能发布独立PR：浏览器连接重置后仍报告browser access host unavailable，native pipe也不存在；公开仓库HTTP读取200，未认证GitHub写入端401。Git dry-run未形成可用写入会话，未写远端分支，未合并，未使用历史token。完整本地代码／git历史／回复／说明已准备，根目录交付包可直接交给具备仓库写权限的会话发布。恢复已登录浏览器或现有Git认证后推送独立分支并创建PR即可；不应把这份本地回复误认为已在GitHub可见。
