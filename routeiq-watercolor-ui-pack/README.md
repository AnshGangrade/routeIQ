# RouteIQ Watercolor UI Pack — corrected direction

This pack follows the user's reference image: a softly hand-illustrated,
watercolor/ink city-map aesthetic with a restrained, muted palette.

This is NOT a Japanese theme and does NOT include Japanese motifs, vans,
packages, warehouse illustrations, or mascots.

## Visual direction
- Warm ivory paper base.
- Muted blue-grey / ink navy roads and text.
- Soft teal waterways and primary route.
- Sage parks and green spaces.
- Dusty lavender urban blocks / secondary route.
- Small terracotta accents for highlights and selected states.
- Thin ink outlines, subtle watercolor texture, restrained shadows.
- Clean modern SaaS UI components around the illustrated-map visual language.

## Included
- Brand/header reference with city-map artwork
- Leaflet map visual-direction reference
- Depot, numbered stop, driver and route-end marker reference
- Four route-line style references
- Thin-stroke interface icon reference
- Buttons, tabs, controls, metric cards and table references
- Map texture, street-grid, contour and route-pattern references
- Empty, optimizing, error and loading state references
- Original generated design board

## Critical: the Leaflet map
The map artwork is only a visual reference / decorative image. It is NOT a real
map and must never be used as the live map layer or as route geometry.

Keep the existing Leaflet map, real geographic tile source, real stop/depot
coordinates, OSRM road geometry and matrix-derived distances. Improve the map
appearance by selecting/styling a muted basemap where licensing and tile
provider capabilities permit; add actual route polylines, markers, stop
numbers, driver colors, selected-route emphasis, map controls and scale from
live app data.

Build all functional markers, route strokes, icons, controls and components as
proper SVG/CSS/React components. Do not display the full design board in the
application. These files are raster crops from a generated reference board,
not editable SVG assets; recreate production components cleanly.

## Suggested palette sampled from the design direction
- Ivory: #F8F4E8
- Ink blue: #314E6A
- Teal: #2F7C7B
- Sage: #8FAF8C
- Lavender: #C7B6D9
- Stone: #D9C9B6
- Terracotta: #D77251

## Typography direction
- Playfair Display: display headlines, used sparingly
- Inter: all UI and body text
- IBM Plex Mono: metrics, coordinates, technical labels

## Do not
- Add Japanese motifs or Japanese text.
- Add vans, packages, warehouses, generic logistics clip-art or mascots.
- Replace the real Leaflet map with generated artwork.
- Fake distances, streets, route geometry, or map labels.
- Treat sample table values in the board as real app data.
