#!/bin/bash
# Install the "Claude Plan Usage" widget into SwiftBar (or xbar).
# Safe to re-run. Does not touch your Claude login or credentials.
set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PLUGIN="claude-usage.5m.py"
SRC="$HERE/$PLUGIN"

if [ ! -f "$SRC" ]; then
  echo "✗ Can't find $PLUGIN next to this script." >&2
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
CFG_DIR="$HOME/.config/claude-usage-meter"
CFG="$CFG_DIR/config.json"
if [ ! -f "$CFG" ]; then
  mkdir -p "$CFG_DIR"
  cp "$HERE/config.example.json" "$CFG"
  echo "✓ Wrote starter config → $CFG"
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
