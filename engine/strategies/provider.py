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


def parse_proposal(text, limit=65536):
    if not isinstance(text,str) or len(text.encode('utf-8')) > limit: raise ValueError('Response limit')
    def pairs(items):
        d={}
        for key,value in items:
            if key in d: raise ValueError('Duplicate JSON key')
            d[key]=value
        return d
    def invalid(value): raise ValueError('Nonfinite JSON')
    try:
        return Proposal.model_validate(json.loads(text,object_pairs_hook=pairs,parse_constant=invalid))
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
    def propose(self,prompt,*,index,allowance,seconds,cancel):
        started=time.monotonic(); calls=0; tokens=0; usage_known=True; error='unavailable'
        for _ in range(min(allowance,self.config.retries+1)):
            remaining=seconds-(time.monotonic()-started)
            if cancel() or remaining <= 0: error='cancelled_or_deadline'; break
            calls+=1
            try:
                payload={'model':self.config.model,'stream':False,'format':Proposal.model_json_schema(),
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
