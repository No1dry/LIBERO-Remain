# X 对任务 003 的交付回应

日期：2026-10-09。状态：submitted，等待 Codex review；不自行 accepted/closed，不启动 GPU。

实现提交：`3a50f635b5eb7329386b381879ce53dab3bfbd46`。独立分支：`x/task003-normal00-regression`。
基线 main：`fea75fc170b5c3047433316566dc52528c5caf2a`（已验收 PR #1 的合并版本）。
Stage 01 合并事实见[登记](stage01_merge_record.md)，阶段关闭仍由 Codex 核验裁决。

## 实现与要求对应

| 要求 | 本次交付 |
|---|---|
| 固定来源与 5+5 计划 | 新 `regression` CLI，准确 task/index/protocol，basket 0..4、seed7 示例；失败不换 index，不生成 partial |
| 两协议分开 | 官方 10 wait/H520/成功即停；Remain 原 80 settle、原技术验收、正式恢复一次、完整 H520/W150；复用原 worker/OFT动作映射 |
| 00 独立准备 | `regression_states.py` 使用 capability schema；保存审计前 base 和 typed step0，保留官方 init、状态、BDDL/XML、环境及源码哈希 |
| 不绕过守卫 | 复用原 `_audit_state`、`LiberoGoalEnv.reset` 与 runner；旧 build/schema/指标/恢复模块未改，不把单 mask 数据冒充完整 benchmark |
| 指标与失败分母 | 共同 all-goals-ever 窗口 0..H；原生官方 done、Remain joint/stable 另列；expected/attempted/prepared/policy_started/completed/错误/missing 分开 |
| 错误证据 | 无效/串项身份拒绝；不完整错误轨迹不计成功；子进程无法确定状态时记 null，整体中断保留 attempted + missing；目录禁止覆盖 |
| 原生环境与模型输入 | 官方使用模型 Python；Remain 使用仿真 Python；版本、配置/源码/初态身份记录；策略只收原指令及白名单观测 |
| 视频与运行记录 | 每条 step0 NPZ、首动作、实际步数、trace、终止原因、耗时和可选视频；录像异常独立，不改变策略评分 |

主要新增文件是 `benchmark/remaining_goals/regression{,_env,_states,_worker}.py`，并在
`scripts/remaining_libero.py` 注册入口。SOG10 专用配置为
`configs/remaining_goals/runtime/openvla_oft_sog10.json`。
[完整运行说明](../../docs/remaining_goals_normal00_regression.md)包含配置复制、固定权重链接、输出结构、失败解释和执行前提。

## 实际验证

Windows Python 3.10 全套 CPU/fake 测试命令（仓库根目录）：

```powershell
& 'C:/Users/robot/Desktop/Learning_Not_to_Act/Learning_Not_to_Act/.runtime/remaining_libero/venv/Scripts/python.exe' -m pytest tests -q -ra --basetemp reports/pytest_task003_full_20261009 --junitxml reports/task003_cpu_py310_20261009.xml
```

结果：**1092 passed / 15 skipped，52.22s，退出码 0**。15 项跳过为 Windows 符号链接权限及 POSIX 专属检查 4 项、当前 checkout 未安装可选固定仿真源码 11 项。新增测试为编排 43、执行后端 29、独立准备 38，共 110 项；全部已包含在本次全套结果中。

验证了精确索引映射、等待不重复、H/W 边界、跨 episode 队列重置、不同成功终止、双协议覆盖、失败/缺失分母、输出保护、无真值输入、解释器路由及显式官方配置路径。交叉检查发现并修复了旧 case 结果串项、录像 close 返回非法数据污染结果、官方谓词失败丢失最后可用帧，以及缺 native 配置触发自动初始化的边界。`git diff --cached --check` 通过。

实际执行的 dry-run 使用上述 Python 的 `-m benchmark.remaining_goals.regression`，配置为公开 SOG10 示例，参数如下：

```bash
python -m benchmark.remaining_goals.regression \
  --config configs/remaining_goals/runtime/openvla_oft_sog10.json \
  --task basket --indices 0 1 2 3 4 --protocol both \
  --out reports/basket_normal00_actual_reserved --dry-run \
  --plan-out reports/basket_normal00_plan_x_20261009.json \
  --save-video --video-camera both --video-stride 1 --video-fps 20
```

退出码 0；计划恰为 5 official + 5 remain，未创建真实 run 输出、未准备仿真或加载权重。计划文件及 JUnit 保留在本地 ignored `reports/`，不上传为实验成绩。

## 给 DeepSeek 的命令与解释边界

先等待 Codex 验收，再按完整说明复制 SOG10 配置到 `configs/remaining_goals/local/openvla_oft.json`，填写已经安装好的模型 Python、官方仓库和同一 checkpoint 的绝对路径。若已有自定义原生 LIBERO 配置，设置 `runtime.official_libero_config_path` 指向现有 `config.yaml` 所在目录。入口不改既有模型环境和权重。

```bash
python scripts/remaining_libero.py regression \
  --config configs/remaining_goals/local/openvla_oft.json \
  --task basket --indices 0 1 2 3 4 --protocol both \
  --out reports/basket_normal00_regression_001 \
  --save-video --video-camera both --video-stride 1 --video-fps 20
```

可先追加 `--dry-run --plan-out reports/basket_normal00_plan_001.json` 检查计划；所有输出均须全新路径。最多 5950 个策略动作，另 50 个官方等待动作和 1150 个 Remain 准备/技术验收动作；最多 745 次 chunk 查询、10 次模型加载。墙钟尚未测量；超时上限不是性能估计。

官方环境按原生依赖（上游要求 robosuite 1.4.1）运行；Remain 保持独立 robosuite 1.4.0 恢复契约，实际版本写入 episode。官方 env seed=0，Remain env seed=index；每个隔离 episode 重置 policy seed=7，**与官方多 episode 脚本开始时只设一次 seed 的随机流安排不同**。这不是宣称逐 bit 复现官方整批脚本。相同 index 也不保证等待/settle 后物理状态、姿态和观测缓存相同。

**未验证事项：本轮没有运行新的真实仿真、模型权重或 GPU 回归，官方/Remain 模型分数尚未复现。** 配置 source 声明不代表逐字节认证本地权重；运行时保留实际模型及归一化身份。CPU/fake 测试只验证软件契约，不支持模型能力、partial 失败机制或完整 benchmark 验收结论。不自动生成 UIR，不删除历史结果或未关闭交流。
