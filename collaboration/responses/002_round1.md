# X 对任务 002 的交付：保留 venv 解释器路径

日期：2026-10-08。执行者：X。状态：交付待审，不作 accepted/closed 裁决。

- 任务：[002_venv_interpreter.md](../tasks/002_venv_interpreter.md)。
- 基线：`main` 的 `467b6d9`；工作分支：`x/stage01-metrics-uir-venv`。
- 实现提交：[46d935b1b8e8109bbc840a2e4347ed520cdd4df7](https://github.com/No1dry/LIBERO-Remain/commit/46d935b1b8e8109bbc840a2e4347ed520cdd4df7)。同一提交包含任务 001，各自文件范围见两份 response。PR：[#1](https://github.com/No1dry/LIBERO-Remain/pull/1)，open、未合并。
- 本轮不 merge、不运行 GPU 实验，不将历史 smoke 数字作为本次测试结果。

## 实现与参考补丁的差异

- `scripts/remaining_libero.py`：解释器先 `expanduser()`，相对路径仍以指定项目根目录为基准，再以 `os.path.abspath()` 绝对化；不解析解释器 symlink。普通 LIBERO config 路径仍使用 `resolve()`。
- `benchmark/remaining_goals/isolated_policy.py`：采用参考补丁的 `expanduser()` + `os.path.abspath()`，保留模型 venv 的入口路径；相对解释器路径仍以调用进程当前目录为基准。
- 两处均保留现有文件存在检查、列表形式的子进程命令和错误传播；未改变 worker 的环境变量隔离、超时或清理协议。
- 相比参考补丁，launcher 增加了 `~` 展开。测试增加绝对、相对、用户目录三种路径、空格参数、子进程环境隔离和启动错误传播；没有创建 symlink 权限的平台仍运行这些可移植检查。
- 真实 symlink 测试在创建失败时明确 skip，报告原因。另新增 POSIX 真实 venv 测试：在仅该 venv 的 site-packages 写入标记模块，由真实 worker 加载并报告 `sys.prefix`，验证被选中的环境确实生效。测试不下载依赖；以临时 `.pth` 复用当前测试依赖目录，标记模块仍只存在于新 venv，避免嵌套 venv 继承规则造成误报。

修改文件：上述两个生产文件、`tests/test_remaining_launcher.py`、`tests/test_remaining_policy_transport.py`，以及本 response。

## 本次验证

执行目录为本任务独立 worktree。第一条为实际基础解释器命令；第二条将本机工作区前缀归一化为 worktree 相对路径，指向同一实际使用的仿真解释器。

```powershell
& 'C:/ProgramData/anaconda3/python.exe' -m pytest -q -rs tests/test_remaining_launcher.py tests/test_remaining_policy_transport.py
& '../../.runtime/remaining_libero/venv/Scripts/python.exe' -m pytest -q -rs tests/test_remaining_launcher.py tests/test_remaining_policy_transport.py
```

| 环境 | 结果 |
|---|---|
| Windows，基础 Python 3.12.7 | 34 passed，3 skipped |
| Windows，现有仿真环境 Python 3.10.0 | 34 passed，3 skipped |

三项 skip 分别是 launcher symlink、worker symlink（本机返回 `WinError 1314`，无创建权限），以及明确限 POSIX 的真实 venv/site-packages 集成测试。其余测试实际运行，包括真实 CPU worker 的 reset/predict/close、超时回收、异常退出和离线 rescore；没有加载 VLA 或 GPU。

`git diff --check` 通过。整合任务 001 后最终全套为 **982 passed，15 skipped（39.71s）**：11 项可选固定仿真源码未安装，3 项 Windows symlink 权限限制，1 项 POSIX 集成。POSIX 回归测试已纳入代码，本机没有可用的 WSL/Linux 运行环境，仍需在 Linux 运行，供 Codex 复核；不宣称 Linux 实装已通过。

## 安装兼容性与未做事项

任务交接已记录：pip 23 在仅使用 PyTorch CPU index 时曾发生依赖解析失败；先通过 PyPI 与 PyTorch CPU 双源安装明确的 `torch==2.2.0+cpu` 后继续成功。这是既有实装证据，本轮未重新安装或复测该网络路径。

本任务未修改 bootstrap。后续若单独修复安装器，应明确普通依赖来自 PyPI、CPU torch 来自 PyTorch CPU 源，并保留显式 CPU 版本和实际安装校验，避免误装 CUDA torch。该安装问题不因本次解释器修复而视为已解决。

等待 Codex 审查；X 不自行验收 Stage 01。
