"""Undo edits the planned lesson; an unfold remains a physical action."""
import copy,json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import MagicMock,patch
from ori.reconstruction.fold_commands import FoldHarness
from ori.reconstruction.fold_audit import audit
from ori.coaching.jobs import Progress,run_paper
from ori.coaching.paper_playback import compile_playback

FOLD=dict(name='Fold top down',crease=[[-1,0,0],[1,0,0]],normal=[0,0,1],moving_side='left',angle_degrees=180)

class PlanningUndoTests(TestCase):
    def test_undo_restores_topology_contacts_and_history_unlike_unfold(self):
        h=FoldHarness();initial=h.state();h.fold(FOLD)
        folded=h.state()
        inverse={**FOLD,'name':'Unfold','moving_side':'right','angle_degrees':-180,'layers':['paper/m']}
        h.fold(inverse)
        self.assertEqual(len(h.history),2);self.assertGreater(len(h.panels),1)
        self.assertNotEqual(h.state(),initial) # Physical unfolding keeps crease subdivisions.
        result=h.submit(dict(commands=[],undo=1,done=False))
        self.assertTrue(result['ok']);self.assertEqual(h.state(),folded);self.assertEqual(h.history,[FOLD])
        h.submit(dict(commands=[],undo=1))
        self.assertEqual(h.state(),initial);self.assertEqual(h.history,[])

    def test_invalid_undo_is_atomic_and_does_not_erase_rejected_work(self):
        h=FoldHarness();h.fold(FOLD);before=h.state();history=copy.deepcopy(h.history)
        for count in [0,-1,2,True,1.0,'1',None]:
            self.assertFalse(h.submit(dict(commands=[],undo=count))['ok'])
            self.assertEqual(h.state(),before);self.assertEqual(h.history,history)
        for extras in [dict(done=True),dict(commands=[FOLD]),dict(probe=[FOLD]),dict(blocked='x')]:
            self.assertFalse(h.submit(dict(commands=[],undo=1)|extras)['ok']);self.assertEqual(h.state(),before)
        failed=h.submit(dict(commands=[{**FOLD,'angle_degrees':999}]))
        self.assertFalse(failed['ok']);self.assertEqual(h.history,history)
        self.assertTrue(h.submit(dict(commands=[],undo=1))['ok'])

    def test_multi_action_undo_retains_prefix_and_rotation_can_be_undone(self):
        h=FoldHarness();h.fold(FOLD);prefix=h.state()
        turn=dict(type='reorient',origin=[0,0,0],axis=[0,1,0],angle_degrees=180)
        h.fold(turn);h.fold(turn)
        result=h.submit(dict(commands=[],undo=2))
        self.assertEqual(result['undo_count'],2);self.assertEqual(result['undone_commands'],[turn,turn])
        self.assertEqual(h.history,[FOLD]);self.assertEqual(h.state(),prefix)

    def test_undo_rebuilds_live_lesson_and_survives_resume_and_audit(self):
        corrected={**FOLD,'name':'Fold other side','moving_side':'right','angle_degrees':-180}
        outputs=[dict(commands=[FOLD]),dict(commands=[],undo=1),dict(commands=[corrected]),dict(commands=[],done=True)]
        def respond(*args,**kwargs):
            text=json.dumps(outputs.pop(0));return SimpleNamespace(status='completed',output_text=text,model_dump=lambda **_:dict(output_text=text))
        with TemporaryDirectory() as directory,patch('ori.reconstruction.fold_trial.generate_content',side_effect=respond):
            base=Path(directory);url='https://youtu.be/10KurnMH_6o';route=dict(title='Fox',summary='Fox face')
            progress=Progress(base,url);progress.data['route']=route
            run_paper(MagicMock(),url,base,progress,route,max_calls=2)
            self.assertEqual(progress.data['commands'],[]);self.assertEqual(progress.playback['motions'],[])
            self.assertEqual(progress.playback['states'],[FoldHarness().state()])
            self.assertIn('undone',[e['kind'] for e in progress.data['events']]);self.assertTrue(audit(base)['passed'])
            progress=Progress(base,url,resume=True)
            report=run_paper(MagicMock(),url,base,progress,route,max_calls=2,resume=True)
            self.assertEqual(report['status'],'model_claimed_done');self.assertEqual(progress.data['commands'],[corrected])
            self.assertEqual(progress.playback['states'],compile_playback([corrected])['states'])
            self.assertTrue(audit(base)['passed'])
            checkpoint=json.loads((base/'checkpoint.json').read_text())
            self.assertEqual(len(checkpoint['history']),4) # Original mistake and undo remain auditable.
