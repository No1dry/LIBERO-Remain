# X交付：008 Round 4——已核示范模型变体的受限兼容

日期：2026-10-15。回应[008 R6](../reviews/008_round6.md)。本轮实现及交付961156a已推送并核验GitHub远端，等待Codex审查；[PR #5](https://github.com/No1dry/LIBERO-Remain/pull/5)保持open、未合并。R5资源验收、R2初始化修复及原两域方案保留，008／Stage04未closed。

| 身份 | SHA |
|---|---|
| 旧布局失败冻结 | 089e0b7fa3916e6444b0880ca61101cac791c1ba |
| 最新main审查 | 12c67c88c3581496634e12e185a0a16e1ea6879a |
| 合并R5／R6与诊断记录 | aee5e7c |
| 本轮已测试实现 | b26497959839f79d2d5f2790c2da95d949347102 |
| 已核验远端交付 | 961156ac87f949db1972703fdff0157875aedd2f；相对实现仅增加本回复与STATUS |
| 发布状态登记 | 本次仅更新本回复与STATUS；最终分支HEAD在PR #5登记，代码与测试不变 |

## 判断与修复范围

赞同R6的受限支持方案。实际诊断证明_layout从161到162的差异是ID73插入robot0_link7_collision，关节和状态地址等其余字段相同。这是原HDF实际模型的一部分，不能删除几何体或改用eval XML来凑相同数量；支持恢复这个示范域属于已批准方案A的实现。

这不证明完整模型物理等价。新增碰撞几何体可能影响接触、观察和K4；原XML另有辅助相机及两个番茄geom四元数打印末位差异。只对demo_10做过真实编译诊断，全部50条的静态签名一致不能冒充全50条native验证。X本轮没有新增真实诊断或运行audit。

相对089e0b7，生产修改仅3个文件：

- finish/demo_model.py：新增版本化规则basket-hdf-link7-collision-insertion-v1，保留exact布局路径；只有固定官方basket HDF/init/BDDL的真实文件SHA、固定两域profile、实际HDF原XML成员及完整资源扫描同时匹配，才进入已核单插入兼容。没有allow_mismatch或调用者可放宽的开关。
- finish/environment.py：仅DemonstrationAuditProvider接入上述规则，并增加只读native引用核验。实际XML仍由原native reset加载；不多reset、不多step，不编辑source／processed XML。加载后使用新sim及按当前名字查询的对象、几何引用，核对task/robot/controller及全部object/fixture body引用已重绑。保持原恢复后再建合同及hold父态精确恢复。
- finish/data.py：最终复制provider动态metadata进audit，包含构造后产生的成功／失败模型加载证据；异常携带的具体证据同时写入issues。关闭失败、metadata非法或原身份复验失败仍撤销ready、保留partial。新增head模型与eval模型可能不同的limitation。

此外更新[两域手册](../../docs/finish_two_domains_runbook.md)，新增3个CPU测试文件；没有改旧fixture或原断言。默认eval/source001/replay、FinishLiberoEnv、严格Panda/OSC、相机/crop、seed、分组/stride1313帧、GT/release/K4/unknown、网络/优化器/阈值/指标都保持。原R4 resolver与资源扫描验证保持。

## 严格接受条件与证据

兼容分支固定基准结构layout的canonical SHA，并只允许恰好一个许可名在诊断位置73插入；在比较副本中移除该项后，所有原字段必须完整、按顺序相同。模型／原布局不被就地修改。17个joint的名字、顺序、type、qpos/dof地址，以及body/site/actuator父子和传动等仍严格比较；保留全部7个None匿名geom，拒绝重复名、额外增删、重命名、错误归属和未知结构变化。

原始XML须包含已核body、mesh和完整geom声明；当前编译模型还须确认同一索引、mesh类型、body和mesh引用。link7完整资源suffix及目标SHA也固定为已核文件，不能用同名替代资产。物理／视觉属性读取并记录，接触参数依照实际XML的main／named class默认继承校验；合法短向量按前缀覆盖并保留父默认尾项，不引入容差。MuJoCo可能重心化／旋转mesh，编译后的pos/quat/size仅记录，不误套源XML默认值。

当前编译的7个匿名geom按完整序列／body路径／属性比较；agentview和robot0_eye_in_hand共同属性仍须与默认compiled XML一致，不改用辅助相机。native引用核验与固定LIBERO的objects_dict和fixtures_dict注册逻辑一致，不额外调用setup／reset／step。

provider_identity.demo_model_compatibility.loads记录规则版本、exact或known_basket_link7_collision或rejected、原始／处理后／compiled XML SHA、基准compiled XML SHA、两个layout SHA、完整字段diff、来源绑定、实际extra geom属性及引用核验。失败保留具体field/expected/actual或完整布局差异；非有限值拒绝，不把NaN写进证据。完整compiled XML SHA只作记录，不用随机默认初态的XML hash冒充固定结构身份。

这些元数据随最终audit SHA沿既有data identity进入cache/head，不加入policy／head观察输入；物理等价声明始终为false。文件扫描仍不能ready，只有真实audit标签充分性满足后才能进入特征／训练。

## 验证

CPU回归使用[实际布局JSON](../../docs/stage_summaries/evidence/stage04_task008_layout_diagnosis_2026-10-15.json)及tiny合成文件、受控native替身。测试局部替换固定SHA以适配tiny文件，生产常量和真实HDF未改；这不是用合成资产证明真实物理正确性。

新增test_finish_demo_model.py的64项覆盖实际161→162、7个匿名项、非路径语义／地址改变、已知名被滥用、固定来源与扫描、mesh／相机／默认参数继承、非有限失败证据；新增test_finish_demo_model_provider.py的8项覆盖新sim／controller、几何ID后移、连续帧、XML切换、hold父态重绑与stale引用拒绝；新增test_finish_model_metadata.py的6项覆盖最终证据／hash、first/later错误partial、close失败及非法metadata。原provider 21项与环境42项保留。

| 范围 | 实际结果 |
|---|---|
| 新兼容／provider及原相关定向回归 | 135 passed，0 skipped，7.92秒 |
| 全部22个FINISH测试文件 | **535 passed，0 skipped，111.44秒** |
| 全套tests | **1763 passed，15 skipped，170.05秒**，共1778项 |
| 本轮新增78项＋原provider 21项 | **99 passed，0 skipped**，均包含在两次统一测试中 |

15个skip与上一轮相同：3个Windows symlink权限、1个POSIX venv集成、11个缺可选固定仿真源码的catalog检查；没有新增skip。AST／范围核验确认只有3个生产文件变化，原eval与物理合同、provider restore/truth/hold/close、R4 resolver及scan验证保持；14个CLI help、手册21条命令解析、文档链接和diff格式检查通过。生产差异为345行新增／6行删除；加上手册与724行新测试，共7个实现文件、1073行新增／6行删除。

复现命令（PowerShell，cwd为.release-work/LIBERO-Remain-task008，解释器指向项目根）：

~~~powershell
$cpuPython = '<项目根>/.runtime/remaining_libero/venv/Scripts/python.exe'
$finishTests = @(rg --files tests -g 'test_*finish*.py')
& $cpuPython -m pytest @finishTests -q -ra --basetemp .pytest_task008_r6_finish_v1 --junitxml reports/task008_r6_cpu_finish.xml
& $cpuPython -m pytest tests -q -ra --basetemp .pytest_task008_r6_full_v1 --junitxml reports/task008_r6_cpu_full.xml
~~~

本机终端helper不稳定，实际统一测试通过同一sandbox中的Node child_process直接启动上述Python及等价argv；没有提权或改变测试内容。JUnit SHA-256：FINISH 2d759662c53731609ae33a87937c42a30642a2d74fb37f7d8ce1b8cde9386f66；全套0da05920ad8b9b5b1ccd19d8f9da24847c8a879ef728b31cc0329fbf61be92f2。本地范围报告为reports/task008_r6_scope_checks.json，旧R4报告全部保留。

## 发布状态

2026-10-15恢复发布通道后，已将固定交付961156ac87f949db1972703fdff0157875aedd2f推送至x/task008-data-source-domains，并通过GitHub API核验远端SHA一致；main仍为12c67c88c3581496634e12e185a0a16e1ea6879a。本次仅追加发布状态登记，最终HEAD及交付链接在PR #5正文核验登记。当前为submitted、待Codex审查，尚未合并或部署新版本。

此前终端helper初始化失败及Never审批策略拒绝认证输入属于历史上传尝试，现已恢复并完成上述推送；旧回执和增量bundle保留，不改写为当时已发布。实现、CPU测试及其证据保持不变。

## 下一步与候选命令

X本轮仅代码、CPU/fake及纯文件证据核对，没有真实sim、HDF state恢复、物理标签、VLA、特征、实验训练或eval，也没有执行或扩展此前Codex的零积分诊断授权。

Codex审查新固定实现／最终SHA后，部署新的不可变源码目录及新session，填齐并校验REPO/CFG/OUT/LOG及文件SHA。沿用同一已核HDF/init/BDDL、profile、runtime、模型及原命令封装。旧089/b596/9ddd失败目录和日志全部保留；旧session不用于重跑新版本。

新session中Codex可沿用既有纯文件注册入口核对50 XML／4450引用／87路径／errors空及资源SHA：

~~~bash
finish_sim 02_registry register-data --config "$CFG/data.json" --out "$OUT/registry"
~~~

验收部署并完成文件核验后，用户亲自启动同一条真实audit，新out/log：

~~~bash
finish_sim 03_audit audit-data --config "$CFG/data.json" --out "$OUT/audit"
~~~

对应实际CLI为"$SIM_PY" -m benchmark.remaining_goals.finish.cli audit-data --config "$CFG/data.json" --out "$OUT/audit"。finish_sim沿用session的逐文件校验与命令/UTC/command_exit/tee_exit日志封装；这些是待Codex填写新冻结路径的候选命令，不声称服务器已经部署。

不新增单独11预检、不重下载HDF、不新增采集，不自动接受未知模型或修改eval。新audit仍需核验完整1313帧、两个head组已知0/1、unknown原因及ready；兼容通过不保证标签充分。原38/4f/b596/9ddd/089、R1..R6和所有失败证据保留。待删=[]，PR #5不自行合并，等待Codex裁决。
