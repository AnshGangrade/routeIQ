"""Phase 6 offline-first declarative strategies; no environment-file access."""
import argparse
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from engine.strategies.models import ExperimentConfig
from engine.strategies.provider import OfflineProvider,OllamaProvider,ProviderConfig
from engine.strategies.evolution import run_experiment
from engine.strategies.experiment import compare,freeze,evaluate_frozen


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('command',choices=['run','compare','freeze','heldout'])
    p.add_argument('--output',required=True)
    p.add_argument('--input',help='Run directory for freeze, frozen strategy JSON for heldout')
    p.add_argument('--config',help='Explicit non-secret experiment JSON')
    p.add_argument('--mode',choices=['offline','ollama'],default='offline')
    p.add_argument('--arm',choices=['llm','random','hand'],default='llm')
    p.add_argument('--model',default='qwen2.5:7b'); p.add_argument('--endpoint',default='http://127.0.0.1:11434')
    p.add_argument('--temperature',type=float,default=.3); p.add_argument('--timeout',type=float,default=20.)
    p.add_argument('--retries',type=int,default=1); p.add_argument('--max-tokens',type=int,default=2048)
    p.add_argument('--max-response-bytes',type=int,default=65536)
    p.add_argument('--resume',action='store_true'); p.add_argument('--acknowledge-heldout',action='store_true')
    args=p.parse_args(argv)
    try:
        failed=False
        if args.command=='freeze': freeze(args.input,args.output)
        elif args.command=='heldout':
            result=evaluate_frozen(args.input,args.output,acknowledge=args.acknowledge_heldout)
            failed=any(r['status']=='failed' for r in result['rows'])
        else:
            config=ExperimentConfig.model_validate(json.loads(Path(args.config).read_text())) if args.config else ExperimentConfig()
            def provider(): return OfflineProvider() if args.mode=='offline' else OllamaProvider(ProviderConfig(model=args.model,endpoint=args.endpoint,temperature=args.temperature,timeout=args.timeout,retries=args.retries,max_tokens=args.max_tokens,max_response_bytes=args.max_response_bytes))
            if args.command=='compare':
                if args.resume: raise ValueError('Resume individual arm directories with run, not compare')
                result=compare(config,args.output,provider)
                failed=any(r['status']=='failed' for r in result['arms'].values())
            else:
                result=run_experiment(config,args.output,arm=args.arm,provider=provider(),resume=args.resume)
                failed=result['status']=='failed'
        print('Strategy artifacts written:',args.output)
        return int(failed)
    except (ValueError,OSError,TypeError,KeyError):
        p.error('Invalid configuration, protocol or output path; existing artifacts are never replaced by a new experiment')


if __name__=='__main__': raise SystemExit(main())
