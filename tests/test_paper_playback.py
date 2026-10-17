import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

import numpy as np

from ori.coaching.paper_playback import compile_playback, cache_key
from ori.coaching import server


class PaperPlaybackTests(unittest.TestCase):
    def test_replay_contains_a_real_rigid_rotation_and_original_final_state(self):
        command = dict(crease=[[-1,0,0],[1,0,0]], normal=[0,0,1], moving_side='left', angle_degrees=180)
        result = compile_playback([command])
        self.assertEqual(len(result['states']),2)
        self.assertEqual(result['motions'][0]['moving'],['paper/m'])
        by_id = {p['id']:p for p in result['states'][-1]}
        for panel in result['motions'][0]['panels']:
            target = by_id[panel['id']]
            for uv, xyz in zip(target['material'],target['vertices']):
                np.testing.assert_allclose(xyz,[uv[0],-abs(uv[1]),0],atol=1e-12)
            self.assertEqual(panel['end_contacts'],target['contacts'])
        self.assertLess(result['metrics']['max_seam_gap'],1e-12)

    def test_library_includes_completed_model_runs_and_excludes_empty_failures(self):
        with TemporaryDirectory() as directory, patch.object(server,'ROOT',Path(directory)):
            root=Path(directory)/'output/fold_trials/runs/video'
            for name,count in [('valid',2),('empty',0)]:
                base=root/name;base.mkdir(parents=True)
                (base/'result.json').write_text(json.dumps(dict(accepted_folds=count,status='model_claimed_done' if count else 'model_reported_blocked',
                    metrics=dict(max_length_error=0,max_seam_gap=0),video_url='https://youtube.com/watch?v=video')))
                (base/'commands.json').write_text('{"commands":[]}')
            library=server.library()
            self.assertEqual(len(library),1)
            self.assertRegex(library[0]['id'],r'^trial-[0-9a-f]{16}$')
            self.assertEqual(server.paper_source(library[0]['id'])[0],root/'valid')
            self.assertEqual(library[0]['replay_url'],'/api/paper/'+library[0]['id'])
            self.assertTrue(library[0]['report']['ok'])

    def test_validated_replay_cache_does_not_spawn_a_simulator_again(self):
        with TemporaryDirectory() as directory:
            base=Path(directory);commands=[]
            (base/'commands.json').write_text('{"commands":[]}')
            (base/'playback.json').write_text(json.dumps(dict(command_hash=cache_key(commands),version=1)))
            with patch.object(server.subprocess,'run') as process:
                self.assertEqual(server.replay(base)['version'],1)
                process.assert_not_called()
