# 033 R2：双壶RGB比较的只读诊断与待裁决提案

本文件是明确的版本修订提案，**尚未批准或启用**。当前v4准入、原失败bool、旧5条ready及其原始manifest/replay完全不改。本轮没有增加render/step，没有运行新仿真或模型，也不把诊断证书用于来源放行。00的30条来源及评测不等待该提案。

## 已有证据与源码核对

[R2工单](../collaboration/tasks/033_round2_source_construction_fixes.md)与[精简数值记录](../collaboration/tasks/033_preparation_findings.json)给出了two_pots来源0/2/7/8/9的代表失败。已读示例中只有腕图7–9像素各差1，非RGB精确一致；source7的reset保存状态也精确一致。source9的24候选整体失败原因来自记录，但只有前两候选的代表帧被逐项核对，不能宣称已读取全部未提供raw或其fresh像素。

当前同步链已有完整处理：`build._step`及正式`LiberoGoalEnv.step`先执行一次物理step，再调用`fresh_observation`；后者forward，刷新success/post_process、force observables并复制原policy数组。`CandidateAuditEnv.validation_snapshot`再次独立刷新，保存refresh前后状态的bit-exact检查。reset则比较本次live reset与原construction的SHA绑定typed observation，要求saved state及初始非RGB精确一致。不是用一个缓存对象自比较。

因此没有发现可据此认定的“未刷新/缓存复用”代码缺口，不应删掉独立刷新以掩盖差异，也不应改动策略路径。已记录现象与同状态GL量化差异一致；这些记录本身不能证明驱动/GL误差的完整成因或所有未读帧都只有量化差异。微波炉真实角速度超限是独立问题，不为本提案提供放宽依据。

v4规则ID为 `named-uint8-rgb-one-level-area-cap-v4-typed-initial-evidence`：每相机最大通道差1，变化像素数 `max(1, floor(H*W*0.0001))`，在256×256为6。因此7–9像素差1在现规则下失败是规则的准确执行，不是计数bug。v4源码已明示此为工程容差，不是已校准的renderer误差界。

## 一次性提交Codex裁决的最小提案

拟定新profile ID：`named-uint8-rgb-one-level-area-cap-v5-proposal-only`。此ID当前仅出现在只读诊断输出，**不是可选择的acceptance profile**。

| 项目 | 现v4 | 拟v5 |
|---|---|---|
| 使用范围 | 原通用构造/回放检查 | 初期只two_pots mask10、256×256双相机 |
| 最大单通道误差 | 1 | 1，保持 |
| 最大变化像素比例 | 0.0001 | **0.00015** |
| 每个256×256相机像素上限 | 6 | **9**；10及以上仍拒绝 |
| nonstepping state | 必须bit-exact | 保持，包括time与原状态位 |
| 非RGB | 初始/reset byte-exact，动态原数值限 | **每次比较均dtype/shape/byte-exact** |
| 实际图像、hash、物理门槛 | 保留 | 全保留；不滤波、重采样、改图或降低物理要求 |

0.00015是针对已读最大9像素样例的最小常用小数比例提案；属于**事后提出的工程规则**，不是独立校准结果。没有选择可接受13像素的0.0002，不能保证未读帧或未来来源通过；误差>1、非RGB差异、state不精确、未知/缺证据、超9变化像素均不支持该提案。相邻帧变化也可能很小，任何RGB容差都不能单独证明同步；state/非RGB与独立刷新仍是必要条件。

若Codex接受，必须一次统一版本化以下路径，不能只改一个常量：

1. construction静态及动态的returned/fresh比较；
2. replay静态/动态同类比较；
3. live formal reset与原construction typed observation的跨render比较；
4. 对应audit/replay/manifest引用的profile和不可变hash；
5. 离线reader按工件记录的profile分派，仍逐字读取旧v4证据，不能让新全局常量否定旧5条ready。

旧构造/回放失败不通过重写bool迁成新版通过。仅凭当前精简数值不能放行：动态原fresh像素未完整保存，缺失部分不能重建或伪造。后续若要新规则的技术验收，Codex需明确可用原证据范围及尚需用户启动的必要新制备/回放，保持原150/2×150、原index和新目录；不以重复运行直到随机过关作为本轮“修复”。旧5条ready继续直接复用，不触发任何物理调用。

## 本轮已实现的只读工具

入口 `benchmark.remaining_goals.headless.rgb_diagnostic` 仅读取指定的原 `audit.json`，不扫描未知来源、不读取模型、不启动native。输出schema为 `remaining-task033-r2-rgb-diagnostic-v1`，包含原文件SHA、原技术结果、各比较原v4结果、假设提案结果、其他物理检查缺口和证据限制。`proposal_candidate`只表示该条已记录比较数字符合待裁决提案；不是source ready、不是原失败被修好，也不是完整物理来源证书。所有输出均 `acceptance_authorized=false`，没有返回ready状态或接入正式验收器。

输入数值须满足原hash一致性、两个named camera完整诊断、原v4 cap及changed fraction一致、state/nonRGB证据为真。工具拒绝误差2、10及以上像素变化、非RGB不一致、状态不明、缺相机/hash或矛盾的原通过标记。完整recorded window也只表示JSON记录齐全，不表示逐帧图像已重新核验。

下面命令由Codex部署后填入实际路径；`OLD_RUN_ROOT`指原aedfe169的运行根，`R2_OUT`必须在独立新目录。只读工具可以在等待提案裁决时执行，不会改变旧来源状态：

```bash
export PY=/path/to/original/libero-simulator-env/bin/python
export OLD_RUN_ROOT=/path/to/original/task033-run-root
export R2_OUT=/path/to/new/task033-r2-review

"$PY" -m benchmark.remaining_goals.headless.rgb_diagnostic \
  --audit "$OLD_RUN_ROOT/preparation/mask10/attempts/two_pots/source_00/attempt_001/replay/group_000/repeat_00/mask_00/audit.json" \
  --audit "$OLD_RUN_ROOT/preparation/mask10/attempts/two_pots/source_00/attempt_001/replay/group_000/repeat_01/mask_00/audit.json" \
  --audit "$OLD_RUN_ROOT/preparation/mask10/attempts/two_pots/source_02/attempt_001/replay/group_000/repeat_01/mask_00/audit.json" \
  --audit "$OLD_RUN_ROOT/preparation/mask10/attempts/two_pots/source_07/attempt_001/replay/group_000/repeat_01/mask_00/audit.json" \
  --audit "$OLD_RUN_ROOT/preparation/mask10/attempts/two_pots/source_08/attempt_001/replay/group_000/repeat_00/mask_00/audit.json" \
  --out "$R2_OUT/two-pots-replay-rgb-review.json"

"$PY" -m benchmark.remaining_goals.headless.rgb_diagnostic \
  --audit "$OLD_RUN_ROOT/preparation/mask10/attempts/two_pots/source_09/attempt_001/build/validation/two_pots_s009_10/attempt_000/audit.json" \
  --audit "$OLD_RUN_ROOT/preparation/mask10/attempts/two_pots/source_09/attempt_001/build/validation/two_pots_s009_10/attempt_001/audit.json" \
  --out "$R2_OUT/two-pots-build-rgb-review.json"
```

路径结构来自工单和实际producer，若部署归档调整了目录，Codex只替换实际路径，不手填hash。工具只读取所列audit；未列入者保持“未读”，不能用上述代表帧报告代替所有候选和150步的重新核验。输出已存在时拒绝覆盖。
