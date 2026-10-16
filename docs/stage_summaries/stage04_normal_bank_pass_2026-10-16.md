# Stage04：15个普通official-init来源与shadow文件计划验收

2026-10-16。裁决：**07_normal_bank及08_shadow_plan子阶段accepted**；008／Stage04未closed。用户亲自运行来源准备，Codex仅读取文件并运行纯文件dry-plan，未启动真实VLA／头推理／sim。

## 已完成与身份

- 15/15来源prepared（100%），恰为官方init35..49，每个一次，无替换。初态均basket normal00；state、初始观测、preparation、官方init/index/state SHA／BDDL、registry和各150步技术审计均经load_source核验。
- 准备记录共1200个settle步（15×80）、2250个技术审计步（15×150），policy_steps=0；不是15条模型rollout，不扣后续30条模型评测预算。
- 实际执行代码为3433f487d38efe0a08e4c814e87412aad5aba9fe；数据位置沿用既定job引用的旧2cb/results/run01/normal_bank新子目录，没有覆盖旧audit/features/raw或修改11冻结部署文件。
- bank内容hash7275f774c215afd4ac3d6d09b1e1f37e687b02e6a155266c3de2308b24e8ab47，bank文件SHA084e55537c25e515153e48624d807483b3348f9cee67db77425f69d5eaa6080c。
- 07日志SHA2f276b6e1eb64cac91848d0d20683fae5e4c16c6ba14d2c72f76027ac5419e4a；exit0/tee0，无preparation_error。

Codex已按用户授权完成08_shadow_plan纯文件检查：load_source读取全部15来源，dry_plan严格选择official-init35..39共5个normal_calibration；40..49保留normal_test，未混用HDF demo或Remain输入。plan_sha256=0c49836a7d5e5c82958362b441c10d44bc5fafaa5d8024de211909daaba4f4b6；simulation_created=false、weights_loaded=false，exit0/tee0。头6636f713…及runtime文件75f2a711…保持不变，262源码／11部署文件核验。

文件计划绑定shadow、H520／W150／chunk8、双相机20fps/stride1，下一阶段5条最多3350物理步、330次模型预测。0.5是shadow记录placeholder，不是正式停止阈值。

[机器回执](evidence/stage04_normal_bank_acceptance_2026-10-16.json)。独立验收回执文件SHA6b0c43866e6838133f8add64903a2ec56e271503a859ecc505810186e647ba19。本地reports/stage04_normal_bank_review_2026-10-16/evidence保存bank清单、07日志、shadow plan、08日志和验收回执，逐SHA与服务器核对；**15条raw state／observation／technical-audit原树留服务器，未声称全量本地复制**。

## 下一步：用户启动5条普通shadow采集

[本次唯一真实命令与完整说明](../experiment_plans/stage04_calibration_shadow_runbook_2026-10-16.md)。这次会真实运行VLA／sim并保存视频。shadow记录FINISH分数但不按FINISH停，不用GT成功早停；达到H后W物理保持。故任务完成后继续动作在本阶段属于采集设计，不能当作接头失败；主合规FINISH指标N/A，不写0%。

用户完成后Codex核验5条完整记录、输入/ledger/视频与错误，再按既定normal_calibration首hit网格／零过早／及时停止规则选择阈值；若不能建立则报告capability_not_established，不能为通过改split／看测试调头或阈值。阈值冻结后才是10条normal active独立停止验证，最后15条Remain active。

目前训练和动作接入检查已完成；**普通停止能力及研究现象尚未由新协议验证**。不把准备100%或parity100%当模型任务成功率；HDF验证仅demo_38两正例、跨来源祖源／SOG10 exposure未证明等限制继续披露。

本总结／回执／下一命令／STATUS与已完成标记按README提交GitHub并本地来源commit+SHA备份。原始数据、失败partial和脏工作区保留，不自动合并PR，不删除交流；精确待删=[]。
