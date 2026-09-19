#!/usr/bin/env python3
"""Backup, state and restore management for the Caelestia Chinese localisation.

The data directory (default ``~/.local/share/caelestia-zh``) contains:

``state.json``
    What the installer changed: shell directory, versions, per-file original
    and installed hashes plus the backup path.
``backup/<timestamp>/...``
    Byte-exact copies of the files as they were before the localisation.

The ``plan``/``commit``/``restore``/``status`` commands are driven by the JSON
reports produced by ``apply.py`` so no shell code has to parse JSON.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

SCHEMA_VERSION = 1


class StateError(Exception):
    pass


def now_stamp() -> str:
    return time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())


def sha256_file(path: Path) -> str:
    import hashlib

    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def load_json(path: Path, default: Any = None) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return default
    except json.JSONDecodeError as exc:
        raise StateError(f"{path} is not valid JSON: {exc}") from exc


def atomic_write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def state_path(data_dir: Path) -> Path:
    return data_dir / "state.json"


def load_state(data_dir: Path) -> Dict[str, Any]:
    data = load_json(state_path(data_dir), default=None)
    if data is None:
        return {"schema": SCHEMA_VERSION, "files": {}}
    if data.get("schema") != SCHEMA_VERSION:
        raise StateError(f"unsupported state schema {data.get('schema')!r}")
    data.setdefault("files", {})
    return data


def report_files(report: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    return {entry["path"]: entry for entry in report.get("files", [])}


def safe_rel(root: Path, relpath: str) -> Path:
    candidate = (root / relpath).resolve()
    if not str(candidate).startswith(str(root) + os.sep):
        raise StateError(f"refusing to touch path outside the tree: {relpath}")
    return candidate


# ---------------------------------------------------------------------------
# plan
# ---------------------------------------------------------------------------


def cmd_plan(args: argparse.Namespace) -> int:
    data_dir = Path(args.data_dir).resolve()
    shell_dir = Path(args.shell_dir).resolve()
    state = load_state(data_dir)
    old_files: Dict[str, Dict[str, Any]] = dict(state.get("files", {}))
    analysis = load_json(Path(args.analysis), default=None)
    if analysis is None:
        raise StateError("analysis report is missing; run apply.py analyze first")

    to_change = [e for e in analysis["files"] if e.get("changed")]
    stamp = now_stamp()
    backup_rel = f"backup/{stamp}"
    backup_dir = data_dir / backup_rel
    entries: Dict[str, Dict[str, Any]] = {}
    created = 0
    reused = 0

    for entry in to_change:
        relpath = entry["path"]
        src = safe_rel(shell_dir, relpath)
        if not src.is_file():
            continue
        current_sha = entry["sha256"]
        old = old_files.get(relpath)
        if old and old.get("backup"):
            backup_file = data_dir / old["backup"]
            if backup_file.is_file() and old.get("original_sha256") in (current_sha, old.get("installed_sha256"), None):
                entries[relpath] = {
                    "original_sha256": old["original_sha256"],
                    "backup": old["backup"],
                    "reused": True,
                }
                reused += 1
                continue
        target = backup_dir / relpath
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, target)
        if sha256_file(target) != current_sha:
            raise StateError(f"backup verification failed for {relpath}")
        entries[relpath] = {"original_sha256": current_sha, "backup": str(target.relative_to(data_dir)), "reused": False}
        created += 1

    plan = {"backup_dir": backup_rel, "shell_dir": str(shell_dir), "entries": entries, "created": created, "reused": reused}
    atomic_write_json(data_dir / "plan.json", plan)
    if not args.quiet:
        print(f"  backups: {created} new, {reused} reused -> {backup_dir if created else 'existing snapshots'}")
    return 0


# ---------------------------------------------------------------------------
# commit
# ---------------------------------------------------------------------------


def cmd_commit(args: argparse.Namespace) -> int:
    data_dir = Path(args.data_dir).resolve()
    shell_dir = Path(args.shell_dir).resolve()
    state = load_state(data_dir)
    old_files: Dict[str, Dict[str, Any]] = dict(state.get("files", {}))
    plan = load_json(data_dir / "plan.json", default=None)
    if plan is None:
        raise StateError("no plan found; run plan before commit")
    applied = load_json(Path(args.applied), default=None)
    if applied is None:
        raise StateError("applied report is missing")

    after = report_files(applied)
    new_files: Dict[str, Dict[str, Any]] = {}

    # Keep previous entries that are still installed and untouched.
    for relpath, entry in old_files.items():
        src = safe_rel(shell_dir, relpath)
        if not src.is_file():
            continue
        current = sha256_file(src)
        if current == entry.get("installed_sha256"):
            new_files[relpath] = entry

    for relpath, plan_entry in plan["entries"].items():
        src = safe_rel(shell_dir, relpath)
        if not src.is_file():
            continue
        current = sha256_file(src)
        applied_entry = after.get(relpath, {})
        installed_sha = applied_entry.get("result_sha256") or current
        if installed_sha == plan_entry["original_sha256"]:
            # nothing actually changed; no need to track it
            continue
        new_files[relpath] = {
            "original_sha256": plan_entry["original_sha256"],
            "installed_sha256": installed_sha,
            "backup": plan_entry["backup"],
        }

    state = {
        "schema": SCHEMA_VERSION,
        "project_version": args.project_version,
        "language": args.language,
        "shell_dir": str(shell_dir),
        "caelestia_shell": args.caelestia_shell,
        "installed_version": args.installed_version,
        "installed_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "files": dict(sorted(new_files.items())),
    }
    atomic_write_json(state_path(data_dir), state)
    try:
        (data_dir / "plan.json").unlink()
    except FileNotFoundError:
        pass
    if not args.quiet:
        print(f"  state: {len(new_files)} file(s) tracked")
    return 0


# ---------------------------------------------------------------------------
# restore
# ---------------------------------------------------------------------------


def cmd_restore(args: argparse.Namespace) -> int:
    data_dir = Path(args.data_dir).resolve()
    shell_dir = Path(args.shell_dir).resolve()
    state = load_state(data_dir)
    files: Dict[str, Dict[str, Any]] = state.get("files", {})
    if not files:
        summary = {
            "restored": [],
            "already_original": [],
            "modified_skipped": [],
            "missing_backup": [],
            "failed": [],
            "state_removed": False,
        }
        if args.json:
            Path(args.json).write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        if not args.quiet:
            print("  nothing to restore (no installed state)")
        return 0

    restored: List[str] = []
    already: List[str] = []
    modified: List[str] = []
    missing_backup: List[str] = []
    failed: List[str] = []

    for relpath, entry in sorted(files.items()):
        src = safe_rel(shell_dir, relpath)
        backup = data_dir / entry.get("backup", "")
        if not src.is_file():
            if entry.get("backup") and backup.is_file():
                if not args.dry_run:
                    try:
                        src.parent.mkdir(parents=True, exist_ok=True)
                        shutil.copy2(backup, src)
                    except OSError:
                        failed.append(relpath)
                        continue
                restored.append(relpath)
            else:
                missing_backup.append(relpath)
            continue
        current = sha256_file(src)
        if current == entry.get("original_sha256"):
            already.append(relpath)
            continue
        if current != entry.get("installed_sha256") and not args.force:
            modified.append(relpath)
            continue
        if not entry.get("backup") or not backup.is_file():
            missing_backup.append(relpath)
            continue
        if args.dry_run:
            restored.append(relpath)
            continue
        try:
            tmp = src.with_name(src.name + ".caelestia-zh-restore")
            shutil.copy2(backup, tmp)
            os.replace(tmp, src)
            restored.append(relpath)
        except OSError:
            failed.append(relpath)

    summary = {
        "restored": restored,
        "already_original": already,
        "modified_skipped": modified,
        "missing_backup": missing_backup,
        "failed": failed,
        "state_removed": False,
    }

    if not args.dry_run and not modified and not missing_backup and not failed:
        try:
            state_path(data_dir).unlink()
            summary["state_removed"] = True
        except FileNotFoundError:
            pass
    elif not args.dry_run and modified:
        # Keep the state but remember which entries were skipped and why.
        for relpath in modified:
            files[relpath]["skipped_modified"] = True
        state["files"] = files
        atomic_write_json(state_path(data_dir), state)

    if args.json:
        Path(args.json).write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if not args.quiet:
        print(f"  restored        : {len(restored)}")
        print(f"  already original: {len(already)}")
        if modified:
            print(f"  modified, kept  : {len(modified)}")
        if missing_backup:
            print(f"  backup missing  : {len(missing_backup)}")
        if failed:
            print(f"  failed          : {len(failed)}")
    return 1 if failed else (3 if (modified or missing_backup) else 0)


# ---------------------------------------------------------------------------
# status
# ---------------------------------------------------------------------------


def cmd_status(args: argparse.Namespace) -> int:
    data_dir = Path(args.data_dir).resolve()
    shell_dir = Path(args.shell_dir).resolve()
    state = load_state(data_dir)
    files: Dict[str, Dict[str, Any]] = state.get("files", {})
    analysis = load_json(Path(args.analysis), default=None) if args.analysis else None
    analysis_files = report_files(analysis) if analysis else {}

    installed = 0
    modified: List[str] = []
    reverted: List[str] = []
    missing: List[str] = []
    untracked: List[str] = []
    for relpath, entry in sorted(files.items()):
        src = safe_rel(shell_dir, relpath)
        if not src.is_file():
            missing.append(relpath)
            continue
        current = sha256_file(src)
        if current == entry.get("installed_sha256"):
            installed += 1
        elif current == entry.get("original_sha256"):
            reverted.append(relpath)
        else:
            modified.append(relpath)

    if analysis:
        for relpath, entry in analysis_files.items():
            if entry.get("changed") and relpath not in files:
                untracked.append(relpath)

    payload = {
        "shell_dir": str(shell_dir),
        "state_dir": str(data_dir),
        "tracked": len(files),
        "installed": installed,
        "reverted": reverted,
        "modified": modified,
        "missing": missing,
        "untracked": untracked,
    }
    if args.json:
        Path(args.json).write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    if not args.quiet:
        if not files:
            print("  localisation state: not installed")
        else:
            print(f"  tracked files     : {len(files)}")
            print(f"  installed         : {installed}")
            print(f"  manually reverted : {len(reverted)}")
            print(f"  modified by user  : {len(modified)}")
            print(f"  missing           : {len(missing)}")
            if modified:
                for relpath in modified[:10]:
                    print(f"    ~ {relpath}")
                if len(modified) > 10:
                    print(f"    ... and {len(modified) - 10} more")
    return 0 if not (modified or missing) else 3


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Caelestia Chinese localisation state manager")
    parser.add_argument("--version", action="version", version="caelestia-zh state.py 1.0.0")
    sub = parser.add_subparsers(dest="command", required=True)

    plan = sub.add_parser("plan", help="snapshot files that are about to change")
    plan.add_argument("--data-dir", required=True)
    plan.add_argument("--shell-dir", required=True)
    plan.add_argument("--analysis", required=True)
    plan.add_argument("--quiet", action="store_true")
    plan.set_defaults(func=cmd_plan)

    commit = sub.add_parser("commit", help="write state.json after a successful apply")
    commit.add_argument("--data-dir", required=True)
    commit.add_argument("--shell-dir", required=True)
    commit.add_argument("--applied", required=True)
    commit.add_argument("--project-version", default="1.0.0")
    commit.add_argument("--language", default="zh_CN")
    commit.add_argument("--caelestia-shell", default="unknown")
    commit.add_argument("--installed-version", default="unknown")
    commit.add_argument("--quiet", action="store_true")
    commit.set_defaults(func=cmd_commit)

    restore = sub.add_parser("restore", help="restore original files from backups")
    restore.add_argument("--data-dir", required=True)
    restore.add_argument("--shell-dir", required=True)
    restore.add_argument("--force", action="store_true")
    restore.add_argument("--dry-run", action="store_true")
    restore.add_argument("--json")
    restore.add_argument("--quiet", action="store_true")
    restore.set_defaults(func=cmd_restore)

    status = sub.add_parser("status", help="report the installed state")
    status.add_argument("--data-dir", required=True)
    status.add_argument("--shell-dir", required=True)
    status.add_argument("--analysis")
    status.add_argument("--json")
    status.add_argument("--quiet", action="store_true")
    status.set_defaults(func=cmd_status)
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.func(args))
    except StateError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    except OSError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
