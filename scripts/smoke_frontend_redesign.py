"""Actual local UI/API/solver smoke; external road responses are explicit fixtures."""
import json
from pathlib import Path
import socket
import subprocess
import sys
import threading
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import dotenv
import httpx
import numpy as np
import uvicorn


def forbidden(*args, **kwargs):
    raise AssertionError('Environment files and external HTTP forbidden in Frontend redesign smoke')


dotenv.load_dotenv = forbidden
dotenv.dotenv_values = forbidden
httpx.HTTPTransport.handle_request = forbidden
httpx.AsyncHTTPTransport.handle_async_request = forbidden

from api.main import app
from api import storage
from api.routers import routing, optimization, strategies
import engine.road
from engine.road.models import RoadDistanceResult
from engine.routing.validation import validate_fleet_solution

ROOT = Path(__file__).resolve().parents[1]
strategies.check_provider = lambda config: {'configured': True, 'reachable': False, 'available': False, 'model': config.model, 'message': 'Local Ollama unavailable (offline smoke fixture). Choose Quick strategy experiment.'}
strategies.ROOT = ROOT / 'runs' / 'phase9' / 'smoke-strategies'


def matrix_fixture(coordinates):
    # Deliberately directed, non-Euclidean matrix in meters. No network.
    n = len(coordinates)
    matrix = np.array([[0. if i == j else float(100 + 17*i + 31*j) for j in range(n)] for i in range(n)])
    return matrix, RoadDistanceResult(provider='osrm', distances=matrix.tolist(), metadata={'fixture': True})


def geometry_fixture(stored, route):
    if stored['mode'] != 'road':
        return None, None, None
    if 1 in route:
        return None, None, 'Fixture road geometry unavailable'
    # Multi-segment fixture checks rendering of returned geometry; NOT live roads.
    coordinates = [stored['depot_coords'], *stored['stop_coords']]
    points = []
    for a, b in zip(route, route[1:]):
        x, y = coordinates[a], coordinates[b]
        points.extend([[x[1], x[0]], [(x[1]+y[1])/2+.001, (x[0]+y[0])/2-.001]])
    points.append([coordinates[route[-1]][1], coordinates[route[-1]][0]])
    return points, None, None


engine.road.create_road_distance_matrix = matrix_fixture
routing.get_route_geometry_if_road = geometry_fixture


def main():
    listener = socket.socket()
    listener.bind(('127.0.0.1', 0))
    server = uvicorn.Server(uvicorn.Config(app, log_level='error'))
    thread = threading.Thread(target=server.run, kwargs={'sockets': [listener]})
    thread.start()
    try:
        deadline = time.monotonic()+10
        while not server.started:
            if not thread.is_alive() or time.monotonic()>deadline:
                raise RuntimeError('Backend startup failed')
            time.sleep(.05)
        result = subprocess.run(['node', 'web/tests/product-browser.mjs', str(listener.getsockname()[1])],
            cwd=ROOT, timeout=360, capture_output=True, text=True, encoding='utf-8',
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform=='win32' else 0)
        print(result.stdout)
        if result.stderr:
            print(result.stderr, file=sys.stderr)
        if result.returncode:
            return result.returncode
        audited = []
        for (instance_id, method), row in storage.routing_results.items():
            problem = storage.instance_store[instance_id]['problem']
            measured = validate_fleet_solution(problem, [d.route for d in row.drivers])
            # Independent full edge sum, beyond the canonical validator.
            independent = sum(problem.distance_matrix[a][b] for d in row.drivers for a,b in zip(d.route,d.route[1:]))
            assert abs(row.total_distance-independent)<1e-8
            assert abs(row.longest_route_distance-measured.longest_route_distance)<1e-8
            assert row.matrix_fingerprint == problem.matrix_fingerprint
            assert row.problem_fingerprint == problem.fingerprint
            audited.append({'instance_id':instance_id,'method':method,'distance':independent,'matrix_fingerprint':problem.matrix_fingerprint})
        assert any(j['state']['status']=='cancelled' for j in optimization.jobs.values())
        strategies_used = [row for row in audited if row['method']=='strategy']
        assert len({row['instance_id'] for row in strategies_used})>=2
        (ROOT/'runs/phase9/smoke-measurements.json').write_text(json.dumps(audited,indent=2),encoding='utf-8')
        print(f'Independent matrix/coverage audit: {len(audited)} route results passed; cancellation and two-instance application verified')
        return 0
    finally:
        for job in optimization.jobs.values(): job['cancel'].set()
        for job in strategies.jobs.values(): job['cancel'].set()
        server.should_exit = True
        thread.join(45)
        listener.close()
        if thread.is_alive():
            raise RuntimeError('Backend did not stop cleanly')


if __name__ == '__main__':
    raise SystemExit(main())
