#!/usr/bin/env bash
# @APP_NAME@ @VERSION@ — Linux installer (generated from template/install.sh and installer.conf)
# Installs with a single password prompt: required packages, one-time commands, the program to
# ~/.local/share and a menu entry. Run again: update or uninstall.
set -euo pipefail

TITLE="@APP_NAME@"
APP_ID="@APP_ID@"
VERSION="@VERSION@"
REPO="@REPO@"
LINUX_FILE="@LINUX_FILE@"
LINUX_RUN="@LINUX_RUN@"
ICON_PNG="@ICON_PNG@"
INSTALL_DIR="$HOME/.local/share/$APP_ID"
DESKTOP_FILE="$HOME/.local/share/applications/$APP_ID.desktop"
ICON_FILE="$HOME/.local/share/icons/hicolor/256x256/apps/$APP_ID.png"
RELEASE_URL="https://github.com/$REPO/releases/latest/download"

GUI=0
if command -v kdialog >/dev/null 2>&1 && [ -n "${DISPLAY:-}${WAYLAND_DISPLAY:-}" ]; then GUI=1
elif command -v zenity >/dev/null 2>&1 && [ -n "${DISPLAY:-}${WAYLAND_DISPLAY:-}" ]; then GUI=2; fi

# Without kdialog/zenity (e.g. a fresh system) there would be no windows and no password prompt:
# then reopen this script in a terminal, where everything is visible.
if [ "$GUI" = "0" ] && [ -n "${DISPLAY:-}${WAYLAND_DISPLAY:-}" ] && [ ! -t 0 ] && [ -z "${IN_TERMINAL:-}" ]; then
    SELF="$(readlink -f "$0")"
    export IN_TERMINAL=1
    for t in konsole gnome-terminal kgx ptyxis xfce4-terminal alacritty kitty foot wezterm xterm; do
        command -v "$t" >/dev/null 2>&1 || continue
        case "$t" in
            gnome-terminal|kgx|ptyxis) exec "$t" -- bash "$SELF" ;;
            xfce4-terminal) exec "$t" -x bash "$SELF" ;;
            kitty|foot) exec "$t" bash "$SELF" ;;
            wezterm) exec "$t" start -- bash "$SELF" ;;
            *) exec "$t" -e bash "$SELF" ;;
        esac
    done
fi
pause_in_terminal() { [ -n "${IN_TERMINAL:-}" ] && [ -t 0 ] && read -rp "Press Enter to close " _ || true; }

info() { case "$GUI" in 1) kdialog --title "$TITLE" --msgbox "$(printf '%b' "$1")" ;;
                        2) zenity --info --title="$TITLE" --text="$1" --width=380 ;; *) printf '%b\n' "$1" ;; esac; }
fail() { case "$GUI" in 1) kdialog --title "$TITLE" --error "$(printf '%b' "$1")" ;;
                        2) zenity --error --title="$TITLE" --text="$1" --width=380 ;; *) printf 'ERROR: %b\n' "$1" >&2 ;; esac
         pause_in_terminal; exit 1; }
as_root() { if [ ! -t 0 ] && command -v pkexec >/dev/null 2>&1; then pkexec /bin/sh -c "$1"; else sudo /bin/sh -c "$1"; fi; }

uninstall() {
    rm -rf "$INSTALL_DIR"
    rm -f "$DESKTOP_FILE" "$ICON_FILE"
    command -v update-desktop-database >/dev/null 2>&1 && update-desktop-database "$HOME/.local/share/applications" || true
    info "$TITLE has been removed."
    pause_in_terminal
    exit 0
}

# Already installed? Then update or uninstall
if [ -d "$INSTALL_DIR" ]; then
    Q="$TITLE is already installed."
    case "$GUI" in
        1) set +e; kdialog --title "$TITLE" --yesnocancel "$Q" --yes-label "Update" --no-label "Uninstall"; CHOICE=$?; set -e ;;
        2) set +e; OUT=$(zenity --question --title="$TITLE" --text="$Q" --ok-label="Update" \
                --cancel-label="Cancel" --extra-button="Uninstall"); RC=$?; set -e
           if [ "$OUT" = "Uninstall" ]; then CHOICE=1; elif [ "$RC" = 0 ]; then CHOICE=0; else CHOICE=2; fi ;;
        *) read -rp "$Q [u]pdate, [r]emove, [x] cancel: " A
           case "$A" in u|U) CHOICE=0 ;; r|R) CHOICE=1 ;; *) CHOICE=2 ;; esac ;;
    esac
    case "$CHOICE" in 0) ;; 1) uninstall ;; *) exit 0 ;; esac
fi

# 1) Packages and one-time commands – all in one step, one password
PKGS=""; HAVE=""; INSTALL=""
if command -v pacman >/dev/null 2>&1; then PKGS="@PKGS_ARCH@"; HAVE="pacman -Q"; INSTALL="pacman -S --needed --noconfirm"
elif command -v apt-get >/dev/null 2>&1; then PKGS="@PKGS_DEB@"; HAVE="dpkg -s"; INSTALL="env DEBIAN_FRONTEND=noninteractive apt-get install -y"
elif command -v dnf >/dev/null 2>&1; then PKGS="@PKGS_RPM@"; HAVE="rpm -q"; INSTALL="dnf install -y"
elif command -v zypper >/dev/null 2>&1; then PKGS="@PKGS_SUSE@"; HAVE="rpm -q"; INSTALL="zypper --non-interactive install"; fi
MISSING=""
for p in $PKGS; do $HAVE "$p" >/dev/null 2>&1 || MISSING="$MISSING $p"; done
ROOT_CMD=""
[ -n "$MISSING" ] && ROOT_CMD="$INSTALL$MISSING"
EXTRA='@ROOT_CMDS@'
[ -n "$EXTRA" ] && ROOT_CMD="${ROOT_CMD:+$ROOT_CMD && }$EXTRA"
if [ -n "$ROOT_CMD" ]; then
    MSG="To set up $TITLE:"
    [ -n "$MISSING" ] && MSG="$MSG\n\nPackages:$MISSING"
    [ -n "$EXTRA" ] && MSG="$MSG\n\nOne-time system settings"
    MSG="$MSG\n\nA window will ask for your password once."
    case "$GUI" in
        1) kdialog --title "$TITLE" --continuecancel "$(printf '%b' "$MSG")" || exit 0 ;;
        2) zenity --question --title="$TITLE" --text="$MSG" --width=420 || exit 0 ;;
        *) printf '%b\n' "$MSG" ;;
    esac
    as_root "$ROOT_CMD" || fail "Setup was cancelled or failed."
fi

# 2) Download the program
command -v curl >/dev/null 2>&1 || fail "curl is missing – it is needed to download the program."
TMP="$(mktemp)"; trap 'rm -f "$TMP"' EXIT
curl -fsSL --retry 2 -o "$TMP" "$RELEASE_URL/$LINUX_FILE" || fail "Download failed.\nIs there an internet connection?"
mkdir -p "$INSTALL_DIR"
cp -f "$TMP" "$INSTALL_DIR/$LINUX_FILE"
chmod 755 "$INSTALL_DIR/$LINUX_FILE"

# 3) Icon and menu entry
ICON=application-x-executable
if [ -n "$ICON_PNG" ]; then
    mkdir -p "$(dirname "$ICON_FILE")"
    curl -fsSL -o "$ICON_FILE" "https://raw.githubusercontent.com/$REPO/HEAD/$ICON_PNG" 2>/dev/null && ICON="$APP_ID" || rm -f "$ICON_FILE"
fi
if [ -n "$LINUX_RUN" ]; then EXEC="${LINUX_RUN//\{file\}/$INSTALL_DIR/$LINUX_FILE}"; else EXEC="$INSTALL_DIR/$LINUX_FILE"; fi
mkdir -p "$(dirname "$DESKTOP_FILE")"
cat > "$DESKTOP_FILE" << DESKTOP
[Desktop Entry]
Type=Application
Name=$TITLE
Comment=@APP_COMMENT@
Exec=$EXEC
Icon=$ICON
Categories=Utility;
X-AppVersion=$VERSION
DESKTOP
command -v update-desktop-database >/dev/null 2>&1 && update-desktop-database "$HOME/.local/share/applications" || true

info "$TITLE $VERSION has been installed!\n\nStart it from the application menu: $TITLE"
pause_in_terminal
