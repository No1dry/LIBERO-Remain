# 00官方成功口径与四个迁移任务（2026-11-02补充）

用户已同意：00能力对照以官方任务成功信号作为主SR；不稳定掉桌检测退出主判分、保留诊断。此前2026-11-02阶段文档的43.75%属于自定义合规率，不应当成官方00 SR；旧数据/文档作为历史保留，以本补充明确主口径。032实现尚待X交付，不宣称已更换源码或新评分报告已执行。

已有轨迹official_goals_achieved=52/80，即65.00%；六个LIBERO-10主轨52/60=86.67%，已评两LIBERO-90迁移任务0/20。goal_values在原执行中逐次验证all-goal与env.check_success一致。此处是既有轨迹按官方任务成功信号统计，不声称完整复现官方初始化/运行协议。

旧合规35/80=43.75%、UNKNOWN16/80=20.00%保留作诊断，不能把UNKNOWN直接算模型失败或为了提高SR当成成功。table_drop在00和10各30/80存在UNKNOWN，集中于stove/frypan_stove3/cabinet_close_bottom_open_top，各10/10；两批均无confirmed table_drop，说明本批尚无其正例识别能力证据。

| 官方suite | 任务key | 官方任务全名 | 00状态 | 10状态 |
|---|---|---|---|---|
| libero_90 | frypan_stove3 | KITCHEN_SCENE3_turn_on_the_stove_and_put_the_frying_pan_on_it | 10条完成，官方目标达成0% | 10条完成，旧合规0% |
| libero_90 | cabinet_close_bottom_open_top | KITCHEN_SCENE4_close_the_bottom_drawer_of_the_cabinet_and_open_the_top_drawer | 10条完成，官方目标达成0% | 10条完成，旧合规0% |
| libero_90 | frypan_stove9 | KITCHEN_SCENE9_turn_on_the_stove_and_put_the_frying_pan_on_it | 未评，缺来源4 | 未评，本任务已有9/10候选，仍缺来源4候选及10条独立回放证据 |
| libero_90 | cabinet_close_top_bowl | KITCHEN_SCENE10_close_the_top_drawer_of_the_cabinet_and_put_the_black_bowl_on_top_of_it | 未评，缺来源5 | 未评，本任务已有9/10候选，仍缺来源5候选及10条独立回放证据 |

四项来自同一官方LIBERO-90 suite，并非四种不同的90子集。当前使用官方SOG10 OFT checkpoint，不是为本轮切换了LIBERO-90专用权重，因此按迁移扩展单列，不能说它们没评或因0%删掉。00本来就失败时，10失败不能单独归因于剩余目标重定向。

031 R2源码已软件accepted并另目录部署；两缺任务00已有18/20来源可复用（90%），10已有18/20候选构造（90%），但20条独立回放证据仍缺。2026-11-02本轮服务器只读检查：约定的两个preparation_report与两条prepare日志均不存在，未收到真实补建产物。不能把软件修复/文件部署完成称作两项物理故障已解决。旧故障分别涉及场景9来源4的腕图一致性与场景10来源5的速度审计，原失败保留。

下一步：X实现032离线报表与评分降级；用户可独立启动已给031补建命令，不等待032；Codex读取实际来源证据后给补20条00/20条10命令。已有80条00/80条10不重跑，没有新训练或模型作业。031/032均未科研closed，精确待删=[]。
