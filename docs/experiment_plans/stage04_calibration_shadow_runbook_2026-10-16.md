> 2026-10-16结果：本页5条shadow已由用户完整执行；既定离线校准尚未建立，selected_threshold=null。**不要重复本命令或直接进入active。** 当前进入[R10释放测量审计](../../collaboration/reviews/008_round10.md)，详见[结果总结](../stage_summaries/stage04_shadow_calibration_unestablished_2026-10-16.md)。下文仅历史。

# Stage04：5条普通任务shadow停止校准采集

2026-10-16。15个官方初态来源及纯文件08_shadow_plan均已accepted；实际实验仍由用户亲自启动，Codex未创建sim／运行VLA。前序audit／features／head训练／parity／normal-bank均完成，不重跑。

## 在服务器执行本次唯一真实命令

```bash
bash
source /HUBU-AI096/zp/ICML/stage04_finish_3433f48/session.sh
finish_sim 09_calibration_shadow run \
  --config "$CFG/validation_shadow.json" \
  --out "$OUT/validation_shadow"
```

session使用冻结3433f487d38efe0a08e4c814e87412aad5aba9fe；runtime、head、原模型及crop／seed不变，stage_log核262源码／11部署文件并保存完整命令、UTC与exit状态。输出和日志禁止覆盖，失败／中断保留partial，不自动重试。

## 本次做什么

只选official init35、36、37、38、39，共5条正常00，来源角色为normal_calibration；40..49独立normal_test不参与本次，Remain0..4也不参与。bank保存路径含旧2cb只是既定数据位置，实际执行3433源码、新head6636f713…、新3433结果根。

mode=shadow：照常执行原动作，记录FINISH概率／候选动作／GT证据，但**不按FINISH停车**。运行时0.5只是记录用placeholder，不能把它当最终阈值；模型完成后继续动作在此阶段是预期采集设计，不代表忘记接头。GT不路由、不许可停车，不因任务成功早停。结果的主合规FINISH成功指标为N/A，不写成0%。

H520、W150、chunk8、t0和H边界query；每条完整670个物理step、最多66次预测；5条最坏3350物理步、330次模型预测。保存双相机20fps／stride1视频、动作／输入与step ledger。技术错误暂停后续，固定5条分母和missing保留，不替换来源、不自动续跑。

## 身份与文件准备已完成

- 15/15来源prepared，35..49，state／观测／原官方init SHA／BDDL／registry与各150步技术审计均已只读核验。
- 纯文件plan：/HUBU-AI096/zp/ICML/stage04_finish_3433f48/results/run01/validation_shadow_plan/plan.json，语义SHA0c49836a7d5e5c82958362b441c10d44bc5fafaa5d8024de211909daaba4f4b6。
- head artifact：6636f7133943d551df31a14822df440b63c1b98c0b3ee95f4873019492512c7f。
- runtime文件SHA：75f2a711a39c58a07715b3a280aeba26a29dfbba70caf87cc051520f0a3f9720。
- cfg：/HUBU-AI096/zp/ICML/stage04_finish_3433f48/configs/validation_shadow.json。
- 新输出：/HUBU-AI096/zp/ICML/stage04_finish_3433f48/results/run01/validation_shadow。
- 新日志：/HUBU-AI096/zp/ICML/stage04_finish_3433f48/logs/run01/09_calibration_shadow.log。

## 完成后

用户报告完成后，Codex核验5条完整记录／identity／输入／ledger／视频／unknown和技术错误，再用既定只读校准规则选并冻结阈值（normal_calibration数据，不能借normal_test或Remain调阈值）。若没有满足约定的及时停止候选则capability_not_established，不能为通过换split、调模型或挑低成功率。

阈值冻结后才交用户10条normal active独立停止能力测试，最后15条Remain主实验。这5条采集结束不自动等于stop-capable。跨域物理祖源／模型曝光未证明、demo_38仅两正例等pilot限制保留。

[来源与计划验收总结](../stage_summaries/stage04_normal_bank_pass_2026-10-16.md)。008／Stage04未closed，不自动合并代码或删除原始数据，精确待删=[]。
