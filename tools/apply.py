#!/usr/bin/env python3
"""Precise QML string-literal replacer for the Caelestia Chinese localisation.

This tool only ever rewrites the literal arguments of ``Tr.*`` helper calls
(``Tr.tr``, ``Tr.trCtx``, ``Tr.trN``, ``Tr.trCtxN`` and the ``mark*`` family).
It never touches code, comments, icon names, config keys or dynamic values.

Commands
--------
analyze   classify every file referenced by the translation map
apply     rewrite matching literals (honours --dry-run)
revert    undo known translations when no backup is available

The tool is intentionally dependency-free (Python 3.8+ standard library) so it
can run on a minimal Arch install where ``caelestia-cli`` already pulls in
Python.
"""

from __future__ import annotations

import argparse
import difflib
import hashlib
import json
import os
import re
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple

SCHEMA_VERSION = 1
HELPER_ARITY = {
    "tr": 1,
    "trCtx": 2,
    "trN": 3,
    "trCtxN": 4,
    "trMarked": 1,
    "mark": 2,
    "markCtx": 3,
    "markN": 4,
    "markCtxN": 5,
}
# (text, plural, context) slots for each helper; None means "not present"
HELPER_SLOTS = {
    "tr": (0, None, None),
    "trCtx": (0, None, 1),
    "trN": (0, 1, None),
    "trCtxN": (0, 1, 3),
    "trMarked": (0, None, None),
    "mark": (0, None, None),
    "markCtx": (0, None, 1),
    "markN": (0, 1, None),
    "markCtxN": (0, 1, 3),
}

TR_IDENT_RE = re.compile(r"(?<![\w$])Tr\s*\.\s*([A-Za-z_][A-Za-z0-9_]*)")


# --------------------------------------------------------------------------
# Errors / helpers
# --------------------------------------------------------------------------


class ApplyError(Exception):
    """Raised for fatal, user-facing problems."""


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def decode_literal(raw: str) -> str:
    """Decode the body of a QML/JS string literal into its runtime value."""
    out: List[str] = []
    i = 0
    n = len(raw)
    simple = {"n": "\n", "t": "\t", "r": "\r", "b": "\b", "f": "\f", "v": "\v", "0": "\0"}
    while i < n:
        ch = raw[i]
        if ch != "\\":
            out.append(ch)
            i += 1
            continue
        if i + 1 >= n:
            out.append("\\")
            break
        nxt = raw[i + 1]
        if nxt == "u" and i + 5 < n:
            try:
                out.append(chr(int(raw[i + 2 : i + 6], 16)))
                i += 6
                continue
            except ValueError:
                pass
        if nxt == "x" and i + 3 < n:
            try:
                out.append(chr(int(raw[i + 2 : i + 4], 16)))
                i += 4
                continue
            except ValueError:
                pass
        if nxt == "\n":
            i += 2
            continue
        out.append(simple.get(nxt, nxt))
        i += 2
    return "".join(out)


def encode_literal(value: str, quote: str) -> str:
    """Encode a runtime string for the given quote style, without the quotes."""
    out: List[str] = []
    for ch in value:
        if ch == "\\":
            out.append("\\\\")
        elif ch == quote:
            out.append("\\" + quote)
        elif ch == "\n":
            out.append("\\n")
        elif ch == "\r":
            out.append("\\r")
        elif ch == "\t":
            out.append("\\t")
        elif quote == "`" and ch == "$":
            # only ${ starts an interpolation; escaping a lone $ is harmless
            out.append("\\$")
        else:
            out.append(ch)
    return "".join(out)


# --------------------------------------------------------------------------
# QML scanner
# --------------------------------------------------------------------------


@dataclass
class Literal:
    start: int  # offset of the opening quote
    end: int  # offset just past the closing quote
    quote: str
    value: str


@dataclass
class CallSite:
    helper: str
    start: int
    end: int
    text: Optional[Literal]
    plural: Optional[Literal]
    context: Optional[Literal]
    dynamic: bool = False


def _skip_string(src: str, i: int) -> int:
    """Return the index just past the string literal starting at ``i``."""
    quote = src[i]
    i += 1
    n = len(src)
    while i < n:
        ch = src[i]
        if ch == "\\":
            i += 2
            continue
        if quote == "`" and ch == "$" and i + 1 < n and src[i + 1] == "{":
            i = _skip_braced(src, i + 1)
            continue
        if ch == quote:
            return i + 1
        i += 1
    return n


def _skip_braced(src: str, i: int) -> int:
    """Skip a ``{ ... }`` block starting at ``i`` (brace at ``i``), string-aware."""
    depth = 0
    n = len(src)
    while i < n:
        ch = src[i]
        if ch == "{":
            depth += 1
            i += 1
        elif ch == "}":
            depth -= 1
            i += 1
            if depth == 0:
                return i
        elif ch in "\"'`":
            i = _skip_string(src, i)
        elif ch == "/" and i + 1 < n and src[i + 1] == "/":
            i = src.find("\n", i)
            if i < 0:
                return n
        elif ch == "/" and i + 1 < n and src[i + 1] == "*":
            end = src.find("*/", i + 2)
            i = n if end < 0 else end + 2
        else:
            i += 1
    return n


def _skip_trivia(src: str, i: int) -> int:
    """Skip whitespace and comments."""
    n = len(src)
    while i < n:
        ch = src[i]
        if ch.isspace():
            i += 1
        elif ch == "/" and i + 1 < n and src[i + 1] == "/":
            nl = src.find("\n", i)
            i = n if nl < 0 else nl + 1
        elif ch == "/" and i + 1 < n and src[i + 1] == "*":
            end = src.find("*/", i + 2)
            i = n if end < 0 else end + 2
        else:
            break
    return i


def _split_args(src: str, open_paren: int) -> Tuple[List[Tuple[int, int]], int]:
    """Split a call's argument list into (start, end) ranges.

    Returns the ranges and the index just past the closing paren.
    """
    args: List[Tuple[int, int]] = []
    depth = 1
    i = open_paren + 1
    arg_start = i
    n = len(src)
    while i < n:
        ch = src[i]
        if ch in "\"'`":
            i = _skip_string(src, i)
            continue
        if ch == "/" and i + 1 < n and src[i + 1] == "/":
            nl = src.find("\n", i)
            i = n if nl < 0 else nl + 1
            continue
        if ch == "/" and i + 1 < n and src[i + 1] == "*":
            end = src.find("*/", i + 2)
            i = n if end < 0 else end + 2
            continue
        if ch in "([{":
            depth += 1
        elif ch in ")]}":
            depth -= 1
            if depth == 0:
                args.append((arg_start, i))
                return args, i + 1
        elif ch == "," and depth == 1:
            args.append((arg_start, i))
            arg_start = i + 1
        i += 1
    # unterminated call: treat the rest as the last argument
    args.append((arg_start, n))
    return args, n


def _parse_literal(src: str, start: int, end: int) -> Optional[Literal]:
    """Parse an argument range as a single string literal, if possible."""
    i = _skip_trivia(src, start)
    # end points at the comma/closing paren; shrink to the last non-space char
    k = end
    while k > i and src[k - 1].isspace():
        k -= 1
    if k <= i:
        return None
    if src[i] not in "\"'`":
        return None
    if src[i] == "`" and "${" in src[i:k]:
        return None
    lit = _skip_string(src, i)
    if _skip_trivia(src, lit) < k:
        return None  # concatenation or an expression
    if k < lit:
        return None
    return Literal(start=i, end=lit, quote=src[i], value=decode_literal(src[i + 1 : lit - 1]))


def build_mask(src: str) -> bytearray:
    """Mark every byte that sits inside a comment or a string literal.

    ``Tr.`` occurrences inside such regions are not real calls (e.g. commented
    out code) and must never be rewritten. Template interpolations are treated
    as part of the template for simplicity; the shell does not nest calls there.
    """
    n = len(src)
    mask = bytearray(n)
    i = 0
    while i < n:
        ch = src[i]
        if ch in "\"'`":
            end = _skip_string(src, i)
            for j in range(i, min(end, n)):
                mask[j] = 1
            i = end
        elif ch == "/" and i + 1 < n and src[i + 1] == "/":
            nl = src.find("\n", i)
            end = n if nl < 0 else nl
            for j in range(i, end):
                mask[j] = 1
            i = end
        elif ch == "/" and i + 1 < n and src[i + 1] == "*":
            close = src.find("*/", i + 2)
            end = n if close < 0 else close + 2
            for j in range(i, end):
                mask[j] = 1
            i = end
        else:
            i += 1
    return mask


def scan_tr_calls(src: str) -> List[CallSite]:
    """Find every ``Tr.<helper>(...)`` call site and parse its literal args."""
    sites: List[CallSite] = []
    mask = build_mask(src)
    for match in TR_IDENT_RE.finditer(src):
        if mask[match.start()]:
            continue  # commented out or inside a string
        helper = match.group(1)
        if helper not in HELPER_ARITY:
            continue
        i = _skip_trivia(src, match.end())
        if i >= len(src) or src[i] != "(":
            continue
        arg_ranges, end = _split_args(src, i)
        text_slot, plural_slot, ctx_slot = HELPER_SLOTS[helper]

        def slot(index: Optional[int]) -> Optional[Literal]:
            if index is None or index >= len(arg_ranges):
                return None
            return _parse_literal(src, *arg_ranges[index])

        text = slot(text_slot)
        plural = slot(plural_slot)
        context = slot(ctx_slot)
        site = CallSite(helper=helper, start=match.start(), end=end, text=text, plural=plural, context=context)
        site.dynamic = text is None
        sites.append(site)
    return sites


# --------------------------------------------------------------------------
# Translation map
# --------------------------------------------------------------------------


@dataclass
class TranslationMap:
    path: Path
    language: str
    shell_version: str
    package_version: str
    global_map: Dict[str, str]
    contexts: Dict[str, Dict[str, str]]
    overrides: Dict[str, Dict[str, str]]
    file_hashes: Dict[str, str]
    file_keys: Dict[str, List[str]]
    file_sequence: Dict[str, List[List[Optional[str]]]]
    plural_keys: Set[str]
    raw: Dict[str, Any]

    @classmethod
    def load(cls, path: Path) -> "TranslationMap":
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError as exc:
            raise ApplyError(f"translation map not found: {path}") from exc
        except json.JSONDecodeError as exc:
            raise ApplyError(f"translation map is not valid JSON: {exc}") from exc
        schema = data.get("schema")
        if schema != SCHEMA_VERSION:
            raise ApplyError(f"unsupported translation map schema {schema!r} (expected {SCHEMA_VERSION})")
        for key in ("language", "global"):
            if key not in data:
                raise ApplyError(f"translation map is missing required key {key!r}")
        return cls(
            path=path,
            language=data["language"],
            shell_version=str(data.get("caelestia_shell", "unknown")),
            package_version=str(data.get("package_version", "")),
            global_map=dict(data["global"]),
            contexts={k: dict(v) for k, v in data.get("contexts", {}).items()},
            overrides={k: dict(v) for k, v in data.get("overrides", {}).items()},
            file_hashes=dict(data.get("file_hashes", {})),
            file_keys={k: list(v) for k, v in data.get("file_keys", {}).items()},
            file_sequence={k: [list(slot) for slot in v] for k, v in data.get("file_sequence", {}).items()},
            plural_keys=set(data.get("plural_keys", [])),
            raw=data,
        )

    def resolve(self, text: str, context: Optional[str], relpath: str) -> Optional[str]:
        if context:
            table = self.contexts.get(context)
            if table and text in table:
                return table[text]
        table = self.overrides.get(relpath)
        if table and text in table:
            return table[text]
        return self.global_map.get(text)

    def resolve_plural(self, text: str, plural: str, context: Optional[str], relpath: str) -> Optional[str]:
        translated = self.resolve(plural, context, relpath)
        if translated is None:
            translated = self.resolve(text, context, relpath)
        return translated

    def is_known_translation(self, value: str, context: Optional[str], relpath: str) -> bool:
        """True when ``value`` is a translation this map could have produced."""
        candidates: Set[str] = set()
        if context and context in self.contexts:
            for src, dst in self.contexts[context].items():
                if dst == value:
                    return True
                candidates.add(src)
        for table in (self.overrides.get(relpath, {}), self.global_map):
            for src, dst in table.items():
                if dst == value:
                    candidates.add(src)
        for src in candidates:
            if self.resolve(src, context, relpath) == value:
                return True
        return False

    def find_original(self, value: str, context: Optional[str], relpath: str, slot_is_plural: bool) -> Optional[str]:
        """Best-effort inverse lookup for the backup-less revert fallback.

        The file's original key list plus the plural index keep this exact for
        every string the map itself produced; synonyms that never co-occur in
        the same file cannot be confused.
        """
        keys = set(self.file_keys[relpath]) if relpath in self.file_keys else None
        pool: Set[str] = set(self.global_map)
        pool |= set(self.overrides.get(relpath, {}))
        if context:
            pool |= set(self.contexts.get(context, {}))
        candidates: List[str] = []
        for src in pool:
            if src == value:
                continue
            if keys is not None and src not in keys and not (context and src in self.contexts.get(context, {})):
                continue
            if self.resolve(src, context, relpath) == value:
                candidates.append(src)
        if not candidates:
            return None
        preferred = [c for c in candidates if (c in self.plural_keys) == slot_is_plural]
        chosen = preferred or candidates
        chosen.sort(key=lambda s: (len(s), s))
        return chosen[0]


# --------------------------------------------------------------------------
# File processing
# --------------------------------------------------------------------------


@dataclass
class FileResult:
    relpath: str
    exists: bool = True
    state: str = "missing"
    sha256: str = ""
    result_sha256: str = ""
    changed: bool = False
    sites: int = 0
    applied: int = 0
    already: int = 0
    unmatched: int = 0
    dynamic: int = 0
    issues: List[str] = field(default_factory=list)
    diff: str = ""
    new_content: Optional[bytes] = None

    def counts(self) -> Dict[str, int]:
        return {
            "sites": self.sites,
            "applied": self.applied,
            "already": self.already,
            "unmatched": self.unmatched,
            "dynamic": self.dynamic,
        }


def process_file(root: Path, relpath: str, tmap: TranslationMap, check_hash: bool) -> FileResult:
    path = root / relpath
    res = FileResult(relpath=relpath)
    if not path.is_file():
        res.exists = False
        res.state = "missing"
        return res

    raw = path.read_bytes()
    res.sha256 = sha256_bytes(raw)
    try:
        src = raw.decode("utf-8")
    except UnicodeDecodeError:
        res.state = "error"
        res.issues.append("file is not valid UTF-8")
        return res

    expected_hash = tmap.file_hashes.get(relpath)
    pristine = expected_hash is not None and res.sha256 == expected_hash
    if expected_hash is None and check_hash:
        res.issues.append("file is not listed in the translation map; skipped")
        res.state = "unsupported"
        return res

    replacements: List[Tuple[int, int, str]] = []
    for site in scan_tr_calls(src):
        res.sites += 1
        if site.dynamic:
            res.dynamic += 1
            continue
        context = site.context.value if site.context else None
        for slot, literal in enumerate((site.text, site.plural)):
            if literal is None:
                continue
            value = literal.value
            if not value:
                continue
            translated = tmap.resolve(value, context, relpath)
            if site.plural is not None and slot == 1:
                translated = tmap.resolve_plural(site.text.value if site.text else "", value, context, relpath)
            if translated is None:
                if tmap.is_known_translation(value, context, relpath):
                    res.already += 1
                else:
                    res.unmatched += 1
                    res.issues.append(f"no translation for {value!r}" + (f" (context {context!r})" if context else ""))
                continue
            if translated == value:
                res.already += 1
                continue
            replacements.append((literal.start + 1, literal.end - 1, encode_literal(translated, literal.quote)))
            res.applied += 1

    if replacements:
        new_src = src
        for start, end, encoded in reversed(replacements):
            new_src = new_src[:start] + encoded + new_src[end:]
        res.new_content = new_src.encode("utf-8")
        res.result_sha256 = sha256_bytes(res.new_content)
        res.changed = True
        res.state = "modified" if not pristine else "pristine"

    if res.changed:
        if pristine:
            res.state = "pristine"
        elif res.unmatched == 0 and res.dynamic == 0:
            res.state = "already-translated" if res.applied == 0 else "modified"
        else:
            res.state = "mixed"
    else:
        if pristine:
            res.state = "pristine"
        elif res.unmatched == 0:
            res.state = "translated"
        else:
            res.state = "mixed"
    return res


# --------------------------------------------------------------------------
# Reporting
# --------------------------------------------------------------------------


def result_to_dict(res: FileResult) -> Dict[str, Any]:
    data: Dict[str, Any] = {
        "path": res.relpath,
        "exists": res.exists,
        "state": res.state,
        "sha256": res.sha256,
        "counts": res.counts(),
    }
    if res.result_sha256:
        data["result_sha256"] = res.result_sha256
    if res.changed:
        data["changed"] = True
    if res.issues:
        data["issues"] = res.issues[:20]
    return data


def print_summary(
    results: Sequence[FileResult], tmap: TranslationMap, root: Path, quiet: bool, verbose: bool = False
) -> Tuple[int, int, int]:
    total_sites = sum(r.sites for r in results)
    total_applied = sum(r.applied for r in results)
    total_unmatched = sum(r.unmatched for r in results)
    total_dynamic = sum(r.dynamic for r in results)
    changed_files = [r for r in results if r.changed]
    missing_files = [r for r in results if not r.exists]
    unsupported = [r for r in results if r.state == "unsupported"]
    errors = [r for r in results if r.state == "error"]

    if not quiet:
        print(f"  shell tree     : {root}")
        print(f"  translation map: {tmap.path.name} ({tmap.language}, Caelestia {tmap.shell_version})")
        print(f"  files          : {len(results)} referenced, {len(missing_files)} missing")
        print(f"  Tr call sites  : {total_sites} parsed "
              f"({total_applied} to translate, {total_unmatched} unknown, {total_dynamic} dynamic)")
        if changed_files and verbose:
            print("  files to update:")
            for res in changed_files[:60]:
                print(f"    - {res.relpath} (+{res.applied})")
            if len(changed_files) > 60:
                print(f"    ... and {len(changed_files) - 60} more")
        if unsupported:
            print(f"  warning: {len(unsupported)} file(s) not covered by the map were skipped")
            for res in unsupported[:10]:
                print(f"    ! {res.relpath}")
        if errors:
            print(f"  error: {len(errors)} file(s) could not be processed")
            for res in errors[:10]:
                print(f"    ! {res.relpath}: {res.issues[0] if res.issues else 'unknown error'}")
    return total_applied, total_unmatched, len(errors)


# --------------------------------------------------------------------------
# Commands
# --------------------------------------------------------------------------


def collect_results(root: Path, tmap: TranslationMap) -> List[FileResult]:
    results: List[FileResult] = []
    for relpath in sorted(tmap.file_hashes):
        results.append(process_file(root, relpath, tmap, check_hash=True))
    return results


def cmd_analyze(args: argparse.Namespace) -> int:
    root = Path(args.root).resolve()
    tmap = TranslationMap.load(Path(args.map))
    results = collect_results(root, tmap)
    applied, unmatched, errors = print_summary(results, tmap, root, args.quiet, args.verbose)
    if args.json:
        payload = {
            "root": str(root),
            "language": tmap.language,
            "caelestia_shell": tmap.shell_version,
            "files": [result_to_dict(r) for r in results],
            "totals": {
                "files": len(results),
                "changed_files": sum(1 for r in results if r.changed),
                "sites": sum(r.sites for r in results),
                "applied": applied,
                "unmatched": unmatched,
                "dynamic": sum(r.dynamic for r in results),
                "errors": errors,
            },
        }
        Path(args.json).write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 1 if errors else 0


def _atomic_write(path: Path, data: bytes) -> None:
    mode = path.stat().st_mode
    fd, tmp = tempfile.mkstemp(prefix=".caelestia-zh-", dir=str(path.parent))
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
        os.chmod(tmp, mode)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def cmd_apply(args: argparse.Namespace) -> int:
    root = Path(args.root).resolve()
    tmap = TranslationMap.load(Path(args.map))
    results = collect_results(root, tmap)

    if args.diff:
        for res in results:
            if not res.changed or res.new_content is None:
                continue
            old = (root / res.relpath).read_text(encoding="utf-8").splitlines(keepends=True)
            new = res.new_content.decode("utf-8").splitlines(keepends=True)
            sys.stdout.writelines(
                difflib.unified_diff(old, new, fromfile=f"a/{res.relpath}", tofile=f"b/{res.relpath}")
            )

    applied, unmatched, errors = print_summary(results, tmap, root, args.quiet, args.verbose)

    to_write = [r for r in results if r.changed and r.new_content is not None]
    if args.dry_run:
        if not args.quiet:
            print("  dry-run: no files were modified")
    else:
        written: List[Tuple[Path, bytes]] = []
        try:
            for res in to_write:
                path = root / res.relpath
                written.append((path, path.read_bytes()))
                _atomic_write(path, res.new_content or b"")
        except BaseException:
            for path, original in reversed(written):
                try:
                    _atomic_write(path, original)
                except OSError:
                    print(f"error: failed to roll back {path}", file=sys.stderr)
            raise ApplyError("failed while writing files; all changes were rolled back")
        if not args.quiet:
            print(f"  wrote {len(to_write)} file(s)")

    if args.json:
        payload = {
            "root": str(root),
            "language": tmap.language,
            "dry_run": bool(args.dry_run),
            "files": [result_to_dict(r) for r in results],
            "totals": {
                "files": len(results),
                "changed_files": len(to_write),
                "sites": sum(r.sites for r in results),
                "applied": applied,
                "unmatched": unmatched,
                "dynamic": sum(r.dynamic for r in results),
                "errors": errors,
            },
        }
        Path(args.json).write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 1 if errors else 0


def normalize_version(version: str) -> str:
    """Strip pkgrel / git suffixes: 2.5.0-1 and 2.5.0.r3.gabc both become 2.5.0."""
    match = re.match(r"\d+(?:\.\d+){1,3}", version or "")
    return match.group(0) if match else (version or "unknown")


def cmd_compat(args: argparse.Namespace) -> int:
    """Check whether a shell tree is hash-compatible with the translation map."""
    root = Path(args.root).resolve()
    tmap = TranslationMap.load(Path(args.map))
    results = collect_results(root, tmap)
    installed = args.version or "unknown"
    version_match = normalize_version(installed) == normalize_version(tmap.shell_version)
    pending = [r for r in results if r.exists and r.state not in ("pristine", "translated")]
    missing = [r for r in results if not r.exists]
    errors = [r for r in results if r.state == "error"]
    compatible = version_match or (not pending and not errors)
    payload = {
        "shell_dir": str(root),
        "installed_version": installed,
        "map_version": tmap.shell_version,
        "version_match": version_match,
        "compatible": compatible,
        "files": len(results),
        "pristine": sum(1 for r in results if r.state == "pristine"),
        "translated": sum(1 for r in results if r.state == "translated"),
        "pending": [r.relpath for r in pending],
        "missing": [r.relpath for r in missing],
        "errors": [r.relpath for r in errors],
    }
    if args.json:
        Path(args.json).write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if not args.quiet:
        print(f"  installed version: {installed}")
        print(f"  map version      : {tmap.shell_version}")
        print(f"  version match    : {'yes' if version_match else 'no'}")
        print(f"  files            : {payload['files']} ({payload['pristine']} pristine, "
              f"{payload['translated']} translated, {len(pending)} pending, {len(missing)} missing)")
        if pending:
            print("  files that do not match the supported revision:")
            for relpath in payload["pending"][:20]:
                print(f"    - {relpath}")
            if len(pending) > 20:
                print(f"    ... and {len(pending) - 20} more")
    return 0 if compatible else 3


def cmd_revert(args: argparse.Namespace) -> int:
    """Reverse known translations at verified call sites (backup-less fallback).

    The translation map records the original literal sequence of every file, so
    when the call sites still line up the revert is exact. If the file was
    edited in a way that changed the sequence, a guarded heuristic is used and
    any ambiguous literal is left untouched.
    """
    root = Path(args.root).resolve()
    tmap = TranslationMap.load(Path(args.map))
    reverted = 0
    changed_files = 0
    for relpath in sorted(tmap.file_hashes):
        path = root / relpath
        if not path.is_file():
            continue
        src = path.read_text(encoding="utf-8")
        sites = [site for site in scan_tr_calls(src) if not site.dynamic]
        replacements: List[Tuple[int, int, str]] = []
        sequence = tmap.file_sequence.get(relpath)
        exact = sequence is not None and len(sequence) == len(sites)

        for index, site in enumerate(sites):
            context = site.context.value if site.context else None
            expected = sequence[index] if exact and sequence is not None else [None, None]
            for slot, literal in enumerate((site.text, site.plural)):
                if literal is None or not literal.value:
                    continue
                original: Optional[str] = None
                if exact:
                    candidate = expected[slot] if slot < len(expected) else None
                    if candidate and candidate != literal.value:
                        translated = tmap.resolve(candidate, context, relpath)
                        if slot == 1 and site.text is not None:
                            translated = tmap.resolve_plural(site.text.value, candidate, context, relpath)
                        if translated == literal.value:
                            original = candidate
                elif tmap.is_known_translation(literal.value, context, relpath):
                    original = tmap.find_original(literal.value, context, relpath, slot == 1)
                if original is None or original == literal.value:
                    continue
                replacements.append((literal.start + 1, literal.end - 1, encode_literal(original, literal.quote)))
                reverted += 1

        if replacements:
            new_src = src
            for start, end, encoded in reversed(replacements):
                new_src = new_src[:start] + encoded + new_src[end:]
            changed_files += 1
            if args.dry_run:
                if not args.quiet:
                    print(f"    would revert {relpath} ({len(replacements)})" if args.verbose
                          else f"    would revert {relpath}")
            else:
                _atomic_write(path, new_src.encode("utf-8"))
    if not args.quiet:
        verb = "would revert" if args.dry_run else "reverted"
        print(f"  {verb} {reverted} literal(s) across {changed_files} file(s)")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Caelestia Chinese localisation engine")
    parser.add_argument("--version", action="version", version="caelestia-zh apply.py 1.0.0")
    sub = parser.add_subparsers(dest="command", required=True)

    def common(p: argparse.ArgumentParser) -> None:
        p.add_argument("--root", required=True, help="shell tree to operate on")
        p.add_argument("--map", required=True, help="translation map JSON")
        p.add_argument("--json", help="write a machine-readable report to this path")
        p.add_argument("--quiet", action="store_true")
        p.add_argument("--verbose", action="store_true")
        p.add_argument("--dry-run", action="store_true")

    analyze = sub.add_parser("analyze", help="classify files and count translatable strings")
    common(analyze)
    analyze.set_defaults(func=cmd_analyze)

    apply = sub.add_parser("apply", help="rewrite matching string literals")
    common(apply)
    apply.add_argument("--diff", action="store_true", help="print unified diffs")
    apply.set_defaults(func=cmd_apply)

    compat = sub.add_parser("compat", help="check version / hash compatibility")
    common(compat)
    compat.add_argument("--version", default="", help="installed caelestia-shell version")
    compat.set_defaults(func=cmd_compat)

    revert = sub.add_parser("revert", help="undo known translations without a backup")
    common(revert)
    revert.set_defaults(func=cmd_revert)
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.func(args))
    except ApplyError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    except OSError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
