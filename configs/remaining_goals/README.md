# LIBERO-Remain 运行配置与研究元数据

本目录有两种用途，不能混用：

| 位置 | 用途 |
|---|---|
| [`runtime/`](runtime/) | 六个实际adapter factory的运行示例；复制到local并填写环境/权重路径 |
| [`plans/libero10.example.json`](plans/libero10.example.json) | 六模型主轨批量计划，路径相对plan文件 |
| 根层六份JSON | 研究元数据模板，用于归档checkpoint、预处理、依赖和回归证据；不是evaluate运行配置 |

安装与命令见[六模型指南](../../docs/remaining_goals_six_model_evaluation.md)，任务、恢复、指标见[协议](../../docs/remaining_goals_benchmark.md)。模型权重和本机环境不在仓库中，接口实现不代表权重已经运行。

LIBERO-Remain 是 Learning_Not_to_Act 的评测贡献，关注部分任务已完成时的剩余目标完成与成果保留。

## 使用已有模型环境

在仓库根目录复制对应运行文件，例如：

```bash
mkdir -p configs/remaining_goals/local
cp configs/remaining_goals/runtime/openvla.json configs/remaining_goals/local/openvla.json
```

填写 `runtime.python_executable`、`adapter_options.repo_path`、`adapter_options.checkpoint` 为本机路径，推荐绝对路径。保留已核准源码revision，`suite`与`adapter_options.suite`必须一致。UniVLA还需action decoder；GR00T需checkpoint_suite；π0需自行提供匹配 `pi0_libero` 配置的已复现微调权重。

`execution.max_chunk_steps`默认分别为OpenVLA 1、OFT 8、π0/π0.5 5、GR00T 8、UniVLA 1。`execution.random_seed`与adapter层seed必须一致；worker会按episode重置Python/NumPy/已导入PyTorch，OpenPI独立噪声序列的范围另记metadata。

```bash
python scripts/remaining_libero.py evaluate check \
  --config configs/remaining_goals/local/openvla.json
```

`static_configuration_ready`只说明静态配置检查通过，不加载模型、不证明能力。接下来必须probe、原始官方00回归、本协议00控制，再解释partial结果。切勿在配置中保存令牌或密码。

## 两条轨道

六个LIBERO-10主轨任务与四个LIBERO-90扩展任务分别构建状态包、配置checkpoint/归一化并单独报告。不能仅修改suite字符串就声称模型完成适配；没有保证六家都有官方90权重。

OpenPI固定四套微调权重用于90时，必须显式 `adapter_options.evaluation_track="zero_shot_extension"` 并修改两处suite。该身份进入metadata；不能称为90微调基线。其他自定义90权重需要独立来源、正确归一化和匹配adapter。缺少覆盖就如实报告，不合并两个suite分数。

## 研究元数据模板

根层六份JSON的未知值为null，`is_template=true`。它们为正式归档准备更完整的证据，不是模型权重，也不自动改变随机数或实例化factory。

```bash
python scripts/check_remaining_baseline_config.py \
  configs/remaining_goals/openvla.json \
  configs/remaining_goals/openvla_oft.json \
  configs/remaining_goals/pi0.json \
  configs/remaining_goals/pi05.json \
  configs/remaining_goals/groot_n1_7.json \
  configs/remaining_goals/univla.json
```

退出码2表示仍有未就绪配置，可用 `--out reports/baseline_readiness.json` 保存报告；输出须尚不存在。相对证据路径以仓库根为基准，可用 `--base-dir`替换。

| 状态 | 含义 |
|---|---|
| `template` | 有效模板，未声明可运行；列出缺失项 |
| `incomplete` | 非模板缺必填内容，或身份/结构/证据哈希不正确 |
| `ready_configuration_only` | 元数据与文件引用完整，不等于模型或研究已验证 |

核验器不import factory、不加载权重、不解释报告成功率；输出明确 `model_validation_claim=false` 和 `evidence_content_assessed=false`。应记录：

- checkpoint来源、不可变版本、各权重分片清单与哈希、归一化资产哈希。
- 模型代码commit、adapter源码哈希、suite和训练数据覆盖。
- 实际相机方向/裁剪/颜色/尺寸/归一化，本体字段顺序与转换；未使用本体时明确说明。
- 7D平移/旋转/夹爪映射、输出反归一化路径、STOP行为和原生执行chunk。
- seed及作用范围、精度、独立依赖环境/解释器/锁文件与哈希。
- 官方原接口00与本协议00各自的任务/初态/预算、结果、报告路径/哈希和审阅摘要。

不得用猜测的归一化key、夹爪符号或chunk补齐；identity映射也需说明依据。官方成绩与新协议00不能互相替代。

## 自定义factory契约

factory接收完整JSON，模型具体参数建议放 `adapter_options`。返回对象提供 `reset()`、`predict(obs, instruction)` 和可选 `close()`。predict返回已经转换为环境控制坐标的 `(7,)`、`(T,7)`，仅有主动停止语义时返回None。

模型输入限白名单传感器与原始完整指令，不读取manifest、mask、谓词或对象真值。runner管理动作队列；STOP后继续执行预先验收的hold控制。

高层 `evaluate run` 从运行配置读取factory和chunk；低层 `benchmark.remaining_goals.cli run` 仍需显式传入 `--policy-factory`、`--policy-id`、`--policy-config`、`--max-chunk-steps`，不会从研究模板自动推断。候选pilot还需完整独立回放证据，不能把 `legal=false` 改成true绕过正式审查。

录像通过运行命令显式启用：`--save-video --video-fps 20 --video-camera both --video-stride 1`；`evaluate run/matrix`和低层 `cli run/demo` 使用同一组选项，默认关闭。相机可选 `agentview`、`wrist`或`both`，不应把录像参数放入 `adapter_options` 冒充模型预处理。录像读取已有观测、不额外step/render，各episode JSON关联run内 `videos/*.mp4` 的录像状态。
