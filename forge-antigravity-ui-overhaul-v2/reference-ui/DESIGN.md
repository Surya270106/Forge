# Design System: Forge AI

## North star

**Rich Air / Living Core**

Forge now reads as a premium engineering product rather than a control-panel
mockup. Rich white creates air and trust, saturated blue carries the product
signal, and the original WebGL form remains the living intelligence behind the
entire experience.

## Principles

1. **One living object.** The original blob shader, geometry, color, and pointer
   response stay intact. It remains fixed at the same centered viewport
   position, moves only through its cursor-responsive surface, and recedes after
   the first viewport.
2. **One idea per viewport.** Each section has a single proposition, one
   supporting explanation, and one purposeful visual mechanism.
3. **Evidence over decoration.** Mono type is reserved for real stages,
   systems, and technology names. There are no fictional counters, status
   panels, or production claims.
4. **Motion explains.** Scroll reveals hierarchy, connectors draw the system
   path, and lifecycle transitions show state. Reduced-motion preferences are
   always respected.

## Color

- **Soft White** `#f3f6fa` — primary field.
- **Paper** `#edf2f7` — cool white depth.
- **Ink** `#061a36` — primary text.
- **Forge Blue** `#075bea` — primary action and signal.
- **Execution Blue** `#063fae` — saturated section field.
- **Paper Blue** `#edf5ff` — architecture field.
- **Muted** `#58708f` — supporting copy.
- **Line** `#cbdcf2` — quiet structure.

Blue is the only saturated accent. Deep navy is used as readable ink, never as
a return to the previous black visual system.

## Typography

Geist is the single visual voice. Large headings use a clean medium weight,
compressed line-height, and tight tracking. Geist Mono appears only for stage
numbers, technical ownership, and stack evidence.

- Hero: `clamp(78px, 8.35vw, 158px)`, weight 470, line-height 0.86.
- Section display: `clamp(58px, 7vw, 126px)`, weight 480.
- Body: 16–20px with 1.6–1.66 line-height.
- Evidence: 10–11px Geist Mono with restrained tracking.

## Layout and shape

The site uses generous 40px desktop gutters and 20px mobile gutters. Sections
alternate translucent white, saturated blue, and pale blue so the fixed blob
remains faintly present behind every viewport. Rounded forms are limited to the
floating navigation, controls, the interactive workflow, and architecture
nodes.

## Components

- **Floating header:** compact glass-white navigation with one dark source
  action.
- **Hero:** one eyebrow, one two-line proposition, one paragraph, and two
  actions. No side metadata or fictional system status.
- **Evidence rail:** a linear request-to-patch sequence.
- **Lifecycle console:** accessible vertical tabs with Arrow, Home, and End key
  support.
- **Guardrail list:** large divided rows instead of repeated cards.
- **Topology:** a drawn ingress-to-backbone-to-state path plus focused engines.

## Motion

- The original blob retains its shader animation and mouse interaction.
- Its transparent WebGL stage includes overscan, keeping deformed pixels clear
  of the canvas boundary without changing the blob's viewport anchor.
- Page scroll reduces its opacity after the hero without moving or resizing its
  viewport position.
- Section content reveals upward on entry where View Timelines are supported.
- Active workflow content uses a short eased transition.
- All decorative movement collapses under `prefers-reduced-motion`.
