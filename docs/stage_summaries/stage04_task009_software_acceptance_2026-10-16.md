# Stage04：009最小释放诊断软件验收、部署与计划完成

2026-10-16。[009 Round1裁决](../../collaboration/reviews/009_round1.md)：软件／纯文件计划accepted，真实native诊断尚未由用户启动，Stage04未closed。用户已确认仅35号最多292条原动作，原FINISH释放／校准／指标不改。

## 交付与独立证据

PR #6冻结final2c6dc4c20a12b4b894a3919d79b9bf810648332d，tested5410355436ef0f418f0c95c47293efbdce905b07；最终仅回复／STATUS不同。PR #5已由X合并3d361f44a9393638d41738d375004e8ea7794301，已审生产仍等价实际3433f48；原验收保留而非科研closed。

只新增3个独立诊断模块、3测试文件和手册；原environment／runner／release／calibration／训练／adapter／数据／指标不变。本地全套1988 passed／12环境skip；服务器新诊断155 passed／0skip；两路独立复核92/63 passed，无明确阻塞，不要求偏好返修。所有均CPU/fake／文件，没有真实native/model/head调用。

293个源码文件逐Git blob+SHA、4冻结部署文件核验。已上传新源码/HUBU-AI096/zp/ICML/LIBERO-Remain-stage04-release-2c6dc4c，运行根/HUBU-AI096/zp/ICML/stage04_release_audit_2c6dc4c，复用旧SIM_PY和LIBERO runtime；实际依赖源码路径已只读核对，未升级包。用旧已生成XML dad2437d…核89引用／87资产通过纯文件解析，不声称本轮native编译认证。

## 文件计划已由Codex完成

01_plan status=plan_ready、exit0/tee0。验证原全部shadow ledger/input/video与bank，冻结1072源文件；292×7原float64动作数组逐bit一致，初态仍原已settle bank，最大293快照、37原query边界0..288。step292不是query，不执行293／FINISH／hold／W150／init37。计划hash8bfc498562ef72c0432fa39aed0055ef1328e388f88af08cc27cddeaaec2ea3d，文件SHAa99b5630c7f76a6860719600ff0f4326d7960ca1fe551df27ecc5fc173f626a4；原动作数组SHA33dee7b84fa13cdf374aaacfbd4298ef884936eae9ef9848ee6d2ff0844256b7。

[机器验收证据](evidence/stage04_task009_acceptance_2026-10-16.json)含源码／bundle／JUnit／plan／输入和文件SHA。本地reports/stage04_task009_review_2026-10-16保存Git tree/source inventory／私有配置、全套JUnit及下载的plan/actions/manifest、服务器CPU日志和纯文件资产检查，相关SHA与服务器一致；旧330输入／视频原树仍留服务器，未声称本轮全量本地复制。

## 用户下一步

[完整唯一run命令](../experiment_plans/stage04_task009_server_runbook_2026-10-16.md)已补齐路径，服务器RUNBOOK.md同步；source只定义函数，不执行。用户启动release_diag 02_run run，Codex未代跑，也不另让用户再做plan或依赖准备。

这是真实native动作重执行但无VLA/head/processor调用，不是benchmark新成功率。首次原obs/truth/action差异即停止，保存侧录和首差异；technical_error与interrupted另报，不开爪／step修复，不自动重试或加预算。即使全部匹配，也只证明这次可观测前缀一致，不能宣称恢复原完整隐状态、unknown物理上已释放、或FINISH停止能力已建立。

执行后Codex只读查看summary／frames／native typed sidecar，作研究决策；不自动改release协议／标签／阈值。当前原calibrated=false／selected_threshold=null、normal_active/Remain未启动。009 PR仍open/unmerged，Codex不代merge；原数据/失败partial/脏工作区及交流不删除。任务009软件accepted不等于closed；007/008/009/Stage04科研未闭环，精确待删=[]。总结／裁决／命令／证据／STATUS及X回复按README提交并本地来源commit+SHA备份。
