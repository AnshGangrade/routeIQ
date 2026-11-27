"""Explicit real local Ollama smoke; never part of offline tests or held-out evaluation."""
import json
from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import dotenv


def forbidden(*args, **kwargs):
    raise AssertionError('Environment-file access forbidden')


dotenv.load_dotenv=forbidden
dotenv.dotenv_values=forbidden
from fastapi.testclient import TestClient
from api.main import app
from api.routers import strategies
from engine.strategies.provider import ProviderConfig
from engine.strategies.models import StrategyRecord
from engine.strategies.product import product_config
from engine.strategies.evaluation import verify_completed_panel


def main():
    output=Path('runs/workflow-completion-20261127')/('live-'+str(time.time_ns()))
    output.mkdir(parents=True,exist_ok=False)
    strategies.ROOT=output/'experiments'
    provider=ProviderConfig(model='qwen3:1.7b',temperature=.3,timeout=20,retries=1,max_tokens=2048)
    check=strategies.check_provider(provider)
    report={'provider':provider.model_dump(mode='json'),'preflight':check,'live':True,'application':None}
    if check['available']:
        with TestClient(app) as client:
            started=client.post('/api/strategy-experiments',json={'workflow':'ai_product','mode':'ollama','arm':'llm',
                'provider':provider.model_dump(mode='json')})
            started.raise_for_status()
            job_id=started.json()['job_id']
            state=client.get(f'/api/strategy-experiments/{job_id}/export').json()
            report['experiment']=state
            if state['status'] in ('completed','stopped') and state['best_id']:
                winner=StrategyRecord.model_validate(state['records'][state['best_id']])
                assert verify_completed_panel(winner,product_config())
                plan=client.post('/api/instances',json={'mode':'synthetic','num_stops':10,'num_drivers':2,'seed':0}).json()
                applied=client.post('/api/optimization/jobs',json={'instance_id':plan['instance_id'],
                    'method':'strategy','strategy_job_id':job_id,'strategy_id':winner.strategy_id})
                applied.raise_for_status()
                report['application']=client.get('/api/optimization/jobs/'+applied.json()['job_id']).json()
    (output/'report.json').write_text(json.dumps(report,indent=2,allow_nan=False),encoding='utf-8')
    state=report.get('experiment',{})
    print(json.dumps({'output':str(output),'model':provider.model,'available':check['available'],
        'status':state.get('status'),'termination':state.get('termination'),'best_id':state.get('best_id'),
        'provider_usage':state.get('provider_usage'),'rejections':state.get('rejections'),
        'application_status':(report.get('application') or {}).get('status')},indent=2))


if __name__=='__main__': main()
