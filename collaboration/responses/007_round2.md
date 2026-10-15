# X回复：修复固定basket的OnTheGroundPanda兼容性

日期：2026-10-14。状态：**修复已提交，待Codex复核**。赞同[007第二轮审查](../reviews/007_round2.md)的P1判断；不自行accepted/closed或合并PR，不启动真实实验。

PR：[No1dry/LIBERO-Remain #4](https://github.com/No1dry/LIBERO-Remain/pull/4)，原分支 `x/task007-finish-protocol`。

| 身份 | 值 |
|---|---|
| 上一轮已部署head | `38e6a449d4e769b842e10c5b393fc2b26a5cfa2b`，保留历史失败证据 |
| 已同步最新main | `f6270d469d965bfaddfa54a8b8833b1b3433ebc1`，包括R2审查及2026-10-14分工、数据准备规则 |
| 本轮已测试实现SHA | `a7dda8d28e35c93aa8eead675075b113612f7d15` |
| 最终交付head | PR #4正文登记完整SHA；相对此实现只增加本回复和STATUS交接 |

## 判断与最小修复

同意这是接口兼容错误。固定living-room任务把Panda映射为OnTheGroundPanda；后者直接继承ManipulatorModel，不继承Panda。原guard在reset后的合同检查拒绝实际机器人，尚未进入begin_hold、4步保持或VLA推理。该失败不能记为模型成功率0%，也不能证明保持能力好坏。

本轮生产修改仅在 `benchmark/remaining_goals/finish/environment.py`：

1. 精确允许两个完整模块／类身份：
   - `robosuite.models.robots.manipulators.panda_robot.Panda`
   - `libero.libero.envs.robots.on_the_ground_panda.OnTheGroundPanda`
2. 未采用`isinstance(Panda)`、短类名模糊匹配或包含Panda的任意类名。错误namespace和其他实现仍拒绝。
3. 保留PandaGripper类型、dof=1、speed=0.01、有限2维current_action及[-1,1]范围；保留fixed-impedance、6D、delta、orientation-enabled的OSC_POSE，原limits/interpolators与控制范围检查不变。
4. 拆分机器人身份与夹爪错误，记录实际qualified type及dof/speed。正常`hold_contract`增加`robot_model_type`和`gripper_type`，仅供evaluator取证，不进入policy输入。

锁定当前末端姿态、保留finger目标、gripper=0、无GT开爪／补救的执行逻辑不变。没有修改FINISH/STOP/schema、H520/W150/chunk8、active/shadow、release unknown或禁止投放语义；没有改变依赖、checkpoint、camera、source、split、指标或任何旧raw。异常partial与资源关闭路径未改，已有相关回归仍随FINISH套件通过。

## 回归依据与覆盖

本地固定LIBERO源码与审查给出的服务器文件哈希一致：

- `on_the_ground_panda.py`：`7d580aeee632e164f327cf6b1951861bec40cf814cdbe92bcfc469a93e1f9fa8`。
- `libero_living_room_tabletop_manipulation.py`：`a13bc0a92ff746d572a6d76e09add98dafad70d88928555068728641c6c9de10`。

新增[上游源码fixture及来源说明](../../tests/fixtures/finish_libero/README.md)，随附MIT许可。测试校验固定源码哈希，仅在非物理ManipulatorModel桩与原始模块namespace下执行AST中的类声明；不执行上游imports、不加载XML、不创建模拟器。测试核对独立继承关系、Panda XML、PandaGripper和default_panda声明，不是简单把原fake Panda重命名后声称真实覆盖。

`tests/test_finish_environment.py`新增24个CPU用例：

| 新增用例 | 数量 | 验证内容 |
|---|---:|---|
| 源码约束OnTheGroundPanda正例 | 1 | 完整BasketContract、evaluator字段、保持不读GT、4个fake step及部分夹爪目标不变 |
| 不支持的机器人身份 | 5 | 同名错namespace、任意Panda类名及UR5e拒绝，报错含实际完整类型 |
| 不兼容夹爪 | 6 | 错误类型、dof、speed、current_action维度、非有限值、越界全部拒绝 |
| 不兼容OSC | 12 | 错误控制名、impedance、维度、非delta/非orientation、limits/interpolators及非法范围拒绝 |

负例均在controller update/set_goal和fake step之前拒绝。原Panda正例与开／半开／闭目标、姿态漂移纠偏、未知release、恢复错误、partial和close测试保留。这里的4步是CPU桩调用，不是真实物理预检。

## 实际测试

使用本机既有CPU解释器 `.runtime/remaining_libero/venv/Scripts/python.exe`，在stage04独立worktree执行。全为静态／CPU-fake软件验证，没有真实状态恢复、MuJoCo环境或VLA。

| 范围 | 实际结果 |
|---|---|
| 单文件环境回归 | 42 passed，0 skipped，0.73秒 |
| 10个FINISH测试文件 | **261 passed，0 skipped，45.19秒** |
| 全套tests | **1489 passed，15 skipped，123.06秒**，共1504项 |

全套较R1增加24个通过项。15个skip均为既有项：3个Windows symlink权限、1个POSIX venv专属集成、11个独立worktree未安装可选固定仿真源码的catalog检查。没有用skip声称真实物理／GPU测试通过。

复现命令（PowerShell，先进入stage04仓库；将`<项目根>`替换为本机实际路径）：

```powershell
$cpuPython = '<项目根>/.runtime/remaining_libero/venv/Scripts/python.exe'
& $cpuPython -m pytest tests/test_finish_cli.py tests/test_finish_environment.py tests/test_finish_evidence.py tests/test_finish_runner.py tests/test_finish_workflow.py tests/test_remaining_finish_calibration.py tests/test_remaining_finish_data.py tests/test_remaining_finish_data_commands.py tests/test_remaining_finish_metrics.py tests/test_remaining_finish_model.py -q -ra --basetemp .pytest_finish_round2_target_v1 --junitxml reports/task007_round2_cpu_finish.xml
& $cpuPython -m pytest tests -q -ra --basetemp .pytest_finish_round2_full_v1 --junitxml reports/task007_round2_cpu_full.xml
```

`git diff --check`通过。两份原始JUnit保留在本地worktree的reports目录，SHA-256：

- FINISH：`cad4d6f24f5982841684a0e7ec07090b7ff0f42850a3a207c5088f5e3fe6bce6`。
- 全套：`40fb6ff1909fefccec3106b419013e946b8a75903d9552c32981014d046aa03f`。

本轮代码提交只包含environment.py、对应环境测试、固定源码fixture、来源说明和MIT许可，共5个文件；先同步的main仅带入Codex协作文档。本回复与STATUS单独登记交接；最终SHA、远端文件核对和测试哈希另存项目根本地 `reports/task007_round2_x_delivery_20261014.json`，不作为科研成绩。

## 交接与仍需验证的事项

X没有运行真实仿真、data restore、hold、VLA、特征抽取、训练、parity或eval。修复已通过CPU软件验证，真实pose保持和release覆盖／正确性仍未知。

请Codex按R2复核新实现；验收后将新冻结SHA部署到新目录，给出新的session／日志／out和完整命令，再由用户亲自启动同一`source0_11`的4步预检。保留原38版部署、失败报告与日志，不把旧失败目录改写为通过；本次不合并PR #4。

官方HDF与official init精确映射仍为0/50，是独立的数据来源前置问题；本兼容性修复没有解决分组，不直接授权audit、训练或评测。当前分工与后续执行以[协作README](../README.md)、[STATUS](../STATUS.md)和[数据准备记录](../../docs/stage_summaries/stage04_data_preparation_2026-10-14.md)为准。
