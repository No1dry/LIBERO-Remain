# 当前协作状态

更新：2026-10-09（用户确认执行职责移交并推进实验）。代码：X；研究决策、代码审查、实验执行与结果审查：Codex。后续不再使用 DeepSeek。

## 当前大阶段

Stage03 / Plan3：外部部分完成后的主动观察/合理试探、剩余目标重判，主实验10/01/11，主表仅JSR↑/UIR↓。5组20状态/40回放通过；005验收及基本语义/物理/身份核对后执行固定15条探索性主pilot。初始遮挡不是停跑/筛状态理由，006非阻塞；最多10条oracle执行诊断另列，不强求对照成功才能测原模型。
Stage02的00能力实验验收完成：[总结](../docs/stage_summaries/stage_02_normal00_capability.md)。003代码accepted，PR #2仍待X合并并登记main SHA，不称已合并main；旧00实验冻结6e29f不再pull/重跑。

Stage01 closed：PR #1已合并，Codex已核验main与既有归档一致；最终关闭总结同步更新。

| 任务 | 执行者 | 状态 | 入口 | 交付/裁决 |
|---|---|---|---|---|
| 001 指标展示与人工 UIR | X | closed | [任务](tasks/001_metrics_and_uir.md) | PR #1已合并；功能验收完成 |
| 002 venv 解释器路径修复 | X | closed | [任务](tasks/002_venv_interpreter.md) | 同上；阶段总结/本地归档已核验 |
| 003 官方/Remain 00 回归入口 | X | accepted | [任务](tasks/003_normal00_regression_entry.md) | [PR #2](https://github.com/No1dry/LIBERO-Remain/pull/2)、[回应](responses/003_round1.md)、[Codex review](reviews/003_round1.md) |
| 004 layered环境有效版本记录 | X | open | [任务](tasks/004_effective_runtime_provenance.md) | P2元数据；不改当前冻结实验 |
| 005 显式subset pilot与隔离执行诊断 | X | open | [任务](tasks/005_subset_pilot_selection.md) | 仅CPU/fake；原指标不改；Codex审后执行 |
| 006 主动观察/合理试探诊断 | X | open | [任务](tasks/006_subset_observability_gate.md) | 非阻塞；原可观察性闸门撤销，不改场景使之理想 |

X独立意见已登记：[Stage02/03回应](responses/x_review_stage02_stage03_20261009.md)。赞同撤销单帧可见性停跑；建议收紧UIR目标/信息时点边界，并将技术故障暂停、实际策略step0 NPZ纳入005。此条仅交付意见，004/005尚未实现、任务状态不变；请Codex据此完善下一轮任务/验收。

Stage 01 main 合并 SHA：`fea75fc170b5c3047433316566dc52528c5caf2a`，见[合并登记](responses/stage01_merge_record.md)。
此前 Codex 独立 macOS 985 passed / 12 skipped、Linux 986 passed / 11 skipped，历史 OFT 数据只读派生与旧分数不变已核验。
X 按明确验收授权合并，未自行宣告阶段 closed。

任务 003 实现提交 `3a50f635b5eb7329386b381879ce53dab3bfbd46`。
X测试1092 passed/15 skipped；Codex独立macOS1095 passed/12 skipped、Linux1096 passed/11 skipped。
两个无模型的真实环境检查通过：official准确初态/10wait；Remain80settle/150audit/正式恢复逐位一致。
代码验收时没有新VLA分数；后续模型回归不冒充完整paired benchmark。

Stage01的[关闭总结](../docs/stage_summaries/stage_01_metrics_uir.md)与本地备份同步更新。
下一步Codex按[Plan3](../docs/experiment_plans/stage03_subset_pilot.md)执行准备与审查；X完成PR #2合并登记、004/005实现。任何新增实现必须独立审查，不在运行目录临时修补。
交接盘点见[交接记录](../docs/stage_summaries/handoff_2026-10-09.md)：已知服务器目录未发现正在运行的本阶段作业或新的正式00回归结果；此前只有旧smoke与无模型预检。运行进度以新 `execute_logs/stage02_normal00/` 和原始run记录为准。
用户随后指定新主机端口30369与 `/HUBU-AI096/zp/ICML`。实际是A100 80GB；初始空目录已建立冻结checkout和两套私有runtime，同一checkpoint的112个文件全部SHA-256校验通过，固定LIBERO1029个Git blobs与真实scene doctor通过。旧OFT tracked patch hash也一致。新机Python3.10.21，旧机3.10.20；simulation torch复用2.4.1+cu121而非旧CPU2.2.0，关键MuJoCo/robosuite版本保持并记录差异。
00正式5+5已于北京时间19:03:44完成，10/10、错误/缺失0，official5/5、Remain5/5；逐条复算/NPZ/视频解码通过。UIR未标注，不从成功率推断克制。旧4090未启动本批GPU作业。
Stage03状态准备完成，528.73秒/exit0：5组20状态构造及40次150-step回放全部通过，本地独立证据校验通过。冻结旧已审代码6e29f；完整archive、本地full_evidence、真实OFT准备RGB预览已保存。
最新[审查2](reviews/stage03_preflight_2.md)撤销[审查1](reviews/stage03_preflight_1.md)的可观察性停跑条件。保留当前001，允许看桌面、查篮子、合理空抓/非破坏试探及反馈调整；006仅诊断，不要求X把场景变容易。当前仍待005代码交付，尚未启动新VLA；不将mask真值喂给主模型。
新发现worker版本dict错误选择parent的shadowed distribution，已给X任务004。独立有效版本快照与episode.runtime确认实际加载版本正确；当前批原始记录不重写，报告此警告，不借修复换模型/协议。
既有四视频的人工UIR语义校准仍由Codex/用户负责。

## 已关闭阶段

- Stage 00：[首次真实 OpenVLA-OFT 接入 smoke 总结](../docs/stage_summaries/stage_00_oft_smoke.md)。
  关闭范围是接入与可复算 smoke；不表示完整 benchmark 验收或模型能力结论成立。

## 清理

001/002已closed，本轮仍保留交流供当前PR追踪；003仅accepted，不清理。README、STATUS与阶段总结长期保留。
每周检查；阶段完成时额外清理。只有阶段总结已推送、本地备份校验一致，才可删除已闭环交流。
