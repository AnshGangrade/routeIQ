"""Bounded native Ollama JSON provider; explicit configuration, no dotenv."""
import json
import time
from urllib.parse import urlsplit
import httpx
from pydantic import Field, field_validator
from .models import StrictModel, Proposal


class ProviderConfig(StrictModel):
    model: str = Field('qwen2.5:7b', min_length=1, max_length=128)
    endpoint: str = 'http://127.0.0.1:11434'
    temperature: float = Field(.3, ge=0, le=2)
    timeout: float = Field(20., gt=0, le=120)
    retries: int = Field(1, strict=True, ge=0, le=3)
    max_tokens: int = Field(2048, strict=True, ge=64, le=8192)
    max_response_bytes: int = Field(65536, strict=True, ge=1024, le=262144)

    @field_validator('endpoint')
    @classmethod
    def local_endpoint(cls,value):
        u=urlsplit(value)
        if (u.scheme not in ('http','https') or u.hostname not in ('localhost','127.0.0.1','::1')
                or u.username or u.password or u.query or u.fragment or u.path not in ('','/')):
            raise ValueError('Use a loopback Ollama origin without credentials or paths')
        return value.rstrip('/')


def parse_proposal(text, limit=65536, schema=Proposal):
    if not isinstance(text,str) or len(text.encode('utf-8')) > limit: raise ValueError('Response limit')
    def pairs(items):
        d={}
        for key,value in items:
            if key in d: raise ValueError('Duplicate JSON key')
            d[key]=value
        return d
    def invalid(value): raise ValueError('Nonfinite JSON')
    try:
        return schema.model_validate(json.loads(text,object_pairs_hook=pairs,parse_constant=invalid))
    except (ValueError,TypeError,RecursionError):
        raise ValueError('Invalid declarative proposal') from None


class OfflineProvider:
    """Repeatable structured fixture, selected by request index, never code."""
    mode='offline'
    def __init__(self, responses=None): self.responses=responses or []
    def propose(self,prompt,*,index,allowance,seconds,cancel):
        if not allowance or seconds <= 0 or cancel(): return None, {'calls':0,'tokens':0,'seconds':0.,'error':'cancelled'}
        # Default deliberately repeats a valid seed: duplicate handling is exercised.
        text=self.responses[index % len(self.responses)] if self.responses else '{"config":{"construction":"cheapest_insertion","operators":["two_opt","relocate"],"ils_iterations":0},"rationale":"Offline fixture, not evidence of LLM reasoning."}'
        try: proposal=parse_proposal(text); error=None
        except ValueError: proposal=None; error='invalid_json'
        return proposal,{'calls':1,'tokens':0,'seconds':0.,'error':error,'mode':'offline','monetary_cost':None}
    def close(self): pass


class OllamaProvider:
    mode='ollama'
    def __init__(self,config=None,transport=None):
        self.config=config or ProviderConfig()
        self.client=httpx.Client(transport=transport,trust_env=False,follow_redirects=False)
    def close(self): self.client.close()
    def propose(self,prompt,*,index,allowance,seconds,cancel,schema=None):
        started=time.monotonic(); calls=0; tokens=0; usage_known=True; error='unavailable'
        for _ in range(min(allowance,self.config.retries+1)):
            remaining=seconds-(time.monotonic()-started)
            if cancel() or remaining <= 0: error='cancelled_or_deadline'; break
            calls+=1
            try:
                payload={'model':self.config.model,'stream':False,'think':False,'format':schema or Proposal.model_json_schema(),
                         'messages':[{'role':'user','content':prompt}],
                         'options':{'temperature':self.config.temperature,'num_predict':self.config.max_tokens}}
                data=bytearray()
                with self.client.stream('POST',self.config.endpoint+'/api/chat',json=payload,
                                        timeout=min(remaining,self.config.timeout)) as response:
                    response.raise_for_status()
                    for chunk in response.iter_bytes(chunk_size=4096):
                        if cancel() or time.monotonic()-started >= seconds: raise TimeoutError()
                        data.extend(chunk)
                        if len(data)>self.config.max_response_bytes: raise ValueError()
                body=json.loads(data)
                usage=[body.get('prompt_eval_count'),body.get('eval_count')]
                if all(type(v) is int and v>=0 for v in usage): tokens+=sum(usage)
                else: usage_known=False
                proposal=parse_proposal(body['message']['content'],self.config.max_response_bytes)
                return proposal,{'calls':calls,'tokens':tokens if usage_known else None,
                    'seconds':time.monotonic()-started,'error':None,'mode':'ollama','monetary_cost':None}
            except (httpx.HTTPError,TimeoutError,ValueError,KeyError,TypeError,RecursionError):
                # Never persist response bodies, URLs, credentials or exception text.
                error='provider_or_response_failure'; usage_known=False
        return None,{'calls':calls,'tokens':tokens if usage_known else None,
            'seconds':time.monotonic()-started,'error':error,'mode':'ollama','monetary_cost':None}


class AdaptiveOllamaProvider:
    """One cancellable, total-deadline request per decision; no retry or fallback.

    Async HTTP cancellation closes the response/client even during a slow read.
    Local inference can continue on the server after disconnect; we do not claim
    to kill Ollama's model process or bound its hardware usage.
    """
    mode = 'ollama'

    def __init__(self, config, transport=None):
        self.config, self.transport = config, transport

    def close(self): pass  # Each request owns a context-managed HTTP client.

    def request(self, prompt, schema, *, seed, seconds, context_tokens, cancel):
        import asyncio
        started = time.monotonic()
        meta = {'calls':0, 'tokens':None, 'seconds':0., 'error':None,
                'model':self.config.model, 'source':'LLM proposal'}

        async def exchange():
            payload = {'model':self.config.model,'stream':False,'think':False,
                'format':schema.model_json_schema(), 'messages':[{'role':'user','content':prompt}],
                'options':{'temperature':self.config.temperature,'seed':seed,
                           'num_predict':self.config.max_tokens,'num_ctx':context_tokens}}
            data = bytearray()
            async with httpx.AsyncClient(transport=self.transport,trust_env=False,follow_redirects=False,
                                         timeout=min(seconds,self.config.timeout)) as client:
                async with client.stream('POST',self.config.endpoint+'/api/chat',json=payload) as response:
                    response.raise_for_status()
                    async for chunk in response.aiter_bytes():
                        data.extend(chunk)
                        if len(data)>self.config.max_response_bytes: raise ValueError()
            body = json.loads(data)
            counts = [body.get('prompt_eval_count'),body.get('eval_count')]
            if all(type(v) is int and v>=0 for v in counts): meta['tokens'] = sum(counts)
            if body.get('done') is not True: raise ValueError()
            return parse_proposal(body['message']['content'],self.config.max_response_bytes,schema)

        async def bounded():
            if cancel():
                meta['error']='cancelled'; return None
            if seconds<=0:
                meta['error']='deadline'; return None
            meta['calls']=1
            task=asyncio.create_task(exchange())
            try:
                deadline=time.monotonic()+min(seconds,self.config.timeout)
                while True:
                    if cancel(): meta['error']='cancelled'; return None
                    left=deadline-time.monotonic()
                    if left<=0: meta['error']='timeout'; return None
                    done,_=await asyncio.wait({task},timeout=min(.05,left))
                    if done: return task.result()
            finally:
                if not task.done(): task.cancel()
                await asyncio.gather(task,return_exceptions=True)
        try:
            proposal=asyncio.run(bounded())
        except (httpx.HTTPError,ValueError,KeyError,TypeError,RecursionError):
            proposal=None; meta['error']='provider_or_response_failure'
        meta['seconds']=time.monotonic()-started
        return proposal,meta
