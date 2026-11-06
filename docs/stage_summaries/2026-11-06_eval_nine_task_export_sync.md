# 2026-11-06：独立LIBERO-Remain-Eval同步九任务及二元合规报告

用户要求更新独立Eval库。同步已完成并以非force方式推送到[No1dry/LIBERO-Remain-Eval](https://github.com/No1dry/LIBERO-Remain-Eval)，release commit **`7ec012522fcf19ec31db59327ce1133c95e999be`**，父提交d2f6cf964b1089ab7f1e14b1ca683636d12d798c。不是只更新README的范围告示。

## 实际同步

- 正式范围九个LIBERO-10复合任务：官方ID0,1,2,3,4,6,7,8,9；每任务init0..9，mask10共90条。新增抽屉/双壶/微波炉，四个LIBERO-90退出主范围。
- 已验收core固定d8541ef4a4bb4cc2e34c95b10227ea5fcaddaff9，reporting固定cb8aca6aca0864bb9a304bdf2471b5025b371479；111个源文件逐字节复制，没有重写评分/构造/控制器/适配器逻辑。
- 导出包含nine_catalog/nine_cli/必要源制备与语义/reader；二元报告包及accepted_core.json一并发布。97个固定core文件SHA均匹配，所以报告loader可在此导出上验证固定core，不因新的Git仓库commit假称原源码变更。
- active配置新增plan90与九任务来源模板；默认console入口改为nine_cli。旧plan100/batch模板移到compat/legacy_0_1，Git历史保留原十任务版本；没有删除历史源码/原实验数据。
- 包装版本0.2.0，README/ADAPTERS/USAGE说明9任务、指标与模型接口；不复制研究/讨论/协作/阶段过程文档到Eval库。核心完整依赖中的legacy00/01/11/FINISH模块仍为SHA/reader兼容所需，不是默认训练或评测协议。

## 验证范围

15/15受影响CPU/fake通过（100%，0.34秒，0skip/error/failure），只检查九任务/90身份、范围漂移拒绝和二元映射/完整性语义；不运行全库或跨平台发布级测试。静态人口90/90、ID准确且全libero_10。原accepted core97及同步源111 SHA匹配；未改物理门槛/端点/动作接口。

原export_task033_eval的Git对象路径先遇本地partial-clone缺失promisor对象错误，失败记录保留；未宣称该ZIP生成成功。改从GitHub精确d854/cb8 commit归档取得同源文件，再核对全部97固定core字节和111源文件，未修改/绕过原exporter。这个文件获取故障不触发仿真/状态重建或X实现返修。

## 必须保留的能力边界

**本次完成的是九任务源码/接口/报告同步，不是新增通用90条batch driver。**

- 通用per-episode runner与OpenVLA/OFT/pi0/pi0.5/GR00T N1.7/UniVLA适配器可作为对接接口。
- 现成nine_cli仍是SOG10“旧六同模型结果复用60＋新三执行30”的参考流程；它拒绝population=all。不能只换runtime就宣称给任意模型跑了全90，也不能拿原OFT的旧六分数给别的模型复用。
- 新模型需90条新模型轨迹及兼容来源证据，通过通用API/自有driver执行；源码库不包含状态bank、模型权重或旧结果，未宣称他机来源已物理验证。
- 新默认主指标是10二元合规SR：已完成success→成功、已完成failure/unknown→不成功，原diagnostics保留；缺失/技术/证据错误不冒充模型0。当前table_drop仅诊断、释放和成果保持等判据全部同原固定core。00可作原生能力控制，但不作为本导出默认新增评测。

README与USAGE已明确以上边界，不为补一个新driver默默修改验收源码或发布假“通用就绪”。若后续需要通用batch，按用户方向另交X实现，不把本次导出当成已完成该功能。

## 备份、权限与下一步

Eval纯仓库不放此阶段文档；本记录提交源benchmark库并复制到本地research_archive/LIBERO-Remain/stage_summaries。release已跟踪文件归档/关键说明/来源清单在research_archive/LIBERO-Remain-Eval的本次发布备份，按实际源commit与GitHub读回/SHA核验、更新各自manifest。未删除任何原始数据/开放任务或自动合并X源PR。

九任务导出准备100%；真实新增GPU/模型/仿真/源准备/训练0。使用方可拉取新版，按ADAPTERS对接其他模型；所有真实评测仍由用户/实际使用方启动。037方法设计审阅不被本次导出自动批准或暂停，角色与预算不变。
