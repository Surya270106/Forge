# Forge AI — UI Design System

## Overview
This document defines the design system implemented during the Forge AI Complete UI Overhaul (V2). It replaces the previous dark-themed admin layout with a bright, spacious, "Living Core" design.

## Typography
- **Primary Interface**: Inter (substituting Geist for Next.js 14.2.x compatibility).
- **Technical/Code**: Roboto Mono (substituting Geist Mono).

## Colors
- **Page Background**: `var(--forge-white)` (#f3f6fa) with a subtle grid pattern.
- **Surface**: `var(--forge-white)` with glassmorphism overlays and soft shadows.
- **Accents**: 
  - `var(--forge-blue)` (#075bea)
  - `var(--forge-blue-bright)` (#2f7dff)
  - `var(--forge-blue-deep)` (#063fae)
- **Status Colors**: 
  - Success: `var(--forge-success)` (#087a55)
  - Warning: `var(--forge-warning)` (#a05a00)
  - Danger: `var(--forge-danger)` (#b4233c)

## Layout & Components
- **Floating Shell (`AppShell`)**: A central shell component that houses a top context header and a left-aligned navigation rail. 
- **Blob Scene**: Central to the Forge identity. Positioned fixed at the center, underneath the `AppShell`. Transparency ranges between `0.1` and `0.2` depending on route depth.
- **Cards**: Replaced standard boxy cards with `.card` that feature a `bg-white/70 backdrop-blur-md` and rounded-2xl borders.
- **Buttons**:
  - Primary: Solid blue with hover state shadow and color shift.
  - Secondary: Translucent blue border, text blue.
  - Ghost: Light translucent fill on hover, no border.
- **Badges**: Standardized `Badge` component reflecting Semantic states (Success/Warning/Destructive).
