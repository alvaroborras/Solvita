# Dashboard Sidebar Scrollbar Design

Date: 2026-06-07
Topic: Make the dashboard right sidebar scrollbar obvious and directly draggable

## Goal

Improve the dashboard's right sidebar so users can scroll it with a clearly visible, directly draggable scrollbar instead of relying mainly on the mouse wheel.

This is a small usability fix, not a layout redesign.

## Current Problem

The right sidebar already uses `overflow-y: auto`, but the scrollbar is styled globally to be very thin and low-contrast.

As a result:

- the sidebar visually reads as if it has no draggable scrollbar
- users have to discover scrolling by wheel or touchpad
- long stage details and evidence lists feel harder to inspect than necessary

## Scope

### In Scope

- `dashboard/frontend` right sidebar scroll behavior and styling
- desktop browsers where a draggable scrollbar is expected
- preventing layout jitter when the scrollbar appears

### Out of Scope

- custom JavaScript scrollbar widgets
- changes to the main content pane scrollbar
- mobile-only custom scroll affordances
- broader dashboard visual redesign

## Design Summary

Use the browser's native scrollbar for the right sidebar, but make it visibly stronger and easier to grab.

The change should:

- apply only to the right sidebar scroll container
- increase scrollbar width on desktop
- increase thumb and track contrast
- keep native drag behavior
- reserve gutter space so content width does not shift when scrollbar visibility changes

## Recommended Approach

### 1. Keep native scrolling

Do not build a custom drag handle.

Rationale:

- native scrollbars already support drag, wheel, keyboard, accessibility settings, and browser behavior
- the requested change is small
- a custom scrollbar would add synchronization and pointer-handling complexity for little product value

### 2. Style only the sidebar scrollbar

The right sidebar should opt into a more visible scrollbar without changing the left/main pane.

Implementation intent:

- add a dedicated sidebar modifier/class if needed
- use `scrollbar-width` / `scrollbar-color` for Firefox
- use `::-webkit-scrollbar*` rules scoped to the sidebar for Chromium/WebKit
- keep the existing global thin scrollbar rules as the default elsewhere

### 3. Stabilize the sidebar gutter

Add `scrollbar-gutter: stable` to the sidebar scroll container.

Rationale:

- prevents text reflow when the scrollbar becomes visible
- makes the right edge feel consistent while switching between runs with short and long content

## Behavioral Requirements

### Desktop

On desktop widths, the right sidebar must expose a clearly visible vertical scrollbar whenever the content overflows.

The scrollbar must:

- be obviously visible against the sidebar background
- be wide enough to comfortably drag with a mouse
- react to hover with a stronger thumb color
- remain native so dragging behaves as the browser expects

### Narrow Layouts

When the layout collapses and the sidebar becomes a stacked section below the main panel, the same sidebar scrollbar styling may remain in effect, but no extra interaction model should be introduced.

This is still the same native scroll container, only in a different layout position.

## Affected Files

Primary expected touch points:

- `dashboard/frontend/src/components/Layout.tsx`
- `dashboard/frontend/src/styles/global.css`

Possible touch point if scoping needs to be clearer:

- `dashboard/frontend/src/styles/theme.css`

No backend changes are required.

## Testing Strategy

### Automated

Add or update a focused frontend test that proves the sidebar keeps the expected scroll container class/structure after the change.

The test does not need to verify browser rendering of the scrollbar itself, but it should protect the DOM hook used for the styling.

### Manual

Verify in the running dashboard that:

1. the right sidebar shows a clearly visible scrollbar when content is tall
2. the scrollbar can be dragged directly with the mouse
3. the main content area appearance is unchanged
4. switching between short and long sidebar content does not cause noticeable width jitter
5. the stacked/mobile layout still scrolls normally

## Risks

### Browser Styling Differences

Scrollbar styling is not fully uniform across browsers.

Mitigation:

- rely on native scrollbar support
- use standards-based Firefox properties plus scoped WebKit pseudo-elements
- avoid pixel-perfect expectations in tests

### Over-styling

If the scrollbar is made too bright or too wide, it can visually dominate the sidebar.

Mitigation:

- keep the treatment stronger than the global default, but still aligned with the dashboard palette
- scope the change only to the sidebar

## Success Criteria

This change is complete when:

1. the dashboard right sidebar exposes an obvious draggable scrollbar for overflowing content
2. users can scroll the sidebar by dragging the scrollbar thumb directly
3. the rest of the page keeps its current scroll behavior
4. the change is covered by a focused frontend test plus manual verification
