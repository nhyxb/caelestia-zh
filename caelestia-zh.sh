#!/usr/bin/env bash
#
# caelestia-zh.sh - Simplified Chinese localisation for the Caelestia shell
#
# Works on top of an installed caelestia-shell (Arch Linux / EndeavourOS).
# The shell QML is never replaced: only the string literals passed to the
# upstream Tr.* helpers are rewritten, with a byte-exact backup taken first.
#
# Exit codes: 0 success, 1 fatal error, 3 finished with warnings.
#
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd)"
readonly SCRIPT_DIR
readonly TOOLS_DIR="$SCRIPT_DIR/tools"

if [[ -r "$SCRIPT_DIR/VERSION" ]]; then
    PROJECT_VERSION="$(tr -d '[:space:]' <"$SCRIPT_DIR/VERSION")"
else
    PROJECT_VERSION="1.0.0"
fi
readonly PROJECT_VERSION
readonly DEFAULT_MAP="$SCRIPT_DIR/translations/zh_CN.json"
readonly SYSTEM_SHELL_DIR="/etc/xdg/quickshell/caelestia"
readonly PACKAGE="caelestia-shell"

# ---------------------------------------------------------------------------
# options
# ---------------------------------------------------------------------------
COMMAND=""
DRY_RUN=0
FORCE=0
FORCE_VERSION=0
STRICT=0
QUIET=0
VERBOSE=0
REVERT_FROM_MAP=0
TARGET="auto"
SHELL_DIR=""
MAP_FILE="$DEFAULT_MAP"
DATA_DIR=""
VERSION_OVERRIDE=""

# ---------------------------------------------------------------------------
# output helpers
# ---------------------------------------------------------------------------
if [[ -t 1 && -z "${NO_COLOR:-}" ]]; then
    C_RESET=$'\033[0m'
    C_RED=$'\033[31m'
    C_GREEN=$'\033[32m'
    C_YELLOW=$'\033[33m'
    C_BLUE=$'\033[34m'
    C_BOLD=$'\033[1m'
else
    C_RESET="" C_RED="" C_GREEN="" C_YELLOW="" C_BLUE="" C_BOLD=""
fi

info() { [[ $QUIET -eq 1 ]] || printf '%s[*]%s %s\n' "$C_BLUE" "$C_RESET" "$*"; }
ok() { [[ $QUIET -eq 1 ]] || printf '%s[+]%s %s\n' "$C_GREEN" "$C_RESET" "$*"; }
warn() { printf '%s[!]%s %s\n' "$C_YELLOW" "$C_RESET" "$*" >&2; }
err() { printf '%s[x]%s %s\n' "$C_RED" "$C_RESET" "$*" >&2; }
die() {
    err "$*"
    exit 1
}
debug() { [[ $VERBOSE -eq 1 && $QUIET -eq 0 ]] && printf '%s[.]%s %s\n' "$C_BLUE" "$C_RESET" "$*" || true; }

usage() {
    cat <<EOF
${C_BOLD}Caelestia 中文本地化 (${PROJECT_VERSION})${C_RESET}

用法:
  ./caelestia-zh.sh <命令> [选项]

命令:
  install      应用简体中文汉化（修改前自动备份）
  uninstall    恢复原始文件（优先使用备份）
  status       查看当前汉化状态
  update        Caelestia 更新后重新应用汉化
  verify       校验已汉化文件是否与安装记录一致
  version      显示版本
  help         显示本帮助

选项:
  --dry-run            只演示，不修改任何文件
  --shell-dir DIR      手动指定 Caelestia shell 配置目录
  --target user|system auto(默认) / 用户配置副本 / 系统目录
  --map FILE           指定翻译表（默认 translations/zh_CN.json）
  --data-dir DIR       指定状态与备份目录
  --force              卸载时忽略用户后续修改，强制恢复备份
  --force-version      版本不匹配时仍继续（谨慎）
  --strict             版本或哈希不匹配、存在未翻译字符串时中止
  --revert-from-map    没有备份时按翻译表反向恢复中文
  --shell-version V    覆盖 Caelestia 版本检测（主要供测试）
  --quiet              安静模式
  --verbose            显示更多细节
  -h, --help           显示帮助

退出码: 0 成功 / 1 失败 / 3 成功但有警告

示例:
  ./caelestia-zh.sh install --dry-run
  ./caelestia-zh.sh install
  ./caelestia-zh.sh status --verbose
  ./caelestia-zh.sh update
  ./caelestia-zh.sh uninstall
EOF
}

# ---------------------------------------------------------------------------
# argument parsing
# ---------------------------------------------------------------------------
parse_args() {
    while [[ $# -gt 0 ]]; do
        case "$1" in
            install | uninstall | status | update | verify | version | help | --help | -h)
                if [[ "$1" == "help" || "$1" == "--help" || "$1" == "-h" ]]; then
                    COMMAND="help"
                elif [[ -z "$COMMAND" ]]; then
                    COMMAND="$1"
                else
                    die "只能指定一个命令（已经指定了 $COMMAND）"
                fi
                shift
                ;;
            --dry-run) DRY_RUN=1; shift ;;
            --force) FORCE=1; shift ;;
            --force-version) FORCE_VERSION=1; shift ;;
            --strict) STRICT=1; shift ;;
            --quiet) QUIET=1; shift ;;
            --verbose) VERBOSE=1; shift ;;
            --revert-from-map) REVERT_FROM_MAP=1; shift ;;
            --shell-dir) SHELL_DIR="${2:?--shell-dir 需要一个参数}"; shift 2 ;;
            --shell-dir=*) SHELL_DIR="${1#*=}"; shift ;;
            --target) TARGET="${2:?--target 需要一个参数}"; shift 2 ;;
            --target=*) TARGET="${1#*=}"; shift ;;
            --map) MAP_FILE="${2:?--map 需要一个参数}"; shift 2 ;;
            --map=*) MAP_FILE="${1#*=}"; shift ;;
            --data-dir) DATA_DIR="${2:?--data-dir 需要一个参数}"; shift 2 ;;
            --data-dir=*) DATA_DIR="${1#*=}"; shift ;;
            --shell-version) VERSION_OVERRIDE="${2:?--shell-version 需要一个参数}"; shift 2 ;;
            --shell-version=*) VERSION_OVERRIDE="${1#*=}"; shift ;;
            *) die "未知选项: $1（用 --help 查看帮助）" ;;
        esac
    done
}

# ---------------------------------------------------------------------------
# environment
# ---------------------------------------------------------------------------
REAL_HOME="$HOME"
REAL_USER=""
if [[ ${EUID} -eq 0 && -n "${SUDO_USER:-}" && "${SUDO_USER}" != "root" ]]; then
    REAL_USER="$SUDO_USER"
    if command -v getent >/dev/null 2>&1; then
        REAL_HOME="$(getent passwd "$SUDO_USER" | cut -d: -f6)"
        [[ -n "$REAL_HOME" ]] || REAL_HOME="/home/$SUDO_USER"
    else
        REAL_HOME="/home/$SUDO_USER"
    fi
fi

check_dependencies() {
    local missing=()
    command -v python3 >/dev/null 2>&1 || missing+=("python3")
    command -v flock >/dev/null 2>&1 || missing+=("flock (util-linux)")
    if [[ ${#missing[@]} -gt 0 ]]; then
        die "缺少依赖: ${missing[*]}。请先安装后再运行。"
    fi
    if ! python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3, 8) else 1)'; then
        die "需要 Python 3.8 或更高版本（当前: $(python3 --version 2>&1)）"
    fi
    [[ -f "$TOOLS_DIR/apply.py" ]] || die "缺少 $TOOLS_DIR/apply.py，请在完整的项目目录中运行本脚本。"
    [[ -f "$TOOLS_DIR/state.py" ]] || die "缺少 $TOOLS_DIR/state.py，请在完整的项目目录中运行本脚本。"
    [[ -f "$MAP_FILE" ]] || die "找不到翻译表: $MAP_FILE"
}

resolve_data_dir() {
    if [[ -n "$DATA_DIR" ]]; then
        printf '%s' "$DATA_DIR"
        return
    fi
    if [[ -n "${CAELESTIA_ZH_DATA_DIR:-}" ]]; then
        printf '%s' "$CAELESTIA_ZH_DATA_DIR"
        return
    fi
    local base="${XDG_DATA_HOME:-$REAL_HOME/.local/share}"
    # When running through sudo the user's XDG_DATA_HOME is not inherited.
    if [[ ${EUID} -eq 0 && -n "$REAL_USER" && "$base" != "$REAL_HOME"/* ]]; then
        base="$REAL_HOME/.local/share"
    fi
    printf '%s' "$base/caelestia-zh"
}

resolve_shell_dir() {
    local user_dir="${XDG_CONFIG_HOME:-$REAL_HOME/.config}/quickshell/caelestia"
    if [[ ${EUID} -eq 0 && -n "$REAL_USER" && -n "${SUDO_USER:-}" ]]; then
        user_dir="$REAL_HOME/.config/quickshell/caelestia"
    fi
    case "$TARGET" in
        user)
            printf '%s' "$user_dir"
            ;;
        system)
            printf '%s' "$SYSTEM_SHELL_DIR"
            ;;
        auto)
            if [[ -f "$user_dir/shell.qml" ]]; then
                printf '%s' "$user_dir"
            elif [[ -f "$SYSTEM_SHELL_DIR/shell.qml" ]]; then
                printf '%s' "$SYSTEM_SHELL_DIR"
            else
                printf '%s' "$user_dir"
            fi
            ;;
        *)
            die "--target 只能是 user、system 或 auto"
            ;;
    esac
}

detect_version() {
    if [[ -n "$VERSION_OVERRIDE" ]]; then
        printf '%s' "$VERSION_OVERRIDE"
        return
    fi
    if command -v pacman >/dev/null 2>&1; then
        local raw
        raw="$(pacman -Q "$PACKAGE" 2>/dev/null || true)"
        if [[ -n "$raw" ]]; then
            printf '%s' "${raw#* }"
            return
        fi
    fi
    printf 'unknown'
}

acquire_lock() {
    local data_dir="$1"
    mkdir -p "$data_dir"
    exec 9>"$data_dir/lock"
    if ! flock -n 9; then
        die "另一个 caelestia-zh 实例正在运行（锁: $data_dir/lock）"
    fi
}

fix_ownership() {
    [[ ${EUID} -eq 0 && -n "$REAL_USER" ]] || return 0
    chown -R "$REAL_USER" "$1" 2>/dev/null || true
}

run_py() {
    # run_py <tool> <args...>; returns the tool's exit code
    local tool="$1"
    shift
    python3 "$TOOLS_DIR/$tool" "$@"
}

json_field() {
    # json_field <file> <key> [<key> ...]
    python3 - "$@" <<'PY'
import json, sys
value = json.load(open(sys.argv[1], encoding="utf-8"))
for key in sys.argv[2:]:
    value = value[key]
print(value)
PY
}

map_field() {
    json_field "$MAP_FILE" "$@"
}

report_field() {
    json_field "$1" "totals" "$2"
}

json_count() {
    # json_count <file> <key> [<key> ...]
    python3 - "$@" <<'PY'
import json, sys
value = json.load(open(sys.argv[1], encoding="utf-8"))
for key in sys.argv[2:]:
    value = value[key]
print(len(value) if isinstance(value, list) else value)
PY
}

compat_gate() {
    local compat_json="$DATA_DIR/reports/compat.json"
    mkdir -p "$DATA_DIR/reports"
    local rc=0
    run_py apply.py compat --root "$SHELL_DIR" --map "$MAP_FILE" \
        --version "$INSTALLED_VERSION" --json "$compat_json" || rc=$?
    if [[ $rc -eq 0 ]]; then
        debug "版本与哈希兼容性检查通过"
        return 0
    fi
    if [[ $rc -ne 3 ]]; then
        die "兼容性检查失败（退出码 $rc）"
    fi
    # rc == 3: version and hashes do not match the supported revision
    warn "当前 Caelestia 版本与翻译表不一致，文件内容也未通过哈希校验。"
    warn "翻译表面向 caelestia-shell $(map_field caelestia_shell)。"
    if [[ $STRICT -eq 1 ]]; then
        die "--strict 已启用：版本或哈希不匹配时终止。"
    fi
    if [[ $FORCE_VERSION -eq 1 || $FORCE -eq 1 ]]; then
        warn "已指定 --force-version，继续以尽力而为的方式汉化；未匹配的字符串会保持英文。"
        return 0
    fi
    err "为避免破坏配置，已停止。确认风险后可加 --force-version 继续。"
    err "如果刚更新了 Caelestia，请等待翻译表更新，或先执行 status 查看详情。"
    exit 1
}

# ---------------------------------------------------------------------------
# commands
# ---------------------------------------------------------------------------
print_context() {
    info "Caelestia shell : $SHELL_DIR"
    info "翻译表          : $MAP_FILE"
    info "状态目录        : $DATA_DIR"
    if [[ "$INSTALLED_VERSION" != "unknown" ]]; then
        info "已安装版本      : $INSTALLED_VERSION"
    fi
}

cmd_install() {
    print_context
    mkdir -p "$DATA_DIR/reports"

    compat_gate || return 1

    local analysis="$DATA_DIR/reports/analyze.json"
    local applied="$DATA_DIR/reports/applied.json"

    if [[ $DRY_RUN -eq 1 ]]; then
        info "dry-run: 以下改动不会被写入磁盘。"
        run_py apply.py apply --root "$SHELL_DIR" --map "$MAP_FILE" --dry-run --diff || true
        info "dry-run 结束，未修改任何文件。"
        return 0
    fi

    local rc=0
    run_py apply.py analyze --root "$SHELL_DIR" --map "$MAP_FILE" --json "$analysis" --quiet || rc=$?
    [[ $rc -eq 0 ]] || die "分析失败（退出码 $rc）"

    local changed unmatched
    changed="$(report_field "$analysis" changed_files)"
    unmatched="$(report_field "$analysis" unmatched)"

    if [[ $STRICT -eq 1 && "$unmatched" != "0" ]]; then
        die "--strict 已启用：有 $unmatched 个字符串没有翻译，已停止且未修改任何文件。"
    fi

    if [[ "$changed" == "0" && "$unmatched" == "0" ]]; then
        ok "所有可翻译字符串都已经是最新状态，无需修改。"
        return 0
    fi

    if [[ ! -w "$SHELL_DIR" ]]; then
        if [[ ${EUID} -ne 0 && "$TARGET" == "system" ]]; then
            die "没有写入 $SHELL_DIR 的权限。系统目录需要 sudo：sudo $0 install --target system"
        fi
        die "没有写入 $SHELL_DIR 的权限。"
    fi

    info "备份将要修改的文件..."
    rc=0
    run_py state.py plan --data-dir "$DATA_DIR" --shell-dir "$SHELL_DIR" --analysis "$analysis" || rc=$?
    [[ $rc -eq 0 ]] || die "创建备份失败（退出码 $rc）"

    info "应用汉化..."
    rc=0
    run_py apply.py apply --root "$SHELL_DIR" --map "$MAP_FILE" --json "$applied" --quiet || rc=$?
    if [[ $rc -ne 0 ]]; then
        die "汉化应用失败（退出码 $rc），文件已由引擎回滚，未记录状态。"
    fi

    local applied_files sites
    applied_files="$(report_field "$applied" changed_files)"
    sites="$(report_field "$applied" applied)"

    rc=0
    run_py state.py commit \
        --data-dir "$DATA_DIR" --shell-dir "$SHELL_DIR" --applied "$applied" \
        --project-version "$PROJECT_VERSION" \
        --language "$(map_field language)" \
        --caelestia-shell "$(map_field caelestia_shell)" \
        --installed-version "$INSTALLED_VERSION" --quiet || rc=$?
    [[ $rc -eq 0 ]] || die "写入状态失败（退出码 $rc）"

    fix_ownership "$DATA_DIR"

    ok "汉化完成：更新 $applied_files 个文件、$sites 处字符串。"
    if [[ "$unmatched" != "0" ]]; then
        warn "有 $unmatched 个字符串在当前版本中没有对应翻译，它们会保持英文。"
        warn "这通常发生在 Caelestia 更新之后；可运行 status --verbose 查看，或等待翻译表更新。"
        info "重新加载 shell：caelestia shell -r"
        return 3
    fi
    info "重新加载 shell 即可看到中文界面：caelestia shell -r"
    return 0
}

cmd_uninstall() {
    print_context
    if [[ $DRY_RUN -eq 1 ]]; then
        info "dry-run: 以下恢复操作不会被执行。"
    fi
    local restore_json="$DATA_DIR/reports/restore.json"
    mkdir -p "$DATA_DIR/reports"
    local rc=0
    local args=(restore --data-dir "$DATA_DIR" --shell-dir "$SHELL_DIR" --json "$restore_json")
    if [[ $FORCE -eq 1 ]]; then
        args+=(--force)
    fi
    if [[ $DRY_RUN -eq 1 ]]; then
        args+=(--dry-run)
    fi
    run_py state.py "${args[@]}" || rc=$?

    if [[ $rc -eq 0 || $rc -eq 3 ]]; then
        local restored_count modified_count
        restored_count="$(json_count "$restore_json" restored)"
        modified_count="$(json_count "$restore_json" modified_skipped)"
        if [[ $REVERT_FROM_MAP -eq 1 ]]; then
            info "对没有备份的文件尝试按翻译表反向恢复..."
            run_py apply.py revert --root "$SHELL_DIR" --map "$MAP_FILE" --quiet || true
        elif [[ $rc -eq 3 ]]; then
            warn "有 $modified_count 个文件没有可靠备份或已被手动修改；加 --revert-from-map 可尝试按翻译表恢复，"
            warn "或加 --force 强制用最初备份覆盖。"
        fi
        if [[ $rc -eq 0 && "$restored_count" != "0" ]]; then
            ok "已恢复 $restored_count 个原始文件。重新加载 shell：caelestia shell -r"
        elif [[ $rc -eq 0 ]]; then
            info "没有需要恢复的文件。"
        fi
    else
        die "恢复失败（退出码 $rc），状态文件已保留，可重试。"
    fi
    fix_ownership "$DATA_DIR"
    return $rc
}

cmd_status() {
    local analysis="$DATA_DIR/reports/analyze.json"
    mkdir -p "$DATA_DIR/reports"
    print_context
    local rc=0
    run_py apply.py analyze --root "$SHELL_DIR" --map "$MAP_FILE" --json "$analysis" || rc=$?
    if [[ $rc -gt 1 ]]; then
        die "分析失败（退出码 $rc）"
    fi
    if [[ $VERBOSE -eq 1 ]]; then
        python3 - "$analysis" <<'PY'
import json, sys
data = json.load(open(sys.argv[1]))
print(f"  可翻译字符串: {data['totals']['sites']} 处，待汉化 {data['totals']['applied']} 处，"
      f"未匹配 {data['totals']['unmatched']} 处，动态 {data['totals']['dynamic']} 处")
PY
    fi
    run_py state.py status --data-dir "$DATA_DIR" --shell-dir "$SHELL_DIR" --analysis "$analysis" || rc=$?
    if [[ $rc -eq 3 ]]; then
        warn "部分文件与安装记录不一致（见上方列表）。"
    fi
    return $rc
}

cmd_verify() {
    cmd_status
}

cmd_update() {
    info "Caelestia 更新后重新应用汉化。"
    if [[ $FORCE_VERSION -eq 0 ]]; then
        FORCE_VERSION=1
        info "update 使用 --force-version：版本不同也继续，未匹配的字符串会保持英文。"
    fi
    cmd_install
}

# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------
main() {
    parse_args "$@"
    [[ -n "$COMMAND" ]] || COMMAND="help"

    case "$COMMAND" in
        help)
            usage
            return 0
            ;;
        version)
            printf '%s %s\n' "$PROJECT_VERSION" "$(basename "$0")"
            return 0
            ;;
    esac

    check_dependencies
    DATA_DIR="$(resolve_data_dir)"
    if [[ -z "$SHELL_DIR" ]]; then
        SHELL_DIR="$(resolve_shell_dir)"
    fi
    if [[ ! -f "$SHELL_DIR/shell.qml" ]]; then
        die "在 $SHELL_DIR 中找不到 shell.qml。请用 --shell-dir 指定正确的目录。"
    fi
    INSTALLED_VERSION="$(detect_version)"
    acquire_lock "$DATA_DIR"

    case "$COMMAND" in
        install) cmd_install ;;
        uninstall) cmd_uninstall ;;
        status) cmd_status ;;
        verify) cmd_verify ;;
        update) cmd_update ;;
        *) die "未知命令: $COMMAND" ;;
    esac
}

main "$@"
