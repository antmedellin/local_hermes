---
name: open-link-chromium
description: Use when opening links in a new tab in Chromium.
---

## Procedure
To open a link in a new tab in Chromium:

1. **Capture:** Call `computer_use(action='capture', app='Chromium', mode='som')`.
2. **New Tab:** Call `computer_use(action='key', keys='ctrl+t', delivery_mode='foreground')`.
3. **Type URL:** Call `computer_use(action='type', text='<link>\\n', delivery_mode='foreground')`.
4. **Wait:** Call `computer_use(action='wait', seconds=3)`.
5. **Verify:** Call `computer_use(action='capture', app='Chromium')`.
6. **Report:** Extract and report the `window_title` from the final capture.

## Constraints
- **Capture Mode:** Use `mode='som'` in the initial capture to ensure orientability.
- **Delivery Mode:** Always use `delivery_mode='foreground'` for `key` and `type` actions; `background_unavailable` errors occur on this surface for typing.
- **URL Submission:** The `\\n` at the end of the URL text is required to submit the URL without a separate Enter key press.
- **Retry Policy:** Do each step exactly once. If any step fails (e.g., a `background_unavailable` error or a tool failure), stop immediately and report the failure to the user.
- **Navigation Verification:** If the final window title is not the expected destination (e.g., it remains on the home/search page), report the navigation failure clearly to the user instead of retrying the same sequence automatically.