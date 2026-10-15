# Stage04 / 008 两来源域运行手册

2026-10-15，X候选交付。依据[008任务](../collaboration/tasks/008_finish_data_source_domains.md)及[修订Plan4](experiment_plans/stage04_finish_protocol.md)。本手册替代新实验使用的旧统一source分组流程；FINISH控制协议仍为v1。代码验收后由Codex部署新冻结SHA、填写并核对服务器配置，再由用户逐阶段启动真实作业。本文不表示这些真实阶段已经执行。

## 1. 固定范围和身份

只使用basket、原SOG10 OFT和既定小型finish head。H520/W150/chunk8、seed7、相机/crop、完整原指令、动作解码、控制与评分不变。已完成的4f版单11四步预检不重复；原38失败和4f成功证据保留。数据域变更不证明W150、其他状态的release或模型停止能力已通过。

| 域 | 固定角色／成员 | 用途 |
|---|---|---|
| `head_demonstration` | `head_train`：demo_5..34，30条 | 头梯度、train-only pos_weight |
| 同上 | `head_validation`：demo_35..39，5条 | 普通BCE选epoch；32不同输入parity |
| 同上 | `head_unused`：demo_0..4和demo_40..49，15条 | 必要文件检查，不恢复、不拟合 |
| `official_initial_state` | `normal_calibration`：init35..39，5条 | 普通00 shadow first-hit阈值校准 |
| 同上 | `normal_test`：init40..49，10条 | 独立普通00 active |
| 同上 | `remain_test`：init0..4 | 既有source001的10/01/11，共15条 |

HDF键为`hdf:{实际文件SHA}:demo_N`，eval键为`init:{实际文件SHA}:N`。**demo_35与init35没有同源映射声明**。新profile明确`ancestry_independence=unproven`：只能保证整轨迹分组、不直接使用编辑评测输入训练头及已检查的直接重复隔离，不能声称HDF与eval的物理祖源独立，也不声称冻结SOG10从未见过eval来源。

新audit/cache/head/job/calibration使用显式v2数据身份；FINISH协议、输入特征与物理标签合同不改。新job绑定同一registry/profile及head和阈值身份，不接受旧v1头、旧normal-bank或旧阈值混入。旧v1读取和默认旧协议仍供历史兼容，旧命令见[历史手册](finish_v1_runbook.md)，不能把旧source_index自动解释为新域键。

## 2. 资产与环境：复用，不重新采集

Codex负责下载／文件准备／路径和SHA核验；用户不需要重新下载已核HDF或手工猜配置。复用原仿真与OFT模型venv，不升级依赖或替换checkpoint。仿真侧需要既有NumPy、h5py和安全CPU初态loader；模型侧使用已有PyTorch与OFT依赖。新代码没有安装后自动执行入口。

| 资产 | 已核身份／位置 |
|---|---|
| 官方basket HDF | revision `147fa5eb607bb696dd922c3518084a90954cd2f3`；SHA `3173ebc709b064683956b757ae8737909457d730aa305b23c5735292e59066af` |
| official init文件 | SHA `1899fe54c51e24a41d5f9e32254730d6777f4894ab68e0e873f1fa7ae2062030`，50个向量 |
| 固定basket BDDL | SHA `2e661058917f683a25bce480015197f0a2c1911bcbc2b9dd9d947199069c9618` |
| HDF服务器文件 | `/HUBU-AI096/zp/ICML/stage04_finish_38e6a44/assets/libero_10/LIVING_ROOM_SCENE2_put_both_the_alphabet_soup_and_the_tomato_sauce_in_the_basket_demo.hdf5` |
| 原sim Python | `/HUBU-AI096/zp/ICML/LIBERO-Remain-normal00-stage02/.runtime/remaining_libero/venv/bin/python`；保留venv symlink选择 |
| LIBERO/init/BDDL | 仍用上述stage02的固定`.runtime`；Codex从有效配置核对确切路径 |
| model Python与runtime | 沿用已验收OFT私有配置；不得另改crop、seed、chunk、权重或源码版本 |
| Remain | 沿用source001及已通过的独立replay；旧bank不重建、不升级为正式发布bank |

配置同时声明`expected_assets`的三项SHA；registry实际读取并复算文件，不只相信配置字符串。缺group、缺index、SHA变化、重叠成员或类别不足均不能自动换组。HDF unused的编号不能作为Remain来源留出的证明。

历史示范XML还可能引用作者机器上的`/home/yifengz/workspace/libero-dev/chiliocosm/assets/`。本实现把这个明确别名及官方robosuite/libero资源路径，按完整相对suffix映射到当前固定安装包的assets根；不会按文件名搜索或使用旧机器路径碰巧存在的文件。根内`scenes/../textures`可规范化，根外路径、symlink逃逸、歧义、缺文件和未知依赖均报告失败。只修改送入仿真的内存XML中的资源file属性；原HDF/XML字节、几何、相机、纹理参数和mesh缩放保留。不需要建立作者/home目录或下载替代素材。

## 3. Codex部署后填写的会话与配置

以下是实现支持的Linux Bash候选命令。`REPO/CFG/OUT/LOG`必须是新008目录；Codex验收部署后填写实际SHA和全部路径，不能直接把含`/ABS/`的模板当成已部署命令。所有命令cwd为`$REPO`。

```bash
REPO=/ABS/NEW_ACCEPTED_TASK008_CHECKOUT
SIM_PY=/HUBU-AI096/zp/ICML/LIBERO-Remain-normal00-stage02/.runtime/remaining_libero/venv/bin/python
MODEL_PY=/ABS/EXISTING_OFT_VENV/bin/python
CFG=/ABS/NEW_PRIVATE_CONFIG/task008
OUT=/ABS/NEW_RESULTS/task008_run01
LOG=/ABS/NEW_LOGS/task008_run01
cd "$REPO"
mkdir -p "$CFG" "$OUT" "$LOG"
set -o pipefail
"$SIM_PY" -m benchmark.remaining_goals.finish.cli --help
```

| 私有配置 | 需要绑定的内容 |
|---|---|
| `data.json` | [data模板](../configs/remaining_goals/finish/data.example.json)：两域完整固定profile、expected_assets、三个实际路径、原指令、stride8 |
| `oft_sog10.json` | 原已冻结runtime，模型解释器／源码／checkpoint保持；Codex记录文件SHA |
| `validation_shadow.json` | [模板](../configs/remaining_goals/finish/validation_shadow.example.json)：新registry、normal-bank、head、同runtime；purpose名称保留，角色为normal_calibration |
| `normal_active.json` | [模板](../configs/remaining_goals/finish/normal_active.example.json)：同registry/head/runtime、新bank和冻结calibration |
| `remain_active.json` | [模板](../configs/remaining_goals/finish/remain_active.example.json)：同registry/head/runtime/calibration、旧source001/replay |
| `remain_shadow.json` | [模板](../configs/remaining_goals/finish/remain_shadow.example.json)：同registry/head/runtime、旧source001/replay；额外15条，默认不运行 |

四个job都使用`remaining-finish-job-v2`和`source_registry`路径（本流程为`$OUT/registry/registry.json`）；不要填旧`split`或`trajectory_source_map`。normal-bank路径为`$OUT/normal_bank/normal_bank.json`，head为`$OUT/train/head`，阈值为`$OUT/calibration/calibration.json`。路径替换由Codex准备，不能把两个validation混用。

可在会话中定义下面的单阶段日志函数；定义不会运行任何实验。每次显式调用只执行一个CLI阶段，保留完整命令、UTC及command/tee两种退出码，拒绝覆盖日志。

```bash
finish_stage() {
  local tag="$1" interpreter="$2"
  shift 2
  local logfile="$LOG/$tag.log"
  (set -o noclobber; : > "$logfile") || return 2
  {
    printf 'UTC: '; date -u '+%Y-%m-%dT%H:%M:%SZ'
    printf 'cwd: %s\ncommand: ' "$PWD"
    printf '%q ' "$interpreter" -m benchmark.remaining_goals.finish.cli "$@"
    printf '\n'
  } >> "$logfile"
  "$interpreter" -m benchmark.remaining_goals.finish.cli "$@" 2>&1 | tee -a "$logfile"
  local codes=("${PIPESTATUS[@]}")
  printf 'command_exit=%s tee_exit=%s\n' "${codes[0]}" "${codes[1]}" | tee -a "$logfile"
  (( codes[0] == 0 && codes[1] == 0 ))
}
```

每个`--out`须全新；中断后保留partial，先审查再决定新的输出目录，不自动resume、重跑或串联。以下各代码块是独立阶段，不是一次粘贴运行的批处理。

## 4. 纯文件计划、预算、registry

这些入口不创建环境、不恢复状态、不加载VLA或生成标签，可由Codex完成。

```bash
finish_stage 00_budget "$SIM_PY" budget-plan
finish_stage 01_data_plan "$SIM_PY" plan-data --config "$CFG/data.json" --out "$OUT/data_plan"
finish_stage 02_registry "$SIM_PY" register-data --config "$CFG/data.json" --out "$OUT/registry"
```

预算仍为5+10+15=30条模型rollout，最坏20100物理步。标签恢复/K4、特征、normal准备和parity64forward另计；没有新增VLA采集预算。registry检查真实HDF states/XML、group、采样frame、全部head组直接重复state和eval init身份，来源schema/profile不因资源重定位改变，**file-only始终不能ready_for_feature_export**。

`register-data`还生成`xml_asset_scan.json`及`registration.json`。扫描全部50条实际HDF XML（含unused），记录resolver版本、批准根、原XML及SHA、每条old→new/目标SHA、覆盖和聚合未解析项；不创建环境，也不导入真实仿真或模型包。成功时registration为`registered_file_only`、scan为`resolved`；缺失/未知/越界等问题保存在清单，registration为`insufficient`、命令exit2。检查两域coverage、文件SHA、固定成员、registry/profile hash和祖源unproven，并确认扫描覆盖50条、未解析0后，才交用户启动audit。历史路径的实际库存见[008 XML资源记录](stage_summaries/evidence/stage04_task008_xml_assets_2026-10-15.json)：4450次引用、87个唯一原路径，其中24个旧别名；该库存是诊断证据，正式扫描以当前代码和实际文件为准。

## 5. 用户真实audit：先检查数据充分性

```bash
finish_stage 03_audit "$SIM_PY" audit-data --config "$CFG/data.json" --out "$OUT/audit"
```

audit在创建provider前再次用同一resolver扫描全部50条XML；有未解析项时保存扫描与insufficient报告，不进入恢复。通过后只恢复head_train/head_validation按stride8加最后state采样的行，使用actual XML和固定任务。先保存当前合法观测，再从同状态做必要K4被动保持，之后恢复原状态；不恢复unused/eval来补覆盖。源HDF字节不变。

`audit.json`嵌入该资源扫描，audit SHA继续绑定cache/head的数据身份。运行时处理XML、审计结束以及后续验证audit时核对资源快照，资源文件变化不能静默复用旧审计。当前v2审计缺少这份完整扫描会被拒绝；旧v1历史读取保留。纯文件扫描通过只证明声明的本地依赖可解析，不证明与不可访问的作者旧机器资产逐字节相同，也不保证后续物理layout、release或标签充分性检查通过。

查看`audit/audit.json`：必须`status=ready_for_feature_export`、无关键issues、两组已知0和1均有覆盖，并核实restore/hold计数、unknown原因、source/row身份及两域registry。当前不满目标或明确夹持为0；全满、released=True且同状态K4稳定为1；缺证据为unknown。最后帧、未来示范动作和时钟不构成标签。fake审计通过不代表真实标签数据充分。若不足，停在此阶段交Codex分析，不挑样本换组，不自动训练。

## 6. 用户特征导出、小头训练

```bash
finish_stage 04_features "$SIM_PY" export-features --audit "$OUT/audit" --runtime-config "$CFG/oft_sog10.json" --out "$OUT/features"
```

检查`features/feature_export.json`完成、`features/cache/cache.json`绑定本audit/profile/registry及实际base/code/raw/input/feature身份。只导出head_train/head_validation的已知标签；metadata不进入网络，每输入沿原同一次forward取56个action-token的均值特征。

```bash
finish_stage 05_train "$MODEL_PY" train --cache "$OUT/features/cache" --training-config "$REPO/configs/remaining_goals/finish/train.json" --out "$OUT/train"
```

检查`train/training.json`完成及`train/head/head.json`、`head.npz`。CPU训练只更新既定小头，pos_weight只用head_train，epoch仅按head_validation普通BCE最小、同分最早。原AdamW/MLP/超参数不变。不借unused、normal_calibration、normal_test或Remain补类别或选择。效果不好按研究结果处理，不自动调参。

## 7. 用户normal-bank准备与32输入parity

```bash
finish_stage 06_normal_bank "$SIM_PY" prepare-normal --source-registry "$OUT/registry/registry.json" --indices 35 36 37 38 39 40 41 42 43 44 45 46 47 48 49 --out "$OUT/normal_bank"
```

检查`normal_bank/normal_bank.json`为prepared、15个固定index、实际init SHA和每个原始official state摘要、各preparation与savedstate/XML/BDDL绑定。保持已有80步settle和150步初态稳定检查的准备协议。新bank显式v2；不能直接换成旧bank绕过registry。此步骤没有VLA采集，也不重建source001。

旧source001的edited savedstate不等于raw official init。新job验证其原有index、savedstate、modelXML、BDDL、preparation/source及replay绑定，再与registry实际eval键关联；不会为旧包补造不存在的原始采集provenance。

```bash
finish_stage 07_parity "$SIM_PY" parity --audit "$OUT/audit" --runtime-config "$CFG/oft_sog10.json" --head-artifact "$OUT/train/head" --atol 0 --rtol 0 --out "$OUT/parity"
```

32不同输入只来自HDF head_validation；state、raw observation、模型输入均去重。不足32就报不足，不能从其他组借。每输入原/只读shadow各一次forward，同worker恢复Python/NumPy/Torch/CUDA RNG；保留预先声明的容差，不看结果再放宽。检查parity报告passed及32pairs/64forward；此命令不创建仿真。

## 8. 五条normal_calibration shadow与冻结阈值

```bash
finish_stage 08_shadow_plan "$SIM_PY" dry-plan --config "$CFG/validation_shadow.json" --out "$OUT/validation_shadow_plan"
```

确认固定eval init35..39共5条，purpose为validation_shadow、角色为normal_calibration；head_validation只用于先前BCE/parity。dry-plan必须核head/profile/registry/runtime/source绑定。

```bash
finish_stage 09_calibration_shadow "$SIM_PY" run --config "$CFG/validation_shadow.json" --out "$OUT/validation_shadow"
```

检查`run.json`、raw、evidence、视频与summary。shadow不应用head的FINISH，新主指标N/A，执行至H后真实W保持。异常保留partial和固定missing，不能把技术失败算模型0%。

```bash
finish_stage 10_calibrate "$SIM_PY" calibrate --run "$OUT/validation_shadow" --out "$OUT/calibration"
```

纯文件first-hit复算：固定五条分母、零提前约束、24步及时率、原候选网格与同分规则不变。必须检查`calibration/calibration.json`是否建立能力以及eval域/角色/成员、profile、head绑定；零FINISH或及时率0不能假通过。能力未建立时先分析，不使用test改阈值或拿shadow未来任务动作证明active保持。

## 9. 独立normal active与Remain active

```bash
finish_stage 11_normal_plan "$SIM_PY" dry-plan --config "$CFG/normal_active.json" --out "$OUT/normal_active_plan"
```

确认仅init40..49共10条、同head与冻结阈值；此后用户独立启动：

```bash
finish_stage 12_normal_active "$SIM_PY" run --config "$CFG/normal_active.json" --out "$OUT/normal_active"
```

检查完成能力、提前停止、24步及时停止、保持合规与unknown/technical覆盖。不能据此反调训练／阈值；90%/10%只作小样本pilot解释，不是代码验收条件。

```bash
finish_stage 13_remain_plan "$SIM_PY" dry-plan --config "$CFG/remain_active.json" --out "$OUT/remain_active_plan"
```

确认固定init0..4×10/01/11=15条、source001/replay和统一520/150/8；此后用户独立启动：

```bash
finish_stage 14_remain_active "$SIM_PY" run --config "$CFG/remain_active.json" --out "$OUT/remain_active"
```

主项仍为合规FINISH成功率n/N及百分比；保留初始成果、退出时完成/释放、退出保持、禁止投放及多标签失败。视频保存当前观测，不额外render/reset/step。先验证证据再解释分数，不能混入旧JSR/UIR成绩。

## 10. 可选shadow、离线复核与错误处理

仅用户另行决定额外15条时使用，默认30条预算不包含此阶段：

```bash
finish_stage 15_optional_shadow_plan "$SIM_PY" dry-plan --config "$CFG/remain_shadow.json" --out "$OUT/remain_shadow_plan"
finish_stage 16_optional_shadow "$SIM_PY" run --config "$CFG/remain_shadow.json" --out "$OUT/remain_shadow"
```

读已有产物的命令不运行仿真或模型；K=1/4/8必须各写新目录，不改变默认K4结论来救分：

```bash
finish_stage 17_inspect "$SIM_PY" inspect --run "$OUT/remain_active"
finish_stage 18_rescore_k1 "$SIM_PY" rescore --run "$OUT/remain_active" --stable-steps 1 --out "$OUT/remain_rescore_k1"
finish_stage 19_rescore_k4 "$SIM_PY" rescore --run "$OUT/remain_active" --stable-steps 4 --out "$OUT/remain_rescore_k4"
finish_stage 20_rescore_k8 "$SIM_PY" rescore --run "$OUT/remain_active" --stable-steps 8 --out "$OUT/remain_rescore_k8"
```

CLI正常完成退出0；insufficient、technical/error、parity失败或能力未建立退出2；中断路径按产物status和退出130检查。日志还须tee_exit=0。读取阶段不能把缺失episode删掉缩分母。任何SHA/profile/domain/role/label或source错配均拒绝；修正配置后由Codex核验新身份、用户决定新目录重跑，不原地改产物。

该设计不新增采集、不保证真实audit类别充分或head有用。数据域、分组、GT、label、frame/time只作metadata；不会进入head输入，也不增加在线predict/reset/step。007与008的代码验收及Stage04科学结论分别记录，不自动closed。
