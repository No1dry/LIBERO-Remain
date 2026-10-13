# 2026-10-12交接总结：用户运行实验，统一FINISH协议进入代码准备

日期：2026-10-12。作者：Codex。类型：责任变更与研究决策长期归档，不是Stage04完成总结。

## 用户确认

用户认可推进统一FINISH协议／普通停止校准的下一步，并明确：所有实验由用户启动、运行、监督；X继续改代码；Codex负责详细需求、审查建议、验收后上传服务器及完整运行命令。除明确错误外尽量不返修，代码需求提前完整描述。

本轮协作README和STATUS已按此分工更新；旧DeepSeek退出状态保持，历史署名、原始证据及以前Codex执行记录不改。

## 研究方向

FINISH首先是benchmark结束接口，不是为提升基线分数救失败。正式主基线为原动作网络加停止校准；原始无FINISH模型只作历史动作／旧JSR参考，不能因不支持新符号赋0%来证明剩余目标能力差。

默认只训练小finish head，原OFT模型、LoRA、action head和projectors冻结。同一次forward读取原action-token hidden，不插入token或改输入。普通00训练／validation／独立能力测试按source整组划分，当前Remain0..4及所有edited variants仅测试。普通停止能力未建立则如实报告，不把低效果自动归咎代码或强行扩大训练。

新finish-v1独立入口：全部mask H520，退出后W150真实物理，t0及H的query边界允许FINISH；active与shadow分开，timeout不冒充FINISH，GT不许可／否决策略停车。保持控制不依据目标真值救分。

自动主项为合规FINISH成功率，结束延迟和失败原因作诊断。错对象投放和初始成果破坏不能由后来FINISH擦除；合理观察、试抓与安全收尾不直接判错。释放／稳定检测、hold和数据来源的真实正确性由用户运行预检验证，CPU fake不冒充科研证据。

完整规格见[Plan4](../experiment_plans/stage04_finish_protocol.md)与[任务007](../../collaboration/tasks/007_finish_protocol_and_stop_calibration.md)。

## 已有状态与禁止主张

PR #3代码已accepted，HEAD4b5145173b979f268625bf154800f14df7194d14仍open；实验代码冻结04508dc。X沿用既有授权处理合并登记；Codex不自动合并。007另开实现分支，不混入PR #3。

Stage03主15条＋隔离诊断10条已完整执行，历史主JSR10=40%（2/5）、01=100%（5/5）、11=100%（5/5），UIR=N/A；这些不是新FINISH协议成绩。当前10的60%（3/5）在H内未完成，完成后停车不会替其完成剩余目标。旧结果／状态／checkpoint不改，Stage03科学审查仍开放。

新11决策预算与旧协议不同，不能直接混表。00正常停止证明基础能力，不证明外部预完成的停止泛化；实验可以反驳原假设，不能为压低基线筛来源或调规则。

## 本轮交付与责任

- docs/experiment_plans/stage04_finish_protocol.md：协议、数据、校准、预算与用户执行顺序。
- collaboration/tasks/007_finish_protocol_and_stop_calibration.md：完整实现需求、CPU/fake负面测试、实际命令交付要求。
- collaboration/README.md：新责任、非阻塞建议为主的审查与命令规范。
- collaboration/STATUS.md：当前任务、PR和阶段状态。
- 本文件：长期保存职责与关键决定，发布来源commit／实际SHA登记在本地backup_manifest中，不虚构自引用commit。
- 每周归档自动化同步用户执行实验的新分工，保持原周期与清理范围；不自动部署、启动或监督实验。

截至本次交付，未修改benchmark实现，未登录服务器部署未交付代码，未启动真实仿真／特征抽取／训练／eval，未生成新成绩。当前只发布需求。实际运行命令待X代码交付、软件审查及冻结部署后补齐，不用未实现CLI或占位符伪装成完整命令。

## 审查、归档和清理

审查只对明确错误／关键合同缺失／泄漏／危险控制／证据失配要求修正；合理替代设计和非关键优化作为建议。科研能力检查未通过不等同代码错误，用户决定下一次实验。

本总结发布后本地备份并校验来源commit、GitHub blob与SHA-256。任务001/002虽closed仍供后续追踪；003/004/005/006非closed或关联未合并PR，007开放。本轮无精确待删清单，不删除任何交流、源码或原始数据。

下一步操作：X实现007并交PR；Codex建议式审查、验收后上传服务器和完整命令；用户启动、运行、监督实验并提交日志。
