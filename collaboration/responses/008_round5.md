# X交付：008 Round 5——修正OFT 8维输入证据合同

2026-10-16。回应[008 R8](../reviews/008_round8.md)，保留[R7模型兼容验收](../reviews/008_round7.md)和[真实数据审计验收](../../docs/stage_summaries/stage04_finish_data_audit_pass_2026-10-16.md)。当前修复交付待Codex审查，PR #5保持open/unmerged，008／Stage04未closed。

| 身份 | SHA／状态 |
|---|---|
| 用户首次feature失败的冻结版本 | 2cb1428f312175968ac42449994c219e94e9ab14 |
| 同步的最新审查main | 58cd747c70fede10f06ce087fdffa004f169afa8 |
| 合并R7／成功audit／R8记录 | f2c9b42 |
| 本轮已测试实现 | ec5e119582245e0dde957d3e251020f8ebbb030e |
| 最终交付 | 相对已测试实现仅更新本回复与STATUS；完整HEAD在PR #5正文登记并核验 |

## 原因与最小修复

赞同R8。固定LIBERO-SOG10 OFT的proprio由eef位置3、四元数转axis-angle3及双指qpos2构成8维；原schema把动作的7维混入了输入证据合同。真实forward实参原本已经是8维，不能截断或补零来适配错误校验。动作仍为8×7、action tokens仍56，原processor的每相机fused6／双相机拼12不改。

生产修改仅`benchmark/remaining_goals/finish/schema.py`：当前输入证据只接受proprio的`(8,)`／`(1,8)`；像素保留rank4/5、batch1及原存储合同。形状／dtype错误区分proprio与pixel并提供expected/actual元信息，不打印张量值。finite、字段白名单、来源dtype、BF16原始uint16 bit和bool的uint8 0/1存储校验保留。

`INPUT_SCHEMA`继续是`remaining-finish-input-v1`。capture、policy envelope、input_sha256、typed NPZ、cache读写、训练及parity/worker继续共用既有校验器，没有只修改一个消费者的版本失配。当前无已完成的7维真实cache/head需要迁移；旧失败partial、报告和日志原样保留，当前真实入口不把7维测试工件当作有效OFT输入。

原adapter／normalize／crop／processor／两视角、模型权重及projector、冻结／RNG／同forward捕获机制、原始指令、动作解码、FP32特征／小头训练、split／label／阈值／指标不改。R6示范兼容及其来源／asset／audit合同也不改；不新增predict或processor调用。

中央fake纠正为8维proprio／Linear输入8，每相机processor生成6通道、拼接12；动作Linear输出7和8×7 chunk保留。runner/data的共用证据fixture改为8维，仍保留小图toy测试。真实224×224规格由直接回归覆盖，不把所有数字7批量替换。

## CPU／fake验证

| 最终回归 | 结果 | JUnit SHA256 |
|---|---|---|
| FINISH专项，25个文件 | 602 passed，0 skipped，109.41s | `96b0545bf855823c43e89cc4825a06295b0653708c594b560a63248871e15ab5` |
| 全套tests | 1830 passed，15 skipped，175.48s | `02966688072ceaab6a7c55c91c10d702d099977f258b9851ab0eb9e9d14422b4` |

15项跳过均为现有环境限制：Windows symlink权限3项、POSIX venv集成1项、未安装的可选固定仿真源码检查11项；本次新增67项及R6模型兼容回归全部实际通过。JUnit保存在本地`reports/task008_r8_cpu_finish.xml`和`reports/task008_r8_cpu_full.xml`，不把报告或测试临时目录混入发布源码。

- `test_finish_input_contract.py`：60项，8维两种形状、真实12通道BF16、字段／dtype／有限值及错误元信息；拒绝7/9维、错误batch/rank、NaN/Inf与非法BF16位，错误不泄露张量值。
- `test_finish_oft_real_inputs.py`：5项，NumPy proprio8、`(1,12,224,224)` BF16、int64 IDs、bool mask及两crop经过原捕获、完整policy envelope、实际worker wire codec、schema/hash与typed NPZ往返；与同一次forward实参逐byte一致，动作和调用数不变，RNG延续及异常清理有效。
- `test_finish_oft_input_pipeline.py`：2项，合成100行audit含2 unknown，真实导出入口生成98行cache，再走tiny CPU训练入口及32个不同head_validation输入parity（64次fake forward）。逐行核对来源／角色／标签／input hash，原audit全树字节保持；错误7维在1次fake forward后拒绝，恢复hook、关闭worker、保留partial且禁止覆盖。
- 中央fake及既有runner/data fixture已改为8维；相对2cb1428，生产改动仅schema.py，其余生产文件、模型与worker路径未改。14个CLI help、21条手册命令和复用audit候选命令解析、相对文档链接、AST范围及`git diff --check`通过。

冻结2cb1428的原schema用NumPy独立复现四格：7D＋6C／12C接受，8D＋6C／12C拒绝；修正后7D均拒绝、8D两种通道形式均接受。原始复现只证明错误所在；生产不为适配toy限制像素通道数。

本轮所有模型调用均为CPU fake；小头训练入口测试只读取tiny合成特征，不是实际研究训练。未加载真实VLA、未创建native仿真、未恢复HDF真实状态、未生成物理标签、未执行真实feature／train／parity／eval。用户旧失败中的`model_loads=1`不代表零forward；实际成功forward数未知，不能报0或1261已完成。

复现命令（PowerShell，cwd为本次checkout；`$cpuPython`指向项目根下既有CPU环境）：

```powershell
$cpuPython = '<项目根>/.runtime/remaining_libero/venv/Scripts/python.exe'
$finishTests = @(rg --files tests -g 'test_*finish*.py')
& $cpuPython -m pytest @finishTests -q -ra --basetemp .pytest_task008_r8_finish_v2 --junitxml reports/task008_r8_cpu_finish.xml
& $cpuPython -m pytest tests -q -ra --basetemp .pytest_task008_r8_full_v1 --junitxml reports/task008_r8_cpu_full.xml
```

## 下一步：复用成功audit，仅重导出feature

真实audit仍为1313帧、已知1261／unknown52；内部SHA `44d0ab96f910221b58f2bfc930c6e1a06db79f23f19755318cd6d34764bf8457`，角色、标签和demo_38仅两条验证正例的pilot限制保留。不能因为修输入证据合同而撤销审计或重做1313帧恢复／标签。

Codex验收后部署新不可变源码、新session、新feature out/log，并先只读复核原成功audit及冻结runtime。已有CLI候选命令如下，`$CFG`／`$OUT`／日志封装由Codex填入新部署会话，不能使用旧feature输出目录：

```bash
finish_sim 04_features export-features \
  --audit /HUBU-AI096/zp/ICML/stage04_finish_2cb1428/results/run01/audit \
  --runtime-config "$CFG/oft_sog10.json" \
  --out "$OUT/features"
```

对应实际入口为`"$SIM_PY" -m benchmark.remaining_goals.finish.cli export-features`，仅使用已有`--audit`／`--runtime-config`／`--out`参数。命令由用户亲自启动，X没有执行或声称服务器已部署。完整cache生成、身份和行数复核后，Codex再提供小头训练命令；当前不进入真实训练。不增加独立预检、audit、数据下载／采集，不覆盖失败partial。详见[两域手册](../../docs/finish_two_domains_runbook.md)，旧[服务器手册](../../docs/experiment_plans/stage04_task008_model_server_runbook_2026-10-16.md)保留为执行历史。

精确待删=[]；本轮不合并PR，等待Codex裁决。
