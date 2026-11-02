# Task033：九个 LIBERO-10 复合任务完整运行说明

本轮唯一正式人口为官方默认 task_id **0,1,2,3,4,6,7,8,9**，每项固定 init index0..9。00、10各90条；旧六任务各60条只读复用，只执行新3/8/9各30条，合计新增60条模型评测。四个 LIBERO-90 退出当前计划；旧两个90任务的未执行补建/补测已取消。旧定义、原80/100报告和原视频保留，取消不代表物理问题解决。

权威实现来自 LIBERO-Remain 的033独立PR；代码parent为已审031 `ac1301779cf6ae4c34ebc80c20936a4f7a4953be`，并同步main `c9145d17a3c279ad7384ad357118095c6b648061` 的032/033/Plan6。新协议版本为 `remaining-headless-nine-normal00-v1`、`remaining-headless-nine-mask10-v1`，评分版本为 `remaining-headless-official00-drop-diagnostic-v1`。旧013支撑v2和031 R2续跑保护均保留。CPU/fake通过仅验证实现，不证明真实状态或模型成功。

## 任务与语义

| official ID | key | A | B | 初态约束 |
|---:|---|---|---|---|
| 0 | basket | 汤罐入篮 | 番茄酱罐入篮 | 旧来源复用 |
| 1 | basket_cheese_butter | 奶酪入篮 | 黄油入篮 | 旧来源复用 |
| 2 | stove | 炉子开启 | 摩卡壶上炉 | 旧来源复用 |
| 3 | bowl_drawer_close | 黑碗在下抽屉内 | 下抽屉关闭 | 00/10均下抽屉Open |
| 4 | dual_mugs | 白杯上左盘 | 黄白杯上右盘 | 旧来源复用 |
| 6 | mug_pudding | 白杯上盘 | 布丁在盘右 | 旧来源复用 |
| 7 | basket_soup_cheese | 汤罐入篮 | 奶酪入篮 | 旧来源复用 |
| 8 | two_pots | moka_pot_1上炉 | moka_pot_2上炉 | Turnon(flat_stove_1)为真 |
| 9 | mug_microwave_close | 黄白杯在微波炉内 | 微波炉关闭 | 00/10均微波炉Open |

10固定A真、B假。3/9必须物已入、门仍开；Open仅约束初态及来源验证，模型关门后当然可变假。构造按容器当前site位姿放置并验证native In/Open，不按BDDL谓词书写先后决定A/B。8的mask仅覆盖两壶，完整官方成功仍含Turnon，10轨迹持续保持A与炉子开启。官方完整任务名、原始谓词顺序及active/invariant映射一起验证。门/柜/炉是相关设施，两壶均为目标，不能误作干扰物。模型只收到原完整指令、双相机与原proprio，不收到mask、谓词或接触真值。

## 环境与固定权重

使用已经运行旧六任务的原环境/资产。评测主解释器需有仓库、NumPy及原pinned LIBERO/robosuite/MuJoCo；模型使用原独立OFT解释器。不要在冻结a23目录内更新源码或产出新报告。将033 accepted commit部署到独立checkout，Codex部署时用实际服务器路径替换下方变量一次；运行命令不需手填hash或编辑来源JSON。

```bash
cd /path/to/isolated/LIBERO-Remain-task033
export PY=/path/to/original/libero-simulator-env/bin/python
export MODEL_PY=/path/to/original/openvla-oft-env/bin/python
export OFT_REPO=/path/to/original/openvla-oft
export OFT_CKPT=/path/to/original/openvla-oft-sog10
export OLD00=/path/to/a23/normal00-eight-run
export OLD10_RESCORE=/path/to/task013/derived-report
export OLD10_RUN=/path/to/original/headless-mask10-run
export OUT="$PWD/reports/task033"

"$PY" -m pip install -e '.[video]'
"$PY" -m benchmark.remaining_goals.headless.nine_cli --help
"$PY" -m benchmark.remaining_goals.headless.selected_preparation --help
```

`PY`是原仿真环境，不能随意替换为模型解释器；上面pip只安装当前仓库与录像依赖，不安装或升级仿真栈。保留已有本机LIBERO路径配置、EGL环境和GPU分配。独立worker通过配置中的 `python_executable` 使用 `MODEL_PY`。Windows可直接用两套Python绝对路径执行同一CLI；正文以Linux部署命令为准。

固定官方[OpenVLA-OFT源码](https://github.com/moojink/openvla-oft/tree/e4287e94541f459edc4feabc4e181f537cd569a8)与[SOG10模型快照](https://huggingface.co/moojink/openvla-7b-oft-finetuned-libero-spatial-object-goal-10/tree/638918f3d1c2e43a39a8a20772bdb8b91835e4b7)。不换权重，不新增下载为本轮前置；沿用原checkpoint准备方式。实际worker仍校验repo、component/inference字节身份、statistics及推理配置；声明revision不等于验证全部大权重字节。

固定 `libero_10_no_noops`、seed7、chunk8、H520、原center crop/双图/proprio、非量化。新九任务拒绝LIBERO-90、suite-transfer、错误归一化、FINISH配置或超出new-three的执行population。

## 1. 只读盘点与生成配置

以下均不创建仿真、不加载权重。输出文件已存在则拒绝覆盖；更换输出名保留旧版。

```bash
"$PY" -m benchmark.remaining_goals.headless.nine_cli runtime-config --oft-repo "$OFT_REPO" --checkpoint "$OFT_CKPT" --model-python "$MODEL_PY" --cuda-visible-devices 0 --out "$OUT/runtime.json"
"$PY" -m benchmark.remaining_goals.headless.nine_cli reuse-index --normal00-run "$OLD00" --mask10-rescore "$OLD10_RESCORE" --mask10-run "$OLD10_RUN" --out "$OUT/reuse.json"
"$PY" -m benchmark.remaining_goals.headless.nine_cli budget-plan --protocol nine-normal00 --out "$OUT/budget00.json"
"$PY" -m benchmark.remaining_goals.headless.nine_cli budget-plan --protocol nine-mask10 --out "$OUT/budget10.json"
"$PY" -m benchmark.remaining_goals.headless.nine_cli sources-template --protocol nine-normal00 --out "$OUT/sources00.json"
"$PY" -m benchmark.remaining_goals.headless.nine_cli sources-template --protocol nine-mask10 --out "$OUT/sources10.json"
"$PY" -m benchmark.remaining_goals.headless.selected_preparation --inventory "$OUT/sources00.json" --output "$OUT/inventory00" --protocol nine-normal00 --mode inspect
"$PY" -m benchmark.remaining_goals.headless.selected_preparation --inventory "$OUT/sources10.json" --output "$OUT/inventory10" --protocol nine-mask10 --mode inspect
"$PY" -m benchmark.remaining_goals.headless.nine_cli summarize --reuse-manifest "$OUT/reuse.json" --out "$OUT/reuse-only-report"
```

首次空来源盘点返回exit2是缺来源，报告仍完整保存；不是请求自动重试。budget每个条件expected90、reuse60、selected30，selected task_id只能是3/8/9。旧数据全在时只读报告覆盖各60/90；这是覆盖率，不是SR。缺旧工件或不可验证记录保持missing/technical/unknown并给具体原因，绝不进入准备或模型队列。

reuse-index优先读取原00 summary/原10的013派生报告；仅在必要字段缺失时读取对应raw，不默认重解码全部视频。`--mask10-run`用于原始执行目录或合法搬迁路径，必须匹配013记录的原batch字节身份；不能指向不同批次。若不搬迁且原路径仍存在，可省此参数。每条保存原model/code/protocol/source/endpoint和读过的文件digest、证据级别；report-only不会伪称本次重验全部视频。完整保留legacy与primary、逐条分类差异，当前读取时再次校验依赖。全局harness变化不会否定旧六；实际资产/统计不同会具体列出身份分组并禁止不兼容聚合，不改原行、不自动重跑。

## 2. 用户启动新三任务来源准备

本节是未来真实操作命令，本轮实现交付没有执行。默认只选3/8/9及index0..9，不准备旧六、不生成01/11。来源准备和模型episode分别记账。

```bash
"$PY" -m benchmark.remaining_goals.headless.selected_preparation --inventory "$OUT/sources00.json" --output "$OUT/prepare00" --protocol nine-normal00 --mode prepare-missing
"$PY" -m benchmark.remaining_goals.headless.selected_preparation --inventory "$OUT/sources10.json" --output "$OUT/prepare10" --protocol nine-mask10 --mode prepare-missing
```

00为官方固定index的settled base：原有settle80及t0必要审计，不追加150 hold或独立回放。10延用selected-A-only和原物理门槛：构造稳定150、正式adapter独立恢复2×150；构造/回放各自保留证据。位置0.005、速度0.01、机器人位移0.002、穿透0.002、观测1e-8、RGB差1/changed fraction0.0001均未放宽。来源级失败隔离；不换index、不调阈值补分。

已有输出可显式 `--continue`；已有构造缺回放只补回放，ready仅重验文件。真正失败的新尝试需显式 `--allow-failed-retry`，保留旧账本。但曾ready后依赖丢失/损坏的来源，在原输出即使 `--continue --allow-failed-retry` 仍只能文件重验、零native调用；恢复原文件后可重验。确需新的物理尝试必须另一个尚不存在的 `--output`，不覆盖旧证据。

## 3. 固定只执行新增60条

配置命令写入实际路径并自动绑定来源，不手填hash。可提前生成配置；后续dry-plan按来源文件逐项判断ready。

```bash
"$PY" -m benchmark.remaining_goals.headless.nine_cli configure --protocol nine-normal00 --runtime-config "$OUT/runtime.json" --sources "$OUT/prepare00/sources.json" --reuse-manifest "$OUT/reuse.json" --out "$OUT/run00.json"
"$PY" -m benchmark.remaining_goals.headless.nine_cli configure --protocol nine-mask10 --runtime-config "$OUT/runtime.json" --sources "$OUT/prepare10/sources.json" --reuse-manifest "$OUT/reuse.json" --out "$OUT/run10.json"
"$PY" -m benchmark.remaining_goals.headless.nine_cli dry-plan --config "$OUT/run00.json" --out "$OUT/plan00.json"
"$PY" -m benchmark.remaining_goals.headless.nine_cli dry-plan --config "$OUT/run10.json" --out "$OUT/plan10.json"
```

检查两个plan的selected均30、task_id均3/8/9，ready各30，旧六为reuse_only；dry-plan不启动模型。`configs/remaining_goals/headless/nine-normal00.example.json` 和 `nine-mask10.example.json` 是对应模板，推荐使用configure命令生成实际文件。

以下两条是用户明确启动的正式评测，每个30条，不能先另加模型smoke/probe；新批第一条正常保存即正式episode。

```bash
"$PY" -m benchmark.remaining_goals.headless.nine_cli run --config "$OUT/run00.json" --out "$OUT/run00"
"$PY" -m benchmark.remaining_goals.headless.nine_cli run --config "$OUT/run10.json" --out "$OUT/run10"
```

来源不足时默认拒绝进入新run；显式 `--allow-missing` 才执行ready部分并保留其余missing。续跑使用完全相同配置加 `--continue`，只补从未尝试且现已ready的来源；已经尝试、失败、中断或证据目录丢失均不会自动重跑。尝试意图在模型加载前落盘，不用文件夹是否存在推测未执行。模型/代码/reuse身份改变时拒绝同目录续跑。缺证据先保留异常，不通过删除目录重置预算。

00在第一次完整native官方成功或H结束，释放、五观测、table_drop均不增加门槛。10仍在全部官方目标+release连续五观测或H结束，A/invariant的回退保留为违规。录像复用每个真实执行步的原双相机帧，包含初始帧与终止帧，保存帧步数/索引/digest；不为录像额外step。worker、chunk截断、typed observation及episode source snapshot沿用原代码。

## 4. 离线核验、032评分与九任务主表

```bash
"$PY" -m benchmark.remaining_goals.headless.nine_cli inspect --run "$OUT/run00" --out "$OUT/inspect00"
"$PY" -m benchmark.remaining_goals.headless.nine_cli inspect --run "$OUT/run10" --out "$OUT/inspect10"
"$PY" -m benchmark.remaining_goals.headless.nine_cli summarize --runs "$OUT/run00" "$OUT/run10" --reuse-manifest "$OUT/reuse.json" --out "$OUT/nine-task-report"
```

生成 `summary.json` 与 `report.md`，按official ID排序。summary保存180个计划位置、每行原分数/新分数/变化和来源，分旧六与新三覆盖。未执行不计模型失败；主SR报告可验证已执行分母n/N，同时明确各90的计划覆盖。无任何eligible执行时SR为N/A而非0%。技术异常、未知、未执行分别列明；旧100分母不混入新90。

- **00主指标：** 轨迹中的完整官方成功bool信号曾为真即成功；缺signal是未知，技术中断和缺文件分别保留。旧legacy compliant仅诊断。新00提前官方终止没有收集旧release+五观测端点，legacy诊断明确N/A，不能把首次官方成功伪称旧确认成功。
- **10主指标：** 合规成功保留A与invariant、剩余目标、错抓/错放、释放等规则。仅 `event == table_drop` 的确认违规及其对应event_unknown降为诊断；混合wrong-placement未知、release未知、其他确定失败不删除，确定失败优先。保留原事件和逐行diff，原始轨迹/013文件不改。
- **可比较项：** 00 official_task_SR与10 official_task_SR同口径。10 compliant_task_SR另列，不把它与00官方SR之差当同一指标下降。
- **路径：** 10成功条件TCP长度按旧口径报告任务均值、等任务宏均值、成功轨迹数/计划数及有成功任务数/9；额外path completeness明确与计划覆盖分开。00旧六与新三终点不同，全轨迹长度只按原协议/端点分组，不出混合效率均值。没有成功时长度N/A。

新run的inspect核验归档source、raw、执行观测、模型身份和录像绑定。历史复用保持其实际证据级别。新旧model/statistics身份允许路径搬迁和不同harness SHA，但不允许实际assets/inference改变后仍无说明合并。原run、源证据与派生报告输出目录必须隔离；不覆写历史summary/batch，也不挑选重复输入中的较好结果。

## 5. 交付后同版本导出

源PR验收后，从**同一接受commit**导出；本次没有推送或宣称更新LIBERO-Remain-Eval。示例：

```bash
python scripts/export_task033_eval.py --source-revision ACCEPTED_FULL_COMMIT_SHA --output /path/to/new/LIBERO-Remain-Eval-task033.zip
```

清单包含九任务catalog、必要benchmark源（含只读legacy兼容依赖）、SOG10 runtime、新九任务配置、此runbook、导出README、安装元数据和许可证；不带原始数据/权重/研究讨论/旧90默认配置。`SOURCE_EXPORT.json`给出source commit和逐文件hash。源变化后重新从同commit生成，不能在Eval手工维护另一套实现。方法库只同步范围及源PR链接。
