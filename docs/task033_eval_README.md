# LIBERO-Remain: nine LIBERO-10 compound tasks

This export is generated from a single accepted commit of [No1dry/LIBERO-Remain](https://github.com/No1dry/LIBERO-Remain). `SOURCE_EXPORT.json` records that commit and each exported file's SHA256. Publishing an export does not claim that sources have been physically constructed or that model episodes have been executed.

The active official task IDs are **0,1,2,3,4,6,7,8,9**, with 90 normal00 and 90 mask10 episodes. The current SOG10 study reuses the historical six tasks' 120 records and executes only IDs **3,8,9**: 30+30 new episodes. Missing reuse evidence never becomes a model queue entry. Old readers are included solely for historical artifact compatibility; no LIBERO-90 configuration belongs to this export's active scope.

Start with the [complete nine-task runbook](docs/task033_nine_task_runbook.md): environment, pinned model identity, source preparation, commands, continuation, metrics, and evidence boundaries. Commands run from the repository root using Python 3.10–3.12. Model weights, simulator installation, generated source states and historical runs are not bundled.

```bash
python -m pip install -e '.[video]'
python -m benchmark.remaining_goals.headless.nine_cli --help
python -m benchmark.remaining_goals.headless.nine_cli budget-plan --protocol nine-normal00
python -m benchmark.remaining_goals.headless.nine_cli budget-plan --protocol nine-mask10
```

Only explicit user-started source preparation creates native environments, and only `nine_cli run` invokes the policy. `budget-plan`, `reuse-index`, `configure`, `dry-plan`, `inspect` and `summarize` are file-only. No selector, FINISH head, additional seed or mask01/11 belongs to this protocol.
