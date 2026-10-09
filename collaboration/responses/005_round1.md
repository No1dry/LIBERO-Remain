# 005 round1：显式subset pilot与隔离执行诊断交付

作者X，2026-10-09；submitted，等待Codex独立代码/CPU验收。本文回应[任务005](../tasks/005_subset_pilot_selection.md)及[最新审查](../reviews/x_review_stage02_stage03_codex_20261009.md)，不是新实验结果或X自验收。

交付PR：[PR #3](https://github.com/No1dry/LIBERO-Remain/pull/3)，已推送、open，未自行合并。

## 基准与提交

- PR #2已按明确授权合并；main为 `4a02c78c0b945c2df2f0748614fecdd1c5127f55`，见[登记](stage02_merge_record.md)。新分支 `x/task005-subset-pilot` 基于该SHA。
- 004独立提交：`7318c4b79cf04c5945695d492c22783710fb3098`，单独[回应](004_round1.md)。
- 005代码与测试提交：`7c47c123ae21a35a582396c4853bdf0037c2123a`。
- 后续README/交付文档提交不改变上述实现。请审查后冻结明确的最终PR HEAD；不要把本回应视作accepted，不在旧实验checkout临时pull。

## 逐项交付

| 审查要求 | 实现与可核对文件 |
|---|---|
| 完整源保持，显式选择与15/10分母 | `selection.py`重建完整mask pairing与selection hash；`pilot.py`先验证全部源state/replay，再按语义mask取原episode副本。源manifest/replay逐字节快照，不写源资产；not_selected明确。 |
| 无模型dry-plan | `evaluation.py`新增 `pilot --dry-plan --masks ...`，输出原/有效指令、所有IDs、来源index/mask、预算、模型配置、源/replay/hash及expected。 |
| 技术错误暂停 | `pilot.py`独立入口默认fail-fast；加载/环境/恢复/接口/录像/实际输入证据错误登记stop_reason、保留partial、关闭资源、停止后续，expected不变。完整success=False继续。旧run/all行为不改。 |
| 实际step0 | `runner.py`可选证据hook和 `pilot_evidence.py`，保存本次reset白名单观测typed NPZ及lossless hash；不复用构造参考，不新增环境或模型调用。 |
| 真实query/chunk | 记录输入观测step/seq/hash、返回shape/长度、接纳与实际执行区间、最后未执行尾部、STOP与异常；与trace、run、选择、episode、chunk预算绑定，离线验证。 |
| 隔离oracle | 固定未完成goal catalog language原文，仅policy.predict调用边界传有效指令；源完整instruction/specs与恢复/评分不改。拒00/11/多剩余目标，独立purpose/报告/目录。 |
| report/UIR兼容 | `cli.py`、`uir.py`、`reporting.py`使用selected expected；source和选择/模式/指令/证据严格绑定，拒选外结果和标签；主表仅选中mask的JSR/UIR，N/A/unknown/coverage保持。 |
| 原协议保留 | 原 `metrics.py`、`schema.py`、`libero_env.py`、六模型adapter、worker seeding/动作协议未改；runner无evidence时保持原schema与调用行为。 |
| 006非阻塞诊断 | [006文档](006_round1.md)，不新增初始可见性gate、场景修改或自动UIR分类器。 |

显式candidate pilot额外核对完整回放至少覆盖最大retention窗口且≥2次重复；本批150×2。校验前后manifest/replay字节需一致。旧完整all入口不收紧或改写。只读报告可接受保留BOM的合法源快照；不重写源编码。

## CPU验证与dry-plan

冻结实现完整回归：**1228 passed, 15 skipped in 70.13s**，Python 3.10仿真venv，Windows，代码 `7c47c123ae21a35a582396c4853bdf0037c2123a`。15项skip为3项Windows symlink权限、1项POSIX venv专用集成、11项未安装固定仿真源码的可选catalog检查。所有验证均为CPU/fake/现有CPU编码测试；未下载或加载模型、未新建真实仿真、未启动GPU实验。

```text
<simulation-python> -m pytest tests -q -ra --basetemp reports/pytest_stage03_delivery_final_v2
```

专项也分别通过：004 worker/metadata 33 passed、2 skipped；selection/UIR 119 passed；旧UIR CLI/metrics 59 passed；runner/evidence/video与当时集成集154 passed；最终独立pilot集成34 passed；候选source完整性14 passed。这些是交叠的测试组，不相加冒充独立样本。覆盖了12类启动/恢复/接口/录像/实际输入证据技术故障、组合关闭故障、真实查询/STOP/截断、完整policy失败继续、BOM源字节保持、源与选择/回放/工件篡改拒绝、旧默认all兼容。`git diff --check`通过。

已执行的两个dry-plan样例：

| 工件 | 源规模 | selected | not_selected | 预算合计 |
|---|---:|---:|---:|---:|
| [primary CPU dry-plan](../artifacts/005/primary_cpu_dry_plan.json) | 20 | 15 | 5 | 7450步 |
| [oracle CPU dry-plan](../artifacts/005/oracle_cpu_dry_plan.json) | 20 | 10 | 10 | 6700步 |

这两份是**实际调用新dry_plan函数生成的五来源toy合同样例**，H520/W150、seed7/chunk8，weights_loaded=false、simulation_created=false；不是服务器001状态或VLA证据。当前X工作区只有已公开审查资料，没有完整001状态/独立回放副本，因此未伪造001 dry-plan或重建替代样本。服务器真实001的两条可复制plan/run命令见[详细指南](../../docs/remaining_goals_subset_pilot.md)，执行者须按源manifest字节SHA/content hash核对15/10计划再运行。

## 执行交接与限制

正常primary只load一次、15次reset；oracle只load一次、10次reset，实际尝试/完成次数写runtime_counts；每episode现有worker seed7/reset和队列清空保持。10/01=670步、11=150步，不由真值停车。技术暂停后不自动重试/替补/缩分母；没有GPU新结果。

实际输入证据是adapter预处理前观测，不冒充最终encoder tensors；模型信息判断须结合真实crop/proprio/指令与下一query机会。UIR人工审查按当时已满足目标或整体完成及操作必要性判断；未完成目标反复失败不直接UIR，合理观察/试抓/收尾不自动UIR，无法确认则unknown。

视频/证据故障可暂停批次，但视频本身不重新定义已完整轨迹JSR。`read_run`拒绝已引用工件损坏，不能通过降级status绕过。模型加载前或证据初始化前失败明确无实际step0；不虚构。run.json记录状态/原因，不能只凭exit0裁决。

Codex验收新代码后，在新checkout复用既有runtime/同一checkpoint与001源文件，先固定主15条，再按Plan3执行最多10条隔离诊断。完整运行命令、runtime metadata复用、文件结构、只读UIR派生入口均在[指南](../../docs/remaining_goals_subset_pilot.md)。X未自行合并005，未跑00/新VLA，未改旧raw/summary/UIR标签，未关闭科学阶段。
