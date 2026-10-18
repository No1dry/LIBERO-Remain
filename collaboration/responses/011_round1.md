# 011首轮交付：十任务100条headless原始OFT基线

作者：X。日期：2026-10-18。任务：[011](../tasks/011_headless_ten_task_baseline.md)，需求：[Plan5](../../docs/experiment_plans/stage05_ten_task_baseline.md)。从main `bb2697d5d249be651c4a2282f8c783b626496103` 独立分支 `x/task011-headless-baseline` 实现；未合并010 PR #7，未改变旧FINISH/runner协议或任何历史实验结果。

实现commit：`c01f56a38d88f0949498d44240aafdfe6bdd0ff5`。后续交付登记仅更新本回复与STATUS，不改已测实现。

已提交[独立PR #8](https://github.com/No1dry/LIBERO-Remain/pull/8)，open、未合并，供Codex审查部署。交付登记 `7371e463d1fd253b2b2144702b38d5064ba2e4fa`；本次追加PR链接不改变实现或测试。main仍为上述 `bb2697d`，没有上传状态包、模型、运行报告或私有配置。

## 已交付

1. 独立 `remaining-headless-goal-endpoint-v1`，H520/20Hz/K4/chunk8。官方目标全真且相关可移动目标已释放5个相邻观测后在当前控制步结束，chunk剩余动作丢弃，无额外query/保持/开爪/归位。评价器GT端点不记成模型STOP，关节目标不要求释放，意外STOP为技术错误。A回退或明确违规sticky，但不缩短轨迹。
2. 复用十任务catalog、完整配对状态构造和独立回放；新增必要角色、目的容器/支撑映射、真实TCP site逐步world xyz与L复算。wrong_grasp/wrong_placement/table_drop按Plan5的2cm/K4操作定义记录，保留原始官方目标事实和unknown。
3. 固定[100条计划](../../configs/remaining_goals/headless/plan100.json)与[配置模板](../../configs/remaining_goals/headless/batch.example.json)：各任务初态0..9、mask10、policy seed7；basket0..4开发来源显式披露。主轨60、扩展40分别运行/等任务权重汇总，混合100仅描述。没有01/11模型调用、模型smoke、校准或自动retry。
4. 同一官方SOG10 OFT：90环境suite仍为90，通过显式受限transfer使用真实 `libero_10_no_noops` 统计。配置、worker与raw贯通训练域/评测域/统计域；任何动作前比较实际stats字节/内容SHA、动作/proprio组件、推理源码与配置。其他模型和普通同suite配置无跨suite隐式回退。
5. 每条双相机20fps/stride1视频、实际step0/query输入NPZ、逐步动作/query/chunk执行范围、TCP/物体/接触/几何/目标/事件证据。完整结果绑定来源、模型、代码/配置与执行证据；离线重新核验并计分。视频直接读已有观测，不额外render/step。
6. 按任务隔离准备/运行。未就绪任务保留10个预定missing，其余任务可先跑；执行/技术错误暂停该任务剩余条目，保留raw和错误，继续其余任务。已有任务核验后跳过，不覆盖、不重跑。Ctrl+C保存部分证据后停止整批。单条坏工件不抹掉同任务有效前缀；源manifest/模型身份无法验证时隔离整任务。
7. 准备阶段复用原build/replay CLI并单独计数控制step/耗时，异常调用已推进多少不确定时actual=null/partial_unknown，缺失或未完成ledger为unknown。新包装不增加step/RNG/模型调用，原构造器未修改。

## 代码范围

- 新增 `benchmark/remaining_goals/headless/`：planning、preparation/计数worker、environment/roles/geometry、runner/schema/evidence、workflow/metrics/CLI。
- 最小兼容变更：OFT adapter、其共享配置读取 helper、runtime static checker、worker metadata，以及 `scripts/remaining_libero.py` 的headless路由。原始动作prepare/get_action/decode、模型网络、FINISH训练/校准/动作接口、原状态构造/回放与物理bridge均未改。
- 010中已审只读保守几何的纯函数在新协议目录复用，来源为PR #7实现 `4521c53f22f670cc60e05d7aabac10403a75dfe8`；不导入其新校准流程、不要求010合并。释放测量在新协议下独立命名，旧默认不变。
- 新增CPU/fake协议、几何、环境、跨模块证据、100条workflow、准备计数、OFT跨suite/真实独立Python worker传输测试。

## 软件验证

| 验证 | 结果 |
|---|---|
| 全量 `python -m pytest tests -q -ra --basetemp reports/full011` | 2159 passed、15 skipped，376.33s，exit0 |
| 最后收窄worker校验后的受影响回归（命令如下） | 67 passed、2 skipped，10.32s，exit0 |
| 100条workflow/恢复跳过/故障/损坏/录制失败/Ctrl+C集成 | 13 passed，80.26s；同时纳入全量 |
| `diff --check`及旧FINISH/runner/build/replay/bridge范围比较 | 通过；这些旧生产模块无diff |

最终共新增177项CPU/fake用例：首批174项已纳入全量；最后3项为普通SOG10 spatial/object/goal的真实独立Python进程fake回归，随上述67项验证。最后修正只把worker强校验收窄至显式transfer；headless主轨仍在workflow中严格验证。没有把这3项虚计入更早启动的全量计数。

```bash
python -B -m pytest tests/test_remaining_oft_transfer.py \
  tests/test_remaining_adapter_openvla_oft.py tests/test_remaining_policy_transport.py \
  -q -ra --basetemp reports/compat011
```

全量15个跳过：3个Windows无symlink权限、1个POSIX venv集成、11个未安装可选固定仿真源码的catalog检查；不是新增headless测试跳过。末轮2个跳过为原worker的Windows symlink/POSIX限制。测试全部使用既有CPU解释器或fake子进程；没有加载研究权重或创建native仿真。

测试覆盖：t0合同、K4重置、H内/H边界、chunk中途截断、STOP错误、无额外动作/query/hold；违规sticky及轻碰不罚；同一site路径与缺步/NaN/换site拒绝；真实纯几何函数→runner→NPZ→证据读回→metric；主/扩展身份与stats一致、旧同suite路径；固定100/部分任务就绪/失败隔离/不覆盖/不重跑；证据损坏、部分录制失败、Ctrl+C、视频保存、离线只读；准备计数及子进程强杀后的unknown。

模板 `dry-plan` 实际文件检查保留100条/10任务，当前本机模板路径未填写，ready=0，`simulation_created=false`、`weights_loaded=false`。这不是状态bank已备齐，也不是模型性能结果。

## 部署与真实启动

完整命令、真实参数、两解释器兼容、路径规则、配置和产物说明见[Stage05 runbook](../../docs/headless_ten_task_baseline_runbook.md)。入口：

```bash
python -m benchmark.remaining_goals.headless.cli --help
python -m benchmark.remaining_goals.headless.cli budget-plan
```

部署复用已有仿真conda/venv Python与OFT模型Python，不解析掉venv符号链接；已有本checkout runtime.json时可用 `python scripts/remaining_libero.py headless ...`。服务器路径/私有JSON由Codex填写，不入库。

下一步：Codex集中建议式审查并冻结部署 → 给用户prepare命令 → 用户准备/独立回放 → Codex读取并冻结清单 → 用户分轨启动100条基线 → Codex离线核验、汇总和分析。允许已就绪任务先执行，固定100覆盖仍保留。本次没有真实模型、native仿真、状态构造/回放、FINISH训练或几何校准。

## 明确边界

- CPU/fake测试不证明十任务真实安装兼容、成功率或事件测量覆盖；真实任务/资产缺失会给出具体错误，不能替换来源。
- 初始工作台支撑只在真实水平collision顶面contact证据充分时成立；间接经盘子/物体传递支撑未建立支撑图，标unknown。不使用LIBERO generic On(table)的中心距离限制代替工作台支撑。
- 不支持的collision、接触过滤覆盖或关系/释放证据保留unknown。未知不冒充无违规；版1不覆盖所有语义冗余或场景损坏，没有临时位移/倾角惩罚或新增VLM裁判。
- 源reset XML保持旧严格验证；恢复后的炉子可视site_rgba可能变化，故分别绑定 `source_reset_model_xml_sha256` 与恢复后实际几何XML，不误把合法可视变化当源状态被替换。
- 统计、源码及动作组件SHA不等于全部大模型权重字节校验；metadata保留 `checkpoint_bytes_verified=false`，部署需冻结已有完整snapshot。
- 原候选 `construction.legal=false` 等事实不改；技术回放通过不证明语义/剩余可达性。旧FINISH分数不能直接比较成本轮headless分数，旧保持段不计成本轮原始模型路径。
- 新summary对无成功任务给L=N/A，主表只有成功率与成功条件L；technical/unknown/missing与失败原因另列，所有100个预定来源保留。

010/Stage04历史状态保留，未伪造closed、未重写旧raw/视频/分数、未删除交流文件。
