> Current contract (2026-11-26): the active product is the integrated planning
> workspace and canonical FleetProblem with trusted construction/VND/ILS, declarative
> strategy evolution and bounded native Ollama feedback (`qwen3:1.7b`). Historical
> executable-code guidance below applies only to legacy APIs. Preserve research
> records, independent validation, baseline definitions and split protection.
> README.md and docs/product-quality-pass.md describe the current workflow.

# RouteIQ Design Guidance

## Priority: Function Over Form

The capstone is evaluated on algorithmic contribution and implementation quality, NOT visual design. A clean, functional dashboard is sufficient.

## Minimal Viable Design (Required)

### Color Palette
- Background: Warm off-white (#f7f4ed or similar)
- Text: Near-black (#1c1c1c)
- Accent: Navy or charcoal for important elements
- Borders: Subtle warm neutral (#eceae4)
- **No neon colors, no unnecessary visual clutter**

### Typography
- Local Inter font; IBM Plex Mono for selected measurements
- 2-3 heading sizes maximum
- Clear hierarchy through size and weight, not elaborate letter-spacing
- Readable body text (16px)

### Components
- Simple flat cards with subtle borders
- Clean button styles (solid or outlined)
- Monochrome Leaflet base map; stable muted driver colors, numbered markers and line patterns
- Default Recharts styling
- Adequate whitespace for readability

### Layout
- Integrated planning column and persistent map; collapsible column on mobile
- Map takes prominent space
- Metrics table clearly formatted
- Charts sized appropriately

## Advanced Design (Optional, Only If Time/Credits Permit)

The DESIGN-theverge.md and DESIGN-lovable.md documents provide inspiration for refined styling. These are **optional enhancements** to consider only after:
- Step 12 is complete
- 100+ credits remain
- Core functionality is tested and stable

Advanced features might include:
- Custom typography with precise letter-spacing
- Sophisticated shadow/depth systems
- Refined color palettes with opacity-based grays
- Polished component styling

**Do NOT implement these during the core build phases.**

## Streamlit Fallback

If credits run low after Step 9 (< 200 remaining), switch to Streamlit:
- Accept Streamlit's default styling
- Customize only: title, color scheme (warm neutrals), whitespace
- Map via st.pydeck_chart or iframe
- Charts via built-in st.line_chart or plotly
- Much faster to build (~60-80 credits vs 150-200 for React)

## Design During Implementation

When building the dashboard:
1. Start with structure and functionality
2. Use Tailwind defaults for spacing and layout
3. Add minimal custom styling for brand consistency
4. Test on different screen sizes
5. Only refine visuals if time permits

**The evolved heuristic's performance matters more than gradient borders.**
