"""Whole-model turns preserve the folded object instead of creating creases."""
import copy
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import MagicMock,patch
import numpy as np
from ori.reconstruction.fold_commands import FoldHarness,PRE_ROTATION_MODEL_INSTRUCTIONS,rotation
from ori.coaching.paper_playback import compile_playback
from ori.reconstruction.fold_trial import run
from ori.reconstruction.fold_audit import audit
from tests.test_fold_trial import reply

ROOT=Path(__file__).resolve().parents[1]
TURN=dict(type='reorient',name='Turn model over',origin=[0,.2,0],axis=[1,0,0],angle_degrees=180)
HALF=dict(name='Fold top down',crease=[[-1,0,0],[1,0,0]],normal=[0,0,1],moving_side='left',angle_degrees=180)

class ReorientationTests(TestCase):
    def test_turning_fox_preserves_all_pairwise_distances_and_contacts(self):
        h=FoldHarness();h.execute(json.loads((ROOT/'examples/fold_commands/fox.json').read_text())['commands'])
        before=copy.deepcopy(h.panels);poses=h.fold(TURN)
        points=np.concatenate([p.xyz for p in before]);distances=np.linalg.norm(points[:,None]-points[None,:],axis=2)
        for fraction,panels in zip(np.linspace(0,1,len(poses)),poses):
            now=np.concatenate([p.xyz for p in panels])
            np.testing.assert_allclose(np.linalg.norm(now[:,None]-now[None,:],axis=2),distances,atol=1e-10)
            matrix=rotation(np.array([1.,0,0]),np.pi*fraction)
            for a,b in zip(before,panels):
                self.assertEqual(a.id,b.id);np.testing.assert_array_equal(a.uv,b.uv)
                self.assertEqual(set(a.contacts),set(b.contacts))
                for other,v in a.contacts.items():np.testing.assert_allclose(b.contacts[other],matrix@v,atol=1e-10)
        h.fold({**TURN,'angle_degrees':-180})
        for a,b in zip(before,h.panels):np.testing.assert_allclose(a.xyz,b.xyz,atol=1e-10)

    def test_reorientation_does_not_make_new_panels_and_subsequent_folds_use_world_frame(self):
        h=FoldHarness();h.fold(dict(type='reorient',origin=[0,0,0],axis=[0,0,1],angle_degrees=90))
        self.assertEqual(len(h.panels),1)
        # Rotating the original horizontal crease 90 degrees gives a vertical crease.
        h.fold({**HALF,'crease':[[0,-1,0],[0,1,0]]})
        reference=FoldHarness();reference.fold(HALF);reference.fold(dict(type='reorient',origin=[0,0,0],axis=[0,0,1],angle_degrees=90))
        for a,b in zip(h.panels,reference.panels):np.testing.assert_allclose(a.xyz,b.xyz,atol=1e-10)

    def test_bad_rotation_is_atomic_and_probe_is_nonmutating(self):
        h=FoldHarness();h.fold(HALF);before=h.state();history=copy.deepcopy(h.history)
        for patch_fields in [dict(axis=[0,0,0]),dict(axis=[1,2]),dict(origin=[float('nan'),0,0]),dict(angle_degrees=0),dict(angle_degrees=181),dict(layers='top'),dict(crease=[[0,0,0],[1,0,0]])]:
            self.assertFalse(h.execute([{**TURN,**patch_fields}])['ok'])
            self.assertEqual(h.state(),before);self.assertEqual(h.history,history)
        result=h.submit(dict(commands=[],probe=[TURN],done=False))
        self.assertTrue(result['probe_result']['ok']);self.assertEqual(h.state(),before)
        replay=compile_playback([HALF,TURN]);motion=replay['motions'][-1]
        self.assertEqual(motion['type'],'reorient');self.assertEqual(set(motion['moving']),{p['id'] for p in replay['states'][-2]})
        self.assertEqual(len(replay['states'][-1]),len(replay['states'][-2]))

    def test_old_contract_can_resume_with_new_rotation_and_remain_auditable(self):
        client=MagicMock();client.interactions.create.side_effect=[reply(json.dumps(dict(commands=[HALF],done=False))),reply(json.dumps(dict(commands=[TURN],done=True)))]
        with TemporaryDirectory() as directory:
            output=Path(directory)
            with patch('ori.reconstruction.fold_trial.MODEL_INSTRUCTIONS',PRE_ROTATION_MODEL_INSTRUCTIONS):
                run(client,'https://youtu.be/10KurnMH_6o','test-model',output,max_calls=1,export=False)
            report=run(client,'https://youtu.be/10KurnMH_6o','test-model',output,max_calls=2,export=False,resume=True)
            self.assertEqual(report['status'],'model_claimed_done');self.assertTrue(audit(output)['passed'])
            request=client.interactions.create.call_args.kwargs
            self.assertIn('Whole-sheet reorientation',request['input'][1]['text'])
