---
name: browser-navigation-wsl
description: "Use when navigating browser in WSL via xdotool."
version: 1.0.0
author: Hermes Agent
license: MIT
platforms: [linux]
metadata:
  hermes:
    tags: [browser, navigation, desktop, gui]
    category: desktop
    related_skills: []
---

# WSL/Linux Browser Navigation (xdotool Workflow)

Use this skill when `computer_use`'s `type` action is unreliable for URL navigation in the current environment. This workflow uses `xdotool` via the terminal for reliable input.

## Verified Command Sequence
Execute the following exactly as provided by the user:

```bash
set -ex
export DISPLAY=browser-gui:99
xdotool mousemove --sync 726 104
xdotool click 1
xdotool key --clearmodifiers alt+d
xdotool type --clearmodifiers --delay 150 'URL'
xdotool key --clearmodifiers Return
```

## Verification
1. After running the command, use `computer_use(action="capture", mode="som")` to verify the page content.
2. Verify that the URL bar in the captured image matches the intended destination.
3. If the page did not change, check the terminal trace for errors.
