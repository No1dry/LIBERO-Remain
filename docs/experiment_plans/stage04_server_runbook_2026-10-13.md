# Stage04 已部署版本：用户分阶段运行命令

2026-10-13，Codex。007软件交付accepted；Stage04真实实验尚未运行、未closed。

**最新真实预检裁决（2026-10-14，优先于下文历史待办）**：用户已启动第3节，结果technical_error／退出2／trace=[]／model_calls=0。官方basket的OnTheGroundPanda被当前严格Panda类名检查误拒绝；[007_round2](../../collaboration/reviews/007_round2.md)已要求X修一个明确P1错误。**当前不要再启动38版第3节或任何受影响真实FINISH阶段，也不要覆盖／删除第一次失败。**待X交新SHA、Codex审查部署新目录后，再给同一11的新out／日志命令。以下“11可启动”描述是此前准备阶段的历史状态，已由本最新裁决覆盖。兼容性修复不自动解决HDF来源映射问题。[结果记录](../stage_summaries/stage04_preflight_failure_2026-10-14.md)。

**2026-10-14准备更新（优先于下文历史待办）**：用户已把非实验准备交给Codex，固定官方HDF5现已下载并核SHA，用户无需执行第4节。纯文件检查的50条HDF演示与50个official init无法建立精确来源对应，init_state属性也未补出映射；当前默认分组尚不具备训练前提。**暂不执行第5节真实audit及后续feature／训练／评测**，先由Codex处理来源证据或提出设计修订供用户确认；不要修改空source map、借test或猜demo编号。第3节已有11物理preflight仍可由用户启动。完整证据见[2026-10-14准备记录](../stage_summaries/stage04_data_preparation_2026-10-14.md)。原命令作为已审软件入口保留，不代表当前全部允许执行。
所有命令由用户启动、运行和监督，Codex不后台启动或代跑。下面各节不是自动串行脚本：每一阶段检查产物后，再手动执行下一节。

## 1. 已部署与已验证

冻结源码：`38e6a449d4e769b842e10c5b393fc2b26a5cfa2b`，PR #4。它与X测试实现`55474fd`的源码相同，最后一提交仅增加交付与STATUS文档。

| 项目 | 实际路径／结果 |
|---|---|
| 新源码目录 | `/HUBU-AI096/zp/ICML/LIBERO-Remain-stage04-finish-38e6a44` |
| 新配置／资产／日志根 | `/HUBU-AI096/zp/ICML/stage04_finish_38e6a44` |
| 本次结果目录 | 上述根下`results/run01` |
| 本次实验日志 | 上述根下`logs/run01` |
| 运行环境 | 保留stage02的独立sim与OFT venv，不升级依赖 |
| 服务器GPU | 只读查询为A100-SXM4-80GB；不是历史4090 |
| 源码核验 | 194个GitHub blob逐文件SHA-1/SHA-256与上传后文件一致 |
| Codex本地软件测试 | 新增237 passed；全套1468 passed / 12 skipped |
| 服务器新增CPU/fake测试 | 237 passed，23.41秒；没有真实VLA／仿真／数据训练 |
| 当前数据前置项 | 官方basket HDF5未在核对的项目数据目录找到；下文给单文件下载命令 |

这是GitHub固定commit的**源码快照**，不是带`.git`的clone。不要在此运行`git pull`或用`git rev-parse`冒充部署证据；身份由`source_inventory.json`及逐文件核验给出。新目录的`.runtime/remaining_libero`只链接旧固定runtime，旧源码、状态、权重、OFT本地patch与实验结果不修改。

OFT运行配置SHA-256固定为`75f2a711a39c58a07715b3a280aeba26a29dfbba70caf87cc051520f0a3f9720`。所有特征／parity／validation／normal／Remain阶段用同一文件、center_crop=true、seed7、chunk8、同一官方SOG10权重。当前head身份未继承完整runtime hash，所以部署包装器在**每个命令前**另核验所有冻结源码与配置，防止阶段间误换输入配置。这是非阻塞部署防护，不要求X本轮返修。

## 2. 登录、设置会话

本段定义环境与手动命令辅助函数，不启动实验。SSH密码在交互提示中输入，文档不保存密码。

```bash
ssh root@122.204.216.104 -p 30369
bash
source /HUBU-AI096/zp/ICML/stage04_finish_38e6a44/session.sh
"$SIM_PY" "$RUNROOT/verify_deployment.py" "$REPO" "$RUNROOT"
```

`finish_sim 日志名 子命令 参数`与`finish_model 日志名 子命令 参数`分别使用已部署的sim和model Python调用`python -m benchmark.remaining_goals.finish.cli`。`stage_log 日志名 完整命令`只负责当前命令的身份检查和tee日志，没有队列／自动下一步／resume／监控。日志记录完整命令、UTC、command_exit与tee_exit。

每个`--out`与日志名只允许首次使用；遇中断或错误保留全部文件，不删失败、不换容易来源、不在原目录重跑。需要重跑时先交Codex审查，再配置另一个新run与对应head／calibration／normal_bank路径；不能只改OUT，因为job JSON仍绑定run01。勿就地修改冻结JSON或重做manifest绕过校验。

本次sim Python：`/HUBU-AI096/zp/ICML/LIBERO-Remain-normal00-stage02/.runtime/remaining_libero/venv/bin/python`；model Python：同旧checkout下`.runtime/oft_worker/bin/python`。保留venv/bin/python路径，不把symlink解析成base Python。会话已设置LIBERO_CONFIG_PATH、EGL、PYTHONPATH、CUDA_VISIBLE_DEVICES=0及无用户包串环境。

## 3. 现在首先运行：已有11状态的4步环境预检

这一步是真实仿真，但不加载模型，不需要HDF5，不是评测rollout。

```bash
finish_sim 00_budget budget-plan
finish_sim 01_preflight_11 preflight \
  --source-config "$CFG/preflight_source.json" \
  --episode-id basket_s000_11 \
  --out "$OUT/environment_preflight_11"
"$SIM_PY" -m json.tool "$OUT/environment_preflight_11/preflight.json"
```

检查`status=recorded`、初态goals=[true,true]、trace完整0..4、hold_contract为退出当前末端pose与原gripper target保持、无technical_error。看每一帧的对象contact／hand与pinch几何距离／released；保守unknown不当作已释放，也不当作确定策略失败。11预检应能确认当前已放下目标的释放与目标保持，否则先交回报告；不能用CPU通过替代物理检查。

补充检查一个partial来源（独立命令，不增加模型rollout；**不证明真实夹持状态的release检测已覆盖**）：

```bash
finish_sim 01b_preflight_10 preflight \
  --source-config "$CFG/preflight_source.json" \
  --episode-id basket_s000_10 \
  --out "$OUT/environment_preflight_10"
```

4步预检只是接口／证据先行，最终真实W150保持效果仍由正式active/timeout轨迹验证。预检没有视频输出，保存初始观测NPZ和物理trace；完整评测才有两路视频。

## 4. 用户补齐官方basket演示：只下载单个HDF5

已核官方HuggingFace LIBERO数据仓库包含该原始文件，约1.47GB。固定revision`147fa5eb607bb696dd922c3518084a90954cd2f3`，文件bytes=1467540242，SHA-256=`3173ebc709b064683956b757ae8737909457d730aa305b23c5735292e59066af`；见[官方数据目录](https://huggingface.co/datasets/yifengzhu-hf/LIBERO-datasets/tree/147fa5eb607bb696dd922c3518084a90954cd2f3/libero_10)和[原始上传commit的LFS指针](https://huggingface.co/datasets/yifengzhu-hf/LIBERO-datasets/commit/e329580e402fb5f07ae3b1f18475fc3b63783b91)。不是RLDS／图像-only转换数据。

Codex没有启动数据下载。以下由用户运行；服务器至HuggingFace的连通性未预先保证。如果下载失败保留`.part`和日志，停下来，不换未经核对的镜像或转换版本。

```bash
mkdir -p "$ASSETS/libero_10"
DATAFILE="$ASSETS/libero_10/LIVING_ROOM_SCENE2_put_both_the_alphabet_soup_and_the_tomato_sauce_in_the_basket_demo.hdf5"
test ! -e "$DATAFILE" && test ! -e "$DATAFILE.part"
```

上面检查必须成功，再单独执行：

```bash
stage_log 02_download curl -fL --connect-timeout 30 --retry 2 \
  'https://huggingface.co/datasets/yifengzhu-hf/LIBERO-datasets/resolve/147fa5eb607bb696dd922c3518084a90954cd2f3/libero_10/LIVING_ROOM_SCENE2_put_both_the_alphabet_soup_and_the_tomato_sauce_in_the_basket_demo.hdf5?download=true' \
  --output "$DATAFILE.part"
```

下载命令退出0，再核验并只重命名新文件：

```bash
printf '%s  %s\n' \
  '3173ebc709b064683956b757ae8737909457d730aa305b23c5735292e59066af' \
  "$DATAFILE.part" | sha256sum -c - && mv -n "$DATAFILE.part" "$DATAFILE"
wc -c < "$DATAFILE"
```

若你已有同字节官方HDF5，可以自己复制到该新assets目标并按上述hash核验，不需重复下载；不移动／覆盖旧实验资产。配置已绑定这个目标、现有官方.pruned_init／BDDL、原指令与stride8，不需要手工填`/ABS/`。

## 5. 数据计划与真实来源／标签审计

```bash
finish_sim 03_data_plan plan-data --config "$CFG/data.json" --out "$OUT/data_plan"
finish_sim 04_audit audit-data --config "$CFG/data.json" --out "$OUT/audit"
"$SIM_PY" -m json.tool "$OUT/audit/audit.json"
```

计划只检查文件；audit才可能真实恢复状态／采4步hold监督标签。只有audit的`status=ready_for_feature_export`且issues=[]、train与validation都有正负类才执行第6节。

默认head整组：train5..34，validation35..39，normal_test40..49，remain_test0..4及全部编辑变体。`trajectory_source_map`目前为空，代码只自动采纳唯一精确初态匹配，不把demo_35猜成init35。

如果`insufficient`／source_mapping_unverified：保留assets hashes与source_inventory，发给Codex。审计inventory不是采集溯源，不允许填虚构manually_confirmed来继续。需要真实采集记录或用户/Codex确认独立替代split后，再部署新版配置到新目录；**不是因为数据不足就要求X改代码**。无法证明映射时，当前默认设计尚不具备训练前提。详见X的`docs/finish_v1_runbook.md`第4节。

## 6. 特征导出与小头训练（审计通过后）

```bash
finish_sim 05_features export-features \
  --audit "$OUT/audit" --runtime-config "$CFG/oft_sog10.json" \
  --out "$OUT/features"
```

检查`features/feature_export.json`为completed、completed=true及`cache/cache.json`完整。这是首次真实VLA forward阶段；从原同一次forward捕获原56动作hidden，不输入GT／split／source。实际forward数量见报告，不计成rollout。

再独立执行：

```bash
finish_model 06_train train --cache "$OUT/features/cache" \
  --training-config "$REPO/configs/remaining_goals/finish/train.json" \
  --out "$OUT/train"
```

检查`train/training.json` status=finished、head.json/head.npz存在并绑定audit/split/base。训练默认CPU、seed7、最多50epoch，仅新增FP32 finish head；本命令仍是用户实验，Codex未执行。训练分数差如实分析，不自动调参、换模型或改源码。job中的head路径已填为这个目录。

## 7. normal来源准备与32输入动作parity

```bash
finish_sim 07_normal_bank prepare-normal \
  --indices 35 36 37 38 39 40 41 42 43 44 45 46 47 48 49 \
  --out "$OUT/normal_bank"
```

检查normal_bank/normal_bank.json为prepared、完整15个请求来源。80settle+150technical audit是初态准备，不冒充独立重复回放／测试rollout。已填validation与normal job的manifest路径。

```bash
finish_sim 08_parity parity --audit "$OUT/audit" \
  --runtime-config "$CFG/oft_sog10.json" --head-artifact "$OUT/train/head" \
  --atol 0 --rtol 0 --out "$OUT/parity"
```

检查32个独立validation输入、passed=true、status=completed、逐输入两路原动作一致。32×2真实forward，不是32rollout。不足32不得借test补；若零容差失败，交回报告，不事后放宽救通过。若将来预先决定非零容差，另留设计记录和新out。

## 8. validation shadow 5条与冻结阈值

```bash
finish_sim 09_validation_plan dry-plan \
  --config "$CFG/validation_shadow.json" --out "$OUT/validation_plan"
finish_sim 10_validation_run run \
  --config "$CFG/validation_shadow.json" --out "$OUT/validation_shadow"
finish_sim 11_validation_inspect inspect --run "$OUT/validation_shadow"
```

逐项确认plan固定5条／3350最大物理步、run完整、inspect全部证据通过，再进行只读校准：

```bash
finish_sim 12_calibration calibrate --run "$OUT/validation_shadow" --out "$OUT/calibration"
"$SIM_PY" -m json.tool "$OUT/calibration/calibration.json"
```

需`status=candidate_threshold_frozen`且calibrated=true才能继续active；这是代码实际返回的status，不是字面`calibrated`。首次越阈校准、无premature并有及时命中；全部不FINISH／及时率0是capability_not_established，不自动用test改阈值。shadow不能证明提前退出后的反事实hold。calibration路径已填，无需手工改job。

## 9. 独立normal00 active 10条

```bash
finish_sim 13_normal_plan dry-plan --config "$CFG/normal_active.json" --out "$OUT/normal_plan"
finish_sim 14_normal_run run --config "$CFG/normal_active.json" --out "$OUT/normal_active"
finish_sim 15_normal_inspect inspect --run "$OUT/normal_active"
sed -n '1,220p' "$OUT/normal_active/report.md"
```

先交回普通停止能力百分比+n/10、premature、及时停止、unknown/technical/missing和视频。Plan4的90%／10%只是小样本pilot沟通参照，不是软件验收门槛；不足不自动要求X返修，也不能称已排除未学停止干扰。用户/Codex决定是否仍按冻结设计做Remain诊断。

## 10. Remain active 15条（用户决定继续后）

```bash
finish_sim 16_remain_plan dry-plan --config "$CFG/remain_active.json" --out "$OUT/remain_plan"
finish_sim 17_remain_run run --config "$CFG/remain_active.json" --out "$OUT/remain_active"
finish_sim 18_remain_inspect inspect --run "$OUT/remain_active"
sed -n '1,220p' "$OUT/remain_active/report.md"
```

固定source0..4×10/01/11，三种mask都H520，FINISH或TIMEOUT后真实W150，chunk8。模型自行FINISH，没有GT许可停车；错停立即退出并失败。完工但不FINISH是TIMEOUT。旧11窗口／旧JSR/UIR与新schema不混分，不覆盖旧结果。

主项为合规FINISH确认成功百分比+n/N：决策当下全部目标满足且目标释放，初始成果全程保持、退出后目标保持，无禁止投放。unknown、technical、missing另报，固定分母仍保留；有未知时成功百分比是确认成功下界，不称未知确定策略失败。该指标不声称无任何冗余尝试。

## 11. 只读重评分与可选shadow

```bash
finish_sim 19_rescore_k4 rescore --run "$OUT/remain_active" --stable-steps 4 --out "$OUT/rescore_k4"
finish_sim 20_rescore_k1 rescore --run "$OUT/remain_active" --stable-steps 1 --out "$OUT/rescore_k1"
finish_sim 21_rescore_k8 rescore --run "$OUT/remain_active" --stable-steps 8 --out "$OUT/rescore_k8"
```

敏感性分析只读验证原raw／输入ledger／video，不修改原分数与证据。

可选额外15条Remain shadow，仅用户另行决定需要时运行：

```bash
finish_sim 22_shadow_plan dry-plan --config "$CFG/remain_shadow.json" --out "$OUT/remain_shadow_plan"
finish_sim 23_shadow_run run --config "$CFG/remain_shadow.json" --out "$OUT/remain_shadow"
finish_sim 24_shadow_inspect inspect --run "$OUT/remain_shadow"
```

shadow主FINISH项N/A。默认总预算30rollout，最大20100物理步；可选shadow另15／10050步。恢复标签、准备、特征及parity费用另计，无耗时承诺。

## 12. 出错、中断、视频与交回

每一步检查日志末尾command_exit和实际产物status；错误／不足／能力未建立一般2，中断130或支持partial的阶段2。不要把文件存在／0退出当科研成功。技术错误暂停余下集合、保存partial与missing，普通策略失败继续；没有自动resume。出现身份失败、hold／release技术错误、parity失败或audit不足，就保留并交回，不继续下一真实阶段。

评测录像在对应run的`videos/0000.mp4`等，raw为`raw/0000.json`等；用raw中的episode_id、任务／mask对应视频，编号不能凭印象猜。每个run另有run.json、summary.json、report.md与evidence/。normal与Remain分别存储。

先发我：`environment_preflight_11/preflight.json`和`audit/audit.json`（以及失败日志）；通过后再按阶段发feature_export、training、parity、calibration、normal和Remain原始产物。不要仅发成功均值。

职责：用户逐阶段启动／监督和保存日志；Codex审查证据、给下一决策；X仅在明确实现错误时修改代码。007代码accepted不代表Stage04真实实验完成。无待清理交流，开放任务与原始资产全部保留。
