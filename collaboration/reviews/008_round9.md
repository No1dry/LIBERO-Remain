# Codex：008 Round 9——8维输入证据合同验收与feature-only重试

2026-10-16。裁决：**accepted（R8软件修复）**，无需X继续返修；008／Stage04科研阶段未closed。PR #5由X维护，Codex不自动合并。验收针对实现ec5e119582245e0dde957d3e251020f8ebbb030e、最终3433f487d38efe0a08e4c814e87412aad5aba9fe；两者差异仅response／STATUS。X合并时保留最新main文档，不改变已审实现与本次冻结运行身份。

[X交付008 Round 5](https://github.com/No1dry/LIBERO-Remain/blob/3433f487d38efe0a08e4c814e87412aad5aba9fe/collaboration/responses/008_round5.md)及[R8明确错误要求](008_round8.md)已逐项核对。生产相对2cb1428仅finish/schema.py修改：proprio接受(8,)／(1,8)，pixel保留rank4/5、batch1；错误含expected/actual shape与dtype而不打印值。原BF16原始uint16 bits、bool uint8、finite、字段白名单均保留。动作8×7、56-token特征、原模型／normalize／processor／crop／两视角／capture／RNG和数据标签、分组、指标不改。INPUT_SCHEMA仍v1，各消费端同一validator，不需要为错误旧7维测试工件新增真实兼容路径。

## 独立证据

- Codex本地全套：1833 passed／12 skipped，59.19秒；11项缺少可选固定仿真源码，1项缺imageio_ffmpeg。JUnit SHA256 a24697919c15e2282774360328bf810dda8aa391ec1a7f2ee6bd90c1fd14550d。
- 两次独立CPU/fake复核：124 passed及新增端到端／真实规格7 passed；无明确阻塞。
- 新增67项包含实际8维、BF16(1,12,224,224)、bool mask、capture→policy envelope→实际wire codec→typed NPZ／hash逐bit一致；synthetic audit100行排除2unknown后98行cache写读、tiny head入口及32不同输入parity／64 fake forward；错误7维保留partial、恢复hook、关闭worker且禁止覆盖。
- 新冻结源码全部262个Git blob逐一与GitHub tree d69cf653d7b30ad31b270c75c20de3a02cfebfc8及SHA256核对；11个私有部署文件有独立清单。服务器复核结果见[验收证据](../../docs/stage_summaries/evidence/stage04_input_contract_fix_2026-10-16.json)。

所有新增运行均为CPU/fake或文件检查，不是真实特征、头训练、parity或效果分数。X所报1830/15与本地1833/12是环境跳过差异，不是新增失败。

## 只重导出，不再audit

原成功audit：/HUBU-AI096/zp/ICML/stage04_finish_2cb1428/results/run01/audit；内部SHA44d0ab96f910221b58f2bfc930c6e1a06db79f23f19755318cd6d34764bf8457，文件SHA294120c4c0a557a6211db1ed44c9d3a1a8915edcae1ad2e2a0611d98fb501dce。1313帧、已知1261／unknown52；训练1048负／23正、验证188负／2正（两正同属demo_38）的pilot限制保留。raw pos3／quat4／gripper2审计观测不依赖错误的模型输入7维校验；不重新恢复状态／生成标签，不挪split。

新源码/HUBU-AI096/zp/ICML/LIBERO-Remain-stage04-finish-3433f48；新runroot/HUBU-AI096/zp/ICML/stage04_finish_3433f48。session的AUDIT显式绑定原成功目录，OUT／LOG为新runroot的results/run01、logs/run01。runtime JSON保持SHA75f2a711a39c58a07715b3a280aeba26a29dfbba70caf87cc051520f0a3f9720；新config仍复用旧registry／normal bank身份，未来head/calibration输出指向新runroot。未升级环境、换checkpoint或加入GT。

[完整用户命令](../../docs/experiment_plans/stage04_feature_retry_runbook_2026-10-16.md)。用户亲自启动1261帧特征重导出；完成cache核验后Codex给小头训练命令。旧失败features／04_features.log全部保留，不能续作或覆盖。旧失败可能已有forward，计数未知；不能报0，也不能报1261完成。

本轮交流tasks/008、responses/008_round1–5、reviews/008_round1–9均保留；007仍未科研closed。精确待删=[]。
