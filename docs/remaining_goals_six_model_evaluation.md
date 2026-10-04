# LIBERO-Remain 六模型统一评测指南

更新日期：2026 年 10 月 4 日。

本项目研究：**当人或外部过程提前完成任意部分任务后，VLA 能否根据当前观测确定剩余目标，并保留已有成果？** 本文说明如何用同一批冻结状态、同一 rollout 和同一评分程序评测 OpenVLA、OpenVLA-OFT、π0、π0.5、GR00T N1.7 和 UniVLA。

LIBERO-Remain 是 Learning_Not_to_Act 项目的评测贡献。新名称与录像功能不改变已有候选的研究身份，也不表示已重建其状态。

## 仓库包含什么

本仓库提供六模型官方API适配器、独立模型worker、单模型与批量入口、状态构造/回放和统一计分。**模型权重、外部官方模型源码和已安装环境不随Git仓库分发。** 配置真实模型环境与权重后才能产生模型结果；已有官方复现环境可以接入，不需要为本仓库重新训练。

本项目尚未完成六模型真实权重推理或官方/新协议00回归，没有六模型成功率。适配器测试使用官方API替身，进程集成测试使用toy策略；均不能替代模型 `probe` 和正常能力回归。

当前十任务参考构造为3个官方初态来源、4种mask，共120个候选；实际构造覆盖与回放结果以目标机报告为准。自动状态保持 `construction.legal=false`。`--candidate-replay` 验证完整独立回放证据后允许candidate pilot，不把候选升级为正式发布集。重建与可选证据包见 [data/README.md](../data/README.md)，一键初始化见 [README](../README.md)。

本文以 **Linux x86_64、NVIDIA GPU、Bash** 为模型部署环境。Windows仿真兼容不等价于六模型支持Windows。若已有官方复现结果，优先复用对应环境和权重，填写其路径；无需为本项目重新训练六个模型。

## 文件与运行架构

| 文件 | 用途 |
|---|---|
| `benchmark/remaining_goals/evaluation.py` | `check`、`probe`、`run`、`matrix`、`summarize` 统一入口 |
| `benchmark/remaining_goals/adapters/` | 五个实现模块覆盖六模型，π0 与 π0.5 共用 OpenPI 模块 |
| `benchmark/remaining_goals/isolated_policy.py` | 仿真进程到模型 Python 进程的代理 |
| `benchmark/remaining_goals/policy_worker.py` | 在每个模型自己的依赖环境中加载官方模型 |
| `benchmark/remaining_goals/policy_transport.py` | 有长度限制的 JSON 与数值数组通信，不使用 pickle |
| `configs/remaining_goals/runtime/*.json` | 可以填写本机路径的运行配置 |
| `configs/remaining_goals/plans/libero10.example.json` | 六模型批量任务清单 |
| `scripts/remaining_libero.py` | 自动选用独立 LIBERO 环境的启动器 |
| `benchmark/remaining_goals/runner.py`、`metrics.py` | 模型共用 rollout 和离线评分 |

仿真环境只负责状态恢复、相机、控制与评价。每个模型 worker 使用自己的 Python、官方仓库与 checkpoint。π0/π0.5 可以共享一个 OpenPI 环境；OpenVLA、OFT、UniVLA 的 `prismatic` 模块和 transformers 版本不能装在同一个模型环境中。

模型只收到相机、机器人自身状态和原始完整指令；不会收到完成掩码、目标谓词、物体真值或“还剩哪个任务”的提示。动作接口统一为已经反归一化的 MuJoCo 7 维动作或 `(T,7)` chunk。worker 输出日志走 stderr，避免污染动作通信。

## 官方代码与应下载的权重

以下记录第一方源码commit和可核准的Hugging Face快照。OpenPI GCS URI不是已核验的不可变权重revision；下载后还需记录本地权重与归一化文件哈希。引用说明具体接口来源，不代表本项目已经运行权重。

| 模型 | 官方代码 | 用于本项目主轨的权重 | 特别注意 |
|---|---|---|---|
| OpenVLA | [openvla/openvla 固定版本](https://github.com/openvla/openvla/tree/c8f03f48af692657d3060c19588038c7220e9af9) | [openvla-7b-finetuned-libero-10 固定快照](https://huggingface.co/openvla/openvla-7b-finetuned-libero-10/tree/80970322773f81baa2e22fe495d0487b93a05cfa) | 不能用 Bridge 的通用 checkpoint 与归一化键冒充 LIBERO 基线 |
| OpenVLA-OFT | [moojink/openvla-oft 固定版本](https://github.com/moojink/openvla-oft/tree/e4287e94541f459edc4feabc4e181f537cd569a8) | [openvla-7b-oft-finetuned-libero-10 固定快照](https://huggingface.co/moojink/openvla-7b-oft-finetuned-libero-10/tree/95220f9a3421a7ff12d4218e73d09ade830fa9a3) | 需完整 action head、proprio projector 与 [官方 transformers fork](https://github.com/moojink/transformers-openvla-oft) |
| π0 | [Physical-Intelligence/openpi](https://github.com/Physical-Intelligence/openpi) | **填写你已经复现的 `pi0_libero` 微调 checkpoint** | 当前官方发布表未确认可直接下载的 π0 LIBERO 专用权重；`pi0_base` 仅是微调起点，不是替代品 |
| π0.5 | [Physical-Intelligence/openpi](https://github.com/Physical-Intelligence/openpi) | `gs://openpi-assets/checkpoints/pi05_libero`，见 [官方权重表](https://github.com/Physical-Intelligence/openpi#model-checkpoints) | 使用 `pi05_libero` 配置和 checkpoint 自带归一化资产 |
| GR00T N1.7 | [NVIDIA/Isaac-GR00T](https://github.com/NVIDIA/Isaac-GR00T) | [nvidia/GR00T-N1.7-LIBERO](https://huggingface.co/nvidia/GR00T-N1.7-LIBERO/tree/main) 的 `libero_10` 子目录 | 这里确实是 N1.7；需 `LIBERO_PANDA`，不能换成基础模型或 N1.6 |
| UniVLA | [OpenDriveLab/UniVLA](https://github.com/OpenDriveLab/UniVLA) | [univla-libero-10 固定快照目录](https://huggingface.co/qwbu/univla-7b-224-sft-libero/tree/0d1979ebd1b7ad00d6a8a02a98213a0835dc82a1/univla-libero-10) | 同时下载并指定目录内的 `action_decoder.pt`，仅 VLA 权重不够 |

π0 与 π0.5 的发布状态依据 [OpenPI 固定版本说明](https://github.com/Physical-Intelligence/openpi/blob/215abfb217dbac7d5f1273282331b9b1866c0479/README.md) 和 [训练配置](https://github.com/Physical-Intelligence/openpi/blob/215abfb217dbac7d5f1273282331b9b1866c0479/src/openpi/training/config.py)。这里区分“有训练配置”“有基础权重”和“已发布可用的 LIBERO 微调权重”，不会推测一个下载地址。

### 10 个任务为什么分两条轨

| 轨道 | 当前任务 | 状态数 | 权重与结果要求 |
|---|---|---:|---|
| 主轨 `libero_10` | basket、stove、basket_cheese_butter、basket_soup_cheese、dual_mugs、mug_pudding | 72 | 六模型先在各自合适的 LIBERO checkpoint 上对齐，是当前横向比较的重点 |
| 扩展轨 `libero_90` | frypan_stove3、frypan_stove9、cabinet_close_top_bowl、cabinet_close_bottom_open_top | 48 | 单独配置、归一化、回归与报告，不与主轨混算 |

本次没有确认六模型都发布了 LIBERO-90 专用权重。GR00T 官方目录只有 10、goal、object、spatial 四套；OpenVLA/OFT/UniVLA 的默认配置也不能自动把 10 的归一化用于 90。OpenPI 的公开 LIBERO 微调数据由四套任务合并，未列 90，见 [第一方数据说明](https://huggingface.co/datasets/physical-intelligence/libero)。

扩展轨可以研究两种不同问题：一是使用在 90 上单独微调的模型测剩余目标能力；二是固定已有模型测向 90 的迁移。后者必须标明 `zero_shot_extension` 或相应迁移身份，不能称为“官方 LIBERO90 复现”。“没在这份微调集里”也不证明预训练完全没有相似任务。当前 OpenPI 适配器只支持固定官方输入、动作与归一化配置；改变训练配置需相应验证或另写 adapter。

## 环境准备

### 共用目录与下载工具

以下命令均在本仓库根目录执行；matrix路径相对其JSON所在目录。建议先固定安装路径；冻结状态XML包含资产绝对路径，迁移目录后应重建状态。

```bash
mkdir -p external checkpoints reports data configs/remaining_goals/local
python -m pip install uv
uv tool install huggingface_hub
hf auth login
```

认证由你在终端完成，不把 token 写入运行 JSON 或日志。已有 Hugging Face CLI 时可以跳过安装。下载工具可独立于模型环境，避免为更新 CLI 改坏模型依赖。

### 独立仿真环境

项目安装器锁定 LIBERO commit `8f1084e3132a39270c3a13ebe37270a43ece2a01`，MuJoCo 2.3.7、robosuite 1.4.0、NumPy 1.26.4。其用途是构造和评测环境，不安装六模型权重。

```bash
python scripts/bootstrap_remaining_benchmark.py simulation \
  --python python3.10 --phase all \
  --out data/remaining_goals_local --reports reports/remaining_goals_local
```

安装器创建 `.runtime/remaining_libero/venv`，并写入 `runtime.json`。后续一律经启动器调用，不必手动拼 `PYTHONPATH` 或改用户的 `~/.libero` 配置。Linux 无显示器环境使用 EGL；doctor 必须在实际评测机器上通过。系统仍需可用的 OpenGL/EGL 驱动与常规编译工具，Python 包不能替代 NVIDIA 驱动。

上述命令包括目标机重建与回放。已有仿真环境、只需另建数据时可运行下面的命令；不能手改旧 `model_xml_sha256` 或fingerprint绕过校验：

```bash
python scripts/build_remaining_ten_tasks.py \
  --out data/remaining_goals_local \
  --reports reports/remaining_goals_local \
  --scenes 3 --start-index 0 --split val --workers 1
```

运行结束应检查 `collection_report.json` 中两套状态与回放均通过。目标机接下来使用 `data/remaining_goals_local/libero_10/manifest.candidates.json` 和 `reports/remaining_goals_local/libero_10/replay_report.json`；扩展轨把目录换为 `libero_90`。

下载的证据包或其他机器的回放记录不替代当前机器验证。上述两个构建流程是备选，不应在同一个已存在输出目录连续执行。

### OpenVLA 和 OFT

两者各建一个 Python 3.10 环境。OpenVLA 参考栈为 torch 2.2.0、torchvision 0.17.0、transformers 4.40.1、tokenizers 0.19.1、timm 0.9.10、flash-attn 2.5.5，见 [官方安装说明](https://github.com/openvla/openvla/blob/c8f03f48af692657d3060c19588038c7220e9af9/README.md#installation)。这些历史版本不保证兼容所有新GPU；RTX 50等新架构需核对CUDA二进制支持。优先使用已完成官方复现的硬件与依赖栈，记录必要修改并重新回归。

下面各块均在本项目根目录运行，不需要 `cd` 进入外部仓库。先完成上面的仿真安装；三模型的官方推理模块会导入 LIBERO 工具，因此模型环境也需要安装其 Python 包和 `libero_requirements.txt`，但不会在 worker 中创建仿真。模型环境中的 robosuite 1.4.1 是官方导入依赖，不会替换独立仿真环境中的 1.4.0。通过 `scripts/remaining_libero.py evaluate` 启动时，`probe` 和 `run` 均向 worker 继承已生成的 `LIBERO_CONFIG_PATH`，避免首次导入时交互式询问配置路径。

```bash
git clone https://github.com/openvla/openvla external/openvla
git -C external/openvla checkout c8f03f48af692657d3060c19588038c7220e9af9
conda create -n openvla python=3.10 -y
conda activate openvla
python -m pip install torch==2.2.0 torchvision==0.17.0 torchaudio==2.2.0 --index-url https://download.pytorch.org/whl/cu121
python -m pip install -e external/openvla
python -m pip install packaging ninja
python -m pip install flash-attn==2.5.5 --no-build-isolation
python -m pip install -r external/openvla/experiments/robot/libero/libero_requirements.txt
python -m pip install -e .runtime/remaining_libero/LIBERO-8f1084e3132a39270c3a13ebe37270a43ece2a01
python -m pip check
python -m pip freeze > reports/openvla_environment_resolved.txt

hf download openvla/openvla-7b-finetuned-libero-10 \
  --revision 80970322773f81baa2e22fe495d0487b93a05cfa \
  --local-dir checkpoints/openvla-libero-10
```

OFT 必须使用支持双向注意力的 [transformers-openvla-oft fork](https://github.com/moojink/transformers-openvla-oft)，普通 `transformers==4.40.1` 不等价。固定 OFT 仓库的 [pyproject.toml](https://github.com/moojink/openvla-oft/blob/e4287e94541f459edc4feabc4e181f537cd569a8/pyproject.toml) 已将该 fork 声明为 Git 依赖，下面的 editable install 会安装它。其 Git 依赖没有随 OFT commit 固定 revision，所以安装后检查并记录实际 fork commit；`pip freeze` 还会记录 dlimp 等 Git 依赖。这是参考安装配方，不是已经实装验证的完整依赖锁。

```bash
git clone https://github.com/moojink/openvla-oft external/openvla-oft
git -C external/openvla-oft checkout e4287e94541f459edc4feabc4e181f537cd569a8
conda create -n openvla-oft python=3.10 -y
conda activate openvla-oft
python -m pip install torch==2.2.0 torchvision==0.17.0 torchaudio==2.2.0 --index-url https://download.pytorch.org/whl/cu121
python -m pip install -e external/openvla-oft
python - <<'PY'
import importlib.metadata as metadata
import json
from pathlib import Path
distribution = metadata.distribution('transformers')
source = json.loads(distribution.read_text('direct_url.json') or '{}')
assert 'github.com/moojink/transformers-openvla-oft' in source.get('url', ''), source
assert len(source.get('vcs_info', {}).get('commit_id', '')) == 40, source
Path('reports/openvla_oft_transformers_source.json').write_text(
    json.dumps({'version': distribution.version, 'source': source}, indent=2) + '\n'
)
PY
python -m pip install packaging ninja
python -m pip install flash-attn==2.5.5 --no-build-isolation
python -m pip install -r external/openvla-oft/experiments/robot/libero/libero_requirements.txt
python -m pip install -e .runtime/remaining_libero/LIBERO-8f1084e3132a39270c3a13ebe37270a43ece2a01
python -m pip check
python -m pip freeze > reports/openvla_oft_environment_resolved.txt

hf download moojink/openvla-7b-oft-finetuned-libero-10 \
  --revision 95220f9a3421a7ff12d4218e73d09ade830fa9a3 \
  --local-dir checkpoints/openvla-oft-libero-10
```

不要只复制 safetensors：配置、统计量、processor、OFT action head 和 projector 都是 checkpoint 的组成部分。OFT 官方 loader 会同步 checkpoint 中的代码与配置；本适配器建立临时 checkpoint 视图，避免改写下载原件，并记录运行时元数据。

### π0 与 π0.5

使用固定 OpenPI 仓库自己的 `uv.lock`，无需装进 Python 3.10 的仿真环境。两者可以共享这一个模型 Python。官方安装与 LIBERO 说明：[OpenPI](https://github.com/Physical-Intelligence/openpi/blob/215abfb217dbac7d5f1273282331b9b1866c0479/README.md)、[LIBERO example](https://github.com/Physical-Intelligence/openpi/tree/215abfb217dbac7d5f1273282331b9b1866c0479/examples/libero)。

```bash
git clone --recurse-submodules https://github.com/Physical-Intelligence/openpi external/openpi
git -C external/openpi checkout 215abfb217dbac7d5f1273282331b9b1866c0479
git -C external/openpi submodule update --init --recursive
GIT_LFS_SKIP_SMUDGE=1 UV_LINK_MODE=copy uv sync --project external/openpi --python 3.11 --frozen
GIT_LFS_SKIP_SMUDGE=1 UV_LINK_MODE=copy uv pip install --python external/openpi/.venv/bin/python -e external/openpi
```

π0.5 的配置已给出官方 GCS URI，`create_trained_policy` 会通过官方下载器下载并使用 checkpoint 中的归一化资产。首次运行需要网络和足够磁盘；也可预下载，再把 `adapter_options.checkpoint` 改为本地目录。π0 的该字段有意留空：填你已经完成 `pi0_libero` 官方接口复现的微调权重，不能填 `pi0_base` 后声称是 LIBERO 专用模型。

模型输入为双图和 8 维机器人状态。官方 output transform 已完成动作反归一化，包含 π0 历史配置的额外 delta 逆变换；本项目不会再反归一化一次或重复翻转夹爪。当前显式采样噪声采用按 episode 重置的 NumPy 高斯序列，方便配对比较；它与官方默认 JAX RNG **不逐比特相同**，需要单列记录并做 00 回归。

先下载 π0.5、取得本地缓存路径，可以从项目根目录执行：

```bash
external/openpi/.venv/bin/python -c "from openpi.shared import download; print(download.maybe_download('gs://openpi-assets/checkpoints/pi05_libero'))"
```

OpenPI 用同一发布权重评测 90 时，必须显式填写 `adapter_options.evaluation_track="zero_shot_extension"`，同时把两处 suite 设为 `libero_90`。这个字段会进入模型运行元数据；不填会拒绝运行，防止把迁移试验误称为在 90 上训练的基线。

### GR00T N1.7

使用 [N1.7 固定版本 README](https://github.com/NVIDIA/Isaac-GR00T/blob/51d4c89f72fda44cbf77285c6a8114b52676b8a1/README.md) 对应的 dGPU 环境：Python 3.12，参考 CUDA 12.8。关键依赖以该 commit 的 `uv.lock` 为准，包括 torch 2.9.0、transformers 4.57.3、diffusers 0.35.1。torchcodec 对应 FFmpeg 4–7；不要直接安装 FFmpeg 8。需按官方页面申请 [Cosmos-Reason2-2B](https://huggingface.co/nvidia/Cosmos-Reason2-2B) 的访问权限。

```bash
git clone --recurse-submodules https://github.com/NVIDIA/Isaac-GR00T external/Isaac-GR00T
git -C external/Isaac-GR00T checkout 51d4c89f72fda44cbf77285c6a8114b52676b8a1
git -C external/Isaac-GR00T submodule update --init --recursive
uv sync --project external/Isaac-GR00T --python 3.12 --frozen
hf download nvidia/GR00T-N1.7-LIBERO \
  --revision 2ea293aa20ba7cf5bbf3ba17a5fbcb1a01cbfe21 \
  --include 'libero_10/*' \
  --local-dir checkpoints/GR00T-N1.7-LIBERO
```

配置 checkpoint 指向 `checkpoints/GR00T-N1.7-LIBERO/libero_10`。适配器验证 `Gr00tN1d7` 架构、LIBERO processor、action modality 和本地权重分片，调用官方 `Gr00tPolicy`。当前 LIBERO processor 的动作长度为 16，默认每次执行前 8 步；不要把基础模型配置中的 40 当作 LIBERO 实际 chunk。

### UniVLA

使用独立 Python 3.10 环境。官方实验说明采用 **torch 2.2.0 + CUDA 12.1**；下面显式安装配套 torchvision 0.17.0，所有 `python -m pip` 都在激活后的 `univla` 环境执行。其 [pyproject.toml](https://github.com/OpenDriveLab/UniVLA/blob/main/pyproject.toml) 固定 transformers 4.40.1、tokenizers 0.19.1、NumPy 1.26.4 等依赖；不要复用 OFT 的 transformers fork。运行需要 VLA 与 action decoder 两部分，见 [官方安装和 LIBERO 说明](https://github.com/OpenDriveLab/UniVLA#video_game-getting-started)。

上游同时固定了旧 setuptools 57.5.0；本配方选用 pip 24.0，保留旧 editable 安装兼容性，避免新版 pip 删除 `setup.py develop` 后与这套历史依赖冲突。这是安装层的兼容选择，不是声称官方实验使用了 pip 24.0；目标机仍需完成实际安装和 `probe`。[pip 变更说明](https://pip.pypa.io/en/stable/news/#v25-3)

```bash
git clone https://github.com/OpenDriveLab/UniVLA external/UniVLA
git -C external/UniVLA checkout 0ab9e9d
conda create -n univla python=3.10 -y
conda activate univla
python -m pip install pip==24.0
python -m pip install torch==2.2.0 torchvision==0.17.0 --index-url https://download.pytorch.org/whl/cu121
python -m pip install -e external/UniVLA
python -m pip install packaging ninja
python -m pip install flash-attn==2.5.5 --no-build-isolation
python -m pip install -r external/UniVLA/experiments/robot/libero/libero_requirements.txt
python -m pip install -e .runtime/remaining_libero/LIBERO-8f1084e3132a39270c3a13ebe37270a43ece2a01
python -m pip check
python -m pip freeze > reports/univla_environment_resolved.txt
git -C external/UniVLA rev-parse HEAD > reports/univla_source_commit.txt
hf download qwbu/univla-7b-224-sft-libero \
  --revision 0d1979ebd1b7ad00d6a8a02a98213a0835dc82a1 \
  --include 'univla-libero-10/*' \
  --local-dir checkpoints/univla-libero
```

checkpoint 路径为 `checkpoints/univla-libero/univla-libero-10`，`action_decoder_path` 指向其中的 `action_decoder.pt`。官方 latent 采样是随机的，温度 0.75、top-p 0.9；适配器保留该设置。window=12 时 decoder 在内部做时间聚合，每次给统一 runner 一条 7 维动作；每个 episode 都清空历史。

当前UniVLA配置固定 `0ab9e9d` commit前缀；安装后用上面的 `git rev-parse HEAD` 归档完整SHA，adapter验证前缀并记录实际HEAD。Hugging Face模型卡中的旧脚本名 `run_libero_eval_decoder.py` 不用于本适配器；实际调用官方仓库 `experiments/robot/libero/run_libero_eval.py` 的API。以上三套安装命令与GPU推理尚未在本项目完成实际验证。

## 填写运行配置

`configs/remaining_goals/runtime/` 是可执行运行配置。根层 `configs/remaining_goals/openvla.json` 等文件是研究归档元数据模板，不能混用。下面以OpenVLA为例，先复制配置再改为本机绝对路径：

```bash
cp configs/remaining_goals/runtime/openvla.json configs/remaining_goals/local/openvla.json
conda activate openvla
python - <<'PY'
import json, pathlib, sys
p = pathlib.Path('configs/remaining_goals/local/openvla.json')
c = json.loads(p.read_text())
c['runtime']['python_executable'] = sys.executable
c['runtime']['cuda_visible_devices'] = '0'
c['adapter_options']['repo_path'] = str(pathlib.Path('external/openvla').resolve())
c['adapter_options']['checkpoint'] = str(pathlib.Path('checkpoints/openvla-libero-10').resolve())
p.write_text(json.dumps(c, ensure_ascii=False, indent=2) + '\n')
PY
```

其余五个模型同样复制对应文件，并填写：

| 字段 | 要求 |
|---|---|
| `policy_id` | 明确模型、checkpoint、suite、实验设置；比较新设置时改名 |
| `policy_factory` | 保留示例中的真实 adapter factory |
| `suite` 与 `adapter_options.suite` | 与 manifest 一致，例如均为 `libero_10` |
| `runtime.python_executable` | 该模型环境中 `python -c 'import sys; print(sys.executable)'` 的结果 |
| `runtime.cuda_visible_devices` | 物理 GPU 编号；worker 中的 `cuda:0` 对应此处第一张可见卡 |
| `adapter_options.repo_path` | 对应固定 commit 的官方仓库绝对路径 |
| `adapter_options.checkpoint` | 微调权重完整本地目录；π0.5 也支持已给出的官方 GCS URI |
| `adapter_options.action_decoder_path` | UniVLA 必填 |
| `adapter_options.checkpoint_suite` | GR00T 必须明确与本次 suite 一致 |
| `execution.max_chunk_steps` | OpenVLA 1、OFT 8、π0 5、π0.5 5、GR00T 8、UniVLA 1 |
| `execution.random_seed` | 固定并归档；有 adapter 层 seed 字段时保持一致 |

这是“保持各模型参考执行频率”的主比较。所有模型强制每步重规划可以作为第二组实验，但会改变 OFT/flow 模型的使用方式，必须另命名并单独报告。`max_chunk_steps` 是执行上限，不会把单步模型的动作重复 8 次。

GPU 显存需求取决于模型、精度和 chunk；默认串行逐个加载与退出，一张合适的 GPU 即可按顺序跑六模型。多 GPU 并行需为每个作业指定互不重叠的 GPU，不能在同一张卡上默认同时加载六个大模型。

## 从配置检查到完整评测

### 1 配置检查

```bash
python scripts/remaining_libero.py evaluate check \
  --config configs/remaining_goals/local/openvla.json \
  --config configs/remaining_goals/local/openvla_oft.json \
  --config configs/remaining_goals/local/pi0.json \
  --config configs/remaining_goals/local/pi05.json \
  --config configs/remaining_goals/local/groot_n1_7.json \
  --config configs/remaining_goals/local/univla.json \
  --out reports/six_models_local_config_check.json
```

这一步不加载权重，`static_configuration_ready=true` 只说明静态路径和字段检查通过。它不是“模型已正确运行”。配置不完整会返回非零退出码，不会静默跳过模型。

### 2 对真实冻结观测做一次推理

```bash
python scripts/remaining_libero.py evaluate probe \
  --config configs/remaining_goals/local/openvla.json \
  --manifest data/remaining_goals_local/libero_10/manifest.candidates.json \
  --episode-index 0 \
  --out reports/openvla_inference_probe.json
```

`probe` 读取保存的真实双相机/机器人观测，启动模型 worker、reset、执行一次推理并检查有限 7 维动作，输出动作形状、耗时与环境信息。对其余配置重复此命令，使用不同输出文件。它不推进仿真、不计算成功率；首次下载/编译产生的延迟也不能直接用作稳定推理速度。

### 3 单模型 pilot

```bash
python scripts/remaining_libero.py evaluate run \
  --config configs/remaining_goals/local/openvla.json \
  --manifest data/remaining_goals_local/libero_10/manifest.candidates.json \
  --candidate-replay reports/remaining_goals_local/libero_10/replay_report.json \
  --out reports/eval_openvla_libero10_pilot_001 \
  --save-video --video-fps 20 --video-camera both --video-stride 1
```

每次使用新的输出目录；程序拒绝覆盖旧结果。该命令验证构造/回放证据后运行全部 72 个 episode，保持候选原始 `legal=false`。正式审定的 release manifest 用同一命令，去掉 `--candidate-replay`；默认正式 loader 仍拒绝未经审定的候选。

不要为了先跑通而手改 H/W、删除难例、只保留某种 mask 或改 legal 标志。需要小规模 smoke 时可在同一目标环境另构建 `--scenes 1` 的完整四掩码配对包，并完整回放验证；正式运行回到预先冻结的数据版本。

### 4 六模型批量运行

先把六份 local 配置全部填好。示例 matrix 的路径相对于 matrix JSON 所在目录；运行 JSON 内路径则建议全部用绝对路径。复制并检查示例清单中的 manifest、replay 和 config 路径：

```bash
cp configs/remaining_goals/plans/libero10.example.json configs/remaining_goals/plans/libero10.local.json
python scripts/remaining_libero.py evaluate matrix \
  --plan configs/remaining_goals/plans/libero10.local.json \
  --out reports/six_models_libero10_pilot_001 \
  --max-workers 1 \
  --save-video --video-fps 20 --video-camera both --video-stride 1
```

这是一条命令串行评测六模型。具备六张分别可运行这些模型的 GPU 时，可在六份配置中分别设 GPU 0–5，再把 `--max-workers` 设为 6。程序检查 GPU 是否重复，逐作业保存日志和结果；任一作业失败都会留有记录并使批量命令非零退出，不用其他模型的成功掩盖它。

要评测扩展轨，另建 matrix，使用 `libero_90` manifest 和 replay，为每个模型提供明确可用的 90 微调配置或显式迁移配置。当前示例不会虚构一份六模型通用的 LIBERO90 配置。

### 5 结果与离线重评分

每个运行目录包含：

- `run.json`：模型配置、解释器/依赖、源码与运行哈希、pilot 身份、回放证据、运行状态。
- `manifest.json`：实际评测 episode 清单，保留原始 legal 声明。
- `episodes/*.json`：逐步动作、目标真假、STOP 与异常，用于重算指标。
- `videos/000000.mp4` 等：启用录像时的episode视频；对应episode JSON记录路径与录像状态。
- `episodes.csv`：逐 episode 指标，含失败/缺失状态。
- `summary.json`：按任务与 mask 分组的成功率、主指标和覆盖率。

matrix 根目录另有 `matrix_plan.json`、`matrix_report.json` 和每模型日志。不同 suite 不合并成一个平均分。录像默认关闭，建议正式评测时使用上面的录像参数检查保持窗口与失败片段。`--video-camera` 可选 `agentview`、`wrist`、`both`；`--video-stride 1` 每控制步采集，`--video-fps 20` 设置播放帧率，增大stride但保持fps会快放。录像读取已有观测，不额外step/render、不改变策略输入或指标；episode失败时仅能保留实际采集的片段，不能补造后续行为。

运行记录保存 `video_config`；启用录像时，episode的 `video.status` 区分 `saved/video_error/empty`，并记录相对路径、帧数、相机、fps、stride和各帧物理步 `frame_steps`（成功保存时包含最后一步）。关闭录像以run的 `video_config.enabled=false` 为准，episode可以没有 `video` 字段。编码错误不覆盖策略的rollout状态或评分。LIBERO图像仅在录像副本旋转180°，策略输入保持原样；toy录像不旋转。

仿真环境已包含imageio及ffmpeg。使用执行toy评测的CPU解释器安装可选编码依赖（固定imageio2.34.2与imageio-ffmpeg0.5.1），再检查录像入口；无需改动模型独立GPU环境：

```bash
python -m pip install -e ".[video]"
python -m benchmark.remaining_goals.cli demo --out reports/video_smoke --scenes 1 --save-video
```

toy视频验证接口，不证明真实相机、GPU权重推理或模型能力。初始状态预览继续使用preview工具；MP4回看也不替代无损初态NPZ、逐步trace或语义/执行可行性审查。

```bash
python scripts/remaining_libero.py evaluate summarize \
  --run-dir reports/eval_openvla_libero10_pilot_001
```

重评分读取逐步 trace，不采信缓存的 `metrics`；也会检查 run/manifest/config 对应关系，避免混入其他模型或其他运行的 episode。

## Rollout 与评价指标

当前冻结包每个任务有两个子目标。三个“初态”指官方 `.pruned_init` 中索引 0、1、2 的三个场景来源，每个来源又构建四种完成状态：00 都未完成；10 仅第一个完成；01 仅第二个完成；11 均已完成。这不是只有三种完成状态。

当前每个候选配置 `H=520` 控制步，`W=150` 保持步。00/10/01 运行 `H+W=670` 步，11 只运行 W=150 步。实际预算始终读 manifest；不要把这个协议的分数称作原始 LIBERO 分数。控制步是仿真动作次数，不是模型查询次数或 wall-clock 秒。

评测从恢复的 t=0 状态直接开始；没有在恢复后额外做 10 步初始化动作，因为那会改变冻结初态。即使 LIBERO 返回 success/done，也继续运行到固定窗口结束，才能观察是否破坏成果。六个当前适配器均未伪造 STOP；若模型没有停止头，就持续调用它，而不是读取真值后替它停手。

| 指标 | 代码字段与精确定义 | 解释 |
|---|---|---|
| 联合成功 JSR | `joint_success`：截至 H（含 H，0…H）全任务至少成功一次，H…H+W 全部保持成功，且所有初始已完成目标在全程从未回退 | 主单 episode 结果 |
| 剩余目标成功 RSR | `remaining_success`：初始未完成的目标截至 H（含 H）同时达成，H…H+W 持续保持 | 11 没有剩余目标，记 null，不能记 100% |
| 已有成果保持率 PSR | `preservation_success`：所有初始已完成目标在整个窗口一直为真 | 00 没有已有成果，记 null |
| 目标回退率 | `goal_regression`：任一初始已完成目标曾变假 | 后来修复也算回退 |
| 回退步数 | `regression_steps`：至少一个初始已完成目标为假的观察步数 | 每步最多计 1 次，不按目标数累加 |
| 截止 H 的任务成功率 | `task_success_by_horizon`：0…H 中所有目标曾同时为真 | 较接近传统最终任务完成视角，但仍不是原版 LIBERO协议 |
| 稳定最终成功率 | `stable_final_success`：截止 H 成功且 H…H+W 始终满足全部目标 | 不额外要求早期已完成目标从不回退 |
| 首次全成功步 | `first_all_success_step` | 大于 H 的首次成功不会授予本轮成功 |
| 停止步 | `explicit_stop_step` | 当前六个无 STOP 适配器一般为 null；不能用零动作代替语义 STOP |
| 覆盖率 | `completed/expected` 及 errors/missing | 程序完成 rollout 不等于任务成功 |

11 的 JSR/保持评价要求 0…W 全部满足；没有“机器人不动”这一额外判据。只要不破坏成果，移动本身不是失败。

主报告字段 `partial_macro.valid_joint_success` 先在每个任务内等权平均 10/01，再对任务等权平均。`normal_00` 和 `terminal_11` 单列控制，不进入主指标。任一预期任务-mask 完全没有有效 episode，valid macro 为 null，不偷偷删掉那一组。

`conservative_joint_success` 把异常/缺失计入总分母，便于看覆盖问题；它不是“模型在有效状态上失败”的概率估计。`invalid_initial_state`、`runtime_error`、`missing` 要分别报告。指标暂未实现置信区间、配对检验、干扰动作分类或每步推理时延统计；这些不能从一个均值反推出。

## 如何验证模型结果可以比较

1. **官方接口回归**：先保存你已有的官方 LIBERO 复现结果、权重版本、预处理、动作映射与依赖信息。官方 00 是原始 protocol，不是本候选包的 00。
2. **新协议 00 控制**：同一 checkpoint 在本包的 00 上运行；成功率与官方结果差异可能来自初态、预算、继续执行和终止条件，不能直接都归因于剩余目标能力。
3. **配对 10/01**：对同任务、同官方初态来源比较 00 与两种部分完成状态；原始完整指令不变。不要把任务难度差异当成“先完成某个目标”的影响。
4. **11 控制**：检查所有目标已完成时是否保持成果。模型无 STOP 不应自动失败；破坏目标才体现在指标中。
5. **失败回看**：区分没有看到状态、重新执行已完成子任务、破坏后修复、剩余任务原本不可达、接口错误等。技术稳定的状态不自动证明语义可观察或剩余任务可执行。

建议先确认每模型 `probe` 和 00 正常，再解释 10/01/11 差异。当前每任务每 mask 只有 3 个来源，更适合现象验证；发表统计结果时应增加独立来源/任务与种子，使用以配对来源组或任务为单位的统计分析，不能把同一来源的四个 mask 当四个独立样本。

本代码保存运行配置和已安装包版本，但没有自动对数十 GB 的所有 checkpoint 字节计算并核验摘要。正式归档还应记录下载 revision、本地权重文件 SHA-256、归一化文件 SHA、官方回归报告和新协议 00 报告。原 `configs/remaining_goals/*.json` 及 `scripts/check_remaining_baseline_config.py` 用于此类研究元数据归档；静态元数据完整也不能替代真实回归。

## 常见问题

| 现象 | 检查方法 |
|---|---|
| `configuration is not ready` | 填完整本机解释器、仓库、checkpoint；π0 默认空权重是有意阻止误跑 |
| `fingerprint differs` 或 XML hash 不匹配 | 在当前机器/路径重建并回放；不能改哈希绕过 |
| 找不到 `prismatic` 或导入错版本 | 检查模型 Python 和对应 repo_path；OFT、OpenVLA、UniVLA 分环境 |
| OFT 动作不对或 loader 报错 | 确认官方 transformers fork、双图、proprio、action_head/projector 文件完整 |
| UniVLA 只下载了主权重 | 同时指定正确的 `action_decoder.pt`，不要跨 episode 保留历史 |
| π0/π0.5 夹爪反向或动作尺度不对 | 不在官方 output transform 后再次反归一化/翻夹爪；检查 checkpoint 的训练配置与资产 |
| GR00T 版本/embodiment 不匹配 | 下载 N1.7 LIBERO 权重，确保是 `libero_10` 子目录且 processor 有 `libero_sim` |
| 第一次启动超时 | 检查模型日志、下载、编译和 gated 权限；可提高 `startup_timeout_seconds`，不要把网络失败记为策略失败 |
| 显存不足 | 默认串行，检查是否仍有其他模型进程；修改精度/量化属于新实验设置，要另做 00 回归 |
| summary 的 valid macro 是 null | 检查缺失任务-mask、invalid state、runtime error，不能仅删错例再平均 |

所有安装配方均依据核对的官方版本编写；本次未在目标 Linux GPU 机器执行这些安装。最终可用性以你的实际环境中 `doctor → check → probe → 00 回归 → 配对评测` 的证据为准。
