"""Phase 5B: strict paired eligibility, observational ILS and durable experiments."""
from concurrent.futures import Future
from copy import deepcopy
from dataclasses import replace
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from engine.evaluation.fleet_benchmark import BenchmarkConfig, run_case, search_diagnostics
from engine.evaluation.fleet_dataset import cases, digest
from engine.evaluation.fleet_reporting import summarize
from engine.evaluation import fleet_experiment as experiments
from engine.routing.search import SearchConfig, SearchEvent
from scripts.audit_fleet_benchmark import audit_bundle, independent_cost
from scripts.run_fleet_campaign import main as campaign
from tests.unit.test_fleet_benchmark import metric_case, pair, small_problem


def test_only_completed_pairs_enter_any_primary_statistic():
    records = [metric_case(0, 90, 100), metric_case(1, 1, 100, status="incomplete"),
               metric_case(2, 500, 100, status="failed", evaluation_failure=True)]
    p = pair(summarize(records))
    assert p["valid_pairs"] == p["percentage_pairs"] == p["complete_pairs"] == 1
    assert p["improvement_percent"]["mean"] == p["improvement_percent"]["median"] == 10
    assert (p["wins"],p["ties"],p["losses"]) == (1,0,0)
    assert p["excluded_pairs"]["failed"] == p["excluded_pairs"]["incomplete"] == 1
    assert p["unavailable_pairs"] == 2 and p["worst_regression_percent"] == 0


def test_reference_incomplete_is_also_excluded():
    records = [metric_case(0, 50, 100)]
    records[0]["results"][1]["status"] = "incomplete"
    p = pair(summarize(records))
    assert p["valid_pairs"] == 0 and p["improvement_percent"]["mean"] is None


def test_zero_reference_denominator_and_completed_only_zero():
    result = pair(summarize([metric_case(0, 1, 0), metric_case(1, 0, 0),
                             metric_case(2, 0, 100, status="incomplete")]))
    assert result["valid_pairs"] == 2 and result["percentage_pairs"] == 1
    assert result["undefined_percentage_pairs"] == 1
    assert result["improvement_percent"]["mean"] == 0
    assert result["losses"] == 1 and result["ties"] == 1


def test_positive_near_zero_is_not_reported_as_a_zero_distance_tie():
    result=pair(summarize([metric_case(0,1e-12,0)]))
    assert result['losses']==1 and result['ties']==0
    assert result['undefined_percentage_pairs']==1 and result['zero_reference_losses']==1


def test_ils_attempt_is_not_necessarily_a_completed_iteration():
    events = [SearchEvent("vnd", "swap", None, True, 90., 10),
              SearchEvent("perturbation", "swap", None, False, 90., 11),
              SearchEvent("vnd", "relocate", None, True, 85., 20),
              SearchEvent("ils_acceptance", "improvement", None, True, 85., 20),
              SearchEvent("perturbation", "swap", None, False, 85., 21),
              SearchEvent("vnd", "swap", None, True, 80., 30, "interrupted")]
    result = SimpleNamespace(initial_solution=SimpleNamespace(total_distance=100.), events=events,
                             ils_iterations=2, operations_used=30, budget_exhausted=True)
    d = search_diagnostics(result)
    assert d["ils_entered"] and d["pre_ils_best_distance"] == 90
    assert d["ils_iterations_attempted"] == 2 and d["ils_iterations_completed"] == 1
    assert d["ils_global_best_updates"] == 2 and d["ils_found_new_global_best"]
    assert d["global_best_distance_drop_by_operator"] == {"vnd/swap": 10., "ils/swap": 5., "ils/relocate": 5., "ils/improvement": 0.}
    assert d["ils_operations"] == 20 and d["budget_exhausted_during_ils"]


def test_budget_before_ils_has_no_fabricated_iteration_or_benefit():
    result = SimpleNamespace(initial_solution=SimpleNamespace(total_distance=100.),
        events=[SearchEvent("vnd","swap",None,True,90.,10)], ils_iterations=0,
        operations_used=10, budget_exhausted=True)
    d = search_diagnostics(result)
    assert not d["ils_entered"] and not d["ils_found_new_global_best"]
    assert d["budget_exhausted_before_ils"] and d["ils_iterations_completed"] == 0


def test_independent_auditor_checks_costs_coverage_and_directed_arcs():
    p = small_problem(True)
    assert independent_cost(p, ((0,1,2,3,0),)) == (16.,16.)
    for routes in (((0,1,2,0),), ((0,1,1,3,0),), ((0,1,2,3),)):
        with pytest.raises(ValueError): independent_cost(p,routes)


def test_audit_detects_tampered_input_and_cost():
    record = run_case(cases()[0], BenchmarkConfig(operations=0))
    bundle = {"split":"development","protocol":{"protocol_fingerprint":"test"},"cases":[record]}
    audit = audit_bundle(deepcopy(bundle))
    assert audit["method_records_verified"] == 7 and audit["ils"]["entered"] == 0
    corrupted = deepcopy(bundle)
    corrupted["cases"][0]["results"][-1]["total_distance"] = -1
    with pytest.raises(ValueError,match="cost"): audit_bundle(corrupted)
    corrupted = deepcopy(bundle)
    corrupted["cases"][0]["results"][0]["problem_fingerprint"] = "other"
    with pytest.raises(ValueError,match="share"): audit_bundle(corrupted)


class InlinePool:
    """Synchronous executor double; experiment/checkpoint logic is unchanged."""
    def __init__(self, **kwargs): pass
    def __enter__(self): return self
    def __exit__(self, *args): pass
    def submit(self, fn, *args):
        future = Future()
        try: future.set_result(fn(*args))
        except Exception as exc: future.set_exception(exc)
        return future


def test_resume_requires_same_manifest_and_independent_checkpoint_validation(tmp_path,monkeypatch):
    selected = cases()[:2]
    monkeypatch.setattr(experiments,"cases",lambda *a:selected)
    monkeypatch.setattr(experiments,"ProcessPoolExecutor",InlinePool)
    config = BenchmarkConfig(operations=0)
    saved = {"protocol_fingerprint":"test"}
    target = tmp_path/'development'
    first = experiments.run_split('development',config,saved,target)
    monkeypatch.setattr(experiments,"run_case",lambda *a:pytest.fail("completed cases must not rerun"))
    second = experiments.run_split('development',config,saved,target,resume=True)
    assert digest(first['cases']) == digest(second['cases'])
    with pytest.raises(ValueError,match="manifest"):
        experiments.run_split('validation',config,saved,target,resume=True)
    checkpoint = target/'cases'/(selected[0].id+'.json')
    value = json.loads(checkpoint.read_text())
    value['result']['results'][-1]['total_distance']=-1
    checkpoint.write_text(json.dumps(value))
    with pytest.raises(ValueError,match="checksum"):
        experiments.run_split('development',config,saved,target,resume=True)
    value['checksum']=digest(value['result'])
    checkpoint.write_text(json.dumps(value))
    with pytest.raises(ValueError,match="cost"):
        experiments.run_split('development',config,saved,target,resume=True)


def test_resume_never_reruns_partial_campaign_completed_cases(tmp_path,monkeypatch):
    selected=cases()[:2]
    monkeypatch.setattr(experiments,"cases",lambda *a:selected)
    monkeypatch.setattr(experiments,"ProcessPoolExecutor",InlinePool)
    original=experiments.run_case
    def fail_second(case,cfg):
        if case==selected[1]: raise RuntimeError('worker crashed')
        return original(case,cfg)
    # Force deterministic completion ordering for this crash-recovery oracle.
    monkeypatch.setattr(experiments,"as_completed",lambda tasks:iter(tasks))
    monkeypatch.setattr(experiments,"run_case",fail_second)
    target=tmp_path/'development'; cfg=BenchmarkConfig(operations=0); saved={'protocol_fingerprint':'test'}
    with pytest.raises(RuntimeError): experiments.run_split('development',cfg,saved,target)
    assert len(list((target/'cases').glob('*.json')))==1
    called=[]
    def tracking(case,cfg): called.append(case.id); return original(case,cfg)
    monkeypatch.setattr(experiments,'run_case',tracking)
    result=experiments.run_split('development',cfg,saved,target,resume=True)
    assert called==[selected[1].id] and len(result['cases'])==2


def test_campaign_requires_explicit_heldout_ack_before_access():
    with pytest.raises(SystemExit) as exc: campaign(['--protocol','unused','--output','unused'])
    assert exc.value.code == 2


def test_real_process_workers_preserve_case_problem_and_budget():
    from concurrent.futures import ProcessPoolExecutor
    cfg=BenchmarkConfig(operations=0,workers=2)
    selected=cases()[:2]
    with ProcessPoolExecutor(max_workers=2) as pool:
        futures=[pool.submit(run_case,c,cfg) for c in selected]
        results=[f.result(timeout=30) for f in futures]
    assert [r['case_id'] for r in results] == [c.id for c in selected]
    for c,result in zip(selected,results):
        assert result['problem_fingerprint']==c.problem(0).fingerprint
        assert all(r['operations_used']==0 for r in result['results'])


def test_real_ils_escape_is_attributed_to_observed_global_best_events():
    from tests.unit.test_hybrid_search import problem
    from engine.routing.search import solve_hybrid
    result=solve_hybrid(problem(),config=SearchConfig(max_operator_calls=1000,ils_iterations=5),
                        operation_budget=500000,time_limit_seconds=60)
    d=search_diagnostics(result)
    assert d['pre_ils_best_distance']==151 and result.final_solution.total_distance==132
    assert d['ils_entered'] and d['ils_found_new_global_best']
    assert d['ils_iterations_completed']==5
    assert sum(value for key,value in d['global_best_distance_drop_by_operator'].items()
               if key.startswith('ils/'))==19
