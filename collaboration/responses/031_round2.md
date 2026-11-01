# 031 round2：失效原库存ready来源的续跑边界修复

日期：2026-11-01。实现：X。对应[031 R1](../reviews/031_round1.md)的唯一P2，提交至[PR #12](https://github.com/No1dry/LIBERO-Remain/pull/12)，待Codex复核；未自动合并。

## 固定提交与修改范围

- 最小修复提交：`18059cb12abdd505144e36c87b521faeba897de9`；parent为已冻结交付 `a23a8116e5e2e2bcd344242b170e787e50535a42`。
- 该提交只改 `selected_preparation.py`、对应测试与031 runbook。生产代码改动为两个条件和一个独立阻断分支，另增加恢复提示。
- 随后的 `6abd21b` 仅同步main的R1审查、任务补记、部署记录和STATUS，未改变修复后的代码。保留原交付与Codex审查记录，不倒改R1裁决。

```bash
git show 18059cb12abdd505144e36c87b521faeba897de9 -- benchmark/remaining_goals/headless/selected_preparation.py tests/test_selected_preparation.py docs/task031_normal00_selected_preparation.md
```

## 根因与修复

原实现已经在ready依赖失效时记录 `ready_origin_invalidated`，但后续阻断依赖 `operations` 非空；原库存直接验收的ready来源没有本次物理操作，因而落入新row创建，丢掉标记与历史，再隐式build／replay。

修复后：

1. continuation对ready和此前已失效的ready来源都做文件重新验收；恢复原文件后能重新ready。
2. 在创建新row／判断续回放之前，独立按失效标记保留原行，不依赖operations。missing／failed均不调用native，重复continue不追加物理工作。
3. 原位更新当前readiness，仅ready转为非ready时追加历史。原origin、旧acceptance历史、previous_attempts、operations与物理计数保留；恢复ready后失效历史仍在，重复缺失不重复追加历史。
4. 对这一类曾ready后失效来源，原输出中的 `--allow-failed-retry` 也不授权重建／回放。报告 `recovery_action` 明确提示：可恢复原证据后只读验收；确需新物理尝试时，用户须指定新的 `--output` 并保留旧报告。新目录中若原证据明确失败，仍沿用原显式retry要求。未曾ready的失败重试、首次缺来源构造、build-only后续补replay保持原语义。

## 有界验证

先新增两协议的6个参数化CPU/fake用例，在原实现上得到 **6 failed / 0.41s**：3个文件删除分支触发意外native build／replay，3个文件损坏分支丢失失效标记。native边界完全由fake代替，没有真实物理调用。

修复后受影响检查：

```bash
python -m pytest tests/test_selected_preparation.py tests/test_selected_producers.py -q --basetemp=.work/pytest031-r2-green
git diff --check
```

结果 **42 passed / 1.47s**，无skip；diff检查通过。新增用例覆盖normal00构造依赖、selected10构造依赖及独立回放依赖的丢失／损坏，均经历首次ready且operations为空、普通continue、带retry标志的再次continue、恢复原文件后重新ready；断言native调用始终0、历史与零物理计数保留、不产生attempt目录。既有build-only→replay、普通失败重试及有物理历史的失效来源检查一并通过。独立只读复核未发现本边界内阻塞问题。

原始本地日志：`.work/task031-r2-red.log`、`.work/task031-r2-green.log`。未扩展GPU、全库测试或真实制备／回放／模型评测／训练；42项是本次受影响软件验证，不冒充新的真实来源认证。

## 部署交接

制备修正版请在独立目录部署。首批80条和后续20条normal00评测继续使用冻结的 **`a23a8116e5e2e2bcd344242b170e787e50535a42`** 评测源码，不热覆盖该目录，不因本小修改变prior-run代码身份或重跑80条。原冻结版本的制备continue问题并未就地修改。

本修复不阻塞已accepted的首批00路径，不宣称两个任务物理问题已解决或100条来源已齐。Codex下一步只需复核该最小修复、隔离准备制备修正版及用户启动命令；真实作业仍由用户启动，031整体仍open。
