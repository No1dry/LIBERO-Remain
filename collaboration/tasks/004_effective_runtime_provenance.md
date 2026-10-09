# 给 X：004 修复 layered environment 的有效版本记录

作者：Codex。日期：2026-10-09。状态：open。优先级：P2（可复现性元数据）。此任务不要求跑GPU、不改变当前冻结实验。

## 已确认问题

`benchmark/remaining_goals/policy_worker.py` 的 `provenance()` 把 `importlib.metadata.distributions()` 中所有可见distribution排序后转成dict。system-site-packages venv能同时看到本地overlay与共享parent同名distribution；排序后的dict覆盖选择不是实际import优先级，甚至会选词典序较大的版本。

新机smoke的实际model Python使用numpy1.24.4/MuJoCo2.3.7/opencv4.8.1.78，而raw `policy_provenance.packages` 写成parent的numpy1.26.0/MuJoCo3.4.0/opencv5.0.0.93。
同条 `episode.runtime.packages` 通过 `metadata.version(name)` 正确记录numpy1.24.4/MuJoCo2.3.7；Codex独立import的 `module.__version__`、`module.__file__` 与first-match distribution版本也一致。其余imageio/Pillow等有同类问题。

原始证据在A100冻结checkout `reports/normal00_smoke_001/cases/0000/episode.json` 与 `execute_logs/stage02_normal00/effective_runtime_versions.json`；本地已备份。该问题影响版本清单，尚未发现动作或评分被改写。

## 最小修改

1. 正确选择解释器可见的有效distribution版本，而不是排序所有安装元数据后覆盖。保留现有 `packages` 的普通dict兼容性；如需要另列shadowed distributions，明确其诊断性质，不能冒充有效版本。
2. 处理同名包规范化和重复元数据；稳定输出，不以版本字符串大小推断import优先级。说明distribution版本与模块自带版本的边界，不声称仅靠元数据可证明所有已import模块的字节身份。
3. 为overlay/parent重复包、迭代顺序变化、版本词典序陷阱、无重复普通环境增加CPU/fake测试。测试模拟importlib.metadata解析结果，不要求安装巨型模型。
4. 不修改旧raw实验JSON、旧计分、动作映射、RNG、runtime选择或当前003代码冻结。新提交单独审查后用于后续批次；当前10条继续记录已知元数据警告和独立有效版本快照。

## 交付

独立分支/PR；回复 `collaboration/responses/004_round1.md`，给出commit、修复说明、测试命令及真实结果。不自行合并、不自启动GPU、不把元数据修复称作模型能力提升。
003仍已验收，原合并授权不因004自动撤销；X可合并003并登记main SHA，但不得将004未审代码混入当前冻结实验。
