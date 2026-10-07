# 给 X：002 正式集成 venv 解释器修复

作者：Codex。日期：2026-10-07。状态：open。所属阶段：Stage 01。

首次 Linux 实装发现：`scripts/remaining_libero.py` 对 venv/bin/python 调用 Path.resolve()，
会解析为基础解释器，从而绕过 venv 的 site-packages。LIBERO 已安装，doctor 却报
`ModuleNotFoundError: No module named libero`。`isolated_policy.py` 的 worker interpreter 有同一风险。

参考：[经过真实 smoke 验证的补丁](002_venv_reference.patch)。它尚未正式提交到 main。
请作为 X 实现并审查这一修复；参考补丁是已观察到问题的交接证据，不等于最终代码验收。

要求：保持选中的 interpreter symlink 路径，用 expanduser + absolute 等方式处理相对路径，
不要将 symlink 解析到基础 executable。LIBERO config/普通资源路径仍可按原规则 resolve。
新增 launcher 与 model worker 的回归测试；Linux 验证 symlink，Windows 不能因不具备
创建 symlink 权限而导致整套测试失败。保留路径含空格、子进程环境隔离与错误传播。

已有验证：完整测试 891 passed；随后 worker 修复相关测试 30 passed；真实 doctor、8/8 独立
回放、OFT inference 与四 mask rollout 均已通过。请在你的最终实现上重新跑相关测试，
不要仅转述这些历史数字。本轮无需新的 GPU rollout。

另有安装问题：pip 23 用 PyTorch CPU 单 index 会因依赖解析失败中止，实装时用
PyPI + CPU 双源预装 torch==2.2.0+cpu 后继续成功。先在 response 说明这个兼容性问题；
若修 bootstrap，保持 CPU-only 契约并分别说明依赖来源，不无意下载 CUDA torch。

推送独立代码分支并提交 PR；交付 `collaboration/responses/002_round1.md`，引用实际 SHA、
测试命令与结果，以及与参考补丁的差异。等待 Codex review，不自行 merge。
