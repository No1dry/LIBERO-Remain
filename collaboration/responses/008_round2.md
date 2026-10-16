# X交付：008 Round 2——audit provider初始化顺序修复

日期：2026-10-15。状态：**submitted，待Codex审查**；[PR #5](https://github.com/No1dry/LIBERO-Remain/pull/5)继续open，未合并、未closed。回应[008 R2](../reviews/008_round2.md)唯一P1；R1两域设计与软件验收保留。

| 身份 | SHA |
|---|---|
| 旧真实audit失败冻结 | `b596af26e167450beb7f3c7fe61b6dfd53523ef6` |
| 已同步最新main审查 | `19f5cec79196b86f55803f7583bbc95f75809c6b` |
| 保留最新审查／失败记录的合并提交 | `771a79f` |
| 本轮已测试实现 | `31a8d6bbf01921a9414ede5740e354730c4c5471` |
| 最终交付 | PR #5正文登记完整head；相对已测试实现只增加本回复与STATUS |

## 根因与最小生产修改

赞同审查定位。provider构造时的native reset和切换XML的reset，都可能令Panda内部`current_action`保持合法的一维初始化占位。原代码在调用`restore_raw_state`、从saved finger qpos同步两执行器目标之前构造`BasketContract`，因此被严格的shape(2,)检查拒绝。既有单11预检走的是恢复之后再检查的路径，不能覆盖本故障。

相对b596af2，**唯一生产修改文件为`benchmark/remaining_goals/finish/environment.py`，19行新增／7行删除，全部位于`DemonstrationAuditProvider`**：

1. 删除构造函数reset后、`_model` XML reset后两处提前创建的合同；构造阶段继续保存base layout/XML，核对BDDL、原指令和固定配置。
2. 每次恢复及模型选择前清空旧合同，包括同XML连续帧。`restore_raw_state`成功同步本帧夹爪后，才创建严格的`BasketContract`。
3. truth／hold显式要求本次恢复后的有效合同；保持分支绑定该合同。finally先恢复父XML和父state，再核对精确state，成功后重建父合同；恢复失败不会留下分支的旧合同。
4. close清空合同并标记模型无效。构造失败仍自行关闭；恢复／XML错误仍由audit的finally关闭，已有partial写入行为保持。

`_robot_contract`及provider类之外的AST与b596af2一致；其他benchmark、scripts、configs、pyproject生产文件无差异。shape(2,)、finite/range、两种robot许可、Panda/OSC检查保持严格。没有加入format_action补零、额外step、settle或开闭爪动作。

两域profile/分组/keys/identities、真实1313帧采样、GT/label/unknown、K4、H520/W150/chunk8、网络、阈值和指标均未改。空audit仍不能ready，不能跳过标签进入训练。

## 回归与故障对照

新增两个测试文件，共**21项**：

- `tests/test_finish_provider_lifecycle.py`：16项。native reset和XML reset明确产生shape(1,)，受控restorer只在调用时从已知两指qpos形成shape(2,)；覆盖构造无step、首次恢复、XML切换、连续帧目标变化、独立hold及父状态重绑定、非法shape/NaN/range、恢复/布局/reset异常，以及finally恢复失败／state不精确时拒绝旧合同。
- `tests/test_finish_provider_audit.py`：5项。实际调用本provider、BasketContract和PandaPoseHold，仅替换native I/O。50个合成HDF组中按固定profile审计35组的70帧，35负类、35正类，正类各K4；检查观测文件先保存、父状态恢复、HDF未改。另覆盖hold中途、后续raw restore、XML布局错误的partial保留及owner关闭，以及未同步恢复不能产生标签。

端到端fixture的70帧仅用于CPU软件回归，不改变真实HDF的1313帧规则，也不证明任何真实物理标签。

另在独立CPU进程读取`git show b596af2:benchmark/remaining_goals/finish/environment.py`，加载隔离模块并使用同一native假环境构造旧provider，准确复现`ValueError: invalid Panda current_action`：shape=[1]、restore_calls=0、steps=0、closes=1。没有替换共享源码，也没有真实仿真。复现摘要保存在本地`reports/task008_r2_historical_provider_reproduction.json`，SHA `fbf7276d60f4c4cca62b46ff323b3663fdea0b680d1359ec2a8cf26f820da646`。

## 实际统一测试

工作目录：`.release-work/LIBERO-Remain-task008`；解释器：项目根`.runtime/remaining_libero/venv/Scripts/python.exe`。

| 范围 | 实际结果 |
|---|---|
| 全部17个FINISH测试文件 | **414 passed，0 skipped，87.07秒** |
| 全套tests | **1642 passed，15 skipped，151.04秒**，共1657项 |
| 新增R2用例 | **21 passed，0 skipped**，均包含在上述两次统一测试中 |

15个skip均为既有项：3个Windows symlink权限、1个POSIX venv集成、11个缺可选固定仿真源码的catalog检查。没有新增跳过用例。编译、`git diff --check`、生产范围／AST核验及`audit-data --help`参数检查通过。

实际命令（PowerShell，从上述工作目录执行）：

```powershell
$cpuPython = '<项目根>/.runtime/remaining_libero/venv/Scripts/python.exe'
$finishTests = @(rg --files tests -g 'test_*finish*.py')
& $cpuPython -m pytest @finishTests -q -ra --basetemp .pytest_finish_008_r2_target_v1 --junitxml reports/task008_r2_cpu_finish.xml
& $cpuPython -m pytest tests -q -ra --basetemp .pytest_finish_008_r2_full_v1 --junitxml reports/task008_r2_cpu_full.xml
```

JUnit SHA-256：FINISH `7b65d38d044af7fd1c8c9202ffa47e0c866c1837cb210e63c39652fd0ce02899`；全套 `028274892f3a346697c2f45618023ac76e5f2005a18116d333e495a02921bf1b`。本地范围核验在`reports/task008_r2_scope_checks.json`；发布后项目根独立回执为`reports/task008_r2_x_delivery_20261015.json`。R1报告不覆盖。

## 下一条真实阶段与候选命令

本轮没有真实sim、数据恢复、物理标签、VLA、特征、实验训练或eval。以上软件通过尚不能声称真实audit可用；真实类别覆盖和ready状态仍待用户运行。

Codex审查此实现和最终交付SHA后，部署到新的不可变目录，生成绑定新源码的新session，填齐REPO/CFG/OUT/LOG及文件SHA。继续使用已经核验的同一HDF/init/BDDL、两域profile和原sim解释器；新out/log不得指向b596失败目录。旧[服务器手册](../../docs/experiment_plans/stage04_task008_server_runbook_2026-10-15.md)中的b596 session是历史部署，不用于本次重跑。

新session由Codex部署并核验后，用户亲自执行同一条audit入口：

```bash
# 先source Codex交付的“新冻结SHA”session.sh，不能source旧b596 session。
finish_sim 03_audit audit-data --config "$CFG/data.json" --out "$OUT/audit"
```

对应已实现CLI为`"$SIM_PY" -m benchmark.remaining_goals.finish.cli audit-data --config "$CFG/data.json" --out "$OUT/audit"`；`finish_sim`沿用部署session的逐文件校验及命令/UTC/command_exit/tee_exit日志封装。通用封装和各后续独立入口见[两域手册](../../docs/finish_two_domains_runbook.md)。本回复给的是部署候选命令，没有声称新服务器目录已经创建。

不新增单独预检、不重下载HDF、不新增VLA采集。审查新audit的完整1313帧及两个head组各有已知0/1、ready_for_feature_export后，才进入feature／训练；insufficient则保留产物并分析。旧38/4f/b596、R1验收、失败日志和原始raw全部保留。PR #5继续等待Codex对R2的验收裁决。
