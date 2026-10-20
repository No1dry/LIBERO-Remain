# 010：版本化释放测量与停止校准运行手册

本手册对应[010任务](../collaboration/tasks/010_versioned_release_and_calibration.md)。这是观察旧pilot之后明确注册的新科学合同：在原保守释放测量上补充完整collision集合的轴向分离证书，再按first-hit与完成时机不确定区间校准。CPU/fake测试通过仅证明软件契约；真实阶段由用户逐项启动。

原5条shadow及其`calibrated=false`、`selected_threshold=null`保持原样。009的init35前292步重放只提供了具体几何诊断，不能代替新5条完整正式校准，也不能补造旧轨迹的新版标签。

## 固定范围与预算

| 阶段 | 来源与数量 | 本轮用途 |
|---|---|---|
| 已完成旧shadow | init35..39，5条 | 探索／发现测量问题；不改结果 |
| 新版shadow | 同一init35..39，新增5条 | 新测量与新规则的正式校准开发 |
| normal active | init40..49，10条 | 冻结阈值后的独立停止验证 |
| Remain active | init0..4 × 10/01/11，15条 | 保留已有成果与完成剩余目标 |
| 累计 | **35条，最坏23450物理步** | 每条上限H520＋W150；不是新增35条 |

原30条计划和旧run不重写。新增5条最坏3350步；audit、features、parity、状态准备及已完成292步诊断另计。本轮不追加Remain shadow，不借normal_test或Remain挑方法、阈值或头。

继续使用已冻结SOG10 OFT/base、LoRA、action与两个projector、原finish head权重、runtime/crop/seed7。head仍按原v1训练标签合同训练；**不重做audit、features、训练、parity或normal-bank**。H520、W150、chunk8、K4（4个区间／5次观测）、24步及时窗口、20个候选阈值及20Hz均保持。

新observer仅接收evaluator侧数据。policy/head输入仍是原图像、8维proprio与原指令，56个action-token特征和8×7动作路径保持；几何、GT、版本、step、source角色均不得进入网络，也不得据此控制FINISH或开爪。

## 释放补充与判定边界

v1顺序保留：双pad抓持为False，其他gripper接触为None，原球与pinch间隙均严格大于2mm为True。v2仅补充原近手包络unknown：要求无抓持／无contact、pinch仍严格大于2mm，且整个对象collision集合与整个gripper contact集合在预注册world x/y/z至少一个轴上有严格大于2mm的保守分离下界。取最大gap，同分按x/y/z；不能只挑一对有利geom。

box使用世界姿态与native半尺寸投影，mesh使用编译后的全部`mesh_vert`和当前geom世界位姿。轴向gap是保守分离下界，不是最短距离。未知合法类型或不支持的过滤／非零margin、gap不能新增True；缺字段、非法引用、身份错配或非有限值是measurement技术错误，不能算持有、策略失败或物理unknown。保留旧sphere/pinch/contact证据及新模型身份、轴、区间、极值geom；只读计算不新增native步、forward、render或RNG消耗。

投影加入float64 `gamma(16)`尺度误差界及向外`nextafter`，gap再向负无穷舍入，避免浮点误差把2mm边界误认证。静态证据保留masks、显式pairs/excludes、weld/parent过滤、collision options及contact-filter状态；callback仅通过已加载MuJoCo模块的既有只读getter检查，不导入新native模块。无法确认无callback或配置不支持时不补True。静态XML只在observer初始化时读取；逐帧校验当前sim/model代际与静态数组、mesh、分组摘要，不重复XML序列化。

新校准仍取每条每阈值的第一次`p >= threshold`。首hit当前False是提前、None是unknown、True才可讨论及时；后续crossing不能补救首hit。将完成truth的None分别全部设True／False，只用于求`tau_low`／`tau_high`假设边界，不生成标签或改动known值。双端有限时，鲁棒及时须`tau_high <= first_hit <= tau_low + 24`；无法证明时保留timing_unknown，不取有利端。

固定五条分母、完整证据和零提前／零unknown-first-hit／零timing-unknown约束保持。可行候选中最大化鲁棒及时数量，同分选较高阈值，且数量须大于0才称新候选阈值已冻结。网格只含0.05..0.95步0.05及0.99。阈值冻结不等于普通停止能力已建立，后续10条active仍必需。

## 复用工件与新目录

部署由Codex核对已验收SHA与实际绝对路径，随后交付用户唯一下一真实命令。沿用原仿真和模型解释器，不升级依赖、不修改原LIBERO/XML或旧bank物理fingerprint；observer版本单独绑定。所有新plan/run/calibration/敏感性及日志写新目录，旧失败partial也保留。

| 复用项 | 核对要求 |
|---|---|
| 原head与权重 | 既有6636f713…身份及原v1标签合同；不得写成v2重新训练 |
| 原runtime | 原OFT解释器、源码、checkpoint、crop、seed7和chunk8不变 |
| 两域registry | 原profile与真实资产SHA；校准使用official-init角色，非HDF head_validation |
| normal-bank | 原init35..49已准备状态与preparation绑定；不再settle/audit |
| Remain | 原source001及独立replay；不重建、不补造provenance |
| 原结果 | 旧shadow、旧calibration、009诊断只读保留 |

新5条同来源是校准开发，不是新来源泛化证明。10条normal_test和15条Remain在阈值冻结前仍留出。

## 显式版本与兼容

| 消费者／工件 | 历史默认 | 010显式选择 |
|---|---|---|
| job | `remaining-finish-job-v1/v2`，原语义 | `remaining-finish-job-v3`＋完整`evaluation_contract` |
| plan / run | 原`remaining-finish-plan-v1/v2`、`remaining-finish-run-v1/v2` | 对应`-v3`，绑定同一contract SHA |
| 逐episode | `remaining-finish-episode-v1` | `remaining-finish-episode-v2`，contract＋`measurement_static` |
| 每帧事实 | 原v1 truth，缺新字段只能按legacy解释 | 当前v2 truth＋`measurement.legacy`，双测量及静态证据SHA |
| 输入／执行证据 | `remaining-finish-evidence-v1` | `remaining-finish-evidence-v2`，额外绑定contract、冻结阈值、静态证据与源state SHA |
| 几何证据 | 无新证书字段 | 静态`remaining-finish-release-geometry-v1`保存一次，逐帧`remaining-finish-release-poses-v1`与可复算证书 |
| release方法 | `panda-dualpad-contact-and-conservative-pinch-clearance-v1` | `panda-contact-pinch-world-axis-separation-v2` |
| calibration | 原`remaining-finish-calibration-v1/v2`，保留全轨迹unknown门槛 | `remaining-finish-calibration-v3`、`first-hit-robust-tau-v2`，正式报告`sensitivity_only=false` |
| FINISH控制协议 | `remaining-finish-v1` | 保持同一控制协议 |
| summary / metric | `remaining-finish-summary-v1`／`remaining-finish-contract-v1` | `remaining-finish-summary-v2`／`remaining-finish-contract-v2`，主评分公式不变，附`timing_diagnostic` |
| head/cache/训练标签 | 已冻结工件与v1训练标签合同 | 原样复用；evaluation合同独立绑定 |

旧job和009 replay默认仍v1测量，不能通过缺字段自动升级。v3的job、plan、环境、结果、证据、读回、指标、校准与active入口须核对相同contract；不同release／校准规则、head、域角色或sensitivity-only报告均不能进入正式active。旧result不强加新字段或重算旧hash。

## 配置与独立命令

新模板位于[versioned_release目录](../configs/remaining_goals/finish/versioned_release/)。三个job都绑定同一完整evaluation contract及原registry/head/runtime。`validation_shadow`使用原normal-bank；`normal_active`仍使用同bank并引用**本轮新正式calibration**；`remain_active`引用原source001/replay及同一新calibration。模板中的绝对路径由Codex填写核验，不能当成已部署配置。

以下为Linux Bash单阶段入口。`REPO/CFG/OUT/LOG`均是010验收后的全新目录，`SIM_PY`沿用原解释器。没有训练、重新准备状态或重做parity命令。

```bash
REPO=/ABS/NEW_ACCEPTED_TASK010_CHECKOUT
CFG=/ABS/NEW_PRIVATE_CONFIG/task010
OUT=/ABS/NEW_RESULTS/task010_run01
LOG=/ABS/NEW_LOGS/task010_run01
SIM_PY=/HUBU-AI096/zp/ICML/LIBERO-Remain-normal00-stage02/.runtime/remaining_libero/venv/bin/python
cd "$REPO"
mkdir -p "$LOG"
finish010_stage() {
  local tag="$1"
  shift
  local logfile="$LOG/$tag.log"
  local codes
  (set -o noclobber; : > "$logfile") || return 2
  {
    printf 'UTC: '; date -u '+%Y-%m-%dT%H:%M:%SZ'
    printf 'cwd: %s\ncommand: ' "$PWD"
    printf '%q ' "$SIM_PY" -m benchmark.remaining_goals.finish.cli "$@"
    printf '\n'
  } >> "$logfile"
  if "$SIM_PY" -m benchmark.remaining_goals.finish.cli "$@" 2>&1 | tee -a "$logfile"; then
    codes=("${PIPESTATUS[@]}")
  else
    codes=("${PIPESTATUS[@]}")
  fi
  printf 'command_exit=%s tee_exit=%s\n' "${codes[0]}" "${codes[1]}" | tee -a "$logfile"
  (( codes[0] == 0 && codes[1] == 0 ))
}
```

函数定义不会启动阶段。每次调用只做一个阶段，日志拒绝覆盖并分别记录命令／tee退出码；已有输出或失败partial不覆盖、不resume。下面各代码块独立，不能作为自动串联作业执行。

Codex先做纯文件预算与shadow计划；这两个命令不创建native环境、不加载模型：

```bash
finish010_stage 00_budget budget-plan --revision task010
```

```bash
finish010_stage 01_shadow_plan dry-plan --config "$CFG/validation_shadow.json" --out "$OUT/validation_shadow_plan"
```

确认计划仅init35..39五条、H520/W150/chunk8、同旧head/bank/runtime、明确新版contract后，由用户独立启动唯一下一真实阶段：

```bash
finish010_stage 02_shadow run --config "$CFG/validation_shadow.json" --out "$OUT/validation_shadow"
```

完整检查新run、raw、输入证据、双视角视频、measurement静态／动态证据及固定missing后，离线生成正式校准与独立敏感性表。这两步只读取同批新5条，不调用模型或仿真：

```bash
finish010_stage 03_calibration calibrate --run "$OUT/validation_shadow" --out "$OUT/calibration"
```

```bash
finish010_stage 04_sensitivity sensitivity --run "$OUT/validation_shadow" --out "$OUT/sensitivity"
```

正式报告若未建立有用候选，停在此处。通过后Codex把新正式`calibration/calibration.json`路径核入两个active配置，再做normal计划；用户只在该阶段核验完成后独立启动：

```bash
finish010_stage 05_normal_plan dry-plan --config "$CFG/normal_active.json" --out "$OUT/normal_active_plan"
```

```bash
finish010_stage 06_normal run --config "$CFG/normal_active.json" --out "$OUT/normal_active"
```

normal10条是独立验证；结果不能反馈修改阈值或几何方法。完成该阶段分析后，Codex核验Remain15条计划，用户再独立启动：

```bash
finish010_stage 07_remain_plan dry-plan --config "$CFG/remain_active.json" --out "$OUT/remain_active_plan"
```

```bash
finish010_stage 08_remain run --config "$CFG/remain_active.json" --out "$OUT/remain_active"
```

需要离线复核时写新目录；下列入口不改变原run或阈值，也不启动下一阶段：

```bash
finish010_stage 09_inspect inspect --run "$OUT/remain_active"
```

```bash
finish010_stage 10_rescore rescore --run "$OUT/remain_active" --stable-steps 4 --out "$OUT/remain_rescore"
```

## 产物检查与停止条件

每次真实阶段独立启动：新shadow → 离线正式校准冻结 → normal active → Remain active。任何技术失败、版本／来源／head错配或能力未建立先停止分析，不自动重跑、改阈值、换来源、调head或扩预算。shadow不会应用FINISH，主FINISH成功率为N/A；技术／缺失／unknown不得伪装成策略0%。

同批新5条保存v1/v2双测量，离线生成release v1/v2 × legacy/new规则的2×2敏感性表。每格固定同5条、同head概率、同20阈值/K4/24步；缺证据写不可判定。全部派生格标记sensitivity-only，不能作为active阈值。正式active只接受预注册新测量＋新规则且头、来源、版本和校准有效性完全一致的正式报告；不得fallback到0.99。

主表仍只有合规FINISH成功率百分比与n/N，附原有延迟、失败原因与覆盖诊断。FINISH时全部目标＋released、初始成果全程保持、FINISH后W150保持和sticky错物K4均不放宽。测量证书与版本是取证，不另造论文主指标。

## 009实数据的纯CPU外部复核

本轮X机器未找到009原始侧录，因此没有宣称完成step280独立复算。提供下列文件读取测试；只需原备份中的`static.npz`与`native/0280.npz`，无需重新创建仿真或模型，也不上传57MB原树到GitHub。路径应由保存备份的Codex核对后填写；测试固定校验原文件SHA，不接受重新生成的替代数据。

```bash
LIBERO_REMAIN_TASK009_FIXTURE=/ABS/ORIGINAL_TASK009_BACKUP_RUN \
  "$SIM_PY" -B -m pytest tests/test_finish_release_geometry.py::test_task009_external_step280_projection -q -ra
```

固定SHA：`static.npz`为`9cf8d6654735b949e67a97840b961659fab21e8b11d149a9a2daf41e08ce0626`，`native/0280.npz`为`b025d3251339def6e393529034adb2841b8ad1d196f243b4a2be88bfdc8b73cd`。测试直接调用本版投影函数核对24个番茄geom与5个hand geom的world-z nominal gap，并核对原sphere/pinch值；不改旧raw或校准。自动化环境缺外部路径会明确skip，不能当成此项已通过。
