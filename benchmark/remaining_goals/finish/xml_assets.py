"""Bounded, file-only relocation of the fixed demonstration XML dependencies.

Only approved asset ``file`` values are changed. No package initialization,
simulator, XML camera postprocessing, basename search or source-file writes occur.
The target hash binds the installed file; it does not prove historical author's
asset bytes were identical to the installed runtime's corresponding suffix.
"""
from __future__ import annotations

from copy import deepcopy
import hashlib
from html import escape
from importlib.machinery import PathFinder
import json
from pathlib import Path
import re
import sys
from xml.parsers import expat

RESOLVER_VERSION = "libero-bounded-xml-assets-v1"
SCAN_SCHEMA = "remaining-finish-xml-assets-scan-v1"
LEGACY_ROOT = "/home/yifengz/workspace/libero-dev/chiliocosm/assets/"
_ROOTS = {"libero", "robosuite"}
_MARKERS = {"libero": ("libero", "assets"), "robosuite": ("robosuite", "models", "assets")}
_ATTR = re.compile(rb'([A-Za-z_][A-Za-z0-9_:.-]*)\s*=\s*([\"\x27])(.*?)\2', re.DOTALL)


def _hash(value):
    return hashlib.sha256(value).hexdigest()


def _canonical(value):
    return _hash(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8"))


def _file_hash(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _package_locations(parts):
    search = list(sys.path)
    full = []
    for part in parts:
        full.append(part)
        spec = PathFinder.find_spec(".".join(full), search)
        locations = None if spec is None else spec.submodule_search_locations
        if not locations:
            raise ValueError(f"installed package path unavailable without imports: {'.'.join(full)}")
        search = list(dict.fromkeys(str(Path(item).resolve()) for item in locations))
        if len(search) != 1:
            raise ValueError(f"ambiguous installed package roots: {'.'.join(full)}")
    return Path(search[0])


def discover_asset_roots(names=None):
    """Resolve installed package directories without executing their __init__."""
    names = sorted(_ROOTS if names is None else set(names))
    if any(name not in _ROOTS for name in names):
        raise ValueError("unknown asset root namespace")
    result = {}
    for name in names:
        base = _package_locations(("libero", "libero") if name == "libero" else ("robosuite",))
        root = base / ("assets" if name == "libero" else "models/assets")
        root = root.resolve(strict=True)
        if not root.is_dir():
            raise ValueError(f"installed asset root is not a directory: {name}")
        result[name] = root.as_posix()
    return result


def _parse(text):
    if not isinstance(text, str) or not text.strip():
        raise ValueError("demonstration model_xml must contain actual XML text")
    raw = text.encode("utf-8")
    parser = expat.ParserCreate()
    records, errors, stack = [], [], []
    def start(tag, attributes):
        if not stack and tag != "mujoco":
            raise ValueError("unsupported XML root; expected mujoco")
        offset = parser.CurrentByteIndex
        end, quote = offset, None
        while end < len(raw):
            item = raw[end]
            if quote is not None:
                if item == quote:
                    quote = None
            elif item in (34, 39):
                quote = item
            elif item == 62:
                break
            end += 1
        spans = {match.group(1).decode("ascii"): (offset + match.start(3), offset + match.end(3))
                 for match in _ATTR.finditer(raw[offset:end+1])}
        fields = [key for key in attributes if key == "file" or key.startswith("file") or key.endswith("file")]
        if tag in {"include", "plugin", "extension"} and not fields:
            errors.append({"tag": tag, "attribute": None, "original": None,
                           "error": "unsupported external XML dependency"})
        if tag == "compiler" and attributes.get("strippath", "false").lower() not in {"false", "0"}:
            errors.append({"tag": tag, "attribute": "strippath", "original": attributes["strippath"],
                           "error": "strippath would discard the approved complete asset suffix"})
        for field in fields:
            allowed = field == "file" and tag in {"mesh", "texture", "hfield"} and stack == ["mujoco", "asset"]
            records.append({"tag": tag, "attribute": field, "original": attributes[field],
                            "allowed": allowed, "span": spans.get(field)})
        stack.append(tag)
    def reject_doctype(*args):
        raise ValueError("XML DTD/external entity dependencies are unsupported")
    parser.StartElementHandler = start
    parser.EndElementHandler = lambda tag: stack.pop()
    parser.StartDoctypeDeclHandler = reject_doctype
    parser.ExternalEntityRefHandler = lambda *args: 0
    parser.Parse(raw, True)
    return raw, records, errors


def _interpret(original):
    if not isinstance(original, str) or not original or "\x00" in original or "://" in original:
        raise ValueError("invalid or unsupported asset path")
    value = original.replace("\\", "/")
    parts = value.split("/")
    candidates = []
    if value.startswith(LEGACY_ROOT):
        candidates.append(("libero", value[len(LEGACY_ROOT):], "legacy_chiliocosm_exact_root"))
    for root, marker in _MARKERS.items():
        for index in range(len(parts) - len(marker) + 1):
            if tuple(parts[index:index+len(marker)]) == marker:
                candidates.append((root, "/".join(parts[index+len(marker):]), f"official_{root}_assets_segment"))
    if len(candidates) != 1:
        raise ValueError("ambiguous asset root interpretations" if candidates else "unknown asset root; no fallback to original path")
    root, suffix, rule = candidates[0]
    normalized = []
    for part in suffix.split("/"):
        if part in {"", "."}:
            continue
        if part == "..":
            if not normalized:
                raise ValueError("asset suffix escapes its approved root")
            normalized.pop()
        elif ":" in part:
            raise ValueError("absolute/drive-qualified component inside asset suffix")
        else:
            normalized.append(part)
    if not normalized:
        raise ValueError("asset suffix names no file")
    return root, normalized, rule


def _roots_for(texts, roots):
    if roots is not None:
        if not isinstance(roots, dict) or set(roots) - _ROOTS:
            raise ValueError("approved roots must map only libero/robosuite to assets directories")
        result = {}
        for key, value in roots.items():
            path = Path(value).resolve(strict=True)
            if not path.is_dir():
                raise ValueError("approved asset root must be an existing directory")
            result[key] = path.as_posix()
        return result, {}
    needed = set()
    for text in texts:
        try:
            _, records, _ = _parse(text)
            for record in records:
                try:
                    needed.add(_interpret(record["original"])[0])
                except ValueError:
                    pass  # Resolve records below to retain every specific error.
        except (ValueError, expat.ExpatError):
            pass
    result, errors = {}, {}
    for name in sorted(needed):
        try:
            result.update(discover_asset_roots([name]))
        except (ValueError, OSError, ImportError) as error:
            errors[name] = f"{type(error).__name__}: {error}"
    return result, errors


def _resolve(text, roots, root_errors, file_hashes=None):
    report = {"resolver_version": RESOLVER_VERSION, "original_xml": text,
              "original_xml_sha256": _hash(text.encode("utf-8")) if isinstance(text, str) else None,
              "processed_xml_sha256": None, "approved_roots": deepcopy(roots), "mappings": [],
              "errors": [], "file_reference_occurrences": 0, "status": "unresolved"}
    try:
        raw, records, errors = _parse(text)
    except (ValueError, expat.ExpatError) as error:
        report["errors"].append({"tag": None, "attribute": None, "original": None, "error": str(error)})
        return None, report
    report["errors"].extend(errors)
    report["file_reference_occurrences"] = len(records)
    edits = []
    for record in records:
        entry = {key: record[key] for key in ("tag", "attribute", "original")}
        try:
            if not record["allowed"] or record["span"] is None:
                raise ValueError("unsupported XML file dependency; only direct asset mesh/texture/hfield file is approved")
            namespace, suffix, rule = _interpret(record["original"])
            if namespace not in roots:
                raise ValueError(root_errors.get(namespace, f"approved asset root unavailable: {namespace}"))
            root = Path(roots[namespace])
            target = root.joinpath(*suffix).resolve()
            if target == root or not target.is_relative_to(root):
                raise ValueError("asset symlink/normalized path escapes its approved root")
            if not target.is_file():
                raise ValueError(f"approved asset file is missing: {target.as_posix()}")
            target_key = target.as_posix()
            target_hash = None if file_hashes is None else file_hashes.get(target_key)
            if target_hash is None:
                target_hash = _file_hash(target)
                if file_hashes is not None:
                    file_hashes[target_key] = target_hash
            entry.update(root=namespace, relative_suffix="/".join(suffix), rule=rule,
                         resolved=target_key, target_sha256=target_hash)
            report["mappings"].append(entry)
            edits.append((*record["span"], escape(target.as_posix(), quote=True).encode("utf-8")))
        except (ValueError, OSError, RuntimeError) as error:
            report["errors"].append({**entry, "error": f"{type(error).__name__}: {error}"})
    if report["errors"]:
        return None, report
    for start, end, replacement in reversed(edits):
        raw = raw[:start] + replacement + raw[end:]
    processed = raw.decode("utf-8")
    report.update(status="resolved", processed_xml_sha256=_hash(raw))
    return processed, report


def resolve_xml(text, roots=None):
    """Return rewritten XML and evidence, or None plus all unresolved errors."""
    approved, errors = _roots_for([text], roots)
    return _resolve(text, approved, errors)


def scan_xml_assets(trajectories, roots=None):
    """Aggregate every actual source XML; file scanning never creates labels."""
    if not isinstance(trajectories, list) or not trajectories:
        raise ValueError("XML scan requires a nonempty list of actual trajectories")
    ids = [item.get("trajectory_id") if isinstance(item, dict) else None for item in trajectories]
    if any(not isinstance(key, str) or not key for key in ids) or len(set(ids)) != len(ids):
        raise ValueError("XML scan trajectory identifiers must be nonempty and unique")
    approved, root_errors = _roots_for([item.get("model_xml") for item in trajectories], roots)
    sources, errors, originals, file_hashes = [], [], set(), {}
    for item in trajectories:
        _, report = _resolve(item.get("model_xml"), approved, root_errors, file_hashes)
        report["trajectory_id"] = item["trajectory_id"]
        sources.append(report)
        errors.extend({"trajectory_id": item["trajectory_id"], **error} for error in report["errors"])
        for entry in [*report["mappings"], *report["errors"]]:
            attribute = entry.get("attribute")
            if (isinstance(attribute, str) and (attribute.startswith("file") or attribute.endswith("file"))
                    and isinstance(entry.get("original"), str)):
                originals.add(entry["original"])
    result = {"schema_version": SCAN_SCHEMA, "resolver_version": RESOLVER_VERSION,
              "approved_roots": approved, "sources": sources, "trajectory_count": len(sources),
              "file_reference_occurrences": sum(row["file_reference_occurrences"] for row in sources),
              "resolved_reference_occurrences": sum(len(row["mappings"]) for row in sources),
              "unique_file_references": len(originals), "errors": errors,
              "status": "unresolved" if errors else "resolved", "simulation_created": False,
              "ready_for_feature_export": False,
              "limitation": "Installed corresponding-suffix file bytes are bound; equality to inaccessible historical author files is unproven."}
    result["scan_sha256"] = _canonical(result)
    return result


def validate_scan(snapshot, trajectories=None, *, verify_files=True):
    """Verify an immutable successful scan, optionally against actual HDF XML."""
    if (not isinstance(snapshot, dict) or snapshot.get("schema_version") != SCAN_SCHEMA
            or snapshot.get("resolver_version") != RESOLVER_VERSION
            or snapshot.get("scan_sha256") != _canonical({k: v for k, v in snapshot.items() if k != "scan_sha256"})
            or snapshot.get("status") != "resolved" or snapshot.get("errors")):
        raise ValueError("XML asset scan is unresolved, changed, or uses another resolver")
    stored = [{"trajectory_id": item["trajectory_id"], "model_xml": item["original_xml"]} for item in snapshot["sources"]]
    if trajectories is not None:
        actual = [{"trajectory_id": item["trajectory_id"], "model_xml": item["model_xml"]} for item in trajectories]
        if actual != stored:
            raise ValueError("actual trajectory XML sources differ from the frozen asset scan")
    if verify_files:
        current = scan_xml_assets(stored, roots=snapshot["approved_roots"])
        if current != snapshot:
            raise ValueError("XML asset resolution or target bytes changed after scan")
    else:
        if (snapshot.get("trajectory_count") != len(stored) or len({row["trajectory_id"] for row in stored}) != len(stored)
                or snapshot.get("simulation_created") is not False or snapshot.get("ready_for_feature_export") is not False):
            raise ValueError("XML scan coverage/readiness metadata differs")
        for row in snapshot["sources"]:
            if (row.get("status") != "resolved" or row.get("errors") or row.get("approved_roots") != snapshot["approved_roots"]
                    or _hash(row["original_xml"].encode("utf-8")) != row.get("original_xml_sha256")):
                raise ValueError("XML source identity differs from its scan")
    return deepcopy(snapshot)


def resolve_scanned_xml(text, snapshot, *, roots=None):
    """Check actual file bytes when compiling a source XML into a native model."""
    validate_scan(snapshot, verify_files=False)
    matching = [row for row in snapshot["sources"] if row["original_xml"] == text]
    if not matching:
        raise ValueError("runtime XML is absent from the frozen pre-provider asset scan")
    processed, current = resolve_xml(text, roots=snapshot["approved_roots"] if roots is None else roots)
    for row in matching:
        if current != {key: value for key, value in row.items() if key != "trajectory_id"}:
            raise ValueError("runtime XML asset target/hash differs from the frozen scan")
    if processed is None:
        raise ValueError("runtime XML asset resolution failed")
    return processed, current
