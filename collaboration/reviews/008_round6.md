# Codex：008 Round 6——保留真实示范模型的受限兼容落实

2026-10-15。**已取得具体诊断证据；请X只补head示范审计的已核模型变体支持，不删除安全检查或修改场景。** R5资源验收、原初始化修复和两域设计保留；当前089e0b7仍不能执行完整真实audit，本项交付前不重跑旧audit/合并未修实现。状态：changes_requested（已批准actual HDF XML流程尚缺受限模型兼容），不是模型效果差返修。

[用户授权最小诊断与结论](../../docs/stage_summaries/stage04_task008_layout_diagnosis_2026-10-15.md)，[可用于CPU回归的实际布局与证据](../../docs/stage_summaries/evidence/stage04_task008_layout_diagnosis_2026-10-15.json)。基准/交付仍[PR #5](https://github.com/No1dry/LIBERO-Remain/pull/5)的089e0b7fa3916e6444b0880ca61101cac791c1ba，X先同步最新main和本审查；本轮不改benchmark/source001/模型或标签定义。

## 1. 已确认的触发原因（不再猜测）

Codex在用户对明确最小诊断请求回复“继续”后，加载默认场景和第一条实际demo_10 XML，仅比较布局，无任务动作、无积分、无HDF state恢复、无标签/VLA/训练。

| 字段 | 当前基准 | demo_10 |
|---|---|---|
| nq / nv / nu / nbody / nsite / njnt | 65 / 57 / 9 / 29 / 23 / 17 | 完全相同 |
| joint名字/type/qposadr/dofadr | 17个及完整地址 | 完全相同 |
| 其余_layout字段（除下述3项） | 基准 | 完全相同 |
| ngeom | 161 | 162 |
| geom_names / geom_bodyid | 基准 | 在ID73增加robot0_link7_collision后后续ID移位 |

新增geom父body=robot0_link7、type=mesh、mesh=robot0_link7、rgba=0 0.5 0 1。**它是真实示范原XML的一部分，不得称为已经证明物理等价的纯ID变化**；可能影响碰撞/观测/K4结果。保持原XML才符合此前批准的actual示范恢复要求。

对demo的geom_names/geom_bodyid只在内存比较副本中排除这一新增项、ngeom减一后，完整_layout与基准逐项相等；这只是严格比较的证据，不是授权删实际geom。两边都有7个匿名geom，不能用dict/set把None合并掉。共同具名geom的body归属未发现变化。

完整XML还存在两处番茄geom四元数打印末位差异0.663328→0.663329，以及辅助相机paperview/canonical_agentview差异；因此不写“完整模型唯一区别是一个geom”。诊断中的实际policy相机agentview和robot0_eye_in_hand共同属性完全一致；全部50原HDF XML的新增geom及这两个相机静态签名一致。只编译验证了demo_10，不冒称50条均完成native验证。

默认compiled XML hash dad2437d1c2f8cbff26232c252f241978ce7de02cc6e34da0267fc94f4607163与既有source001一致；demo compiled hash b97ae2c76617c06aa6006e1818b34a4f5c37c4d18a2762d32e0e96afb198055b。不是此前路径修复暗改了基准场景。

## 2. 研究裁决与严格范围

原方案A已要求使用官方HDF actual XML；在**不编辑HDF/XML/asset/state、只在head示范审计分支接受这一已核变体**的边界内，是原方案的实现完善，不重新选择A/B。不得为凑161删geom、禁碰撞或换用默认eval模型。head数据域与eval域因此可能还有模型差异，必须metadata/报告披露，不归因模型失败/不报物理等价。

benchmark的normal/Remain eval、source001/replay、FinishLiberoEnv及原无FINISH参考不变；冻结OFT/相机/crop/seed/chunk/网络/优化器/阈值/metric、GT/释放/K4/unknown合同不变。若想改eval模型、删/禁碰撞几何、接纳其他未知变体或改label，超出本项，另找用户决策。

## 3. X的最小实现要求

- 保留默认完全相同布局的通过路径；仅DemonstrationAuditProvider的actual已审HDF来源允许版本化、显式的已知额外geom变体。绑定实际HDF/profile/原XML/扫描身份，不能提供任意allow_mismatch或caller宽松开关。
- 关节names/type/顺序/qposadr/dofadr、nq/nv/nu/nbody/nsite/njnt、body/site/actuator名字与地址/父子/传动等既有字段仍严格相同。不能只比123维、集合或数量，不重排/重映射saved state。
- 几何比较要保留顺序和匿名项：只允许**恰好一个**robot0_link7_collision插入，必须绑定已核body robot0_link7与mesh robot0_link7/实际源资产；除该项外geom_names/geom_bodyid完整序列及ngeom与基准相同。其他增删、重复、错归属、缺gripper/目标geom、匿名项变化、状态地址变化一律拒绝。可以采取等价更明确的实现，不要求固定函数名。
- 读取actual source XML及当前compiled model验证该变体，不靠名字包含collision放行；不要把其他geo改名成许可项。源HDF/XML/资源SHA及当前asset resolver检查保留，不编辑XML去“对齐”。实际新增几何体的物理/视觉属性保留并记录，不把它说成惰性/无影响。
- 兼容证据记录到audit/provider已有metadata链：规则版本、exact或已核variant、原/processed/compiled XML hash、baseline/loaded layout hash、具体差异/新增geom归属。让这些实际证据随audit SHA进cache/head，不进policy/head输入。失败也落具体field diff，不再只有笼统layout error。
- 使用加载后新model的实际geom引用/名字与native重绑references；不能继续按旧数字ID读contact/geom。保持R2恢复后才建合同及父态精确恢复，unknown不伪造。实际policy相机仍agentview/wrist，不用辅助camera弥补视野。
- 不扩大到自动接受任意dataset。当前支持范围就是原任务的官方basket HDF/profile与已核源XML；其他未知model变化明确拒绝。原物理label/观察/hold的正常运行与退出行为不改。

## 4. 一次交齐的CPU/fake回归

不得X代跑真实sim/VLA/科研训练。使用本次真实布局JSON回放与受控fake：

1. exact通过；实际161→162已核变体通过；实际7个None不丢。比较前后布局/源XML不被函数就地改写。
2. 未知extra、two extras、重复许可名、wrong body/mesh/target/gripper geometry、匿名数量/顺序/归属改变均拒绝；即使nq/nv等数量相同也不能放行。
3. joint名字/顺序/type/qpos/dof地址、actuator transmission、body/site语义改变仍拒绝；不通过tuple/set丢重复/None。
4. 兼容只作用head actual-demo provider，不影响FinishLiberoEnv/eval或开任何GT停车；default/env配置及原失败raw不改。
5. 实际provider首次/换XML/连续帧/hold父态重绑回归、tinyHDF 0/1/unknown/partial关闭、资源scan/cache复核、原FINISH全套仍过。
6. 失败报告包含具体before/after/diff，成功报告标明真实模型域差异而非“与eval完全一致”。

交response008_round4、实现/最终固定SHA、精确生产diff、CPU结果/skip原因/候选audit命令。X不自行accepted/closed/运行真实阶段。Codex审查部署后用户仍重跑原同一audit、新out/log，不新增单独11预检、下载或采集；本次诊断授权已用完，不自动扩为Codex跑真实audit。

下一步执行者：**X补这一受限示范模型支持；Codex审查部署与命令；用户启动真实audit，充分后feature/训练。** 原38/4f/b596/9ddd/089失败和R1..R6证据全保留，待删=[]。
