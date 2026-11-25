"""Problem-aware Ollama selection and bounded feedback decisions, not model training."""
from copy import deepcopy
import json
from .adaptive_models import AdaptiveRequest, InitialSelection, AdaptiveAction
from .experience import summarize_problem, development_experience
from .provider import AdaptiveOllamaProvider
from engine.routing.control import InitialControl, SearchAction


class ControllerUnavailable(ValueError): pass


class AdaptiveController:
    def __init__(self, request=None, *, provider=None, experience=(), progress=None):
        self.request=request or AdaptiveRequest()
        self.provider=provider or AdaptiveOllamaProvider(self.request.provider)
        self.experience=experience
        self.progress=progress
        self.max_checkpoints=self.request.limits.max_checkpoints
        self.state={'schema':'adaptive-controller/v1','mode':self.provider.mode,
                    'model':self.request.provider.model,'provider':self.request.provider.model_dump(mode='json'),
                    'limits':self.request.limits.model_dump(mode='json'),'calls':0,'reserved_tokens':0,
                    'actual_calls':0,'reported_tokens':0,'usage_known':True,'model_seconds':0.,'decisions':[],
                    'experience_job_ids':list(self.request.experience_job_ids)}

    def snapshot(self):
        from engine.evaluation.fleet_dataset import digest
        value=deepcopy(self.state)
        value['decision_fingerprint']=digest([{'source':d['source'],'proposal':d.get('proposal'),
            'effective_action':d.get('effective_action'),'execution':d.get('execution')} for d in value['decisions']])
        return value
    def close(self):
        if not getattr(self,'closed',False):
            self.closed=True
            self.provider.close()

    def applied(self, decision):
        self.state['decisions'][-1]['execution']=decision
        self._publish()

    def _publish(self):
        if self.progress: self.progress(self.snapshot())

    def _request(self, payload, schema, budget):
        limits=self.request.limits
        charge=limits.context_tokens+self.request.provider.max_tokens
        seconds=min(budget.deadline-budget.clock(),limits.max_model_seconds-self.state['model_seconds'])
        error=None
        if not budget.check(): error=budget.reason
        elif self.state['calls']>=limits.max_calls: error='model_call_limit'
        elif self.state['reserved_tokens']+charge>limits.max_reserved_tokens: error='model_token_limit'
        elif seconds<=0: error='model_time_limit'
        prompt=json.dumps(payload,allow_nan=False,separators=(',',':'))
        if len(prompt.encode('utf-8'))>limits.max_prompt_bytes: error='prompt_limit'
        if error: return None,{'error':error,'calls':0,'tokens':None,'seconds':0.}
        # Reserve worst-case context+output allowance even for invalid/failed requests.
        self.state['calls']+=1; self.state['reserved_tokens']+=charge
        self._publish()
        import time
        started=time.monotonic()
        try:
            proposal,meta=self.provider.request(prompt,schema,seed=self.seed,seconds=seconds,
                context_tokens=limits.context_tokens,cancel=lambda:not budget.check())
            if proposal is not None: proposal=schema.model_validate(proposal.model_dump(mode='json'))
        except Exception:
            proposal=None
            meta={'error':'provider_or_response_failure','calls':1,'tokens':None,'seconds':time.monotonic()-started}
        self.state['model_seconds']+=meta['seconds']
        self.state['actual_calls']+=meta.get('calls',0)
        if meta.get('tokens') is None: self.state['usage_known']=False
        else: self.state['reported_tokens']+=meta['tokens']
        if not budget.check(): return None,{**meta,'error':budget.reason}
        return proposal,meta

    def initialize(self, problem, budget, seed):
        from pathlib import Path
        from engine.evaluation.fleet_benchmark import source_fingerprint
        self.seed=seed
        self.state['search_seed']=seed
        self.state['source_fingerprint']=source_fingerprint(Path(__file__).resolve().parents[2])
        self.state['operation_budget']=budget.limit
        self.state['problem']=summarize_problem(problem)
        experience=development_experience(self.experience,problem,maximum=4)
        self.state['experience']=experience
        payload={'task':'Select an initial supported fleet strategy. Return JSON only. No source code.',
            'problem':self.state['problem'],'development_experience':experience,
            'experience_caution':'Historical data under different budgets, not proof of transfer; null means unavailable.',
            'semantics':'Operator order is priority. Only existing restart VND and bounded seeded stop-swap diversification. Mandatory legacy comparators remain. No weights or unsupported constraints.',
            'host_budget':{'operations':budget.limit,'seconds_remaining':max(0.,budget.deadline-budget.clock()),
                           'checkpoint_slice_range':[100,20000]},
            'schema':InitialSelection.model_json_schema()}
        proposal,meta=self._request(payload,InitialSelection,budget)
        if proposal is None:
            self.state['decisions'].append({'stage':'initial','source':self.source,'accepted':False,'request':meta})
            self._publish()
            raise ControllerUnavailable('AI strategy selection unavailable or invalid; no AI search was started')
        config=proposal.config
        if config.construction=='contiguous_sweep' and (problem.directed or problem.coordinate_system!='cartesian'
                or problem.matrix_provenance.source!='euclidean'):
            self.state['decisions'].append({'stage':'initial','source':self.source,'accepted':False,
                'proposal':proposal.model_dump(mode='json'),'request':{**meta,'error':'inapplicable_construction'}})
            self._publish()
            raise ControllerUnavailable('AI selected a construction unavailable for this problem')
        self.state['strategy_fingerprint']=config.fingerprint
        self.state['decisions'].append({'stage':'initial','source':self.source,'accepted':True,
                                        'proposal':proposal.model_dump(mode='json'),'request':meta})
        self._publish()
        return InitialControl(config.construction,config.search_config(),proposal.operation_slice)

    def checkpoint(self, telemetry, budget):
        payload={'task':'Choose the next bounded search action from measured feedback. Return JSON only.',
            'problem':self.state['problem'],'telemetry':telemetry,
            'semantics':'continue keeps priority; reorder selects an ordered operator subset; diversify uses the existing seeded stop swap only if the host allows it; stop ends search. operation_slice allocates remaining work, never adds work. Stagnation is observed, not proof of optimality.',
            'schema':AdaptiveAction.model_json_schema()}
        proposal,meta=self._request(payload,AdaptiveAction,budget)
        entry={'stage':'checkpoint','telemetry':deepcopy(telemetry),'request':meta,
               'proposal':proposal.model_dump(mode='json') if proposal else None,
               'source':self.source if proposal else 'deterministic fallback','accepted':proposal is not None}
        if proposal is None:
            action=SearchAction()  # Keep trusted schedule; no random substitute.
        else:
            action=SearchAction(proposal.action,proposal.operators,proposal.max_moves,proposal.operation_slice)
        entry['effective_action']={**action.__dict__}
        self.state['decisions'].append(entry); self._publish()
        return action

    @property
    def source(self):
        return 'LLM proposal' if self.provider.mode=='ollama' else 'offline fixture'


class ReplayController:
    """Explicit recorded-decision replay. Never attributed to a new model call."""
    def __init__(self, record):
        from engine.evaluation.fleet_dataset import digest
        if record.get('termination') in ('cancelled','deadline','cancellation_error','operator_error'):
            raise ValueError('Interrupted or failed traces are evidence, not executable replays')
        expected=digest([{'source':d['source'],'proposal':d.get('proposal'),
            'effective_action':d.get('effective_action'),'execution':d.get('execution')} for d in record['decisions']])
        if record.get('decision_fingerprint')!=expected: raise ValueError('Replay decision fingerprint mismatch')
        self.record=deepcopy(record); self.max_checkpoints=len(record['decisions'])-1
        if not 0<=self.max_checkpoints<=8: raise ValueError('Invalid replay length')
        self.index=1

    def initialize(self, problem, budget, seed):
        from pathlib import Path
        from engine.evaluation.fleet_benchmark import source_fingerprint
        if problem.fingerprint!=self.record['problem']['problem_fingerprint']: raise ValueError('Replay problem mismatch')
        if seed!=self.record['search_seed']: raise ValueError('Replay seed mismatch')
        if budget.limit!=self.record['operation_budget']: raise ValueError('Replay work budget mismatch')
        if self.record['source_fingerprint']!=source_fingerprint(Path(__file__).resolve().parents[2]): raise ValueError('Replay source mismatch')
        first=InitialSelection.model_validate(self.record['decisions'][0]['proposal'])
        return InitialControl(first.config.construction,first.config.search_config(),first.operation_slice)

    def checkpoint(self, telemetry, budget):
        item=self.record['decisions'][self.index]; self.index+=1
        expected=item['telemetry']
        for key in ('operations','best_distance','operator_calls'):
            if telemetry[key]!=expected[key]: raise ValueError('Replay trajectory mismatch')
        raw=item['effective_action']
        validated=AdaptiveAction.model_validate(raw)
        return SearchAction(validated.action,validated.operators,validated.max_moves,validated.operation_slice)

    def snapshot(self): return {**deepcopy(self.record),'mode':'recorded decision replay','new_model_calls':0}
    def verify_result(self, result):
        from engine.evaluation.fleet_dataset import digest
        if (result.operations_used!=self.record['operations_used'] or
                result.final_solution.total_distance!=self.record['final_distance'] or
                digest(result.final_solution.routes)!=self.record['final_routes_fingerprint']):
            raise ValueError('Replay final result mismatch')
    def close(self): pass
