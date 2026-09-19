#!/usr/bin/env python3
"""Build or refresh a translation map for a Caelestia shell tree.

The translation map shipped in ``translations/`` contains two kinds of data:

* human-authored translations (``global``, ``contexts``, ``overrides``);
* derived metadata used for safe, verifiable patching (``file_hashes``,
  ``file_keys``, ``file_sequence``).

``make_map.py`` regenerates the derived half from a pristine shell tree while
keeping the authored half untouched, so supporting a new Caelestia release is:

    python3 tools/make_map.py --update translations/zh_CN.json \\
        --root /etc/xdg/quickshell/caelestia --version 2.6.0

New strings that have no translation yet are listed; add them to the map and
run the command again. Use ``--dictionary`` to start a new language instead.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent))
from apply import ApplyError, scan_tr_calls, sha256_file  # noqa: E402

SCHEMA_VERSION = 1


def iter_qml_files(root: Path) -> List[str]:
    files: List[str] = []
    for dirpath, _dirnames, filenames in os.walk(root):
        for filename in sorted(filenames):
            if filename.endswith(".qml"):
                rel = os.path.relpath(os.path.join(dirpath, filename), root)
                files.append(rel.replace(os.sep, "/"))
    return sorted(files)


def collect_derived(
    root: Path,
) -> Tuple[
    Dict[str, str],
    Dict[str, List[str]],
    Dict[str, List[List[Optional[str]]]],
    List[Tuple[str, str, Optional[str]]],
]:
    hashes: Dict[str, str] = {}
    keys: Dict[str, List[str]] = {}
    sequence: Dict[str, List[List[Optional[str]]]] = {}
    literal_sites: List[Tuple[str, str, Optional[str]]] = []
    for relpath in iter_qml_files(root):
        path = root / relpath
        src = path.read_text(encoding="utf-8")
        sites = scan_tr_calls(src)
        if not sites:
            continue
        hashes[relpath] = sha256_file(path)
        file_keys: List[str] = []
        file_seq: List[List[Optional[str]]] = []
        for site in sites:
            if site.dynamic:
                continue
            context = site.context.value if site.context else None
            file_seq.append(
                [
                    site.text.value if site.text is not None else None,
                    site.plural.value if site.plural is not None else None,
                ]
            )
            for literal in (site.text, site.plural):
                if literal is not None and literal.value:
                    if literal.value not in file_keys:
                        file_keys.append(literal.value)
                    literal_sites.append((relpath, literal.value, context))
        keys[relpath] = file_keys
        sequence[relpath] = file_seq
    return hashes, keys, sequence, literal_sites


def lookup(data: Dict[str, Any], text: str, context: Optional[str], relpath: str) -> Optional[str]:
    if context:
        table = data.get("contexts", {}).get(context)
        if table and text in table:
            return table[text]
    table = data.get("overrides", {}).get(relpath)
    if table and text in table:
        return table[text]
    return data.get("global", {}).get(text)


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Build or refresh a Caelestia translation map")
    parser.add_argument("--root", required=True, help="pristine Caelestia shell tree")
    parser.add_argument("--out", help="map file to write")
    parser.add_argument("--update", help="existing map to refresh in place")
    parser.add_argument("--dictionary", help="JSON file with global/contexts/overrides")
    parser.add_argument("--language", default=None)
    parser.add_argument("--version", default=None, help="caelestia-shell version the map targets")
    parser.add_argument("--package-version", default=None)
    parser.add_argument("--project-version", default="1.0.0")
    parser.add_argument("--allow-uncovered", action="store_true",
                        help="write the map even when some strings have no translation")
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args(argv)

    root = Path(args.root).resolve()
    if not (root / "shell.qml").is_file():
        print(f"error: {root} does not look like a Caelestia shell tree (shell.qml missing)", file=sys.stderr)
        return 1

    if args.update:
        source_path = Path(args.update)
        data = json.loads(source_path.read_text(encoding="utf-8"))
        if args.out is None:
            args.out = args.update
    elif args.dictionary:
        data = json.loads(Path(args.dictionary).read_text(encoding="utf-8"))
    else:
        print("error: provide either --update MAP or --dictionary FILE", file=sys.stderr)
        return 1

    hashes, keys, sequence, literal_sites = collect_derived(root)
    data.setdefault("global", {})
    data.setdefault("contexts", {})
    data.setdefault("overrides", {})

    if args.language:
        data["language"] = args.language
    if args.version:
        data["caelestia_shell"] = args.version
    if args.package_version:
        data["package_version"] = args.package_version

    # Report strings without a translation
    uncovered: List[str] = []
    for relpath, text, context in literal_sites:
        if lookup(data, text, context, relpath) is None:
            suffix = f" (context {context!r})" if context else ""
            line = f"{relpath}: {text!r}{suffix}"
            if line not in uncovered:
                uncovered.append(line)
    # verify contexts / overrides keys are actually used somewhere
    used_global = set()
    for relpath, file_keys in keys.items():
        for text in file_keys:
            used_global.add(text)
    unused = [text for text in data["global"] if text not in used_global]
    stale_overrides = [
        (relpath, text) for relpath, table in data["overrides"].items() for text in table if relpath not in keys
    ]

    if not args.quiet:
        print(f"  shell tree      : {root}")
        print(f"  files with Tr   : {len(hashes)}")
        print(f"  literal strings : {sum(len(v) for v in keys.values())}")
        if uncovered:
            print(f"  untranslated    : {len(uncovered)}")
            for line in uncovered[:40]:
                print(f"    ? {line}")
            if len(uncovered) > 40:
                print(f"    ... and {len(uncovered) - 40} more")
        if unused:
            print(f"  unused entries  : {len(unused)} (kept)")
        if stale_overrides:
            print(f"  overrides for files without Tr calls: {len(stale_overrides)}")

    if uncovered and not (args.allow_uncovered or args.update):
        print("error: refusing to write a map with untranslated strings (use --allow-uncovered)", file=sys.stderr)
        return 3

    data["schema"] = SCHEMA_VERSION
    data["file_hashes"] = hashes
    data["file_keys"] = keys
    data["file_sequence"] = sequence
    plural_keys = sorted(
        {slot[1] for seq in sequence.values() for slot in seq if slot[1]}
    )
    data["plural_keys"] = plural_keys

    out_path = Path(args.out).resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if not args.quiet:
        print(f"  wrote           : {out_path}")
    return 0 if not uncovered else 3


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (ApplyError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        sys.exit(1)
