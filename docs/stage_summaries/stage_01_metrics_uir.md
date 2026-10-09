# Stage 01 总结：指标精简、人工 UIR 与解释器修复

日期：2026-10-09。作者：Codex。
状态：**closed**。2026-10-09由Codex核验PR #1已合并与main/本地备份一致。
发布main SHA：`fea75fc170b5c3047433316566dc52528c5caf2a`。
PR：https://github.com/No1dry/LIBERO-Remain/pull/1
已审 HEAD：`7ca5cec421925bb14cbbbf7997ddc8e9294db0c9`。
代码实现 commit：`46d935b1b8e8109bbc840a2e4347ed520cdd4df7`。

## 完成内容

X 实现了任务 001/002：默认 JSR/UIR 主表、独立人工标注模板与严格校验、只读派生报告、
coverage 和错误分母、旧指标/JSON/CSV 兼容，以及 simulator/model worker interpreter 的 symlink 保留。
没有改变 metrics.py、物理 runner 或 LIBERO 环境语义，没有训练和新 GPU rollout。

UIR 需要人工依据完整录像和任务契约给出 true/false；unknown、未标注与运行错误不当作零。
首轮可用既有视频开展语义校准；本阶段代码通过不意味着已经取得真实 UIR 分数。

## Codex 独立验收

- macOS Python 3.12.7：985 passed、12 skipped，16.69s。
- Linux Python 3.10.20，禁用 CUDA：986 passed、11 skipped，51.44s。
- Linux 的实际 selected-venv/site-packages worker 回归通过。
- 跳过项：审查副本没有固定 simulator sources；macOS 另缺一个 ffmpeg Python 包。
- 对本次四条真实 OFT 旧结果生成无标注报告与模板报告：原始全树文件 hash 不变，
  旧 summary 完全一致，UIR=N/A、annotated=0/unannotated=4。
- 实际 JSR 仍是 00=0、10=0、01=1、11=1，partial macro=0.5；仅单来源个案。

没有阻塞代码问题，001/002 功能验收通过。审查工件保存在用户本地项目的
`reports/libero_remain_stage01_codex_review_2026-10-09/`。

## 限制与禁止主张

不必要性判定仍是人工语义判断；代码校验录像引用不证明审核者确实看完。
不能把闭爪次数、一次接触、非零动作或没有 STOP 自动当 UIR=true。
first_all_success_step 是诊断字段，可能包括超预算达成，不当作已成功样本效率。
bootstrap CPU 单 index 兼容性问题未解决；已安装环境中的当前功能不因此失效。

本次实际正常 00 失败原因尚未定位。不能据此断言普遍 skip 缺陷，也不能先认定失败只是偶然。
单样本 partial macro 和软件 synthetic 标签不能作为正式 benchmark 性能。

## 交流、归档与移交

本阶段交流：tasks/001、tasks/002 及其参考 patch；responses/001_round1、002_round1；
reviews/stage01_round1。当前暂保留供任务003追踪；更新后的总结再次完成GitHub/本地备份核验后，
可按协作清理规则处理，但不随意删除引用尚需使用的文件。
阶段总结同步保存在用户本地 `research_archive/LIBERO-Remain/stage_summaries/`，
backup_manifest 记录来源 commit 和 SHA-256；发布 closed 时再更新状态与来源。

X已按明确授权合并PR #1，合并提交已独立核验；此前main总结与本地归档字节/hash一致。
Codex关闭Stage01，更新本总结及本地备份。代码验收不等于已有真实UIR标签。
任务 003 属 Stage 02，仍 open，不能因 Stage 01 关闭被删除。

下一步先做既有四视频人工 UIR 校准；新 GPU 工作需等待任务 003 的官方/Remain 00 回归
入口验收，然后由 DeepSeek 固定 basket indices 0..4 机械执行。暂不训练 gate 或跑六模型大矩阵。
