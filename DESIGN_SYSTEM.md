# Design system & hardening pass — crm_app (2026-07-03)

One tokenized stylesheet (`CSS` constant in `ui.py`) drives both the Director console and the Advocate app. Page templates carry no inline style rules anymore — `<style>__CSS__</style>` only. Change a token, both pages move together.

## Tokens (`:root`)

- **Type:** one family (`--font`, Segoe UI stack). Scale: `--fs-2xs 10.5 · xs 11.5 · sm 12.5 · base 14 · md 15 · lg 16 · 2xl 22`. Weights `--fw 400 / med 600 / bold 700 / heavy 800`. No one-off sizes in components.
- **Color — single (cool slate) temperature.** Neutrals `--ink #1e293b · ink-2 · muted #64748b · faint #94a3b8 · line · line-2`. Surfaces `--bg / surface / surface-2 / header`. Brand (accent, program CTAs) `--brand #2563eb` + ink/weak/border. Semantics are a fixed set: `--good / --warn / --bad` each with weak + ink variants. Every component color is `var(--…)`; only `#fff` and shadow rgba remain literal.
- **Spacing** 4/8 rhythm `--s1…--s6`. **Radii** `--r-sm 6 · r 8 · r-md 10 · r-lg 12 · pill`. **Elevation** `--sh-1/2`. **Focus** `--ring`. **Tap** `--tap 40 · --tap-lg 44`.

## Components (consistent, with all states)

- **Buttons:** primary (`button`), secondary (`.sec`), tertiary (`.link/.linky`); good/warn/bad variants. Hover / active / disabled / focus-visible defined once. Min-height 40; primary CTAs (`.callbtn`, `.bigassign`) 44.
- **Inputs/select/textarea:** shared height, radius, border, placeholder color, focus ring.
- **Chips:** base + `.on / .inc / .exc` states; unmistakable selected vs unselected.
- **Cards/panels, tables, tabs, segmented controls, stat cards, presets, pie, advocate cards** — all one definition, shared across pages.

## Accessibility

- `:focus-visible` ring on every interactive element (Tab-navigable); header links get a white ring for contrast.
- `@media (prefers-reduced-motion: reduce)` disables transitions/animations/smooth-scroll.
- Icon-only pager buttons carry `aria-label`; decorative carets/dots are `aria-hidden`.
- Contrast verified (WCAG AA): body text 14.6:1, muted 4.8:1, semantic text on weak surfaces 4.8–7.3:1, button text ≥3.3:1 (large/UI). Meaning never by color alone — every colored state also carries text/icon.

## Open decisions (for the next builder)

1. **Emoji as affordance:** meaningful emoji (📞 💬 ⚡ 🟢 🕊) are kept as an intentional friendly-voice choice, marked decorative where icon-only. Swap to an SVG icon set if brand requires; the tokens are ready.
2. **Tap target 40 vs 44:** dense desktop utility controls (chips, segmented buttons, tabs) sit at 34–40px for information density; primary CTAs are ≥44. Revisit if the advocate app is used primarily on touch tablets.
3. **SMS templates** in `main.py` `SMS_TEMPLATES` are unbranded outreach texts (opt-out included) — no MLR/PRC required per program owner; director-editable.
4. **Click-to-email** deferred (needs Gmail-API send to keep addresses hidden).

## Not-yet-wired / status

Nothing dead: every control has a handler; empty/loading/error/zero-result states exist on both pages (list empties, "no batches yet", toast on API error). No TODO/lorem/placeholder copy in the code. Seed/preview data is labeled "PREVIEW". App version state lives in `../PROJECT_STATE.md`.
