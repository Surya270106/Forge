---
name: Forge
description: Editorial engineering workspace for reviewed code changes
colors:
  paper: "#f3f6fa"
  ink: "#061a36"
  muted: "#58708f"
  cobalt: "#075bea"
  cobalt-deep: "#063fae"
  navy: "#041d49"
  line: "#cbdcf2"
typography:
  display:
    fontFamily: "Inter, Arial, sans-serif"
    fontWeight: 480
    lineHeight: 0.95
  body:
    fontFamily: "Inter, Arial, sans-serif"
    fontSize: "16px"
    lineHeight: 1.6
rounded:
  control: "12px"
  panel: "24px"
spacing:
  gutter: "clamp(20px, 3.2vw, 52px)"
components:
  button-primary:
    backgroundColor: "{colors.cobalt}"
    textColor: "{colors.paper}"
    rounded: "{rounded.control}"
---

## Overview

Forge uses calm, light engineering surfaces with navy text and a single cobalt action color. Its oversized editorial lettering and blue wireframe motif identify the product. Signed-in work surfaces use the motif quietly so code, state, and actions remain primary.

## Colors

Paper grounds reading surfaces. Cobalt marks primary actions and active state. Navy provides depth for execution logs and selected editorial sections. Success and failure colors are reserved for actual results, with text labels alongside color.

## Typography

Inter carries both display and body text; code, hashes, paths, and log output use the existing monospace stack. The signed-in dashboard and task workspace use a smaller title scale than the marketing page to keep useful data in the first viewport.

## Layout

The shared horizontal navigation and page gutter remain. Engineering screens place the next action and current state above supporting detail. Data ledgers align status and timestamps. At narrow widths, columns stack and code panels scroll within their own bounds.

## Elevation & Depth

Prefer tone changes and existing fine dividers for stable content. Reserve shadows for floating navigation or dialogs. Avoid persistent blur behind logs and diffs.

## Shapes

Controls use modest radii; panels may use the established wider radius. Code and diff areas are plain rectangular reading surfaces.

## Components

Buttons have explicit primary and secondary hierarchy, visible focus, disabled state, and quick press feedback. Status always has text. Loading and empty states explain the next possible action. Tabs identify the selected stage without hiding the overall task lifecycle.

## Do's and Don'ts

- Keep the Forge logo, cobalt/navy palette, and blue motif.
- Show real API state and actionable links.
- Keep long intent, logs, diagnostics, and diffs readable.
- Do not use fabricated metrics, generic icon tiles, or decorative motion over task evidence.
