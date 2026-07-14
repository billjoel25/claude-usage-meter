#!/bin/bash
# Uninstall the "Claude Plan Usage" widget.
#
#   bash uninstall.sh          remove the plugin + its cache (keeps your login)
#   bash uninstall.sh --all    also remove config + stored account tokens
#
# Optional: pass the plugin folder as an argument if auto-detect misses it.
set -uo pipefail

PLUGIN="claude-usage.5m.py"
APP_DIR="${CLAUDE_USAGE_METER_HOME:-$HOME/.config/claude-usage-meter}"

ALL=0
DEST_ARG=""
for a in "$@"; do
  case "$a" in
    --all) ALL=1 ;;
    *) DEST_ARG="$a" ;;
  esac
done

# --- find the plugin folder: arg > SwiftBar > xbar > default ---
DEST="$DEST_ARG"
if [ -z "$DEST" ] && command -v defaults >/dev/null 2>&1; then
  DEST="$(defaults read com.ameba.SwiftBar PluginDirectory 2>/dev/null || true)"
  [ -z "$DEST" ] && DEST="$(defaults read com.xbarapp.app PluginDirectory 2>/dev/null || true)"
fi
[ -z "$DEST" ] && DEST="$HOME/Library/Application Support/SwiftBar/Plugins"

if [ -f "$DEST/$PLUGIN" ]; then
  rm -f "$DEST/$PLUGIN" && echo "✓ Removed plugin → $DEST/$PLUGIN"
else
  echo "• No plugin found at $DEST/$PLUGIN (already removed, or a different folder)."
fi

if [ -d "$APP_DIR/cache" ]; then
  rm -rf "$APP_DIR/cache" && echo "✓ Cleared cache → $APP_DIR/cache"
fi

if [ "$ALL" -eq 1 ]; then
  if [ -d "$APP_DIR" ]; then
    rm -rf "$APP_DIR" && echo "✓ Removed config + account tokens → $APP_DIR"
  fi
else
  echo "• Kept your login + config in $APP_DIR (run with --all to remove them)."
fi

echo
echo "Done. If SwiftBar still shows the widget, click SwiftBar → Refresh All"
echo "(or quit and reopen SwiftBar)."
