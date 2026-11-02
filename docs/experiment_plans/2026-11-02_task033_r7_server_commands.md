# Task033 R7：用户启动版本化位姿稳定补建

固定源码d8541ef4a4bb4cc2e34c95b10227ea5fcaddaff9，实现c8c50e639b01802382b2bdfee73f0f946e8c465a。独立95项CPU/fake通过；这不是新物理来源通过或模型效果。当前新三初态仍20/30=66.67%ready，新三30条10模型未开始。

## 本次范围

只补微波炉0..9，沿用R5几何/24候选/400上限及首0门控。A杯子按完整150控制步/151观测的位置跨度≤5mm、姿态跨度≤1°准入，A原始速度保留诊断；非A速度、穿透/谓词/机器人/观测与两次独立150回放不变。stability_profile=v7与RGB observation_profile=v6分开，旧20和旧失败原样保留。

本次使用新物理reader，不能切回冻结06817e61来读取新v7工件。代码和输出都已另设目录，不热改旧部署。

## 在服务器复制执行（bash）

沿用原已跑通LIBERO仿真venv，不使用selector或解析后的conda基础解释器，不安装/升级依赖。

```bash
source /HUBU-AI096/zp/ICML/LIBERO-Remain-normal00-stage02/.runtime/remaining_libero/venv/bin/activate
cd /HUBU-AI096/zp/ICML/LIBERO-Remain-task033-r7-d8541ef4
export PYTHONPATH=/HUBU-AI096/zp/ICML/LIBERO-Remain-task033-r7-d8541ef4
export LIBERO_CONFIG_PATH=/HUBU-AI096/zp/ICML/LIBERO-Remain-normal00-stage02/.runtime/remaining_libero/libero_config
export MUJOCO_GL=egl PYOPENGL_PLATFORM=egl
set -o pipefail

python -u -m benchmark.remaining_goals.headless.repair033_pose_stability prepare \
  --inventory /HUBU-AI096/zp/ICML/task033_r3_06817e61/preparation/sources.json \
  --preparation-report /HUBU-AI096/zp/ICML/task033_r3_06817e61/preparation/preparation_report.json \
  --revision-report /HUBU-AI096/zp/ICML/task033_r5_942db12f/microwave_repair/microwave_repair_report.json \
  --out /HUBU-AI096/zp/ICML/task033_r7_d8541ef4/microwave_repair \
  2>&1 | tee -a /HUBU-AI096/zp/ICML/task033_r7_d8541ef4/logs/microwave_pose_prepare.console.log
echo "prepare_exit=${PIPESTATUS[0]} tee_exit=${PIPESTATUS[1]}"
```

首次只运行这条；不要提前创建microwave_repair、不加continue/retry、不重跑旧plan或旧R5命令。0号是本批首个来源，不是额外probe；构造和两个独立回放实际ready后才继续1..9。若首0失败，程序停止其余9，保留未尝试，不用同命令重试。

退出0表示报告30ready；退出2表示还有准备缺口，不是模型成功率0%。完整新30就绪后，Codex读真实证据再给单独的一次30条模型命令，不自动串联、不部分20、不allow-missing。

## 查看进度与结果

主报告：
`/HUBU-AI096/zp/ICML/task033_r7_d8541ef4/microwave_repair/microwave_repair_report.json`。
组合来源同目录sources.json；原worker账本在preparation/preparation_report.json。失败原证据/完整raw state/qvel/接触/位姿映射/观察检查均保留。

另开终端按需读一次（不是监控或新实验）：

```bash
python -c 'import json; from pathlib import Path; p=Path("/HUBU-AI096/zp/ICML/task033_r7_d8541ef4/microwave_repair/microwave_repair_report.json"); d=json.loads(p.read_text()); n=d["counts"].get("ready",0); print(f"来源就绪：{n}/30 = {n/30:.2%}"); print(d["counts"],d["stability_profile"],"stopped_after_source0=",d["stopped_after_source0"])'
```

核心状态随来源写入JSON；暂未刷新终端不等于卡住。运行结束、报错或中断后保留目录，交Codex读取，不自己删目录/换index/改阈值重跑。若确需续跑，读回原证据后再提供精确命令。

旧六10六十条、九任务00九十条均不重跑。正式10模型记录覆盖仍60/90=66.67%，与这里初态准备进度分开。
