# RouteIQ Repository Structure

## Top Level
```
routeiq/
├── engine/              # Python optimization package
├── api/                 # FastAPI backend
├── web/                 # React frontend
├── tests/               # pytest test suite
├── runs/                # Saved experiment logs (gitignored)
├── docs/                # Report figures
├── scripts/             # Utilities and benchmark runners
├── .kiro/               # Kiro config and steering
├── README.md
├── requirements.txt
├── pytest.ini
├── .gitignore
├── .env.example
└── Source docs/        # ROUTEIQ_PLAN.md, design docs, synopsis, PPT
```

## Engine Package (engine/)
```
engine/
├── __init__.py
├── instances/          # Instance generator, cost function
├── baselines/          # NN and 2-Opt solvers
├── heuristics/         # Heuristic harness (builds routes from scores)
├── llm/                # LLM client, prompt builder, parser
├── sandbox/            # Code validator and safe execution
├── evaluation/         # Evaluator, fitness scoring
├── evolution/          # Main evolution loop
├── routing/            # Multi-driver routing layer
└── metrics/            # Comparison and reporting
```

## Test Structure (tests/)
```
tests/
├── __init__.py
├── conftest.py         # Shared fixtures
├── test_foundation.py  # Setup verification
├── unit/               # Unit tests per module
└── integration/        # End-to-end tests
```

## Naming Conventions
- Modules: lowercase_with_underscores.py
- Classes: PascalCase
- Functions: lowercase_with_underscores
- Constants: UPPERCASE_WITH_UNDERSCORES
- Test files: test_*.py
- Test functions: test_*

## Module Organization
- One logical component per folder
- Clear __init__.py in each package
- Keep modules focused and cohesive
- Avoid circular dependencies
