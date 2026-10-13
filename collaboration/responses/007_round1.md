# X交付：007 FINISH-v1实现与停止校准

日期：2026-10-13。状态：**submitted，待Codex代码审查**；不自行accepted/closed，不启动真实实验。

PR：[No1dry/LIBERO-Remain #4](https://github.com/No1dry/LIBERO-Remain/pull/4)。分支 `x/task007-finish-protocol`。

| 身份 | 值 |
|---|---|
| 独立实现基线main | `869f409884b73fa7de8dcacb4c7861d6ddfa19f8` |
| 已测试实现SHA | `55474fddc934ad8b4e257b64dd21a41921242af4` |
| 最终交付SHA | PR #4正文登记最终完整head SHA；包含本回复及STATUS，代码仍为上行已测试实现 |
| 协议／结果／ledger | `remaining-finish-v1` / `remaining-finish-episode-v1` / `remaining-finish-evidence-v1` |
| 特征／小头 | `oft-l1-action56-mean-v1` / `remaining-finish-head-v1` |
| 数据／标签 | `remaining-finish-data-audit-v1` / `current-state-passive-hold-v1` |
| 默认预算 | basket，H520/W150/chunk8，5 shadow validation + 10 normal active + 15 Remain active；最多20100物理步 |

## PR #3合并登记

已按既有accepted与007 A.1授权合并 [PR #3](https://github.com/No1dry/LIBERO-Remain/pull/3)。原头 `4b5145173b979f268625bf154800f14df7194d14`；为保留最新main规则，合入 `1ce05ce4bbb1d7248c0228deb6302bf79ed13fe1`，仅STATUS文档冲突采用新版main，得到 `c16ba550da552d2265ab22cc5d12cda7b62be49a`。确认相对已验收 `04508dc0b0c48bf10e33c69ed3d3e830df793aaf` 的benchmark/scripts/tests/configs没有代码差异。GitHub合并后main为上述 `869f409...`。

007从该main独立分支开发，没有追加到PR #3。2026-10-12协作README/STATUS/007/Plan4规则保留。Stage03科学审查未因合并代码被宣布closed，旧实验仍冻结04508dc。

## 实现内容

1. **独立协议与证据**：t0与H实际query、chunk边界/末尾截断、active FINISH优先、shadow只记头判定、明确TIMEOUT；两种退出均真实W步hold，不再predict。记录候选/接纳/已执行映射、实际同次预处理张量与两路crop、logit/p/阈值/头身份。技术异常/中断保留partial、固定expected/missing并关闭资源；完成但策略失败继续。真实episode主入口仍固定520/150/8，纯runner另有非整chunk假测试。
2. **物理契约**：basket对象全集，真实双指grasp/全gripper contact/必要几何，无法确认则unknown；禁止投放按初始篮外非目标可移动物体的入篮+释放稳定事件判定，确认后粘滞。退出hold锁定当前EE姿态，固定delta OSC逆缩放纠偏，Panda grip0保持已有finger目标；不靠GT开爪、不冻结sim。真实数据provider使用示范XML并核验布局；缺XML报不足，4步标签分支结束恢复进入前状态。
3. **自动评分**：合规FINISH百分比+n/N；初始成果全程保持、决策当下全完成/释放、保持窗口目标稳定及禁止投放；多标签失败、technical/unknown/missing、τ和延迟覆盖。K=1/4/8只读复算。shadow新主项N/A；独立normal报告完成/提前/24步内正确停止及保持合规版本，90/10仅pilot解释。
4. **同forward只读头**：观察原L1实际56个action-token输入，不切EOS，不改原输入/crop/forward/解码；冻结原模块，detach后均值池化；FP32 LayerNorm→128→GELU→1。train-only pos_weight、普通validation BCE选最早最佳epoch，安全NPZ和完整身份。真实32输入parity在同worker内恢复RNG并逐动作比较；不以CPU或最终成功率替代。
5. **数据与校准**：精确初态映射或明确采集provenance，绝不猜demo编号；未映射inventory提供真实hash但不自动建立映射。source/trajectory/重复state跨组拒绝，正类来自当前状态+同hold4步，unknown不冒充负类；缓存从证据重新校验标签。来源不足给确定性候选或not_proposable，需明确确认。仅validation first-hit阈值搜索，零提前且全部不FINISH/及时率0不假通过，不拿test救阈值。
6. **全流程入口**：文件计划、用户真实audit/normal准备/环境预检、特征、头训练、parity、validation shadow、calibration、normal/Remain active和可选shadow、inspect/rescore。新out不覆盖；没有自动resume、后台调度、训练→eval串联。

生产新增集中在 `benchmark/remaining_goals/finish/`；配置在 `configs/remaining_goals/finish/`，新增10个CPU测试文件；README加新入口，pyproject新增console入口与可选h5py依赖，gitignore排除临时测试产物。既有benchmark/adapter/runner/metrics/scripts源码、旧raw和scores没有改变；旧默认入口与原JSR/UIR语义保留。

## 实际软件验证

本机 Windows，现有CPU解释器 `.runtime/remaining_libero/venv/Scripts/python.exe`。工作目录为新stage04 worktree；测试数据全为tiny synthetic数组/HDF5/模拟worker与fake环境，没有真实资产恢复或真实VLA。

```powershell
& '<项目根>/.runtime/remaining_libero/venv/Scripts/python.exe' -m pytest tests -q -ra --basetemp .pytest_finish_full_v1 --junitxml reports/task007_cpu_full.xml
```

结果：**1465 passed，15 skipped，127.38秒**。1480个收集项中，本次新增FINISH共 **237 passed / 0 skipped**。跳过均为旧项：3个Windows无symlink权限、1个POSIX venv专属集成、11个可选固定仿真源码在该独立checkout不存在的catalog检查。没有把真实GPU/物理正确性当成被通过的测试。

测试覆盖007 F矩阵：旧schema拒混、t0/H/超时/末chunk、隐藏GT不影响策略输入、高p shadow不退出、非法头/概率/输入hash、双退出恰W hold、query/action时序、禁止投放/既有物体/短暂接触/初始成果回归、分母与N/A、冻结/池化/参数/训练选择、来源/标签/缓存篡改、τ与延迟覆盖、dry-plan导入隔离、异常/中断pause及资源释放、录像和证据失败partial。

额外实际检查：

- 13个子命令全部 `--help` 返回成功；`budget-plan` 输出30条/20100步，断言未导入torch/libero/robosuite/mujoco。
- `plan-data --config configs/remaining_goals/finish/data.example.json --out reports/task007_data_plan_example`：文件计划如实显示三个占位资产不存在，不恢复状态/加载权重。
- 完整source/head `dry-plan`已由CPU文件夹具测试，覆盖实际NPY/typed observation/head manifest/分组身份及拒错；没有用缺真实资产模板冒充真实计划通过。
- 手册23条命令经实际argparse静态解析，9个本地链接存在；未执行这些真实命令。
- `git diff --check`通过。交付扫描确认旧源码未改变、无凭据进入本次文件。
- 本地JUnit SHA256：`a603e1b45b2ecf93ce79cab981c0a8f444d58f5bafdceadcd8d9cf4794e39447`。原始JUnit/CLI计划在worktree的reports下；根目录 `reports/task007_x_delivery_20261013.json` 保存最终SHA、测试计数与校验回执，不作为科研成绩。

## 实际命令与使用说明

完整手册：[docs/finish_v1_runbook.md](../../docs/finish_v1_runbook.md)。含资产/官方链接、解释器/cwd/依赖、全部参数、输入artifact、新输出、日志、退出码、各阶段检查、unknown及partial处理；按已知 `/HUBU-AI096/zp/ICML` 工作根与旧stage03资产线索提供候选配置，Codex部署后核对并填写新的确切服务器路径/SHA。

入口：

```bash
python -m benchmark.remaining_goals.finish.cli --help
python -m benchmark.remaining_goals.finish.cli budget-plan
```

全部13子命令为 `budget-plan / plan-data / audit-data / prepare-normal / preflight / export-features / train / parity / dry-plan / run / calibrate / rescore / inspect`。`run`由purpose显式选择validation_shadow/normal_active/remain_active/remain_shadow。真实实验没有被任何默认测试、安装或无参入口自动启动。

## 边界与下一步

真实hold稳定性、保守release判定的覆盖/正确性、官方数据来源映射是否充分、真实CUDA动作parity、head效果和校准候选是否成立，均需用户执行对应独立命令后检查。官方旧init格式仅用受限NumPy反序列化，缺数据/未知globals明确不足。保守几何可能增加unknown；这不是已验证物理成功。

K以物理间隔计数（K+1状态）；真实head/calibration只在训练与validation的固定source上构建。shadow未来原策略动作不认证active保持；合规FINISH不是UIR或全过程无冗余证明；官方SOG10的既有训练来源单独披露。

本次代码实现与候选命令已交付，**没有新的真实实验成绩**。下一步Codex审查PR #4；验收后部署冻结版本到新服务器目录并给最终机器命令，用户逐步运行。X不自行合并007或宣告研究阶段完成。
