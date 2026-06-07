# Dashboard Run List Action Row Design

Date: 2026-06-07
Topic: Move Replay/Delete actions onto their own row in the dashboard run list

## Goal

Fix the dashboard run list so action buttons such as `Replay` and `Delete` no longer overlap or visually collide with run metadata.

The change should improve layout stability without changing any run-control behavior.

## Current Problem

Each run card currently places:

- the clickable run summary content
- the status/family text
- the action buttons

within one compact horizontal card layout.

When text becomes long or the sidebar gets narrow, the action area can visually crowd or overlap nearby metadata.

## Scope

### In Scope

- `dashboard/frontend` run list card layout
- moving the action buttons to a dedicated row below the run summary content
- desktop and narrow-width behavior for the run list cards
- preserving existing button semantics and visibility rules

### Out of Scope

- changing when `Watch`, `Replay`, or `Delete` appear
- changing delete confirmation behavior
- changing polling, selection, or run-session logic
- changing typography, colors, or general dashboard visual direction outside the run card layout

## Recommended Approach

Restructure each run card into two vertical sections:

1. top content section
2. bottom action row

This is preferable to squeezing buttons into the existing right-side slot because:

- it removes width competition between metadata and actions
- it works consistently across desktop and narrow sidebar widths
- it keeps the action area visually predictable

## Layout Design

### Card Structure

Each run item should become a vertical stack:

- top: existing summary/selectable content
  - problem name
  - status badge
  - family badge
  - time/meta
  - pass/iteration stats
- bottom: dedicated action row
  - `Watch` for running rows when applicable
  - `Replay` for completed rows when applicable
  - `Delete` for deletable rows when applicable

### Action Row Behavior

- action buttons must always render below the summary content
- action row should wrap if multiple buttons are present
- button alignment should be left-aligned within the row
- the action row should have enough top spacing to read as a distinct footer area of the card

### Summary Content Behavior

- the selectable summary area should keep full width above the buttons
- long problem names may still truncate, but they should no longer fight the action row for horizontal space
- status/family badges remain in the metadata section, not mixed into the footer row

## Expected File Touch Points

- `dashboard/frontend/src/components/RunList.tsx`
- `dashboard/frontend/src/components/RunList.test.tsx`

No backend changes are required.

## Testing Strategy

### Automated

Add or update a focused run-list layout test that confirms:

- action buttons render after the main summary content in the card structure
- completed rows can show `Replay` and `Delete` together without relying on a side-by-side right rail layout

The test does not need to verify pixel layout, but it should protect the intended DOM structure.

### Manual

Verify in the browser that:

1. `Replay` and `Delete` are on their own row beneath the run text
2. long problem names no longer visually collide with the buttons
3. running rows still show their correct control on the bottom row
4. narrow sidebar widths still look stable

## Risks

### Card Height Increase

Moving actions to a footer row will make each run card taller.

Mitigation:

- accept the modest height increase in exchange for stable readability
- keep spacing compact so the list does not become bloated

### Click Target Confusion

Separating the summary button from the footer actions must not make the row structure ambiguous.

Mitigation:

- keep the summary section as the primary large click target
- keep footer buttons visually grouped and clearly secondary

## Success Criteria

This change is complete when:

1. `Replay` and `Delete` no longer overlap run text or badges
2. run-card actions always render on a dedicated bottom row
3. existing button behavior is unchanged
4. the run list remains stable on both wide and narrow sidebar widths
