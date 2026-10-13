# Stage04 软件验收与部署阶段记录

2026-10-13，Codex。这里只完成软件审查与部署，不是Stage04科学结论完结，不宣称stop能力已建立。

## 目标与裁决

用户的研究问题仍是：外部过程提前完成任意部分任务后，VLA能否重新确定剩余目标、保留已完成成果并完成余下任务。新增FINISH接口使结束点可评估，控制“原模型未学停止”的混淆；不是为了把原模型分数做低，也不把后验GT停车当学会停止。

task007 / PR #4的已审head为`38e6a449d4e769b842e10c5b393fc2b26a5cfa2b`，X实现`55474fd`；两者仅交付/STATUS文档不同。Codex裁决accepted（软件），没有阻塞项、无需本轮返修。X按既有协议可合并已审实现并记录；Codex不自动合并，Stage04/007不标closed。

## 独立证据

- macOS新增237 passed；全套1468 passed/12 skipped，1480项；Linux新237 passed。全部CPU/fake，不加载真实VLA，不创建真实仿真，不进行实际数据训练。
- 194个源码文件逐GitHub blob与SHA-256核验；上传后194源码+10冻结部署文件一致；服务器CLI帮助与日志包装器通过；完整runbook 25条CLI参数解析通过。
- 证据位置、JUnit hashes、逐模块结论见[007首轮审查](../../collaboration/reviews/007_round1.md)。软件正确性不等同真实物理接口、标签、GPU parity和stop能力已经通过。

## 部署身份

源码快照：`/HUBU-AI096/zp/ICML/LIBERO-Remain-stage04-finish-38e6a44`；资产/配置/命令根：`/HUBU-AI096/zp/ICML/stage04_finish_38e6a44`。无`.git`，source_inventory标记GitHub commit和逐文件证据。

| 产物 | SHA-256 |
|---|---|
| 固定GitHub源码归档source.tar.gz | `7d80e387a74ea66b5f3709f3830a37e6270048b726a7226f466413c68ac09928` |
| 私有部署归档deployment.tar.gz | `10036c4fbfb9947cac6cd0db63b3e8ca0076fd5b8b144fdc2d64235da953f33c` |
| source_inventory.json | `e68b5009b33b1d34e7c22cc25a564724ccef81bb9b1b2dadc26191340d4ef669` |
| configuration_manifest.json | `ef4b130bf0c503c219687bad96670b12e0a9f12191a87e1419351cf0eb679a8c` |
| 同一oft_sog10.json | `75f2a711a39c58a07715b3a280aeba26a29dfbba70caf87cc051520f0a3f9720` |

运行环境保持旧stage02两个venv；sim Python3.10.21，NumPy1.26.4/robosuite1.4.0/MuJoCo2.3.7；worker Python3.10.21，NumPy1.24.4/Torch2.4.1+cu121/Transformers4.40.1。服务器只读查询为A10080GB。OFT仍e4287e9及既有local patch、SOG10仍原snapshot；不升级依赖或替换模型。旧stage02/stage03源码、raw、视频、manifest、replay不修改。

## 尚未完成和边界

没有真实预检、数据restore、标签audit、feature forward、真实数据头训练、32输入parity、校准或新eval。默认30rollout预算尚未消耗。

现有basket init/BDDL/source001/replay与权重路径已确认；旧datasets目录空，核对范围未找到对应官方HDF5。给用户固定revision/单文件hash下载命令，不代下载。真实source对应若不足必须保留insufficient，不以demo编号或虚构manual confirmation填满split。

软件advisory：base/head身份未完整绑定center_crop等runtime配置；本次以冻结同一JSON和每命令前SHA校验防护，无需为偏好返修。保守release可能导致unknown；报告固定分母确认成功率与覆盖，不能把未知写成确定失败。主项不证明无一切冗余，也不证明理解剩余目标。普通00独立stop能力仍待用户active检验，不能凭shadow候选阈值宣称成立。

## 下一阶段与角色

详细[服务器命令](../experiment_plans/stage04_server_runbook_2026-10-13.md)：用户先11环境预检，再补HDF5和来源audit；交回报告后Codex审查，才决定特征/训练/parity及5val+10normal+15Remain。可选15shadow独立决定，不自动运行。

用户启动、运行、监督所有真实阶段；Codex详细需求、建议式审查、部署和命令、结果审查；X改代码，仅明确错误阻塞或返修，原DeepSeek退出的历史证据仍保留。

本次交流保留清单：`collaboration/tasks/007_finish_protocol_and_stop_calibration.md`、`responses/007_scope_review_20261013.md`、`responses/007_round1.md`、`reviews/007_scope_response_20261013.md`、`reviews/007_round1.md`。007accepted但未closed，PR未合并、真实阶段未闭环；**精确待删清单为空，不删除任何交流、源代码或原始实验数据**。

本总结提交GitHub后按协议备份到本地`research_archive/LIBERO-Remain/stage_summaries/`并核来源commit与SHA；备份不是宣称大研究阶段已完成。
