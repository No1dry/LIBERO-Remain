# 013：修复桌面支撑误判，只用已有80条记录离线重算

日期：2026-10-18。状态：open。需求/诊断：Codex；实现：X；离线结果审查：Codex。用户已要求立即把具体修复指示上传。此前聊天中的“X修评分器”没有形成GitHub任务，本文件正式补齐。

## 1. 精确位置与错误

实现基准是已验收PR #9的固定交付 `6e14b7b42123d467fab32b258fd8c4783353352a`。先fetch最新main、保留无关改动；从该已审实现接入即可，不要求先合并其它PR或改010/FINISH。

文件：`benchmark/remaining_goals/headless/environment.py`，函数 `_initial_support`，固定交付第139行：
https://github.com/No1dry/LIBERO-Remain/blob/6e14b7b42123d467fab32b258fd8c4783353352a/benchmark/remaining_goals/headless/environment.py#L139

当前条件：

```python
if (
    nz > 1 - 1e-5
    and abs(contact["position"][2] - height) <= tolerance
    and position[2] >= height - tolerance
):
    valid.append((tid, table_geom["top_lower_bound_m"]))
```

最后的 `position[2] >= height - tolerance` 把物体body参考点误当成了接触底面/支撑几何。body参考点可以低于桌面，实际碰撞表面仍正确支撑在桌面上。不能据此否定前两项已经充分记录的真实顶面接触。

传播链：初始support eligible=None / table_height_m=None → 每步basket_1.table_drop=None → schema.analyze_trace记录event_unknown → metrics.score_episode第35/51行把本来已完成的轨迹分类unknown。

不要通过在metrics里忽略table_drop、将所有unknown默认False、仅按目标达成判成功、硬编码这11个episode为成功来解决。

## 2. 已有真实证据，足够写CPU回归

11条都是同一原因：
- basket_cheese_butter，来源7、8；
- basket_soup_cheese，来源0、1、2、3、4、6、7、8、9。

它们全部已goal_confirmed，没有已记录wrong_grasp/wrong_placement/goal_regression失败，唯一unknown事件是basket_1.table_drop，从t0持续到末帧。

11条的初始篮子body z均为 `0.43219202665003076` m，桌面top z为 `0.43676000000000015` m，参考点低4.567973mm。真实4个接触的法向均为 `[0, 0, 1]`；顶面位置检查均通过，只是body参考点条件失败。

可用于最小CPU fixture的第一接触：
```json
{
  "basket_body_z": 0.43219202665003076,
  "table_top_z": 0.43676000000000015,
  "contact_geom_ids": [10, 156],
  "contact_position_z": 0.4367599203801213,
  "contact_normal": [0, 0, 1],
  "contact_distance": -7.961987883728483e-8,
  "includemargin": 0,
  "existing_tolerance": 1.398099394186424e-7,
  "expected_contact_plane_pass": true,
  "expected_legacy_body_origin_pass": false,
  "expected_corrected_support_eligible": true
}
```

这不是新待采集数据。Codex已只读检查这11条的全程已有掉落几何字段，记录的basket collision上界最低约0.5782m，仍高于桌面约14.14cm；没有出现记录中的“整组碰撞几何低于桌面2cm”条件。完整原始记录留在服务器，X无需访问服务器或取得大轨迹才能实现，Codex在交付后用它们离线复算。

## 3. 最小修复要求

1. 修正支撑判定：使用实际物体—固定桌面顶面接触、正确方向的接触法向和既有顶面位置容差，移除body参考点必须高于桌面的错误假设。保留侧面接触/无接触/未知几何的不确定边界；不要任意增大容差或改掉2cm/K4。
2. 同一规则适用于任务内所有相关对象，不限篮子或上述11个ID。不能要求构建通用支撑图、增加VLM裁判、训练头或重新做几何校准。
3. 明确新支撑/派生计分版本；旧v1记录仍可按旧规则读取。**不能只删第139行后调用旧inspect**：当前validate_measurement_static会按helper重推旧support，直接改helper会让旧raw因支持事实不同而被拒绝。请保留legacy读取语义，并提供纠正后的派生重算路径。实现组织/版本字段命名由X合理决定，不为风格返修。
4. 离线入口读取既有80条记录，以保存的initial_contacts、table几何、对象角色及每步object_bounds重算受影响table_drop证据和sticky事件，再统一得到新版分类/汇总。旧绑定可用原语义核对；不需重复构造/回放/渲染或把大模型重新load。复用原已核验证据，不新增不相关的昂贵审计。
5. **原raw、measurement_static、execution证据、source bank、原summary和SHA绑定全部不覆盖。** 新版只写独立派生输出，引用原批次/代码/源身份和修订版本。不要将修改后的派生帧伪装成实际新执行的原始轨迹或篡改旧SHA。
6. 模型、动作、原端点/步数、释放判定、goal真值、wrong_grasp/wrong_placement、A保留、L和全部阈值保持。只修支撑假设与因此受影响的table_drop/unknown。L可随成功集合改变重新汇总，但逐episode原路径不改变。
7. 统一处理全部80条，不只挑11条改分；保留100条固定计划中的20条missing。报告实际已执行80的成功率/覆盖，以及计划100的缺口，不能把missing或unknown当作模型行为失败。重算若出现新table_drop事件也要如实报告，不能只允许分数上升。

## 4. 精简CPU/fake验证

只跑受影响的小回归：
- 真实数值fixture：body原点低于桌面但顶面接触有效，修订后support=True；legacy读取仍还原旧None。
- 侧面接触/无接触/不支持几何不误证实支撑。
- 确认真实掉桌仍被2cm/K4捕获；轻微移动且未掉桌不罚。
- 离线新旧结果并存、原文件不变；原事件/目标/步数/L不变；无native/model调用。
- 一条仅因篮子support unknown而未认证的已完成fake例子，可由新规则判成功；有真实错抓/未完成的例子仍失败。

不要全库/多平台回归，不启动真实仿真、推理、回放、训练或追加模型episode。不要为“更完美”附加设计往返，本需求足够直接实现。

## 5. 一次性交付和完成条件

X提交独立PR/commit、上述少量测试及实际结果、**只读原批次→新派生目录**的可用离线命令，回复collaboration/responses/013_round1.md。在交付分支STATUS更新当前任务指向013，保留旧历史，不宣告实验阶段closed。

Codex审查、独立目录部署后自行执行纯文件CPU离线重算；用户不需要再启动任何真实实验。输出逐任务旧/新分类、变化episode清单、变化依据、成功率百分比与n/N及成功条件L。

已知10/80=12.5%是旧已认证成功，11条纠正后可能到21/80=26.25%；**这是诊断线索，不是代码必须凑出的答案或调参目标**。实际统一复算结果如实给出。当前旧分数保持不变，X不要在回复中声称已重算服务器80条。

本次不处理另外20条状态准备缺口，不阻塞已有80条结果分析，不合并其它实现、不清理交流、不修改benchmark科学目标。
