"""Host-owned schemas. A proposal is data, never a callable or source program."""
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator
from engine.evaluation.fleet_dataset import digest, case_by_id
from engine.routing.search import SearchConfig, OPERATORS, CONSTRUCTORS


class StrictModel(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True, allow_inf_nan=False)


class StrategyConfig(StrictModel):
    schema_version: Literal['fleet-strategy/v1'] = 'fleet-strategy/v1'
    construction: Literal['portfolio', 'legacy_2opt', 'nearest_neighbor_starts',
                          'cheapest_insertion', 'contiguous_sweep'] = 'portfolio'
    operators: tuple[Literal['relocate','swap','or_opt_2','two_opt','cross_relocate','cross_exchange'], ...] = tuple(OPERATORS)
    scheduling: Literal['restart_on_improvement'] = 'restart_on_improvement'
    improvement: Literal['best_scanned_strict'] = 'best_scanned_strict'
    perturbation: Literal['seeded_stop_swap'] = 'seeded_stop_swap'
    acceptance: Literal['improve_or_bounded_diversify'] = 'improve_or_bounded_diversify'
    nn_attempts: int = Field(4, strict=True, ge=1, le=16)
    max_operator_calls: int = Field(500, strict=True, ge=0, le=1000)
    max_moves_per_operator: int = Field(10000, strict=True, ge=1, le=100000)
    two_opt_iterations: int = Field(1, strict=True, ge=1, le=100)
    ils_iterations: int = Field(0, strict=True, ge=0, le=100)
    perturbation_moves: int = Field(2, strict=True, ge=1, le=8)
    max_diversifications: int = Field(3, strict=True, ge=0, le=100)

    @model_validator(mode='after')
    def canonical(self):
        if len(set(self.operators)) != len(self.operators):
            raise ValueError('Duplicate operators')
        # Collapse inactive knobs rather than count equivalent configurations.
        updates = {}
        if self.max_operator_calls == 0 or not self.operators:
            updates.update(operators=(), max_operator_calls=0, max_moves_per_operator=10000)
        if 'two_opt' not in updates.get('operators', self.operators): updates['two_opt_iterations'] = 1
        if set(updates.get('operators',self.operators)) <= {'two_opt'}: updates['max_moves_per_operator'] = 10000
        if self.construction not in ('portfolio','nearest_neighbor_starts'): updates['nn_attempts'] = 1
        if self.ils_iterations == 0: updates.update(perturbation_moves=1,max_diversifications=0)
        for key,value in updates.items(): object.__setattr__(self,key,value)
        return self

    @property
    def fingerprint(self): return digest(self.model_dump(mode='json'))

    @property
    def construction_alternatives(self):
        return CONSTRUCTORS if self.construction == 'portfolio' else tuple(dict.fromkeys(('legacy_nn','legacy_2opt',self.construction)))

    def search_config(self):
        return SearchConfig(**{k:getattr(self,k) for k in SearchConfig.__dataclass_fields__})


class Proposal(StrictModel):
    config: StrategyConfig
    rationale: str = Field('', max_length=500)


class StrategyRecord(StrictModel):
    strategy_id: str
    parents: tuple[str, ...] = ()
    generation: int = Field(ge=0)
    config: StrategyConfig
    rationale: str = Field('', max_length=500)
    creation_method: Literal['seed','llm','mutation','crossover','random']
    protected: bool = False
    evaluation_history: tuple[dict, ...] = ()
    fitness: dict = Field(default_factory=dict)
    configuration_fingerprint: str = ''

    @model_validator(mode='after')
    def fingerprint_matches(self):
        if self.configuration_fingerprint and self.configuration_fingerprint!=self.config.fingerprint:
            raise ValueError('Configuration fingerprint mismatch')
        object.__setattr__(self,'configuration_fingerprint',self.config.fingerprint)
        return self


class ExperimentConfig(StrictModel):
    schema_version: Literal['strategy-experiment/v1'] = 'strategy-experiment/v1'
    case_ids: tuple[str, ...] = ('development-n20-k2-uniform-symmetric-r0',)
    seed: int = Field(0, strict=True, ge=0, le=2**32-1)
    search_seed: int = Field(0, strict=True, ge=0, le=2**32-1)
    population_size: int = Field(6, strict=True, ge=4, le=32)
    generations: int = Field(3, strict=True, ge=1, le=100)
    elites: int = Field(2, strict=True, ge=1, le=16)
    max_proposals: int = Field(100, strict=True, ge=4, le=5000)
    max_llm_calls: int = Field(10, strict=True, ge=0, le=100)
    max_evaluations: int = Field(24, strict=True, ge=1, le=10000)
    operations_per_evaluation: int = Field(100000, strict=True, ge=0, le=10000000)
    seconds_per_evaluation: float = Field(10., ge=0, le=120)
    max_total_operations: int = Field(2400000, strict=True, ge=0, le=1000000000)
    max_seconds: float = Field(600., gt=0, le=86400)

    @model_validator(mode='after')
    def panel(self):
        if not 1 <= len(self.case_ids) <= 360 or len(set(self.case_ids)) != len(self.case_ids):
            raise ValueError('Unique nonempty development panel required')
        if any(case_by_id(c).split != 'development' for c in self.case_ids):
            raise ValueError('Evolution accepts development cases only')
        if self.elites >= self.population_size: raise ValueError('Elites must leave offspring slots')
        return self
