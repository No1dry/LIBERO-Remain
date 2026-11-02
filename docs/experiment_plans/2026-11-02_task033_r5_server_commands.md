# Task033 R5：用户启动微波炉10初态补建

源码固定942db12fec2596d5faee6876e99587a7749e0d96，实现fc2dd617b9434a82d27710d1da023101e87af1f5。软件审查通过不代表真实微波炉已通过。新增初态当前20/30=66.67% ready，微波炉仍待真实补建；新三30条10模型评测尚未启动。

## 本次只做什么

只补微波炉index0..9；先执行本批固定0号，只有构造与两次独立回放真正ready才继续1..9，0号失败即停。0号不是额外probe。其他20个初态、00、旧六均复用，不重建、不评部分20，不自动串联模型，不提高原物理阈值或24/400预算。

## 在服务器复制执行（bash）

沿用已跑通的原仿真venv，不用selector环境或解析后的conda基础解释器，不安装/升级依赖。下面主命令仍为python。

```bash
source /HUBU-AI096/zp/ICML/LIBERO-Remain-normal00-stage02/.runtime/remaining_libero/venv/bin/activate
cd /HUBU-AI096/zp/ICML/LIBERO-Remain-task033-r5-942db12f
export PYTHONPATH=/HUBU-AI096/zp/ICML/LIBERO-Remain-task033-r5-942db12f
export LIBERO_CONFIG_PATH=/HUBU-AI096/zp/ICML/LIBERO-Remain-normal00-stage02/.runtime/remaining_libero/libero_config
export MUJOCO_GL=egl PYOPENGL_PLATFORM=egl
set -o pipefail

python -u -m benchmark.remaining_goals.headless.repair033_microwave prepare \
  --inventory /HUBU-AI096/zp/ICML/task033_r3_06817e61/preparation/sources.json \
  --preparation-report /HUBU-AI096/zp/ICML/task033_r3_06817e61/preparation/preparation_report.json \
  --out /HUBU-AI096/zp/ICML/task033_r5_942db12f/microwave_repair \
  2>&1 | tee -a /HUBU-AI096/zp/ICML/task033_r5_942db12f/logs/microwave_prepare.console.log
echo "prepare_exit=${PIPESTATUS[0]} tee_exit=${PIPESTATUS[1]}"
```

首次执行只复制上面这一条，不提前创建microwave_repair、不加--continue/retry，不重跑plan。返回2表示仍有来源未ready；首0失败后其余9未尝试是预期停止保护，不是模型成功率0%。返回0表示报告ready30，仍由Codex读取实际证据后给单独模型命令。

## 进度与交回结果

主报告按来源更新：
`/HUBU-AI096/zp/ICML/task033_r5_942db12f/microwave_repair/microwave_repair_report.json`。
组合来源同目录sources.json；原worker操作账本在preparation/preparation_report.json，真实控制计数和候选原记录保留。

另一个终端需要时读一次，不启动监控或仿真：

```bash
python -c 'import json; from pathlib import Path; p=Path("/HUBU-AI096/zp/ICML/task033_r5_942db12f/microwave_repair/microwave_repair_report.json"); d=json.loads(p.read_text()); n=d["counts"].get("ready",0); print(f"初态就绪：{n}/30 = {n/30:.2%}"); print(d["counts"],"stopped_after_source0=",d["stopped_after_source0"])'
```

若终端暂未刷新，以上JSON是按来源写入的状态，不代表卡死。脚本结束、报错或中断后保留目录/日志并交Codex读取；不要自己删除输出重跑。普通续跑不是失败重试，本轮先不交额外真实命令。

用户已选择30个新增来源齐备后一次评30；当前九任务10模型记录仍60/90=66.67%，与来源准备进度分开。00完整90条和旧六10不重跑。
