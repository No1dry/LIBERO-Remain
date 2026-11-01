# Task013：桌面支撑修正与离线重评分

本页对应[任务013](../collaboration/tasks/013_table_support_origin_fix_and_offline_rescore.md)，用于对已经保存的 headless 基线记录统一重评分。只读原批次，写入独立派生目录；不启动模型、仿真、渲染、状态构造、回放或训练，也不追加模型 episode。任务011的 rollout 协议与任务012的 mask10 来源选择保持。

## 修正内容与兼容边界

旧支撑判据要求物体 body 原点不低于桌面。body 原点并不是碰撞底面：即使原点低于桌面，物体仍可能有方向正确、位置落在桌面顶面容差内的真实接触。该额外条件会把已有支撑证据误判为 unknown，再传播到 `table_drop` 与合规分类。

修订规则使用已保存的物体—固定桌面顶面接触、接触法向与原位置容差，移除 body 原点高度的错误要求。它适用于角色表中所有相关对象，不按篮子名称或特定 episode ID 改分。侧面接触、无接触和不支持的几何仍保留不确定边界；严重掉桌的 2cm 阈值与 K4 连续确认不变。

旧 v1 记录继续按旧语义读取和验证。新入口先核对旧批次身份、源选择、raw、measurement static、执行证据及原 SHA 绑定，再基于保存的 `initial_contacts`、桌面几何、对象角色与逐步碰撞边界生成修订评分。不要修改旧 helper 后直接把旧 `inspect` 的结果当成新版分数，也不要把派生记录替换进旧 raw 或重写它的 execution hash。

| 测量版本 | 支撑规则 |
|---|---|
| `remaining-headless-measurement-v1` | 保留旧 body 原点门槛；历史 static 没有 `support_rule` 字段，仍可验证 |
| `remaining-headless-measurement-v2` | 显式 `support_rule=direct-table-top-contact-no-body-origin-v2`；使用顶面接触，移除 body 原点门槛 |

修订 static 有独立摘要，原 static 摘要继续引用原记录。每帧重算沿用旧证据中已经保存并核验的 `object_bounds`，没有补造新的接触或碰撞观测。

仅支撑判断及其影响的 `table_drop`、sticky 事件和 unknown 分类可改变。模型、query、动作、目标真值、释放判定、wrong grasp/placement、A 保持、原端点、步数和每条 TCP 路径长度保持原记录。成功集合变化后，成功条件平均路径可以变化；这不表示任何轨迹被重新执行或缩短。

## 运行命令

在已部署 task013 的独立 checkout 根目录执行，使用已有 CPU/仿真 Python 环境中满足文件读取依赖的解释器；命令本身只做 CPU 文件处理。`OLD_RUN` 指向原模型批次根，`NEW_OUT` 必须是原批次外、尚不存在的新目录。

```bash
CPU_PY=/absolute/path/to/existing/python
OLD_RUN=/absolute/path/to/existing/headless_batch
NEW_OUT=reports/task013_table_support_rescore_001

"$CPU_PY" -m benchmark.remaining_goals.headless.cli rescore \
  --run "$OLD_RUN" --out "$NEW_OUT"
```

不需要新增模型配置、checkpoint、mask 选择或 prepare/replay 命令。原批次的 raw、`measurement_static`、execution 证据、source bank、视频、summary 和 hash 全部保留。派生输出引用原批次、源、代码与修订版本，不能用作一批新的实际执行记录。原 `inspect`/`summarize` 仍用于读取原版本结果，不负责替它们静默换分。

命令产物如下：

| 文件 | 内容 |
|---|---|
| `summary.json` | 版本 `remaining-headless-table-support-rescore-v2`，原批次/源码身份与 `derivation_harness_sha256`，固定计划、旧新统计、变化列表和未验证工件 |
| `report.md` | 每任务旧新成功率、分类、覆盖、成功条件 L、变化清单及源工件问题 |
| `episodes.csv` | 固定 100 条人口，含旧新分类、失败/unknown 原因、原步数和 L、缺失原因 |
| `changes.json` | 支撑、事件或分类变化的 episode 及依据；没有变化的记录仍计入汇总 |
| `episodes/<episode_id>.json` | 版本 `remaining-headless-derived-support-episode-v2`；原 raw/static/execution 身份引用、旧新评分、修订 static、逐步派生 `table_drop_trace`、保留事实与动作/query 摘要 |

派生记录显式标记 `derived_only=true`、`new_execution=false`，支撑版本为 `direct-table-top-contact-no-body-origin-v2`。若存在未验证工件，报告将列出 `unverified_task_artifacts`，CLI 返回 2；报告生成不等于所有原记录都有效，不能补造它们的评分。

## 统一人口与结果解释

本次任务记载的现场人口为已执行 80 条、计划中另外 20 条 missing。入口应处理同批全部已执行记录，不仅挑出已知的 11 条；固定十任务 × 每任务 10 条的 100 条计划不变。实际读取数量、未验证工件与未执行缺口必须在报告中可见，不能将缺失或 unknown 改成模型行为失败。

对比报告需同时阅读以下信息：

| 项目 | 解释 |
|---|---|
| 原版与修订版分类 | 每任务和每 episode 的 success、failure、unknown、technical error、missing |
| 变化清单与依据 | 哪些对象支撑发生变化、哪些 `table_drop`/unknown 被重算、最终分类为何改变 |
| 已执行人口 | 基于实际已执行记录的成功率百分比、成功数/已执行数及有效证据覆盖；现场预期为 80 条 |
| 固定计划人口 | 仍以 100 条显示计划分母及缺口；每任务分母仍为 10 |
| 成功条件路径 | 各版本成功集合的平均 L 与 n/N；无成功为 N/A；逐 episode 原 L 不变 |
| 分轨汇总 | LIBERO-10 主轨与 LIBERO-90 zero-shot 扩展分别报告、按任务等权；混合总体仅描述性 |

`summary.json.comparison` 及逐任务比较中的 `executed` 定义为至少记录一个策略控制步；`recorded` 还包括零步技术错误。`success_among_executed` 把已执行的 unknown/technical 条目保留在分母中，并分别列出类别；`success_over_plan` 保留计划人口。`old_summary`/`new_summary` 保存原规则的分轨等任务权重、路径 episode 覆盖和路径任务覆盖。`report.md` 主比较表使用 episode 分母，不把它与等任务汇总混称。

若修正后出现此前未确认的真实 `table_drop`，也应记录为新事件并据此计分；修订不是只允许分数上升。原证据缺失或其它未知原因也不能靠这次修正自动消除。

任务中的旧已认证 `10/80=12.5%`、11 条支撑误判与可能的 `21/80=26.25%` 是诊断线索，**不是必须达到的答案或调参目标**。最终分数以全部记录统一离线复算为准。本软件文档不表示已经读取或重算服务器上的 80 条真实轨迹。
