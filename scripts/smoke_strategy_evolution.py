"""Real loopback HTTP smoke; no environment files, live LLMs or road requests."""
import json
from pathlib import Path
import socket
import sys
from threading import Thread
import time
from urllib.request import Request,urlopen
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import dotenv
import httpx
import uvicorn


def forbidden(*args,**kwargs): raise AssertionError('External HTTP/environment-file access prohibited')
dotenv.load_dotenv=forbidden
dotenv.dotenv_values=forbidden
httpx.HTTPTransport.handle_request=forbidden
from api.main import app


def main():
    listener=socket.socket(); listener.bind(('127.0.0.1',0))
    server=uvicorn.Server(uvicorn.Config(app,log_level='error'))
    thread=Thread(target=server.run,kwargs={'sockets':[listener]}); thread.start()
    base='http://127.0.0.1:'+str(listener.getsockname()[1]); checks=0
    def request(path,body=None):
        data=None if body is None else json.dumps(body).encode()
        req=Request(base+path,data=data,headers={'Content-Type':'application/json'})
        with urlopen(req,timeout=10) as response: return json.load(response)
    def terminal(key):
        deadline=time.monotonic()+40
        while time.monotonic()<deadline:
            state=request('/api/strategy-experiments/'+key)
            if state['status'] in ('completed','stopped','failed','cancelled'): return state
            time.sleep(.05)
        raise AssertionError('Job did not reach a terminal state')
    try:
        deadline=time.monotonic()+10
        while not server.started:
            if not thread.is_alive() or time.monotonic()>deadline: raise AssertionError('Backend did not start')
            time.sleep(.05)
        assert request('/api/health')['status']=='ok'; checks+=1
        config={'population_size':4,'generations':2,'max_evaluations':8,'operations_per_evaluation':1000,
                'max_total_operations':8000,'seconds_per_evaluation':5,'max_seconds':20}
        first=request('/api/strategy-experiments',{'config':config})['job_id']; checks+=1
        state=terminal(first); assert state['status']=='completed' and state['best_id']; checks+=1
        prefix='/api/strategy-experiments/'+first
        history=request(prefix+'/history')['history']; assert len(history)==2; checks+=1
        best=request(prefix+'/strategies/'+state['best_id'])
        assert best['fitness']['eligible'] and best['configuration_fingerprint']; checks+=1
        exported=request(prefix+'/export'); assert exported['manifest']['provider_mode']=='offline'; checks+=1
        assert all('source_code' not in record for record in exported['records'].values()); checks+=1
        long_config={**config,'population_size':6,'generations':5,'max_evaluations':20,
                     'operations_per_evaluation':50000,'max_total_operations':1000000}
        second=request('/api/strategy-experiments',{'config':long_config})['job_id']; checks+=1
        request('/api/strategy-experiments/'+second+'/cancel',{})
        assert terminal(second)['status']=='cancelled'; checks+=1
        assert request(prefix)['status']=='completed'; checks+=1
        request('/api/strategy-experiments/'+second+'/resume',{})
        assert terminal(second)['status'] in ('completed','stopped'); checks+=1
        assert request('/api/strategy-experiments/'+second+'/export')['best_id']; checks+=1
        print(f'Phase 6 loopback smoke: {checks} passed, 0 failed')
        return 0
    finally:
        server.should_exit=True; thread.join(10); listener.close()
        if thread.is_alive(): raise AssertionError('Backend did not stop')


if __name__=='__main__': raise SystemExit(main())
