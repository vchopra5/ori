import json
import unittest
from unittest.mock import patch, MagicMock
from contextlib import redirect_stdout
from tempfile import TemporaryDirectory
from pathlib import Path
from types import SimpleNamespace
import io
import httpx
from google import genai
from ori.reconstruction.fold import initial_state, build_fold_request, geometry_issues, fold_document
from ori.reconstruction import extract

URL='https://www.youtube.com/watch?v=GC_Szxdqh2Y'

def observed():
    return SimpleNamespace(status='completed',output_text=json.dumps({'actions':[{'description':'Lift the bottom tip upward','completed':True}]}),model_dump=lambda **_: {'usage':{}})

def state():
    f=initial_state()
    f['vertices_ori:uv']=f['vertices_coords']
    f['vertices_coords']=[[*v,0] for v in f['vertices_coords']]
    f['frame_classes']=['foldedForm']
    return {k:v for k,v in f.items() if not k.startswith('file_')}

class FoldTests(unittest.TestCase):
    def test_video_observation_accepts_an_action_list_without_a_wrapper(self):
        from ori.reconstruction.animation import parse_observation
        actions=[{'description':'Lift the bottom tip'}]
        self.assertEqual(parse_observation(json.dumps(actions)),{'actions':actions})
        self.assertEqual(parse_observation(json.dumps({'actions':actions})),{'actions':actions})
        with self.assertRaises(ValueError):parse_observation('{"unexpected":true}')

    def test_geometry_checks_flag_stretch_without_mutating_output(self):
        f=state();self.assertEqual(geometry_issues(f),[])
        f['vertices_coords'][0][2]=1
        before=json.dumps(f)
        self.assertTrue(any('length' in x for x in geometry_issues(f)))
        self.assertEqual(json.dumps(f),before)
        self.assertTrue(geometry_issues({'frame_title':'Cannot infer this state'}))

    def test_request_passes_sdk_serialization_without_network(self):
        request=build_fold_request(URL,'gemini-3.5-flash',[state()],25,60,30,1)
        self.assertIn('vertices_coords',request['input'][1]['text'])
        self.assertIn('Previous state',request['input'][1]['text'])
        class Intercepted(Exception):pass
        def intercept(client,request,*args,**kwargs):
            data=json.loads(request.content)
            self.assertEqual(data['input'][0]['content'][0]['processing']['end_offset'],'60s')
            raise Intercepted()
        with patch.object(httpx.Client,'send',intercept):
            with genai.Client(api_key='offline-test-key') as client:
                with self.assertRaises(Intercepted):client.interactions.create(**request)

    def test_recipe_resolution_preserves_provenance_and_returns_errors(self):
        from ori.reconstruction.animation import resolve_steps, build_request
        proposed=[{'description':'Collapse square base','recipe':{'name':'square_base'}}]
        result=resolve_steps([],proposed)
        self.assertTrue(result['ok'])
        self.assertEqual(result['steps'][0]['recipe'],proposed[0]['recipe'])
        self.assertIn('r s11',result['steps'][0]['commands'])
        self.assertNotIn('commands',proposed[0])
        self.assertFalse(resolve_steps([],[{'description':'Wrong state','recipe':{'name':'petal_fold'}}])['ok'])
        prompt=build_request(URL,'test',[],0,30,0,1)['input'][1]['text']
        self.assertIn('Prefer the tested upstream recipes',prompt)
        self.assertIn('petal_fold',prompt)

    def test_failed_operation_returns_successful_prefix_state(self):
        from ori.reconstruction.animation import resolve_steps
        result=resolve_steps([], [
            {'description':'Create diagonal','commands':'by2d p0 p2'},
            {'description':'Bad selection','operation':{'name':'align_edge','moving_edge':'s999','target_edge':'s0','seed_face':'f0','direction':'valley'}}])
        self.assertFalse(result['ok'])
        self.assertEqual(result['failed_step'],2)
        self.assertEqual(len(result['resolved_steps']),1)
        self.assertEqual(len(result['state']['segments']),5)
        self.assertIn('BEFORE',result['state_scope'])

    def test_feedback_keeps_prior_failure_summary(self):
        with TemporaryDirectory() as directory:
            state={}
            path=Path(directory)/'checkpoint.json'
            extract.save_feedback(state,{'mode':'probe_result','probe_commands':'bad','engine_feedback':{'ok':False,'error':'Invalid hinge','failed_step':2}},path)
            extract.save_feedback(state,{'mode':'probe_result','probe_commands':'corrected','engine_feedback':{'ok':True}},path)
            history=state['pending_feedback']['recent_attempts']
            self.assertEqual(history[0]['error'],'Invalid hinge')
            self.assertEqual(history[0]['proposal'],'bad')

    def test_operation_probe_then_visual_approval_saves_expanded_commands(self):
        operation={'description':'Align parallel edges','operation':{'name':'align_edge','moving_edge':'s0','target_edge':'s2','seed_face':'f0','direction':'valley'}}
        def reply(data):return SimpleNamespace(status='completed',output_text=json.dumps(data),model_dump=lambda **_: {'usage':{}})
        client=MagicMock();client.interactions.create.side_effect=[observed(),reply({'probe_steps':[operation]}),reply({'steps':[operation]}),reply({'approved':True})]
        with TemporaryDirectory() as directory:
            path=Path(directory)/'GC_Szxdqh2Y.json'
            with patch('google.genai.Client') as factory,patch('ori.config.load_settings',return_value=SimpleNamespace(gemini_api_key='fake')),patch.object(extract,'plan_path',return_value=path),patch('sys.argv',['extract','--duration','30']),patch.object(extract,'publish_preview'),patch.object(extract,'render',return_value=[]),redirect_stdout(io.StringIO()):
                factory.return_value.__enter__.return_value=client
                extract.main()
            steps=json.loads(path.read_text())['steps']
            self.assertEqual(len(steps),1)
            self.assertEqual(steps[0]['operation'],operation['operation'])
            self.assertIn('b3d',steps[0]['commands'])
            self.assertEqual(steps[0]['selection']['moving_points'],['p0','p1'])
            self.assertIn('probe_result',client.interactions.create.call_args_list[2].kwargs['input'][1]['text'])

    def test_eighth_candidate_gets_reserved_review_without_automatic_acceptance(self):
        def reply(data):return SimpleNamespace(status='completed',output_text=json.dumps(data),model_dump=lambda **_: {'usage':{}})
        candidate={'steps':[{'description':'Fold diagonal','commands':'by2d p0 p2\nt 1500 r s4 180 p1'}]}
        for approved in [True,False]:
            with self.subTest(approved=approved),TemporaryDirectory() as directory:
                path=Path(directory)/'GC_Szxdqh2Y.json'
                client=MagicMock();client.interactions.create.side_effect=[observed()]+[reply({'probe':'by2d p0 p2'}) for _ in range(7)]+[reply(candidate),reply({'approved':approved,'reason':'Wrong layer'})]
                with patch('google.genai.Client') as factory,patch('ori.config.load_settings',return_value=SimpleNamespace(gemini_api_key='fake')),patch.object(extract,'plan_path',return_value=path),patch('sys.argv',['extract','--duration','30']),patch.object(extract,'publish_preview') as preview,patch.object(extract,'render',return_value=[]),redirect_stdout(io.StringIO()):
                    factory.return_value.__enter__.return_value=client
                    if approved:extract.main()
                    else:
                        with self.assertRaises(SystemExit):extract.main()
                self.assertEqual(client.interactions.create.call_count,10)
                self.assertIn('FINAL REVIEW',client.interactions.create.call_args_list[-1].kwargs['input'][-1]['text'])
                checkpoint=json.loads(next(Path(directory).glob('**/progress.checkpoint.json')).read_text())
                self.assertEqual(checkpoint['completed_seconds'],30 if approved else 0)
                self.assertEqual(len(checkpoint['steps']),1 if approved else 0)
                self.assertEqual(preview.call_count,1 if approved else 0)
                if not approved:self.assertEqual(checkpoint['pending_feedback']['review_response']['reason'],'Wrong layer')

    def test_runner_saves_native_script_and_preview_without_format_flag(self):
        with TemporaryDirectory() as directory:
            path=Path(directory)/'GC_Szxdqh2Y.json'
            output={'steps':[{'description':'Fold diagonal','commands':'by2d p0 p2\nt 1500 r s4 180 p1'}]}
            result=SimpleNamespace(status='completed',output_text=json.dumps(output),model_dump=lambda **_: {'usage':{}})
            probe=SimpleNamespace(status='completed',output_text=json.dumps({'probe':'by2d p0 p2\nt 1500 r s4 90 p1'}),model_dump=lambda **_: {'usage':{}})
            client=MagicMock();approved=SimpleNamespace(status='completed',output_text='{"approved":true}',model_dump=lambda **_: {'usage':{}});rejected=SimpleNamespace(status='completed',output_text=json.dumps({'approved':False,'reason':'Missing the opposite flap'}),model_dump=lambda **_: {'usage':{}});client.interactions.create.side_effect=[observed(),probe,result,rejected,result,approved]
            with patch('google.genai.Client') as factory,patch('ori.config.load_settings',return_value=SimpleNamespace(gemini_api_key='fake')),patch.object(extract,'plan_path',return_value=path),patch('sys.argv',['extract','--duration','30']),patch.object(extract,'publish_preview') as preview,patch.object(extract,'render',return_value=[]) as render,redirect_stdout(io.StringIO()):
                factory.return_value.__enter__.return_value=client
                extract.main()
            self.assertEqual(json.loads(path.read_text())['steps'],output['steps'])
            self.assertIn('t 1500',path.with_suffix('.txt').read_text())
            self.assertEqual(preview.call_count,1)
            self.assertEqual(render.call_count,3)  # temporary motion, rejected proposal, corrected proposal
            self.assertIn('probe_result',client.interactions.create.call_args_list[2].kwargs['input'][1]['text'])
            self.assertEqual(client.interactions.create.call_count,6)
            self.assertIn('Missing the opposite flap',client.interactions.create.call_args_list[4].kwargs['input'][1]['text'])
            self.assertEqual(len(list(Path(directory).glob('**/*.response.json'))),6)
            self.assertTrue(json.loads(next(Path(directory).glob('**/*.execution.json')).read_text())['ok'])

    def test_motion_choices_are_rendered_and_require_selection_and_review(self):
        def reply(data):return SimpleNamespace(status='completed',output_text=json.dumps(data),model_dump=lambda **_: {'usage':{}})
        step={'description':'Fold diagonal','commands':'by2d p0 p2\nt 1500 r s4 180 p1'}
        choices={'candidates':[{'id':'test-motion','description':'Test motion','step':step,'resolved_step':step,'max_strain':0}],
                 'unavailable':[],'validation':'Test geometry'}
        client=MagicMock();client.interactions.create.side_effect=[observed(),reply({'compare_motions':{'after_steps':[]}}),reply({'select_motion':'test-motion'}),reply({'approved':True})]
        with TemporaryDirectory() as directory:
            path=Path(directory)/'GC_Szxdqh2Y.json'
            with patch('google.genai.Client') as factory,patch('ori.config.load_settings',return_value=SimpleNamespace(gemini_api_key='fake')),patch.object(extract,'plan_path',return_value=path),patch('sys.argv',['extract','--duration','30']),patch.object(extract,'publish_preview') as publish,patch.object(extract,'render',return_value=[]) as render,patch.object(extract,'motion_candidates',return_value=choices),redirect_stdout(io.StringIO()):
                factory.return_value.__enter__.return_value=client
                extract.main()
            self.assertEqual(json.loads(path.read_text())['steps'],[step])
            self.assertEqual(render.call_count,2)  # comparison, then ordinary review
            self.assertEqual(publish.call_count,1)
            prompts=[call.kwargs['input'][1]['text'] for call in client.interactions.create.call_args_list]
            self.assertIn('motion_options',prompts[2])
            self.assertIn('visual_review',prompts[3])
            self.assertNotIn('Actual executed state',prompts[0])
            self.assertIn('Lift the bottom tip upward',prompts[3])
            self.assertNotIn('Actual executed state',prompts[3])
            self.assertEqual(len(list(Path(directory).glob('**/*.motions.json'))),1)

    def test_unknown_motion_selection_cannot_commit(self):
        result=SimpleNamespace(status='completed',output_text='{"select_motion":"invented"}',model_dump=lambda **_: {})
        client=MagicMock();client.interactions.create.side_effect=[observed(),result]
        with TemporaryDirectory() as directory:
            path=Path(directory)/'GC_Szxdqh2Y.json'
            with patch('google.genai.Client') as factory,patch('ori.config.load_settings',return_value=SimpleNamespace(gemini_api_key='fake')),patch.object(extract,'plan_path',return_value=path),patch('sys.argv',['extract','--duration','30']),patch.object(extract,'publish_preview') as publish,redirect_stdout(io.StringIO()):
                factory.return_value.__enter__.return_value=client
                with self.assertRaises(SystemExit):extract.main()
            self.assertFalse(path.exists())
            publish.assert_not_called()
