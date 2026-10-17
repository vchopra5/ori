"""Render harness-generated paper with its recorded layer contacts."""
import numpy as np
from PIL import Image, ImageDraw
from .fold_layers import ordered


def render(panels, title, oblique=False):
    image = Image.new('RGB', (720, 640), '#f4f1e9')
    draw = ImageDraw.Draw(image)
    draw.text((24, 20), title, fill='#38312b', font_size=22)
    # Fixed camera throughout; oblique view reveals the motion out of plane.
    matrix = np.array([[1, 0, 0], [0, .78, -.63], [0, .63, .78]]) if oblique else np.eye(3)
    for panel in ordered(panels, matrix[2]):
        points = panel.xyz @ matrix.T
        xy = [(360 + 235 * p[0], 300 - 235 * p[1]) for p in points]
        normal = np.cross(panel.xyz[1] - panel.xyz[0], panel.xyz[2] - panel.xyz[0])
        color = '#ef7935' if normal[2] >= 0 else '#e99a55'
        draw.polygon(xy, fill=color)
        draw.line(xy + xy[:1], fill='#8c431e', width=2)
    draw.text((24, 598), 'One square / rigid folds / no cuts or drawn features', fill='#655e54', font_size=18)
    return image



def export_history(commands, output):
    """Replay accepted commands and render their actual intermediate geometry."""
    from pathlib import Path
    from .fold_commands import FoldHarness
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    harness = FoldHarness()
    stills = [render(harness.panels, 'Initial harness state')]
    frames = [render(harness.panels, 'Initial harness state', True)] * 10
    for index, command in enumerate(commands, 1):
        poses = harness.fold(command)
        label = f'Harness fold {index}: ' + str(command.get('name', 'Fold'))
        frames.extend(render(pose, label, True) for pose in poses[::4])
        frames.extend([render(harness.panels, label, True)] * 8)
        stills.append(render(harness.panels, label))
    frames.extend([frames[-1]] * 15)
    frames[0].save(output / 'preview.gif', save_all=True, append_images=frames[1:], duration=80, loop=0)
    stills[-1].save(output / 'final.png')
    sheet = Image.new('RGB', (720 * min(3, len(stills)), 640 * ((len(stills) + 2) // 3)), '#f4f1e9')
    for i, still in enumerate(stills):
        sheet.paste(still, (i % 3 * 720, i // 3 * 640))
    sheet.save(output / 'steps.png')
