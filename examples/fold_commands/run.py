"""Run fold-command JSON and render engine-computed paper, without an LLM call."""
import argparse
import json
from pathlib import Path

from PIL import Image

from ori.reconstruction.fold_commands import FoldHarness, MODEL_INSTRUCTIONS
from ori.reconstruction.fold_render import render




def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('plan', nargs='?', type=Path, default=Path(__file__).with_name('fox.json'))
    parser.add_argument('--output', type=Path, default=Path('output/fold_commands_fox'))
    args = parser.parse_args()
    plan = json.loads(args.plan.read_text())
    stem = args.plan.stem
    args.output.mkdir(parents=True, exist_ok=True)
    harness = FoldHarness()
    snapshots = [render(harness.panels, '0. Start with one square')]
    frames = [render(harness.panels, '0. Start with one square', True)] * 12
    states = [harness.state()]
    layers = [harness.layer_state()]
    for index, command in enumerate(plan['commands'], 1):
        try:
            poses = harness.fold(command)
        except ValueError as exc:
            report = {'ok': False, 'failed_command': index, 'error': str(exc), 'state': harness.state()}
            (args.output / 'report.json').write_text(json.dumps(report, indent=2))
            raise SystemExit(json.dumps(report, indent=2))
        title = f'{index}. ' + command['name']
        frames.extend(render(pose, title, True) for pose in poses[::2])
        frames.extend([render(harness.panels, title, True)] * 10)
        snapshots.append(render(harness.panels, title))
        states.append(harness.state())
        layers.append(harness.layer_state())
    frames.extend([frames[-1]] * 30)
    frames[0].save(args.output / f'{stem}.gif', save_all=True, append_images=frames[1:], duration=60, loop=0)
    snapshots[-1].save(args.output / f'{stem}.png')
    sheet = Image.new('RGB', (720 * 3, 640 * ((len(snapshots) + 2) // 3)), '#f4f1e9')
    for i, shot in enumerate(snapshots):
        sheet.paste(shot, (i % 3 * 720, i // 3 * 640))
    sheet.save(args.output / 'steps.png')
    report = {'ok': True, 'commands_executed': len(harness.history), **harness.metrics(),
              'layer_contacts': len(harness.layer_state()['contacts']),
              'layer_check': 'Contact order inherited through splits, rotated with packets, and inferred from landing approach; blocked departures and contact cycles rejected.',
              'collision_check': 'Strict noncoplanar crossings sampled at <=3 degree intervals; coplanar overlap and boundary contact permitted.',
              'limitations': ['Zero thickness; no forces, gravity, friction, or permanent creases.',
                              'Layer selection uses whole convex panels; partial exposure requires subdivision.',
                              'Sampled collision checks are not continuous collision certification.']}
    for name, value in [('report.json', report), ('states.json', states), ('layers.json', layers), ('commands.json', plan)]:
        (args.output / name).write_text(json.dumps(value, indent=2) + '\n')
    (args.output / 'model-instructions.txt').write_text(MODEL_INSTRUCTIONS)
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
