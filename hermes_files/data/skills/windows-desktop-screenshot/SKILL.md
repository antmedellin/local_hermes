---
version: 0.1
author: Hermes Agent
license: MIT
tags:
screenshot
wsl
xdotool
pyautogui
related_skills:
devops/sdlc-review
description: Capture WSL/Windows screenshots via xdotool or pyautogui.
category: computer-use
name: windows-desktop-screenshot
---
# Windows/WSL Desktop Screenshot Capture

## When to Use

Capturing screenshots from a WSL browser-gui session or Windows host where direct Python capture libraries fail due to display constraints.

## Procedure

1. **Attempt `xdotool screenshot`** (if available):
   ```bash
   xdotool screenshot -o /opt/data/cache/scratch/desktop.png
   ```

2. **Fallback: Install `pyautogui`** (requires working pip):
   ```bash
   .venv/bin/python3 -m pip install pyautogui -q && \
   python3 -c "from pyautogui import screenshot; img = screenshot(); img.save('/opt/data/cache/scratch/desktop.png')"
   ```

3. **Fallback: Manual capture** if all tools unavailable:
   - Ask user to use `Win+Shift+S` (Snipping Tool) or `Print Screen` key.
   - User pastes image → use `kanban_attach_url` with the hosted URL, or state local path to attach via `kanban_attach`.

## Pitfalls

- **WSL without X11 forwarding**: Python's `pyscreenshot`, `mss`, and `tkinter` all fail (`_tkinter.TclError: no display`). Try alternative methods first.
- **Avoid `-c` flag Python invocations**: WSL terminal auto-approves scripts only; use `python3 -m pip` and full paths (`.venv/bin/python3`) to prevent "command not found" noise.
- **Verify output**: Always check that the saved file is a valid PNG (`PIL.Image.open`) before passing to `vision_analyze`.

## Tools and Files

- Output directory: `/opt/data/cache/scratch/`
