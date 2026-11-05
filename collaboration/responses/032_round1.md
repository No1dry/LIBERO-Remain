# 032 Round1 — 随033九任务范围交付

日期：2026-11-02。实现SHA `1b2ce8b7f88026e6c3aeee1cae22f864e266d183`，分支 `x/task033-libero10-nine`。按033覆盖旧6+4未来计划的指示，032与九任务同PR交付，不先另跑旧十任务重评分流程。详细实现、测试、命令与限制见[033 Round1](033_round1.md)及[完整runbook](../../docs/task033_nine_task_runbook.md)。

`headless/offline_scoring.py` 提供版本 `remaining-headless-official00-drop-diagnostic-v1`：

- 00按完整官方bool成功信号提取主评分；原合规/UNKNOWN及原执行端点保留。新00采用首官方成功终止，旧release+五观测诊断为N/A，不能伪称执行过旧终点。
- 10只将 `table_drop` 确认事件及其对应event_unknown降级为诊断，保留混合事件、释放未知、既有成果/炉子保持及其他确定失败。保存legacy/primary、原事件与逐条classification diff。原013 v2支撑修正不撤销。
- 03100和013派生/原执行reader读取原身份、必要文件与hash，report-only与raw fallback证据级别分开。历史工件只读，路径搬迁须匹配原batch身份；异常来源逐行列出，不重跑。
- 033当前报告00/10各90，旧六120条只读复用，新三60条尚待用户执行。旧80/100报告留存，不直接改分母或归零未执行记录；主SR和计划覆盖n/N分别报告。

最终含032/033与受影响旧runtime的定向组合 **187 passed in38.03s**；评分阶段旧031/013回归 **68 passed**，invariant字段补充后评分自身 **34 passed**，均与最终组合重叠，不累加。包括table_drop-only UNKNOWN解除、mixed wrong-placement UNKNOWN保留、确定失败优先、缺signal/metadata、013路径搬迁/字节变化、旧00分阶段union、新00诊断N/A、10关炉恢复仍失败等CPU/fake案例。

本次没有服务器原始结果，因此没有冒称重新算得历史52/80或21/80。Codex在真实路径执行runbook的 `reuse-index` 和 `summarize` 即可获得旧六新口径派生报告；无需模型/仿真重跑。未改历史raw/分数/视频，未自动merge，待审查部署。
