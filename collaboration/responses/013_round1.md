# 013 Round 1：桌面支撑修正与独立离线派生

日期：2026-10-18。实现：X。状态：submitted，待Codex集中审查与独立目录部署。

## 交付身份

- 实现：`ba21f388a29d7f7275036293833b50c63cb9be9a`。
- 分支：`x/task013-table-support-rescore`；独立PR创建后补充链接。
- 基于已验收012交付 `6e14b7b42123d467fab32b258fd8c4783353352a`，接入最新main `2b4ab600805994894ab00882eb7fd9c2eaf23ba8` 的012审查和013任务，仅本地形成基线 `9250b784903dfc5b52b55fb8b3616e6a21def633`。013增量可直接查看实现提交或相对该基线的diff；未合并其它PR或推送main。

## 修正与旧记录兼容

`headless/environment.py` 的支撑判定使用实际物体—固定桌面顶面接触、朝向正确的法向和原位置容差。新规则移除“body参考点必须高于桌面”这一错误假设，对全部相关对象统一应用，不按篮子名称、11个episode或预期成功数特判。原法向/位置容差、2cm、K4、未知几何与接触不确定边界保留。

新测量版本为 `remaining-headless-measurement-v2`，显式支撑规则 `direct-table-top-contact-no-body-origin-v2`。历史 `remaining-headless-measurement-v1` 仍按原body原点规则核验，不能通过直接改变helper静默重解释旧raw。旧static和旧SHA不改，新派生static有自身版本与摘要。

新增 `headless/rescore.py` 与 CLI `rescore`：先复用原reader核对原批次、来源、raw、measurement、execution绑定；再依据原始initial_contacts/table/roles和已核验逐帧object_bounds派生table_drop。沿用原`analyze_trace`重算sticky事件与unknown，复用同一分类和固定分母汇总逻辑。`metrics.py`只抽出已验证数据的内部评分/汇总函数，未忽略table_drop或把unknown默认改成False；`workflow.py`只抽出已有批次身份读取，原inspect语义保持。

派生记录使用独立schema `remaining-headless-derived-support-episode-v2`，标记 `derived_only=true`、`new_execution=false`，保存原raw/static/execution、批次/源码/源计划身份，旧新评分、支撑变化与每帧table_drop依据。不会把派生帧重新绑定为一批“新执行”raw。原raw、measurement_static、执行证据、状态bank、视频、旧summary全部不覆盖。

模型、query、动作、目标真值、释放、wrong_grasp/wrong_placement、A保留、端点/步数和每条L保持；只有table_drop及其影响的unknown/分类变化。成功条件平均L可因成功集合改变而变化。新发现真实掉桌也如实记为失败，不限制分数只能上升。

## 定向CPU/fake验证

仅运行受影响路径和小兼容回归，无全库、多平台或真实sim/model测试。以下命令在本交付根目录执行，`python`为已有CPU测试解释器：

```bash
python -m pytest tests/test_headless_support_versions.py tests/test_headless_environment.py -q --basetemp reports/task013_support_tmp
python -m pytest tests/test_headless_runner.py -q -k 'fixed_100_denominator or confirmed_wrong_event or unknown_event_breaks or middle_chunk_confirmation' --basetemp reports/task013/scoring_legacy
python -m pytest tests/test_headless_support_rescore.py -q -ra --basetemp .pytest_task013_support_rescore
```

- 支撑版本和旧环境：**62 passed，1.17秒**；含16项新版本验证与46项旧环境回归。
- 原计分/端点兼容：**6 passed，33 deselected，0.35秒**。
- 原始绑定→离线派生→旧reader集成：**2 passed，9.60秒**。
- 合计 **70 passed，0 skipped**，均exit0；`git diff --check`通过。

真实数值fixture使用任务中的body z `0.43219202665003076`、table top `0.43676000000000015`、接触z `0.4367599203801213` 和原容差 `1.398099394186424e-7`：旧support=None，新support=True。侧面、无接触、不支持桌面几何、反向法向及超出平面容差仍未知；反转geom顺序时法向按顺序处理。plate/distractor也应用同一规则。

集成fixture使用合法旧v1几何及真实runner/evidence/reader，policy/env/video为CPU fake；10条原记录旧分类0 success/2 failure/8 unknown，新分类7 success/3 failure，另外90 missing仍在100计划中。其中真实掉桌从unknown转failure，在第5个持续越2cm的观测确认；1.9cm未越界不罚，错抓/未完成继续失败。这只是软件反例覆盖，不是研究结果。测试使用H8缩短未完成fake例，生产H520/K4/chunk8和固定计划未改。

原批次/source/config的全文件字节哈希及原inspect结果保持；逐条动作/query、端点、步数、L和源绑定保持。离线阶段禁止native/model包导入及环境、策略、录像器初始化，CLI源工件问题返回2。

## 可执行离线交接

部署到独立checkout后，在仓库根目录运行：

```bash
python -m benchmark.remaining_goals.headless.cli rescore \
  --run /absolute/path/to/original_headless_batch \
  --out /absolute/path/to/new_task013_derived_directory
```

`--out`必须是原批次之外、尚不存在的独立目录。[完整说明](../../docs/task013_table_support_rescore.md)包含版本、口径和文件清单：`summary.json`、`report.md`、固定100行`episodes.csv`、`changes.json`及逐episode派生JSON。

统一处理批次中全部可核验记录，不硬编码80或只筛11条。报告逐任务旧新分类、变化依据、成功率百分比和n/N、覆盖及成功条件L。实际执行口径为至少一个已记录控制步，recorded另含零步技术错误；unknown/technical/missing分别列出，不改成模型行为失败。`old_summary`/`new_summary`保留主轨与扩展轨等任务权重汇总，整体episode分母比较只作描述。

Codex可在审查和独立部署后直接执行这个纯文件CPU入口，无需用户再启动真实实验。本轮X没有访问服务器、没有重算80条真实轨迹，没有新增仿真、构建/回放、推理、训练或校准。任务所述旧10/80与可能21/80保持为诊断线索，真实新分数等待统一复算；不处理另20条准备缺口，不清理交流，不宣告研究阶段closed。
