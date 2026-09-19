#!/usr/bin/env bash
#
# Test suite for caelestia-zh.sh.
#
# Runs against isolated sandboxes under a temporary directory; the real
# ~/.config and ~/.local are never touched. Usage:
#
#   ./tests/run-tests.sh
#
set -uo pipefail

TEST_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd)"
PROJECT_DIR="$(cd -- "$TEST_DIR/.." >/dev/null 2>&1 && pwd)"
SUT="$PROJECT_DIR/caelestia-zh.sh"
FIXTURE="$TEST_DIR/fixtures/shell"
DICT="$TEST_DIR/fixtures/translations/zh_CN.dict.json"
PROJECT_MAP="$PROJECT_DIR/translations/zh_CN.json"
REAL_TREE="/etc/xdg/quickshell/caelestia"

TMP="$(mktemp -d /tmp/caelestia-zh-tests.XXXXXX)"
trap 'chmod -R u+rwX "$TMP" 2>/dev/null; rm -rf "$TMP"' EXIT

if [[ -t 1 && -z "${NO_COLOR:-}" ]]; then
    C_GREEN=$'\033[32m'; C_RED=$'\033[31m'; C_BOLD=$'\033[1m'; C_RESET=$'\033[0m'
else
    C_GREEN=""; C_RED=""; C_BOLD=""; C_RESET=""
fi

PASS=0
FAIL=0
SKIP=0
CASE_FAIL=0
RC=0
OUT=""
SB=""
PRJ_MAP=""
PRJ_SHELL=""
PRJ_DATA=""

# ---------------------------------------------------------------------------
# assertions
# ---------------------------------------------------------------------------
pass() { PASS=$((PASS + 1)); }
fail() {
    FAIL=$((FAIL + 1))
    CASE_FAIL=$((CASE_FAIL + 1))
    printf '    %sFAIL%s %s\n' "$C_RED" "$C_RESET" "$1"
}

assert_eq() {
    if [[ "$1" == "$2" ]]; then pass; else fail "${3:-assert_eq}: got '$1', want '$2'"; fi
}

assert_rc() {
    if [[ "$RC" == "$1" ]]; then pass; else fail "exit code: got $RC, want $1"; fi
}

assert_contains() {
    if [[ "$1" == *"$2"* ]]; then pass; else fail "${3:-output}: missing '$2'"; fi
}

assert_not_contains() {
    if [[ "$1" != *"$2"* ]]; then pass; else fail "${3:-output}: unexpectedly contains '$2'"; fi
}

assert_file_contains() {
    if grep -qF -- "$2" "$1" 2>/dev/null; then pass; else fail "$1: missing '$2'"; fi
}

assert_file_not_contains() {
    if grep -qF -- "$2" "$1" 2>/dev/null; then fail "$1: still contains '$2'"; else pass; fi
}

assert_file_exists() {
    if [[ -f "$1" ]]; then pass; else fail "$1 should exist"; fi
}

assert_file_missing() {
    if [[ -f "$1" ]]; then fail "$1 should not exist"; else pass; fi
}

assert_tree_equal() {
    if diff -rq "$1" "$2" >/dev/null 2>&1; then
        pass
    else
        fail "trees differ: $(diff -rq "$1" "$2" 2>&1 | head -3 | tr '\n' ' ')"
    fi
}

tree_hash() {
    find "$1" -type f -print0 2>/dev/null | sort -z | xargs -0 sha256sum 2>/dev/null | sha256sum | cut -d' ' -f1
}

# ---------------------------------------------------------------------------
# sandbox / runner
# ---------------------------------------------------------------------------
new_sandbox() {
    local name="$1"
    SB="$TMP/$name"
    rm -rf "$SB"
    mkdir -p "$SB"
    cp -a "$FIXTURE" "$SB/shell"
    cp -a "$FIXTURE" "$SB/pristine"
    if ! python3 "$PROJECT_DIR/tools/make_map.py" \
        --dictionary "$DICT" --root "$SB/shell" --out "$SB/zh_CN.json" \
        --language zh_CN --version 2.5.0 --package-version 2.5.0-1 --quiet; then
        printf '%s[!]%s failed to build fixture map\n' "$C_RED" "$C_RESET"
        exit 1
    fi
    PRJ_MAP="$SB/zh_CN.json"
    PRJ_SHELL="$SB/shell"
    PRJ_DATA="$SB/data"
}

run_prj() {
    OUT="$("$SUT" "$@" --shell-dir "$PRJ_SHELL" --data-dir "$PRJ_DATA" --map "$PRJ_MAP" \
        --shell-version 2.5.0-1 2>&1)"
    RC=$?
}

run_raw() {
    OUT="$("$SUT" "$@" 2>&1)"
    RC=$?
}

begin() {
    printf '%s== %s%s\n' "$C_BOLD" "$1" "$C_RESET"
    CASE_FAIL=0
}

finish() {
    if [[ $CASE_FAIL -eq 0 ]]; then
        printf '  %sok%s\n' "$C_GREEN" "$C_RESET"
    else
        printf '  %s%d assertion(s) failed%s\n' "$C_RED" "$CASE_FAIL" "$C_RESET"
    fi
}

# ---------------------------------------------------------------------------
# tests
# ---------------------------------------------------------------------------
test_fresh_install() {
    begin "fresh install"
    new_sandbox fresh
    local before
    before="$(tree_hash "$PRJ_SHELL")"

    run_prj install
    assert_rc 0
    assert_contains "$OUT" "汉化完成"
    assert_file_contains "$PRJ_SHELL/components/Basic.qml" 'Tr.tr("壁纸与样式")'
    assert_file_contains "$PRJ_SHELL/components/Basic.qml" "Tr.tr('单引号')"
    # shellcheck disable=SC2016  # literal backticks are intentional
    assert_file_contains "$PRJ_SHELL/components/Basic.qml" 'Tr.tr(`反引号`)'
    assert_file_contains "$PRJ_SHELL/components/Basic.qml" 'Tr.tr("内部含 \"引号\"")'
    assert_file_contains "$PRJ_SHELL/components/Basic.qml" '第一行\n第二行'
    assert_file_contains "$PRJ_SHELL/components/Basic.qml" '"暂无新通知"'
    assert_file_contains "$PRJ_SHELL/components/Basic.qml" 'text: "chevron_right"'
    assert_file_contains "$PRJ_SHELL/components/Basic.qml" 'Tr.tr(root.iconName)'
    assert_file_contains "$PRJ_SHELL/components/Basic.qml" '// Tr.tr("Commented out string")'
    assert_file_contains "$PRJ_SHELL/components/Basic.qml" '/* Tr.tr("Block comment string") */'
    assert_file_contains "$PRJ_SHELL/components/Basic.qml" '// text: Tr.tr("Cancel")'
    assert_file_contains "$PRJ_SHELL/components/Basic.qml" 'text: Tr.tr("取消")'
    assert_file_not_contains "$PRJ_SHELL/components/Basic.qml" '// text: Tr.tr("取消")'
    assert_file_contains "$PRJ_SHELL/modules/Panel.qml" 'Tr.trCtx("启用", "toggle label")'
    assert_file_contains "$PRJ_SHELL/modules/Panel.qml" 'Tr.trCtx("已启用", "panel status")'
    assert_file_contains "$PRJ_SHELL/modules/Panel.qml" 'Tr.trN("%n 个设备可用", "%n 个设备可用", root.count)'
    assert_file_contains "$PRJ_SHELL/modules/Panel.qml" 'Tr.trCtx("开放", "wifi security type")'
    assert_file_contains "$PRJ_SHELL/modules/Panel.qml" 'Tr.tr("打开设置")'
    assert_file_contains "$PRJ_SHELL/services/Toast.qml" 'Tr.mark("已录制 %1"'
    assert_file_contains "$PRJ_SHELL/services/Toast.qml" 'Tr.tr(someVariable)'
    assert_file_exists "$PRJ_DATA/state.json"
    assert_file_missing "$PRJ_DATA/plan.json"
    if [[ -n "$(find "$PRJ_DATA/backup" -type f -print -quit 2>/dev/null)" ]]; then pass; else fail "no backups created"; fi
    if [[ "$(tree_hash "$PRJ_SHELL")" != "$before" ]]; then pass; else fail "tree should have changed"; fi
    finish
}

test_idempotent_install() {
    begin "repeated install is idempotent"
    new_sandbox repeat
    run_prj install
    assert_rc 0
    local after_first
    after_first="$(tree_hash "$PRJ_SHELL")"

    run_prj install
    assert_rc 0
    assert_contains "$OUT" "无需修改"
    assert_eq "$(tree_hash "$PRJ_SHELL")" "$after_first" "tree changed on second install"
    finish
}

test_dry_run() {
    begin "dry-run install"
    new_sandbox dryrun
    local before
    before="$(tree_hash "$PRJ_SHELL")"

    run_prj install --dry-run
    assert_rc 0
    assert_contains "$OUT" "dry-run"
    assert_contains "$OUT" "壁纸与样式"
    assert_eq "$(tree_hash "$PRJ_SHELL")" "$before" "dry-run modified files"
    assert_file_missing "$PRJ_DATA/state.json"
    finish
}

test_status() {
    begin "status before and after install"
    new_sandbox status
    run_prj status
    assert_rc 0
    assert_contains "$OUT" "not installed"

    run_prj install
    assert_rc 0
    run_prj status --verbose
    assert_rc 0
    assert_contains "$OUT" "installed"
    assert_contains "$OUT" "可翻译字符串"
    finish
}

test_uninstall_restores() {
    begin "uninstall restores byte-exact originals"
    new_sandbox uninstall
    run_prj install
    assert_rc 0

    run_prj uninstall
    assert_rc 0
    assert_contains "$OUT" "已恢复"
    assert_tree_equal "$PRJ_SHELL" "$SB/pristine"
    assert_file_missing "$PRJ_DATA/state.json"
    finish
}

test_repeated_uninstall() {
    begin "repeated uninstall is a no-op"
    new_sandbox uninstall2
    run_prj install
    run_prj uninstall
    assert_rc 0

    run_prj uninstall
    assert_rc 0
    assert_contains "$OUT" "没有需要恢复的文件"
    assert_tree_equal "$PRJ_SHELL" "$SB/pristine"
    finish
}

test_dry_run_uninstall() {
    begin "dry-run uninstall keeps files"
    new_sandbox uninstall-dry
    run_prj install
    assert_rc 0

    run_prj uninstall --dry-run
    assert_rc 0
    assert_contains "$OUT" "dry-run"
    assert_file_contains "$PRJ_SHELL/components/Basic.qml" '壁纸与样式'
    assert_file_exists "$PRJ_DATA/state.json"
    finish
}

test_missing_shell_dir() {
    begin "missing shell directory is rejected"
    new_sandbox missing
    run_raw install --shell-dir "$SB/does-not-exist" --data-dir "$SB/data" --map "$PRJ_MAP"
    assert_rc 1
    assert_contains "$OUT" "shell.qml"
    finish
}

test_version_mismatch_gate() {
    begin "version mismatch gate"
    new_sandbox version
    printf '\n// local tweak\n' >>"$PRJ_SHELL/modules/Panel.qml"

    OUT="$("$SUT" install --shell-dir "$PRJ_SHELL" --data-dir "$PRJ_DATA" --map "$PRJ_MAP" \
        --shell-version 9.9.9 2>&1)"
    RC=$?
    assert_rc 1
    assert_contains "$OUT" "--force-version"

    OUT="$("$SUT" install --shell-dir "$PRJ_SHELL" --data-dir "$PRJ_DATA" --map "$PRJ_MAP" \
        --shell-version 9.9.9 --force-version 2>&1)"
    RC=$?
    assert_rc 0
    assert_file_contains "$PRJ_SHELL/components/Basic.qml" '壁纸与样式'
    assert_file_contains "$PRJ_SHELL/modules/Panel.qml" '// local tweak'

    # Same version with a user tweak installs without forcing
    new_sandbox version-ok
    printf '\n// local tweak\n' >>"$PRJ_SHELL/modules/Panel.qml"
    run_prj install
    assert_rc 0
    assert_file_contains "$PRJ_SHELL/components/Basic.qml" '壁纸与样式'
    assert_file_contains "$PRJ_SHELL/modules/Panel.qml" '// local tweak'
    finish
}

test_user_modified_after_install() {
    begin "user modification after install"
    new_sandbox modified
    run_prj install
    assert_rc 0
    sed -i 's/壁纸与样式/壁纸与样式（自定义）/' "$PRJ_SHELL/components/Basic.qml"

    run_prj uninstall
    assert_rc 3
    assert_contains "$OUT" "已被手动修改"
    assert_file_contains "$PRJ_SHELL/components/Basic.qml" '壁纸与样式（自定义）'
    assert_file_exists "$PRJ_DATA/state.json"

    run_prj uninstall --force
    assert_rc 0
    assert_tree_equal "$PRJ_SHELL" "$SB/pristine"
    assert_file_missing "$PRJ_DATA/state.json"
    finish
}

test_new_untranslated_string() {
    begin "new upstream string stays English and warns"
    new_sandbox newstring
    printf '\nStyledText { text: Tr.tr("Brand new string") }\n' >>"$PRJ_SHELL/components/Basic.qml"

    run_prj install
    assert_rc 3
    assert_contains "$OUT" "保持英文"
    assert_file_contains "$PRJ_SHELL/components/Basic.qml" 'Tr.tr("Brand new string")'
    assert_file_contains "$PRJ_SHELL/components/Basic.qml" '壁纸与样式'
    finish
}

test_missing_mapped_file() {
    begin "missing mapped file is skipped gracefully"
    new_sandbox missing-file
    rm -f "$PRJ_SHELL/modules/Panel.qml"

    run_prj install
    assert_rc 0
    assert_file_contains "$PRJ_SHELL/components/Basic.qml" '壁纸与样式'

    run_prj status
    assert_rc 0
    finish
}

test_rollback_on_write_failure() {
    begin "write failure rolls everything back"
    new_sandbox rollback
    local before
    before="$(tree_hash "$PRJ_SHELL")"
    chmod 500 "$PRJ_SHELL/services"

    run_prj install
    assert_rc 1
    chmod 700 "$PRJ_SHELL/services"
    assert_contains "$OUT" "回滚"
    assert_not_contains "$OUT" "汉化完成"
    assert_eq "$(tree_hash "$PRJ_SHELL")" "$before" "partial changes were left behind"
    assert_file_missing "$PRJ_DATA/state.json"
    finish
}

test_map_revert_fallback() {
    begin "map-based revert without backups"
    new_sandbox revertmap
    run_prj install
    assert_rc 0
    rm -rf "$PRJ_DATA"

    run_prj uninstall --revert-from-map
    assert_rc 0
    assert_tree_equal "$PRJ_SHELL" "$SB/pristine"
    finish
}

test_restore_deleted_file() {
    begin "uninstall restores a deleted translated file"
    new_sandbox deleted
    run_prj install
    assert_rc 0
    rm -f "$PRJ_SHELL/modules/Panel.qml"

    run_prj uninstall
    assert_rc 0
    assert_tree_equal "$PRJ_SHELL" "$SB/pristine"
    finish
}

test_lock_contention() {
    begin "concurrent run is rejected"
    new_sandbox lock
    mkdir -p "$PRJ_DATA"
    exec 8>"$PRJ_DATA/lock"
    if flock -n 8; then
        run_prj status
        assert_rc 1
        assert_contains "$OUT" "另一个"
        flock -u 8
    else
        fail "could not acquire test lock"
    fi
    exec 8>&-
    finish
}

test_unwritable_shell() {
    begin "unwritable shell directory is rejected"
    new_sandbox unwritable
    chmod 500 "$PRJ_SHELL"
    run_prj install
    chmod 700 "$PRJ_SHELL"
    assert_rc 1
    assert_contains "$OUT" "权限"
    finish
}

test_target_auto() {
    begin "target auto detection via XDG_CONFIG_HOME"
    new_sandbox auto
    mkdir -p "$SB/xdg/quickshell"
    cp -a "$FIXTURE" "$SB/xdg/quickshell/caelestia"

    OUT="$(XDG_CONFIG_HOME="$SB/xdg" "$SUT" status --data-dir "$PRJ_DATA" --map "$PRJ_MAP" \
        --shell-version 2.5.0-1 2>&1)"
    RC=$?
    assert_rc 0
    assert_contains "$OUT" "$SB/xdg/quickshell/caelestia"
    finish
}

test_bad_map() {
    begin "missing and corrupt translation maps"
    new_sandbox badmap
    run_raw install --shell-dir "$PRJ_SHELL" --data-dir "$PRJ_DATA" --map "$SB/nope.json"
    assert_rc 1
    assert_contains "$OUT" "找不到翻译表"

    printf '{ not json' >"$SB/broken.json"
    run_raw install --shell-dir "$PRJ_SHELL" --data-dir "$PRJ_DATA" --map "$SB/broken.json"
    assert_rc 1
    assert_contains "$OUT" "not valid JSON"
    finish
}

test_strict_mode() {
    begin "strict mode aborts on untranslated strings"
    new_sandbox strict
    printf '\nStyledText { text: Tr.tr("Brand new string") }\n' >>"$PRJ_SHELL/components/Basic.qml"
    local before
    before="$(tree_hash "$PRJ_SHELL")"

    run_prj install --strict
    assert_rc 1
    assert_contains "$OUT" "--strict"
    assert_eq "$(tree_hash "$PRJ_SHELL")" "$before" "strict install modified files"

    run_prj install
    assert_rc 3
    assert_file_contains "$PRJ_SHELL/components/Basic.qml" '壁纸与样式'
    finish
}

test_real_tree_roundtrip() {
    begin "integration: real Caelestia tree round-trip"
    if [[ ! -f "$REAL_TREE/shell.qml" ]]; then
        SKIP=$((SKIP + 1))
        printf '  %sskipped (no Caelestia installation)%s\n' "$C_BOLD" "$C_RESET"
        return
    fi
    SB="$TMP/real"
    rm -rf "$SB"
    mkdir -p "$SB"
    cp -a "$REAL_TREE" "$SB/shell"
    cp -a "$REAL_TREE" "$SB/pristine"

    OUT="$("$SUT" install --shell-dir "$SB/shell" --data-dir "$SB/data" --map "$PROJECT_MAP" \
        --shell-version "$(pacman -Q caelestia-shell 2>/dev/null | awk '{print $2}')" 2>&1)"
    RC=$?
    assert_rc 0
    assert_file_contains "$SB/shell/modules/nexus/PageRegistry.qml" '壁纸与样式'
    assert_file_contains "$SB/shell/modules/nexus/PageRegistry.qml" '//     label: Tr.tr("Display")'

    OUT="$("$SUT" uninstall --shell-dir "$SB/shell" --data-dir "$SB/data" 2>&1)"
    RC=$?
    assert_rc 0
    assert_tree_equal "$SB/shell" "$SB/pristine"
    finish
}

# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------
main() {
    printf '%sCaelestia-zh test suite%s\n' "$C_BOLD" "$C_RESET"
    printf '  project : %s\n' "$PROJECT_DIR"
    printf '  sandbox : %s\n\n' "$TMP"

    test_fresh_install
    test_idempotent_install
    test_dry_run
    test_status
    test_uninstall_restores
    test_repeated_uninstall
    test_dry_run_uninstall
    test_missing_shell_dir
    test_version_mismatch_gate
    test_user_modified_after_install
    test_new_untranslated_string
    test_missing_mapped_file
    test_rollback_on_write_failure
    test_map_revert_fallback
    test_restore_deleted_file
    test_lock_contention
    test_unwritable_shell
    test_target_auto
    test_bad_map
    test_strict_mode
    test_real_tree_roundtrip

    printf '\n%s%d passed%s, %s%d failed%s, %d skipped\n' \
        "$C_GREEN" "$PASS" "$C_RESET" "$C_RED" "$FAIL" "$C_RESET" "$SKIP"
    [[ $FAIL -eq 0 ]] || exit 1
    exit 0
}

main "$@"
