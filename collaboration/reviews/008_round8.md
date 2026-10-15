# Codex：008 Round 8——真实OFT输入证据8维合同P1

2026-10-16。**changes_requested，仅明确输入证据校验错误；成功的1313帧audit保留，不重做仿真/标签。** 用户已运行2cb1428的04_features，status=error、completed=false、model_loads=1，cache_path=null、cache/cache.json不存在，exit2/tee0；尚不可训练。此前audit ready/完整观测与标签复核仍有效。

## 已核错误与来源

异常：`unexpected OFT proprio/pixel tensor shape`。

- report路径stage04_finish_2cb1428/results/run01/features/feature_export.json，文件SHA c0db3c91c5b9c507292c2348fa1bdf11e8f5e12d77f9d981fb10161443190d8b。
- log路径stage04_finish_2cb1428/logs/run01/04_features.log，SHA 8b5d82683cb0abcadc9f7d93fcb3383f4a3306c122815e5bba1178d0ef5c9313。已下载本地并逐SHA核对一致，失败partial全部保留。
- finish/schema.py:97–98只接受proprio.shape=(7,)或(1,7)；这是错误的LIBERO-OFT合同。
- 实际固定上游e4287的prepare_observation把eef_pos3、quat转axis-angle3、gripper_qpos2拼成8；initialize_model明确proprio_dim=8。第一份真实审计观测shape也为pos3/quat4/gripper2，实际checkpoint dataset_statistics.json的libero_10_no_noops proprio所有统计向量均8。不是猜测新模型结构。
- 原Capture在oft.py:133–145复制原predict_action实参，未更改它；错误在返回的证据校验阶段触发。原forward可能已执行并返回，**不能把model_loads1解释成只加载且0 forward，更不能称1261次已完成**；完整成功forward计数没有写入该失败回执。
- fused vision每相机6通道、两个相机拼12，是原预处理；当前schema只检查pixel rank4/5，12C不是本异常原因。7是每个action维度，action chunk仍(8,7)、action tokens56。

[实际代码/config/观测shape与CPU复现证据](../../docs/stage_summaries/evidence/stage04_feature_input_shape_2026-10-16.json)保留来源文件SHA。Codex没有重载模型或追加forward。

## 一次落实的最小要求

1. 纠正**新真实SOG10输入证据合同**为原始8维proprio，接受其实际(8,)/(1,8)单样本形式；保留batch1、finite、dtype、BF16 uint16 bit保真、bool和字段白名单。拒绝任意其他尺寸，不能删除shape校验。错误应分别给expected/actual proprio与pixel shape/dtype，不打印张量值。
2. 不截断丢一个手指、不补零、不reshape原model实参、不改normalize/crop/processor/两视角或动作解码；所有真实输入字节保持由原adapter/上游决定。原模型、权重/projector、原指令、动作(8,7)、56-token均值、FP32特征/头训练/阈值/指标不改。
3. 中央fake修正混淆：proprio从7/Linear7改为8，双相机processor测试覆盖每图fused6、concat12，不把所有数字7批量改8（动作维仍7）。保留小型toy输入测试，但必须增加真实入口形状，防止“全部fake过、真接口不符”。
4. capture→policy envelope→input哈希/typed NPZ→feature cache写/读→parity输入/worker同一合同。优先修正现有错误，不要求新版本号/CLI；若自行版本化，必须同步全部消费者，尤其data._input_evidence的schema字符串与input_sha256，不能只改验证器让保存/读取下一处再失败。
5. 历史原始结果/已完成audit/旧失败缓存不覆盖；若确有旧7维测试工件读取需要，用明确legacy路径，不把它当当前固定OFT真实输入。当前没有可用新真实cache或头需要迁移，不允许复用本次partial伪造completed。
6. 同forward/原动作/原输入捕获/RNG机制保持，避免新增predict/processor调用来凑证据。异常仍恢复捕获方法、关闭worker、保留partial与原错误；不得为调试自行加载真实VLA或重跑实验。

## CPU/fake回归交齐

- 原冻结schema的NumPy复现：7+6C接受、7+12C接受；8+6C及8+12C均同报本异常。修复后当前真实合同8维/单batch形状通过，错误7/9/错误batch/rank、NaN/错误dtype等拒绝。
- 采用原调用形态：numpy proprio8、bf16 pixel_values(1,12,224,224)、int64 IDs、bool attention，两个真实风格RGB crop；通过capture及实际schema/hash/codec往返，BF16逐bit相同，原模型fake收到的输入和原action chunk逐bit不变，调用次数不增加。
- 端到端synthetic audit→export→cache load→tiny head训练入口/32 distinct parity选择，两个head角色/label/来源身份及unknown排除不变；不只测孤立validate函数。可用小图减CPU费用，但真实12C/8D规格必须有直接回归。
- 原冻结/RNG/同forward、R6示范兼容、audit/asset及全套CPU/fake继续通过；报告passed/skip原因、生产diff、CLI/runbook候选参数。

交response008_round5、实现/最终SHA、最小diff和证据；X不做真实forward/训练、Codex不代改benchmark。范围不扩成改模型或新数据采集。

## 新部署与下一阶段（不要再次audit）

已验收audit仍在`/HUBU-AI096/zp/ICML/stage04_finish_2cb1428/results/run01/audit`，audit内部SHA44d0ab96f910221b58f2bfc930c6e1a06db79f23f19755318cd6d34764bf8457，1313帧、已知1261、unknown52；验证仅demo_38两正例的pilot限制不改。

Codex验收后新源码/新session/新feature out/log，但--audit显式指向上述原成功目录，复核后复用，不复制/改造labels、不重新恢复1313帧。用实现已有export-features入口；实际新绝对路径由Codex填齐。本次partial feature目录与04_features.log不得覆盖。features成功且cache身份复核后再给用户小头训练命令；当前不进入训练。

本P1交付验收前暂停未修PR合并及旧版feature重跑；数据audit子阶段不撤销，008/Stage04未closed，所有旧失败/成功与交流保留，待删=[]。执行者：X修证据合同和测试；Codex审查部署/只读复核；用户仅启动特征重导出。
