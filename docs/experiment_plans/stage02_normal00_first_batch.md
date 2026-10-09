# Codex 执行：Stage 02 首批 normal-00 回归

决策者、实验执行与审查者：Codex。代码实现：X。
修订：2026-10-09，用户移交原执行职责，并确认 X 看过审查、可以推进实验。
服务器修订：用户随后切换至端口30369的新主机，工作目录 `/HUBU-AI096/zp/ICML`；实际GPU为A100 80GB。新目录初始为空，需要先迁移相同资产、安装独立环境并复核。凭据不写入文档。旧4090结果不与本批混合。
状态：代码 accepted，可在独立目录冻结已审查 PR 提交 `6e29f110b56a18ade63f401a1b6d8376fa9f95ba` 后执行，不再因待合并阻塞本批。X 仍负责合并 PR #2、登记 main SHA。原“先合并”要求由本次冻结方式替代，其他实验闸门、预算和范围不变；不得声称此提交已是 main。
代码实现 commit 为 `3a50f635b5eb7329386b381879ce53dab3bfbd46`。

## 0. 范围与禁止变更

模型：同一份官方 SOG10 OFT，snapshot `638918f3d1c2e43a39a8a20772bdb8b91835e4b7`。
任务：basket。policy seed7。协议：official/remain。正式indices：0、1、2、3、4，不换失败初态。
允许填写 local JSON 中的真实路径，不修改源码、预算、指标、checkpoint或已安装环境。
不下载新模型、不训练、不跑partial状态或全部任务。出现代码问题记录并暂停受影响实验，由Codex给X发修复任务。

## 1. 使用独立干净代码目录

不要 reset/覆盖之前带 smoke 补丁的 checkout。新建目录、克隆并冻结已审查提交，记录SHA；
确认包含任务003代码。冻结后不要在实验中pull。
如果冻结提交相比已审实现存在源码、scripts、tests、tracked configs的额外变化，暂停核对。后续main合并只登记，不在本批中pull或换版本。

```bash
git -c http.version=HTTP/1.1 clone --branch x/task003-normal00-regression --single-branch \
  https://github.com/No1dry/LIBERO-Remain.git LIBERO-Remain-normal00-stage02
cd LIBERO-Remain-normal00-stage02
git checkout --detach 6e29f110b56a18ade63f401a1b6d8376fa9f95ba
git rev-parse HEAD
git merge-base --is-ancestor 3a50f635b5eb7329386b381879ce53dab3bfbd46 HEAD
git diff --exit-code 3a50f635b5eb7329386b381879ce53dab3bfbd46 HEAD -- benchmark scripts tests configs
```

当前新checkout绝对路径为 `/HUBU-AI096/zp/ICML/LIBERO-Remain-normal00-stage02`。代码也可由本地已审查Git bundle离线克隆；HEAD与源码diff核对要求相同。
新机没有旧runtime，不能创建指向旧机器路径的链接。先迁移旧机器已验证LIBERO源码/cache，在新checkout运行现有 `scripts/setup_remaining_libero.py --full` 重新核对Git blobs并创建独立venv，依赖沿用安装器固定版本；不改已有共享conda环境。
model Python建立独立system-site-packages overlay，复用现有torch2.4.1+cu121及固定OFT transformers；核对native robosuite1.4.1，使用与旧模型环境相同的numpy1.24.4/MuJoCo2.3.7等关键版本。新机Python补丁版本及其他差异进入日志。
旧SOG10 checkpoint迁移到新工作目录；全量文件SHA-256与源目录比对后才允许加载，不能替换为新机其他微调模型。OFT源码及已有tracked patch迁移到本项目独立 `external/openvla-oft`，记录commit与patch hash，不修改新机其他人的OFT目录。

```bash
mkdir -p configs/remaining_goals/local
cp configs/remaining_goals/runtime/openvla_oft_sog10.json configs/remaining_goals/local/openvla_oft.json
```

local配置填写并保存：

| 字段 | 当前已验收服务器路径 |
|---|---|
| runtime.python_executable | `/HUBU-AI096/zp/ICML/LIBERO-Remain-normal00-stage02/.runtime/oft_worker/bin/python` |
| runtime.official_libero_config_path（新增字段） | `/HUBU-AI096/zp/ICML/LIBERO-Remain-normal00-stage02/.runtime/remaining_libero/libero_config` |
| adapter_options.repo_path | `/HUBU-AI096/zp/ICML/external/openvla-oft` |
| adapter_options.checkpoint | `/HUBU-AI096/zp/ICML/checkpoints/openvla-7b-oft-libero-sog10` |

保持原示例中的SOG10来源/revision、OFT revision、seed7、chunk8、center_crop和精度选项。
local配置没有凭据。若机器路径与上述不符，使用已有经过验收的真实路径并记录。
运行launcher可使用 `/root/anaconda3/envs/peft-openvla/bin/python`，它会按runtime选择simulation解释器。
运行前确认GPU无其他作业；长作业存完整stdout/stderr、PID、起止时间、返回码。

## 2. 先做index0的两条技术smoke

先dry-run，不加载模型，检查计划恰为2条、official10wait/H520、Remain80settle/150audit/H520/W150。
输出路径都必须全新；下面名字已存在就使用新后缀。

```bash
python scripts/remaining_libero.py regression \
  --config configs/remaining_goals/local/openvla_oft.json \
  --task basket --indices 0 --protocol both \
  --out reports/normal00_smoke_001 --dry-run \
  --plan-out reports/normal00_smoke_plan_001.json \
  --save-video --video-camera both --video-stride 1 --video-fps 20
```

实际smoke：

```bash
python scripts/remaining_libero.py regression \
  --config configs/remaining_goals/local/openvla_oft.json \
  --task basket --indices 0 --protocol both \
  --out reports/normal00_smoke_001 --case-timeout-seconds 2400 \
  --save-video --video-camera both --video-stride 1 --video-fps 20
```

技术通过条件：两条完整执行，无准备/加载/运行错误；模型身份与norm key正确；
step0均为00，预算/等待/恢复符合计划；step0 NPZ、首动作、trace和两条视频齐全。
official策略步数1..520且结束理由正确；Remain恰为670步。
任务失败、success=False不使技术smoke失败，不能据此换seed。
若录像失败或技术条件不满足，保留产物并暂停；Codex核对原因，由X修代码，不在冻结运行目录临时改实现。

## 3. 技术通过后执行正式5+5，不再等一次文字许可

先生成10条计划并核对正式固定indices。

```bash
python scripts/remaining_libero.py regression \
  --config configs/remaining_goals/local/openvla_oft.json \
  --task basket --indices 0 1 2 3 4 --protocol both \
  --out reports/normal00_formal_001 --dry-run \
  --plan-out reports/normal00_formal_plan_001.json \
  --save-video --video-camera both --video-stride 1 --video-fps 20

python scripts/remaining_libero.py regression \
  --config configs/remaining_goals/local/openvla_oft.json \
  --task basket --indices 0 1 2 3 4 --protocol both \
  --out reports/normal00_formal_001 --case-timeout-seconds 2400 \
  --save-video --video-camera both --video-stride 1 --video-fps 20
```

smoke重复的index0不进入正式10条分母；它只是独立技术检查，不当新增独立样本。
正式错误不替换、不删除，按固定expected5+5报告；遇到共享接口故障可暂停并保留missing。

最坏正式预算：5950策略动作、50官方wait、1150 Remain准备/审计，最多745次查询、10次加载。
此处没有保证墙钟；以实际日志和每条elapsed更新估算。smoke2条费用单列。

## 4. 交付后暂停

新建 `execute_logs/stage02_normal00/`，交付summary、命令日志、manifest/代码/权重身份、
实际两个环境版本、step0与首动作、全部case结果/视频路径、异常及missing清单。

主表每个index各列official/remain的common_success；另列official native success与
Remain task_success_by_horizon/stable/joint，不能拿两种native SR当同一定义。
逐协议保存expected/attempted/prepared/policy_started/completed/errors/missing及精确分子分母。
记录实际来源文件/选中state hash，不预设两个warmup后的起点相同。

结束后停止，不扩task/checkpoint、训练或partial。本轮只回答正常能力与协议敏感性；
5个来源是pilot，统计解释与下一步裁决由Codex负责。
