# 给 X：003 单任务、多初态的官方/Remain 00 回归入口

作者：Codex。日期：2026-10-09。状态：open。所属阶段：Stage 02。
前提：PR #1 合并与版本冻结。代码由 X 实现；之后的实验由 DeepSeek 机械运行。

## 原因与目标

真实 smoke 中 basket 的 00 在 Remain 和官方接口各一条都失败，但历史 Plan 1 有不同
wait/恢复口径的 5/5。现在不能认定失败偶然，也不能将 partial 失败归因于 goal selection。
先提供可直接运行的 00 能力回归入口，避免要求 DeepSeek 临时改源码或写实验脚本。

首轮限定同一个 SOG10 checkpoint、basket、官方 initial-state indices 0..4、policy seed 7。
此任务只实现代码并以 CPU/fake policy 验证，不运行新的 GPU 实验。

## 最小接口

CLI 至少可指定：model runtime config、task catalog key、准确 initial-state index 列表、
protocol（official / remain / both）、全新输出路径和录像参数。提供 dry-run/计划输出，
列出将跑的所有 task/index/protocol、checkpoint、预算、warmup/settling 与总 episode 数。
首轮 both 应恰好是 5 official + 5 remain 00，不默默扩到全部任务或 partial masks。

优先复用官方 OFT init/inference/action 代码、现有隔离 worker 和环境恢复模块，避免复制新动作映射。
若某官方控制需要 model Python 创建它原生的环境，明确记录 interpreter、LIBERO/robosuite/MuJoCo 版本。
不要把现有部署 observation 输入改成带 predicate 或对象真值。

## 两协议必须明确区分

- official：使用该模型官方初态/等待/预算/成功终止方式；先按同 seed/index 验证。
  对照本轮是 10-step wait、H=520、success 即停；不将 evaluator 停止冒充模型主动 STOP。
- remain：保持本库既有 00 准备与恢复、H=520/W=150 的评分契约；success 不替模型停车。
  输出完整目标轨迹与现有分数。不得为了救回归改为早停或换更容易的初态。
- 共同比较字段是预算内 all-goals-ever success；Remain 的稳定保持/joint 分数另外报。
  两种协议的原生 SR 定义、观察窗口、仿真版本、机器人初态差异都进入报告。

首轮只是 capability regression，不冒充完整 00/10/01/11 benchmark。
复用已验证 state bank 时记录原 manifest/state hash。缺对应来源时可提供独立 00 准备流程，
不为 00 回归强制跑所有 partial 状态；但不能绕过旧完整配对验证，将单 mask 包伪装成完整 benchmark。
使用清楚的 purpose/schema 标记 capability-regression 数据与结果。

## 记录与失败规则

每条保存 task name、suite、准确初态 index、RNG seed、模型/代码/归一化身份、
原指令、实际 warmup/settle、step0 观测、首动作、结束原因、控制步数、trace、视频与耗时。
切换 episode 清 harness queue；恢复 guard 沿用已验收实现。

固定尝试 0..4，不替换失败初态，不因 policy 失败筛 eligibility。环境/加载/运行错误单列。
同状态重复确定性执行不作为独立样本。物理准备失败与策略失败分开，保留 attempted 分母。
新输出目录；不改历史结果、官方 checkpoint 或已有实验环境。

## 验证与 GitHub 交付

CPU/fake policy 测试：task/index 准确映射、预算/等待不重复、队列清理、官方成功终止与
Remain 持续窗口区分、双协议覆盖完整且无重复、错误/缺失分母、无输出覆盖、无真值泄漏。

推送独立分支与 PR，交付 `collaboration/responses/003_round1.md`：实现 commit、实际测试结果、
dry-run 示例、两协议原生环境差异、DeepSeek 可复制执行的命令和预估预算。
官方模型分数未在此轮复现时明确标为未验证。等待 Codex review，机械执行前不自启动 GPU。
