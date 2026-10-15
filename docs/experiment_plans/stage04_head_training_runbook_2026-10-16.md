# Stage04：已验收特征缓存上的FINISH小头训练

2026-10-16。仅用户启动05_train；不串联parity、校准或eval。冻结源码3433f487d38efe0a08e4c814e87412aad5aba9fe。04_features及原audit已完成，不重跑，不覆盖旧失败。

## 服务器命令

```bash
bash
source /HUBU-AI096/zp/ICML/stage04_finish_3433f48/session.sh
finish_model 05_train train \
  --cache "$OUT/features/cache" \
  --training-config "$REPO/configs/remaining_goals/finish/train.json" \
  --out "$OUT/train"
```

已登录root@122.204.216.104:30369后执行；不在文档保存密码。session只设置环境与日志函数，不自动作业。finish_model选择原oft_worker Python并核验262源码／11部署文件，记录完整命令、UTC、退出码；已存在的05_train.log或train目录拒绝覆盖。

## 固定训练合同

仅从1261条已验收FP32特征训练LayerNorm(D)→Linear128→GELU→Linear1小头，不加载真实VLA／base权重、不仿真、不改动作网络。训练head_train1071条（1048负、23正）；head_validation190条（188负、2正，两正均demo_38）。unknown52不作为负例、不入训练。

使用已随源码冻结的configs/remaining_goals/finish/train.json，SHA256 d16c0d7ea3a3ae476aa8746cae0713e0f9cce6f2db47208a1a41b73c6dea413d：seed7、AdamW lr0.001、weight_decay0.0001、batch128、50轮、CPU FP32。pos_weight仅由训练集1048/23计算；普通未加权head_validation BCE选权重，严格改善才替换、同分保留最早epoch。完整跑完50轮再载best，不是early stopping。不改split、不用official init／Remain测试选epoch或调阈值。

输入cache SHA5d09999ed6b91b1927eb02bf775d623d38064fbdca12503805a34ea01bcc8efc，绑定原audit SHA44d0ab96f910221b58f2bfc930c6e1a06db79f23f19755318cd6d34764bf8457和原base identity SHA4601be2d7857e255cfde08ad06680428e01c49fb982614221f5bd04a92f39734。

## 输出与完成后

- training.json：/HUBU-AI096/zp/ICML/stage04_finish_3433f48/results/run01/train/training.json
- head：同目录head/head.json及head.npz
- 日志：/HUBU-AI096/zp/ICML/stage04_finish_3433f48/logs/run01/05_train.log

预期training.json.status=finished、50个epoch、有效best_epoch、head工件、feature_provenance绑定上述cache、command_exit=tee_exit=0；这些都由Codex收到用户“完成”后核验。失败／中断保留partial及日志，不原地重跑、不自动改训练参数。完成小头仍不等于stop-capable；接着由Codex交真实32输入／64forward的同worker动作parity命令，再做独立普通停止校准与测试。

Codex只读文件验收和准备命令，没有启动真实训练。验证正例仅demo_38两帧的pilot限制保留，跨来源域物理祖源独立性未证明。008／Stage04未closed，待删=[]。
