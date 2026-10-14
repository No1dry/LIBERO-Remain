# 007 首轮软件审查与部署裁决

2026-10-13，Codex。裁决：**accepted（软件范围），无需本轮返修**。PR #4尚未由Codex合并；Stage04真实实验与科研结论未closed。所有真实阶段由用户启动、运行和监督。

## 冻结交付与独立测试

- PR：<https://github.com/No1dry/LIBERO-Remain/pull/4>；已审head=`38e6a449d4e769b842e10c5b393fc2b26a5cfa2b`，Git tree=`d6e96c7a9484fc5e6dfba72908455734ebb89a3e`。
- X测试实现=`55474fddc934ad8b4e257b64dd21a41921242af4`。GitHub compare确认最终head仅增加`collaboration/STATUS.md`与`collaboration/responses/007_round1.md`；benchmark/scripts/tests/configs未变。
- 下载固定源码到独立临时目录；194个文件逐一核对GitHub blob SHA。没有pull/reset已有dirty checkout。
- Codex macOS／Python3.12.7：新增10个FINISH测试文件**237 passed，7.68秒**；全套**1468 passed / 12 skipped，30.66秒**。跳过11项未安装的固定LIBERO BDDL文件核查与1项缺imageio_ffmpeg编码测试，不是悄悄跳过失败。全套1480项。
- 部署服务器／sim Python3.10.21：同10文件**237 passed，23.41秒**。全部CPU/fake/tiny合成数据，不是真实物理保持、CUDA动作parity、VLA能力或实际数据训练。
- 服务器专用runbook中25条CLI命令仅做parser参数检查通过；部署后的`--help`和日志包装器实际通过。没有把parser通过写成实验已执行。

本地JUnit目录：`/Users/zhangpeng/Desktop/Learning_Not_to_Act /reports/stage04_pr4_review_2026-10-13/tests/`。

| 证据 | SHA-256 |
|---|---|
| finish-review-junit.xml | `828c480aa2a22c34338da9fa44af1933dface20a29dd1513b69d89638a471013` |
| full-review-junit.xml | `9b496173e670ce92a29fd0032b287667334afe2407f22c058b66707aa66e656a` |
| server-fake-tests.xml | `2c79712b113a9314f8521f496325385a987e2bd9215f367aa28803369702e293` |

## 审查结论

没有发现满足README阻塞标准的明确实现错误。以下已落实约定而非新增要求：

1. `finish/runner.py`：t0与H都查询，active FINISH在H优先，shadow只记录不退出；候选chunk按剩余预算截断；FINISH与TIMEOUT均真实W150保持且不再predict；GT不门控模型退出。
2. `finish/environment.py`：锁定退出当前末端姿态，逆OSC缩放纠偏，Panda增量gripper输入0保留原目标；不假定0action开爪、不GT补救。release结合双pad grasp、所有gripper接触与保守手／指间几何距离；不把无夹持直接视作释放。
3. `finish/metrics.py`／evidence／schema：固定预定分母、unknown/technical/missing单列；FINISH当下全部目标+释放、已有成果全程保留、退出后目标保持；初始篮外非目标稳定投放事件粘滞；不让早停被后续hold完成抵消。actual输入张量、原processor两路crop、动作／hold账本及录像字节身份可离线核查。
4. `finish/oft.py`／model：严格捕获原L1实际(B,56,D)输入并FP32 meanpool/detach，一次原forward，排除EOS/prompt/patch；冻结动作模块；parity在同一worker恢复Python/NumPy/Torch/CUDA RNG。
5. data／training／calibration：不猜demo编号；整组source/trajectory/repeated state隔离；监督来自当前状态+独立被动hold，unknown不造label；cache复验；pos_weight仅train；val BCE选择头；校准只取首次越阈、及时FINISH全0不伪称通过。
6. workflow／CLI：独立显式命令、新目录拒绝覆盖、技术错暂停保留partial/missing、策略失败继续；无自动resume／background／真实阶段串行启动。13种子命令已实现。

## 非阻塞建议与解释边界

- 当前`oft.base_identity`未记录center_crop等完整runtime配置，head identity也没有直接继承feature_export的runtime hash。换runtime文件可能仍通过base/head/calibration身份但改变输入。**本轮通过部署冻结同一runtime文件及每命令前独立SHA校验防护，不要求X返修**。以后若要自由跨配置复用head，可另行完善这项绑定。
- 保守release几何可能产生较多unknown；用户先看真实preflight与coverage，不把unknown写成确定策略失败。主表确认成功/预定N在未知存在时是确认成功下界。
- FINISH主项只覆盖明确契约违规和结束判定，不证明完全无语义冗余；普通00独立active能力不足也不自动要求X改代码。
- `calibration.json`成功时实际status为`candidate_threshold_frozen`且calibrated=true；服务器runbook按实际值检查，避免把叙述“calibrated”当成status字符串。
- 官方演示HDF5是否有足够初态对应、实际正负标签与32个独立validation输入尚未验证。数据不足按insufficient保存，是实验前置条件，不允许虚构采集溯源或改test分组救通过。

## 实际部署和用户下一步

已上传冻结源码到`/HUBU-AI096/zp/ICML/LIBERO-Remain-stage04-finish-38e6a44`；运行资产根`/HUBU-AI096/zp/ICML/stage04_finish_38e6a44`。194个源码文件、10个冻结部署文件上传后核验一致，旧目录／模型／patch／raw全保留。源码快照无`.git`，用source_inventory核验，不冒充git clone。

模型解释器、sim解释器、LIBERO init/BDDL、现有basket source001/replay、官方SOG10 checkpoint与OFT代码路径已只读确认。旧项目datasets目录为空，未找到该basket HDF5；用户按[部署runbook](../../docs/experiment_plans/stage04_server_runbook_2026-10-13.md)自行下载单文件并核SHA，再做来源／标签audit。先行11物理preflight不依赖HDF5。

完整分阶段命令含预检、下载／audit、feature、train、normal准备、parity、validation、calibration、normal active、Remain active、可选shadow和K敏感性重评分；没有启动其中任何真实阶段。默认30rollout预算未消耗。

X无需为了审查意见追加纯意见轮次；按既有协作授权可在保留此已审实现的前提下合并PR并记录merge SHA，勿为效果或偏好改协议。若合并包含实现变动，必须另列diff，不能自称同版已审。Codex本次不合并实现。007状态accepted而非closed，交流全部保留，Stage04待用户真实证据。

下一步操作：用户运行11预检、补齐HDF5与audit，交回preflight.json／audit.json和日志；Codex审查再决定进入真实特征／训练。执行者：用户，随后Codex审查。
