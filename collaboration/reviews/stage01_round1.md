# Codex Review：Stage 01，PR #1

日期：2026-10-09。审查者：Codex。
PR：https://github.com/No1dry/LIBERO-Remain/pull/1
审查 HEAD：`7ca5cec421925bb14cbbbf7997ddc8e9294db0c9`；实现 commit：`46d935b1b8e8109bbc840a2e4347ed520cdd4df7`。

## 裁决

**001 与 002 代码功能验收通过，无阻塞发现。**
UIR 是独立人工标注指标；本轮没有产生真实 UIR 分数，也没有证明模型已经具备行动克制。
PR 还未合并；代码实现者 X 现在获得明确的合并授权：在确认实现代码没有新增未审查变化后，
可将包含本轮审查文档的 PR #1 合并到 main，并记录 merge SHA。若有实现变更，需再提交 review。

这份文档由 Codex 给出验收裁决，不是 X 自行宣布完成。发布前保持 Stage 01 的 accepted 状态；
合并与本地归档核验后才标记 closed、清理交流。

## 独立验证

1. macOS，Python 3.12.7 / NumPy 1.26.4 / pytest 8.2.0：**985 passed，12 skipped，16.69s**。
   跳过 11 项可选固定仿真源码、1 项本机无 imageio_ffmpeg 的视频测试。
2. Linux，Python 3.10.20 / 既有 vla_lgm CPU 测试环境，禁用 CUDA：
   **986 passed，11 skipped，51.44s**。跳过项均为审查副本未安装的固定仿真源码。
   Linux 的真实 venv symlink/site-packages worker 集成实际通过，补齐 X 的平台限制。
3. 用本次真实 OFT 四 episode 历史结果调用新 `report` 和 `uir-template`：
   - 源 run 全部文件 SHA-256 前后相同；
   - 旧 summary，包括每项分子/分母与 macro，完全一致；
   - 四行模板均为 null/unreviewed；UIR macro=N/A，annotated=0、unannotated=4；
   - 同 task/source 的 JSR 仍为 00=0、10=0、01=1、11=1，partial macro=0.5。
4. Git diff 核对：`metrics.py`、物理 `runner.py`、`libero_env.py` 未改；
   `git diff --check` 通过。

本地审查工件位于项目 `reports/libero_remain_stage01_codex_review_2026-10-09/`。
未加载 VLA 权重、未运行新 GPU rollout、未改历史结果。

## 已核对的计分与实现边界

- 未标注、unknown、运行错误均不当作 UIR=false。
- 有效 true/false 绑定 run/manifest/episode、完整 rollout 与录像证据；
  不同 run 同名 episode、重复、非法标签/区间和越界路径被拒绝。
- task×mask、partial macro 与 suite 的统计没有被池化替代；缺标注格显示 N/A，覆盖率另报。
- 模板与派生报告写到源 run 之外的新路径，旧原地 rescore API 保持兼容。
- 两个 interpreter 路径均保留 symlink；子进程环境隔离、超时、清理行为未被改写。

完整录像/区间校验只检查证据声明和绑定，不能证明人工真的完整审核，也不能自动认证语义。
严格全帧约束是 v1 的已声明边界，不能在标注时偷偷放宽。

## 非阻塞注意事项

- first_all_success_step 的诊断均值可能含 H 后首次达到目标的样本；它不等同于预算内成功耗时。
  现有文档已解释，正式结果读者仍须同时看成功率与 n。
- bootstrap 的 pip 23 / CPU 单 index 安装问题未修。使用原有已安装环境时不会阻塞此次功能发布；
  若要宣称全新机器一键安装稳定，应另设安装任务，不能把旧 workaround 当已修复。
- 正式论文中不能从本次单来源 00 失败推出“模型普遍不会 skip”，也不能先给 01 人工标签 true。

## 下一步

1. X 合并 PR #1、记录 main SHA；若本轮仅新增交流/总结文档，已审实现结论保持。
2. Codex 核验 main 的阶段总结、本地备份 hash，之后关闭 Stage 01；当前不删除任何交流。
3. 先对既有四段视频做人工 UIR 校准。DeepSeek 只生成模板/派生报告、核验原结果 hash；
   真实语义判断由 Codex/用户完成，不能让机械执行者用闭爪自动贴标签。
4. X 执行 [任务 003](../tasks/003_normal00_regression_entry.md)，补齐官方/Remain 00 回归入口；
   Codex 通过代码审查后，DeepSeek 再按固定 basket indices 0..4 跑 00 配对回归。
5. 正常能力和接口差异解释清楚后，才扩 partial tasks。此轮不训练 gate、不上六模型全矩阵。
