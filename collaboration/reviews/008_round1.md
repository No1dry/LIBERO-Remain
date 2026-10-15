# Codex审查：008 Round 1

日期：2026-10-15。裁决：**accepted（软件范围），无阻塞返修；任务与Stage04未closed。**

审查[PR #5](https://github.com/No1dry/LIBERO-Remain/pull/5)，独立base `94c061e99168d76fbe50bef85b187db8fe2b9898`，已测试实现 `b973133a08216eaab4a36901b1b968c4d8b87452`，冻结交付 `b596af26e167450beb7f3c7fe61b6dfd53523ef6`。测试实现到交付只有STATUS和008回复两份文档。220个源码文件逐个核对GitHub Git blob及本地SHA-256；未操作用户已有脏checkout。

## 结论与需求核对

1. 固定HDF轨迹域30/5/15与official init域5/10/5，键使用实际文件SHA加实际group/index；不按相同数字制造demo→init映射，祖源独立性保持unproven。
2. registry是纯文件证据，不能ready。真实audit仅恢复head_train/head_validation，先保存当前合法输入再做同状态K4保持；unknown不偷变标签。完整采样、原文件SHA、state/XML、跨head组直接state/raw重复、类别/工作计数与物理label均重新核验。
3. audit→cache→head继承v2来源/label/base/code/input/feature身份，旧合同不混入；梯度和pos_weight只用head_train，普通BCE与32不同parity输入只用HDF head_validation。
4. 阈值只用official-init normal_calibration 35..39；active重新核head/profile/registry/校准域、角色及完整成员。normal_test 40..49、Remain 0..4×10/01/11不参与拟合或选择。新normal-bank核原始init文件和原始state；旧source001不被补造采集provenance。
5. 与已验收4f76f49逐Git blob核对，environment.py、runner.py、schema.py、metrics.py、evidence.py、oft.py全部未变。两robot许可、hold/release、H520/W150/chunk8、GT不控制停车、同forward特征与动作、评分算法均不因008改变。
6. 两域手册21条候选命令均能通过实际CLI参数解析，无缺失flag。保留独立阶段、new-out/no-overwrite、partial与关闭资源；不自动接着训练或评测。

没有为了命名、代码风格或未经验证的效果追加返修。未发现本任务范围内的明确错域、泄漏、危险控制、证据错误或关键消费者漏迁移。

## 独立软件证据

| 检查 | Codex实际结果 |
|---|---|
| 本地全部15个FINISH CPU/fake文件 | 393 passed / 0 skipped，25.75秒 |
| 本地全套 | 1624 passed / 12 skipped，49.11秒，共1636项 |
| 并行独立数据审查 | 83 passed，6.70秒，tiny HDF/fake provider |
| 并行独立消费者审查 | 166 passed，19.57秒，CPU fake；21条手册命令只解析参数 |

本地12个skip：11个缺可选固定模拟器源码的catalog检查、1个缺imageio_ffmpeg；与X在Windows报告的15个既有平台/可选skip不矛盾。无新的008 skip。

本地JUnit：

- `reports/stage04_pr5_review_2026-10-15/cpu_finish.xml`，SHA `c306d7f40ee1c4cd726536a9ee8081f499ef6262f951ea3c0cce639f2caa33ff`。
- `reports/stage04_pr5_review_2026-10-15/cpu_full.xml`，SHA `642d873885ea57cc832db7ace3c7544b2a711ea41c622e755771dbf0506bbce1`。

## 验收边界与后续

软件接受不证明真实标签两类充分、unknown可接受、head学会停止、W150通过或HDF与eval物理祖源独立。成功示范缺失败/停滞负例继续披露；不为降低原始模型分数选择组或阈值。没有启动真实sim/状态恢复/物理标签/VLA/特征/训练/parity/eval。

允许X在保留此验收、最新Plan4/README/STATUS和已审实现不变的前提下合并本PR并登记merge SHA；Codex不代合并，不等待代码合并才部署已冻结交付。若有实现变化应列明，不覆盖既有实验。

部署与纯文件准备结果见[长期记录](../../docs/stage_summaries/stage04_task008_acceptance_deployment_2026-10-15.md)。下一真实阶段为用户亲自启动audit；已通过的4f单11四步预检不重复。数据充分后再由Codex审查产物、交下一实际命令。不删除007/008交流、旧失败或新成功原始证据。
