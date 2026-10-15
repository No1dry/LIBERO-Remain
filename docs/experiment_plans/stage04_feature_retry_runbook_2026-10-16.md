> 2026-10-16完成记录：本页04_features已由用户执行，1261/1261完成并经Codex完整缓存核验。**不要重复执行本页命令**；下一步用[05_train小头训练手册](stage04_head_training_runbook_2026-10-16.md)。本页以下保留为历史执行命令。

# Stage04：R8修复后的特征重导出命令

2026-10-16。仅本轮04_features重试；软件已验收，新冻结源码3433f487d38efe0a08e4c814e87412aad5aba9fe。**原1313帧audit已完成，不再运行audit-data、预检或数据下载。用户亲自启动下面一个阶段，Codex没有代跑。**

## 在服务器直接执行

SSH入口为root@122.204.216.104，端口30369；本文件不保存密码。已经登录则从bash开始：

```bash
bash
source /HUBU-AI096/zp/ICML/stage04_finish_3433f48/session.sh
finish_sim 04_features export-features --audit "$AUDIT" --runtime-config "$CFG/oft_sog10.json" --out "$OUT/features"
```

session只设置环境和函数，不自动启动任何作业；stage_log自动检查262源码／11部署文件、拒绝覆盖同名日志，保存UTC、完整命令和command_exit／tee_exit。不是后台任务，不自动串联训练。

| 项目 | 固定路径 |
|---|---|
| 源码／cwd | /HUBU-AI096/zp/ICML/LIBERO-Remain-stage04-finish-3433f48 |
| runroot | /HUBU-AI096/zp/ICML/stage04_finish_3433f48 |
| AUDIT（旧成功，只读复用） | /HUBU-AI096/zp/ICML/stage04_finish_2cb1428/results/run01/audit |
| CFG | /HUBU-AI096/zp/ICML/stage04_finish_3433f48/configs |
| 新features | /HUBU-AI096/zp/ICML/stage04_finish_3433f48/results/run01/features |
| 新log | /HUBU-AI096/zp/ICML/stage04_finish_3433f48/logs/run01/04_features.log |
| simulator侧CLI Python | /HUBU-AI096/zp/ICML/LIBERO-Remain-normal00-stage02/.runtime/remaining_libero/venv/bin/python |
| 隔离模型worker Python | /HUBU-AI096/zp/ICML/LIBERO-Remain-normal00-stage02/.runtime/oft_worker/bin/python |

runtime JSON字节SHA256为75f2a711a39c58a07715b3a280aeba26a29dfbba70caf87cc051520f0a3f9720。固定原SOG10 OFT／seed7／原crop不改。AUDIT内部SHA44d0ab96f910221b58f2bfc930c6e1a06db79f23f19755318cd6d34764bf8457。

## 完成后

预期是1261个已知标签帧的真实模型forward，unknown52不导出；训练1071、head_validation190。以feature_export.json的status=completed、completed=true、expected_forwards=completed_forwards=1261及cache/cache.json实际存在为初步信号，随后Codex复核cache行身份／标签／hash后再交训练命令。不要把model_loads=1或CPU测试通过当作真实特征导出完成。

进程失败或中断时保留新partial和log，不原地重跑；给Codex读取结果。旧2cb失败feature目录不删除、不覆盖、不恢复为“成功”。这一步不启动sim／物理标签，但会加载真实VLA，故仍由用户亲自启动。真实head训练、parity、校准与评测尚待后续逐阶段命令。

[审查裁决](../../collaboration/reviews/008_round9.md)；[长期记录](../stage_summaries/stage04_input_contract_fix_acceptance_2026-10-16.md)。008／Stage04未closed，待删=[]。
