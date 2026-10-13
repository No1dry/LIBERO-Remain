# Stage03执行总结：外部完成子集的15条主pilot与10条诊断

日期：2026-10-10。执行/审查：Codex；代码实现：X。状态：本轮有界GPU执行与完整性核验完成，UIR视频语义审核待完成；不是Stage03科学完结或benchmark发布。
冻结源码 `04508dc0b0c48bf10e33c69ed3d3e830df793aaf`，PR #3代码accepted；实验不随分支或main移动。独立macOS1231 passed/12 skipped、Linux1243 passed；详见[验收](../../collaboration/reviews/005_round1.md)。

## 身份与范围

A100 80GB；同一SOG10 OFT、snapshot638918f3，原checkpoint迁移112文件一致。policy seed7、chunk8、原camera/center_crop/解码；simulation robsuite1.4.0/MuJoCo2.3.7，model numpy1.24.4/robsuite1.4.1/MuJoCo2.3.7、torch2.4.1+cu121。
同一basket任务、官方来源0..4、原001状态：manifest SHA50c557f0…8797d、replay SHAee4902bf…5ef46。20状态/40回放技术通过；保留初始遮挡作为允许主动观察/试探的挑战，不重摆或改crop，不因成败筛来源。
主15条只10/01/11各5，原完整指令、无mask/剩余提示/专家动作；诊断10条只10/01各5，仅policy调用边界用唯一剩余goal语言，不改源episode或完整目标评分。两批分开记录、一次load各15/10次reset。

## 执行与核验

主批北京时间00:14:42–00:25:22，639.72秒/exit0；诊断00:49:50–01:00:15，625.02秒/exit0。分别15/15、10/10完整，invalid/runtime/missing均0，stop_reason=null；00未选、不新增00模型episode。
独立read_run校验源快照、选择/模式/指令/实际reset step0 NPZ、真实query与动作区间/trace绑定；25条metrics从原trace重算一致，25段MP4实际解码均匹配n_steps+1。
没有额外render/step/predict，success=False不停止/换样本；主模型不由GT提前停车。UIR不自动从闭爪/无效抓取或没STOP赋值，当前N/A。

| mask | 主原指令JSR | 隔离剩余指令JSR | 主UIR |
|---|---|---|---|
| 10 | 2/5 | 2/5 | 未审核=N/A |
| 01 | 5/5 | 5/5 | 未审核=N/A |
| 11 | 5/5 | 不运行 | 未审核=N/A |

| 来源 | 主10首次全部达成步 | 诊断10首次全部达成步 | 两批预算内JSR |
|---|---:|---:|---|
| 0 | 266 | 265 | 都成功 |
| 1 | 无 | 无 | 都失败 |
| 2 | 663 | 无 | 都失败；主663已超过H520 |
| 3 | 368 | 262 | 都成功 |
| 4 | 无 | 无 | 都失败 |

两批25条初始成果preservation均true；这些10失败不是已经观察到的初始成果破坏。source2主轨迹最终达成但超预算，不说它整个窗口永远无法完成。
oracle告知剩余目标没有改变这批10的预算内成功来源集合；source3完成更早也不等于整体改善。oracle成功是执行正证据，失败仅未证实，不作物理不可达、性能上界或内部因果断言。

## 科学判断与禁止主张

可报告：本任务固定5个来源下，10的预算内成功/稳定明显低于01，存在外部完成子集改变后的执行敏感性；不是每个10都失败。每mask只有5个来源，同源配对不是15/25个独立样本，不作泛化/显著性结论。
不能直接宣称：失败全部因为没意识到已完成/不知道剩余目标；把完成goal从指令删除就能修好；oracle失败证明任务物理不可能；01/11的JSR100%证明会停止或没有无必要操作。
当前结果不支持直接锁定“单帧满足判别器＋路由”作为必然解决方案。先看失败/成功视频及实际query信息，区分合理试探、已满足目标重做、未完成目标执行失败、空间恢复/反馈或记忆因素。必要观察/试抓允许，目标/必要性不明确unknown；不增加主metric。

## 原始产物、备份和下一步

服务器冻结checkout `/HUBU-AI096/zp/ICML/LIBERO-Remain-stage03-pilot-04508dc`：reports/stage03_primary_001、stage03_oracle_001；execute_logs/stage03_partial有命令/PID/起止/退出码。
完整证据archive SHA-256 `e9e7391786e0099e065c3d0631d646d9d48eb3db3db6739357acf83902ca4dd7`，服务器/本地一致。本地完整解包 `reports/stage03_pr3_review_2026-10-10/full_evidence/`，含两批源/plan/config/trace/实际观测/evidence/25视频/日志。旧源码和001状态不改。
关键summary SHA：主d796181ab0d76ed9a7802d2368adebacef08768f89f5341dd3dce3109777838c；诊断e8eb4af840e1a1f1f54640d6a90011f52e3c99c7226ede98083e25f719a9e2b3。
本总结发布后复制至本地research_archive/LIBERO-Remain/stage_summaries并登记来源commit/SHA，一致后才可能清理已闭环交流；本轮不删除004/005/006/原始资产，不把UIR待审阶段closed。

下一步操作：Codex逐段核对10失败源1/2/4与成功源0/3、01/11代表录像，按实际crop/query机会和已满足目标/操作必要性审UIR，争议请用户共同确认；保留未知，不新增GPU/训练/任务/模型。X按accepted授权合并PR #3并登记，无新增未审源码；实验仍冻结04508dc。
