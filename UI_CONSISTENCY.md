# CommStat UI Consistency Tracker

Read this at the start of every UI consistency session to know exactly where we are.

**Last updated:** 2026-04-24  
**Session:** 3

---

## Standards Checklist Key

| # | Standard |
|---|----------|
| 1 | **COLORS** — reads from `DEFAULT_COLORS` in `constants.py` (no hardcoded hex) |
| 2 | **TITLE** — Roboto Slab Black 16px, first widget in layout, `program_background`/`program_foreground`, `setFixedHeight(36)`, 9px top/bottom padding |
| 3 | **PANEL** — dialog background set to `data_background` (per reference impl js8mail.py) |
| 4 | **LABELS** — Roboto Bold 13px, end with ":" |
| 5 | **DATA FONT** — Kode Mono 13px for all input fields (and any DB/API data displays) |
| 6 | **BUTTONS** — Roboto Bold 15px, `:hover` + `:pressed` states, action words (Save/Cancel/Close/Add/Update/Remove) |
| 7 | **INPUTS** — white bg, `#333333` text, `1px solid #cccccc` border, `border-radius: 4px` |
| 8 | **LAYOUT** — `QVBoxLayout(self)`, `setContentsMargins(15,15,15,15)`, `setSpacing(10)`, `addStretch()` before buttons |
| 9 | **TABLE** — `_TITLE_BG/_TITLE_FG` headers, `_DATA_BG/_DATA_FG` rows, Kode Mono cells, Roboto Bold headers, selected: `#cce5ff`/`#000000` (only if module has QTableWidget) |
| 10 | **WINDOW** — `radiation-32.png` icon (with `os.path.exists` check), standard window flags, `setFixedSize` or `setMinimumSize` |

---

## Module Status

`✅` = done · `⬜` = not yet · `N/A` = not applicable

| Module | Lines | 1 COLORS | 2 TITLE | 3 PANEL | 4 LABELS | 5 DATA FONT | 6 BUTTONS | 7 INPUTS | 8 LAYOUT | 9 TABLE | 10 WINDOW | Done? |
|--------|-------|----------|---------|---------|----------|-------------|-----------|----------|----------|---------|-----------|-------|
| `filter.py` | 130 | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | N/A | ✅ | ✅ **Session 1** |
| `groups.py` | 304 | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | N/A | ✅ | ✅ **Session 1** |
| `direct_message.py` | 367 | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | N/A | ✅ | ✅ **Session 2** |
| `view_statrep.py` | 480 | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ **Session 2** |
| `gridfinder.py` | 350 | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ **Session 2** |
| `alert.py` | 905 | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | N/A | ✅ | ✅ **Session 2** |
| `message.py` | 847 | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | N/A | ✅ | ✅ **Session 3** |
| `qrz_lookup.py` | 1,447 | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ **Session 3** |
| `statrep.py` | 1,445 | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ | N/A | ⬜ | ⬜ **Next up** |
| `js8_connectors.py` | 500 | ✅ | ⬜ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ⬜ **After statrep** |
| `js8mail.py` | 477 | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | N/A | ✅ | ✅ |
| `js8sms.py` | 479 | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | N/A | ✅ | ✅ |

---

## Reference Implementations

- **`js8mail.py`** — canonical reference: title pattern, dialog stylesheet, label/input/button patterns
- **`js8_connectors.py`** — best pattern for QTableWidget styling and helper functions
- **`direct_message.py`** — designated title placement reference per CLAUDE.md (needs update first)

## Session Log

| Session | Date | Modules Completed |
|---------|------|-------------------|
| 1 | 2026-04-24 | `filter.py`, `groups.py` |
| 2 | 2026-04-24 | `direct_message.py`, `view_statrep.py`, `gridfinder.py`, `alert.py` |
| 3 | 2026-04-24 | `message.py`, `qrz_lookup.py` |

---

## How to Start the Next Session

Tell Claude: **"continue UI consistency work"**

Claude will:
1. Read this file to find the next `⬜ **Next up**` module
2. Read that module fully
3. Apply all 10 standards
4. Update this file
5. Commit both files together
