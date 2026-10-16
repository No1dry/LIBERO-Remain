> 2026-10-16进度更新：下文动作parity命令已由用户执行，32/32逐bit一致并获验收。不要重复parity；现在进入[普通初态来源准备](../experiment_plans/stage04_normal_bank_runbook_2026-10-16.md)。原训练与执行记录以下保留。

# Stage04：FINISH小头训练完成；用户所贴结尾不是失败

2026-10-16。裁决：**05_train子阶段accepted**，无需重训／返修。用户运行冻结3433f487d38efe0a08e4c814e87412aad5aba9fe，贴出artifact JSON与exit0/tee0后询问是否失败；Codex读取完整1945行日志、training.json、head.json和head.npz，只读核验完成。原始文件均保留并已按服务器SHA备份本地。

## 完成证据

- training.json.status=finished、无error，50/50轮完成（100%），command_exit=tee_exit=0；全日志无Traceback，去除命令头／退出尾后可完整解析成与head.json相同的JSON，不是异常堆栈。
- 最佳epoch46，普通验证BCE0.0015248957788571715；最后epoch50为0.0016702923458069563，按既定严格改善／最早同分规则选中46。训练weighted BCE由首轮1.3244473528739562降至末轮0.001458570340484812。
- head为4096输入、LayerNorm→Linear128→GELU→Linear1，532737个有限FP32参数，NPZ无pickle，bytes1970485；artifact SHA6636f7133943d551df31a14822df440b63c1b98c0b3ee95f4873019492512c7f，权重SHA cdb2f7099c9e24cb51af25181113059c914889de8e61c2585ca7534cea6ec164。
- 原seed7／AdamW1e-3、wd1e-4／batch128／50轮／CPU配置不变。训练1071条1048负23正，验证190条188负2正；pos_weight1048/23仅由训练组计算。cache SHA仍5d09999ed6b91b1927eb02bf775d623d38064fbdca12503805a34ea01bcc8efc。
- 头与cache的base／data／source／label身份、行hash、特征来源及三个实现文件SHA均匹配；保存的training provenance与最终training.json一致（最终文件额外含head artifact SHA）。
- notice“Finish head only; base action weights are neither stored nor updated.”是正常说明：只训FINISH小头，不存／不改原VLA。base_modules_present=false、base参数hash=null也属离线cache-only训练预期，因为根本没加载动作模型，不是失败或“没有训练”。

[机器可读验收](evidence/stage04_head_training_acceptance_2026-10-16.json)。本地reports/stage04_head_training_review_2026-10-16/evidence保存四份原文件，完整SHA逐项与服务器一致；核验脚本只读JSON／NumPy，**没有实例化研究头、做头推理、加载VLA、训练或创建sim**。

这只证明训练作业及工件正确，不证明stop-capable，更不是模型成功率。验证正例仅demo_38两帧，不能由低BCE宣称跨场景停止泛化；普通停止校准／独立测试和Remain仍未执行。

## 下一步：用户启动动作一致性检查（不重训）

在服务器运行：

```bash
bash
source /HUBU-AI096/zp/ICML/stage04_finish_3433f48/session.sh
finish_sim 06_parity parity \
  --audit "$AUDIT" \
  --runtime-config "$CFG/oft_sog10.json" \
  --head-artifact "$OUT/train/head" \
  --atol 0 --rtol 0 \
  --out "$OUT/parity"
```

只取32个不同HDF head_validation输入，在同一个worker上原／shadow各1次，共64次真实forward；不是32条rollout，不创建native仿真。原Python、runtime文件SHA75f2a711…、checkpoint／crop／seed不改。阈值0.5仅为parity诊断，不是正式停止阈值；atol=rtol=0预先固定，不能事后放宽来救通过。

本次head路径OUT/train/head；新OUT/parity与LOG/06_parity.log已确认不存在，命令拒绝覆盖旧结果。完成后Codex核验parity.json status=completed、passed=true、32不同输入、零误差及原始pair／input/hash/RNG证据、exit0/tee0，再交普通停止校准所需准备／运行命令。Codex未代跑。

008／Stage04未closed。PR本轮不自动合并，源码和既有脏工作区不改；tasks/responses/reviews保留，精确待删=[]。本总结／回执／STATUS和历史训练手册完成标记按README提交GitHub并本地备份来源commit／SHA。
