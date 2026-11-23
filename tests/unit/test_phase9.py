"""Offline Phase 9 provider preflight; no real provider traffic."""
import httpx
import pytest
from fastapi.testclient import TestClient
from api.main import app
from api.routers import strategies
from engine.strategies.provider import ProviderConfig

@pytest.mark.parametrize('models,available', [([{'name':'qwen3:1.7b'}],True),([{'name':'other'}],False)])
def test_exact_model_inventory(monkeypatch,models,available):
    original=httpx.Client
    transport=httpx.MockTransport(lambda request:httpx.Response(200,json={'models':models}))
    monkeypatch.setattr(httpx,'Client',lambda **kwargs:original(transport=transport,**kwargs))
    result=strategies.check_provider(ProviderConfig(model='qwen3:1.7b'))
    assert result['reachable'] and result['available']==available
    assert result['model']=='qwen3:1.7b'

@pytest.mark.parametrize('failure',['network','malformed','oversize'])
def test_unavailable_and_invalid_are_sanitized(monkeypatch,failure):
    original=httpx.Client
    def response(request):
        if failure=='network':raise httpx.ConnectError('private detail',request=request)
        return httpx.Response(200,content=b'x'*300000 if failure=='oversize' else b'not json')
    monkeypatch.setattr(httpx,'Client',lambda **kwargs:original(transport=httpx.MockTransport(response),**kwargs))
    result=strategies.check_provider(ProviderConfig())
    assert not result['available'] and not result['reachable']
    assert 'private detail' not in str(result)

def test_check_endpoint_preserves_jobs_and_rejects_external_origin(monkeypatch):
    before=dict(strategies.jobs)
    monkeypatch.setattr(strategies,'check_provider',lambda config:dict(configured=True,reachable=False,available=False,model=config.model,message='Start Ollama'))
    with TestClient(app) as client:
        response=client.post('/api/strategy-experiments/provider/check',json={'model':'qwen3:1.7b'})
        assert response.status_code==200 and response.json()['available'] is False
        assert client.post('/api/strategy-experiments/provider/check',json={'endpoint':'https://example.com'}).status_code==422
    assert strategies.jobs==before
