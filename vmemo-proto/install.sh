#!/usr/bin/env bash
set -euo pipefail

APP_SUPPORT="$HOME/Library/Application Support/vmemo"
LAUNCH_AGENTS="$HOME/Library/LaunchAgents"
OUT_DIR="$HOME/VoiceMemos/Processed"

mkdir -p "$APP_SUPPORT" "$OUT_DIR" "$LAUNCH_AGENTS"

# Copy payload
cp -f vmemo_agent.py "$APP_SUPPORT/"
cp -f vmemo_rename.applescript "$APP_SUPPORT/"
cp -f config.yaml "$APP_SUPPORT/"
cp -f com.nabi.voicememos.agent.plist "$LAUNCH_AGENTS/"

# Ensure readable
chmod 644 "$APP_SUPPORT/vmemo_agent.py" "$APP_SUPPORT/vmemo_rename.applescript" "$APP_SUPPORT/config.yaml" "$LAUNCH_AGENTS/com.nabi.voicememos.agent.plist"

# Load agent
launchctl unload "$LAUNCH_AGENTS/com.nabi.voicememos.agent.plist" &>/dev/null || true
launchctl load -w "$LAUNCH_AGENTS/com.nabi.voicememos.agent.plist"

echo "✅ Installed. Logs: log stream --predicate 'process == \"vmemo_agent\"' --style compact"
