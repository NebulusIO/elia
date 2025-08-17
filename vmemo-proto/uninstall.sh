#!/usr/bin/env bash
set -euo pipefail

LAUNCH_AGENTS="$HOME/Library/LaunchAgents"
APP_SUPPORT="$HOME/Library/Application Support/vmemo"

launchctl unload "$LAUNCH_AGENTS/com.nabi.voicememos.agent.plist" &>/dev/null || true
rm -f "$LAUNCH_AGENTS/com.nabi.voicememos.agent.plist"

rm -rf "$APP_SUPPORT"

echo "✅ Uninstalled."
