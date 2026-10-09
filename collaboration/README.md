# Codex—X 协作入口

本目录是 No1dry/LIBERO-Remain 的代码任务与审查交流区。先读 [STATUS.md](STATUS.md)。
用户于 2026-10-09 更新分工：原 DeepSeek 执行职责全部移交 Codex，后续不再分配 DeepSeek 任务。

| 角色 | 职责 |
|---|---|
| 用户 | 研究目标和资源决策 |
| Codex | 研究决策、制定代码任务、审查 GitHub 提交、执行与审查实验、验收与阶段归档 |
| X | 修改代码、验证、推送 GitHub、逐项回应代码审查 |

Codex 按明确授权的实验计划，在冻结的已验收版本上运行实验，保存命令、日志、身份与原始产物，再独立核对结果。benchmark 实现、修 bug、修改指标或协议仍由 X 完成；出现接口故障，Codex 保留证据、暂停受影响实验并向 X 发任务，不在执行目录临时改源码救分数。
历史任务和日志中的原执行者署名保留，当前责任以本协议、STATUS 和对应最新执行计划为准。交接盘点见 [2026-10-09 交接记录](../docs/stage_summaries/handoff_2026-10-09.md)。

## 交流与交付

- `tasks/NNN_*.md`：Codex 给 X 的可执行任务。
- `responses/NNN_roundN.md`：X 的交付或逐项回应。
- `reviews/NNN_roundN.md`：Codex 的审查、未解决问题及验收裁决。
- `STATUS.md`：当前阶段、任务状态、提交/PR 链接与最新裁决；保持简短。
- `../docs/stage_summaries/`：长期保存的大阶段总结，不随交流清理删除。

任务状态为 `open → submitted → changes_requested/accepted → closed`。
X 可以提交和回应；只有 Codex 能给出 accepted/closed 的裁决。未关闭事项不能因时间长而删除。

X 每次开始前 fetch 最新 main 并阅读任务及最新 review；保留无关改动。代码通常在独立分支实现，推送并建立 PR，供 Codex 检查 diff。回复文档应引用 commit SHA/PR、修改文件、运行命令、实际测试结果、未完成事项；不要只写“已接受”。向 main 发布代码前须有明确验收裁决，不自行宣告研究阶段完成。

新增回复/review 使用新文件名，避免双方覆盖同一文档。需要补充时标出修订日期。不得在仓库中放密码、token、私密环境变量或大体积实验资产。

## 阶段总结与本地备份

每完成一个大阶段，Codex 在 `docs/stage_summaries/stage_NN_*.md` 记录：

1. 阶段目标、完成/未完成事项与验收范围；
2. 代码提交、测试与实验原始证据；
3. 科学结论、禁止主张、风险与下一步；
4. 本阶段交流文件清单，以及已关闭/仍开放的事项。

总结必须同时提交到 GitHub，并在用户的本地项目中复制到
`research_archive/LIBERO-Remain/stage_summaries/`。本地 `backup_manifest.json`
保存文件 SHA-256 与来源 commit。**只有 GitHub 内容和本地备份校验一致，才能清理已闭环交流。**
X 可起草总结，但不能以自己的“已备份”声明替代 Codex 对本地文件的核验。

## 清理规则

每周检查一次，并在大阶段验收时再次检查。只清理 tasks/responses/reviews 中明确属于已关闭事项的文件，且关键决定已写入长期阶段总结。

执行顺序：检查状态 → 写/更新阶段总结 → 推送并核验 → 本地备份并核验 SHA →
将精确待删清单登记到总结/STATUS → 用 Git 删除这些已跟踪文件 → 提交、推送、核验。

不删除开放任务、未解决 review、未合并代码所需交流、协议 README、STATUS、阶段总结、源码或实验结果。不使用目录级递归清空。没有符合条件的文件时不产生空清理提交。
已清理交流仍可通过 Git 历史恢复。发生实际清理后，Codex 简要报告删除清单、对应总结及恢复方式。

这个协议已经获得用户对 GitHub 文档交流、定期清理和本地备份的授权。具体 GPU 实验按用户认可的逐阶段计划执行；职责移交本身不授权扩任务、换 checkpoint、训练、外部消息或删除原始数据。
