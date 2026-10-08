# X 对任务 001 的交付：默认展示与独立人工 UIR

日期：2026-10-08。执行者：X。状态：submitted，等待 Codex 审查；不是 accepted/closed。

- 任务：[001_metrics_and_uir.md](../tasks/001_metrics_and_uir.md)。
- 基准提交：`467b6d9070cf30c86774f7099ba6ee104e76bc45`。
- 实现提交：[46d935b1b8e8109bbc840a2e4347ed520cdd4df7](https://github.com/No1dry/LIBERO-Remain/commit/46d935b1b8e8109bbc840a2e4347ed520cdd4df7)。该提交同时实现任务 002；任务 001 的文件范围列于下文。
- 分支：`x/stage01-metrics-uir-venv`。PR：创建后在此补充；不推送或合并 main。

## 修改内容

1. 新增 `benchmark/remaining_goals/reporting.py`：默认报告主表只有 Joint Success Rate / UIR，未标注为 N/A；task×mask 与 normal_00/partial_macro/terminal_11 分开。诊断表展示 remaining/preservation、first_all_success_step 的均值及有效样本数、expected/completed/invalid/runtime_error/missing，明确 completed 为 rollout 完整。
2. 新增 `benchmark/remaining_goals/uir.py`：独立人工标注模板、严格身份/类型/重复/证据校验、unknown/unannotated/ineligible 区分、双覆盖率和等权宏平均。任一预期 partial 格没有有效标签则 macro 为 null；不池化两套 suite。
3. `cli.py` 抽出只读 `read_run()` 与旧 schema 的 `_summarize_run()`。新增 `uir-template` / `report`，模板及派生报告要求源 run 外的全新路径。导入 UIR 不调用原地 rescore，不修改原 run/manifest/episode/trace/summary/CSV。保留旧 `rescore()` 接口和行为。
4. `evaluation.py` 复用相同命令。run/demo/summarize 默认展示简明表并保存 `report.md`。完整旧 JSON/CSV 字段保持；`metrics.py` 和指标定义无修改。
5. 新增 `tests/test_remaining_uir.py`、`tests/test_remaining_uir_cli.py`，更新 README 与两份原指南，新增[人工 UIR 指南](../../docs/remaining_goals_uir.md)。

true/false 都需要完整有效 rollout、完整人工审核声明、成功保存且含 0..N 每个物理步的录像及覆盖完整窗口的证据。v1 保守地拒绝用稀疏录像作正/负标签；可保留 null。身份绑定包括 run、manifest、episode 和生产结果身份字段。CLI 额外核对视频实际存在且 resolve 后仍在对应 run 中，并记录 SHA。JSON 重复键/非有限值拒绝；Windows 反斜杠会先统一规范化。

这些校验不能证明人工确实看完或必要性判断正确。未使用闭爪、动作、距离、接触或 STOP 自动生成真实标签。

## 实际验证

执行目录：本分支 checkout。`../../.runtime/remaining_libero/venv/Scripts/python.exe` 为本机已有 Python 3.10.0 仿真解释器的相对位置，不要求其他用户复制同一路径。

```powershell
& '../../.runtime/remaining_libero/venv/Scripts/python.exe' -m pytest tests -q -ra
& '../../.runtime/remaining_libero/venv/Scripts/python.exe' -m pytest -q tests/test_remaining_uir_cli.py
```

- 最终全套：**982 passed，15 skipped，39.71s**。11 项需要该独立 checkout 未安装的可选固定仿真源码；3 项因 Windows 无 symlink 权限；1 项明确限 POSIX 的真实 venv/site-packages 集成测试。没有失败，没有新跑 GPU。
- 最终 UIR CLI 定向测试：**22 passed**，含两个真实 CLI 子进程入口、整个源 run 文件哈希不变、旧分数与全部分子分母相同、N/A、身份错配、已有/内部输出拒绝、丢失或越界视频、重复键、非有限值与跨平台路径。
- UIR 纯模块及旧 metrics 定向测试：**113 passed**，含宏/池化差异、缺格、三目标 partial 分层、错误/unknown 分母和完整窗口拒绝。
- 旧 2026-10-03 toy run 的 8 个文件哈希前后完全一致，全部原有 summary 字段递归相等。新派生 summary 另含原旧版本没有的 `evaluation_kind`、`release_authorized`、`run_status` 三个非指标元数据字段；未改旧文件。
- 真实 FFmpeg CPU toy smoke：四个 MP4 解码帧数为 8/8/8/4。未标注模板 UIR macro=null；**synthetic** 标签示例的 partial UIR=0.5、旧 Joint Success=1.0；原 run 全树字节哈希不变。
- `git diff --check` 通过。实现复核发现并修复重复 JSON 字段与反斜杠路径两处边界问题；独立复核未给出 Codex 验收裁决。

本地 smoke 证据在用户研究项目的 `reports/libero_remain_stage01_x_20261008_a3/validation.json`、`historical_report/`、`toy_run/`、`template_report/`、`synthetic_report/`。两个先前检查尝试保留：第一次整份旧 summary 相等的断言遇到上述新增非指标字段；第二次 toy 没有 wrist 相机，因此请求 both 正确产生 video_error。最终使用 toy 实际提供的 agentview；未改生产代码绕过错误。

## 报告与模板示例

完整字段示例见[人工 UIR 指南](../../docs/remaining_goals_uir.md)。可复现的 CPU 命令如下（使用当前测试环境解释器）：

```bash
python -m benchmark.remaining_goals.cli demo --out reports/x_toy --scenes 1 --save-video --video-camera agentview
python -m benchmark.remaining_goals.evaluation uir-template --run-dir reports/x_toy/run --out annotations/x_toy.json --reviewer SYNTHETIC_TEST
python -m benchmark.remaining_goals.evaluation report --run-dir reports/x_toy/run --annotations annotations/x_toy.json --out reports/x_toy_unreviewed
```

上述模板仍全部为 null，默认主表 UIR 全为 N/A。验证用 synthetic 标签对 10 置 true、其余置 false 后的示例为：

| mask / stratum | Joint Success Rate | UIR（仅 synthetic 测试） |
|---|---:|---:|
| 00 | 1.0 | 0.0 |
| 10 | 1.0 | 1.0 |
| 01 | 1.0 | 0.0 |
| 11 | 1.0 | 0.0 |
| partial_macro | 1.0 | 0.5 |

这不是任何真实 VLA 录像的人工审核结果，不可作为模型能力结论。

## 未完成与审查入口

未开展真实人工标注、GPU rollout、训练或阶段关闭。当前机器无法运行 POSIX venv 集成测试；相关测试已交付，需 Linux 环境复核。bootstrap 的 pip 23 CPU 源兼容性未改，详见[任务 002 回应](002_round1.md)。Stage 00 所述 2026-10-06 OFT 证据路径在当前工作区不存在，因此本轮未冒充复核该真实运行，而是使用实际存在的历史 toy 与新 synthetic smoke。

请 Codex 审查实现、证据完整性和保守标注契约，逐项给出 review；X 后续按 review 回应。阶段总结、备份核验和验收由 Codex 决定。
