"""Small, explicit product protocol; research controls remain independently available."""
from .models import ExperimentConfig, StrategyConfig, Proposal


def product_proposal_schema():
    """Generation guidance is a subset of the unchanged strict strategy schema.

    The host still validates the response with Proposal and product_proposal;
    Ollama's structured-output formatting is not a trust boundary.
    """
    schema=Proposal.model_json_schema()
    config=schema['$defs']['StrategyConfig']
    properties=config['properties']
    properties['construction'].update(enum=['legacy_2opt','nearest_neighbor_starts'],default='legacy_2opt')
    # Both trusted seeds already cover two_opt alone. Request an actual added
    # neighborhood rather than encouraging the model to repeat a schema default.
    operators=['relocate','swap','or_opt_2','two_opt','cross_relocate','cross_exchange']
    choices=[[op] for op in operators if op!='two_opt']+[[a,b] for a in operators for b in operators if a!=b]
    properties['operators'].pop('default',None)
    properties['operators'].update(minItems=1,maxItems=2,enum=choices)
    properties['nn_attempts'].update(maximum=2,default=1)
    properties['max_operator_calls'].update(minimum=100)
    properties['max_moves_per_operator'].update(minimum=100000,default=100000)
    properties['ils_iterations'].update(maximum=0)
    config['required']=['construction','operators','nn_attempts','max_operator_calls','max_moves_per_operator','ils_iterations']
    return schema


def product_config():
    return ExperimentConfig(proposal_policy='llm_only', search_scope='best_construction',
        case_ids=('development-n20-k2-uniform-symmetric-r0', 'development-n20-k3-clustered-directed-r1'),
        population_size=4, elites=2, generations=2, max_proposals=8, max_llm_calls=6,
        max_evaluations=8, operations_per_evaluation=100000, seconds_per_evaluation=20,
        max_total_operations=800000, max_seconds=180)


def product_seeds():
    return [StrategyConfig(construction='legacy_2opt', operators=('two_opt',)),
            StrategyConfig(construction='nearest_neighbor_starts', nn_attempts=1, operators=('two_opt',))]


def product_proposal(config):
    """Admission, never silently rewrite the model's selected configuration."""
    return (config.construction in ('legacy_2opt', 'nearest_neighbor_starts') and
            1 <= len(config.operators) <= 2 and config.operators!=('two_opt',) and config.nn_attempts <= 2 and
            config.ils_iterations == 0 and config.max_operator_calls >= 100 and
            (config.operators == ('two_opt',) or config.max_moves_per_operator >= 100000))


def application_budget(stops):
    """Host default; explicit request caps (including zero) still take precedence."""
    return min(500000, max(100000, 20 * stops * stops)), min(30., max(15., stops * .15))
