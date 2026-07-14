#!/bin/bash
# Install the "Claude Plan Usage" widget into SwiftBar (or xbar).
#
# Two ways to run it:
#   • From a clone:  bash install.sh
#   • Standalone:    curl -fsSL https://raw.githubusercontent.com/billjoel25/claude-usage-meter/main/install.sh | bash
#
# Optional first argument: the SwiftBar/xbar plugin folder to install into.
# Safe to re-run. Does not touch your Claude login or credentials.
set -uo pipefail

REPO="${CUM_REPO:-billjoel25/claude-usage-meter}"
REF="${CUM_REF:-main}"
RAW="${CUM_RAW_BASE:-https://raw.githubusercontent.com/$REPO/$REF}"
PLUGIN="claude-usage.5m.py"
CONFIG_EXAMPLE="config.example.json"

# Where this script lives, if it's on disk. Empty when piped from curl, which is
# how we tell "running from a clone" (use sibling files) from "standalone" (download).
SELF="${BASH_SOURCE[0]:-}"
HERE=""
if [ -n "$SELF" ] && [ -f "$SELF" ]; then
  HERE="$(cd "$(dirname "$SELF")" && pwd)"
fi

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

# fetch <url> <dest> — download with curl or wget; fail on HTTP error or empty file.
fetch() {
  local url="$1" dest="$2"
  if command -v curl >/dev/null 2>&1; then
    curl -fsSL "$url" -o "$dest" || return 1
  elif command -v wget >/dev/null 2>&1; then
    wget -qO "$dest" "$url" || return 1
  else
    echo "✗ Need curl or wget to download files." >&2
    return 1
  fi
  [ -s "$dest" ]
}

# resolve <filename> — print a path to the file, preferring a local copy (clone),
# else downloading it from the repo (standalone). Returns non-zero on failure.
resolve() {
  local name="$1"
  if [ -n "$HERE" ] && [ -f "$HERE/$name" ]; then
    printf '%s' "$HERE/$name"; return 0
  fi
  if fetch "$RAW/$name" "$TMP/$name"; then
    printf '%s' "$TMP/$name"; return 0
  fi
  echo "✗ Couldn't download $name from $RAW/$name" >&2
  echo "  Check your network, or clone the repo and run: bash install.sh" >&2
  return 1
}

SRC="$(resolve "$PLUGIN")" || exit 1
# Guard against a 404/HTML error page masquerading as the plugin.
if ! head -n1 "$SRC" | grep -q "python3"; then
  echo "✗ Downloaded $PLUGIN doesn't look like the plugin (an error page?)." >&2
  exit 1
fi

# --- find the plugin folder: arg > SwiftBar > xbar > sane default ---
DEST=""
if [ "${1:-}" != "" ]; then
  DEST="$1"
elif command -v defaults >/dev/null 2>&1; then
  DEST="$(defaults read com.ameba.SwiftBar PluginDirectory 2>/dev/null || true)"
  [ -z "$DEST" ] && DEST="$(defaults read com.xbarapp.app PluginDirectory 2>/dev/null || true)"
fi
if [ -z "$DEST" ]; then
  DEST="$HOME/Library/Application Support/SwiftBar/Plugins"
  echo "• No SwiftBar/xbar plugin folder configured yet — defaulting to:"
  echo "    $DEST"
  echo "  (In SwiftBar, set this same folder under Preferences → Plugin Folder.)"
fi

if ! mkdir -p "$DEST" || ! cp "$SRC" "$DEST/$PLUGIN"; then
  echo "✗ Couldn't install the plugin into: $DEST" >&2
  echo "  Check the folder exists and is writable, then re-run." >&2
  exit 1
fi
chmod +x "$DEST/$PLUGIN"
echo "✓ Installed widget → $DEST/$PLUGIN"

# --- seed an editable config the first time ---
CFG_DIR="${CLAUDE_USAGE_METER_HOME:-$HOME/.config/claude-usage-meter}"
CFG="$CFG_DIR/config.json"
if [ ! -f "$CFG" ]; then
  if CFG_SRC="$(resolve "$CONFIG_EXAMPLE")"; then
    mkdir -p "$CFG_DIR"
    cp "$CFG_SRC" "$CFG"
    echo "✓ Wrote starter config → $CFG"
  else
    echo "• Skipped starter config (couldn't fetch $CONFIG_EXAMPLE); the widget still works."
  fi
else
  echo "• Kept existing config → $CFG"
fi

echo
echo "Next:"
echo "  1. Install SwiftBar if needed:   brew install --cask swiftbar"
echo "  2. Point SwiftBar's Plugin Folder at:  $DEST"
echo "  3. The widget appears within ~5 min (or SwiftBar → Refresh)."
echo "  4. Click the Claude icon in the menu bar → '➕ Add Claude account' and sign in."
echo "     (It also auto-detects an existing Claude Code login.)"
