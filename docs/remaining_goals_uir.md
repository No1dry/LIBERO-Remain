# 人工 UIR 与只读派生报告

默认 `report.md` 主表只展示 Joint Success Rate 和 Unnecessary Intervention Rate（UIR）；没有有效人工标注时 UIR 显示 `N/A`，JSON 使用 `null`。10/01 的 partial 宏平均沿用任务内 mask 等权、任务间任务等权。00、11 单列，LIBERO-10 与 LIBERO-90 分开运行和报告。

旧 `metrics.py` 的计算定义、`summary.json` 字段和 `episodes.csv` 保留。诊断表展示 remaining/preservation success、first_all_success_step（达到过全部目标的完整 episode 的均值及样本数）、expected/completed/invalid/runtime_error/missing。`completed` 只表示 rollout 完整。其他分数、分子分母、STOP、步数、queries、elapsed 和原始 trace 继续保存在详细 JSON 中。

## 定义与人工审核

UIR 的 episode 标签表示：策略至少一次对当时已满足的目标，发起没有剩余任务必要性的任务操作。它覆盖部分完成后的重做，以及全部完成后的多余任务操作。必要释放、安全撤离、偶然接触、任务契约允许的必要调整不算。无法判断目标对象或必要性时记录 unknown。

UIR 不从闭爪、动作幅度、距离、接触一次或没有 explicit STOP 自动推断；不会改变 joint success。审核者需要结合原始指令、任务契约和完整录像判断，必要时检查 trace。视频完整、步范围合法只是机械校验；程序不能证明审核者确实看完视频，也不能自动证明其必要性判断正确。

### 2026-10-09 用户澄清：允许主动观察和合理试探

必要性包含合理的信息获取，不只包含直接推进最终谓词。初始画面未展示全部答案，不意味着试探已完成目标就是多余操作。
查看桌面是否有物体、寻找篮子、移动腕部视角、非破坏性的合理试抓并利用空抓反馈、必要释放/安全撤离，不自动记为unnecessary_intervention=true。允许模型通过这些过程调整判断后执行剩余目标。
桌面缺物体是线索，不是目标已完成的充分证明；审核需参考策略当时能获得的观测/反馈，不能按评估器全知状态要求它起点立即跳过或静止。
无新增信息或任务推进的持续无效循环、无必要地完整重做已完成目标，才是待审核的不必要干预。不存在未经校准的“抓几次/动几步就判错”阈值，一个chunk多步闭爪不等于多次尝试；有争议保留unknown。
这是后续Stage03使用的标注澄清，不重写旧raw/旧标签，不改变UIR分子分母、JSR或评分函数。新标注reason注明所采用的本条规则/来源commit，保持可追溯性。

## 命令

下例使用轻量评测解释器，不加载模型或启动仿真。两个入口 `benchmark.remaining_goals.cli` 和 `benchmark.remaining_goals.evaluation` 都支持相同命令；在配置好 runtime 的 checkout 中也可用 `python scripts/remaining_libero.py evaluate ...`。

```bash
# 生成独立模板；所有标签初始为 null，未审核。
python -m benchmark.remaining_goals.evaluation uir-template \
  --run-dir reports/openvla_pilot \
  --out annotations/openvla_round1.json --reviewer reviewer_A

# 完成人工审核后导入；必须写到源 run 之外的新目录。
python -m benchmark.remaining_goals.evaluation report \
  --run-dir reports/openvla_pilot \
  --annotations annotations/openvla_round1.json \
  --out reports/openvla_pilot_review1

# 尚未标注也可生成简明报告，UIR 为 N/A。
python -m benchmark.remaining_goals.evaluation report \
  --run-dir reports/openvla_pilot \
  --out reports/openvla_pilot_unannotated
```

输出目录或模板文件已存在会拒绝覆盖。新入口只读源 run，连旧 `summary.json` 和 `episodes.csv` 也不回写；历史 `summarize` / `rescore()` 接口保留原地重算行为，需要保留旧文件原字节时使用上述 `report` 命令。

派生目录包含 `report.md`、`report.json`、完整旧指标 `summary.json`。导入标注后另有 `uir.json` 和原字节 `annotations.json`。报告绑定 run ID、manifest hash、源 run/manifest/episode 文件 SHA-256、标注 schema、canonical 标注 SHA-256、原标注文件 SHA-256，以及被引用视频的 SHA-256。视频路径必须指向该 episode 记录的视频，且实际文件位于其 run 内；不会读取任意外部路径。

## 标注字段

模板使用 `remaining-goals-uir-annotations-v1`，绑定从 `run.json` 读取的 `run_id` 与 `manifest_hash`。每个 episode 最多一条标注，不接受其他 run 的同名 episode。

| 字段 | 含义 |
|---|---|
| `unnecessary_intervention` | 严格 JSON `true` / `false` / `null`，不接受 0/1 或字符串 |
| `review_status` | `unreviewed` 为尚未审核；`reviewed` + null 为审核后无法判断 |
| `reviewed_full_episode` | 审核者是否完整看过整个观察窗口；true/false 标签必须为 true |
| `reviewer` / `reason` | 审核者及理由；审核结论需要非空字符串 |
| `evidence` | 录像与物理步区间列表：`video_path`、`start_step`、`end_step`；端点包含在区间内 |
| 顶层 `synthetic` | 人为测试标签必须为 true，报告显著标记，不能用作真实人工审核结果 |

v1 对 true/false 采取保守证据约束：episode 必须完整有效，录像状态为 saved，`frame_steps` 覆盖每个物理步 0..N，审核证据区间覆盖完整窗口。N 为普通/partial 的 H+W，或 11 的 W。可另添干预事件区间并在 reason 解释。缺视频、录像失败、稀疏抽帧或无法完整核对时保留 null；录制评测时使用 `--save-video --video-stride 1`。

下面只演示字段形状，**全部是 synthetic 占位值，不能直接用于实际结果**。真实身份、episode ID、视频路径与 N 应以生成的模板和对应 run 为准。

```json
{
  "schema_version": "remaining-goals-uir-annotations-v1",
  "run_id": "SYNTHETIC_RUN_ID",
  "manifest_hash": "SYNTHETIC_MANIFEST_HASH",
  "synthetic": true,
  "annotations": [{
    "episode_id": "SYNTHETIC_EPISODE",
    "unnecessary_intervention": false,
    "review_status": "reviewed",
    "reviewed_full_episode": true,
    "reviewer": "SYNTHETIC_REVIEWER",
    "reason": "SYNTHETIC 示例标签，不是任何真实录像的审核。",
    "evidence": [{"video_path": "videos/000000.mp4", "start_step": 0, "end_step": 7}]
  }]
}
```

## 分母与缺失

每个 task×mask 格子内：`UIR = true / (true + false)`。`annotated` 为 true+false，`unknown` 为 reviewed+null，`unannotated` 为完整有效 rollout 中缺行或未审核者。缺失、invalid 和 runtime error 属于 ineligible，不能以 false 或 unknown 混入有效标签分母。标注覆盖率同时报告 annotated/expected 和 annotated/completed。

partial UIR 先等权平均同一任务的 partial masks，再等权平均任务，00/11 不参与。任何 manifest 预期 task×mask 格子没有有效标签，主 macro 为 N/A；不能只平均已标注格子。“覆盖全部格子”不等于“每个 episode 都已审核”，因此必须同时查看 episode 标注覆盖率，报告保留每格分子分母及缺失数量。macro 的原始标签总数用于审计，不应拿总 true 除以总有效标签替代宏平均。

本功能不自动产生真实 UIR，不训练分类器，不启动 GPU，也不认证候选状态语义合法性。
