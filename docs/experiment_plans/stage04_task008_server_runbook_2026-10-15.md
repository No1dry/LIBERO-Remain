# Stage04 / 008 已冻结服务器启动手册

2026-10-15。PR #5软件accepted，冻结 `b596af26e167450beb7f3c7fe61b6dfd53523ef6`；不是模型成绩或阶段closed。候选完整方法见[两域手册](../finish_two_domains_runbook.md)，本页补齐本服务器实际路径与会话。真实阶段只能用户显式启动；Codex已做的纯文件准备不要重复。

## 会话与第一条真实命令

登录现有服务器后，在Bash中执行：

```bash
bash
source /HUBU-AI096/zp/ICML/stage04_finish_b596af2/session.sh
finish_sim 03_audit audit-data --config "$CFG/data.json" --out "$OUT/audit"
```

source仅设置路径/定义函数，不运行实验；最后一行才启动真实状态恢复和物理标签审计。本阶段无VLA调用、没有head训练。不重复旧预检，不运行旧38/4f目录的audit。

- 源码：`/HUBU-AI096/zp/ICML/LIBERO-Remain-stage04-finish-b596af2`。
- 私有配置/会话根：`/HUBU-AI096/zp/ICML/stage04_finish_b596af2`。
- 原sim/model Python保留stage02的venv入口，不解析symlink为系统Python。
- `$CFG=$RUNROOT/configs`，`$OUT=$RUNROOT/results/run01`，`$LOG=$RUNROOT/logs/run01`。
- 结果：`$OUT/audit/audit.json`和逐帧观测NPZ。
- 日志：`$LOG/03_audit.log`，同时保存命令与command_exit/tee_exit。
- stage helper每次先核220源码及9个冻结部署文件；日志和阶段输出均禁止覆盖，不自动resume/串联。

此后把“完成了”发给Codex，由Codex直接读取服务器产物；用户不需要手动算SHA或下载数据。须audit完整、ready_for_feature_export且head_train/head_validation各有已知0/1，才能进入下阶段。unknown单列，insufficient不是模型失败；不足先分析，不自行换组或新增采集。

## 后续逐阶段命令（尚未执行，不要一次全部粘贴）

每个代码块是一次独立用户启动。仅在前一步完成、Codex检查产物后执行对应下一块。

特征导出：

```bash
finish_sim 04_features export-features --audit "$OUT/audit" --runtime-config "$CFG/oft_sog10.json" --out "$OUT/features"
```

仅小头训练，CPU也属于真实实验，用户启动：

```bash
finish_model 05_train train --cache "$OUT/features/cache" --training-config "$REPO/configs/remaining_goals/finish/train.json" --out "$OUT/train"
```

普通init35..49的真实normal-bank准备：

```bash
finish_sim 06_normal_bank prepare-normal --source-registry "$OUT/registry/registry.json" --indices 35 36 37 38 39 40 41 42 43 44 45 46 47 48 49 --out "$OUT/normal_bank"
```

32个HDF head_validation输入、64个同worker RNG配对forward：

```bash
finish_sim 07_parity parity --audit "$OUT/audit" --runtime-config "$CFG/oft_sog10.json" --head-artifact "$OUT/train/head" --atol 0 --rtol 0 --out "$OUT/parity"
```

5条official-init35..39普通shadow与离线阈值冻结，二者分别调用，不自动串联：

```bash
finish_sim 08_shadow_plan dry-plan --config "$CFG/validation_shadow.json" --out "$OUT/validation_shadow_plan"
```

```bash
finish_sim 09_calibration_shadow run --config "$CFG/validation_shadow.json" --out "$OUT/validation_shadow"
```

```bash
finish_sim 10_calibrate calibrate --run "$OUT/validation_shadow" --out "$OUT/calibration"
```

阈值需candidate_threshold_frozen、calibrated=true；零及时率/永不FINISH不是停止能力通过。不得用test调整阈值。

10条normal active（init40..49）：

```bash
finish_sim 11_normal_plan dry-plan --config "$CFG/normal_active.json" --out "$OUT/normal_active_plan"
```

```bash
finish_sim 12_normal_active run --config "$CFG/normal_active.json" --out "$OUT/normal_active"
```

15条Remain active（init0..4×10/01/11）：

```bash
finish_sim 13_remain_plan dry-plan --config "$CFG/remain_active.json" --out "$OUT/remain_active_plan"
```

```bash
finish_sim 14_remain_active run --config "$CFG/remain_active.json" --out "$OUT/remain_active"
```

可选Remain shadow额外15条未批准自动启动；其命令与K1/4/8离线复核见候选完整手册，需要时再给用户。默认模型预算仍30条、最坏20100物理步；audit/特征/normal准备/parity另计，没有新增VLA数据采集。

## 固定资产与限制

已下载官方HDF继续使用旧38目录的同一文件；SHA `3173ebc709b064683956b757ae8737909457d730aa305b23c5735292e59066af`。init SHA `1899fe54c51e24a41d5f9e32254730d6777f4894ab68e0e873f1fa7ae2062030`；BDDL SHA `2e661058917f683a25bce480015197f0a2c1911bcbc2b9dd9d947199069c9618`。不重复下载/转换数据。

OFT私有runtime逐字节沿用已冻结文件，SHA `75f2a711a39c58a07715b3a280aeba26a29dfbba70caf87cc051520f0a3f9720`；其中notes的38字样是历史来源，不表示本次执行旧源码。checkpoint、OFT patch、crop=true、seed7、chunk8不改。头/评测采用新v2数据身份，控制/评分仍原FINISH-v1。

跨域物理祖源独立性unproven；软件测试与file-only registry不证明物理label或模型停止能力。旧38失败、4f预检成功及stage03 raw/video全部保留；不删除交流。
