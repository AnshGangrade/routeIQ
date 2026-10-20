# Flexible Real-World Location Testing Guide

**Date**: October 18, 2026  
**Feature**: Flexible location configuration with geolocation and nearby stop generation

---

## Changes Made

### 1. Removed Hardcoded Berlin Defaults ✅
- **Before**: Berlin coordinates pre-filled, 30 stops default, 3 drivers default
- **After**: Empty depot fields, 5 stops default, 2 drivers default
- **Status**: Default values are now sensible for quick demos

### 2. Current Location Support ✅
- **Feature**: "Use My Current Location" button with browser geolocation API
- **Behavior**:
  - Requests permission only when button is clicked
  - Sets depot longitude/latitude from browser position
  - Handles errors with clear messages:
    - Permission denied
    - Position unavailable  
    - Timeout
  - Never silently substitutes a different location
- **Fallback**: Manual coordinate entry always available

### 3. Flexible Stop Configuration ✅
- **Two modes**:
  1. **Generate Nearby Stops**: Creates N simulated stops within configurable radius (1-50 km)
  2. **Enter Manually**: Add/remove stops with longitude/latitude inputs
- **Features**:
  - Stop count updates automatically based on "Delivery Stops" field
  - Driver count configurable independently (1-10)
  - Clear labeling: "simulated delivery locations for demonstration purposes"
  - Warning shown when insufficient stops entered

### 4. Improved UI Workflow ✅
Clear 3-step process for road mode:
1. **Depot Location**: Use current location OR enter manually
2. **Configure Fleet**: Set number of stops and drivers
3. **Delivery Stop Locations**: Generate nearby OR enter manually

### 5. Validation ✅
- Depot coordinates required before generating nearby stops
- Geographic range validation: longitude [-180, 180], latitude [-90, 90]
- Clear error messages for:
  - Missing depot
  - Invalid coordinates
  - Insufficient stops
  - Out-of-range values
- No silent fallbacks

---

## Testing Checklist

### A. Geolocation Tests

#### Test 1: Current Location Success
1. Start frontend: `cd web ; npm run dev`
2. Select "Real Road Network" mode
3. Click "Use My Current Location"
4. **Expected**: Browser prompts for location permission
5. **Expected**: After accepting, longitude/latitude fields populate with your location
6. **Verify**: Coordinates are numeric and within valid ranges

#### Test 2: Permission Denied
1. Select "Real Road Network" mode
2. Click "Use My Current Location"
3. Deny permission in browser
4. **Expected**: Error message: "Location permission denied. Please enter coordinates manually."
5. **Verify**: Depot fields remain empty (no silent Berlin substitution)

#### Test 3: Manual Fallback
1. After any geolocation failure, enter coordinates manually
2. Example: Longitude: `-122.4194`, Latitude: `37.7749` (San Francisco)
3. **Expected**: Values accepted, no error

---

### B. Variable Stop Count Tests

#### Test 4: Generate 3 Stops
1. Set "Delivery Stops" to 3
2. Set "Drivers" to 2
3. Enter depot coordinates (or use current location)
4. Select "Generate simulated stops nearby"
5. Set radius to 5 km
6. Click "Generate 3 Stops"
7. **Expected**: 3 stop coordinates appear
8. **Verify**: Green checkmark shows "3 stop location(s) ready"
9. Click "Generate Instance (Road)"
10. **Expected**: Instance created with 3 stops, 2 drivers

#### Test 5: Generate 5 Stops
1. Set "Delivery Stops" to 5
2. Generate nearby stops (radius 10 km)
3. **Expected**: 5 stops generated
4. Create instance
5. **Verify**: Route visualization shows 5 stops

#### Test 6: Generate 10 Stops
1. Set "Delivery Stops" to 10
2. Set "Drivers" to 3
3. Generate nearby stops (radius 15 km)
4. **Expected**: 10 stops generated around depot
5. Create instance
6. **Verify**: Algorithm comparison works with 10 stops

#### Test 7: Generate 20 Stops
1. Set "Delivery Stops" to 20
2. Set "Drivers" to 4
3. Generate nearby stops (radius 20 km)
4. **Expected**: 20 stops generated
5. Run Nearest Neighbor and 2-Opt
6. **Verify**: Routes calculated correctly with OSRM distances

---

### C. Variable Driver Count Tests

#### Test 8: Single Driver
1. Set "Drivers" to 1
2. Generate 5 stops
3. Create instance and solve
4. **Verify**: Single route visiting all stops

#### Test 9: Two Drivers
1. Set "Drivers" to 2
2. Generate 8 stops
3. **Verify**: Stops split between 2 drivers

#### Test 10: Five Drivers
1. Set "Drivers" to 5
2. Generate 15 stops
3. **Verify**: Fleet metrics show 5 driver routes

---

### D. Manual Stop Entry Tests

#### Test 11: Add Stops Manually
1. Select "Enter specific addresses/coordinates"
2. Click "+ Add Stop" multiple times
3. Enter coordinates for each:
   - Stop 1: `-122.4194, 37.7749` (SF)
   - Stop 2: `-122.4083, 37.7849` (North Beach)
   - Stop 3: `-122.4311, 37.7911` (Presidio)
4. **Verify**: Warning shows if fewer than required stops
5. **Verify**: Green check appears when enough stops entered

#### Test 12: Remove Stops
1. Add 5 stops manually
2. Click "×" to remove stop 3
3. **Verify**: Stop removed, count updates
4. **Verify**: Warning appears if now below required count

---

### E. Validation Tests

#### Test 13: Missing Depot
1. Leave depot fields empty
2. Try to generate nearby stops
3. **Expected**: Button disabled OR alert "Please set depot location first"

#### Test 14: Invalid Longitude
1. Enter depot longitude: `200` (out of range)
2. Enter latitude: `40`
3. Click "Generate Instance (Road)"
4. **Expected**: Error: "Longitude must be between -180 and 180"

#### Test 15: Invalid Latitude
1. Enter depot longitude: `-80`
2. Enter latitude: `95` (out of range)
3. Click "Generate Instance (Road)"
4. **Expected**: Error: "Latitude must be between -90 and 90"

#### Test 16: Non-numeric Coordinates
1. Enter depot longitude: `abc`
2. Click "Generate Instance (Road)"
3. **Expected**: Error: "Please enter valid depot coordinates"

#### Test 17: Insufficient Stops
1. Set "Delivery Stops" to 10
2. Only add 7 stops manually
3. Click "Generate Instance (Road)"
4. **Expected**: Error: "Need 10 stops but only have 7. Add more stops manually."

---

### F. Road Routing Integration Tests

#### Test 18: Real OSRM Distances
1. Configure depot and 5 stops around San Francisco
2. Generate instance (road mode)
3. Solve with Nearest Neighbor
4. **Expected**: Routes use real road distances (not Euclidean)
5. **Verify**: Distance values realistic for road network

#### Test 19: Algorithm Comparison with Same Matrix
1. Generate road instance (10 stops)
2. Solve with Nearest Neighbor
3. Solve with 2-Opt
4. **Verify**: Both algorithms receive identical OSRM distance matrix
5. **Verify**: 2-Opt total distance ≤ Nearest Neighbor distance

#### Test 20: OSRM Connection Failure
**Note**: Hard to test without blocking network
1. If OSRM request fails, check backend console
2. **Expected**: Error message with network issue details
3. **Expected**: Frontend shows actionable error (not silent fallback)

---

### G. Synthetic Mode Preservation Tests

#### Test 21: Synthetic Mode Still Works
1. Select "Synthetic (Random Coordinates)" mode
2. Set 30 stops, 3 drivers, uniform layout
3. Seed: 42
4. Generate instance
5. **Verify**: Instance created with Euclidean distances
6. **Verify**: Coordinate plot visualization works

#### Test 22: Mock Evolution Still Works
1. Generate synthetic instance (20 stops)
2. Configure evolution: 3 gen, 4 candidates, mock mode
3. Run evolution
4. **Verify**: Evolution completes with predefined heuristics
5. **Verify**: Progress chart updates

---

### H. Edge Cases

#### Test 23: Zero Radius (Nearby Stops)
1. Set radius to 0 km
2. Generate stops
3. **Expected**: All stops at depot location (edge case, but valid)

#### Test 24: Very Large Radius
1. Set radius to 50 km
2. Generate 10 stops
3. **Expected**: Stops spread widely around depot

#### Test 25: More Drivers Than Stops
1. Set 5 stops, 10 drivers
2. Generate instance
3. **Expected**: Some drivers have no assigned stops (valid, existing behavior)

---

## Success Criteria

### Must Pass
- ✅ Geolocation button requests permission correctly
- ✅ Permission denial shows clear error with manual fallback
- ✅ No silent substitution of Berlin or other defaults
- ✅ Stop count and driver count independently configurable
- ✅ Nearby stop generation works with configurable radius
- ✅ Manual stop entry with add/remove functionality
- ✅ Geographic coordinate validation (-180 to 180, -90 to 90)
- ✅ Clear error messages for all validation failures
- ✅ Road routing uses real OSRM distances
- ✅ All algorithms share the same distance matrix
- ✅ Synthetic mode unchanged and working
- ✅ Mock/live evolution modes working
- ✅ Frontend builds successfully (TypeScript clean)
- ✅ Backend tests pass (323/323)

### Visual Verification
- UI shows clear 3-step workflow for road mode
- Warning labels identify simulated stops
- Stop counter updates correctly
- Buttons disabled when inputs incomplete
- Error messages actionable and specific

---

## Known Limitations

1. **Geocoding**: No address-to-coordinate conversion implemented. Users must provide coordinates.
2. **Address Search**: Not implemented. Would require geocoding API integration.
3. **Map Preview**: Locations shown on route visualization only after instance created.
4. **OSRM Alternatives**: Only public demo server supported (no self-hosted option in UI).

---

## Quick Test Commands

```powershell
# Backend
py -m uvicorn api.main:app --reload --host 127.0.0.1 --port 8000

# Frontend
cd web
npm run dev

# Visit: http://localhost:5173

# Run backend tests
py -m pytest tests/ -v

# Build frontend
cd web
npm run build
```

---

**Testing Complete When**: All checklist items pass and no silent failures occur.
