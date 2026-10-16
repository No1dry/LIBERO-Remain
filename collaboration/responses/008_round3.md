# X交付：008 Round 3——历史XML资源根兼容与全量文件扫描

日期：2026-10-15。状态：**submitted，待Codex审查**。回应[008 R4](../reviews/008_round4.md)资源路径P1；[PR #5](https://github.com/No1dry/LIBERO-Remain/pull/5)保持open、未合并。R2初始化修复及两来源域设计保留。

| 身份 | SHA |
|---|---|
| 旧XML路径失败冻结 | `9ddd40f2968ed5dc3d0e0be59db00b8e91d28e5c` |
| 本轮同步main审查 | `1f07522af79b84a7cdc06bd1be8638c5576398a9` |
| 保留最新审查／失败记录的合并提交 | `e35a766` |
| 本轮实现 | `201457a46dfbb8c84ba41416eec08ffb1b64163b` |
| 最终交付 | PR #5正文登记完整head；相对上述实现只增加本回复与STATUS |

## 根因与修改边界

赞同审查定位：固定官方helper只识别独立的robosuite或libero路径段，实际HDF中24个旧chiliocosm资源路径不满足这一条件。9ddd已越过provider初始化，本次不是current_action问题，也不是模型效果失败。

相对9ddd，生产修改限于4个文件：

- `finish/xml_assets.py`：新增版本化、纯文件resolver。官方libero/robosuite资源按完整suffix重定位；对已核的`/home/yifengz/workspace/libero-dev/chiliocosm/assets/`作精确历史别名匹配。批准根来自当前安装包目录，发现目录时不执行包初始化。不按basename搜索，不使用旧路径恰好存在的文件；根内`..`可规范化，根外`..`、symlink逃逸、未知根、歧义及缺文件明确失败。未知file字段、include等外部依赖整体报错，不跳过。
- `finish/environment.py`：`_processed_demo_xml`使用同一resolver，替换旧cwd/helper路径处理。只替换批准file属性的值，保留其他XML字节；不改相机、材质、mesh尺度或几何。provider接收审计冻结的资源扫描，并在创建环境前及加载示范XML时验证。R2的恢复／合同／hold生命周期保持。
- `finish/data.py`：在provider创建前读取全部实际HDF轨迹（包含unused）的XML，扫描并聚合所有失败。扫描副本传入provider，原始配置不改；审计结束及后续audit验证再次核对实际HDF/XML和资源。资源变化使审计insufficient或拒绝复用，已有partial仍保存。
- `finish/cli.py`：复用`register-data`，保留来源registry并增写`xml_asset_scan.json`、`registration.json`；未解析时exit2。无新增CLI、依赖或实验阶段。

扫描记录resolver版本、实际原XML及SHA、处理后XML SHA、批准根、逐条old→new/目标SHA、全部轨迹覆盖与聚合错误。它始终`simulation_created=false`、`ready_for_feature_export=false`。扫描嵌入audit，audit SHA沿用既有cache/head绑定；当前v2审计缺少完整扫描会被拒绝，旧v1历史读取保留。元数据不进入模型输入。

两域profile、分组、keys、1313帧采样、严格Panda/OSC合同、release/K4/unknown规则、H520/W150/chunk8、网络、阈值和指标均未改。没有追加step、settle或采集，也不修改原HDF、XML或资产文件。4个生产文件之外只改两域手册及3个测试文件；相对9ddd这8个实现文件共914行新增／30行删除，其中新resolver310行、新测试506行。

## CPU证据与实际数据边界

新增43项CPU用例：`test_finish_xml_assets.py`34项，`test_finish_asset_audit.py`9项。使用[实际库存](../../docs/stage_summaries/evidence/stage04_task008_xml_assets_2026-10-15.json)中的87条原路径字符串及对应完整suffix，包括24条旧别名；目标都是明确标注的tiny合成文件，其SHA特意不同于真实候选资源。覆盖同名纹理不可互换、根内／根外路径、symlink逃逸、近似旧根拒绝、聚合错误、非路径XML字节不变、同一resolver及改变资源后拒绝旧快照。

集成测试用50组小型HDF，证明unused中的错误也会在provider前被发现、来源文件字节不变、注册失败保留全量报告、缓存／导出前核对身份、审计中途资源变化保留partial并拒绝ready。这些合成数据不证明真实物理标签。

原provider生命周期21项全部保留。移除了fixture对`_processed_demo_xml`的旧单参数透传stub，使这21项也经过实际纯文件处理；native I/O仍受控，测试不创建真实环境。没有放宽原断言。

首轮全套发现新源码中的公开历史绝对路径字面量触发不可变源码的隐私路径guard（1 failed、1678 passed、15 skipped）。现将公开兼容规则表示为完整路径段并精确比较，不改隐私guard、不扩大别名；这不是用户名脱敏。增加6项近似路径拒绝回归后，XML与发布包专项39项通过。首轮失败JUnit保留为`reports/task008_xml_cpu_full.xml`，不覆盖。

最终代码上的统一测试：

| 范围 | 实际结果 |
|---|---|
| 全部19个FINISH测试文件 | **457 passed，0 skipped，93.27秒** |
| 全套tests | **1685 passed，15 skipped，155.55秒**，共1700项 |
| 新增43项＋原provider 21项 | **64 passed，0 skipped**，均包含在上述两次统一测试中 |

15个skip为3个Windows symlink权限、1个POSIX venv集成、11个缺可选固定仿真源码的catalog检查，与R2相同；本轮没有新增skip。范围／AST检查确认仅上述4个生产文件变化，provider恢复／truth／hold等方法、严格合同及其他标签／训练／指标实现保持；14个CLI help、手册21条命令解析、文档链接和`git diff --check`通过。

实际命令（PowerShell，cwd为`.release-work/LIBERO-Remain-task008`）：

```powershell
$cpuPython = '<项目根>/.runtime/remaining_libero/venv/Scripts/python.exe'
$finishTests = @(rg --files tests -g 'test_*finish*.py')
& $cpuPython -m pytest @finishTests -q -ra --basetemp .pytest_finish_008_xml_target_v2 --junitxml reports/task008_xml_cpu_finish_v2.xml
& $cpuPython -m pytest tests -q -ra --basetemp .pytest_finish_008_xml_full_v2 --junitxml reports/task008_xml_cpu_full_v2.xml
```

JUnit SHA-256：FINISH `0496776c89a2886a08952c3f898ba30e093b0e57d1aa9d6620b2b797508df0c0`；全套 `7d34103e4b1f70821c84c38929cdb445e858686344ccb744e4ee348b762c6b87`。本地范围报告为`reports/task008_xml_scope_checks.json`；发布后独立远端核验回执写入项目根`reports/task008_xml_x_delivery_20261015.json`。这些CPU报告不替代服务器实际文件扫描。

## Codex部署／文件扫描及用户下一条命令

X本轮未运行真实sim、state恢复、物理标签、VLA、特征、训练或eval；也未在服务器应用本resolver。实际87/87候选存在是此前Codex的诊断证据，不是此次实现的服务器验证，更不能声称与不可访问的作者机器原资产逐字节相同。

Codex审查通过后部署**新的不可变源码目录及session**，核验完整head和文件SHA，沿用同一已核HDF/init/BDDL、profile和sim解释器；生成新的CFG/OUT/LOG。原9ddd/b596失败目录、4f通过记录全部保留。旧session只作历史，不用于新版本。

Codex在新session执行已有纯文件注册入口：

```bash
# source Codex部署并核验的新冻结SHA session.sh 后执行；不能复用旧out。
finish_sim 02_registry register-data --config "$CFG/data.json" --out "$OUT/registry"
```

底层实际入口为`"$SIM_PY" -m benchmark.remaining_goals.finish.cli register-data --config "$CFG/data.json" --out "$OUT/registry"`。检查registration=`registered_file_only`、scan=`resolved`、errors为空、trajectory_count=50、file_reference_occurrences=resolved_reference_occurrences=4450、unique_file_references=87；逐项核对原XML、批准根和实际目标SHA。两份报告的ready仍为false，不导入仿真或加载模型；若实际文件检查不符，保留报告并分析，不启动audit。

完成验收和上述扫描后，Codex给用户填好准确路径的新session及完整命令；用户仍只亲自启动同一个真实audit入口：

```bash
finish_sim 03_audit audit-data --config "$CFG/data.json" --out "$OUT/audit"
```

对应底层为`"$SIM_PY" -m benchmark.remaining_goals.finish.cli audit-data --config "$CFG/data.json" --out "$OUT/audit"`。`finish_sim`沿用session逐文件校验、命令/UTC/command_exit/tee_exit日志封装；通用完整入口见[两域手册](../../docs/finish_two_domains_runbook.md)。这里是部署候选命令，不声称服务器目录已准备好。

文件扫描不保证后续物理layout、restore、release/K4或类别覆盖通过。仍须审查真实1313帧、两head组已知0/1覆盖及ready后才能进入feature／训练。不新增单独11预检、不重下载HDF、不新增VLA采集。PR #5等待Codex裁决，不自行合并；008／Stage04未closed，待删=[]。
