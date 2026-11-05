# Browser Automation Workflows (computer_use tool)

Use `computer_use` for desktop automation: screenshots, clicks, typing, drag/scroll. The tool runs on WSL/Windows/macOS via a driver layer — it doesn't control the terminal or execute code directly.

## Core Workflow

```bash
# 1. Capture current window (SOM = Shareable Object Model)
computer_use(action="capture", mode="som")

# 2. Click an element at [x, y] or by index
computer_use(action="click", coordinate=[350, 330], capture_after=true)

# 3. For text input:
computer_use(action="type", text="Hello World", capture_after=true)

# 4. Verify state changed:
computer_use(action="capture", mode="vision")
```

### Coordinate vs Element Index

- **Preferred:** Use SOM (Shareable Object Model) element indices when available — they're stable across window moves/scales. The capture output lists interactable elements with indices (#0, #1, …).
- **Fallback:** When no element index exists, use pixel coordinates `[x, y]` relative to the captured window. These are screen-relative and work for fixed-position elements.

### WSL/Chromium-Specific Patterns

**Google Scholar author profile navigation:**

```bash
# Capture SOM overlay first
computer_use(action="capture", mode="som")

# Parse output for element indices:
# "#0 window '...' @ bounds-unknown"

# If the target link is visible but unresponsive to clicks in background mode:
computer_use(action="click", coordinate=[target_x, target_y], capture_after=true)

# If still no response, try foreground delivery (requires approval):
computer_use(action="click", coordinate=[x, y], delivery_mode="foreground")
```

**Key verdict patterns:**

- `verify_fresh_state` — Input was delivered but effect isn't confirmed. **Re-capture immediately before any retry.** Do not assume the click worked; check the fresh capture for visual confirmation or updated DOM state.
- `screen_unchanged=true` — State did not change after the action. The tool is working correctly; either the target isn't interactive, the coordinates are wrong, or a JavaScript blocker prevents interaction.

**Background mode limitations:**

In `delivery_mode="background"` (default), input is routed globally without raising the window. Many modern web apps (especially Chromium's) intercept clicks at the app level and ignore background-routed events for non-native elements. Use:
- **Foreground mode** when a verdict explicitly says to escalate there (`deliver...`).
- **Element indices** instead of coordinates when possible (they route via the driver's internal dispatch, not raw OS mouse).

## Decision Table

| Goal | Recommended Action |
|------|-------------------|
| Initial window inspection | `capture(mode="som")` — get both image + element tree |
| Clicking a visible link/button | Use SOM index if available; else approximate coordinates |
| Click failed, verdict says "verify_fresh_state" | Re-capture immediately before retrying |
| Need to type text into a field | `computer_use(action="type", text="...", capture_after=true)` — waits for input event, captures result |
| Scroll long page | `scroll(direction="down", amount=10)` — wheel ticks |
| Drag element from A to B | Use `from_element`/`to_element` indices if available; else `from_coordinate`/`to_coordinate` |
| Need to handle modals/popups | Capture after action, parse SOM tree for new elements, click the matching index |
| Background mode clicks don't work on web app | Switch to `delivery_mode="foreground"` (or use element indices) |

## Pitfalls & Lessons

- **Never assume background-routed clicks hit web-rendered links** — Chromium/WebView apps intercept at their own level. Use foreground mode for interactive web content when verdicts suggest escalation.
- **"verify_fresh_state" ≠ failure** — it's a pattern to re-verify state. The action may have worked but the agent must confirm via fresh capture.
- **Coordinate clicks are fragile** — window moves/scale changes break them. Prefer SOM indices when available.
- **`capture_after=true` captures automatically** — saves a round-trip; use it for any input action (click, type, key).
- **Don't repeat failed clicks** — if one click doesn't navigate, don't spam the same coordinates. Re-capture to verify state or switch to element indexing.

## Tool Parameters Summary

```json
{
  "action": ["capture", "click", "type", "key", "scroll", "drag", ...],
  "mode": ["som", "vision", "ax"],       // som = screenshot + numbered overlays + AX tree (preferred)
  "coordinate": [x, y],                  // for clicks when no element index available
  "element": 0,                         // SOM index (preferred over coordinates)
  "capture_after": true,                 // auto-capture after input action
  "delivery_mode": ["background", "foreground"], // background = default, no focus steal; foreground = brief window raise
  "buttons": ["left", "right", "middle"]
}
```

**Capture modes:**

- `mode="som"` — screenshot with numbered clickable overlays + accessibility tree. Best for automation workflows. Returns interactable elements with indices.
- `mode="vision"` — plain screenshot, no element indices. Use when the model needs to inspect the screen visually (e.g., verify colors/images).
- `mode="ax"` — accessibility tree only, no image. For text-only models or when coordinates/indices are already known.
