# Codex Review：任务 003，PR #2

日期：2026-10-09。审查者：Codex。
PR：https://github.com/No1dry/LIBERO-Remain/pull/2
审查 HEAD：`fb89ccd2d10f4612c8780f58afae0a0d53480929`。
代码实现：`3a50f635b5eb7329386b381879ce53dab3bfbd46`。
基准 main：`fea75fc170b5c3047433316566dc52528c5caf2a`。

## 裁决

**代码功能 accepted，无阻塞发现。** X 获准在实现代码无新增未审查修改的前提下合并 PR #2，
登记 main SHA。然后由 DeepSeek 按[首批执行说明](../../docs/experiment_plans/stage02_normal00_first_batch.md)
先做2条技术 smoke，再执行固定5个初态×2协议的10条 00 能力回归。

本轮不训练模型，不跑 partial 或六模型矩阵。任务是否成功不是技术 smoke 的通过条件。
没有获得新模型成功率，代码验收不能替代后续结果审查。

## 独立测试与真实接口核对

- macOS Python 3.12.7：**1095 passed，12 skipped，17.16s**。
  11 项可选固定 simulator sources，1 项本机无 imageio_ffmpeg。
- Linux Python 3.10.20、禁用 CUDA 的完整软件测试：**1096 passed，11 skipped，47.62s**。
  跳过项均为审查副本未安装的固定 simulator sources。
- dry-plan 独立复核：恰为 basket indices 0..4 的5 official + 5 remain；
  5950 模型动作、50官方等待、1150 Remain settle/audit，最多745次 chunk 查询。
- 官方真实环境接口（没有加载模型）：准确 task index=0、50个官方初态、初态0；
  native reset/set_init_state + 10步 dummy 后 `[False,False]`，双相机/proprio可读取。
- Remain 真实独立准备（没有加载模型）：80步 settle + 150步动态审计全部完成且通过；
  从保存的审计前 base 正式恢复后，flattened state 逐位一致，目标仍为 `[False,False]`。
- Git diff：旧 metrics.py、runner.py、libero_env.py 和 adapters 未改；diff whitespace检查通过。

真实环境检查使用已有安装，产物保留在本地 `reports/libero_remain_task003_review_2026-10-09/`
和服务器独立审查目录。未调用 policy、未加载权重、未产生 VLA 任务分数。
早期一次短时官方检查超90秒，以及审查临时启动命令的路径/时序失败，不属于 X 的计分或执行错误；
纠正审查启动方式后，上述两个检查实际通过。环境冷启动耗时不能用控制频率推算。

## 已核对的关键契约

1. 精确索引、固定分母、不替换失败来源；错误、missing与策略失败区分。
2. 官方10 wait和520策略步分开；success即停来自评估器，不伪装模型 STOP。
3. Remain80 settle/150 audit属于准备，策略670步完整执行；恢复保存 base，未重复wait。
4. 共同 all-goals-ever只看0..H；Remain joint/stable另列，未把H后成功算预算内成功。
5. 原生模型环境和独立仿真环境分进程；动作已经在adapter解码，不重复翻夹爪/反归一化。
6. 单 mask 00 使用 capability schema，不绕过旧配对manifest校验、不冒充完整benchmark。
7. step0、首动作、trace、结束原因、版本/源码/初态身份与视频错误均有记录。

## 实验前提与注意事项

- 显式设置 `runtime.official_libero_config_path`，避免用不匹配的默认本机配置。
  审查机器用现有固定源码的配置目录，official仍用model Python里的robosuite1.4.1。
- 同index不保证两协议的策略起点相同；原生cache/restore、80 settle与版本差异需保留解释边界。
- 每case重置policy seed7不同于官方整批脚本只设一次seed；已在代码/文档中声明。
- 默认case timeout是故障上限，不是耗时估计。首批建议显式2400秒，超时留错误、不换index。
- 本轮已验证 index0 的环境准备；其他初态仍需实际执行，不把单例技术验收外推所有来源。

## Stage 01 核验

PR #1 已合并到 main `fea75fc…`；main的Stage01总结与既有本地归档字节/hash一致。
Codex确认 Stage01功能阶段可 closed。原有交流暂保留供当前PR和实验追踪；只有最终总结更新、
GitHub与本地新备份再次核验后才可清理，不删除任务003或原始实验数据。
