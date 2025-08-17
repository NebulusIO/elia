-- vmemo_rename.applescript
-- Best-effort GUI scripting to rename the topmost Voice Memos item.
-- Usage: osascript vmemo_rename.applescript "New Title"

on run argv
  if (count of argv) is 0 then
    display dialog "Usage: osascript vmemo_rename.applescript \"New Title\"" buttons {"OK"} default button "OK"
    return
  end if
  set newTitle to item 1 of argv

  tell application "Voice Memos" to activate
  delay 0.5

  tell application "System Events"
    if not (exists process "Voice Memos") then
      display dialog "Voice Memos not running." buttons {"OK"} default button "OK"
      return
    end if

    tell process "Voice Memos"
      set frontmost to true
      try
        -- Attempt to select first row in the left outline (All Recordings)
        -- UI hierarchies change often; this targets typical structure.
        tell window 1
          tell splitter group 1
            tell group 1
              tell scroll area 1
                tell outline 1
                  if (count of rows) is 0 then error "No recordings found."
                  select row 1
                end tell
              end tell
            end tell
          end tell
        end tell

        delay 0.1
        -- Start inline rename: Return often enters "edit title" on selection.
        key code 36
        delay 0.05
        -- Select all, type title, press Return
        keystroke "a" using {command down}
        keystroke newTitle
        key code 36
      on error errMsg number errNum
        display dialog "Rename failed: " & errMsg buttons {"OK"} default button "OK"
      end try
    end tell
  end tell
end run
