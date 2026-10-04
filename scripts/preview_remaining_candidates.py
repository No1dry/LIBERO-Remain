"""Create a self-contained visual review of a technically validated candidate pack."""
from __future__ import annotations

import argparse
import base64
import html
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from benchmark.remaining_goals.replay_candidates import _candidate_pack, _audit_path
from benchmark.remaining_goals.package_audit import validate_replay_evidence


DOCUMENT_MARKER = "<!-- remaining-goals-candidate-preview-v1 -->\n"


def _pack_content(manifest_path: Path, replay_path: Path | None = None):
    manifest, groups, states, observation_hashes = _candidate_pack(manifest_path)
    replay_note = "尚未提供独立回放报告"
    if replay_path:
        _, replay = validate_replay_evidence(manifest_path, manifest, replay_path, states, observation_hashes)
        replay_note = ("独立回放通过" if replay["technical_acceptance"] else "独立回放未通过")
        replay_note += (f" · {replay['records']}/{replay['expected_records']} 次加载记录"
                        f" · 每次请求 {replay['requested_steps']} 个物理步")
    sections = []
    for group in groups:
        cards = []
        for episode in group:
            audit_path = _audit_path(manifest_path.parent, episode["construction"]["technical_audit"])
            audit = json.loads(audit_path.read_text(encoding="utf-8"))
            png = audit_path.parent / "start.png"
            if not png.resolve().is_relative_to(manifest_path.parent.resolve()):
                raise ValueError("preview image is outside the candidate pack")
            encoded = base64.b64encode(png.read_bytes()).decode("ascii")
            mask = "".join("1" if bit else "0" for bit in episode["initial_mask"])
            completed = [g["language"] for bit, g in zip(episode["initial_mask"], episode["goal_specs"]) if bit]
            remaining = [g["language"] for bit, g in zip(episode["initial_mask"], episode["goal_specs"]) if not bit]
            drift = max(max(row["object_position_drift"].values()) for row in audit["trace"])
            cards.append(f'''<article><h3>{mask}</h3>
<img src="data:image/png;base64,{encoded}" alt="{html.escape(episode['episode_id'])}">
<p><b>已完成：</b>{html.escape('; '.join(completed) or '无')}</p>
<p><b>剩余：</b>{html.escape('; '.join(remaining) or '无')}</p>
<small>构造时 {audit['completed_steps']} 步技术验收通过 · 物体最大位移 {drift * 1000:.3f} mm</small></article>''')
        title = html.escape(group[0]['instruction'])
        details = (f"{html.escape(group[0]['suite'])} / {html.escape(group[0]['task_id'])} · 官方初态 {group[0]['initial_state_index']}"
                   f" · {len(group[0]['goal_specs'])} 个目标 · {len(group)} 个完成子集")
        sections.append(f"<section><h2>{title}</h2><p>{details}</p><div class='grid'>{''.join(cards)}</div></section>")
    return manifest, groups, sections, replay_note


def preview(manifest_path: Path | list[Path], output: Path,
            replay_path: Path | list[Path] | None = None, *, overwrite: bool = False):
    """Show separate suite packs together without creating a mixed evaluation manifest."""
    manifests = [manifest_path] if isinstance(manifest_path, Path) else list(manifest_path)
    replays = ([None] * len(manifests) if replay_path is None else
               [replay_path] if isinstance(replay_path, Path) else list(replay_path))
    if not manifests or len(manifests) != len(replays):
        raise ValueError("provide one replay per manifest, in the same order, or omit all replays")
    output = Path(output)
    if output.suffix.lower() not in (".html", ".htm"):
        raise ValueError("preview output must be an HTML file")
    if any(output.resolve() == path.resolve() for path in [*manifests, *replays] if path is not None):
        raise ValueError("preview output cannot overwrite an input manifest or replay report")
    output_exists = output.exists()
    if output_exists:
        if not overwrite:
            raise FileExistsError("preview already exists; use --overwrite only to replace a generated preview")
        if not output.is_file() or not output.read_text(encoding="utf-8").startswith(DOCUMENT_MARKER):
            raise ValueError("--overwrite only replaces this tool's marked preview HTML, never arbitrary files")
    packs = [_pack_content(path, replay) for path, replay in zip(manifests, replays)]
    native_tasks = [{(e['suite'], e['task_id']) for e in pack[0]['episodes']} for pack in packs]
    if sum(map(len, native_tasks)) != len(set().union(*native_tasks)):
        raise ValueError("preview packs must not duplicate tasks")
    document = DOCUMENT_MARKER + '''<!doctype html><html lang="zh-CN"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>LIBERO Remaining Goals · 真实场景预览</title>
<style>body{font:16px/1.55 system-ui,sans-serif;margin:0;background:#f4f6f8;color:#19222d}
main{max-width:1200px;margin:auto;padding:32px}h1{font-size:28px}h2{font-size:19px}
section{margin:32px 0}.grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:16px}
article{padding:14px;background:white;border:1px solid #dbe1e7;border-radius:10px}
h3{margin:0 0 10px;font:700 22px monospace}img{width:100%;height:auto;border-radius:6px}
p{font-size:14px;overflow-wrap:anywhere}small{color:#54616e;font-size:12px}
.note{padding:16px;background:#e8eef5;border-radius:8px}@media(max-width:850px){.grid{grid-template-columns:repeat(2,minmax(0,1fr))}}
</style><main><h1>LIBERO Remaining Goals · 真实场景预览</h1>
<p>同一来源的全部完成子集共享机器人起始姿态；同一已完成目标在不同子集中使用相同状态组件。双目标展示四格，三目标展示八格。</p>
'''
    document += (f"<p>{sum(map(len, native_tasks))} 个任务 · "
                 f"{sum(len(p[1]) for p in packs)} 个来源组 · "
                 f"{sum(len(p[0]['episodes']) for p in packs)} 个真实候选状态</p>")
    document += "<p class='note'>本页展示真实仿真候选状态，尚未认证剩余任务的执行可行性，也未运行 VLA 策略。不同 LIBERO suite 分别评测，使用匹配的模型权重与归一化配置，不直接混合得分。</p>"
    for manifest, groups, sections, replay_note in packs:
        suites = ', '.join(sorted({e['suite'] for e in manifest['episodes']}))
        document += f"<h2>{html.escape(suites)}</h2><p class='note'>{html.escape(replay_note)}</p>"
        document += "".join(sections) + f"<small>Manifest hash: {manifest['content_hash']}</small>"
    document += "</main></html>"
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w" if output_exists else "x", encoding="utf-8") as file:
        file.write(document)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, action="append", required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--replay", type=Path, action="append", help="one per manifest, in matching order")
    parser.add_argument("--overwrite", action="store_true", help="replace only a marked HTML preview from this tool")
    args = parser.parse_args()
    preview(args.manifest, args.out, args.replay, overwrite=args.overwrite)
