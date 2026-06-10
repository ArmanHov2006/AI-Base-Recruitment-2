# Design

## Visual Theme
Dark-mode professional interface with high-contrast data signals. The aesthetic is "Modern & AI-forward," using deep blues and vibrant semantic colors to distinguish candidate statuses and scores.

## Color Palette

### Base
- **Background**: `#09090e` (var(--color-bg-base))
- **Panel**: `#0e0e15` (var(--color-panel))
- **Panel Soft**: `#13131c` (var(--color-panel-soft))

### Ink & Muted
- **Ink (Text)**: `#ededf5` (var(--color-ink))
- **Muted**: `#a1a1bb` (var(--color-muted))
- **Soft**: `#64648a` (var(--color-soft))
- **Line/Border**: `rgba(255, 255, 255, 0.08)` (var(--color-line))

### Semantic Signals
- **Primary/Action**: `#5b6af5` (var(--color-primary))
- **Positive/Hired**: `#34d399` (var(--color-signal-positive))
- **Attention/In-Progress**: `#fbbf24` (var(--color-signal-attention))
- **Risk/Rejected**: `#f87171` (var(--color-signal-risk))

### Stage Accents
- **Applied**: `#5b6af5`
- **Screening**: `#a78bfa`
- **Interview**: `#38bdf8`
- **Offer**: `#fbbf24`
- **Hired**: `#34d399`
- **Rejected/Withdrawn**: `#64648a`

## Typography
- **Primary**: 'Fira Sans', sans-serif
- **Mono**: 'Fira Code', monospace
- **Title**: `clamp(26px, 3vw, 38px)`
- **Body**: `14px`
- **Label/Caption**: `12px`

## Layout & Components

### Kanban Board
- **Orientation**: Horizontal scrolling for columns.
- **Columns**: Flex-basis adaptive, min-width `280px` (recommended over current 140px).
- **Cards**: Surface elevation via `var(--color-panel)`, subtle left-border accent for seniority.

### Grid & Spacing
- Base unit: `4px`
- Standard gap: `16px`
- Column padding: `10px`

## Motion
- **Hover**: Subtle background brightening and border-color shift (140ms ease-out).
- **Drag & Drop**: Opacity reduction on drag, background tint on drop-target hover.
