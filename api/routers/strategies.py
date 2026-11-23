"""Isolated Phase 6 jobs. Existing /api/evolution contracts are unchanged."""
from copy import deepcopy
import json
import logging
from pathlib import Path
import re
from threading import Event,RLock
import uuid
from fastapi import APIRouter,BackgroundTasks,HTTPException
from typing import Literal
from pydantic import model_validator
from engine.strategies.models import StrictModel,ExperimentConfig
from engine.strategies.provider import ProviderConfig,OfflineProvider,OllamaProvider
from engine.strategies.evolution import run_experiment

router=APIRouter()
ROOT=Path(__file__).resolve().parents[2]/'runs'/'strategy-api'
jobs={}; lock=RLock()
MAX_JOBS=20; MAX_ACTIVE=2


class StartRequest(StrictModel):
    config: ExperimentConfig = ExperimentConfig()
    mode: Literal['offline','ollama'] = 'offline'
    arm: Literal['llm','random','hand'] = 'llm'
    provider: ProviderConfig = ProviderConfig()

    @model_validator(mode='after')
    def admission(self):
        c=self.config
        if (len(c.case_ids)>12 or c.population_size>16 or c.max_proposals>200 or c.max_evaluations>128
                or c.max_seconds>1800 or c.operations_per_evaluation>1000000 or c.max_total_operations>128000000):
            raise ValueError('API experiment exceeds local capstone limits; use the explicit offline CLI')
        return self


def path_for(job_id):
    if not re.fullmatch('[0-9a-f]{32}',job_id): raise HTTPException(404,'Experiment not found')
    return ROOT/job_id


def snapshot(job_id):
    path=path_for(job_id)
    with lock:
        if job_id in jobs: return deepcopy(jobs[job_id]['state'])
    if (path/'checkpoint.json').is_file():
        value=json.loads((path/'checkpoint.json').read_text())
        from engine.evaluation.fleet_dataset import digest
        if digest(value['state'])!=value['checksum']: raise HTTPException(409,'Checkpoint integrity failure')
        value=value['state']
        if value['status']=='running': value['status']='interrupted'
        return value
    raise HTTPException(404,'Experiment not found')


def execute(job_id,request,resume):
    entry=jobs[job_id]
    def progress(state):
        with lock: entry['state']=state
    try:
        provider=OfflineProvider() if request.mode=='offline' else OllamaProvider(request.provider)
        state=run_experiment(request.config,path_for(job_id),arm=request.arm,provider=provider,resume=resume,
            cancel=entry['cancel'].is_set,progress=progress)
        progress(state)
    except Exception as exc:
        logging.getLogger(__name__).warning('strategy_experiment_failed',extra={'job_id':job_id,'error_type':type(exc).__name__})
        with lock: entry['state'].update(status='failed',termination='experiment_failure')


def register(job_id,request,tasks,resume=False):
    with lock:
        active=sum(j['state']['status'] in ('pending','running','cancelling') for j in jobs.values())
        if active>=MAX_ACTIVE or (job_id not in jobs and len(jobs)>=MAX_JOBS): raise HTTPException(429,'Strategy experiment capacity reached')
        if job_id in jobs and jobs[job_id]['state']['status'] in ('pending','running','cancelling'):
            raise HTTPException(409,'Experiment already active')
        jobs[job_id]={'state':{'status':'pending','job_id':job_id},'cancel':Event()}
    tasks.add_task(execute,job_id,request,resume)
    return {'job_id':job_id,'status':'pending'}


@router.post('')
def start(request:StartRequest,tasks:BackgroundTasks):
    return register(uuid.uuid4().hex,request,tasks)


def check_provider(config):
    """Bounded loopback-only model inventory probe; never generates proposals."""
    import httpx
    import time
    started=time.monotonic()
    try:
        with httpx.Client(trust_env=False, follow_redirects=False, timeout=3.) as client:
            with client.stream('GET', config.endpoint+'/api/tags') as response:
                response.raise_for_status()
                data=bytearray()
                for chunk in response.iter_bytes(chunk_size=4096):
                    data.extend(chunk)
                    if time.monotonic()-started>3 or len(data)>262144: raise ValueError('Inventory too large')
            body=json.loads(data)
            if not isinstance(body,dict): raise ValueError('Invalid inventory')
            models=body.get('models',[])
            if not isinstance(models,list): raise ValueError('Invalid model list')
            available=any(isinstance(m,dict) and m.get('name')==config.model for m in models)
            return {'configured':True,'reachable':True,'available':available,'model':config.model,
                    'message':'Model available' if available else 'Model is not installed in Ollama. Install the exact model shown in Advanced settings, then retry.'}
    except (httpx.HTTPError,ValueError,TypeError,KeyError):
        return {'configured':True,'reachable':False,'available':False,'model':config.model,
                'message':'Cannot reach local Ollama or read its model inventory. Start Ollama and retry, or choose Quick strategy experiment.'}


@router.post('/provider/check')
def provider_check(config:ProviderConfig):
    return check_provider(config)


@router.get('/{job_id}')
def status(job_id:str):
    state=snapshot(job_id)
    return {'job_id':job_id,**{k:state.get(k) for k in ('status','termination','generation','best_id','reserved_evaluations','actual_operations','llm_calls','elapsed_seconds')}}


@router.get('/{job_id}/history')
def history(job_id:str): return {'job_id':job_id,'history':snapshot(job_id).get('history',[])}


@router.get('/{job_id}/strategies/{strategy_id}')
def strategy(job_id:str,strategy_id:str):
    record=snapshot(job_id).get('records',{}).get(strategy_id)
    if record is None: raise HTTPException(404,'Strategy not found in this experiment')
    return record


@router.get('/{job_id}/export')
def export(job_id:str): return snapshot(job_id)


@router.post('/{job_id}/cancel')
def cancel(job_id:str):
    path_for(job_id)
    with lock:
        if job_id not in jobs: raise HTTPException(404,'Active experiment not found')
        entry=jobs[job_id]
        if entry['state']['status'] in ('pending','running','cancelling'):
            entry['cancel'].set(); entry['state']['status']='cancelling'
        return {'job_id':job_id,'status':entry['state']['status']}


@router.post('/{job_id}/resume')
def resume(job_id:str,tasks:BackgroundTasks):
    state=snapshot(job_id)
    if state['status'] in ('pending','running','cancelling','completed'): raise HTTPException(409,'Experiment is active or complete')
    try:
        m=state['manifest']
        request=StartRequest(config=ExperimentConfig.model_validate(m['config']),mode=m['provider_mode'],
                             arm=m['arm'],
                             provider=ProviderConfig.model_validate(m['provider_config'] or {}))
    except (KeyError,ValueError): raise HTTPException(409,'Checkpoint configuration invalid') from None
    return register(job_id,request,tasks,resume=True)
