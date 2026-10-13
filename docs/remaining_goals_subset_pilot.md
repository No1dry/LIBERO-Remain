# Stage03 子集 pilot：执行与交付说明

本入口实现任务005。先由Codex验收实现、冻结新checkout，再执行Plan3；X的CPU/fake测试不是VLA结果。旧 `evaluate run` 默认all的行为保持兼容。**不要从源manifest删00，不改001状态、相机或crop，不在旧00实验目录pull或覆盖产物。**

## 数据、选择与两个输出

`evaluate pilot --masks 10 01 11` 在完整源bank及完整独立replay通过原有验证后，仅执行选中episode。显式pilot另要求回放至少覆盖源bank最大retention窗口、至少2次重复；本批为150步×2，1步×1不能代替。源顺序决定执行顺序，mask由布尔语义读取，不由文件序号猜测。源manifest逐字节复制到新run，源state不改；候选replay报告也逐字节保存并核对验证前后字节未变。`execution_selection`明确绑定源hash、selected/not_selected IDs、expected、模式、原指令与有效指令及hash，并进入run/config/结果/离线报告/UIR身份检查。

| 模式 | 固定来源 | masks | expected | 原指令与有效指令 | 用途 |
|---|---|---|---:|---|---|
| original | basket indices 0..4 | 10、01、11 | 15 | 均为原始完整指令 | 探索性主pilot |
| oracle-remaining-initial | 同一5来源 | 10、01 | 10 | 源仍完整指令；policy收到唯一初始未完成goal的catalog language原文 | 隔离执行可行性诊断 |

显式oracle拒绝00/11和多剩余目标，绝不为11虚构指令。环境恢复、完整goal specs、保持与评分沿用源episode；只有policy调用边界覆盖固定有效指令。oracle joint成功提供可行性正证据，失败仅为未证实；不能作为主模型分数、性能上界或因果证明。两种模式输出到不同新目录，先主15条再诊断最多10条，是否运行由Codex按Plan3裁决。

未选00为 `not_selected`；所选错误/未尝试维持固定分母并显示errors/missing。不会补来源或按成功筛样本。选择入口通用于完整bank，并不自动把任何20条数据认作本批basket；执行者核对dry-plan里的task、indices 0..4、state/manifest/replay/checkpoint身份。

## 复制执行的命令

以下为Linux服务器命令。在**新验收源码checkout**运行，复用已核验的simulation interpreter、模型runtime和旧001源目录。先将变量指向服务器已存在路径；`MODEL_CONFIG`必须是00已用的同一份实际local配置，不能把未填模板当实际配置。本入口不重新安装模型或修改旧运行目录。

```bash
# 从新验收checkout运行；OLD指向保持不变的Stage02/001准备checkout。
OLD=/HUBU-AI096/zp/ICML/LIBERO-Remain-normal00-stage02
SIM_PY="$OLD/.runtime/remaining_libero/venv/bin/python"
MODEL_CONFIG="$OLD/configs/remaining_goals/local/openvla_oft.json"
MANIFEST="$OLD/data/stage03_basket_candidates_001/manifest.candidates.json"
REPLAY="$OLD/reports/stage03_basket_replay_001/replay_report.json"

# 新checkout只创建指向既有runtime的local metadata，不安装、不修改旧runtime。
# 保留venv解释器路径，不调用resolve()解开python symlink。
"$SIM_PY" - "$OLD" <<'PY'
import json, os, sys
from pathlib import Path
old = Path(sys.argv[1])
runtime = json.loads((old / ".runtime/remaining_libero/runtime.json").read_text())
for key in ("python", "libero_config_path"):
    value = Path(runtime[key]).expanduser()
    runtime[key] = os.path.abspath(value if value.is_absolute() else old / value)
target = Path(".runtime/remaining_libero/runtime.json")
target.parent.mkdir(parents=True, exist_ok=True)
with target.open("x") as stream:
    json.dump(runtime, stream, indent=2)
PY

# 若实际local配置另有文件名，仅将MODEL_CONFIG改成已验收配置的绝对路径。
"$SIM_PY" scripts/remaining_libero.py evaluate check --config "$MODEL_CONFIG"

"$SIM_PY" scripts/remaining_libero.py evaluate pilot \
  --config "$MODEL_CONFIG" --manifest "$MANIFEST" --candidate-replay "$REPLAY" \
  --masks 10 01 11 --instruction-mode original --dry-plan \
  --save-video --video-fps 20 --video-camera both --video-stride 1 \
  --out reports/stage03_primary_plan_001.json

"$SIM_PY" scripts/remaining_libero.py evaluate pilot \
  --config "$MODEL_CONFIG" --manifest "$MANIFEST" --candidate-replay "$REPLAY" \
  --masks 10 01 --instruction-mode oracle-remaining-initial --dry-plan \
  --save-video --video-fps 20 --video-camera both --video-stride 1 \
  --out reports/stage03_oracle_plan_001.json

# 验收与身份核对后，原指令主批。
"$SIM_PY" scripts/remaining_libero.py evaluate pilot \
  --config "$MODEL_CONFIG" --manifest "$MANIFEST" --candidate-replay "$REPLAY" \
  --masks 10 01 11 --instruction-mode original \
  --save-video --video-fps 20 --video-camera both --video-stride 1 \
  --out reports/stage03_primary_001

# 主批技术正常完成并按Plan3裁决后，另列诊断。
"$SIM_PY" scripts/remaining_libero.py evaluate pilot \
  --config "$MODEL_CONFIG" --manifest "$MANIFEST" --candidate-replay "$REPLAY" \
  --masks 10 01 --instruction-mode oracle-remaining-initial \
  --save-video --video-fps 20 --video-camera both --video-stride 1 \
  --out reports/stage03_oracle_001
```

`--dry-plan`只读完整源资产与replay，输出新JSON，不加载模型/创建仿真；静态配置不可用会列在 `configuration_readiness`，不能把dry-plan exit0当模型已就绪。run会要求静态配置检查通过。输出存在即拒绝，换新的编号；不提供自动resume/retry，不在技术暂停后自行换index/seed或现场改代码。若既有Remain运行需要显式环境配置，可在两种plan/run中都传相同的 `--environment-config /absolute/existing.json`。

运行前核对：manifest字节SHA `50c557f087783d7aa346992f4449dc81c1c59302e8850b3a3bee1c820c18797d`、content hash `c3f15ec71bb1a663e6db048ca145c96e7f33e752afa975b502d215fb03213cbb`（来自Codex的001审查）；primary expected15、oracle10、完整source20、indices0..4、无00执行、相同checkpoint112文件身份。两条plan中的源/replay/state身份必须相同，只有选择/用途/有效指令不同。

## 预算、暂停与资源

沿用原runner：10/01为H520+W150=670策略控制步；11为W150；不真值early-stop。worker每episode `reset()`仍重置seed7，runner每episode新建队列，chunk上限8、center_crop与BF16使用既有实际配置。默认不为保存证据增加reset/render/step/predict。每次pilot仅加载模型一次、复用环境一次；正常primary有15次policy reset、oracle10次。`runtime_counts`登记load/reset尝试与完成次数；加载错误、invalid reset等可能使实际次数小于计划。两批正常合计两次load、25次reset；这与旧00入口逐case加载方式不同，不能把load次数当episode数。

显式pilot要求开启录像。模型加载/环境初始化/策略接口异常、invalid reset、证据保存/验证错误、录像错误或缺失会写 `status=technical_paused` 与 `stop_reason`，关闭已创建资源，停止后续selected case。expected不变，后续missing。完整技术执行但任务success=False继续；保存原trace与原指标。视频错误本身不更改已完成轨迹的JSR，暂停状态与视频覆盖独立显示。检查run.json/summary.json和coverage，不能只看exit0。旧默认all仍保留已有继续行为。

## 产物与证据范围

| 文件 | 内容 |
|---|---|
| `manifest.json`、`source/replay_report.json` | 完整源的逐字节快照；后者仅candidate模式 |
| `plan.json`、`run.json` | 预定选择、原/有效指令、源hash、模型配置、实际provenance、失败原因与load/reset计数 |
| `episodes/000000.json` | 原episode身份、选择/模式/有效指令、原trace/指标、证据与录像引用 |
| `evidence/000000/initial_observation.npz` | 本次真实reset后runner白名单整理的typed观测；用于首次predict的原始观测，非构造参考 |
| `evidence/000000/execution.json` | query序号、输入观测step/hash、返回/接纳chunk长度、真实执行区间、STOP/异常/未执行尾部及run身份 |
| `videos/000000.mp4` | 已获取观测录像；Plan3双相机20fps/stride1 |
| `summary.json`、`episodes.csv`、`report.md` | 固定所选分母、JSR、UIR N/A及覆盖；旧指标作诊断保留 |

观测NPZ和query hash记录的是adapter预处理**之前**的白名单输入，不冒称最终encoder tensor。policy的实际信息仍要结合OFT既有crop/预处理、proprio与指令解释；全幅双视角录像和评估器GT不能证明policy已看到或理解目标关系。反馈在chunk中途出现后，要到真实下一query才有新决策机会。证据只记录，不增加第三项主指标或自动生成UIR。

`read_run`、rescore、UIR与只读派生报告会重建选择、验证源快照hash、逐结果身份和实际step0/query证据，拒绝混入未选00、不同模式或篡改工件。启动前错误允许明确 `episode_not_started`，不会虚构step0；执行中错误保留可用partial证据。损坏的已引用证据不能用改status掩盖。

## UIR与只读派生

```bash
"$SIM_PY" scripts/remaining_libero.py evaluate uir-template \
  --run-dir reports/stage03_primary_001 \
  --out reports/stage03_primary_annotations_001.json --reviewer Codex

"$SIM_PY" scripts/remaining_libero.py evaluate report \
  --run-dir reports/stage03_primary_001 \
  --out reports/stage03_primary_derived_001

# 完成独立人工标注后，在另一个新目录派生。
"$SIM_PY" scripts/remaining_libero.py evaluate report \
  --run-dir reports/stage03_primary_001 \
  --annotations reports/stage03_primary_annotations_001.json \
  --out reports/stage03_primary_annotated_001
```

主表仅所选task/mask的JSR↑/UIR↓；不混入00或宏平均行。oracle报告明确为诊断，分目录另表。未标注=N/A，unknown与已审核覆盖独立显示。模板绑定selection与有效指令，不能拿主批标签直接套诊断批。旧 `summarize` 是原有原目录重评分接口；研究旧raw和summary保持原字节时使用上面的 `report` 新目录派生。

006不阻塞实验，不新增可见性分类器或自动UIR规则。查看桌面/篮子、移动腕部、合理无破坏试抓、空抓反馈、必要释放/撤离不自动UIR。对**未完成目标**反复抓取失败是执行失败，不能仅凭重复计UIR；事件须绑定当时已满足目标或整体完成，以及操作对象和缺乏任务/合理信息获取必要性的证据。不能确认对象/状态/必要性/完整审核覆盖时保留unknown。细则见[006回应](../collaboration/responses/006_round1.md)。
