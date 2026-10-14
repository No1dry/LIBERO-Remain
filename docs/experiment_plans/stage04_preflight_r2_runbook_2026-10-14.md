# Stage04 R2已部署版本：只重做同一11的真实预检

2026-10-14，Codex。已审冻结head=`4f76f4917a9174fc5b80ef83e3cf21eaf053c98d`，对应X实现a7dda8d。修复OnTheGroundPanda类型误拒绝，全部夹爪／OSC／FINISH控制语义不放宽。

新源码：`/HUBU-AI096/zp/ICML/LIBERO-Remain-stage04-finish-4f76f49`。
新配置／session／结果／日志根：`/HUBU-AI096/zp/ICML/stage04_finish_4f76f49`。

204源码和4个部署文件核验一致；本地全套1492 passed/12 skipped，新增FINISH本地和服务器均261 passed。**这些是CPU软件验证，Codex没有运行本次真实preflight。**

## 1. 用户现在启动

若已登录服务器，直接从bash/source开始。输入SSH密码时交互输入，文档不保存。

```bash
ssh root@122.204.216.104 -p 30369
bash
source /HUBU-AI096/zp/ICML/stage04_finish_4f76f49/session.sh

finish_sim 01_preflight_11_r2 preflight \
  --source-config "$CFG/preflight_source.json" \
  --episode-id basket_s000_11 \
  --out "$OUT/environment_preflight_11_r2"
```

session只设置新源码cwd、原sim/model Python、原固定LIBERO配置与EGL，并定义显式命令日志函数；不自动启动任何实验。finish_sim在命令前核验冻结文件，记录UTC/完整命令/command_exit/tee_exit；不存在后台链式作业。

sim Python仍`/HUBU-AI096/zp/ICML/LIBERO-Remain-normal00-stage02/.runtime/remaining_libero/venv/bin/python`，保留venv symlink选择，不解析为base Python；不要pip升级或bootstrap环境。

本命令使用原source001及独立replay报告，task／mask／seed／camera／指令不变。只真实恢复同一个11并执行4个保持步，不加载VLA，不是模型rollout或停止能力成绩。

## 2. 产物与检查

新报告：

`/HUBU-AI096/zp/ICML/stage04_finish_4f76f49/results/run01/environment_preflight_11_r2/preflight.json`

新日志：

`/HUBU-AI096/zp/ICML/stage04_finish_4f76f49/logs/run01/01_preflight_11_r2.log`

期待command_exit=0／tee_exit=0、status=recorded、error=null、model_calls=0、trace完整0..4。初始观测应保存为NPZ；hold_contract应标明实际OnTheGroundPanda／PandaGripper、当前pose和原finger目标保持、gripper=0。

检查五个真实状态的两目标、released及对象contact／hand/pinch clearance。unknown不当作已释放或确定模型失败。若技术错误、未知释放或目标回退，先保留并交Codex，不改源码／GT／out来救通过。4步预检不能替代正式W150保持或所有样本覆盖验证。

此preflight没有视频产物，只有初始观测和实际trace；不要称有模型视频。任务完成后告诉Codex，Codex上服务器读取报告和日志，你不用手工下载整理。

## 3. 不覆盖、不扩实验

只运行上面这一条新命令。已有日志/out拒绝覆盖，若中断／失败不在相同out重跑，先交Codex检查并给新的明确命令。

旧38版代码、`environment_preflight_11/preflight.json`及原失败日志不修改。不要再用旧session运行；不要在源码快照git pull（无.git）。本轮新的主错误已软件修复，但真实效果未知。

**当前不启动HDF audit、特征、head训练、parity、校准或Remain eval。**官方HDF与official init来源对应仍未建立；兼容性修复不改变这项门槛。旧全流程runbook只作为历史软件入口保留，后续需先确认来源设计／记录。

分工：X修改实现，本轮R2软件已通过；Codex校验部署／文件准备／结果审查；用户确认并启动真实实验。没有自动监控、追加或重试作业。

下一步操作：按第1节启动同一11预检，完成后由Codex审查报告。执行者：用户启动，Codex审查。
