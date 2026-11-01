# 031 R1：首批00软件验收通过；制备续跑一处有界修复

日期：2026-11-01。审查：Codex。对象：[PR #12](https://github.com/No1dry/LIBERO-Remain/pull/12)，固定HEAD `a23a8116e5e2e2bcd344242b170e787e50535a42`，实现`0a198a18d05d7a893518aa50d42f48e15e8172c2`。

## 裁决与范围

**首批80条normal00的运行/评分/文件来源路径accepted，可由用户启动；031整体仍open。** selected preparation的一个普通continuation分支needs-fix（下节P2），不是要求重做全部交付，也不阻塞首批00。PR不自动merge，不将源码通过等同两个任务真实物理修复。

相对已审c6dc98d只看本轮增量；0a198a18到a23a8116仅031回复/STATUS变动，实际实现一致。独立定向CPU/fake：新00/来源/制备/runner验收175 passed（17.72s），旧workflow及mask10 workflow15 passed（24.97s），共190 passed；另一个新增边界复现按预期失败，确认下面错误。没有把该失败抹进“全部通过”。

## P2：原库存ready来源失效时，普通continue会隐式重建

位置：[selected_preparation.py:240–321](https://github.com/No1dry/LIBERO-Remain/blob/a23a8116e5e2e2bcd344242b170e787e50535a42/benchmark/remaining_goals/headless/selected_preparation.py#L240)。

1. 首次从既有库存验收ready，未运行native，故`operations=[]`。
2. 其依赖文件随后丢失，续盘点247–253行正确标记`ready_origin_invalidated=True`。
3. 281行只拦截`old.operations`非空的行；原库存ready不满足。
4. 286行重建row时还丢失invalidated/历史标记，309–321行随后调用native build/replay，没有额外重建授权。

这会导致未预期的物理制备与预算消耗，且违背031回复“失效来源只标缺失，不自动重建”的约定。它不影响首次00 run或file-only dry-plan。

CPU/fake复现骨架（在固定PR源码，沿用现有测试fixture；native完全被fake替代）：

```python
from pathlib import Path
from tempfile import TemporaryDirectory
import importlib
import pytest
from tests.test_selected_preparation import setup_inventory, entry, fake_sources, TASK

p = importlib.import_module("benchmark.remaining_goals.headless.selected_preparation")
patch = pytest.MonkeyPatch()
try:
    with TemporaryDirectory() as temporary:
        root = Path(temporary)
        fake_sources(patch, p)
        calls = []
        def native(operation, task, index, origin, output, protocol):
            calls.append(operation)
            return {"manifest": "new.json", "ready": True}, {
                "actual_control_steps": 450, "count_status": "complete"}
        patch.setattr(p, "_native", native)
        inventory = setup_inventory(root, [entry(0, manifest="old.json", ready=True)])
        output = root / "out"
        p.prepare(inventory, output, mode="prepare-missing", tasks=[TASK], indices=[0])
        sources = p._sources()
        def resolve(protocol, task, index, origin):
            if origin.get("ready") and origin["manifest"] == "new.json":
                return {"episodes": [{"episode_id": "synthetic"}], "source_acceptance": {}}
            raise FileNotFoundError("existing source dependency removed")
        def inspect(*args):
            raise FileNotFoundError("existing candidate dependency removed")
        sources.resolve_source, sources.inspect_candidate = resolve, inspect
        patch.setattr(p, "_sources", lambda: sources)
        p.prepare(inventory, output, mode="prepare-missing", tasks=[TASK],
                  indices=[0], continuation=True)
        assert calls == [], "ordinary continuation implicitly rebuilds a previously ready origin"
finally:
    patch.undo()
```

实际输出：首次ready且operations空；续跑`native_calls=['build']`，上述断言失败。完整本地复现脚本/原始失败输出保留。

### 给X的最小修正

- 失效ready来源的阻断不得依赖`operations`是否为空；普通continuation只能保留missing/failed及其readiness历史，不能native重建/回放。
- `_inspect`生成新row后不能丢失失效标记及旧证据历史。
- 明确区分“文件恢复后重新验收”与“授权新物理尝试”。可用已有明确retry机制或拒绝并提示新尝试，但不要自动重试；不强制新增flag命名。
- 用原库存ready、operations为空的两种协议，覆盖build/replay缺依赖、文件恢复重新ready的fake分支即可；既有相关证据复用，不新增GPU/全库测试。
- 只改本边界、独立新提交，回复031_round2；不要热改已冻结00运行目录。后续两段00继续用同一冻结评测源码，避免无关制备小修导致prior-run代码身份漂移或要求重跑80条。

## 已接受的关键语义

- 实际t0必须00；在首次预测前拒绝错误起点。00保持集合为空，goal_regression=null/N/A，A/B都合法。
- 仍用H520、chunk8、全目标+释放连续5观测，wrong-grasp/placement/严重破坏规则不降低；策略只读原RGB/proprio与完整指令。
- 00仅验t0必要事实，旧后续hold失败原样保留；10仍需至少150建设验证和两次独立150回放。
- 逐来源绑定原manifest/replay/init字节，缺证据不ready；原80条10不重跑，旧文件不覆盖。
- 新构造/来源方法明确版本化，不冒充旧全mask银行通过。

## 部署及当前可运行范围

固定a23a8116已隔离上传，源码harness SHA-256 `0d02231ee9e2636161a66429ed00d0336b2cb36b9529a71ed4c86fe560c3676e`本地/服务器一致。三条纯文件命令exit0；旧8任务00来源80/80 ready、未就绪0。代码/配置传输一致，旧环境和源工件未改。

这只是已有保存状态/观测/审计文件的一致性验收，不是新物理回放通过：simulation_created=false、model_loaded=false、real_model_episodes_started=0。

用户下一步可以直接启动首批80条00；完整conda/venv/python命令由Codex本地交接。暂不使用存在上述问题的`selected_preparation --continue`组合；两个任务的真实补建/回放尚未启动、尚未证实修好。X小修与首批00独立推进。

## 非阻塞提醒

首阶段00 summary保留全计划100，20条未选中记missing。报告八任务结果时从同一summary选取对应80条，不把successes/100冒充八任务SR。原始字段/全计划覆盖仍保留。终端CLI主要在结束时输出JSON，若需中途进度可手动调用纯文件inspect；不因此阻塞或再要求一次代码返修。

下一步操作和执行者：用户启动首批00；X只修上述续跑边界并CPU/fake交付；Codex审查该小提交、准备缺失两任务后续命令。不自动merge、训练、清理或追加真实作业。
