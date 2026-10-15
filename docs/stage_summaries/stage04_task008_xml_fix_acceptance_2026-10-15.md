# Stage04：008历史XML资源兼容验收与全量实际文件核验

2026-10-15。[R5裁决](../../collaboration/reviews/008_round5.md)：软件accepted，无进一步返修；008/Stage04未closed。X代码、Codex审查/文件准备/部署、用户启动真实实验的分工不变。

## 版本与软件证据

[PR #5](https://github.com/No1dry/LIBERO-Remain/pull/5)已测试实现201457a46dfbb8c84ba41416eec08ffb1b64163b；最终冻结089e0b7fa3916e6444b0880ca61101cac791c1ba，tree7aff772638ba75542e3fde4e5712a0c1ac8b9533。实现到交付仅STATUS/response文档。238文件逐Git blob/SHA核验；原脏工作区、依赖/权重和实验数据未动。

唯一生产范围：finish/xml_assets.py、environment.py、data.py、cli.py。精确历史根/官方资源段按完整suffix映射，规范化后contained、实际SHA绑定；只替换原XML批准file值，不序列化/改非路径字节。全50XML扫描先于provider，审计后及缓存加载重验。R2状态恢复/夹爪/Panda/OSC/保持/释放约束、两域/label/网络/阈值/指标不变。

Codex本地全套1688 passed/12既有可选skip（52.75秒，共1700）；并行resolver/provider97 passed、data/CLI92 passed；服务器19个FINISH文件457 passed/0 skipped（58.95秒）。本地skip为11个固定源码可选catalog、1个缺imageio_ffmpeg，非新增008 skip。

## 真实HDF文件检查已通过（不是物理audit）

源码：`/HUBU-AI096/zp/ICML/LIBERO-Remain-stage04-finish-089e0b7`。
运行/会话根：`/HUBU-AI096/zp/ICML/stage04_finish_089e0b7`。
238源码/9冻结部署文件已核验；沿用原sim/model venv与同一HDF/init/BDDL。

register-data在真实HDF上完成，exit0/tee0，registration=registered_file_only，scan=resolved：

| 检查 | 实际结果 |
|---|---|
| 全部实际model_file XML | 50/50（100%） |
| file引用解析 | 4450/4450（100%），87唯一原路径，未解析0 |
| 独立核对原XML/hash | 50/50与上轮真实库存一致 |
| 独立核对非file值的XML原字节 | 50/50完全不变 |
| 目标资源内容 | 87/87与前次候选文件SHA一致，4450次映射逐项核对 |
| 原HDF完整SHA | 前后均3173ebc709b064683956b757ae8737909457d730aa305b23c5735292e59066af |
| 物理标签/ready | labels0、ready=false，尚未真实恢复/生成标签 |

独立核验器首版02b误把安装目录相等当内容身份条件：63个robosuite文件在已使用的sim venv内，而前次诊断读的是base env副本；完整suffix和全部SHA均一致，没有素材差异。保留02b失败脚本/日志；02c改为完整suffix＋精确内容SHA＋approved-root containment，并通过上述全部检查。没有为此修改benchmark、资产或指标。两个检查都仅CPU文件操作，未导入native包/创建仿真。此路径差异与当前XML兼容软件bug区分记录。

## 证据与哈希

实际scan语义SHA `44d7a1c4cddb523fbda475bb16d4d28d3f8ab326790685977eb1ebacfed11f07`，文件SHA `705a44e6f41d5a172dc5819e50a8101b35430539b4f6dc623e495ba416f8cc03`。来源registry语义仍f8706e9018e618566f53165b50b8e21e6347c089a500cbe3bc21c0930ff8edfe，文件SHA18491d64d5bcc6dfef18dd97f8191aabb1577e111216d0e566a2ee8b1cd15581；分组资产不变。

源码tar SHA63caae87ba465f97441e9545a7cb3fa0fc5f7447f6792423817e62d151cbb736；部署tar c7a24243bf833237f6a289656a82b110c3a6173806694bc7665a022a21a568f5；配置manifest edbe001fb900517124bc3008b5a3379da619ade6bd54471b91ec09db2fc199e2。原OFT runtime仍75f2a711a39c58a07715b3a280aeba26a29dfbba70caf87cc051520f0a3f9720。

服务器JUnit/registry/registration/完整XML扫描/02_registry/02b和02c共7份证据已下载本地项目reports/stage04_task008_xml_fix_2026-10-15/evidence/并逐SHA与服务器一致；部署回执、独立检查脚本、本地JUnit、源码/配置清单同目录。服务器JUnit SHA71c4f8fef2173c96e9abe8b6a1822d43a7150407749b879a6be96823748b54e9；02c日志SHAb570fd8e2820f7205e3833fc03139844d905128190f7fc299d39dd8b7ed0c091。

## 下一步及边界

[新实际会话与逐阶段命令](../experiment_plans/stage04_task008_xml_server_runbook_2026-10-15.md)。用户只重跑原1313帧audit；旧b596/9ddd失败目录不覆盖。不再新增独立预检、下载或采集。数据充分后才进入feature/头训练；不自动串联。默认模型30rollout预算未消耗。

这是实际资源文件兼容通过，不是native XML编译/物理layout/restore/release/K4/类别覆盖或停止能力认证，不能承诺audit必过。素材来自当前固定runtime，未证明与作者不可访问原机文件逐字节相同；跨HDF/init物理祖源unproven仍保留。没有真实新label/feature/head/parity/calibration/eval或视频，没有模型新分数。

解除R4合并暂停，X可保留最新协议/Plan4/STATUS及R1..R5和已审实现合并PR并登记；Codex不代合并。007/008及Stage04未closed，交流和旧38/4f/b596/9ddd证据全保留；待删=[]。本轮总结/验收/命令/STATUS提交并本地按来源commit/SHA归档，无删除。
