# Stage04：真实特征导出完成与缓存验收

2026-10-16。裁决：**04_features子阶段accepted**；008／Stage04未closed。用户亲自运行冻结3433f487d38efe0a08e4c814e87412aad5aba9fe的特征重导出，Codex只读核验。没有重做audit、原模型训练或追加模型forward。

## 已完成

本次重试expected_forwards=completed_forwards=1261，完成100%，model_loads=1，status=completed、completed=true、error=null，command_exit=tee_exit=0。完整cache存在，矩阵为1261×4096 float32。这里只报这次完整重试的1261次，旧2cb失败实际forward数仍未知，不把它算成0。

| 角色 | 可用特征 | label0 | label1 |
|---|---:|---:|---:|
| head_train | 1071 | 1048 | 23 |
| head_validation | 190 | 188 | 2 |
| 合计 | 1261 | 1236 | 25 |

原audit1313帧中的52unknown按约排除，不填负例；已知标签覆盖96.04%，不是模型成功率。验证正例仍仅demo_38两帧；训练正例来自11条演示。完整cache没有遗漏已知角色行，也没有加入official-init或Remain评测输入。

## 独立只读核验与身份

Codex在冻结源码下运行load_feature_cache，显式比对原audit、原base及两来源域身份；核对全部1313原始观测、1261模型输入NPZ及schema／BF16／来源dtype／input hash、特征NPZ和行级label／source／role。1261个输入hash均唯一，4096维FP32特征有限。源代码262文件／11部署文件不变。没有模型forward、物理sim或真实小头训练。

- cache语义SHA：5d09999ed6b91b1927eb02bf775d623d38064fbdca12503805a34ea01bcc8efc
- feature NPZ SHA：f5d8509235cbd003f18288e3c842b6ba160be74475be1caa9839b1ee41ac8ffe
- audit内部SHA：44d0ab96f910221b58f2bfc930c6e1a06db79f23f19755318cd6d34764bf8457
- base identity SHA：4601be2d7857e255cfde08ad06680428e01c49fb982614221f5bd04a92f39734
- frozen runtime文件SHA：75f2a711a39c58a07715b3a280aeba26a29dfbba70caf87cc051520f0a3f9720
- feature_export.json文件SHA：c27be8ed11691764cfaf161557379838d5273eecb4cbe0a7ff96a75fd5b1fef4
- cache.json文件SHA：6fe7395330a35aecae3ed0ee0f8a25f3ae891216fb6138ffdfe8a7baf67f2685
- 04_features.log SHA：0e253360c1ec92c1d1b6ad126daa0ff1f45daac84b5fc7df11bf46f2ae7b0bdf
- 服务器独立验收回执文件SHA：1b6c62d5452687deb30c03333783f1b8b7d55c304d4259f5a0dfe3909d50777e

[机器可读回执](evidence/stage04_feature_cache_acceptance_2026-10-16.json)。本地reports/stage04_feature_export_pass_2026-10-16/evidence保存report、cache清单、feature NPZ、log和验收回执，按SHA与服务器核对；**没有把完整1313观测／1261输入NPZ树全量复制本地**，原树仍在服务器。2cb失败partial与日志全部保留。

## 下一阶段

[完整小头训练命令](../experiment_plans/stage04_head_training_runbook_2026-10-16.md)。用户只启动05_train，从已验收缓存训练FP32小头；原train.json参数不改：seed7、AdamW1e-3／1e-4、batch128、50轮、CPU；仅训练组计算pos_weight1048/23，完整50轮后按head_validation普通BCE选最早最优权重。独立核对CLI／配置与此前约定一致，不需X返修。

训练尚未由Codex启动。完成后Codex核验head及训练日志，再交32输入／64forward的真实同worker动作parity命令，随后普通停止校准、独立normal测试和Remain评测。当前不能由特征齐全宣称stop-capable、模型成功率或研究假设成立。跨域物理祖源／SOG10 exposure未证明、HDF模型域差异和失败负例覆盖不足仍披露，不因结果临时改split／预算／阈值。

本记录、命令及回执按README提交GitHub并本地备份来源commit／SHA。没有新实现变更、PR自动合并或删除；007／008仍非科研closed，tasks/responses/reviews保留，精确待删=[]。
