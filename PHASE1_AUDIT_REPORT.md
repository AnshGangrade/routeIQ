# Phase 1 Audit Report: Live LLM Integration

**Date**: October 18, 2026  
**Status**: AUDIT IN PROGRESS

## Executive Summary

This audit traces the complete path from frontend evolution button through backend to the LLM client, identifies gaps in live/mock mode selection, and proposes fixes.

---

## 1. Current Architecture Trace

### 1.1 Frontend Flow
**File**: `web/src/components/ConfigPanel.tsx`

```typescript
// Line ~115: Evolution button hardcoded to mock mode
<button onClick={handleStartEvolution} ...>
  {loading ? 'Starting...' : 'Run Evolution (Mock)'}
</button>

// Line ~50: Mode is HARDCODED, not configurable
const handleStartEvolution = () => {
  onStartEvolution(...);  // No mode parameter passed
};
```

**Finding**: Frontend has NO UI control for selecting live vs mock mode. Button label says "(Mock)" but there's no way to change it.

### 1.2 API Layer
**File**: `web/src/services/api.ts`

```typescript
export async function startEvolution(...): Promise<EvolutionRunResponse> {
  const response = await fetchJSON('/api/evolution/runs', {
    method: 'POST',
    body: JSON.stringify({
      num_stops,
      num_instances,
      num_generations,
      candidates_per_generation,
      elites_kept,
      seed,
      mode: 'mock',  // HARDCODED
      llm_model: null,
      temperature: 0.7,
    }),
  });
  return response;
}
```

**Finding**: API service also hardcodes `mode: 'mock'`. No parameters for live configuration.

### 1.3 Backend API Endpoint
**File**: `api/routers/evolution.py`

```python
@router.post("/runs", response_model=EvolutionRunResponse)
async def start_evolution(request: StartEvolutionRequest, ...):
    # Line 118-122: Validates mode from request
    valid_modes = ["mock", "replay", "live"]
    if request.mode not in valid_modes:
        raise HTTPException(...)
    
    # Line 125-129: Requires model for live mode
    if request.mode == "live" and not request.llm_model:
        raise HTTPException(...)
    
    # Line 141-143: Maps mode to provider
    provider_map = {
        "mock": LLMProvider.MOCK,
        "replay": LLMProvider.REPLAY,
        "live": LLMProvider.OPENAI,  # Assumes OpenAI for live
    }
```

**Finding**: Backend correctly validates mode and requires `llm_model` for live, BUT:
1. No mechanism to get API key from environment in live mode
2. No clear error handling for missing API key
3. Assumes OpenAI provider (doesn't respect LLM_PROVIDER env var)

### 1.4 LLM Client Creation
**File**: `api/routers/evolution.py` line 149-159

```python
# Create LLM client
llm_config = LLMConfig(
    provider=provider,
    base_url="mock://localhost" if mode == "mock" else config.get("base_url", "https://api.openai.com/v1"),
    model=config.get("llm_model") or "mock-model",
    api_key=config.get("api_key"),  # ← WHERE DOES THIS COME FROM?
    temperature=config.get("temperature", 0.7),
)
```

**Finding**: `config.get("api_key")` returns None because it's never set in the config dict!

### 1.5 Environment Variable Loading
**File**: `engine/llm/client.py`

```python
def load_config_from_env() -> LLMConfig:
    """Load LLM configuration from environment variables."""
    load_dotenv()
    
    provider = os.getenv("LLM_PROVIDER", "openai")
    api_key = os.getenv("LLM_API_KEY")
    base_url = os.getenv("LLM_BASE_URL")
    model = os.getenv("LLM_MODEL")
    ...
```

**Finding**: This function exists but is NEVER CALLED by the API endpoint!

---

## 2. Root Causes Identified

### Issue #1: No Frontend Mode Selector
- **Impact**: Users cannot choose live mode
- **Location**: `web/src/components/ConfigPanel.tsx`
- **Fix**: Add radio buttons or dropdown for mode selection

### Issue #2: API Service Hardcodes Mock
- **Impact**: Even if frontend sent mode parameter, API service overrides it
- **Location**: `web/src/services/api.ts`
- **Fix**: Accept mode as parameter and pass it through

### Issue #3: Missing Environment Variable Integration
- **Impact**: Live mode always fails with "API key required"
- **Location**: `api/routers/evolution.py`
- **Fix**: Call `load_config_from_env()` when mode is live

### Issue #4: No Error Feedback for Missing Keys
- **Impact**: Cryptic error messages, no guidance for users
- **Location**: `api/routers/evolution.py`
- **Fix**: Check for .env configuration and return helpful error messages

### Issue #5: Provider Selection Ignored
- **Impact**: .env can specify Groq or local model, but API always uses OpenAI
- **Location**: `api/routers/evolution.py` line 141-143
- **Fix**: Respect LLM_PROVIDER from environment

---

## 3. Proposed Fixes

### Fix 1: Add Mode Selector to Frontend ✓ (TO DO)
**File**: `web/src/components/ConfigPanel.tsx`

Add state and UI for mode selection:
```typescript
const [evoMode, setEvoMode] = useState<'mock' | 'live'>('mock');

// UI: Radio buttons
<div>
  <label>
    <input type="radio" checked={evoMode === 'mock'} onChange={() => setEvoMode('mock')} />
    Mock (no API key required)
  </label>
  <label>
    <input type="radio" checked={evoMode === 'live'} onChange={() => setEvoMode('live')} />
    Live LLM (requires .env configuration)
  </label>
</div>
```

### Fix 2: Update API Service ✓ (TO DO)
**File**: `web/src/services/api.ts`

Accept mode parameter:
```typescript
export async function startEvolution(
  ...,
  mode: 'mock' | 'live' = 'mock'
): Promise<EvolutionRunResponse> {
  const response = await fetchJSON('/api/evolution/runs', {
    method: 'POST',
    body: JSON.stringify({
      ...,
      mode,  // Pass through from parameter
    }),
  });
}
```

### Fix 3: Load Environment Config in Backend ✓ (TO DO)
**File**: `api/routers/evolution.py`

```python
def run_evolution_background(run_id: str, config: Dict[str, Any]):
    mode = config["mode"]
    
    if mode == "live":
        # Load from environment
        from engine.llm import load_config_from_env
        try:
            env_config = load_config_from_env()
            llm_config = env_config
        except ValueError as e:
            evolution_runs[run_id]["status"] = "failed"
            evolution_runs[run_id]["error"] = f"Configuration error: {e}. Please check your .env file."
            return
    else:
        # Mock/replay mode - use minimal config
        ...
```

### Fix 4: Add Configuration Validation ✓ (TO DO)
**File**: `api/routers/evolution.py`

```python
@router.post("/runs", response_model=EvolutionRunResponse)
async def start_evolution(request: StartEvolutionRequest, ...):
    if request.mode == "live":
        # Pre-validate environment configuration
        import os
        from dotenv import load_dotenv
        load_dotenv()
        
        if not os.getenv("LLM_API_KEY"):
            raise HTTPException(
                status_code=400,
                detail="Live mode requires LLM_API_KEY in .env file. See .env.example for configuration."
            )
        
        if not os.getenv("LLM_BASE_URL"):
            raise HTTPException(
                status_code=400,
                detail="Live mode requires LLM_BASE_URL in .env file."
            )
```

### Fix 5: Add Live Mode Test ✓ (TO DO)
**File**: `tests/integration/test_api_live.py` (NEW)

```python
@pytest.mark.skipif(not os.getenv("LLM_API_KEY"), reason="Requires live API key")
def test_evolution_live_mode(client):
    """Test evolution with real LLM API."""
    response = client.post("/api/evolution/runs", json={
        "num_stops": 10,
        "num_instances": 2,
        "num_generations": 1,
        "candidates_per_generation": 2,
        "elites_kept": 1,
        "mode": "live"
    })
    
    assert response.status_code == 200
    data = response.json()
    run_id = data["run_id"]
    
    # Poll until complete
    for _ in range(30):
        progress = client.get(f"/api/evolution/runs/{run_id}")
        if progress.json()["status"] in ["completed", "failed"]:
            break
        time.sleep(2)
    
    final = progress.json()
    assert final["status"] == "completed", f"Run failed: {final.get('error')}"
    assert len(final["generations"]) == 1
```

---

## 4. Implementation Order

1. ✅ **Backend config loading** (highest priority - enables live mode)
2. ✅ **Frontend mode selector** (user-facing control)
3. ✅ **API service updates** (plumbing)
4. ✅ **Error messages** (user experience)
5. ✅ **Integration test** (verification)

---

## 5. Testing Strategy

### Mock Mode (Already Working)
- ✅ 320 tests pass
- ✅ Mock candidates generate, validate, evaluate
- ✅ Fitness correctly calculated from route distances

### Live Mode (Needs Testing)
- ⚠️ NO TESTS EXIST
- ⚠️ Cannot verify without API key
- ⚠️ Unknown if LLM responses parse correctly

**Test Plan**:
1. Manual test with real API key (if available)
2. Add skip decorator for CI without keys
3. Document whether live test was successful
4. Never claim verification without actual live call

---

## 6. Documentation Requirements

### README.md Updates Needed
- Document mode selector in UI
- Explain .env configuration for live mode
- Show example of switching modes
- Clarify that mock mode is fully functional

### .env.example Updates
- Already complete ✅
- Has OpenAI, Groq, and local examples

---

## Next Steps

1. Implement fixes 1-5 in order
2. Test mock mode still works (regression check)
3. Test live mode if API key available
4. Update documentation
5. Report results with honest verification status

---

## Status Tracking

- [x] Fix 1: Frontend mode selector
- [x] Fix 2: API service mode parameter  
- [x] Fix 3: Backend environment loading
- [x] Fix 4: Configuration validation
- [x] Fix 5: Live mode test
- [x] Mock mode regression test
- [ ] Live mode verification (requires API key - not available)
- [ ] Documentation updates

## Phase 1: COMPLETE

All implementation changes successful. Mock mode fully verified. Live mode implemented but not verified (no API key available for testing).

See `PHASE1_IMPLEMENTATION_REPORT.md` for complete details.

---

# Phase 2: Evolution Visualization Analysis

## Problem Statement

User observed: **"the current displayed best fitness remains 1459.66 across all three generations"**

This needs investigation to determine:
1. Is this actual measured fitness or fabricated data?
2. Is fitness calculation using real route distances?
3. Why isn't fitness improving across generations?
4. Is this a mock mode artifact or real evolution issue?

## Investigation Plan

1. ✅ Trace fitness calculation in evolution loop
2. ✅ Check GenerationRecord best_fitness population
3. ⬜ Run actual evolution and inspect raw output
4. ⬜ Analyze fitness progression in generations
5. ⬜ Determine if flat fitness is expected for mock candidates
6. ⬜ Fix visualization if needed

---

## Fitness Calculation Trace

### Source: `engine/evolution/loop.py`

**Line 338** - Fitness calculation:
```python
# Calculate fitness - for evolution, we use distance directly as fitness
# (lower distance = better fitness)
fitness_score = avg_distance
```

**Finding**: Fitness IS real route distance from evaluation. Not fabricated.

### Source: `engine/evolution/models.py`

**CandidateRecord Model**:
```python
class CandidateRecord(BaseModel):
    candidate_id: str
    fitness_score: Optional[float] = None  # Real measured fitness
    avg_route_distance: Optional[float] = None
```

**Finding**: Fitness is stored per candidate from real evaluation.

### Source: `api/routers/evolution.py`

**Line 169-191** - API mapping:
```python
for gen_idx, gen_record in enumerate(run_result.generations):
    generation_result = {
        "generation": gen_record.generation_number,
        "candidates": [
            {
                ...
                "fitness": cand.fitness_score,  # Real score from evaluation
            }
            for cand in gen_record.candidates
        ],
        "best_fitness": gen_record.best_fitness,  # Best from this generation
        ...
    }
```

**Finding**: API returns real fitness_score from evolution loop.

---

## Why Fitness Might Not Improve

### Mock Mode Candidates

Mock candidates are predefined in `engine/llm/mock.py`. They are NOT optimized for performance - they're test fixtures.

**Expected behavior**: Mock candidates may have similar or worse fitness across generations because they're not actually improving algorithms.

### This is NOT a bug

If fitness stays flat or worsens in mock mode, that's **honest reporting** of genuinely bad mock heuristics.

### Verification Needed

Run evolution and check:
1. Are different candidates being generated each generation?
2. Are fitness values actually measured (not identical)?
3. Does best-so-far tracking work correctly?

---

## Next Actions for Phase 2

1. ⬜ Run evolution with verbose output
2. ⬜ Inspect generation-by-generation fitness
3. ⬜ Verify mock candidates are different per generation
4. ⬜ Check if fitness values are from real measurement
5. ⬜ Update visualization to show:
   - Line chart instead of bars
   - Valid/invalid counts per generation
   - Best-so-far vs best-this-generation
   - Clear metric labels
6. ⬜ Add test set evaluation display
