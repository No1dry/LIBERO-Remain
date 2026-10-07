# Stage 00 总结：首次真实 OpenVLA-OFT 接入

总结日期：2026-10-07。作者：Codex。状态：closed（仅接入 smoke 范围）。
这不是完整 benchmark 验收，不代表 Plan 2 全部完成。

## 完成内容与身份

基准仓库 commit：`31288234bc9d2765e9647bc36b529b421da4ee19`。
任务：LIBERO-10 basket，官方 initial-state index 0，00/10/01/11 各一条。
输入为原完整指令、双相机与 proprio，不向模型提供完成 mask 或谓词真值。

模型来源：[作者发布的 SOG10 联合 checkpoint](https://huggingface.co/moojink/openvla-7b-oft-finetuned-libero-spatial-object-goal-10)。
下载 metadata 的 revision 为 `638918f3d1c2e43a39a8a20772bdb8b91835e4b7`，四个大权重分片均记录该 revision。
未在本阶段训练权重，也未对全部大文件重新做官方 SHA 比对。
不是仅 LIBERO-10 微调的示例 checkpoint。

OFT 源码 HEAD 为 `e4287e94541f459edc4feabc4e181f537cd569a8`，有历史路径/录像等本地改动。
transformers 使用 OFT fork。输出 8×7 action chunk，unnorm key 为 libero_10_no_noops。
模型不输出显式 STOP。

仿真固定 LIBERO `8f1084e3132a39270c3a13ebe37270a43ece2a01`、robosuite 1.4.0、MuJoCo 2.3.7。
模型使用已有 CUDA 环境的 overlay venv，仿真与模型分进程。

## 验收证据

- CPU fixture 四 mask 完成；最初测试 879 passed、11 skipped。
- 固定 simulator 安装后，真实 EGL doctor 通过。
- 四状态构造均通过 150-step 动态审计。
- 独立进程每 mask 两次、每次 150 steps：8/8 replay 通过。
- 真实 OFT inference 输出有限值的 8×7 动作块。
- 四 rollout 均完整执行，无 runtime error/invalid initial state/missing；四视频保存。
- 在线 summary、服务器离线 rescore、本地独立 metrics 复算一致。

实装时对两个 interpreter resolve 问题作了本地修复与回归验证：完整测试 891 passed，
worker 修复后相关测试 30 passed。正式 GitHub 集成尚未完成，移交 Stage 01 的任务 002。

## 结果

| mask | 预算内全目标达成 | 当前 joint_success | 初始成果保留 | 首次满足 | queries |
|---|---|---|---|---:|---:|
| 00 | 否 | 否 | N/A | — | 84 |
| 10 | 否 | 否 | 是 | — | 84 |
| 01 | 是 | 是 | 是 | 140 | 84 |
| 11 | 起点满足 | 是 | 是 | 0 | 19 |

00/10/01 运行 H=520、W=150，共 670 步；11 为 150 步。
01 在首次完成后继续 530 步，其中 226 步闭爪、29 次开→闭切换；目标关系保持。
这些是动作命令统计，不能当作实际抓取次数或指定对象的接触证据。
当前 trace 只有 step/goals/action/stopped，不含逐步对象接触或位姿。

官方接口的同 checkpoint/seed/initial index 单样本 00 控制也失败，使用 robosuite 1.4.1、
10-step wait 与官方 success 即停；与 Remain 的 80-step settled base、1.4.0 不等同。
四 mask 的 partial macro 为 0.5，只是这个单来源个案。

## 科学结论与边界

可以说真实模型接入已打通，01 有目标完成与保持的成功个案。
不能说 01/11 实现了 Learning Not to Act：没有 STOP，当前计分也不惩罚不必要任务操作。
不能把 10 失败确认为 skip 缺陷，因为本次正常 00 也失败。
一个来源不能确认 00 是偶然失败，更不能外推模型或 benchmark 总体成功率。

候选仍为 construction.legal=false；技术回放不认证全部语义/可见性/可执行性。
历史 Plan 1 的 5/5 门槛有不同 wait/恢复口径，不能覆盖本次 00 失败。

## 证据与本地归档

本地证据包 ID：`reports/libero_remain_oft_smoke_2026-10-06/`，位于用户的 Learning_Not_to_Act 项目。
含 README、完整 state construction/replay 包、probe、四 episode JSON、summary、run provenance、视频、
官方单样本控制，以及 interpreter 修复参考补丁。大资产与凭据不提交 GitHub。

关键相对工件为 codex_oft_basket_s0_run/{episodes,summary.json,videos}、
codex_oft_official00/result.json、codex_basket_s0_replay/replay_report.json。
summary 与此总结在本地长期备份，备份清单记录来源 commit 和 SHA-256。

## 关闭范围与移交

Stage 00 接入 smoke 关闭。当前 GitHub 交流目录尚无已闭环交流可清理。
开放事项：Stage 01 任务 001（指标展示/人工 UIR）、002（正式 interpreter 修复）。
它们不随本阶段关闭删除。

下一步先完成代码审查和版本冻结，再让 DeepSeek 做多初态官方/新协议 00 能力回归，
随后扩大 partial masks。UIR 先通过独立人工标注补充，避免把闭爪命令当重执行。
