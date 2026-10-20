# RouteIQ Dashboard

React + TypeScript frontend for the RouteIQ LLM-guided route optimization system.

## Tech Stack

- **React 18** + **TypeScript** - UI framework and type safety
- **Vite** - Fast build tool and dev server
- **Tailwind CSS** - Utility-first styling
- **SVG** - Route visualization (synthetic coordinate plot)

## Features

### 1. Configuration Panel
- Instance generation (stops, drivers, layout, seed)
- Routing controls (Nearest Neighbor, 2-Opt)
- Evolution parameters (generations, candidates, instances)
- Mock mode evolution (no LLM API key required)

### 2. Route Visualization
- Synthetic coordinate plot (not geographic map)
- Color-coded driver routes
- Depot marker and stop identifiers
- Method selector for viewing different solutions

### 3. Algorithm Comparison
- Side-by-side performance metrics
- Total distance and max route distance
- Improvement percentages (including negative improvements)
- Best algorithm identification
- Computation time tracking

### 4. Driver Metrics
- Total fleet distance
- Longest driver route (workload balance indicator)
- Per-driver breakdowns
- Stop counts and percentage of total

### 5. Evolution Progress
- Real-time generation-by-generation progress
- Fitness progression chart
- Valid/invalid candidate counts
- Best candidate selection
- Status tracking (pending/running/completed/failed)

## Architecture

### API Integration
All API calls are in `src/services/api.ts`:
- Type-safe requests using TypeScript interfaces
- Error handling with custom `ApiError` class
- Matches backend Pydantic models exactly

### State Management
Simple React useState in App.tsx:
- Instance state
- Routing results (Map by method)
- Evolution run progress
- Comparison data
- Loading and error states

### Polling
Evolution progress is polled every 2 seconds:
- Only while status is 'running' or 'pending'
- Stops automatically on completion or failure
- No server-sent events required

## Design

### Visual Identity
- **Background**: Warm off-white (#f7f4ed)
- **Text**: Navy/charcoal for high contrast
- **Accents**: Blue, teal, purple for different actions
- **Borders**: Subtle warm neutral
- **Spacing**: Clean, professional hierarchy

### Subtle Retro Elements
- Pixel-style loading animation (3 square dots)
- Clean coordinate grid (not geographic basemap)
- Bold typography
- ~10-15% retro influence, 85-90% modern dashboard

### No Excessive Design
- No pixel-art characters or game UI
- No neon colors or oversaturated cards
- No unnecessary animations
- Professional engineering/AI product aesthetic

## Running

### Development
```bash
npm run dev
```
Starts on http://localhost:5173 with hot reload.

### Production Build
```bash
npm run build
```
Outputs to `dist/` directory.

### Preview Production Build
```bash
npm run preview
```

## Backend Connection

The frontend expects the backend at http://localhost:8000.

Vite proxy configuration (vite.config.ts):
```typescript
proxy: {
  '/api': {
    target: 'http://localhost:8000',
    changeOrigin: true,
  },
}
```

## TypeScript Types

All API types in `src/types/api.ts` match backend Pydantic models:
- GenerateInstanceRequest / InstanceResponse
- SolveRoutingRequest / RoutingResultResponse
- StartEvolutionRequest / EvolutionProgressResponse
- ComparisonResponse / MethodComparison

## Components

- **App.tsx** - Main application, state management, API orchestration
- **ConfigPanel.tsx** - Instance and evolution configuration
- **RouteVisualization.tsx** - SVG coordinate plot of routes
- **AlgorithmComparison.tsx** - Performance comparison table
- **DriverMetrics.tsx** - Per-driver route statistics
- **EvolutionProgress.tsx** - Generation tracking and fitness chart

## Important Notes

1. **Synthetic Coordinates**: All coordinates are generated, not real addresses
2. **Euclidean Distance**: Straight-line distance, not road distance
3. **Honest Reporting**: Shows negative improvements when evolved performs worse
4. **Mock Mode**: Evolution runs without LLM API calls using MockLLMClient
5. **No Authentication**: Dashboard is open, suitable for demo/capstone only

## Browser Compatibility

Tested on:
- Chrome/Edge (Chromium)
- Firefox
- Safari (modern versions)

Requires modern browser with:
- ES2020 support
- CSS Grid
- Flexbox
- SVG rendering
