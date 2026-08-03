# ماهد گنجه — Style Reference
> midnight precision instrument (Linear-inspired)

**Theme:** dark  
**Source:** [Refero Linear](https://styles.refero.design/style/90ce5883-bb24-4466-93f7-801cd617b0d1)

Midnight command center on near-black surfaces with paper-white type and one electric acid-lime accent used sparingly for primary actions. Hairline borders instead of decorative shadows. Compact, precision-machined components. Persian UI uses Vazirmatn (weights capped at 500–600; avoid 700+).

## Colors

| Token | Value | Role |
|-------|-------|------|
| `--color-void` | `#08090a` | Page canvas |
| `--color-carbon` | `#0f1011` | Cards, nav |
| `--color-obsidian` | `#161718` | Elevated panels |
| `--color-graphite` | `#23252a` | Subtle borders |
| `--color-smoke` | `#383b3f` | Stronger dividers |
| `--color-ash` | `#62666d` | Muted text |
| `--color-fog` | `#8a8f98` | Tertiary / placeholders |
| `--color-mist` | `#d0d6e0` | Secondary headings, nav text |
| `--color-bone` | `#e5e5e6` | High-contrast on dark buttons |
| `--color-paper` | `#ffffff` | Primary headings |
| `--color-acid-lime` | `#e4f222` | Primary CTA / active nav only |
| `--color-pulse-green` | `#27a644` | OK / connected outlines |
| `--color-coral-red` | `#eb5757` | Errors / bad status |

## Typography

- **UI:** Vazirmatn (RTL Persian) — weights 400, 500, 600 max
- **Mono:** ui-monospace / JetBrains Mono for IDs and raw JSON
- Body ~15–16px / 400 / line-height 1.5–1.6
- Headings: weight 500, tight letter-spacing on large sizes
- Do not use weight 700+

## Spacing & shape

- Base unit: 4px — ladder 8 / 12 / 24
- Page max-width: 1200px
- Card padding: 24px
- Element gap: 8px
- Radius: cards 12px · inputs/buttons 6px · badges 4px · pills 9999px
- Elevation: hairline borders (`1px` graphite/smoke), not glow or heavy shadow

## Do / Don't

**Do**
- One acid-lime filled button per view for the primary action
- Flat void canvas; surface separation via border + tonal step
- Compact nav as typographic links / ghost chips

**Don't**
- Decorative gradients on buttons, cards, or text
- Glass blur / frosted panels
- Gold/green brand gradients from the old theme
- Bold 700+ display weights
