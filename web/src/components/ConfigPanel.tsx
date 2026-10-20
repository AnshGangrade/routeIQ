import { useState } from 'react';

interface ConfigPanelProps {
  onGenerateInstance: (
    numStops: number,
    numDrivers: number,
    layout: 'uniform' | 'clustered',
    seed?: number,
    mode?: 'synthetic' | 'road',
    depotCoords?: number[],
    stopCoords?: number[][]
  ) => void;
  onSolveRouting: (method: 'nearest_neighbor' | '2opt') => void;
  onStartEvolution: (
    numStops: number,
    numInstances: number,
    numGenerations: number,
    candidatesPerGen: number,
    elitesKept: number,
    mode: 'mock' | 'live',
    seed?: number
  ) => void;
  hasInstance: boolean;
  loading: boolean;
}

export function ConfigPanel({
  onGenerateInstance,
  onSolveRouting,
  onStartEvolution,
  hasInstance,
  loading,
}: ConfigPanelProps) {
  const [numStops, setNumStops] = useState(5);
  const [numDrivers, setNumDrivers] = useState(2);
  const [layout, setLayout] = useState<'uniform' | 'clustered'>('uniform');
  const [instanceMode, setInstanceMode] = useState<'synthetic' | 'road'>('synthetic');
  const [seed, setSeed] = useState('42');
  const [useRandomSeed, setUseRandomSeed] = useState(false);

  // Road mode depot configuration
  const [depotLon, setDepotLon] = useState('');
  const [depotLat, setDepotLat] = useState('');
  const [geolocating, setGeolocating] = useState(false);
  const [geolocationError, setGeolocationError] = useState<string>('');

  // Road mode stops configuration
  const [stopGenerationMode, setStopGenerationMode] = useState<'nearby' | 'manual'>('nearby');
  const [nearbyRadius, setNearbyRadius] = useState(5); // km
  const [roadStops, setRoadStops] = useState<Array<{ lon: string; lat: string }>>([]);

  // Evolution params
  const [evoNumStops, setEvoNumStops] = useState(20);
  const [evoNumInstances, setEvoNumInstances] = useState(5);
  const [evoGenerations, setEvoGenerations] = useState(3);
  const [evoCandidates, setEvoCandidates] = useState(4);
  const [evoElites, setEvoElites] = useState(2);
  const [evoMode, setEvoMode] = useState<'mock' | 'live'>('mock');

  // Geolocation handler
  const handleUseCurrentLocation = () => {
    if (!navigator.geolocation) {
      setGeolocationError('Geolocation is not supported by your browser');
      return;
    }

    setGeolocating(true);
    setGeolocationError('');

    navigator.geolocation.getCurrentPosition(
      (position) => {
        setDepotLon(position.coords.longitude.toFixed(6));
        setDepotLat(position.coords.latitude.toFixed(6));
        setGeolocating(false);
        setGeolocationError('');
      },
      (error) => {
        setGeolocating(false);
        let errorMsg = 'Unable to retrieve location';
        switch (error.code) {
          case error.PERMISSION_DENIED:
            errorMsg = 'Location permission denied. Please enter coordinates manually.';
            break;
          case error.POSITION_UNAVAILABLE:
            errorMsg = 'Location unavailable. Please enter coordinates manually.';
            break;
          case error.TIMEOUT:
            errorMsg = 'Location request timeout. Please enter coordinates manually.';
            break;
        }
        setGeolocationError(errorMsg);
      },
      {
        enableHighAccuracy: true,
        timeout: 10000,
        maximumAge: 0
      }
    );
  };

  // Generate nearby stops (simulated locations for demo)
  const generateNearbyStops = () => {
    const depot = [parseFloat(depotLon), parseFloat(depotLat)];
    if (isNaN(depot[0]) || isNaN(depot[1])) {
      alert('Please set depot location first');
      return;
    }

    // Generate random points within radius
    // 1 degree ≈ 111km, so radius in degrees
    const radiusDeg = nearbyRadius / 111;
    const stops: Array<{ lon: string; lat: string }> = [];

    for (let i = 0; i < numStops; i++) {
      // Random angle and distance
      const angle = Math.random() * 2 * Math.PI;
      const distance = Math.sqrt(Math.random()) * radiusDeg; // sqrt for uniform distribution
      
      const lon = depot[0] + distance * Math.cos(angle);
      const lat = depot[1] + distance * Math.sin(angle);
      
      stops.push({
        lon: lon.toFixed(6),
        lat: lat.toFixed(6)
      });
    }

    setRoadStops(stops);
  };

  const handleGenerate = () => {
    const parsedSeed = useRandomSeed ? undefined : parseInt(seed) || 42;
    
    if (instanceMode === 'road') {
      // Validate depot coordinates
      const depot = [parseFloat(depotLon), parseFloat(depotLat)];
      
      if (!depotLon || !depotLat || isNaN(depot[0]) || isNaN(depot[1])) {
        alert('Please enter valid depot coordinates');
        return;
      }

      // Validate geographic range
      if (depot[0] < -180 || depot[0] > 180) {
        alert('Longitude must be between -180 and 180');
        return;
      }
      if (depot[1] < -90 || depot[1] > 90) {
        alert('Latitude must be between -90 and 90');
        return;
      }

      // Validate stops
      if (roadStops.length < numStops) {
        alert(`Need ${numStops} stops but only have ${roadStops.length}. ${stopGenerationMode === 'nearby' ? 'Click "Generate Nearby Stops"' : 'Add more stops manually'}.`);
        return;
      }

      const stops = roadStops.slice(0, numStops).map(s => {
        const lon = parseFloat(s.lon);
        const lat = parseFloat(s.lat);
        
        if (isNaN(lon) || isNaN(lat)) {
          throw new Error('Invalid stop coordinate');
        }
        if (lon < -180 || lon > 180 || lat < -90 || lat > 90) {
          throw new Error('Stop coordinate out of valid range');
        }
        
        return [lon, lat];
      });
      
      onGenerateInstance(numStops, numDrivers, 'uniform', parsedSeed, 'road', depot, stops);
    } else {
      onGenerateInstance(numStops, numDrivers, layout, parsedSeed, 'synthetic');
    }
  };

  const addRoadStop = () => {
    setRoadStops([...roadStops, { lon: '', lat: '' }]);
  };

  const removeRoadStop = (index: number) => {
    setRoadStops(roadStops.filter((_, i) => i !== index));
  };

  const updateRoadStop = (index: number, field: 'lon' | 'lat', value: string) => {
    const updated = [...roadStops];
    updated[index] = { ...updated[index], [field]: value };
    setRoadStops(updated);
  };

  const handleStartEvolution = () => {
    const parsedSeed = useRandomSeed ? undefined : parseInt(seed) || 42;
    onStartEvolution(
      evoNumStops,
      evoNumInstances,
      evoGenerations,
      evoCandidates,
      evoElites,
      evoMode,
      parsedSeed
    );
  };

  return (
    <div className="bg-white rounded-lg border border-warm-border shadow-sm p-6">
      <h2 className="text-2xl font-bold text-navy mb-4">Configuration</h2>

      {/* Instance Configuration */}
      <div className="space-y-4 mb-6">
        <h3 className="text-sm font-semibold text-slate-700 uppercase tracking-wide">
          Instance Setup
        </h3>

        <div>
          <label className="block text-sm font-medium text-slate-700 mb-1">
            Instance Mode
          </label>
          <select
            value={instanceMode}
            onChange={(e) => setInstanceMode(e.target.value as 'synthetic' | 'road')}
            className="w-full px-3 py-2 border border-slate-300 rounded-md focus:ring-2 focus:ring-blue-500 focus:border-transparent"
          >
            <option value="synthetic">Synthetic (Random Coordinates)</option>
            <option value="road">Real Road Network</option>
          </select>
        </div>

        {instanceMode === 'road' && (
          <>
            <div className="p-4 bg-blue-50 border border-blue-300 rounded-lg space-y-4">
              <div className="text-sm text-blue-900 font-medium">
                📍 Real Road Network Configuration
              </div>

              {/* Step 1: Depot Location */}
              <div className="space-y-2">
                <label className="block text-sm font-semibold text-slate-700">
                  1. Depot Location
                </label>
                
                <button
                  onClick={handleUseCurrentLocation}
                  disabled={geolocating}
                  className="w-full px-3 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed text-sm font-medium"
                >
                  {geolocating ? 'Getting Location...' : '📍 Use My Current Location'}
                </button>

                {geolocationError && (
                  <div className="p-2 bg-red-50 border border-red-300 rounded text-xs text-red-800">
                    {geolocationError}
                  </div>
                )}

                <div className="text-xs text-slate-600 text-center">or enter manually:</div>

                <div className="grid grid-cols-2 gap-2">
                  <div>
                    <label className="block text-xs font-medium text-slate-600 mb-1">
                      Longitude
                    </label>
                    <input
                      type="text"
                      placeholder="e.g., -122.4194"
                      value={depotLon}
                      onChange={(e) => setDepotLon(e.target.value)}
                      className="w-full px-2 py-1 text-sm border border-slate-300 rounded focus:ring-1 focus:ring-blue-500"
                    />
                  </div>
                  <div>
                    <label className="block text-xs font-medium text-slate-600 mb-1">
                      Latitude
                    </label>
                    <input
                      type="text"
                      placeholder="e.g., 37.7749"
                      value={depotLat}
                      onChange={(e) => setDepotLat(e.target.value)}
                      className="w-full px-2 py-1 text-sm border border-slate-300 rounded focus:ring-1 focus:ring-blue-500"
                    />
                  </div>
                </div>
              </div>

              {/* Step 2: Number of Stops and Drivers */}
              <div className="space-y-2">
                <label className="block text-sm font-semibold text-slate-700">
                  2. Configure Fleet
                </label>
                
                <div className="grid grid-cols-2 gap-2">
                  <div>
                    <label className="block text-xs font-medium text-slate-600 mb-1">
                      Delivery Stops
                    </label>
                    <input
                      type="number"
                      min="3"
                      max="50"
                      value={numStops}
                      onChange={(e) => setNumStops(parseInt(e.target.value) || 5)}
                      className="w-full px-2 py-1 text-sm border border-slate-300 rounded focus:ring-1 focus:ring-blue-500"
                    />
                  </div>
                  <div>
                    <label className="block text-xs font-medium text-slate-600 mb-1">
                      Drivers
                    </label>
                    <input
                      type="number"
                      min="1"
                      max="10"
                      value={numDrivers}
                      onChange={(e) => setNumDrivers(parseInt(e.target.value) || 2)}
                      className="w-full px-2 py-1 text-sm border border-slate-300 rounded focus:ring-1 focus:ring-blue-500"
                    />
                  </div>
                </div>
              </div>

              {/* Step 3: Stop Generation Mode */}
              <div className="space-y-2">
                <label className="block text-sm font-semibold text-slate-700">
                  3. Delivery Stop Locations
                </label>
                
                <div className="space-y-2">
                  <label className="flex items-center gap-2 cursor-pointer">
                    <input
                      type="radio"
                      checked={stopGenerationMode === 'nearby'}
                      onChange={() => setStopGenerationMode('nearby')}
                      className="text-blue-600 focus:ring-blue-500"
                    />
                    <span className="text-sm text-slate-700">
                      Generate simulated stops nearby
                    </span>
                  </label>
                  
                  <label className="flex items-center gap-2 cursor-pointer">
                    <input
                      type="radio"
                      checked={stopGenerationMode === 'manual'}
                      onChange={() => setStopGenerationMode('manual')}
                      className="text-blue-600 focus:ring-blue-500"
                    />
                    <span className="text-sm text-slate-700">
                      Enter specific addresses/coordinates
                    </span>
                  </label>
                </div>

                {stopGenerationMode === 'nearby' && (
                  <div className="space-y-2 mt-2 p-2 bg-white rounded border border-slate-200">
                    <div className="flex items-center gap-2">
                      <label className="text-xs font-medium text-slate-600">
                        Radius (km):
                      </label>
                      <input
                        type="number"
                        min="1"
                        max="50"
                        value={nearbyRadius}
                        onChange={(e) => setNearbyRadius(parseInt(e.target.value) || 5)}
                        className="w-20 px-2 py-1 text-sm border border-slate-300 rounded focus:ring-1 focus:ring-blue-500"
                      />
                      <button
                        onClick={generateNearbyStops}
                        disabled={!depotLon || !depotLat}
                        className="flex-1 px-3 py-1 bg-slate-600 text-white rounded hover:bg-slate-700 disabled:opacity-50 disabled:cursor-not-allowed text-sm"
                      >
                        Generate {numStops} Stops
                      </button>
                    </div>
                    <div className="text-xs text-amber-700 leading-tight">
                      ⚠️ These are simulated delivery locations for demonstration purposes.
                    </div>
                  </div>
                )}

                {stopGenerationMode === 'manual' && (
                  <div className="space-y-2 mt-2 p-2 bg-white rounded border border-slate-200">
                    <div className="flex items-center justify-between">
                      <span className="text-xs font-medium text-slate-600">
                        {roadStops.length} of {numStops} stops entered
                      </span>
                      <button
                        onClick={addRoadStop}
                        className="text-xs text-blue-600 hover:text-blue-800 font-medium"
                      >
                        + Add Stop
                      </button>
                    </div>
                    
                    <div className="space-y-1 max-h-48 overflow-y-auto">
                      {roadStops.map((stop, idx) => (
                        <div key={idx} className="grid grid-cols-[1fr,1fr,auto] gap-1 items-center">
                          <input
                            type="text"
                            placeholder="Longitude"
                            value={stop.lon}
                            onChange={(e) => updateRoadStop(idx, 'lon', e.target.value)}
                            className="px-2 py-1 text-xs border border-slate-300 rounded focus:ring-1 focus:ring-blue-500"
                          />
                          <input
                            type="text"
                            placeholder="Latitude"
                            value={stop.lat}
                            onChange={(e) => updateRoadStop(idx, 'lat', e.target.value)}
                            className="px-2 py-1 text-xs border border-slate-300 rounded focus:ring-1 focus:ring-blue-500"
                          />
                          <button
                            onClick={() => removeRoadStop(idx)}
                            className="text-sm text-red-600 hover:text-red-800 px-2"
                            title="Remove stop"
                          >
                            ×
                          </button>
                        </div>
                      ))}
                    </div>
                    
                    {roadStops.length < numStops && (
                      <div className="text-xs text-amber-700">
                        ⚠️ Need {numStops - roadStops.length} more stop(s)
                      </div>
                    )}
                  </div>
                )}

                {roadStops.length > 0 && (
                  <div className="text-xs text-green-700 bg-green-50 border border-green-200 rounded p-2">
                    ✓ {roadStops.length} stop location(s) ready
                  </div>
                )}
              </div>

              <div className="text-xs text-slate-600 leading-relaxed pt-2 border-t border-slate-200">
                <strong>Note:</strong> Uses OSRM public routing service for real road distances. 
                Ensure you have network connectivity and have set valid geographic coordinates.
              </div>
            </div>

            {/* Still show the common controls but make them specific to road */}
          </>
        )}

        {instanceMode === 'synthetic' && (
          <>
            <div>
              <label className="block text-sm font-medium text-slate-700 mb-1">
                Number of Stops
              </label>
              <input
                type="number"
                min="5"
                max="200"
                value={numStops}
                onChange={(e) => setNumStops(parseInt(e.target.value))}
                className="w-full px-3 py-2 border border-slate-300 rounded-md focus:ring-2 focus:ring-blue-500 focus:border-transparent"
              />
            </div>

            <div>
              <label className="block text-sm font-medium text-slate-700 mb-1">
                Number of Drivers
              </label>
              <input
                type="number"
                min="1"
                max="20"
                value={numDrivers}
                onChange={(e) => setNumDrivers(parseInt(e.target.value))}
                className="w-full px-3 py-2 border border-slate-300 rounded-md focus:ring-2 focus:ring-blue-500 focus:border-transparent"
              />
            </div>

            <div>
              <label className="block text-sm font-medium text-slate-700 mb-1">
                Layout
              </label>
              <select
                value={layout}
                onChange={(e) => setLayout(e.target.value as 'uniform' | 'clustered')}
                className="w-full px-3 py-2 border border-slate-300 rounded-md focus:ring-2 focus:ring-blue-500 focus:border-transparent"
              >
                <option value="uniform">Uniform</option>
                <option value="clustered">Clustered</option>
              </select>
            </div>
          </>
        )}

        {/* Common fields */}
        <div>
          <label className="block text-sm font-medium text-slate-700 mb-1">
            Random Seed
          </label>
          <div className="flex items-center gap-2 mb-2">
            <input
              type="checkbox"
              checked={useRandomSeed}
              onChange={(e) => setUseRandomSeed(e.target.checked)}
              className="rounded"
            />
            <span className="text-sm text-slate-600">Use random seed</span>
          </div>
          {!useRandomSeed && (
            <input
              type="number"
              value={seed}
              onChange={(e) => setSeed(e.target.value)}
              className="w-full px-3 py-2 border border-slate-300 rounded-md focus:ring-2 focus:ring-blue-500 focus:border-transparent"
            />
          )}
        </div>

        <button
          onClick={handleGenerate}
          disabled={loading}
          className="w-full bg-navy text-white py-2 px-4 rounded-md hover:bg-slate-800 disabled:opacity-50 disabled:cursor-not-allowed font-medium"
        >
          {loading ? 'Generating...' : instanceMode === 'road' ? 'Generate Instance (Road)' : 'Generate Instance'}
        </button>
      </div>

      {/* Routing Controls */}
      {hasInstance && (
        <div className="space-y-4 mb-6 pt-6 border-t border-warm-border">
          <h3 className="text-sm font-semibold text-slate-700 uppercase tracking-wide">
            Solve Routing
          </h3>

          <button
            onClick={() => onSolveRouting('nearest_neighbor')}
            disabled={loading}
            className="w-full bg-blue-600 text-white py-2 px-4 rounded-md hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            Nearest Neighbor
          </button>

          <button
            onClick={() => onSolveRouting('2opt')}
            disabled={loading}
            className="w-full bg-teal-600 text-white py-2 px-4 rounded-md hover:bg-teal-700 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            2-Opt
          </button>
        </div>
      )}

      {/* Evolution Controls */}
      <div className="space-y-4 pt-6 border-t border-warm-border">
        <h3 className="text-sm font-semibold text-slate-700 uppercase tracking-wide">
          Evolution
        </h3>

        {/* Mode Selection */}
        <div>
          <label className="block text-xs font-medium text-slate-600 mb-2">
            Mode
          </label>
          <div className="space-y-2">
            <label className="flex items-center gap-2 cursor-pointer">
              <input
                type="radio"
                checked={evoMode === 'mock'}
                onChange={() => setEvoMode('mock')}
                className="text-purple-600 focus:ring-purple-500"
              />
              <span className="text-sm text-slate-700">
                <strong>Mock</strong> — No API key required (predefined candidates)
              </span>
            </label>
            <label className="flex items-center gap-2 cursor-pointer">
              <input
                type="radio"
                checked={evoMode === 'live'}
                onChange={() => setEvoMode('live')}
                className="text-purple-600 focus:ring-purple-500"
              />
              <span className="text-sm text-slate-700">
                <strong>Live LLM</strong> — Requires .env configuration (real API calls)
              </span>
            </label>
          </div>
          {evoMode === 'live' && (
            <div className="mt-2 p-2 bg-amber-50 border border-amber-200 rounded text-xs text-amber-800">
              <strong>⚠️ Configuration Required:</strong> Backend must have .env file with
              LLM_API_KEY, LLM_BASE_URL, LLM_MODEL, and LLM_PROVIDER. See .env.example.
            </div>
          )}
        </div>

        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="block text-xs font-medium text-slate-600 mb-1">
              Stops
            </label>
            <input
              type="number"
              min="10"
              max="100"
              value={evoNumStops}
              onChange={(e) => setEvoNumStops(parseInt(e.target.value))}
              className="w-full px-2 py-1 text-sm border border-slate-300 rounded focus:ring-1 focus:ring-blue-500"
            />
          </div>

          <div>
            <label className="block text-xs font-medium text-slate-600 mb-1">
              Instances
            </label>
            <input
              type="number"
              min="3"
              max="50"
              value={evoNumInstances}
              onChange={(e) => setEvoNumInstances(parseInt(e.target.value))}
              className="w-full px-2 py-1 text-sm border border-slate-300 rounded focus:ring-1 focus:ring-blue-500"
            />
          </div>

          <div>
            <label className="block text-xs font-medium text-slate-600 mb-1">
              Generations
            </label>
            <input
              type="number"
              min="2"
              max="20"
              value={evoGenerations}
              onChange={(e) => setEvoGenerations(parseInt(e.target.value))}
              className="w-full px-2 py-1 text-sm border border-slate-300 rounded focus:ring-1 focus:ring-blue-500"
            />
          </div>

          <div>
            <label className="block text-xs font-medium text-slate-600 mb-1">
              Candidates
            </label>
            <input
              type="number"
              min="2"
              max="10"
              value={evoCandidates}
              onChange={(e) => setEvoCandidates(parseInt(e.target.value))}
              className="w-full px-2 py-1 text-sm border border-slate-300 rounded focus:ring-1 focus:ring-blue-500"
            />
          </div>
        </div>

        <div>
          <label className="block text-xs font-medium text-slate-600 mb-1">
            Elites Kept
          </label>
          <input
            type="number"
            min="1"
            max="5"
            value={evoElites}
            onChange={(e) => setEvoElites(parseInt(e.target.value))}
            className="w-full px-2 py-1 text-sm border border-slate-300 rounded focus:ring-1 focus:ring-blue-500"
          />
        </div>

        <button
          onClick={handleStartEvolution}
          disabled={loading}
          className="w-full bg-purple-600 text-white py-2 px-4 rounded-md hover:bg-purple-700 disabled:opacity-50 disabled:cursor-not-allowed font-medium"
        >
          {loading ? 'Starting...' : `Run Evolution (${evoMode === 'mock' ? 'Mock' : 'Live'})`}
        </button>

        <p className="text-xs text-slate-500 leading-relaxed">
          {evoMode === 'mock' 
            ? 'Mock mode uses predefined candidates for testing without API calls.'
            : 'Live mode generates real heuristics using the configured LLM. API calls will be made.'
          }
        </p>
      </div>
    </div>
  );
}
