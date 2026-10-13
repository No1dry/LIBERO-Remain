# 004 round1：有效distribution版本记录修复

作者X，2026-10-09；submitted，待Codex独立验收。

基准main：`4a02c78c0b945c2df2f0748614fecdd1c5127f55`（已授权PR #2合并后）。004独立实现提交：`7318c4b79cf04c5945695d492c22783710fb3098`，仅包含 `benchmark/remaining_goals/policy_worker.py` 和 `tests/test_remaining_runtime_provenance.py`。

`packages`仍为普通name→version字典。名称规范化为小写且折叠 `-_.`，每项通过当前解释器的 `importlib.metadata.version(name)` first-match解析取得；distribution枚举只发现名称，不以枚举顺序或版本排序覆盖有效版本。新增 `package_metadata_resolution` 说明范围，并把重复候选放在独立诊断字段；候选排序只稳定输出，不声称是import优先级。

这个记录描述有效distribution metadata，不证明已import模块的字节身份或必然等于 `module.__version__`。不为记录引入重型包导入，不改解释器选择、worker seed/reset、动作/统计量/模型或旧raw。已枚举但解析失败的异常如实上报，不拿任一候选猜版本。

实际CPU验证：

```text
<simulation-python> -m pytest tests/test_remaining_runtime_provenance.py tests/test_remaining_policy_transport.py -q
33 passed, 2 skipped in 8.09s
```

覆盖fake overlay/parent、2.9/2.10词典排序陷阱、枚举逆序、普通环境、大小写/连字符/下划线规范化与重复诊断、实际临时dist-info目录的sys.path first-match。两项skip是已有Windows symlink权限与POSIX venv集成限制。未运行GPU或新仿真；完整交付回归见[005回应](005_round1.md)。

历史00/001原记录不回写；旧版本字段警告仍由既有有效版本快照解释。提交本修复不构成历史数据“纠正重发”。
