# 033 R3服务器命令：只补必要10初态

日期：2026-11-02。软件和文件部署已验收；固定源码 `06817e61e07975279b4f3c4b29f410edc2357172`，实现 `65e0509d0fc713130110f0fcce158e619b49c744`。此文件不是已执行日志：**下面真实命令仍由用户亲自启动**。

## 本次做什么

实际文件计划已生成，exit0、无blocked和reuse问题。新增三任务10初态8/30=26.67%可复用（原5＋新3个原证据派生），剩22个真实来源操作：抽屉10、微波炉10、双壶来源9构造及回放、来源7只成对回放300步。不是模型评测，不调用VLA，不追加训练；旧六、完整00及8条可复用来源不重跑。原failed和原raw不变。

## 直接在服务器复制运行（bash）

沿用已跑通LIBERO的原仿真venv，不用selector环境、不安装/升级依赖。仿真venv和OFT worker虽然链接同一底层conda，不能替换为解析后的conda Python；激活此venv后主命令就是python。

```bash
source /HUBU-AI096/zp/ICML/LIBERO-Remain-normal00-stage02/.runtime/remaining_libero/venv/bin/activate
cd /HUBU-AI096/zp/ICML/LIBERO-Remain-task033-r3-06817e61
export PYTHONPATH=/HUBU-AI096/zp/ICML/LIBERO-Remain-task033-r3-06817e61
export LIBERO_CONFIG_PATH=/HUBU-AI096/zp/ICML/LIBERO-Remain-normal00-stage02/.runtime/remaining_libero/libero_config
export MUJOCO_GL=egl PYOPENGL_PLATFORM=egl
set -o pipefail

python -u -m benchmark.remaining_goals.headless.repair033_v6 prepare \
  --plan /HUBU-AI096/zp/ICML/task033_r3_06817e61/plan/repair_plan.json \
  --out /HUBU-AI096/zp/ICML/task033_r3_06817e61/preparation \
  2>&1 | tee -a /HUBU-AI096/zp/ICML/task033_r3_06817e61/logs/prepare.console.log
echo "prepare_exit=${PIPESTATUS[0]} tee_exit=${PIPESTATUS[1]}"
```

此prepare输出此前未创建；只首次执行这条，不重跑plan。暂不加--continue/retry，不删旧输出或改index。退出2表示仍有准备缺口，不是模型成功率0%。中断、错误或完成后把结果交Codex读取。

## 输出和进度

- 汇总（运行时按来源更新）：`/HUBU-AI096/zp/ICML/task033_r3_06817e61/preparation/preparation_report.json`。
- 组合来源：同目录 `sources.json`。
- 终端日志：`/HUBU-AI096/zp/ICML/task033_r3_06817e61/logs/prepare.console.log`。核心状态在JSON，未刷终端不代表未运行。
- 每来源的实际控制调用账本保留在 `preparation/sources/` 下，失败或中断不虚报0次。

另一个终端可随时读一次当前准备进度（不创建仿真，不启动监控）：

```bash
python -c 'import json; from pathlib import Path; p=Path("/HUBU-AI096/zp/ICML/task033_r3_06817e61/preparation/preparation_report.json"); d=json.loads(p.read_text()); s=d["sources"]; n=sum(r["status"]=="ready" for r in s); print(f"来源就绪：{n}/30 = {n/30:.2%}"); print(d.get("counts",{}))'
```

全部30来源完成后，Codex据实际证据配置仅新增30条10模型评测，再给单独启动命令；本命令不自动串联模型。00完整官方SR86.67%（78/90）不重跑；10现有模型覆盖66.67%（60/90），与这里的来源准备进度分开。
