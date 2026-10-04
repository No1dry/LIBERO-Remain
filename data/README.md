# 候选数据与可选证据包

Git仓库不提交大型仿真资源、已安装环境、模型权重或全部构造/回放日志。推荐在目标机器重建候选：

```bash
python scripts/bootstrap_remaining_benchmark.py simulation \
  --python python3.10 --phase all \
  --out data/remaining_goals_local --reports reports/remaining_goals_local
```

完整参考规模为10任务×3来源×4掩码=120候选；LIBERO-10与LIBERO-90分别为72和48。每候选重复两次150步HOLD回放用于恢复一致性验收，不调用VLA，也不增加独立研究样本。

生成目录如下：

```text
data/remaining_goals_local/
  libero_10/manifest.candidates.json
  libero_10/states/*.npy
  libero_10/validation/...
  libero_90/...
reports/remaining_goals_local/
  collection_report.json
  preview.html
  libero_10/replay_report.json
  libero_10/group_*/repeat_*/mask_*/...
  libero_90/...
```

构造报告保留尝试、失败和排除原因。只有整组四掩码通过才导出；数量与结果以报告为准。所有自动生成状态仍为 `construction.legal=false`，需另行审查语义、可见性、支撑关系及剩余执行可行性。

如 [v0.1.0-pilot Release](https://github.com/No1dry/LIBERO-PAB/releases/tag/v0.1.0-pilot) 提供 `libero-pab-v0.1.0-pilot.zip`，可按实际清单下载并离线检查。该链接标识计划版本，不承诺附件已存在；没有附件时仍可使用上面的重建流程。文件哈希只证明包内一致性，不是正式研究批准或跨机器运行保证。

若附件采用本项目的候选交付格式，可以使用仅依赖标准库的验证入口：

```bash
python -S scripts/package_remaining_benchmark.py verify --zip /path/to/candidate-evidence.zip
```

模型XML哈希可能包含绝对资产路径，环境指纹还包含版本、资源和兼容实现。新机器或新路径必须重新构建/验收；不要改旧manifest指纹绕过检查。历史通过记录只适用于其实际记录的环境和协议。

策略评测结果另存到指定run目录，包含配置、逐步动作/谓词、异常和离线评分；当前不生成策略rollout视频。候选HOLD验收帧不能替代真实VLA失败视频。
