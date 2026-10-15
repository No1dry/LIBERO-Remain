# Codex：008 Round 4——历史示范XML资源根兼容P1

2026-10-15。**changes_requested，仅实际XML资源路径兼容错误；R2初始化顺序修复结论保留，不改两域研究设计。** 当前9ddd40f2968ed5dc3d0e0be59db00b8e91d28e5c在第二次用户真实audit被首帧XML路径阻塞。此P1验收前暂停PR #5合并及同版audit重跑；不覆盖原失败out/log。

## 已核实际结果

status=insufficient，command_exit=2/tee_exit=0；provider_identity已完整建立，restore_attempts=1、rows=0、hold=0，无标签/类别覆盖、无VLA/模型成绩。初始化P1确已越过，本次不是原current_action错误。

确切错误：
`demonstration XML references an unavailable asset: /home/yifengz/workspace/libero-dev/chiliocosm/assets/scenes/../textures/seamless_wood_planks_floor.png`

9ddd服务器原始报告SHA `ad035bc1168bcade689e5a7f527d923abd5d44d32abfb0c81a8fbaf449d46fbd`；日志SHA `dde9517edd48e62223f20853ac9f1c27cd27320a175096d2f0711c4462cc0ae5`。两份已本地下载并逐SHA一致。

固定LIBERO8f1084的envs/utils.py::postprocess_model_xml只识别独立path segment为robosuite，或demo_generation=True且为libero；libero-dev/chiliocosm并非独立libero段，故现有_processed_demo_xml的cwd处理无法重定位该根。

## Codex已完成全部50实际XML的纯文件检查

[实际资源库存与候选文件SHA](../../docs/stage_summaries/evidence/stage04_task008_xml_assets_2026-10-15.json)。不是替代物理audit，也尚未应用映射。

- 50/50实际HDF model_file XML，4450个file引用出现：texture750、mesh3700。
- 去重87个原路径；其中63个robosuite路径可按原官方语义重定位，24个chiliocosm/assets旧根需要补充别名；87/87（100%）候选在固定本地资源根中存在且contained，未解析候选0。所有87个引用均在50条轨迹中出现。
- 当前只出现mesh/texture file属性，没有include。compiler为angle=radian、meshdir=meshes/、autolimits=true；实际file引用全是绝对路径。不要为并不存在的include构造新系统，未知依赖可整体报unsupported，不能跳过。
- 候选仅按完整资源相对suffix映射并规范化，未按basename搜索，没改HDF/XML/资产，没有创建/home软链，没有仿真/restore/render/模型/标签。
- 这是“当前固定官方runtime中对应suffix文件存在且SHA已知”，**不声称与不可访问的作者旧机器原文件逐字节相同**。

## 最小修复与边界（一次落实）

1. 复用官方robosuite/libero映射语义，并显式支持已核历史根`/home/yifengz/workspace/libero-dev/chiliocosm/assets/`→固定LIBERO包assets根；可合理设计版本化alias规则，但必须已声明根、完整相对suffix，不用任意substring、basename全盘搜索或猜文件。
2. 允许scenes/../textures这类规范化后仍落在批准assets根内的路径；normpath和symlink resolve后严格contained。未知根/绝对逃逸/根外..或symlink/缺失/歧义继续明确失败，不能被旧路径恰好存在绕过固定资源绑定。
3. 原HDF与原XML字节/SHA不变，只在传给MuJoCo的内存XML中改批准file路径；material/texture参数、mesh缩放、几何/物体、joint、pose、camera等非路径结构/属性不改，不能替换纹理、移除元素、换场景或跳存在检查。
4. 运行时和纯CPU文件扫描共用同一个resolver，**在创建provider前一次扫描全部50 actual XML的依赖**，聚合全部缺失/未知/越界项，避免修第一张再让用户撞下一张。可复用audit-plan/register/audit的数据准备入口或纯文件函数，不要求新增CLI/依赖/通用框架；现有默认CPU/help不能导入真实仿真或创建环境。
5. 记录resolver版本、实际原XML/hash、批准根及每条old→new/目标SHA、全量覆盖和未解析项到现有审计/纯文件报告中，保持metadata不进模型。不把文件扫描标ready；后续物理layout/restore/release/K4及label未知规则不变。缓存/头仍绑定实际audit/data/source身份，不接受文件改变后静默复用。
6. R2初始化两处顺序、严格Panda/OSC/hold、source分组/stride1313帧、head训练/阈值/指标全部不改。不加step、settle、重采、不换checkpoint、不给GT停车。不要在/root/home或作者/home创建假根软链来绕过实现问题。

## CPU/fake回归与交付

X不跑真实sim/VLA/科研训练。用真实旧路径字符串、tiny资源文件及受控XML测试：

- 此次完整旧纹理路径、24类旧mesh/texture目录模式、正常robosuite/libero路径；完整suffix保持，同名texture_map.png在不同对象目录不能互换。
- 根内..允许，根外..和symlink逃逸拒绝；缺文件/未知根一次聚合，不在第一个错误处停止清单；XML非路径结构/属性、原HDF/source XML字节不变。
- 扫描与_processed_demo_xml使用同一resolver，不只是另写一个宽松report让文件检查过；不创建环境的纯文件入口可验证。
- 保留实际provider生命周期21项及既有FINISH/全套回归；报告真实passed/skipped原因。
- 当前这87个原路径及目标相对suffix/SHA清单作为可核真实形态证据，不需要把大资产或示范state提交GitHub；Codex部署时用实际HDF再做全部50 XML文件扫描，目标是未解析0，不声称保证后续物理audit必过。

交response008_round3、固定实现/最终SHA、最小diff/测试/候选audit命令。只处理本兼容P1，不重做训练设计。Codex验收新不可变目录部署并完成全量纯文件检查后，用户仍只启动同一真实audit、新out/log；**不新增单独11预检、不下载HDF、不新增VLA采集**。文件扫描不能替代真实标签充分性检查。原9ddd与b596失败、4f通过全部保留，不删除交流。

下一步执行者：X补受限资源重定位与全量文件检查；Codex审查/部署/实际50XML扫描；用户启动原audit，充分后进入feature/训练。
