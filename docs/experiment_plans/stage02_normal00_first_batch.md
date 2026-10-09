# 给 DeepSeek：Stage 02 首批 normal-00 回归

决策者/审查者：Codex。代码实现：X。机械执行：DeepSeek。
状态：代码验收后授权；必须先由 X 合并 PR #2、登记 main SHA，再按该版本执行。
代码实现 commit 为 `3a50f635b5eb7329386b381879ce53dab3bfbd46`。

## 0. 范围与禁止变更

模型：同一份官方 SOG10 OFT，snapshot `638918f3d1c2e43a39a8a20772bdb8b91835e4b7`。
任务：basket。policy seed7。协议：official/remain。正式indices：0、1、2、3、4，不换失败初态。
允许填写 local JSON 中的真实路径，不修改源码、预算、指标、checkpoint或已安装环境。
不下载新模型、不训练、不跑partial状态或全部任务。出现代码问题记录并交回Codex/X。

## 1. 使用独立干净代码目录

不要 reset/覆盖之前带 smoke 补丁的 checkout。新建目录、克隆已合并 main并记录SHA；
确认包含任务003代码。冻结后不要在实验中pull。
如果 main 相比已审实现存在源码、scripts、tests、tracked configs的额外变化，暂停让Codex核对。

```bash
git -c http.version=HTTP/1.1 clone --branch main --single-branch \
  https://github.com/No1dry/LIBERO-Remain.git LIBERO-Remain-normal00-stage02
cd LIBERO-Remain-normal00-stage02
git rev-parse HEAD
git merge-base --is-ancestor 3a50f635b5eb7329386b381879ce53dab3bfbd46 HEAD
git diff --exit-code 3a50f635b5eb7329386b381879ce53dab3bfbd46 HEAD -- benchmark scripts tests configs
```

复用现有独立simulation runtime，不重装：在新checkout创建 `.runtime/remaining_libero`
符号链接，目标为原已验证安装的完整runtime目录。不要覆盖已有链接/目录。
实际服务器原目录为 `/HUBU-AI004/zp/benchmarks/LIBERO-Remain/.runtime/remaining_libero`。

```bash
mkdir -p .runtime
ln -s /HUBU-AI004/zp/benchmarks/LIBERO-Remain/.runtime/remaining_libero .runtime/remaining_libero
mkdir -p configs/remaining_goals/local
cp configs/remaining_goals/runtime/openvla_oft_sog10.json configs/remaining_goals/local/openvla_oft.json
```

local配置填写并保存：

| 字段 | 当前已验收服务器路径 |
|---|---|
| runtime.python_executable | `/HUBU-AI004/zp/benchmarks/LIBERO-Remain/.runtime/oft_worker/bin/python` |
| runtime.official_libero_config_path（新增字段） | `/HUBU-AI004/zp/benchmarks/LIBERO-Remain/.runtime/remaining_libero/libero_config` |
| adapter_options.repo_path | `/HUBU-AI004/lgm/openvla-oft` |
| adapter_options.checkpoint | `/HUBU-AI004/zp/ICML/checkpoints/openvla-7b-oft-libero-sog10` |

保持原示例中的SOG10来源/revision、OFT revision、seed7、chunk8、center_crop和精度选项。
local配置没有凭据。若机器路径与上述不符，使用已有经过验收的真实路径并记录。
运行launcher可使用 `/root/miniconda3/envs/vla_lgm/bin/python`，它会按runtime选择simulation解释器。
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
若录像失败或技术条件不满足，保留产物并暂停，不自行修代码。

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
