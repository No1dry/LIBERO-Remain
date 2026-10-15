# Stage04：089e0b7真实audit在布局身份检查处停止

2026-10-15。用户运行冻结089e0b7fa3916e6444b0880ca61101cac791c1ba的同一audit。status=insufficient、command_exit=2/tee_exit=0；restore_attempts=1、rows=0、hold=0，无标签/类别覆盖或模型分数。

确切错误：`demonstration XML changed basket scene inventory or saved-state joint/layout identity`。当前资源解析已通过、provider已建立，加载第一条训练域XML（按实际排序为demo_10）后，_layout结果与默认场景的_base_layout不相等，在HDF saved state真正恢复之前被拒绝。现有产物没有保存逐字段before/after/diff，**不能据此判断是可兼容ID重排、命名差异，还是实质结构/状态地址变化**，更不能直接删guard或仅凭123维state放行。

_layout同时比较nq/nv/nu/nbody/ngeom/nsite/njnt、按ID排列的name、joint type/qposadr/dofadr、body/geom/site关系和actuator transmission。固定源码的reset_from_xml_string会重新绑定部分native references，但这也不证明任意差异安全。R5的资源路径/字节/SHA验收保留，不能等同于物理audit通过；目前未认定需要哪一项代码修复。

## 只读排查与原始证据

Codex只读取结果、已保存源包及XML，没有创建/编译新场景、restore/step或跑模型。全部50条示范XML的有序worldbody body/joint/geom/site/camera名称/type签名一致（1个签名）；每条28 body、17 joint、162 geom、23 site、8 camera。这是静态XML清单，不是compiled layout，也不能替代默认场景的实际对比。来源已有state只是npy数组，历史源审计无完整compiled layout可供复用。

报告：`/HUBU-AI096/zp/ICML/stage04_finish_089e0b7/results/run01/audit/audit.json`，文件SHA `63af0f9583efa5502a1529c5e648a99f34432b23795eb04170d7fe28d1b757fd`；内部audit hash ab0bdd88a1a14e6c80a92163c81e4958b2b229664bca63210efb30ba2a73fe00。
日志：`/HUBU-AI096/zp/ICML/stage04_finish_089e0b7/logs/run01/03_audit.log`，SHA `db9b7ffe83d3417cfb528f3d1c4edca1521e354bc2b35342493a40c388adff33`。两份已下载项目reports/stage04_task008_layout_failure_2026-10-15/evidence/，与服务器SHA一致。

## 下一决策

当前分工不允许Codex自行创建真实环境诊断。建议请求用户明确授权一次有边界的兼容诊断：仅加载默认/该示范XML并导出compiled layout与逐字段差异，不执行任务动作、不生成标签、不跑VLA/特征/训练。**尚未获得授权、尚未执行**。先取得具体差异再决定是否需要X改代码；不发布猜测性的放宽guard要求，不让用户继续重跑同版audit。

PR #5已有R5软件裁决不被改写为新模型成功；此处真实数据/运行兼容性仍未闭环，不额外伪称代码错误已经定性。初始化和资源问题的历史修复及原始失败全保留。无新实验成绩、无覆盖/删除，007/008/Stage04未closed，精确待删=[]。本记录和STATUS提交后本地按来源commit/SHA归档。
