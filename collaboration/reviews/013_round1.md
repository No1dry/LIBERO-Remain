# 013 Round 1：软件验收通过，执行纯文件离线重算

日期：2026-10-18。审查：Codex。PR [#10](https://github.com/No1dry/LIBERO-Remain/pull/10)。冻结交付 `c6dc98de0c54517c976057598b60f4cedf7fa3e5`，实现 `ba21f388a29d7f7275036293833b50c63cb9be9a`。

裁决：**accepted（软件范围），无阻塞返修。**

## 核验

- 修复明确位于_initial_support的body原点高度假设，真实顶面法向/接触点容差保留；2cm/K4、侧面/无接触/不支持几何的unknown边界不变，对所有相关对象统一适用。
- v1静态证据按legacy规则读取，新v2声明support_rule；旧raw/static与execution绑定不被改写。避免只改helper使旧记录被错误拒绝的问题。
- 离线入口先复用原读取链核对旧绑定，然后只重算table_drop及其影响的sticky/unknown，派生输出明确不是新执行。goal、释放、端点/步数、路径、动作/query及其它事件通道保持一致。
- 对所有可核验原记录统一处理，固定100列表/缺口保持；计分没有忽略table_drop或将unknown统一设False，真实新掉桌也会成为失败。
- 独立定向CPU/fake：支撑/旧环境/派生集成64 passed（5.02秒）；旧计分/端点6 passed、33 deselected（0.18秒）。合计70 passed、0 skipped。不跑全库、多平台或真实sim/model。
- 342个跟踪文件与固定GitHub tree的blob身份/SHA一致。代码部署独立目录，纯文件CPU重算由Codex执行，用户无需启动任何真实实验。

## 交接

同意直接对既有批次重算。原批次/原summary身份单独保留；输出新目录，旧结果不覆盖，不追加模型、回放、训练或准备。实际新分数以统一复算为准，21/80只是此前诊断线索，不作验收目标。

本次不处理剩余20条来源准备缺口，不扩benchmark，不清理交流或代合并实现。X可按accepted裁决合并保持已审实现的PR并登记；不为工程偏好返修。
