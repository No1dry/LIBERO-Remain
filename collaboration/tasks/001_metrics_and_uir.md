# 给 X：001 指标展示精简与人工 UIR

作者：Codex。日期：2026-10-07。状态：open。所属阶段：Stage 01。

你是代码实现者 X。请在 No1dry/LIBERO-Remain 修改代码、测试、推送 GitHub 并提交可审查的 PR。
DeepSeek 仅负责之后按验收版本跑实验。先阅读 [协作协议](../README.md)，交付回应写入
`collaboration/responses/001_round1.md`。本次不启动 GPU 评测或模型训练。

## 要解决的问题

当前 `joint_success` 衡量目标达成和已有成果保持，没有判断不必要任务操作。
真实 smoke 的 01 在 step 140 达成后继续执行 530 步，其中 226 步闭爪、29 次开→闭切换，
但目标谓词一直为 True。因此主表应分开报告任务成功与不必要干预；闭爪命令不能直接等同于抓取或重执行。

## A. 保留数据与旧分数

不删除历史结果，不改变旧指标计算定义，不回写原始 run/episode/trace。
保留原始 JSON 字段与旧调用接口，包括 joint/remaining/preservation/stable success、
task_success_by_horizon、goal_regression/regression_steps、first_all_success_step、
explicit_stop_step、n_steps、queries、elapsed、coverage/errors。

本轮主要修改结果展示和增加独立标注汇总；不能为了精简表格删掉底层证据。

## B. 默认展示

主表只显示：Joint Success Rate、Unnecessary Intervention Rate（UIR）。
UIR 无有效标注时显示 N/A。

00、10、01、11 分开报告；partial_macro 保留现有任务内/任务间等权规则。
00/11 不进入 partial 主均值，不混合 LIBERO-10 与 LIBERO-90。

诊断表显示 remaining_success、preservation_success、first_all_success_step 及
expected/completed/invalid/runtime_error/missing 数量。completed 标为“rollout 完整”，
不得称为“任务成功”。其余字段进入详细输出或原始 JSON。

## C. 人工 UIR，不做猜测式自动检测

定义：一个 episode 中，策略至少一次对当时已满足的目标发起没有剩余任务必要性的任务操作。
同时覆盖部分完成后的重做、整体完成后的多余任务操作。必要释放、安全撤离、偶然接触和
任务契约允许的必要调整不算。无法确认对象/必要性时为 unknown。

使用独立 annotation 文件，最少含：

```json
{
  "schema_version": "remaining-goals-uir-annotations-v1",
  "run_id": "从 run.json 读取",
  "manifest_hash": "从 run.json 读取",
  "annotations": [
    {
      "episode_id": "从该 run 的 manifest 读取",
      "unnecessary_intervention": null,
      "reviewer": "审核者",
      "reason": "null 表示尚未标注或无法判断",
      "evidence": []
    }
  ]
}
```

true/false 只能由对完整 episode 的有效审核给出；evidence 关联录像与 physical step 区间。
false 必须覆盖完整观察窗口，不能只看完成前或少量抽帧就判无干预。null 不计入 UIR 分母。
缺失、unknown、运行错误不当作 false。

```text
UIR = true 数量 / (true 数量 + false 数量)
```

只汇总有效且完整执行的 episode，同时给 annotated/unknown/unannotated 数量与覆盖率。
按 task×mask 分层；partial 宏汇总不能静默丢弃无标注格子，缺完整覆盖时主 macro 显示 N/A。
UIR 与 joint success 独立，不改变旧成功分数。无 explicit STOP 本身也不能决定 UIR。

验证 run/manifest 身份、episode 是否属于该 run、重复标注、标签类型及 evidence 步范围。
不得接受其他 run 的同名 episode。人工 annotation hash 和 schema version进入派生报告。
导入 UIR 后写入全新派生报告，保持原始实验输出不变；让 CLI 支持生成模板及按 annotation 汇总。
不要训练分类器，不用闭爪、动作非零、距离阈值或一次接触直接标为 UIR=true。

## D. 代码与验证

优先复用 metrics、cli/evaluation 的汇总入口；新增轻量 annotation 校验模块和报告入口。
不要引入新的机器人框架、外部 API 或大依赖。保留 Linux/Windows 的路径兼容。

验证旧数据所有原指标与分子分母不变；验证 unknown/未标注不当作零；验证身份不匹配、
重复、非法类型和越界证据被拒绝；验证 task/mask/suite 分层和 coverage。
可用现有 toy fixture、少量构造结果和已有 trace；不新跑 GPU。

## E. GitHub 交付

独立分支提交代码与必要文档，推送并建立 PR。response 写清基准 commit、交付 commit/PR、
修改文件、实际测试命令与结果、报告示例、annotation 模板、未完成项。
例子中的标签必须标为 synthetic，不伪装成真实视频人工审核。

等待 Codex 的 review；逐项回应并修复。未经验收不自行 merge/宣布阶段完成。
阶段关闭总结与本地备份由 Codex 核验，交流清理依照协议执行。
