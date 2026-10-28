---
name: open-link-chromium
description: Use when opening links in a new tab in Chromium.
---

## Procedure
To open a link in a new tab in Chromium:

1. **Capture:** Call `computer_use(action='capture', app='Chromium')`.
2. **New Tab:** Call `computer_use(action='key', keys='ctrl+t', delivery_mode='foreground')`.
3. **Type URL:** Call `computer_use(action='type', text='<link>\n', delivery_mode='foreground')`.
4. **Wait:** Call `computer_use(action='wait', seconds=3)`.
5. **Verify:** Call `computer_use(action='capture', app='Chromium')`.
6. **Report:** Extract and report the `window_title` from the final capture.

## Constraints
- **Delivery Mode:** Always use `delivery_mode='foreground'`. Never use background delivery for this task.
- **Retry Policy:** Do each step exactly once. If any step fails, stop immediately and report the failure to the user.