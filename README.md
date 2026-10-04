# LIBERO-PAB

**Partial-completion evaluation for vision-language-action models on LIBERO.** Given the original instruction and the current observation, can a VLA complete the remaining goals while preserving what has already been achieved?

LIBERO-PAB provides paired-state construction, independent simulator replay, a shared rollout and scoring interface, and adapters for OpenVLA, OpenVLA-OFT, π0, π0.5, GR00T N1.7 and UniVLA. It is an independent research project built on [LIBERO](https://github.com/Lifelong-Robot-Learning/LIBERO), not an official LIBERO release. Model weights and installed environments are not included.

本项目评测：**外部过程提前完成部分任务后，VLA 能否从当前观测选择剩余目标，并保留已有成果？** 模型始终收到原始完整指令，不收到完成掩码或仿真目标真值。

## 当前范围

| 内容 | 状态 |
|---|---|
| 任务 | 10 个双目标任务：LIBERO-10 主轨6个，LIBERO-90 扩展轨4个；分轨构建、运行和报告 |
| 配对状态 | 每来源构建 `00/10/01/11`；三个来源的参考规模为120个候选，两个suite各自保存 |
| 工程 | 状态构造、技术验收、重复回放、统一rollout、离线重评分、缺失/异常统计已实现 |
| 模型接口 | 六模型factory及独立Python worker已实现；权重、模型环境与实际00回归需配置 |
| 数据身份 | 自动输出仍为 `construction.legal=false` 的候选；技术稳定不认证语义、可见性或剩余可执行性 |
| 研究结果 | 没有六模型成功率；CPU测试和HOLD回放不能替代VLA评测 |

## 1. Clone 后运行 CPU smoke

需要 Python 3.10–3.12。下列命令创建仓库内 `.venv`，安装轻量依赖，再运行已知答案的toy策略和离线重评分，不下载LIBERO资产或模型权重。

```bash
git clone https://github.com/No1dry/LIBERO-PAB.git
cd LIBERO-PAB
python scripts/bootstrap_remaining_benchmark.py cpu --out reports/cpu_smoke
```

输出位于 `reports/cpu_smoke/`。这是接口、rollout和指标的smoke测试，不是机器人任务成功率。目录已存在时换一个新的 `--out`。

当前发布候选的代码测试为842 passed、1 skipped；这不包含六模型真实GPU权重推理。完整测试可另行运行：

```bash
.venv/bin/python -m pytest tests -q -ra
```

Windows 将解释器替换为 `.venv/Scripts/python.exe`。已有NumPy/PyYAML环境可用 `cpu --skip-install --python /path/to/python --out reports/cpu_smoke_002`；此模式不安装依赖。推荐从clone的源码使用editable安装，wheel本身不包含任务配置、文档和仿真资产。

## 2. 一键初始化仿真并重建候选

需要可用的 **Python 3.10**、网络和OpenGL驱动；Linux无显示器环境默认EGL，Windows使用GLFW。安装器会创建独立仿真环境，下载固定版本CPU PyTorch与LIBERO资源，执行doctor，再构建两轨候选并各重复回放两次。它不安装VLA模型。

```bash
python scripts/bootstrap_remaining_benchmark.py simulation \
  --python python3.10 --phase all \
  --out data/remaining_goals_local \
  --reports reports/remaining_goals_local
```

`--python` 接受命令名或解释器完整路径。Windows PowerShell 可在单行输入同一命令并提供Python3.10路径。默认每任务3个官方初态来源，完整覆盖应为72个主轨候选和48个扩展轨候选；构造失败会记录原因，不能把请求数量当成实际通过数量。

检查 `reports/remaining_goals_local/collection_report.json` 和 `preview.html`。两条轨道都通过才构成完整技术验收。每个状态仍为候选，不能直接宣称正式研究数据已发布。

- 仅安装：`simulation --python python3.10 --phase setup`。
- 已安装环境做检查：`simulation --phase doctor`。
- 已安装环境重建：`simulation --phase build --out data/new_candidates --reports reports/new_candidates`。
- `--workers 2` 可并行两个suite，需足够内存与渲染资源；默认1。
- 普通依赖索引可通过 `--index-url` 或 `PIP_INDEX_URL` 选择；CPU PyTorch使用其官方专用索引。

初态XML身份包含资源绝对路径，复制预构建状态到新机器通常不能直接复用。应在最终安装路径重建，不能改指纹绕过校验。预构建证据的边界见 [data/README.md](data/README.md)。

## 3. 接入已有权重并运行模型

按[六模型指南](docs/remaining_goals_six_model_evaluation.md)建立或复用各模型自己的环境。将 [`configs/remaining_goals/runtime/`](configs/remaining_goals/runtime/) 中的配置复制到 `configs/remaining_goals/local/`，填写解释器、官方源码和真实checkpoint路径。π0需要提供已复现的LIBERO微调权重；不会自动替换为基础模型。

以已填写的OpenVLA配置为例：

```bash
python scripts/remaining_libero.py evaluate check \
  --config configs/remaining_goals/local/openvla.json
python scripts/remaining_libero.py evaluate probe \
  --config configs/remaining_goals/local/openvla.json \
  --manifest data/remaining_goals_local/libero_10/manifest.candidates.json \
  --episode-index 0 --out reports/openvla_probe.json
python scripts/remaining_libero.py evaluate run \
  --config configs/remaining_goals/local/openvla.json \
  --manifest data/remaining_goals_local/libero_10/manifest.candidates.json \
  --candidate-replay reports/remaining_goals_local/libero_10/replay_report.json \
  --out reports/openvla_pilot
```

`check`只做静态检查；`probe`做一次真实模型推理但不推进仿真；`run --candidate-replay`是明确标记的候选pilot。解释partial结果前，还需保存官方原接口00与本协议00回归。

填好全部六份local配置后，可用一条matrix命令串行运行：

```bash
cp configs/remaining_goals/plans/libero10.example.json configs/remaining_goals/plans/libero10.local.json
python scripts/remaining_libero.py evaluate matrix \
  --plan configs/remaining_goals/plans/libero10.local.json \
  --out reports/six_model_pilot --max-workers 1
```

扩展轨需要独立配置和结果。没有保证六个模型都有官方LIBERO-90权重；OpenPI使用同一四套微调权重时必须显式标记 `zero_shot_extension`，不能冒称90训练基线。

## 文档与数据

- [完整协议、状态构造与计分](docs/remaining_goals_benchmark.md)
- [六模型安装、权重来源与统一命令](docs/remaining_goals_six_model_evaluation.md)
- [运行配置与研究元数据的区别](configs/remaining_goals/README.md)
- [候选数据、可选证据包与重建](data/README.md)
- [Releases](https://github.com/No1dry/LIBERO-PAB/releases)：如有发布附件，以该版本实际文件清单为准；clone不自动下载附件。

源码、外部模型、LIBERO及其资产可能采用不同许可。请遵守对应上游许可与模型卡；本README不替第三方授予许可，也不把模型权重视为本仓库的一部分。
