# Analytics Page Override

Inherits `../MASTER.md`.

## Purpose

- Put task counts and local-compute usage in one read-only operational view.
- Keep “estimated reference cost” visually and verbally separate from “actual API bill”.

## Structure

1. Scope and measurement period.
2. Four task-state cards.
3. Four Token cards: input, output, total, estimated USD.
4. Accessible 14-active-day Token trend with a numeric table fallback.
5. Restricted versus trusted execution-mode breakdown.
6. Cost explanation and actual API billing value.

## Visual and interaction rules

- Preserve the purple/cyan dark console palette and existing type scale.
- Use compact horizontal CSS bars; do not add chart, font, or network dependencies.
- Input and output require both labels and distinct colors.
- Numeric values use tabular figures and locale-aware formatting.
- Reflow to two Token cards at tablet width and one card at narrow phone width.
- Empty or unavailable Hermes ledgers must show explanatory text rather than a blank chart.
