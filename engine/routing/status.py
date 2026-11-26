"""Versioned status for newly measured searches; never reinterpret saved records."""

STATUS_SCHEMA = 'fleet-search-status/v2'
RESOURCE_REASONS = {'operation_budget', 'deadline', 'operator_call_limit'}
COMPLETE_REASONS = {'local_search_complete', 'no_perturbation_available', 'ils_iteration_limit'}


def search_status(reason, *, truncated=0, errors=(), route_valid=True):
    failed = bool(errors) or reason in {'operator_error', 'cancellation_error', 'request_failure'}
    state = ('failed' if failed else 'cancelled' if reason == 'cancelled' else
             'completed' if reason in COMPLETE_REASONS and not truncated else
             'unknown' if reason not in COMPLETE_REASONS | RESOURCE_REASONS |
             {'controller_stop', 'neighborhood_limit', 'completed_with_errors'} else 'incomplete')
    return {'schema_version': STATUS_SCHEMA,
            'route_validity': 'validated' if route_valid else 'unverified',
            'search_status': state, 'termination': reason,
            'schedule_completed': state == 'completed',
            'budget_exhausted': reason in RESOURCE_REASONS,
            'neighborhoods_truncated': truncated}
