"""Browser/product integration with actual solver and explicitly mocked Ollama HTTP."""
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
import uvicorn
import numpy as np


def forbidden(*args, **kwargs):
    raise AssertionError('Environment files and external HTTP forbidden')


dotenv.load_dotenv = forbidden
dotenv.dotenv_values = forbidden
httpx.HTTPTransport.handle_request = forbidden
httpx.AsyncHTTPTransport.handle_async_request = forbidden

from api.main import app
from api import storage
from api.routers import strategies, optimization, routing
import engine.road
from engine.road.models import RoadDistanceResult
from engine.strategies.provider import OllamaProvider
from engine.routing.validation import validate_fleet_solution

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / 'runs' / 'milestone11-20261128' / ('browser-' + str(time.time_ns()))
OUTPUT.mkdir(parents=True, exist_ok=False)
strategies.ROOT = OUTPUT / 'strategies'
strategies.check_provider = lambda config: dict(status='available', configured=True,
    reachable=True, available=True, model=config.model, message='Available (explicit automated HTTP fixture)')


def fixture_provider(config):
    calls = []
    def respond(request):
        calls.append(request)
        time.sleep(.35)  # Ensure progress/cancellation can be observed in the browser.
        return httpx.Response(200, json={'done': True, 'message': {'content': json.dumps({
            'config': {'construction': 'legacy_2opt', 'operators': ['relocate' if len(calls)==1 else 'swap'],
                       'max_moves_per_operator': 100000}, 'rationale': 'Automated fixture, not live evidence'})},
            'prompt_eval_count': 10, 'eval_count': 20})
    return OllamaProvider(config, httpx.MockTransport(respond))


strategies.OllamaProvider = fixture_provider


def matrix_fixture(coordinates):
    n=len(coordinates)
    matrix=np.array([[0. if i==j else float(100+17*i+31*j) for j in range(n)] for i in range(n)])
    return matrix, RoadDistanceResult(provider='osrm',distances=matrix.tolist(),metadata={'fixture':True})


def geometry_fixture(stored,route):
    if stored['mode']!='road': return None,None,None
    coordinates=[stored['depot_coords'],*stored['stop_coords']]
    points=[]
    for a,b in zip(route,route[1:]):
        x,y=coordinates[a],coordinates[b]
        points.extend([[x[1],x[0]],[(x[1]+y[1])/2+.001,(x[0]+y[0])/2-.001]])
    points.append([coordinates[route[-1]][1],coordinates[route[-1]][0]])
    return points,120.,None


engine.road.create_road_distance_matrix=matrix_fixture
routing.get_route_geometry_if_road=geometry_fixture


def main():
    listener = socket.socket()
    listener.bind(('127.0.0.1', 0))
    server = uvicorn.Server(uvicorn.Config(app, log_level='error'))
    thread = threading.Thread(target=server.run, kwargs={'sockets': [listener]})
    thread.start()
    try:
        deadline = time.monotonic()+10
        while not server.started:
            if not thread.is_alive() or time.monotonic()>deadline: raise RuntimeError('Backend startup failed')
            time.sleep(.05)
        result = subprocess.run(['node', 'web/tests/completed-workflow-browser.mjs',
            str(listener.getsockname()[1]), str(OUTPUT)], cwd=ROOT, timeout=240,
            capture_output=True, text=True, encoding='utf-8',
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform=='win32' else 0)
        print(result.stdout)
        if result.stderr: print(result.stderr, file=sys.stderr)
        if result.returncode: return result.returncode
        audited=[]
        for (instance_id, method), row in storage.routing_results.items():
            problem=storage.instance_store[instance_id]['problem']
            checked=validate_fleet_solution(problem,[d.route for d in row.drivers])
            independent=sum(problem.distance_matrix[a][b] for d in row.drivers for a,b in zip(d.route,d.route[1:]))
            assert row.total_distance==independent==checked.total_distance
            assert row.longest_route_distance==checked.longest_route_distance
            assert row.problem_fingerprint==problem.fingerprint and row.matrix_fingerprint==problem.matrix_fingerprint
            audited.append(dict(instance_id=instance_id,method=method,distance=independent))
        assert len({r['instance_id'] for r in audited if r['method']=='strategy'})==2
        assert any(j['state']['status']=='incomplete' and j['state']['result'] is None for j in optimization.jobs.values())
        assert any(j['state']['status']=='cancelled' for j in strategies.jobs.values())
        (OUTPUT/'independent-audit.json').write_text(json.dumps(audited,indent=2),encoding='utf-8')
        print(f'Independent route/matrix audit: {len(audited)} results passed. Evidence: {OUTPUT}')
        return 0
    finally:
        for job in optimization.jobs.values(): job['cancel'].set()
        for job in strategies.jobs.values(): job['cancel'].set()
        server.should_exit=True
        thread.join(45)
        listener.close()
        if thread.is_alive(): raise RuntimeError('Backend did not stop')


if __name__=='__main__':
    raise SystemExit(main())
