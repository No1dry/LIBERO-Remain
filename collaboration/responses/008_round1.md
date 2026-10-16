# X交付：008 两来源域数据合同与完整消费者迁移

日期：2026-10-15。状态：**submitted，待Codex审查**；不自行accepted/closed，不启动真实实验。独立[PR #5](https://github.com/No1dry/LIBERO-Remain/pull/5)，分支`x/task008-data-source-domains`。

| 身份 | SHA |
|---|---|
| 007已验收实现／原交付 | `4f76f4917a9174fc5b80ef83e3cf21eaf053c98d` |
| 007合入最新main文档后的PR头 | `48cad17b0df8b1391450f639f1761c8885bd6068` |
| PR #4已合并main／008独立base | `94c061e99168d76fbe50bef85b187db8fe2b9898` |
| 本轮已测试实现 | `b973133a08216eaab4a36901b1b968c4d8b87452` |
| 最终交付 | PR #5正文登记最终完整head；相对已测试实现只增加本回复与STATUS |

## 007合并登记

依据[007 R3 accepted](../reviews/007_round3.md)与[008 A.1](../tasks/008_finish_data_source_domains.md)授权，已合并[PR #4](https://github.com/No1dry/LIBERO-Remain/pull/4)。先合入最新main `4bad486`的008需求、Plan4及分工；唯一STATUS冲突采用新版main。逐文件确认benchmark/scripts/tests/configs/pyproject相对已审4f实现无差异，再以48cad17合并，得到main 94c061e。

008从该main建立新工作树／分支，没有追加为007返修。4f真实单11四步通过、38旧技术失败及原始产物全部保留，不改为新模型成绩；007和Stage04不因此closed。

## 实现范围与身份版本

代码提交共24个文件：finish目录7个消费者模块及2个新模块；5个示例配置；README与两份手册；5个新增测试文件和共享合成fixture；仅忽略本轮临时CPU测试产物的gitignore规则。

| 消费者 | 实现及绑定 |
|---|---|
| profile／registry | 新`data_profiles.py`、`data_registry.py`；固定30/5/15 HDF轨迹组与5/10/5 eval初态组，实际三资产SHA、group、frame/state/XML摘要、各域coverage；不创建环境或标签 |
| audit／validate_audit | `data.py`显式`remaining-finish-data-audit-v2`；不要求demo首state匹配init，只恢复预定head_train/head_validation；保存当前观测后才做K4标签分支；重新核源文件与物理证据 |
| feature cache／export/load | `remaining-finish-feature-cache-v2`；严格继承audit、profile/registry、合法raw/input/feature/base/code身份，拒绝遗漏行、错组、错state/XML和篡改标签 |
| head／training | `remaining-finish-head-v2`及training-v2；四身份槽保留，`split_identity`明确为两域身份v2；train仅head_train，epoch仅head_validation；head.training额外绑定validated cache、feature文件和输入行SHA |
| parity | selection/command-v2；32不同输入只来自HDF head_validation，state/raw observation/实际model input分别去重，不足不借其他组；同worker原/shadow双forward及RNG恢复机制不变 |
| normal-bank | 显式bank-v2；`prepare-normal --source-registry`绑定实际init文件SHA及原始pre-settle state摘要，再保存既有prepared state、XML、BDDL和审计绑定 |
| job／dry-plan／run／read | job/plan/run-v2；按eval registry选择normal_calibration 35..39、normal_test 40..49、Remain 0..4×三mask；开模型前即核完整head身份四槽与逐槽hash |
| calibration | calibration-v2；固定eval normal_calibration五成员，与HDF head_validation分开；active核同head、profile、registry、eval角色和全部成员 |
| CLI／配置／手册 | 新增纯文件`register-data`，共14个显式CLI阶段；新模板不含旧trajectory_source_map；提供完整[两域运行手册](../../docs/finish_two_domains_runbook.md)，旧手册明确标为历史流程 |

新profile为`remaining-finish-data-profile-v2`／`basket-two-source-domains-v1`，registry为`remaining-finish-source-registry-v2`，身份为`remaining-finish-source-domains-identity-v2`。

HDF键为`hdf:{实际文件SHA}:demo_N`；eval键为`init:{实际文件SHA}:N`。新head row使用domain/role/source_key/trajectory_id/saved_state_index，不制造旧source_index别名。registry和identity始终明确`ancestry_independence=unproven`；`demo_35`不解释为`init35`。旧统一source合同不能默默进入v2；无新标记的旧v1默认和历史读取保留，混入新字段或新schema则拒绝。新config缺profile但仍有expected_assets也不会静默降级。

注册时实际读取文件并与expected_assets比较，检查50组轨迹／50个init向量、请求成员、采样和跨head组直接重复state；unused只做必要文件检查。registry没有标签、不能ready。新audit/cache/export/train及job启动前复验源文件SHA；冻结run离线read/calibrate使用其完整registry快照，不依赖后来机器路径，也不改旧raw。

## 标签、泄漏与不变项

当前不全完成或已证夹持为0；当前全完成且released=True，再从同一state按原hold合同K4稳定才为1；缺释放／几何／保持证据仍unknown。不用末帧、未来示范动作或time生成标签。先保存当前合法输入，分支结束恢复父状态；实际XML/layout仍由已验收provider核验。

跨head组trajectory/state/raw observation直接重复、eval/edited行混入head缓存、错误domain/role/key、错误profile或资产、已重算外层hash但内部身份／标签不符均拒绝。未知标签不能改列值变成正负类；train和head_validation都要各有已知0/1，file-only不能通过。异常保存partial，保留原始当前观测与计数并关闭provider；malformed hold返回也不能破坏错误落盘。

本轮未改`environment.py / runner.py / schema.py / metrics.py / evidence.py / oft.py`，包括两类机器人许可、hold/release、无GT停车／开爪、禁止投放、原动作forward、crop/seed/chunk、H520/W150和评分。原标签推导、56-token池化和MLP声明AST一致；优化器、pos_weight规则、BCE/earliest tie及阈值first-hit算法不变。只修改数据来源选择、身份验证和相应metadata。没有新增VLA采集、重新下载HDF、真实渲染或真实状态恢复。

旧source001保存的是已准备／编辑状态，不能要求它等于raw official init。008继续校验既有index、savedstate、modelXML、BDDL、preparation/source/replay，再关联registry实际eval键；明确这是index关联，不回填旧包未记录的pre-settle来源证据。新normal-bank则直接验证实际原始init文件和state摘要。

## 实际CPU验证

Windows既有解释器`<项目根>/.runtime/remaining_libero/venv/Scripts/python.exe`，工作目录为独立`.release-work/LIBERO-Remain-task008`。全部使用tiny合成HDF/数组、受控provider/model worker或CPU小矩阵；不加载真实VLA、不执行LIBERO状态恢复或实验训练。

| 范围 | 实际结果 |
|---|---|
| 全部15个FINISH文件 | **393 passed，0 skipped，86.44秒** |
| 全套tests | **1621 passed，15 skipped，154.96秒**，共1636项 |
| 008新增5个测试文件 | **132 passed，0 skipped**：CLI 8、workflow/calibration 29、data domains 52、cache/parity 25、head/training 18 |

15个skip均为既有项：3个Windows symlink权限、1个POSIX venv专属集成、11个独立工作树缺可选固定仿真源码的catalog检查。没有新增被跳过的008用例，也未把这些CPU结果写成科研成绩。

```powershell
$cpuPython = '<项目根>/.runtime/remaining_libero/venv/Scripts/python.exe'
& $cpuPython -m pytest tests/test_finish_cli.py tests/test_finish_environment.py tests/test_finish_evidence.py tests/test_finish_runner.py tests/test_finish_workflow.py tests/test_remaining_finish_calibration.py tests/test_remaining_finish_data.py tests/test_remaining_finish_data_commands.py tests/test_remaining_finish_metrics.py tests/test_remaining_finish_model.py tests/test_finish_domains_cli.py tests/test_finish_workflow_domains.py tests/test_remaining_finish_data_domains.py tests/test_remaining_finish_domain_consumers.py tests/test_remaining_finish_domain_model.py -q -ra --basetemp .pytest_finish_008_target_v1 --junitxml reports/task008_cpu_finish.xml
& $cpuPython -m pytest tests -q -ra --basetemp .pytest_finish_008_full_v1 --junitxml reports/task008_cpu_full.xml
```

JUnit SHA-256：

- FINISH：`bf988c29c8831f2c3deb381ccce1c22f1cbef4d1701ef2f00130903af421882f`。
- 全套：`0852ce2d8564d77bb381521b52a05bafceb30a814e18233a1c1d50dc6746f0e5`。

额外已执行检查：14个CLI `--help`成功；手册21条阶段命令经实际argparse解析，8个本地文档链接存在；新模板通过实际profile验证；真实调用register-data的CLI集成测试只用合成文件并阻止导入torch/libero/robosuite/mujoco/transformers。纯plan/help检查未导入实验模块；`git diff --check`通过。测试与静态证据在本工作树`reports/`，最终GitHub SHA及远端blob核对回执记录在项目根本地`reports/task008_x_delivery_20261015.json`。

## 候选命令与下一步

完整命令、输入/新out/日志/状态检查见[两域运行手册](../../docs/finish_two_domains_runbook.md)。包括文件plan/budget/register、用户audit、特征、CPU头训练、registry绑定normal准备、HDF32输入parity、5 init shadow校准、10 normal active、15 Remain active及可选shadow/K复算。实际服务器新路径和冻结SHA由Codex验收部署后补齐；本轮没有代填不存在的已部署目录。

X未启动真实sim、data restore、物理label/hold、VLA、feature、实验训练、parity或eval。HDF与eval祖源独立性仍未证明；真实类别覆盖、unknown、head效果和W150物理效果均待用户运行后审查。成功示范缺失败／停滞负例继续披露，数据不足不自动换组或补采。

下一步：Codex审查PR #5，验收后部署新目录并完成文件准备；用户先启动真实audit，确认数据充分才进入特征与训练。007/008及研究阶段都不由X自行closed；008 PR保持open，旧交流和原始结果不删除。
