# Stage04：32输入真实动作parity通过；进入普通停止控制准备

2026-10-16。裁决：**06_parity子阶段accepted**，无需重训／返修。用户运行冻结3433f487d38efe0a08e4c814e87412aad5aba9fe；Codex只读检查全部原始工件，没有代跑模型或sim。008／Stage04未closed。

## 真实结果与验收范围

- 32/32输入完成（100%），32/32组动作逐bit一致（100%），最大绝对误差0；预先固定atol=rtol=0，没有事后放宽。
- 32个distinct HDF head_validation输入覆盖demo_35..39；state／原始观测／实际模型input hash各32个不同。每输入同worker原模型／shadow各1次，按工件声明共64次真实forward；model_loads=1。**不是32条仿真rollout，也不是模型任务成功率100%。**
- status=completed、passed=true、error=null，command_exit=tee_exit=0。原／shadow使用同一原模型与RNG配对机制；这些证据只支持本次32个固定输入的动作不变，不外推所有状态或整段轨迹。

Codex逐文件验证32个原动作／shadow动作NPZ的shape8×7、dtype、finite、文件SHA与逐byte相等；32个实际input NPZ及BF16／dtype／schema／hash、32份复制观测及其原audit观测身份均一致。选择清单按既定_validation_selection重算相同，不自适应换样；head／audit／base／runtime及来源域身份全部匹配。262源码／11部署文件不变。

- report内部SHA：e547e183d9d9d88da93de904cae2e3c20b367223dadbb1a2aa87e6f97f163993
- selection内部SHA：d5055114a8def44a8cc62bbd9a89ece40704d0ee4c322999fe0a057952ecc5ba
- head：6636f7133943d551df31a14822df440b63c1b98c0b3ee95f4873019492512c7f
- audit：44d0ab96f910221b58f2bfc930c6e1a06db79f23f19755318cd6d34764bf8457
- base：4601be2d7857e255cfde08ad06680428e01c49fb982614221f5bd04a92f39734
- runtime文件SHA：75f2a711a39c58a07715b3a280aeba26a29dfbba70caf87cc051520f0a3f9720
- 原始文件SHA和范围见[机器验收回执](evidence/stage04_parity_acceptance_2026-10-16.json)；服务器只读回执文件SHA344df3c6c6bf69bd43eb0ac04b36ea9c3c0993a27c774fe485363eef71f86f99。

本地reports/stage04_parity_review_2026-10-16/evidence已备份parity.json、inputs.json、完整06_parity.log和独立验收回执，并逐SHA核对；**32对action／input／observation NPZ原树仍在服务器，未声称全部本地复制。** 原训练头与此前raw／失败partial均保留。

启动日志有既有TF插件重复注册／缺TensorRT／robosuite宏等信息，后续完整64forward和零误差证据成功，不作为本轮失败或无依据升级环境。首版Codex文件核验器误将带启动消息的混合日志直接当纯JSON，解析失败；第二版只解析最终报告并与原JSON逐项比对，全部通过。仅修核验器、未改benchmark／容差或重跑模型，保留初版检查痕迹；不把这次解析错误记为模型／parity失败。

## 下一步：先准备15个普通official init入口

[完整07_normal_bank命令与验收范围](../experiment_plans/stage04_normal_bank_runbook_2026-10-16.md)。新旧normal_bank均未生成；整个旧2cb目标目录已确认不存在。沿用固定job JSON引用的旧2cb registry／bank位置，用户从新3433 session生成此前不存在的bank目录，不改11冻结部署文件、不覆盖旧结果；实际生产代码仍3433，log在新3433根。

本步只恢复／保存官方init35..49来源，不加载VLA、不训练、不校准阈值，也不是15条模型rollout。35..39留后续5条normal_calibration shadow，40..49留10条独立normal_test；不把HDF demo编号当init，不改变来源域分组。

bank完成后Codex只读核验／dry-plan并给下一真实命令，再由用户启动普通shadow校准、冻结阈值、独立normal active验证，最后15条Remain active。训练和动作接入已完成；**普通停止能力尚未建立，不能宣称stop-capable或研究现象已解决**。验证仅demo_38两正例、跨域祖源／SOG10 exposure未证明、HDF域差异等限制继续保留。

本总结／回执／STATUS／下一命令按README提交GitHub及本地来源commit／SHA备份；不自动合并PR，不改脏工作区，不删除tasks/responses/reviews或原始数据。精确待删=[]。
