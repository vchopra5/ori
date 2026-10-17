"""Ephemeral Gemini step checks with optional local mask/depth evidence."""
import argparse
import base64
import io
import json
from pathlib import Path


def validate_result(result):
    if not isinstance(result,dict) or result.get('verdict') not in {'match','before_fold','mistake','unclear'}:
        raise ValueError('Invalid observation verdict')
    if result.get('provider') not in {'local-dinov2','gemini-assisted'} or not isinstance(result.get('advance_allowed'),bool):
        raise ValueError('Invalid local observation')
    if result['advance_allowed'] and result['verdict']!='match':
        raise ValueError('Only a match may advance')
    for key in ('observation','instruction'):
        if not isinstance(result.get(key),str) or not result[key].strip():
            raise ValueError('Missing coaching text')
    return result


def observe(matcher,playback,commands,step,jpeg,point=None):
    from PIL import Image
    image=Image.open(io.BytesIO(jpeg))
    if image.format!='JPEG' or not 64<=image.width<=1280 or not 64<=image.height<=1280:
        raise ValueError('Use a JPEG frame between 64 and 1280 pixels per side')
    if isinstance(step,bool) or not isinstance(step,int) or not 0<=step<len(playback['states']):
        raise ValueError('Unknown lesson step')
    image.load()
    return validate_result(matcher.compare(playback,commands,step,image.convert('RGB'),point=point))


def process(body,matcher):
    playback=json.loads(Path(body['playback']).read_text())
    commands=json.loads(Path(body['commands']).read_text())
    if isinstance(commands,dict):
        commands=commands['commands']
    return observe(matcher,playback,commands,body['step'],base64.b64decode(body['frame'],validate=True),body.get('point'))


def main():
    import sys
    from .gemini_coach import GeminiCoach
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--worker',action='store_true')
    parser.add_argument('playback',type=Path,nargs='?')
    parser.add_argument('commands',type=Path,nargs='?')
    parser.add_argument('step',type=int,nargs='?')
    args=parser.parse_args()
    matcher=None
    if args.worker:
        for line in sys.stdin:
            try:
                body=json.loads(line)
                if matcher is None:
                    matcher=GeminiCoach()
                print(json.dumps(process(body,matcher)),flush=True)
            except Exception:
                # Never echo camera contents or arbitrary library error messages.
                print(json.dumps(dict(error='The Gemini step check could not finish. Check your connection and Gemini configuration, then try again.')),flush=True)
    else:
        if args.playback is None or args.commands is None or args.step is None:
            parser.error('Provide playback, commands and step, or --worker')
        body=json.load(sys.stdin)
        body.update(playback=str(args.playback),commands=str(args.commands),step=args.step)
        print(json.dumps(process(body,GeminiCoach())))


if __name__=='__main__':
    main()
