# Stage04 数据准备记录：文件已补齐，来源映射尚未建立

2026-10-14，Codex。本轮用户明确将准备工作交给Codex，用户只负责亲自启动真实实验；X仍负责benchmark实现。本记录不把文件准备写成真实预检／训练完成，也不改变已验收007源码。

## 已完成

官方basket演示HDF5已下载到：

`/HUBU-AI096/zp/ICML/stage04_finish_38e6a44/assets/libero_10/LIVING_ROOM_SCENE2_put_both_the_alphabet_soup_and_the_tomato_sauce_in_the_basket_demo.hdf5`

官方仓库`yifengzhu-hf/LIBERO-datasets`，固定revision=`147fa5eb607bb696dd922c3518084a90954cd2f3`。服务器直连HuggingFace超时，使用hf-mirror仅作传输端点；下载后本地文件大小1467540242 bytes及SHA-256=`3173ebc709b064683956b757ae8737909457d730aa305b23c5735292e59066af`均与已核官方文件身份一致，未换数据版本。[官方固定目录](https://huggingface.co/datasets/yifengzhu-hf/LIBERO-datasets/tree/147fa5eb607bb696dd922c3518084a90954cd2f3/libero_10)、[原上传文件指针](https://huggingface.co/datasets/yifengzhu-hf/LIBERO-datasets/commit/e329580e402fb5f07ae3b1f18475fc3b63783b91)。

纯文件预检结果：

| 项目 | 已核结果 |
|---|---|
| HDF5 trajectory | 50条 |
| saved states | 合计14700个，float64，每个123维 |
| actual model XML | 50/50非空且可解析为mujoco XML |
| 官方.pruned_init | 50个123维初态，可按受限CPU加载读取 |
| HDF5首state→官方init完整精确匹配 | 0/50；没有建立source map |
| HDF属性init_state | 50/50等于本trajectory首saved state；匹配官方init仍0/50 |
| 仿真／restore／hold／标签／VLA／训练／rollout | 本轮全部0 |

此次使用`audit_demonstrations(..., provider_factory=None, out=None)`做文件hash／source inventory，故没有真实audit目录，也没有构造provider。另只做CPU数组差异诊断；去除首scalar也不能产生精确匹配，差异不限于时钟。最近邻只供诊断，没有转成source_index，没有填manual confirmation。

## 当前前置问题与已核证据

文件本身没有hash损坏、字段缺失或XML缺失；**不能直接证明公开demo与当前official init来源编号对应**。默认train5..34、validation35..39、normal40..49、Remain0..4的同源整组设计，目前不满足训练前提。代码正确返回insufficient：50项source_mapping_unverified和1项group_source_coverage_incomplete；没有新的模型成绩。

已读官方固定代码ref=`f78abd68ee283de9f9be3c8f7e2a9ad60246e95c`，不是替换服务器固定LIBERO8f1084：

- 官方采集每条reset，并按采集目录遍历计数命名demo；该脚本没有选择.pruned_init编号的流程。不能从demo数值推出eval init数值。[collect_demonstration.py](https://github.com/Lifelong-Robot-Learning/LIBERO/blob/f78abd68ee283de9f9be3c8f7e2a9ad60246e95c/scripts/collect_demonstration.py)
- processed数据脚本跳过前5步、裁剪states后重新命名demo，并将裁剪后的第一state写入init_state。因此该属性不提供更早采集初态；当前HDF实测50条属性均与首state相等，不能靠它补映射。[create_dataset.py](https://github.com/Lifelong-Robot-Learning/LIBERO/blob/f78abd68ee283de9f9be3c8f7e2a9ad60246e95c/scripts/create_dataset.py)
- benchmark API分别给出task HDF路径与.pruned_init，没有提供demo→init对应表。[benchmark API](https://github.com/Lifelong-Robot-Learning/LIBERO/blob/f78abd68ee283de9f9be3c8f7e2a9ad60246e95c/libero/libero/benchmark/__init__.py)

这些证据支持“不应按编号猜映射”，**不证明演示与eval初态完全独立随机生成或绝无共享采集来源**。没有真实记录就不宣称来源隔离已经成立。

不通过放宽状态匹配、最近邻、去掉时钟、随机分单帧、借test、伪造collection_provenance来继续。也不把资产前提不足当X必须返修的软件错误；007软件accepted裁决保留。

## 当前可启动与不可启动

已有Remain source001的11物理preflight独立于这个HDF映射问题，可以由用户启动：

```bash
ssh root@122.204.216.104 -p 30369
bash
source /HUBU-AI096/zp/ICML/stage04_finish_38e6a44/session.sh
finish_sim 01_preflight_11 preflight \
  --source-config "$CFG/preflight_source.json" \
  --episode-id basket_s000_11 \
  --out "$OUT/environment_preflight_11"
```

本命令才创建真实仿真、恢复已有状态和做4步hold；没有VLA forward。看preflight.json的status=recorded、error=null、trace0..4及goals/released/contact/geometry。它不是HDF标签审计，也不证明全部W150保持可靠。

**当前不启动HDF真实audit／feature／训练／校准／新eval。**真实audit使用当前空map也会先返回insufficient，无需让用户重复发现同一前置问题。Codex下一研究决策是：继续寻找真实采集对应证据，或提出明确的独立数据域／来源隔离修订供用户确认。若要改设计或新增可追溯采集，先确认范围与预算，由X实现必要代码；不自动改变现有分组、状态、原指令或预定集合。

用户不再需要下载或填写路径；Codex负责准备、配置核验和结果检查。真实阶段仍由用户确认并启动，Codex不自主重启或追加实验。

## 证据、保存与清理

服务器准备报告：`/HUBU-AI096/zp/ICML/stage04_finish_38e6a44/preparation/2026-10-14/file_inventory.json`和`state_identity_diagnostic.json`；下载日志：`logs/run01/prep_download_20261014.log`。本地副本在`/Users/zhangpeng/Desktop/Learning_Not_to_Act /reports/stage04_data_preparation_2026-10-14/`，没有额外下载大HDF到本机。

| 证据 | SHA-256 |
|---|---|
| file_inventory.json | `e3e6bb06db50826c5db50c55c722cd88f7315c8ac3a5c0d2de916496c28b368e` |
| state_identity_diagnostic.json | `d5fc19d41eb48745351a8d5119dd8e38afaf361f6786e6d3536f3e6724143228` |
| read_only_inventory.py（部署诊断，不是benchmark修改） | `2c2c01f92f9985d996be993b924de039cbdd8e50ea06e600567a6989d2dbfbfe` |
| prep_download_20261014.log | `d67cecbe2498922067c0c224ba613e32e19be91fc498e7e3ae67a2b4f24b67a7` |

HDF/初态/BDDL完整SHA及各trajectory state／XML摘要在file_inventory；官方init hash=`1899fe54c51e24a41d5f9e32254730d6777f4894ab68e0e873f1fa7ae2062030`，BDDL hash=`2e661058917f683a25bce480015197f0a2c1911bcbc2b9dd9d947199069c9618`。

源码仍38e6a44，194个文件和10个冻结部署文件复核通过，runtime／source map／split没有改动；结果run01仍空，旧原始实验数据不改。Stage04不closed，**待删清单为空**。本记录提交GitHub并备份到本地阶段总结、记录来源commit和SHA后核验；保留昨天的部署回执和历史runbook，不倒改历史“尚缺数据”记录。

下一步操作：用户启动已有11预检；Codex审查物理证据并准备来源分组问题的明确决策，不启动训练。执行者：用户启动，Codex准备／审查；X按确认需求实现。
