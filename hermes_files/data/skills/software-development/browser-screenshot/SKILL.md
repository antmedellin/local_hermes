---
name: browser-screenshot
description: "Capture a screenshot of a specific web page via Chromium."
version: 0.1.0
author: Hermes
platforms: [linux]
metadata:
  hermes:
    tags: [Browser, Screenshot, Automation]
---

# Browser Screenshot

This skill provides a reliable workflow for capturing high-quality screenshots of web pages using a headless-capable Chromium instance. It ensures that existing browser profiles are not disrupted and that the environment is properly configured for X11 display.

## When to Use
- "take a screenshot of [URL]"
- "capture the profile of [Name] on Google Scholar"
- "get a screenshot of the login page"

## Prerequisites
- `chromium` or `google-chrome` installed.
- `computer_use` tool configured.
- Permissions to run `chromium` with `--no-sandbox`.

## How to Run
Execute via the `terminal` tool to launch the instance, then use `computer_use` to trigger the capture.

## Quick Reference
- Check Env: `echo $DISPLAY; echo $XAUTHORITY`
- Launch: `chromium --headless --remote-debugging-port=9222 --user-data-dir=/tmp/screenshot-profile --no-sandbox [URL]`
- Capture: `computer_use(action='capture')`

## Procedure
1. **Verify Environment**: Run `terminal(command="echo $DISPLAY; echo $XAUTHORITY")` to ensure the X server is accessible.
2. **Launch Chromium**: Use `terminal(command="chromium --remote-debugging-port=9222 --user-data-dir=/tmp/screenshot-profile --no-sandbox [URL]", background=True)` to open the page in a fresh profile.
3. **Wait for Load**: Allow 10-15 seconds for the page to stabilize.
4. **Capture**: Call `computer_use(action='capture', mode='vision')`.
5. **Verify**: Use `vision_analyze(image_url=screenshot_path)` to confirm the correct content is visible.

## Pitfalls
- **Sandbox Issues**: Use `--no-sandbox` if running in a container or restricted environment.
- **DBus Errors**: Ignore `dbus` or `accessibility bus` connection errors; they typically do not block the browser rendering.
- **Profile Conflicts**: Always use a unique `--user-data-dir` to avoid locking the main profile.

## Verification
- **Verification**: Verify the page content via `vision_analyze` or by checking the file path. If navigation failed despite a successful `terminal` exit code, re-verify the URL using `curl -I` before attempting a re-capture.
