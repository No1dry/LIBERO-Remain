# LIBERO-PAB 协议与候选状态规范

版本：v0.1 pilot。LIBERO-PAB 是基于 [LIBERO](https://github.com/Lifelong-Robot-Learning/LIBERO) 的独立研究工程，并非LIBERO官方基准版本。

研究问题是：当人或外部过程提前完成任意合法部分任务后，VLA能否从当前观测识别剩余目标，并在保留已有成果的同时完成任务？本仓库实现状态构造、独立回放、统一rollout、计分和六模型接口。快速开始见 [README](../README.md)，真实模型配置见[六模型指南](remaining_goals_six_model_evaluation.md)。

自动构建结果始终是 `construction.legal=false` 的候选。技术稳定不证明语义可观察、剩余任务可执行或模型能力。代码和配置齐备不等于正式数据发布或六模型实验已完成。

## 1. 固定的比较单位

LIBERO提供任务定义、完整语言指令、仿真和官方初态。本协议新增外部部分完成状态与成果保护要求；其分数不等于原始LIBERO成功率。

| 部分 | 模型更换时固定的内容 |
|---|---|
| 任务 | 原始完整指令、官方最终谓词、目标分组 |
| 状态 | 来源、完成子集、机器人姿态、仿真状态与哈希 |
| Rollout | 控制频率、环境步预算、保持窗口和停止契约 |
| 适配器 | 使用各checkpoint真实的相机/本体输入、预处理、归一化、动作解码与缓存重置；原生执行chunk单列 |
| 计分 | 同一程序从逐步谓词重算指标，透明报告异常和缺失 |

manifest和模型运行配置共同定义一次实验。模型名、seed或一个均值不足以复现。模型只收到允许的相机/机器人本体观测和原始完整指令，不收到完成mask、对象真值或目标谓词。

## 2. 任务、轨道和完成子集

任务目录见 [task_catalog.py](../benchmark/remaining_goals/task_catalog.py)。官方task name用于查找suite内索引，不将索引写死。

| 轨道 | 任务键 | A / B |
|---|---|---|
| LIBERO-10 | `basket` | 汤罐入篮 / 番茄酱入篮 |
| LIBERO-10 | `stove` | 炉子开启 / 摩卡壶上炉 |
| LIBERO-10 | `basket_soup_cheese` | 汤罐入篮 / 奶油奶酪盒入篮 |
| LIBERO-10 | `basket_cheese_butter` | 奶油奶酪盒入篮 / 黄油入篮 |
| LIBERO-10 | `dual_mugs` | 白杯上左盘 / 黄白杯上右盘 |
| LIBERO-10 | `mug_pudding` | 白杯上盘 / 布丁位于指定右侧区域 |
| LIBERO-90 | `frypan_stove3` | 炉子开启 / 平底锅上炉，KITCHEN_SCENE3 |
| LIBERO-90 | `frypan_stove9` | 炉子开启 / 平底锅上炉，KITCHEN_SCENE9 |
| LIBERO-90 | `cabinet_close_top_bowl` | 顶层抽屉关闭 / 碗在固定柜顶 |
| LIBERO-90 | `cabinet_close_bottom_open_top` | 底层抽屉关闭 / 顶层抽屉开启 |

`--tasks all`或`primary`选择六个LIBERO-10任务；`extension`选择四个LIBERO-90任务。也可指定同一suite内的逗号分隔任务键。一个manifest和一个运行只包含一个suite，不混用checkpoint归一化或合并两轨成功率。

每任务3个官方初态、每来源4mask，对应主轨72候选和扩展轨48候选。实际导出数量取决于整组技术验收，不等于请求数量。默认 `--start-index 0 --split val` 使用索引0/1/2；split标签不证明来源独立，开发中使用过的来源不能冒充留出测试集。

| mask | 初始状态 | 用途 |
|---|---|---|
| 00 | A、B都未完成 | 正常任务控制 |
| 10 | A完成，B未完成 | 完成剩余目标并保持A |
| 01 | B完成，A未完成 | 完成剩余目标并保持B |
| 11 | A、B都完成 | 完成后保持与停止行为 |

主分数只汇总partial状态；00和11单列。通用schema/掩码代码支持三个目标，但当前没有真实三目标发布数据。十任务覆盖八个官方场景模板，入篮、开炉放锅等存在重复家族，不能视为十种独立能力。

目标组必须无重复且恰好覆盖官方最终谓词。不能仅因指令含“and”就拆目标，也不能把工具性前置动作当独立最终成果。双抽屉具有独立滑动关节，构造按region→body→joint精确匹配；中层、机器人和非目标分量保持共同基底。关闭区间从官方对象属性读取，不以数值零泛指关闭。独立关节不证明操作可达。

双摩卡壶任务的官方初态已包含 `Turnon`，该目标是初始不变约束，不能关炉制造000。当前将其标为 `requires_invariant_protocol` 并拒绝构建。依赖任务、动态中途帮助和必须临时撤销成果的任务不进入首版严格保留轨道。

## 3. 配对构造和来源隔离

状态离线构建、验收后冻结，再供所有模型使用。不能从每个待测模型自己的成功轨迹挑接手帧，也不能按模型成功率筛选初态。

构建器先从官方初态得到共同的settled 00基底并单独验收，再按预先排序生成有限个11联合候选。联合候选落稳后按明确状态索引白名单提取每个目标的分量；全部mask均来自**同一个联合候选**和同一个00基底：位为1使用相同完成分量，位为0使用相同未完成分量。机器人及白名单外状态来自共同基底。

放置目标复制物体完整自由关节的7个qpos和6个qvel，不能只复制xyz而恢复旧朝向。对象级On候选使用实际支撑物碰撞几何生成种子，最终仍由官方谓词、接触和动态验收判断。10与11中的A分量、01与11中的B分量完全相同；匹配仅针对冻结起点，不要求执行中静止。

settle后恢复机器人到共同姿态可能改变接触，因此每个派生状态还需重新恢复并独立验收。只有四个partner都通过才导出整组；一个失败就记录证据并尝试下一个联合候选，00基底失败则停止该来源搜索。报告保留attempted、rejected、eligible和失败原因。

同一来源、共享donor的全部mask、姿态及帧必须属于同一split。新增自然中间态、无编辑恢复、mask不变几何扰动或姿态挑战时应单列诊断，不能替代完整子集配对集。

## 4. 状态工件与身份

manifest顶层含 `schema_version`、`environment`、`episodes`、`content_hash`。关键episode字段：

| 字段 | 含义 |
|---|---|
| `episode_id`, `task_id` | 实例与任务身份 |
| `suite`, `libero_task_id`, `task_name`, `instruction` | 官方任务身份及完整指令 |
| `goal_specs` | 目标id、语言和原子谓词分组 |
| `initial_mask` | 仅evaluator使用的布尔完成向量 |
| `state_path`, `state_sha256` | 包内相对路径与状态文件SHA |
| `initial_observation` | 原始初始观测NPZ的format、path、文件SHA及内容SHA |
| `source_id`, `donor_source_ids` | 来源及可选共享donor |
| `initial_state_index`, `seed`, `pose_id`, `split` | 官方初态索引、仿真seed、接手姿态与划分 |
| `horizon`, `retention_steps` | H与W |
| `construction` | method、legal、reviewed_by和技术证据 |
| `bddl_sha256`, `model_xml_sha256` | 任务与reset模型身份，真实LIBERO必须提供 |

XML哈希绑定reset后、编辑前的模型，防止同长度state装入错误模型；炉子视觉状态可能改变候选呈现后的XML，不能将其混作reset身份。精确XML包含资源路径，迁移目录后需重建/验收，不能改哈希绕过。

环境指纹包含LIBERO Python/BDDL、仿真包版本、控制频率、资产实际内容与相对路径、兼容规则和源码哈希。它是部分环境锁，不能代替驱动、完整依赖环境及其他外部资源记录。

`remaining-observation-npz-v1` 保存原值、原dtype数组和uint8 JSON结构，加载禁止pickle。构造 `initial_observation` 相对状态包；回放 `reset_initial_observation` 相对该audit目录。两份完整初态含双相机与本体，绑定文件SHA和观测内容SHA，能独立重算比较而非只信“passed”。

## 5. 恢复、观测和技术验收

[兼容层](../benchmark/remaining_goals/libero_compat.py)不修改已校验的官方Python文件。它局部处理旧 `collections.Iterable` 调用；reset默认最多重试50次且仅重试 `RandomizationError`。抽屉hard reset重建前核验并清空由BDDL生成的属性sampler，避免累积改变RNG消耗与fixture XML；soft/deterministic reset保留列表，自定义不匹配sampler报错。Windows准备通过官方macro hook与当前MuJoCo包自带DLL完成，并记录哈希。

只保存MuJoCo flattened state不够。控制器目标、夹爪Python隐态、执行器控制与观测缓存均使用同一恢复规则。严格匹配官方PandaGripper契约后，从手指qpos反算控制目标并同步 `current_action`/ctrl，不调用额外物理步；关节边缘仅裁剪控制目标，不改物理state。未知夹爪/执行器明确报错。

每个真实step后，环境桥接显式 `sim.forward()` 并强制刷新视觉状态和observable，不增加控制步。刷新前后物理state必须通过严格检查；forward对已归一化四元数的机器精度舍入按单独受限规则处理。该观测时序与官方缓存接口不同，需另跑本协议00，不能直接引用官方分数。

观测规则：`named-uint8-rgb-one-level-area-cap-v4-typed-initial-evidence`。初始和动态命名相机uint8 RGB允许每通道最大差1，变化像素数至多 `max(1, floor(height * width * 0.0001))`，256²为6像素；任意通道改变都算该像素变化，小图最少1像素特例可能超过0.01%。仅在刷新前后物理state严格一致时适用该容差。

初始非RGB观测、保存state、mask、XML和工件SHA保持严格检查；动态本体有独立的固定比较规则。RGB上限是登记的工程容差，不是实证误差上界，也不保证检出所有陈旧图像。策略图像不被替换，原始哈希、exact结果、差异像素数/比例/上限/最大误差和 `bounded_allowance_used` 都记录。

[验收器](../benchmark/remaining_goals/validation.py)先做steps=0静态门槛，再重新恢复同一状态并做默认150步HOLD检查：

- 每步官方目标向量与要求的mask一致，状态/速度/观测有限。
- 监测可动物体及目标关节region的位置漂移，检查机器人相对共同参考姿态变化。
- 接触穿透使用 `max(0, -contact.dist)`；若排除固定接触须明示并保留原始记录，当前build无接触排除参数。
- 返回与独立强制刷新观测满足上述规则，刷新不改变物理state。

默认位置容差0.005 m、穿透容差0.002 m、最大绝对qvel为0.01、机器人qpos容差0.002。后两者按各自由度原生单位，不能一概称m/s或rad/s。阈值必须在开发阶段登记，不能看测试模型成绩后调整。

HOLD为 `[0,0,0,0,0,0,-1]`，仅用于当前无人抓持起点的候选稳定性验证，不是普遍安全的VLA STOP。验收不证明物体方向、接触力、可见性、可达性或剩余任务接续。篮子/柜顶碗可能在画幅边缘，锅可能遮炉圈，腕图未必独立证明上炉或开关；非空图像或mask间不同图像不等于语义可判。

完整原始NPZ保存初始观测；每步保存哈希和诊断，PNG在初始及每50步等记录点保存，不是完整动态视频。构建预览旋转180°便于阅读，doctor保留原始相机方向；均不能替代模型预处理设置。

## 6. 构建与独立回放命令

先按 [README](../README.md)安装独立仿真环境。可以一键安装、doctor、构建及回放：

```bash
python scripts/bootstrap_remaining_benchmark.py simulation \
  --python python3.10 --phase all \
  --out data/remaining_goals_local --reports reports/remaining_goals_local
```

已有环境时构建两轨，或单独构建/回放主轨：

```bash
python scripts/build_remaining_ten_tasks.py \
  --out data/remaining_goals_local --reports reports/remaining_goals_local \
  --scenes 3 --start-index 0 --split val --workers 1
python scripts/remaining_libero.py build \
  --out data/primary_candidates --tasks all --scenes 3 --start-index 0 --split val
python scripts/remaining_libero.py replay \
  --manifest data/primary_candidates/manifest.candidates.json \
  --out reports/primary_replay --steps 150 --repeats 2
```

输出目录必须尚不存在。扩展轨用 `--tasks extension` 与独立目录；`--workers 2` 只并行两条独立suite子进程链，各自build→replay并有独立GL上下文。任一失败会取消另一未完成轨道并保留证据，集合不会标为通过。

| build参数 | 默认/含义 |
|---|---|
| `--scenes`, `--start-index`, `--split` | 每任务来源数、官方起始索引、来源划分标签 |
| `--settle-steps 80` | 基底和联合编辑候选的物理稳定步数 |
| `--validation-steps 150` | 各mask独立动态验收窗口 |
| `--max-candidates 24` | 有限联合候选上限，不保证合格结果存在 |
| `--velocity-tolerance 0.01` | 最大绝对qvel |
| `--robot-tolerance 0.002` | 机器人qpos相对起点/参考姿态限值 |

构建产物含 `construction_report.json`、`manifest.candidates.json`、`states/*.npy` 和 `validation/`下的静态/动态audit、初态NPZ及间隔PNG。无完整组通过时manifest可能为空；有不完整组命令返回非零，失败搜索不能从覆盖报告中删除。

独立回放从磁盘经 `LiberoGoalEnv.reset()` 恢复，默认同环境按00→10→01→11重复两遍，包含11→00跨遍切换，每条150个真实保持步且不调用模型。它检查完整mask、状态SHA、白名单内分量配对和白名单外共同状态、构造记录及初始观测工件，然后核验：

| 检查 | 含义 |
|---|---|
| `saved_state_exact` | 恢复state与保存state相同 |
| `initial_mask_exact` | 官方谓词与要求mask相同 |
| `construction_observation_matches` | 构造与恢复初观测按固定RGB上限及其他严格规则比较 |
| `initial_non_rgb_exact` | 非RGB初态严格相同 |
| 返回/刷新观测 | step0与动态帧均执行同一观测审计 |
| 动态验收 | 继续检查谓词、有限值、速度、漂移、接触和姿态 |

`--image-size`默认256，必须与构造一致。每episode×repeat的audit记录实际初态NPZ和差异；总 `replay_report.json` 绑定源manifest原始SHA/content hash、覆盖和逐条证据。目录mask编号不是语义mask：双目标编号00/01/02/03对应00/10/01/11，以 `initial_mask` 为准。

失败和错误保留并非零退出；回放成功只证明这份记录下的恢复与保持结果，不批准研究发布。集合报告和preview必须核对唯一episode×repeat、完整窗口与哈希，不能只相信顶层布尔值。

## 7. Rollout与STOP契约

1. 检查manifest、文件哈希、完整掩码及单suite身份；模型归一化配置与suite对应。
2. 恢复冻结state与控制器，刷新观测，无隐藏初始化物理步。
3. 验证step0 mask；不匹配记 `invalid_initial_state`，不当策略失败或成功。
4. reset模型缓存和runner队列，只向模型传白名单传感器与原始指令。
5. 非全满足初态执行H+W个控制步；全满足初态只执行W步。
6. 不因真值success或环境done提前结束；预算按环境步而非模型查询次数计。
7. 策略显式返回None表示STOP；之后进入吸收状态，不再询问策略，但逐步执行预先声明的保持控制，不冻结物理世界。
8. 记录每步动作、目标向量、STOP、调用数及异常；离线重算指标。

当前候选默认H=520、W=150，以manifest为准，正式比较前固定。H后首次成功不算预算内成功，W不是额外完成预算。模型输出单动作或chunk；runner每次最多执行登记的 `max_chunk_steps`，不把单步动作重复成chunk。

环境不猜安全HOLD。固定7D `hold_action` 必须附 `hold_contract` 并先验收；需要动态收尾的任务应实现明确控制接口。希望检查后恢复执行的方法应在策略内持续决策，不能过早返回None。六个当前适配器没有伪造STOP，也不读取真值替模型停手。

## 8. 指标与统计分母

step0是初态，后续每行是执行一次环境动作后的谓词值。C0为初始已完成目标，U0为初始未完成目标。所有deadline含H，所有窗口端点均包含。

| 字段 | 非终态定义 |
|---|---|
| `task_success_by_horizon` | 0…H至少一次所有目标同时成立 |
| `stable_final_success` | 预算内达成且H…H+W每步所有目标成立 |
| `remaining_success` | U0在预算内同时成立，且H…H+W每步成立 |
| `preservation_success` | C0在0…H+W每步成立 |
| `joint_success` | stable成功且初始成果全程保持；00的空保护集合不阻止成功 |
| `goal_regression` | C0至少一个目标曾变假，即使之后修复 |
| `regression_steps` | 至少一个初始成果失效的观察步数，每步最多一次 |
| `first_all_success_step` | 首次全目标成立，可能超过H；无成功为null |
| `explicit_stop_step` | STOP决策对应观察步，首次stopped行减一 |
| `n_steps` | 实际要求的控制步数，不含初态 |

11的 `remaining_success=null`，joint/stable要求0…W全部保持；它在step0已task_success。00的 `preservation_success=null`。`goal_regression`只针对初始成果，不是全部新完成目标的回退率。手臂移动或接触已完成对象本身不算失败。

这是严格逐步保护口径：短暂破坏后修复仍使joint失败；不忽略单帧谓词失效，不要求H前额外连续10步成立。谓词抖动、允许临时破坏等需要独立预注册协议，不在看分数后调整。

主 `partial_macro` 先在任务内等权平均partial masks，再在任务间等权平均。`normal_00`与`terminal_11`单列；任一期望task×mask完全无有效样本时valid macro为null，不静默删组。

`completed`只表示完整rollout，不表示成功；`invalid_initial_state`、`runtime_error`与missing分别报告。completed-only指标保留成功分子/有效分母；`conservative_joint_success`把错误和缺失留在expected分母中，是保守覆盖分数，不是合法状态上的模型失败概率。宏平均仍遵循任务/掩码等权。

汇总从trace重算，不信外部缓存metrics；拒绝未知/重复episode、错误类型、不完整或重复步、step0 mask不一致和混合运行身份。策略异常不能通过只保留成功文件来隐藏。

## 9. 运行产物、模型比较和发布

每次运行输出 `run.json`、manifest审计快照、`episodes/*.json`逐步轨迹、`episodes.csv`及`summary.json`。记录绑定manifest、policy、运行配置哈希和run ID；它是内部一致性检查，不是防伪签名。

run内manifest不复制状态文件，相对state路径仍属于原状态包。离线summarize不需要原状态，因此不能宣称它重新验证物理初态。当前策略rollout没有完整图像/视频；构造HOLD帧不替代VLA失败视频。

默认正式loader拒绝 `legal=false`。显式 `evaluate run --candidate-replay` 可在完整通过的独立证据绑定后运行候选pilot，并保留原始声明。正式发布需另审语义、可见性、支撑与剩余执行可行性，记录实际审查者/证据，另存release manifest；没有自动晋升命令，不能手改legal冒充审核。

先完成官方原接口00、本协议00，再解释10/01/11差异。各模型参考相机、训练数据和chunk不同，比较的是这些配置下的模型系统，不能单独归因为架构。主轨和扩展轨必须分开报告；官方90权重缺失时标未覆盖或明确迁移身份。

当前没有自动语义/可达性认证、干扰动作分类、重执行识别、聚类置信区间或跨模型配对检验。三个来源的小规模pilot不能支撑论文级稳定结论；统计应以配对来源组/任务处理依赖，不把同来源mask或重复回放当独立样本。

数据重建与可选证据包见 [data/README.md](../data/README.md)。工件阶段、`record_class`、失败记录和覆盖分母必须如实保留；公开仓库、归档完整性检查、研究数据审定是不同状态。
