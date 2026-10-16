# 010 / Round 1 — X实现与软件交付

2026-10-16，submitted，待Codex审查。对应[任务010](../tasks/010_versioned_release_and_calibration.md)和009真实验收；这是观察旧pilot后明确注册的测量／校准新合同，不改写旧失败。X没有启动真实仿真、模型、状态恢复、物理标签、训练或任何新增rollout。Stage04未closed。

## 交付身份

- 已按010授权合并accepted PR #6，main合并SHA：`190629495001df9cf53e08d2f5c501ca22a9e7b5`。合并保留main的009真实结果与010任务文档；009已审生产实现未改。
- 010独立分支：`x/task010-versioned-release`，基于上述main；[PR #7](https://github.com/No1dry/LIBERO-Remain/pull/7)已提交，保持open、未合并。
- 实现SHA：`4521c53f22f670cc60e05d7aabac10403a75dfe8`。本文件与STATUS属于后续交付文档，最终SHA以PR head及PR正文登记为准。
- evaluation contract SHA：`7effc031c35a7dc95b68a0523d1a09a67787451fe4597f0188edc34f501493aa`。

## 实现范围与对应要求

| 要求 | 实现与证据 |
|---|---|
| v1保持、v2显式启用 | `evaluation.py`注册唯一方法／规则对；旧job v1/v2保持原路径，只有job v3传递新contract。v1双pad False、接触None、已知True均保留。 |
| 纯读完整几何证书 | `release_geometry.py`对全部对象collision与全部hand／pad计算world x/y/z区间union；box native halfsizes、compiled mesh全顶点，严格gap>2mm且原pinch>2mm。最大gap，同分x/y/z。 |
| 数值、覆盖与技术错误 | 区间外扩gamma(16)+nextafter，gap向下舍入；检查完整geom组、mesh、pose、mask、pairs/excludes、weld/parent/options/margin/gap/callback。合法不支持保留None并记录coverage；缺失／错配／非法／非有限值单列技术错误。 |
| 缓存／只读约束 | 当前sim/model/raw model代际及静态数组／mesh／分组摘要核验；reset新建observer。XML初始化读取一次，逐帧不序列化XML、不增加step/forward/controller/render/RNG；callback只读取已加载模块的现有getter。 |
| 同轨迹双测量 | 每episode一次`measurement_static`，逐帧保存必要geom位姿、旧truth与新证书。schema及read_run离线重算，不能只信certificate=True；XML与冻结源episode绑定。 |
| 新校准 | `calibration_v2.py`保持首hit与固定5分母；tau两端仅替换None作时机假设，known值不动。零premature／unknown_first_hit／timing_unknown，最大化robust timely，同分高阈值，有用数须>0。 |
| 版本／阈值／来源绑定 | job→plan→env→raw／evidence→read_run→metrics／calibration→active显式分派。错误方法、head、域角色、旧未校准、派生报告都拒绝。实际adapter阈值须在接受首动作前匹配plan；离线逐query再核对，源state SHA／task／seed进入v2证据绑定。 |
| 2×2敏感性 | 独立`sensitivity`命令只读本轮新5条，v1/v2测量×legacy/new规则，同概率／网格／分母。全部`sensitivity_only=true`、`active_eligible=false`、正式threshold=null；诊断候选独立字段保存。 |
| 主指标／控制保持 | 仍为合规FINISH成功率，旧延迟及失败原因保留；v2增加timing_diagnostic。FINISH、W150、初始成果、错物K4不放宽；shadow主分数N/A，技术错误／缺失单列。normal能力汇总使用robust timely。 |
| 预算与配置 | 新budget-plan显式`--revision task010`：5旧+5新+10normal+15Remain=35，最坏23450步；剩余30、20100步。默认旧budget输出保持，v3禁止额外Remain shadow。3个模板与逐阶段runbook已提供。 |

完整实际版本／字段读写表及11个可解析CLI入口见[运行手册](../../docs/finish_versioned_release_runbook.md)。配置在[versioned_release](../../configs/remaining_goals/finish/versioned_release/)。`model.py`、`training.py`、`oft.py`、adapter、标签合同、旧cache/head和物理来源身份均无实现diff；不重建bank，不把旧头伪装成按v2重训。

## tau判定依据

固定known值、仅补全None时，全True补全的最早稳定起点不晚于任意补全，全False补全不早于任意补全。因此两端有限时所有可能tau在`[tau_low,tau_high]`内；保证每种补全及时恰需`tau_high <= f <= tau_low+24`。区间外可证不及时，不把它改成premature；重叠而无法保证则timing_unknown。两端均无参考时False；一端无参考保守标unknown，不拿有限端通过。未触发的及时性恒False，当前False／None按首hit优先分流。小规模三态穷举与边界反例测试核验此结论，未生成新的物理标签。

## CPU/fake验证

最终冻结代码全库回归：**2115 passed、16 skipped、0 failed，321.34秒，exit 0**。其中新增130 passed／1 external-fixture skip；旧FINISH 602项及009诊断155项全部通过。新增四个文件另做定向最终回归：**130 passed、1 skipped，78.44秒，exit 0**。统一使用当前Windows已有CPU解释器，未安装或升级依赖，未创建真实MjModel/MjData或加载研究模型／head。

16项skip全部披露：4项Windows符号链接权限／POSIX环境限制、11项可选pinned simulator源码检查、1项缺009原始侧录的外部fixture。首轮全库曾有6项新fixture回调状态不一致失败，仅修正CPU fake明确无callback的声明；生产校验未放宽，之后整库重新运行取得上述最终全绿结果，不用定向成功冒充整库通过。

JUnit SHA-256：`task010_full_final.xml`为`bd7738e1b59c069f0268cd5a48043530e2c95c004e2aedf060bd8d96358b91d5`；`task010_new_final.xml`为`6e9ad1976cd529f24706abd5cbb502e4a7d93af794e36b52f98ad1a7b80ef0ac`。JUnit与fake产物保留在本地忽略目录`reports/`，不上传实验产物。代码／文档diff检查、相对链接与冻结模型／训练／物理代码无diff检查通过。

```powershell
$py010 = 'C:/Users/robot/Desktop/Learning_Not_to_Act/Learning_Not_to_Act/.runtime/remaining_libero/venv/Scripts/python.exe'
Set-Location 'C:/Users/robot/Desktop/Learning_Not_to_Act/Learning_Not_to_Act/.release-work/LIBERO-Remain-task010'
& $py010 -B -m pytest tests -q --basetemp=reports/task010_full_final_tmp --junitxml=reports/task010_full_final.xml
& $py010 -B -m pytest tests/test_finish_calibration_v2.py tests/test_finish_calibration_v2_records.py tests/test_finish_release_geometry.py tests/test_finish_versioned_workflow.py -q --basetemp=reports/task010_new_final_tmp --junitxml=reports/task010_new_final.xml
& $py010 -B -m benchmark.remaining_goals.finish.cli budget-plan --revision task010
```

定向覆盖完整真实几何函数的CPU fake五条shadow→原输入／视频／双测量保存→read_run→正式校准→2×2→10条fake active及15条Remain来源计划。GT变化不改变policy输入、动作字节、FINISH应用时序或hold；缺帧／改pose／legacy truth／静态XML／state SHA／阈值／head／来源／版本等不通过读取。错误adapter阈值在首动作前技术暂停，n_steps=0，保留固定missing；timing_diagnostic=None不会导致技术失败汇总再崩。

## 尚未实测的外部fixture

本机没有009原始`static.npz`和`native/0280.npz`，所以**未完成010 §6.3的原始实数据CPU复算**，不把合成反例当作该实测。已提供固定原SHA的外部fixture测试，路径与完整命令见[运行手册末节](../../docs/finish_versioned_release_runbook.md#009实数据的纯cpu外部复核)。保存备份的Codex可以只读文件完成这项核验，无需真实native／模型；旧run及其uncalibrated结果不改。该项缺失不应被“其他测试通过”掩盖，审查时请单独记录。

新方法的软件测试不证明所有场景释放正确或停止能力已建立。callback无法核实、合法未支持几何／过滤配置继续coverage unknown；明确只支持已证明的当前box/mesh范围。真实runtime测量覆盖和计算开销仍须在经审查后的新阶段结果中观察，不能提前宣称实测。

## 下一步与实验边界

Codex先审查本独立PR并用已保存009备份补做上述纯文件核验。验收后由Codex部署新目录、核验原head／runtime／registry／bank、填写本轮私有模板并交付唯一下一真实命令。用户单独启动新5条shadow；离线新校准若未建立有用候选，停在分析。只有新阈值冻结后，分别独立启动10条normal active和15条Remain，不能用后两组挑阈值／方法／head。

原5条是探索性问题发现，新5条同来源是校准开发，不是独立泛化证明。旧calibration ac4cd37c…的false/null保留，原6636f713…head仍按v1标签训练。X未运行、排队或自动重试真实阶段，不合并010、不清理任何交流或原始产物；精确待删=[]。
