# vmemo-proto (Voice Memos → Transcribe → Rename → Export)

A lightweight, local-first prototype that **detects new Apple Voice Memos on macOS**, pulls the **built‑in transcript** (if present), falls back to **Whisper.cpp** if missing, **generates a clean title**, and **exports a renamed copy** with the transcript next to it.

**Why copy instead of renaming inside the app?** Voice Memos tracks recordings via internal IDs and a database. Renaming files in the app container can cause link breakage. This tool **keeps the app’s library intact** and creates a **clean, portable export** for your automations. (Optional: a best‑effort AppleScript can also try to rename the item in the app UI — off by default.)

## What you get
- ✅ Watches the iCloud‑synced Voice Memos folder
- ✅ Extracts Apple’s transcript from the M4A (`trsp` atom) when available
- ✅ If no transcript is found, **optionally** runs Whisper.cpp (if installed) to transcribe locally
- ✅ Generates a slugified, short title (configurable) and exports:
  - `/root/VoiceMemos/Processed/YYYY-MM-DD/<title>.m4a`
  - `/root/VoiceMemos/Processed/YYYY-MM-DD/<title>.txt` (plain transcript)
  - `/root/VoiceMemos/Processed/YYYY-MM-DD/<title>.json` (metadata)
- ✅ LaunchAgent so it runs at login
- ✅ MCP snippet for Claude Desktop to add an AppleScript server (for optional UI automation)
- ✅ Zero Python deps (standard library only)

## Requirements
- macOS with Voice Memos syncing via iCloud (default)
- Python 3.10+ (preinstalled on recent macOS)
- (Optional) **Whisper.cpp** via Homebrew for on-device fallback transcription
  ```bash
  brew install whisper-cpp ffmpeg
  # download a model, e.g. base
  curl -L -o ~/Library/Application\ Support/vmemo/models/ggml-base.en.bin \
       https://ggml.ggerganov.com/ggml-model-whisper-base.en-q5_1.bin
  ```

## Install
```bash
chmod +x ./install.sh
./install.sh
```

This will:
- put files under `~/Library/Application Support/vmemo`
- create `~/VoiceMemos/Processed` if needed
- load the LaunchAgent so it starts watching immediately

## Uninstall
```bash
./uninstall.sh
```

## Configuration: `config.yaml`
```yaml
recordings_dir: "~/Library/Group Containers/group.com.apple.VoiceMemos.shared/Recordings"
out_dir: "~/VoiceMemos/Processed"
rename_in_app: false                 # try to rename inside Voice Memos UI (fragile)
title_words: 8                       # max words in generated title
whispercpp_path: "whisper-cpp"       # CLI name or absolute path
whisper_model: "~/Library/Application Support/vmemo/models/ggml-base.en.bin"
language: "en"
```

## MCP (Claude Desktop) – optional AppleScript control
Add an AppleScript MCP server so Claude can run small AppleScripts like “rename latest Voice Memo to X”. Put this snippet in your Claude client MCP config (see docs):

```json
{
  "mcpServers": {
    "applescript_execute": {
      "command": "npx",
      "args": ["@peakmojo/applescript-mcp@latest"]
    }
  }
}
```

Then you can ask Claude to run AppleScript like:
> rename latest voice memo to “Standup Sync – blockers”

(You may still need to grant **Accessibility** permissions for automation to control Voice Memos.)

## Notes & caveats
- Voice Memos’ internal library is not officially scriptable and can change. This tool purposely **does not** mutate the library. It **exports clean copies** for downstream workflows.
- The included AppleScript (`vmemo_rename.applescript`) tries to rename the topmost item in the Voice Memos list — it works on many setups but is **brittle** across OS updates. Keep it off unless you need it.
- You can run the agent manually: `python3 vmemo_agent.py --once` to process pending items once and exit.
