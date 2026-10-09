# Codex Stage03 前置审查1

日期：2026-10-09。裁决：技术准备通过，观测/语义与剩余执行证据待补；尚未启动新VLA批。源bank仍legal=false，不宣告可发布。

## 已核实

准备冻结benchmark6e29f110，服务器原状态/旧00结果未改。basket固定来源0..4，5组完整四mask共20状态；每来源第一个joint候选通过，未按policy表现挑选。
构造、独立回放、预览均exit0；耗时528.73秒；无policy/权重加载。40条episode×repeat全部通过150-step回放。
完整证据archive SHA-256 `3f59cc6a2dea4804500a1c9418c33b7c9362be5ab14a31c24ad4e0e89daab5ad`，服务器与本地一致；本地 `_candidate_pack` 和 `validate_replay_evidence` 独立校验5组/20状态/40记录全部通过。
源manifest SHA-256 `50c557f087783d7aa346992f4449dc81c1c59302e8850b3a3bee1c820c18797d`，content hash `c3f15ec71bb1a663e6db048ca145c96e7f33e752afa975b502d215fb03213cbb`。

## 未通过的前置证据，不是policy失败

1. 现有评测不能只选10/01/11，任务005补selection/准确分母/隔离oracle诊断，代码需验收。
2. 查看20个主相机起点及初态0的双相机/真实OFT准备RGB，发现篮中完成物体的可辨认证据弱，且crop保留的区域有限；不能因mask=true就认证可观察性。任务006先诊断/方案，允许提供合理非破坏主动观察证据；不是已证明不可观察。
3. 几何终态/稳定回放未证明机器人能完成剩余任务，005隔离oracle诊断/其他独立正例仍待实际验证。失败只能未证实，不等同物理不可达；不筛来源。

操作说明：首次目录SCP备份因大量文件超过60秒，改用单archive完成并核验；本地full_evidence为可信完整副本，早期部分mirror不作证据。首次RGB helper遗漏wrist=True而失败；改为与真实adapter相同调用后002的20个RGB预览完成。都是操作过程问题，不是X评分/策略错误。

## 当前记录和下一步

服务器：冻结checkout下data/stage03_basket_candidates_001、reports/stage03_basket_replay_001、reports/stage03_model_input_preview_002；execute_logs/stage03_partial/preparation_001.json。
本地：reports/stage03_partial_2026-10-09/full_evidence/与stage03_model_input_preview_002/，overview仅作审查图，不是可见性自动认证。
Plan3本轮主VLA执行前保持闸门；等待X005、006交付，Codex分别审查后执行相同固定来源。原00能力前提已完成，不重跑00模型、不训练、不扩样本或任务。主指标仍JSR/UIR，UIR无标注=N/A。
