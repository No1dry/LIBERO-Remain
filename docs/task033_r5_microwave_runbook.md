# 033 R5：只补微波炉10初态

本轮源码固定为 `fc2dd617b9434a82d27710d1da023101e87af1f5`，对应 [PR #14](https://github.com/No1dry/LIBERO-Remain/pull/14)。下面的部署和真实准备命令是交付内容，**X未执行**；由Codex审查并隔离部署后，用户启动必要真实准备。不修改原 `aedfe169` 或 `06817e61` 部署，不升级依赖。

## 范围与方法

原R3新三任务30来源中20 ready、微波炉10 failed。抽屉10、双壶10及其原证书只读复用，旧六任务和九任务00均不重跑。此入口不生成新30来源plan，不加载策略，不启动部分20评测；用户选择30来源齐备后一次评新增30条10，正式90分母和旧六60条模型记录保留。

显式方法为 `microwave_gravity_support_pose_transplant_v3`，只允许 `nine-mask10/mug_microwave_close/index0..9`，强制v6。用真实底板有限顶面、原In容积及杯子全部39个collision box构造直立种子，按基底yaw、+90°、−90°、180°轮转；每种姿态重新计算底高、完整footprint和墙/门余量。不是把门关闭后摆放，B和机器人不改。候选只改变A的7个qpos，所有基底qvel保留；真实HOLD后移植实际A的xyz、quat、qvel。

不改碰撞资产、margin、摩擦、阻尼、solver及官方In/Open/Close。不增加24候选和每候选400 HOLD上限；base80、候选min80、连续20合格、qvel0.01、位置/穿透/机器人、150构造和两次独立150回放保持原要求。v6的RGB及非RGB规则也不变。

## 绑定的旧输入

入口直接验证原字节hash和20/10分组，不需要用户手写hash或重建计划：

| 输入 | 固定位置及SHA256 |
|---|---|
| 原报告 | `/HUBU-AI096/zp/ICML/task033_r3_06817e61/preparation/preparation_report.json`；`195c8a38c8bb8f4683cf0a4d3925348b5f08e64941621b3379a0ffec57a61f04` |
| 原sources | 同目录 `sources.json`；`3454ee8a1a776f357a05511c98e12bd9e8c63aba548a0db9f6eb8a32aec6369e` |

全部20复用来源先经文件reader检查，包括引用的manifest、回放及RGB证书。缺少旧证据、字节变化或不匹配时停止，不把它们转成待重建。新输出不能与原报告、来源或证书目录重叠。原R3失败报告不改，新输出保存两个原文件的逐字节副本及各来源的原记录。

## Codex审查后：新目录隔离部署（bash）

下列代码位置必须尚不存在。使用新clone，不操作冻结部署内的源码；此命令不启动仿真。

```bash
R5_COMMIT=fc2dd617b9434a82d27710d1da023101e87af1f5
R5_CODE=/HUBU-AI096/zp/ICML/LIBERO-Remain-task033-r5-fc2dd617
git clone --no-checkout --single-branch --branch x/task033-r2-sources \
  https://github.com/No1dry/LIBERO-Remain.git "$R5_CODE"
git -C "$R5_CODE" checkout --detach "$R5_COMMIT"
test "$(git -C "$R5_CODE" rev-parse HEAD)" = "$R5_COMMIT"
```

沿用原已跑通的仿真venv，保留venv路径，不把符号链接解析成底层conda解释器；不使用selector环境。

```bash
source /HUBU-AI096/zp/ICML/LIBERO-Remain-normal00-stage02/.runtime/remaining_libero/venv/bin/activate
R5_CODE=/HUBU-AI096/zp/ICML/LIBERO-Remain-task033-r5-fc2dd617
R5_RUN_ROOT=/HUBU-AI096/zp/ICML/task033_r5_fc2dd617
R3_PREP=/HUBU-AI096/zp/ICML/task033_r3_06817e61/preparation
cd "$R5_CODE"
export PYTHONPATH="$R5_CODE"
export LIBERO_CONFIG_PATH=/HUBU-AI096/zp/ICML/LIBERO-Remain-normal00-stage02/.runtime/remaining_libero/libero_config
export MUJOCO_GL=egl PYOPENGL_PLATFORM=egl
mkdir -p "$R5_RUN_ROOT/logs"
set -o pipefail
```

## 用户启动：先index0，ready后才继续1..9

```bash
python -u -m benchmark.remaining_goals.headless.repair033_microwave prepare \
  --inventory "$R3_PREP/sources.json" \
  --preparation-report "$R3_PREP/preparation_report.json" \
  --out "$R5_RUN_ROOT/microwave_repair" \
  2>&1 | tee -a "$R5_RUN_ROOT/logs/microwave_prepare.console.log"
R5_PIPESTATUS=("${PIPESTATUS[@]}")
printf 'prepare_exit=%s tee_exit=%s\n' "${R5_PIPESTATUS[0]}" "${R5_PIPESTATUS[1]}"
```

首次执行不要提前创建 `microwave_repair`，也不要加 `--continue`。入口先派发固定index0，这就是本批十条中的第一条，不是额外probe。只有构造和成对回放均被reader认可、状态真正ready，才顺序派发1..9；首条构造或回放失败即停止，另外9条保持 `not_attempted`。失败退出2不是VLA失败或模型成功率0%。输入不合法会抛出错误且不进入native。

入口复用 `selected_preparation` 的原操作账本，没有另建物理执行框架。所有新的native调用都只能属于微波炉，不会执行旧20、旧六、00。各候选实际HOLD读数、失败及真实控制次数按原机制落盘；抛异常/中断保留unknown，不按预算填成已执行值。

## 续跑边界

只有需要继续同一输出里尚未执行的工作时，保留相同输入和输出，显式运行：

```bash
python -u -m benchmark.remaining_goals.headless.repair033_microwave prepare \
  --inventory "$R3_PREP/sources.json" \
  --preparation-report "$R3_PREP/preparation_report.json" \
  --out "$R5_RUN_ROOT/microwave_repair" --continue \
  2>&1 | tee -a "$R5_RUN_ROOT/logs/microwave_prepare.console.log"
R5_PIPESTATUS=("${PIPESTATUS[@]}")
printf 'prepare_exit=%s tee_exit=%s\n' "${R5_PIPESTATUS[0]}" "${R5_PIPESTATUS[1]}"
```

已失败或记录为running/中断的操作不会自动重试。首0失败或派发后缺子报告时，其余9仍不派发；缺报告保留 `interrupted/unknown`。首0已ready时，后续某条中断不会重跑该条，但续跑可以继续此前没有派发的索引。若构造已保存、回放从未尝试，原worker可只补回放。已经ready的证据丢失只允许恢复原文件，不隐式补建。

需要新的物理尝试时，先交回失败/中断证据审查，再指定另一个新输出目录；不要删报告、手改状态或换索引假装首次尝试。普通 `--continue` 不是重试开关。本入口没有 `--allow-failed-retry`、`--allow-missing` 或模型评测选项。

## 交回文件及只读进度

- `microwave_repair/microwave_repair_report.json`：全部30来源，区分原20复用和微波炉本轮状态；`original`保留原记录，顶层计数/operations是本轮工作。
- `microwave_repair/sources.json`：完整90条expected及组合引用；旧20及证书原样保留，旧六引用不改，只替换本轮实际得到的微波炉来源。
- `microwave_repair/preparation/preparation_report.json`：现有worker的微波炉操作账本。
- `microwave_repair/preparation/attempts/mug_microwave_close/source_XX/attempt_XXX/`：新构造、回放及相邻control ledger，含失败证据。
- `microwave_repair/original_preparation_report.json`、`original_sources.json`：原字节副本；日志在上面的 `logs`。

单次只读进度，不创建仿真：

```bash
python -c 'import json; from pathlib import Path; p=Path("/HUBU-AI096/zp/ICML/task033_r5_fc2dd617/microwave_repair/microwave_repair_report.json"); d=json.loads(p.read_text()); print(d["counts"]); print("stopped_after_source0=", d["stopped_after_source0"])'
```

只有真实报告与reader确认 `ready: 30` 后，Codex再给一次新增30条10的单独模型命令；本入口不会串联模型。新工件保持冻结 `06817e61` v6 reader的格式契约，不要求热改reader。CPU/fake兼容性通过不代表微波炉真实10条已经ready。
