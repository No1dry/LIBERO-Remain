> 2026-10-16完成：本页07_normal_bank已由用户执行，15/15（100%）并经完整文件验收；Codex已完成08_shadow_plan。不要重复准备来源。下一步用[5条普通shadow采集手册](stage04_calibration_shadow_runbook_2026-10-16.md)。下文原命令保留为历史。

# Stage04：动作parity通过后的普通official-init来源准备

2026-10-16。只由用户启动07_normal_bank。此前audit、features、小头训练和32输入动作parity均完成，不重跑；冻结实际代码3433f487d38efe0a08e4c814e87412aad5aba9fe，原sim与assets不改。

## 本次唯一真实命令

在服务器root@122.204.216.104:30369执行；不在文档保存密码：

```bash
bash
source /HUBU-AI096/zp/ICML/stage04_finish_3433f48/session.sh
finish_sim 07_normal_bank prepare-normal \
  --source-registry /HUBU-AI096/zp/ICML/stage04_finish_2cb1428/results/run01/registry/registry.json \
  --indices 35 36 37 38 39 40 41 42 43 44 45 46 47 48 49 \
  --out /HUBU-AI096/zp/ICML/stage04_finish_2cb1428/results/run01/normal_bank
```

source只加载会话，最后一条才创建仿真恢复官方初态并保存正常00来源。**这一步不运行VLA、不训练、不校准阈值，也不是15条模型rollout。** 15个official init：35..39仅用于后续5条normal_calibration shadow，40..49仅用于10条独立normal_test。HDF head_validation不替代这两组，不能按demo编号猜init。

## 为何输出路径含旧2cb1428

目前新／旧normal_bank均未生成，整个旧目标目录也已只读确认不存在。已经冻结的validation_shadow／normal_active job JSON引用旧2cb目录的registry与normal_bank，新3433的runtime和head。因此本步在**此前不存在的新子目录**生成bank，沿用既定资产位置，不修改11个冻结部署文件、不覆盖旧audit或失败features。

实际执行仍由新3433 session及源码完整性校验控制，log为/HUBU-AI096/zp/ICML/stage04_finish_3433f48/logs/run01/07_normal_bank.log；目录名不是生产代码SHA，不把bank误署为旧2cb执行。prepare-normal的mkdir(exist_ok=False)与日志noclobber防覆盖。输入registry已存在，身份仍f8706e9018e618566f53165b50b8e21e6347c089a500cbe3bc21c0930ff8edfe。

## 完成后与边界

预期normal_bank.json schema为v2、status=prepared、expected_indices恰为35..49，15个episode／preparation各一次，command_exit=tee_exit=0；由Codex只读核验state／initial observation／preparation与官方init/index/SHA/BDDL和registry身份。失败或中断保留partial，不原地重跑／删目录，不擅自改变编号或split。

用户完成后Codex做file-only dry-plan和下一步命令准备，再由用户启动5条普通shadow停止校准；阈值冻结、10条normal active停止能力测试，再15条Remain active。尚无新协议模型成功率，不把parity100%当任务成功100%。不因2个验证正例少临时换分组或看测试调头。所有真实阶段仍用户启动，Codex不代跑或后台排队。

[parity验收](../stage_summaries/stage04_parity_pass_2026-10-16.md)。008／Stage04未closed，待删=[]。
