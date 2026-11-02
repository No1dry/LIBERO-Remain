# Task033：正式启动新增三任务30条mask10模型评测

日期：2026-11-02。新增三任务初态已30/30 ready（100%），微波炉0..9各完成150构造与两次独立150回放；本轮微波炉实际6100控制调用，不是模型episode。旧抽屉/双壶20来源复用。此命令才是OpenVLA-OFT模型评测，不是再做初态准备。

固定评测源码d8541ef4a4bb4cc2e34c95b10227ea5fcaddaff9（R7实现c8c50e63）；原官方SOG10 checkpoint/统计量、crop/proprio/全精度、seed7/chunk8/H520不变，无FINISH/selector。只执行task_id3/8/9各10条：黑碗入下抽屉并关闭、双摩卡壶上炉、黄白杯入微波炉并关门。旧六60条10只读复用，正式九任务90分母保留。00完整90不重跑。

## 在服务器复制执行（bash）

沿用原仿真venv和runtime中固定的独立OFT worker环境，不用selector环境，不安装/升级依赖。配置已由Codex纯文件准备；不再运行configure/dry-plan或任何补建入口。

```bash
source /HUBU-AI096/zp/ICML/LIBERO-Remain-normal00-stage02/.runtime/remaining_libero/venv/bin/activate
cd /HUBU-AI096/zp/ICML/LIBERO-Remain-task033-r7-d8541ef4
export PYTHONPATH=/HUBU-AI096/zp/ICML/LIBERO-Remain-task033-r7-d8541ef4
export LIBERO_CONFIG_PATH=/HUBU-AI096/zp/ICML/LIBERO-Remain-normal00-stage02/.runtime/remaining_libero/libero_config
export MUJOCO_GL=egl PYOPENGL_PLATFORM=egl
export CUDA_VISIBLE_DEVICES=0
export HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1
set -o pipefail

python -u -m benchmark.remaining_goals.headless.nine_cli run \
  --config /HUBU-AI096/zp/ICML/task033_r7_d8541ef4/configs/mask10-new3.json \
  --out /HUBU-AI096/zp/ICML/task033_r7_d8541ef4/runs/mask10-new3-001 \
  2>&1 | tee -a /HUBU-AI096/zp/ICML/task033_r7_d8541ef4/logs/eval-mask10-new3.console.log
echo "eval_exit=${PIPESTATUS[0]} tee_exit=${PIPESTATUS[1]}"
```

首次执行不要加--continue/--allow-missing。不要提前创建run输出目录，不运行旧R3二十条配置或旧补建命令。模型轨迹失败是正常科研结果，会保留并继续；技术错误/中断则交回日志，不自行重跑已尝试episode。

## 输出、成功率和视频

- 主结果：run目录的summary.json、report.md；运行结束自动保存，合并原六任务60条形成正式90条10报告，覆盖率和成功率分开。
- 逐条状态：run目录batch.json（每episode更新），只会包含这次新增30个模型episode。旧六仅作为引用，不重新调用模型。
- 原视频：run目录episodes/<episode_id>/videos/<episode_id>.mp4，完成轨迹必须保存全程录像。raw记录/模型身份/来源与状态证据一并保存。
- 终端日志：/HUBU-AI096/zp/ICML/task033_r7_d8541ef4/logs/eval-mask10-new3.console.log。终端不一定逐条打印SR，不能把未显示SR理解为未评测；最终summary包含官方目标达成率与合规成功率。

运行中如要读一次完成进度（不启动或监督作业）：

```bash
python -c 'import json; from collections import Counter; from pathlib import Path; p=Path("/HUBU-AI096/zp/ICML/task033_r7_d8541ef4/runs/mask10-new3-001/batch.json"); d=json.loads(p.read_text()); c=Counter(x["status"] for x in d["episodes"].values()); n=c["completed"]; print(f"新增模型评测完成：{n}/30 = {n/30:.2%}"); print(c)'
```

运行结束、报错或暂停后把结果交Codex读取；不自行删除输出或重复启动同批。正式九任务10现有60/90模型记录（66.67%），本次新增30评完才达到100%；当前准备100%不是VLA成功率。

用户亲自启动这条真实模型命令。Codex没有启动或排队任何模型/仿真/训练，也不自动监控。X此阶段无实现待办，不以验收确认作为开跑门槛。
