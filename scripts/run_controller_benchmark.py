"""Four-arm measurement only. Does not load environment files or run held-out data."""
import argparse
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from engine.evaluation.controller_benchmark import ControllerProtocol, freeze_protocol, run, report, write_reports


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command',choices=('freeze','run','audit'))
    parser.add_argument('--output',required=True)
    parser.add_argument('--config',help='Explicit non-secret protocol JSON, freeze only')
    parser.add_argument('--protocol')
    parser.add_argument('--input',help='Saved experiment directory, audit only')
    parser.add_argument('--split',choices=('development','validation'),default='development')
    parser.add_argument('--development',help='Verified development evidence required for validation')
    parser.add_argument('--live',action='store_true',help='Real exact configured Ollama model; otherwise explicit offline fixtures')
    args=parser.parse_args(argv)
    try:
        if args.command=='freeze':
            config=ControllerProtocol.model_validate(json.loads(Path(args.config).read_text(encoding='utf-8'))) if args.config else ControllerProtocol()
            freeze_protocol(config,args.output)
        elif args.command=='run':
            if not args.protocol: raise ValueError('Protocol path required')
            run(json.loads(Path(args.protocol).read_text(encoding='utf-8')),args.output,split=args.split,
                live=args.live,development=args.development)
        else:
            if not args.input: raise ValueError('Input experiment required')
            manifest=json.loads((Path(args.input)/'manifest.json').read_text(encoding='utf-8'))
            result=report(args.input,manifest)
            Path(args.output).mkdir(parents=True,exist_ok=False)
            write_reports(args.output,result)
        print('Artifacts:',args.output)
        return 0
    except (ValueError,OSError,TypeError,KeyError) as exc:
        print(f'Experiment stopped safely ({type(exc).__name__}); no existing evidence was replaced.',file=sys.stderr)
        return 2


if __name__=='__main__': raise SystemExit(main())
