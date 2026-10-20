# 014：为独立mask10评测库增加真正的通用VLA批处理入口

日期：2026-10-20。需求方：用户；研究决策与需求：Codex；实现：X。
状态：待实现。没有真实实验启动授权。

## 目标与仓库边界

用户要求把项目复制为干净的评测仓库，交给其他人运行其他VLA。目标仓库：

https://github.com/No1dry/LIBERO-Remain-Eval

该仓库已复制验收源码、十任务mask10计划、评测核心、模型适配器、配置模板和CPU/fake测试；没有复制研究计划、讨论、协作历史、阶段文档或原始结果。源代码来自原仓库已验收的c6dc98de0c54517c976057598b60f4cedf7fa3e5。

本工单及后续响应/审查仍放在本仓库LIBERO-Remain的collaboration，**不要把过程交流文档放进新的评测仓库**。实现以新仓库PR交付，不自动合并；不修改原仓库既有实验入口或结果。

## 具体问题，不是偏好性重构

新仓库现在的 headless.runner.run_episode 是模型无关的，但现成100条批处理不是：

1. headless/planning.py:load_config 调用 regression._validate_config、validate_sog10_pair，强制原始SOG10 OFT。
2. headless/workflow.py:shared_model_identity 强制libero_10_no_noops；初始化、运行与读取结果均调用OFT专属validate_policy_metadata。
3. headless/metrics.py的说明文字含SOG10扩展身份，不能把该文字原样套到任意模型。
4. 旧evaluation.py虽然支持六个model_id，但采用旧H+W/STOP协议，不能当新版mask10通用评测的替代。

因此，只替换JSON无法达到“别人跑其他VLA”的目标。此次只解决这个实际功能缺口，不设计新训练、规划器或指标。

## 实现范围

新增显式版本化的通用mask10批处理契约与CLI。建议独立模块而非移除旧OFT保护；保留参考OFT工作流可读取原有结果。

公开命令必须包含：
- 文件级计划/配置检查；
- 用户启动的真实运行；
- 读取已有输出的inspect/summarize。

命令名和具体schema由X统一确定并在交付中列清，但需满足下述语义。

### 任务与来源

- 冻结已有十任务，官方init索引0..9，全部mask10；不加入00/01/11模型评测。
- 复用现有headless.planning的计划与source_plan，以及MASK10_ACCEPTANCE来源证据；不得要求无关mask通过作为新增前提。
- primary六任务与extension四任务允许分轨运行。不因extension缺少兼容checkpoint阻塞primary。
- 计划清楚保留请求范围和缺失项；未配置模型、准备缺口、运行错误不算模型失败，不私自换来源。
- 已有状态/回放有效时直接复用，不为新入口重新构建状态或重跑物理检查。
- 内部00构造基准与既有构造器保持，不为“mask10-only”重写状态生成。

### 模型配置与适配

- 支持每suite明确配置独立runtime，保留解释器、factory、checkpoint来源、实际模型元数据及种子。
- 不要求model_id等于openvla_oft，不要求统计key是libero_10_no_noops。
- 至少允许已有六个adapter factory以及自定义factory；不能用六模型白名单阻止别人接入新VLA。
- 工作者仍复用SubprocessPolicy；不要重写通信协议、把所有模型依赖塞入仿真环境。
- 普通同suite配置不套SOG10双轨校验。模型自己的归一化、processor、action decoder、动作坐标和夹爪规范保留其adapter约束。
- 跨suite必须显式说明真实checkpoint训练域和归一化来源；没有可用权重就标缺失/不支持，不给所有模型静默回退OFT统计。
- 不伪造其它模型的metadata；不知道的字段如实为空或声明未知，不填成OFT。
- 不自动下载、加载或执行真实权重验证“兼容”。

### 原评测语义不变

直接复用现有headless的：
- environment、geometry、roles；
- runner与schema；
- evidence与mask10 source acceptance；
- 成功/失败分类与TCP路径计算。

H520、20Hz、K4五观测确认、评价端完成即结束、已完成成果保持、sticky错抓/错放/严重掉落、完整双相机视频及逐控制步路径保持。无需FINISH或保持段。

动作执行cap使用现有runner允许的1..8，配置中明确记录；返回更长chunk仍按runner既有截断语义记录返回/接受/执行长度。不要为此扩展核心schema或把模型原生horizon伪称为8。

若通用化需要修改说明文字或身份封装，可以最小修改，但不能改变现有指标公式、几何判据或原结果解释。旧OFT证据仍由旧reader读取。

### 输出与读取

- 为通用批处理使用独立版本身份，记录请求范围、源证据、实际runtime和checkpoint。
- 同一次批处理允许不同suite使用明确不同模型配置；不得仍强制两轨同一SOG10。
- 新输出目录，不覆盖旧目录；已有不完整/错误记录保留，不自动重试真实episode。
- inspect/summarize只读已有文件，不新建环境或调用模型；不能仍因其不是OFT而拒绝。
- 逐任务成功率报告百分比与n/N，成功条件平均路径及覆盖；各suite分开，混合统计标明权重。
- 报告如实描述实际模型训练域；LIBERO90不一律写成SOG10 zero-shot。
- 结果归档保持源、视频、动作、观测与证据对应关系，不降低真值隔离要求。

## 对外精简

更新新仓库README与ADAPTERS：
- 通用mask10主命令成为别人运行其它模型的推荐入口。
- 给出一个已有非OFT模板和一个自定义factory的完整配置/命令示例。
- 不把示例或fake测试说成真实模型已跑通。
- 旧参考OFT入口明确标参考；不要引导用户使用旧H+W/STOP协议。
- 只保留使用说明、接口和必要归属声明，不新增计划/讨论/阶段/协作目录。
- 若需要配置模板修改，使用中性路径，不包含用户服务器地址、密码或本机绝对路径。

## 精简CPU/fake验收

定向检查以下直接影响结果正确性的路径即可：
1. 非OFT及自定义factory能进入通用配置、计划、运行、读取；不触发OFT专属统计断言。
2. 两suite不同runtime身份如实保留，无隐式跨域归一化；primary单独请求不被extension缺失阻塞。
3. 非mask10被拒绝；策略输入仍仅原完整指令、图像与本体状态，无mask/对象/目标GT。
4. chunk cap 1/5/8及长chunk截断；完成在chunk中途立即按原端点结束。
5. 模型无关封装不改变已有成功、错抓sticky、成果回退、unknown/technical/missing、逐步路径判定。
6. 保存和离线读取身份一致；非OFT inspect/summarize可用；不覆盖、不自动重跑。
7. 端到端fake批次可产出视频替身、动作/观测证据与报告；不会加载torch模型或创建native仿真。

复用已有fake fixtures，不要求全库、多平台或发布级检查；不新增任何GPU实验、真机、状态回放或训练门槛。

## 交付

- 新仓库PR，清楚列出改动和定向CPU/fake结果。
- 最简可用配置与完整运行/汇总命令。
- 在本仓库collaboration/responses中对应014说明尚未真实执行的模型。
- Codex审查通过后由用户或接收方亲自启动真实评测；X/Codex不自主启动、停止或追加实验。
