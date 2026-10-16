# X交付：009 Round 1——init35 原动作前缀的释放可测性诊断

2026-10-16。回应[008 R11](../reviews/008_round11.md)及[009完整任务](../tasks/009_release_observability_replay.md)。赞同R11：旧证据尚不能判定35号的释放窗口，先测量原包络几何来源。按用户“同意最小诊断”的授权完成独立实现和CPU/fake验证；当前为submitted，等待Codex软件审查，009／Stage04未closed。

## 版本与范围

| 身份 | SHA／状态 |
|---|---|
| 原实验实际生产版本 | `3433f487d38efe0a08e4c814e87412aad5aba9fe` |
| 已审PR #5的合并head | `7d4ad719f92e356239a5d1bff6616534ba75a3f1` |
| PR #5合入main／009分支基准 | `3d361f44a9393638d41738d375004e8ea7794301` |
| 本轮已测试实现 | `5410355436ef0f418f0c95c47293efbdce905b07` |
| 最终交付 | 相对已测试实现仅增加本回复与STATUS；完整最终SHA及独立PR在PR正文登记并核验 |

[PR #5](https://github.com/No1dry/LIBERO-Remain/pull/5)已按R9 accepted及009明确授权合并，保留最新main的R11／009文档，已审生产代码不变。本轮独立分支为`x/task009-release-observability`，不自行合并009。

生产仅新增`release_audit.py`、`release_audit_plan.py`、`release_audit_native.py`三个模块；另新增三个测试文件及[运行手册](../../docs/finish_release_audit_runbook.md)。原environment、runner、release判据、校准、数据域、标签、训练、控制、adapter、阈值网格与指标文件逐字节不变。当前`calibrated=false`、`selected_threshold=null`和所有历史raw／partial／分数保留。

## 已实现行为

`plan`是纯文件入口。固定run ID、run/raw/bank/state/XML/BDDL SHA、唯一`basket_s035_00`及seed35；复用真实`read_run`／`load_source`验证原完整shadow ledger、输入证据和bank，而非只校验新计划自己。只能从原已settle保存初态开始，不能替换为official raw init或step280状态。原未校准状态不阻止诊断，也不加载当前head或模型资源。

计划输出全新目录内的`plan.json`、float64 `actions.npz`、`manifest.json`，绑定所有读取源文件SHA、动作原字节、query对应关系及原环境身份。`run`先重核计划清单和全部来源，再创建唯一原`FinishLiberoEnv`。LIBERO源码／资产由原环境的实时内容fingerprint与bank强制匹配，原reset／restore／step、fresh observation和runner观察／evaluator次序沿用。

默认只顺序执行原step1..292，允许CLI表达1..292的更短前缀但本次部署仍固定292，不自动缩短重试。step292归原query37的chunk3，没有292处query；上限293张状态快照、37个原query对照，不执行第293个动作、不补FINISH／hold／W150。动作dtype、顺序、phase、chunk归属及float64字节精确核对，不重采样或更改gripper。

step0比原live initial observation；0、8、…、288比原raw observation SHA，沿用白名单与dtype／shape／bytes口径。每一步精确比较旧goals、每目标released、grasp/contact和两clearance；JSON浮点按float64位比较，保留signed zero，不引入容差。首个observation／truth／action差异即停止并保留partial，绝不回写旧帧。

记录器只读取当前native数组，新增`mj_stateSize`／`mj_getState`只读调用；不为诊断追加step、forward、collision、controller update或render。一次性保存实际XML、资产、源码、依赖版本／二进制hash、geom/body映射、碰撞过滤与编译mesh；逐帧保存固定2.3.7 INTEGRATION mask4095 typed向量、ctrl/time、可获取OSC目标、gripper、Python/NumPy RNG、geom位姿、已有contact及旧球／pinch包络的最小对。无pickle、不计算接触力、不实现新距离或新release标签。

每次侧录前后比较integration／ctrl／controller／gripper／RNG指纹；字段缺失、非法形状、非有限值或状态变化属于technical_error。初始化、动作期、侧录和清理的native入口调用与时间分别统计，已尝试动作数和成功返回动作数分别报告；292控制步不冒充292次物理积分。VLA forward／head inference／processor调用没有执行路径，均为0。

输出目录必须全新，禁止resume或覆盖源树。`summary.json`区分`plan_ready`、`diagnostic_completed`、`replay_mismatch`、`technical_error`、`interrupted`，异常始终尝试关闭recorder、环境并恢复monitor hooks；不通过物理动作收尾。清单失败会降为技术错误／中断，写明`phase=manifest`、`manifest=null`；清理阶段中断也保持130退出语义，不留下假完成。

## CPU／fake证据

全套`tests`：**1985 passed，15 skipped，252.61s**。其中新增诊断155项全部通过，既有FINISH专项602项全部通过；这些是同一次全量运行的子集，不重复计数。JUnit SHA256：`8f6043b2307abeb8eb942bde93f5c5f0b40cb3f7f3810de22170e88c9d78ad5e`，本地文件`reports/task009_cpu_full.xml`。

15项跳过为既有环境限制：Windows符号链接权限3项、POSIX venv集成1项、未安装的可选固定仿真源码检查11项。新增文件分别46／46／63项，无skip。首次全量命令因新checkout尚未创建`reports`父目录而出现pytest临时目录setup错误，已停止并复现定位；创建目录后完成上述全量运行，没有为此修改生产代码或删除旧失败记录。

三个实际CLI help均exit0，手册5条CLI的参数由真实parser解析通过；相对文档链接、7文件hash与既有生产diff检查通过。最终交付另核验`git diff --check`及文档提交不改已测试实现。测试工件和本地检查报告不上传到源码库。

新增测试覆盖真实文件合同v1／v2：v2 fixture实际构建registry、15源bank和5条完整shadow run，并通过现有reader、artifact和ledger校验；只在测试里将固定SHA常量替换为明确合成文件身份，没有mock验证器。完整292循环使用fake环境；另有实际create-plan CLI→load-plan→fake-run链路，及生成计划后篡改raw/state/query NPZ时在创建环境前拒绝的回归。

覆盖292无新query／无第293步、dtype与signed-zero动作、旧truth／clearance首处差异、状态及RNG只读、native计数、非法geom/contact／非有限值、目录防覆盖、初始化／执行／清理中断与partial。help与plan在禁止导入torch、LIBERO、robosuite、MuJoCo、transformers的独立进程中通过；真实run仍允许LIBERO的传递import，不把“导入torch”误当作“执行NN”。typed NPZ和文件manifest都有往返、hash及篡改拒绝测试。

全部是CPU／合成文件／fake证据。既有回归可使用tiny CPU模型fixture，不是研究模型或真实训练。本轮没有创建真实native仿真、加载真实VLA/head、恢复真实状态、生成物理标签、运行真实诊断或训练。不存在本轮真实释放结论。

复现全量CPU回归（PowerShell，cwd为009 checkout）：

```powershell
$cpuPython = '<项目根>/.runtime/remaining_libero/venv/Scripts/python.exe'
New-Item -ItemType Directory -Path reports -Force | Out-Null
& $cpuPython -m pytest tests -q -ra --basetemp reports/task009_cpu_tmp_final --junitxml reports/task009_cpu_full.xml
```

## 实际命令与交接

完整路径、原输入SHA表、日志防覆盖及command／tee双退出码封装见[运行手册](../../docs/finish_release_audit_runbook.md)。以下是已实现的实际参数，`$SIM_PY`、`$SOURCE_RUN`、`$DIAG_ROOT`按手册由Codex部署后固定；两条命令分别执行，不能自动串联真实作业。

```bash
"$SIM_PY" -m benchmark.remaining_goals.finish.release_audit plan \
  --source-run "$SOURCE_RUN" --episode-id basket_s035_00 \
  --max-action-steps 292 --out "$DIAG_ROOT/plan"
```

```bash
"$SIM_PY" -m benchmark.remaining_goals.finish.release_audit run \
  --plan "$DIAG_ROOT/plan/plan.json" --out "$DIAG_ROOT/run"
```

下一步由Codex审查、部署新不可变源码并准备纯文件计划、补齐服务器路径和日志命令，用户亲自启动唯一真实run。没有声称服务器已部署或源文件真实plan已通过。失败后只读分析partial，不自动重试／扩到296／W150／init37／normal_active／Remain。

## 解释限制

即使全部对照通过，只能报告“从原保存初态重执行同动作前缀，可观测证据匹配”。旧run没有完整native checkpoint，不能证明原step280所有不可见solver/controller状态精确恢复。新状态是本次侧录，不是通用resume系统。

native计数范围是指定Python API入口，不逐个统计内部C调用，XML序列化的`mj_saveLastXML`不在计数列表。新二进制／robosuite源码／资产SHA记录此次运行，不能倒推原产物没有保存的历史摘要。指纹证明范围仅为声明的状态字段及已发现RNG，不覆盖所有潜在Python隐态。CPU/fake只验证软件合同，不冒充真实native认证。

精确待删=[]；不删除交流、历史结果或本地无关工作区，不自行给出accepted／closed裁决。
