> 2026-10-16完成：本页唯一292步诊断已由用户完成，37原观测/293旧truth全匹配并获R2验收。**不要重复此run。** 用户已确认[010版本化测量/校准修订](../../collaboration/tasks/010_versioned_release_and_calibration.md)；现在等待X实现，不直接active。以下命令保留历史。

# Stage04 / 009：用户启动唯一init35释放诊断

2026-10-16。软件验收后部署冻结2c6dc4c20a12b4b894a3919d79b9bf810648332d；原模型、release／校准／评分代码不改。本页只运行用户已同意的35号原动作前缀，不重训、不重跑5条、不执行normal_active／Remain。

## 服务器直接执行

已登录root@122.204.216.104:30369后：

```bash
bash
source /HUBU-AI096/zp/ICML/stage04_release_audit_2c6dc4c/session.sh
release_diag 02_run run --plan "$DIAG_PLAN" --out "$DIAG_ROOT/run"
```

source只定义路径／日志函数，不启动native。release_diag先核293源码／4冻结部署文件，使用原SIM_PY虚拟环境Python，保存UTC／完整命令和command_exit／tee_exit；日志与输出拒绝覆盖。没有conda切换、依赖升级或新checkpoint。

- REPO：/HUBU-AI096/zp/ICML/LIBERO-Remain-stage04-release-2c6dc4c
- DIAG_ROOT：/HUBU-AI096/zp/ICML/stage04_release_audit_2c6dc4c
- DIAG_PLAN：上述根/plan/plan.json（由Codex纯文件准备，不要用户再运行plan）
- 新run输出：上述根/run
- 日志：上述根/logs/02_run.log
- SIM_PY：/HUBU-AI096/zp/ICML/LIBERO-Remain-normal00-stage02/.runtime/remaining_libero/venv/bin/python

## 范围和完成后

仅basket_s035_00从原bank已settle初态开始，最多原step1..292动作／293快照；逐步比较旧truth、原query观测hash和动作，侧录native状态／geometry/contact。首差异就停止并保留partial，不能用偏离轨迹的新测量冒充原真值。step292没有query；不执行293、不进入FINISH／hold／W150、不追加init37。

VLA／head／processor调用0；这一步是用户启动的真实native仿真重执行，可能使用原EGL渲染，不是模型推理或成功率评测。292控制步与初始化、内部native substep分别计数。

状态含义：diagnostic_completed=授权前缀及可观测对照完成；replay_mismatch=首个原轨迹对照不一致；technical_error=接口／证据技术问题；interrupted=中断。CLI分别0/2/130，tee单独记录。任何非完成状态都保留已有文件，不原地重跑、不删目录、不自动放宽容差；通知Codex读取summary.json、首差异和sidecar。

即使全部一致，也只证明这次从原保存初态重执行的可观测证据匹配，不能宣称恢复了旧step280完整隐状态、已经证实释放或已经校准成功。原calibrated=false／threshold=null和旧结果不变；本次不生成新label／阈值。更紧判据、296步K4、W150或其他轨迹需另行确认。

Codex没有代跑真实run；完成后由Codex只读核验产物并作研究决策。009／Stage04未closed，精确待删=[]。
