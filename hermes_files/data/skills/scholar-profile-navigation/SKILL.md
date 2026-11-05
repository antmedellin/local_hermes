---
name: scholar-profile-navigation
description: "Navigate Google Scholar profiles for academic research."
version: 1.0.0
author: Hermes Agent
platforms: [linux]
metadata:
  hermes:
    tags: [Browser, Google Scholar, Academic Profiles, Citation Analysis]
---

# Google Scholar Profile Navigation

## Overview

This skill provides a reliable workflow for locating and analyzing academic author profiles on Google Scholar.

## When to Use
- "locate Hiram Moya's Google Scholar profile"
- "find top-cited papers for [Author Name]"
- "navigate scholar.google.com/citations?user=[USER_ID]"

## Procedure

### 1. Initial Profile Search

1. **Search for the author**: Navigate to `scholar.google.com/scholar?q=[author name]`
2. **Locate profile section**: Find the "User profiles" section in results
3. **Click profile link**: Click the blue author name link under the profile header

### 2. Profile Verification

Once on the profile page, verify by checking:
- Author photo (usually circular avatar)
- Display name and affiliation text
- "Cited by" total count in sidebar

### 3. Identify Most-Cited Paper

1. **Check papers list**: Papers appear sorted by citation count (highest first)
2. **Read top entry**: Extract from the first visible paper row:
   - **Title**: Full blue hyperlink text under "TITLE" column
   - **Citation count**: Number displayed in "CITED BY" column
   - **Authors**: Listed below title in smaller gray text
   - **Journal**: Publication venue and year
3. **Report findings**:
   ```
   Title: [full paper title]
   Citation count: [number]
   Link: [blue hyperlink to PDF/source]
   Journal: [publication info]
   Year: [publication year]
   ```

### 4. Direct Profile URL (if known)

If you have the Scholar ID:
- Navigate to `scholar.google.com/citations?user=[USER_ID]`
- Example: `scholar.google.com/citations?user=j4Pwmh8AAAAJ`

## Tools Reference

| Tool | Purpose |
|------|---------|
| `computer_use(action='capture')` | Screenshot current page state |
| `computer_use(action='click', coordinate=[x,y])` | Click profile/link at coordinates |
| `terminal(command="DISPLAY=... python3 ...")` | Capture desktop via PIL |
| `xdotool mousemove --sync X Y && xdotool click 1` | Terminal-based clicking |

## Pitfalls

- **Malformed URLs**: If URL contains parameters like "sleep0.5keyalt+d", it indicates a failed previous navigation attempt. Clear the address bar (Ctrl+A, select all text) and type fresh.
- **Computer_use vs xdotool**: In Docker environments, `computer_use` clicks may not navigate reliably. Use `DISPLAY=browser-gui:99 xdotool mousemove --sync X Y && xdotool click 1` as fallback.
- **Command Success != State Change**: `xdotool` commands may return exit code 0 even if the browser fails to process the input (e.g., focus issues or incorrect coordinates). Always capture and verify the URL and page content after a navigation command.

## Quick Reference

### Navigate to profile
```
terminal(command="xdotool type 'scholar.google.com/citations?user=[USER_ID]' && xdotool key Enter")
```

### Capture page state
```
computer_use(action='capture', mode='vision')
```

### Click profile link
```
computer_use(action='click', coordinate=[estimated_x, estimated_y], delivery_mode='foreground')
```

## Example Output Format

**Hiram Moya's Most-Cited Paper:**
- **Title**: `Blockchain technology-enabled supply chain systems and supply chain performance: a resource-based view`
- **Displayed citation count**: 378 citations
- **Link**: Blue hyperlink at top of papers list (first result)
- **Journal**: Supply Chain Management: An International Journal 25 (6), 841-862
- **Year**: 2020
