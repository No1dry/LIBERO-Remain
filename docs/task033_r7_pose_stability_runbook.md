# 033 R7：A杯子位姿稳定准入与仅微波炉补建

对应 [033 R7已确认工单](../collaboration/tasks/033_round7_pose_stability_revision.md) 和 [PR #14](https://github.com/No1dry/LIBERO-Remain/pull/14)。实现版本：`c8c50e639b01802382b2bdfee73f0f946e8c465a`。本文件提供交付命令，不是执行日志；**X没有运行以下部署或真实制备命令**。Codex审查后隔离部署，用户亲自启动必要真实步骤。

## 版本与准入边界

新物理规则显式为 `stability_profile=active-free-object-pose-stability-v7`；RGB继续独立的 `observation_profile=named-uint8-rgb-one-level-v6`。新audit schema为 `remaining-goals-validation-v2-active-pose`。初次范围仅nine-mask10/mug_microwave_close、A杯子white_yellow_mug_1、官方index0..9。构造method仍使用R5 `microwave_gravity_support_pose_transplant_v3`，几何候选不变。

| 项目 | R7要求 |
|---|---|
| A位置稳定 | 完整150控制步、151观测；全窗位置bbox对角线跨度≤0.005m |
| A姿态稳定 | 同一完整窗口；归一化四元数最大两两最短旋转≤1°，使用abs(dot)，q与−q等价 |
| A瞬时广义速度 | 全部原值照实保存，记录每观测最大分量越界比例及峰值；不单独拒绝，不清零/裁剪/替换 |
| 非A速度 | 所有其余qvel分量仍≤0.01，包含机器人、门和其他物体 |
| 其他物理条件 | 全场景原位置稳定、机器人/reference≤2mm、穿透≤2mm、native10/Open及其他保持谓词不变 |
| 观察对应 | RGB v6不变；构造/reset初始非RGB精确、动态非RGB原1e-8，非步进state精确及原hash要求保持 |
| 正式窗口 | 150构造、两次分别恢复的150回放；三份完整151点证据，不可用static0或settle尾部代替 |
| 预算 | base80、最多24候选、每候选min80/max400 HOLD；前置20观测改用同一A位姿规则，非A及其它检查保留 |

广义速度含不同关节的原生单位，不把所有分量统一表述为m/s或rad/s。位置/角度窗口是已批准的来源准入操作定义，不宣称证明可达性或任务可执行性。

这是在来源准备观察到瞬时速度与位姿稳定性不一致后作出的**事后测量修订**，须在新增30条模型评测前固定版本并披露。不是按VLA成功/失败挑来源。原R5末150采样点只有149控制间隔且缺完整state/contact，不能离线拼成正式认证；所有旧failed/raw按原结果保留。

## 证据及reader

每个新准入窗口保留完整raw state/qvel、A原pose、全joint映射与layout、模型XML hash、原谓词、接触深度、观察比较和诊断。映射来自实际编译模型，构造/正式恢复再次核对；不能把任意坐标当A豁免速度检查。A pose及qvel必须对应raw state切片。

生产、回放及reader显式核对manifest/episode/audit/report的profile和mapping；缺151点、缺第二回放、映射不符、非A超速、姿态/位置/谓词/接触/机器人/观察失败均拒绝。static0只能决定是否进入完整150构造，不能独立授予technical acceptance。

R7来源用**新隔离checkout的reader**读取、归档和后续配置；冻结06817e61不支持新audit schema，不能宣称它能读R7，更不能修改其目录或把v7标成v6。新reader仍读取旧v4/v6来源及旧RGB证书，旧20按各自原profile复用；不声称它们通过了新增A姿态检查。RGB证书不能用来授权/重算R7物理规则。

## 固定输入

选择复用R3的原20/10清单，同时额外绑定实际R5失败报告，避免重做30来源计划：

| 输入 | SHA256 |
|---|---|
| `/HUBU-AI096/zp/ICML/task033_r3_06817e61/preparation/preparation_report.json` | `195c8a38c8bb8f4683cf0a4d3925348b5f08e64941621b3379a0ffec57a61f04` |
| 同目录 `sources.json` | `3454ee8a1a776f357a05511c98e12bd9e8c63aba548a0db9f6eb8a32aec6369e` |
| `/HUBU-AI096/zp/ICML/task033_r5_942db12f/microwave_repair/microwave_repair_report.json` | `d0ca805413e78cd9fbfee212b1d8b66f93d802f90969f37ad3b0dbd9193b4fcb` |

入口自动核对这些字节hash、R5真实20ready/1failed/9not_attempted、旧20引用一致性及现有文件reader证据。缺失/变化停止，不降级成重建旧20。R5的source0失败、其余9未尝试及实际控制账本保存在原报告；R7是新输出里的新版本尝试，不修改原状态。

## 审查后隔离部署（bash，不启动仿真）

新代码目录必须尚不存在。使用新clone，不在aedfe169/06817e61/942db12f冻结目录内checkout、pull或修改文件。

```bash
R7_COMMIT=c8c50e639b01802382b2bdfee73f0f946e8c465a
R7_CODE=/HUBU-AI096/zp/ICML/LIBERO-Remain-task033-r7-c8c50e63
git clone --no-checkout --single-branch --branch x/task033-r2-sources \
  https://github.com/No1dry/LIBERO-Remain.git "$R7_CODE"
git -C "$R7_CODE" checkout --detach "$R7_COMMIT"
test "$(git -C "$R7_CODE" rev-parse HEAD)" = "$R7_COMMIT"
```

使用原已跑通的仿真venv，不升级依赖、不改模型环境，也不把venv符号链接解析成底层conda Python：

```bash
source /HUBU-AI096/zp/ICML/LIBERO-Remain-normal00-stage02/.runtime/remaining_libero/venv/bin/activate
R7_CODE=/HUBU-AI096/zp/ICML/LIBERO-Remain-task033-r7-c8c50e63
R7_RUN_ROOT=/HUBU-AI096/zp/ICML/task033_r7_c8c50e63
R3_PREP=/HUBU-AI096/zp/ICML/task033_r3_06817e61/preparation
R5_REPORT=/HUBU-AI096/zp/ICML/task033_r5_942db12f/microwave_repair/microwave_repair_report.json
cd "$R7_CODE"
export PYTHONPATH="$R7_CODE"
export LIBERO_CONFIG_PATH=/HUBU-AI096/zp/ICML/LIBERO-Remain-normal00-stage02/.runtime/remaining_libero/libero_config
export MUJOCO_GL=egl PYOPENGL_PLATFORM=egl
mkdir -p "$R7_RUN_ROOT/logs"
set -o pipefail
```

## 用户启动必要真实步骤

```bash
python -u -m benchmark.remaining_goals.headless.repair033_pose_stability prepare \
  --inventory "$R3_PREP/sources.json" \
  --preparation-report "$R3_PREP/preparation_report.json" \
  --revision-report "$R5_REPORT" \
  --out "$R7_RUN_ROOT/microwave_repair" \
  2>&1 | tee -a "$R7_RUN_ROOT/logs/microwave_pose_prepare.console.log"
R7_PIPESTATUS=("${PIPESTATUS[@]}")
printf 'prepare_exit=%s tee_exit=%s\n' "${R7_PIPESTATUS[0]}" "${R7_PIPESTATUS[1]}"
```

首次不要预建 `microwave_repair` 或加continue。新CLI固定物理v7、RGB v6、R5 method，复用现有selected_preparation和首0门控；不会重新构造抽屉/双壶或任何旧通过来源。0号是本批十条中的第一条，不是额外probe；只有它通过完整构造与两次回放、reader确认ready，才继续1..9。若失败立即停止其余9条并保留not_attempted。退出0仅表示新30来源全部ready；退出2表示仍有来源缺口，不是模型成功率0%。非法/缺失输入直接报错，不派发native。

## 续跑与新尝试边界

仅继续同一输出里的未尝试工作时使用相同三个输入和输出：

```bash
python -u -m benchmark.remaining_goals.headless.repair033_pose_stability prepare \
  --inventory "$R3_PREP/sources.json" \
  --preparation-report "$R3_PREP/preparation_report.json" \
  --revision-report "$R5_REPORT" \
  --out "$R7_RUN_ROOT/microwave_repair" --continue \
  2>&1 | tee -a "$R7_RUN_ROOT/logs/microwave_pose_prepare.console.log"
R7_PIPESTATUS=("${PIPESTATUS[@]}")
printf 'prepare_exit=%s tee_exit=%s\n' "${R7_PIPESTATUS[0]}" "${R7_PIPESTATUS[1]}"
```

continue绑定profile、原R3输入和R5修订前证据，不在旧R5目录retry。已经failed/running/中断的操作不自动重做；缺子报告保持interrupted/unknown。0号未ready时另外9条继续停；0号ready后可继续后续尚未尝试部分。构造完成但回放尚未尝试时，原worker可只补回放。已ready证据丢失仅恢复原文件，不隐式重建。

若仍失败或中断，保留全部证据交回审查；新物理尝试需要另一个新输出，不能删除报告或改状态重试。不要增加候选、延长400步或进一步改阈值；本CLI没有allow-failed-retry、allow-missing或自动模型run。

## 输出与交回

- `microwave_repair_report.json`：完整30来源状态、独立stability_profile、三个原输入身份；旧20为reuse_only，原记录放在original，不将它们说成v7测量。
- `sources.json`：90条expected及混合版本的原/新引用；旧六和原20、证书保持，替换实际得到的新微波炉工件。
- `original_sources.json`、`original_preparation_report.json`、`pre_revision_report.json`：三个原输入的逐字节副本。
- `preparation/preparation_report.json`：复用worker的操作账本及profile。
- `preparation/attempts/mug_microwave_close/source_XX/attempt_XXX/`：新构造/回放审计和相邻control ledger；完整raw在构造settle samples及正式audit trace中，失败同样保存。

单次只读状态（不创建仿真）：

```bash
python -c 'import json; from pathlib import Path; p=Path("/HUBU-AI096/zp/ICML/task033_r7_c8c50e63/microwave_repair/microwave_repair_report.json"); d=json.loads(p.read_text()); print(d["counts"]); print(d["stability_profile"]); print("stopped_after_source0=", d["stopped_after_source0"])'
```

正式新30来源齐备后，Codex在新reader版本下检查组合来源，再交用户一次新增30条10的模型评测命令。原OpenVLA-OFT SOG10/输入/环境/计分不变，物理GT只用于来源准入/评分，不进入策略。旧六60条10、00九任务90和旧20来源均复用；不启动部分20、不更换固定index、不引入FINISH/selector、不自动评测或合并。
