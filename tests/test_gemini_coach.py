"""Gemini sees raw paper, optional auxiliary views, and real harness transitions."""
import io
import json
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock,AsyncMock,patch
from PIL import Image
from ori.coaching.gemini_coach import GeminiCoach, reference_images,snapshot_check
from ori.coaching.paper_vision import png_url
from ori.coaching.paper_playback import compile_playback


class GeminiCoachTests(unittest.TestCase):
    def setUp(self):
        self.command=dict(name='Fold top down',crease=[[-1,0,0],[1,0,0]],normal=[0,0,1],moving_side='left',angle_degrees=180)
        self.playback=compile_playback([self.command])
        self.image=Image.new('RGB',(320,320),'orange')
        self.client=MagicMock()
        self.client.models.generate_content.return_value=SimpleNamespace(text=json.dumps(dict(verdict='match',observation='The paper is a triangle.',instruction='Continue.')))
        self.local=MagicMock()
        self.local.compare.return_value=dict(verdict='unclear',advance_allowed=False,perception={
            'mask_preview':png_url(self.image),'depth_preview':png_url(self.image)})

    def test_raw_camera_optional_views_and_before_mid_target_reach_judge(self):
        before=json.dumps(self.playback)
        result=GeminiCoach(self.client,self.local).compare(self.playback,[self.command],1,self.image)
        self.assertTrue(result['advance_allowed'])
        self.assertEqual(result['provider'],'gemini-assisted')
        contents=self.client.models.generate_content.call_args.kwargs['contents']
        labels=[p.text for p in contents if p.text]
        self.assertTrue(any('CURRENT CAMERA' in label for label in labels))
        for label in ['BEFORE front','MID-FOLD front','TARGET front']:
            self.assertIn(label,labels)
        self.assertEqual(sum(bool(p.inline_data) for p in contents),9)
        self.assertEqual(json.dumps(self.playback),before)

    def test_missing_or_failed_depth_never_blocks_camera_match(self):
        self.local.compare.side_effect=RuntimeError('No local model')
        result=GeminiCoach(self.client,self.local).compare(self.playback,[self.command],1,self.image)
        self.assertTrue(result['advance_allowed'])
        self.assertEqual(result['perception'],{})

    def test_nonmatches_hold_and_invalid_model_outputs_cannot_advance(self):
        for verdict in ['mistake','unclear','before_fold']:
            self.client.models.generate_content.return_value.text=json.dumps(dict(verdict=verdict,observation='Not yet.',instruction='Adjust the last fold.'))
            self.assertFalse(GeminiCoach(self.client,self.local).compare(self.playback,[self.command],1,self.image)['advance_allowed'])
        for output in ['not json','{}','{"verdict":"skip_all"}']:
            self.client.models.generate_content.return_value.text=output
            with self.assertRaises(RuntimeError):GeminiCoach(self.client,self.local).compare(self.playback,[self.command],1,self.image)

    def test_initial_stage_has_only_target_reference(self):
        self.assertEqual([label for label,_ in reference_images(self.playback,0)],['TARGET front','TARGET oblique'])

    def test_compound_midpoint_uses_paths_without_a_single_crease(self):
        # Multi-hinge replays have compiled vertex trajectories, not a crease key.
        motion=self.playback['motions'][0]
        paths=[dict(material=uv,position=xyz) for p in motion['panels'] for uv,xyz in zip(p['material'],p['vertices'])]
        self.playback['motions'][0]=dict(type='compound',panels=motion['panels'],paths=paths,moving=motion['moving'])
        before=json.dumps(self.playback)
        labels=[label for label,_ in reference_images(self.playback,1)]
        self.assertIn('MID-FOLD front',labels)
        self.assertEqual(json.dumps(self.playback),before)


class AsyncSnapshotTests(unittest.IsolatedAsyncioTestCase):
    async def test_ear_mistake_keeps_specific_diagnosis_and_repair(self):
        diagnosis=dict(verdict='mistake',paper_visible=True,closest_state='other',
            before_excluded=True,unfolded_excluded=True,target_feature='Ear points up and outward.',
            camera_feature='Right ear points toward the face.',visible_evidence='Inward-pointing right flap.',
            observation='The right ear points inward toward the face.',
            instruction='Gently reopen the right ear and refold it so its tip points up and away from the face.')
        generate=AsyncMock(return_value=SimpleNamespace(text=json.dumps(diagnosis)))
        client=SimpleNamespace(aio=SimpleNamespace(models=SimpleNamespace(generate_content=generate)))
        result=await snapshot_check(client,{},[{'name':'Form the right ear'}],1,b'camera',[])
        self.assertEqual(result,diagnosis)

    async def test_raw_snapshot_and_trusted_reference_reach_independent_judge(self):
        generate=AsyncMock(return_value=SimpleNamespace(text=json.dumps(dict(verdict='match',paper_visible=True,closest_state='target',before_excluded=True,unfolded_excluded=True,target_feature='New triangular flap.',camera_feature='Top triangle touches center.',visible_evidence='Top flap touches center.',observation='The corner meets the center.',instruction='Continue.'))))
        client=SimpleNamespace(aio=SimpleNamespace(models=SimpleNamespace(generate_content=generate)))
        with patch('ori.coaching.gemini_coach.reference_images',return_value=[('TARGET front',b'reference')]):
            result=await snapshot_check(client,{'states':[[]]},[],0,b'actual-camera')
        self.assertEqual(result['verdict'],'match')
        self.assertEqual(generate.call_args.kwargs['model'],'gemini-3.5-flash-lite')
        config=generate.call_args.kwargs['config']
        self.assertIsNone(config.thinking_config.thinking_budget)
        self.assertEqual(config.thinking_config.thinking_level,'MINIMAL')
        self.assertEqual(config.max_output_tokens,2048)
        parts=generate.call_args.kwargs['contents']
        self.assertEqual([p.inline_data.data for p in parts if p.inline_data],[b'reference',b'actual-camera'])
        # Segmentation/depth previews must not enter this independent judge.
        self.assertEqual(len([p for p in parts if p.inline_data]),2)

    async def test_claimed_matches_require_contrast_against_before_and_unfolded(self):
        valid=dict(verdict='match',paper_visible=True,closest_state='target',before_excluded=True,
                   unfolded_excluded=True,target_feature='New triangular flap at top.',camera_feature='Top flap reaches center.',
                   visible_evidence='Top flap.',observation='Top corner.',instruction='Continue.')
        for contradictory in [dict(closest_state='unfolded'),dict(closest_state='before'),
                              dict(before_excluded=False),dict(unfolded_excluded=False),dict(camera_feature='')]:
            generate=AsyncMock(return_value=SimpleNamespace(text=json.dumps({**valid,**contradictory})))
            client=SimpleNamespace(aio=SimpleNamespace(models=SimpleNamespace(generate_content=generate)))
            result=await snapshot_check(client,{},[{'name':'Fold top corner'}],1,b'camera',[])
            self.assertNotEqual(result['verdict'],'match')
            self.assertNotEqual(result['instruction'],'Continue.')

    async def test_flat_reference_is_provided_beyond_first_fold_without_mid_animation(self):
        generate=AsyncMock(return_value=SimpleNamespace(text=json.dumps(dict(verdict='before_fold',paper_visible=True,
            visible_evidence='Flat sheet.',observation='No fold.',instruction='Fold the corner.'))))
        client=SimpleNamespace(aio=SimpleNamespace(models=SimpleNamespace(generate_content=generate)))
        refs=[('BEFORE front',b'before'),('TARGET front',b'target'),('MID-FOLD front',b'mid')]
        with patch('ori.coaching.gemini_coach.reference_images',return_value=[('TARGET front',b'flat')]):
            await snapshot_check(client,{},[{},{}],2,b'camera',refs)
        parts=generate.call_args.kwargs['contents']
        self.assertEqual([p.inline_data.data for p in parts if p.inline_data],[b'flat',b'before',b'target',b'camera'])
        self.assertIn('UNFOLDED flat sheet',[p.text for p in parts if p.text])

    async def test_absent_paper_or_empty_evidence_cannot_match(self):
        for visible,evidence in [(False,'a face'),(True,'')]:
            generate=AsyncMock(return_value=SimpleNamespace(text=json.dumps(dict(verdict='match',paper_visible=visible,visible_evidence=evidence,observation='Paper',instruction='Continue.'))))
            client=SimpleNamespace(aio=SimpleNamespace(models=SimpleNamespace(generate_content=generate)))
            result=await snapshot_check(client,{},[],0,b'camera',[])
            self.assertNotEqual(result['verdict'],'match')


if __name__=='__main__':unittest.main()
