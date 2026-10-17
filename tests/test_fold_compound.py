import copy
import json
import unittest
import numpy as np
from ori.reconstruction.fold_commands import FoldHarness
from ori.reconstruction.fold_compound import expression
from ori.coaching.paper_playback import compile_playback


def base_commands():
    creases = [[[0,-1,0],[0,1,0]],[[-1,0,0],[1,0,0]],
               [[-.5,-.5,0],[.5,.5,0]],[[-.5,.5,0],[.5,-.5,0]]]
    return [dict(type='precrease', name='Prepare a hinge', crease=c, normal=[0,0,1], moving_side='left') for c in creases]


def collapse():
    # Independent analytic square-base linkage, expressed through the generic
    # mechanism API. No square-base recipe is registered in the harness.
    coordinates = {
        (1,-1): ['cos(b)', '-1', 'sin(b)'],
        (-1,1): ['-1', 'cos(b)', 'sin(b)'],
        (1,1): ['cos(a)', 'cos(a)', 'sqrt(2)*sin(a)'],
        (0,1): ['(cos(a)-1)/2', '(cos(a)+1)/2', 'sin(a)/sqrt(2)'],
        (1,0): ['(cos(a)+1)/2', '(cos(a)-1)/2', 'sin(a)/sqrt(2)'],
    }
    return dict(type='compound',name='Collapse the precreased square together',
        parameters={'a':'pi*t','b':'2*atan2(sqrt(2)*sin(a/2),cos(a/2))'},
        paths=[dict(material=[(x-y)/2,(x+y)/2],
                    position=[f'(({p[0]})-({p[1]}))/2',f'(({p[0]})+({p[1]}))/2',f'({p[2]})/sqrt(2)'])
               for (x,y),p in coordinates.items()])


class CompoundTests(unittest.TestCase):
    def test_collapse_and_replay(self):
        h=FoldHarness()
        self.assertTrue(h.execute(base_commands())['ok'])
        before=copy.deepcopy(h.state())
        poses=h.fold(collapse())
        self.assertEqual(len(h.panels),8)
        self.assertLess(h.metrics()['max_length_error'],1e-8)
        self.assertLess(h.metrics()['max_seam_gap'],1e-8)
        self.assertTrue(all(abs(p.xyz[:,2]).max()<1e-8 for p in h.panels))
        self.assertNotEqual(before,h.state())
        self.assertTrue(h.layer_state()['contacts'])
        replay=compile_playback(h.history)
        self.assertEqual(replay['states'][-1],h.state())
        self.assertEqual(replay['motions'][-1]['type'],'compound')
        # The interior is three-dimensional and metric-preserving, not a flat
        # morph between endpoints.
        self.assertGreater(max(abs(p.xyz[:,2]).max() for p in poses[len(poses)//2]),.5)

    def test_probe_is_nonmutating_and_rejection_atomic(self):
        h=FoldHarness(); before=copy.deepcopy(h.state())
        result=h.submit(dict(commands=[],probe=base_commands()+[collapse()],done=False))
        self.assertTrue(result['probe_result']['ok'],result)
        self.assertEqual(h.state(),before); self.assertEqual(h.history,[])
        h.execute(base_commands()); before=copy.deepcopy(h.state())
        bad=collapse(); bad['paths'][0]['position'][2]='t'
        result=h.execute([bad]); self.assertFalse(result['ok'])
        self.assertIn('constraint',result['error']); self.assertEqual(h.state(),before)
        self.assertEqual(len(h.history),4)

    def test_coordinated_unfold_preserves_contacts_and_continuity(self):
        h=FoldHarness(); h.execute(base_commands()); flat=copy.deepcopy(h.state())
        h.fold(collapse())
        reverse=collapse(); reverse['parameters']['a']='pi*(1-t)'
        h.fold(reverse)
        for p,q in zip(h.state(),flat):
            self.assertTrue(np.allclose(p['vertices'],q['vertices'],atol=1e-8))
        self.assertEqual(h.layer_state()['contacts'],[])

    def test_bad_expressions_and_start(self):
        for value in ['__import__("os")','t.__class__','[t][0]','t**2','sin(t,pi)',float('nan')]:
            with self.assertRaises(ValueError): expression(value)
        h=FoldHarness(); h.execute(base_commands()); c=collapse()
        c['parameters']['a']='pi*(t+0.1)'
        self.assertIn('exact current',h.execute([c])['error'])
        c=collapse();c['paths'][0]['material']=[.123,.456]
        self.assertIn('existing material',h.execute([c])['error'])

class CompoundContinuityTests(unittest.TestCase):
    def test_probe_compaction_resume_and_audit(self):
        from pathlib import Path
        from tempfile import TemporaryDirectory
        from unittest.mock import MagicMock
        from tests.test_fold_context import reply
        from ori.reconstruction.fold_context import DEFAULT_POLICY, compact_context
        from ori.reconstruction.fold_trial import run
        from ori.reconstruction.fold_audit import audit
        bad=collapse(); bad['paths'][0]['position'][2]='t'
        client=MagicMock()
        client.interactions.create.side_effect=[
            reply(dict(commands=base_commands())),
            reply(dict(commands=[],probe=[bad])),
            reply(dict(commands=[],probe=[collapse()])),
            reply(dict(commands=[collapse()],done=True))]
        with TemporaryDirectory() as directory:
            output=Path(directory); args=dict(context_policy=DEFAULT_POLICY,export=False)
            run(client,'url','model',output,max_calls=3,**args)
            saved=json.loads((output/'checkpoint.json').read_text())
            self.assertEqual(len(saved['physics_checkpoint']['physics']['accepted_commands']),4)
            context=compact_context(saved['feedback'],saved['history'],dict(DEFAULT_POLICY,recent_chars=1))
            self.assertEqual(context['failed_move_memory'][0]['command'],bad)
            result=run(client,'url','model',output,max_calls=4,resume=True,**args)
            self.assertEqual(result['accepted_folds'],5)
            self.assertTrue(audit(output)['passed'])

    def test_legacy_session_gains_tools_without_resetting_physics(self):
        from pathlib import Path
        from tempfile import TemporaryDirectory
        from unittest.mock import MagicMock, patch
        from tests.test_fold_context import reply
        from ori.reconstruction.fold_commands import LEGACY_MODEL_INSTRUCTIONS, MODEL_INSTRUCTIONS
        from ori.reconstruction.fold_context import DEFAULT_POLICY
        from ori.reconstruction.fold_trial import run
        from ori.reconstruction.fold_audit import audit
        client=MagicMock()
        client.interactions.create.side_effect=[reply(dict(commands=[])),reply(dict(commands=base_commands()))]
        with TemporaryDirectory() as directory:
            output=Path(directory); args=dict(context_policy=DEFAULT_POLICY,export=False)
            with patch('ori.reconstruction.fold_trial.MODEL_INSTRUCTIONS',LEGACY_MODEL_INSTRUCTIONS):
                run(client,'url','model',output,max_calls=1,**args)
            original=(output/'contract.txt').read_bytes()
            self.assertTrue(audit(output)['passed'])
            run(client,'url','model',output,max_calls=2,resume=True,**args)
            self.assertEqual((output/'contract.txt').read_bytes(),original)
            self.assertEqual(json.loads((output/'config.json').read_text())['action_contract_upgrades'],
                             [dict(after_call=1,instructions=MODEL_INSTRUCTIONS)])
            self.assertTrue(audit(output)['passed'])


if __name__ == "__main__": unittest.main()
