---
name: browser-navigation
description: "Drive browser navigation via computer_use or xdotool."
version: 2.0.0
author: Hermes Agent
license: MIT
platforms: [macos, windows, linux]
metadata:
  hermes:
    tags: [browser, navigation, desktop, gui]
    category: desktop
    related_skills: []
---

# Browser Navigation (Desktop/GUI)

Use this skill when you need to navigate a browser window that is being driven via `computer_use` or direct OS-level interaction.

## Workflow (The Reliable Method)

1.  **Capture First:** Always start with a `computer_use(action="capture", mode="som", app="Chromium")` to map the window state.
2.  **Focus Address Bar:**
    *   **Reliable Method:** Click the address bar at explicit coordinates (e.g., `[525, 90]`).
    *   **Fallback:** Use `key(keys="ctrl+l")` in `foreground` mode. Note: Background delivery of hotkeys often fails in Chromium-based browsers.
3.  **Selection:** Send `key(keys="ctrl+a")` in `foreground` mode to ensure the entire existing URL is selected.
4.  **Input:** Type the URL in `foreground` mode.
5.  **Execution:** Send `key(keys="enter")` in `foreground` mode.
6.  **Verification:** Re-capture the window and verify the URL bar update and page content change.

## Link Clicking Procedure (WSL/DESKTOP Workflow)

When clicking a visible hyperlink (e.g., author profiles, external links):

1.  **Capture with SOM mode** to obtain element indices:
    ```bash
    computer_use(action="capture", mode="som")
    ```
2.  **Estimate Click Coordinates** from the captured image (center of target text/link):
    *   Use `vision` capture to inspect current state if needed.
3.  **Convert to Desktop Coordinates** using xdotool:
    ```bash
    export DISPLAY=browser-gui:99
    # Find Chromium window geometry
    xdotool search --name "Chromium" getwindowgeometry 2>/dev/null | grep -A1 "Window"
    # Calculate: desktop_x = capture_origin_x + window_x, same for y
4.  **Execute Click with xdotool:**
    ```bash
    export DISPLAY=browser-gui:99
    xdotool mousemove --sync X Y
    xdotool click 1
    ```
5.  **Verify Navigation** with a fresh `computer_use(action="capture", mode="vision")`:
    *   Check if screen changed (page navigated)
    *   If unchanged, adjust coordinates and retry once more

## Pitfalls

*   **Background Hotkeys:** Do not use background delivery for `ctrl+l` or `enter` in Chromium; the driver may return `ok: true`, but the browser will ignore the input. Use `delivery_mode="foreground"`.
*   **Address Bar Click:** If navigation fails with hotkeys, use a direct coordinate click on the address bar. This forces the browser's UI state to focus the input field.
*   **Synthetic Input Rejection:** If `xdotool` or `computer_use` type actions are "delivered" but the URL bar remains unchanged, the browser may be ignoring synthetic events. In these cases, use coordinate clicks for focus and verify the text programmatically if possible.
### WSL/DISPLAY Environment Notes

*   DISPLAY env var: On WSL, set `export DISPLAY=browser-gui:99` before xdotool commands.
*   Window origin offset: Use actual window geometry from `xdotool search --name "Chromium" getwindowgeometry`, not assumed (10,10) values.
*   Click coordinate precision: Links require center-point clicks; if first attempt fails, adjust by +/- 20-30 pixels in each axis and retry.
*   Verify via capture: Always re-capture after click attempts with `mode="vision"` to confirm page state changed before concluding automation failed.

## Verification Criteria

Navigation is only considered successful if:
1. The address bar visibly updates to the target URL.
2. The page content matches the target domain's primary content (e.g., the "Example Domain" page for `example.com`).
