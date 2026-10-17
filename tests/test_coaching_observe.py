"""Local stage matching never calls a remote vision API or mutates the harness."""
import base64
import io
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import MagicMock, patch
from PIL import Image, ImageDraw
import numpy as np

from ori.coaching.observe import observe, validate_result
from ori.coaching.local_vision import canonical, decide, reference_views, LocalStageMatcher
from ori.coaching.paper_vision import previews
from ori.coaching.server import observe_request, OBSERVATION_LOCK
from ori.coaching.paper_playback import compile_playback


def local_result(**overrides):
    return dict(provider='local-dinov2',verdict='match',advance_allowed=True,confidence=None,
                similarity=.96,margin=.08,shape_agreement=.94,
                observation='Visible shape resembles this stage.',instruction='Hold still.',**overrides)


class ObserveTests(unittest.TestCase):
    def setUp(self):
        self.command=dict(name='Fold top down',crease=[[-1,0,0],[1,0,0]],normal=[0,0,1],moving_side='left',angle_degrees=180)
        self.playback=compile_playback([self.command])
        buffer=io.BytesIO()
        Image.new('RGB',(320,240),'white').save(buffer,format='JPEG')
        self.jpeg=buffer.getvalue()
        self.matcher=MagicMock()
        self.matcher.compare.return_value=local_result()

    def test_local_matcher_receives_selected_stage_without_altering_playback(self):
        before=json.dumps(self.playback)
        result=observe(self.matcher,self.playback,[self.command],1,self.jpeg)
        self.assertEqual(result['provider'],'local-dinov2')
        self.assertEqual(self.matcher.compare.call_args.args[2],1)
        self.assertEqual(json.dumps(self.playback),before)

    def test_bad_frames_or_steps_never_reach_encoder(self):
        for step,jpeg in [(99,self.jpeg),(True,self.jpeg),(0,b'not jpeg')]:
            with self.subTest(step=step),self.assertRaises((ValueError,OSError)):
                observe(self.matcher,self.playback,[self.command],step,jpeg)
        self.matcher.compare.assert_not_called()

    def test_ambiguity_and_low_geometry_agreement_hold_stage(self):
        for scores in [(.85,.70,.99),(.96,.80,.5),(float('nan'),.4,.99)]:
            self.assertEqual(decide(*scores),('unclear',False))
        self.assertEqual(decide(.96,.85,.94),('match',True))
        self.assertEqual(decide(.96,.97,.94),('match',True))
        self.assertEqual(decide(.82,.96,.94),('other_stage',False))

    def test_blank_frame_does_not_run_segmentation_or_advance(self):
        matcher=LocalStageMatcher.__new__(LocalStageMatcher)
        matcher.perception=MagicMock()
        result=matcher.compare(self.playback,[self.command],0,Image.new('RGB',(224,224),'white'))
        self.assertEqual(result['verdict'],'unclear')
        self.assertFalse(result['advance_allowed'])
        matcher.perception.predict.assert_not_called()

    def test_neural_mask_drives_shape_matching_on_a_busy_background(self):
        image=Image.new('RGB',(224,224))
        draw=ImageDraw.Draw(image)
        for y in range(0,224,16):
            for x in range(0,224,16):
                draw.rectangle((x,y,x+15,y+15),fill='#24354d' if (x+y)//16%2 else '#bda58a')
        draw.polygon([(112,40),(45,180),(180,180)],fill='orange')
        mask_image=Image.new('L',image.size)
        ImageDraw.Draw(mask_image).polygon([(112,40),(45,180),(180,180)],fill=255)
        mask=np.asarray(mask_image)>0
        _,reference_mask=canonical(image,mask)
        matcher=LocalStageMatcher.__new__(LocalStageMatcher)
        matcher.perception=MagicMock()
        matcher.perception.predict.return_value=([(mask,.99)],np.tile(np.linspace(0,1,224),(224,1)))
        matcher.encode=lambda images: np.array([[1.,0.] for _ in images])
        matcher.references=lambda state: (np.array([[1.,0.]]),[reference_mask])
        result=matcher.compare(self.playback,[self.command],1,image,point=[.5,.5])
        self.assertTrue(result['advance_allowed'])
        self.assertEqual(result['matching_method'],'sam2-outline-and-nn')
        self.assertFalse(result['perception']['depth_used_for_advancement'])
        self.assertEqual(matcher.perception.predict.call_args.args[1],[.5,.5])

    def test_previews_mask_background_and_do_not_present_depth_as_distance(self):
        image=Image.new('RGB',(32,32),'red')
        mask=np.zeros((32,32),dtype=bool);mask[8:24,8:24]=True
        evidence=previews(image,mask,np.ones((32,32)))
        decoded=Image.open(io.BytesIO(base64.b64decode(evidence['mask_preview'].split(',')[1])))
        self.assertEqual(decoded.getpixel((0,0)),(237,240,248))
        self.assertIn('not measured',evidence['depth_kind'])
        self.assertFalse(evidence['depth_used_for_advancement'])

    def test_references_are_built_from_actual_current_geometry(self):
        square=list(reference_views(self.playback['states'][0]))
        triangle=list(reference_views(self.playback['states'][1]))
        self.assertEqual(len(square),12)
        self.assertFalse(np.array_equal(square[0][1],triangle[0][1]))

    def test_server_uses_warm_worker_and_releases_lock_on_failure(self):
        with TemporaryDirectory() as directory:
            base=Path(directory)
            (base/'playback.json').write_text(json.dumps(self.playback))
            (base/'commands.json').write_text(json.dumps(dict(commands=[self.command])))
            body=dict(run_id='lesson',step=1,frame=base64.b64encode(self.jpeg).decode())
            with patch('ori.coaching.server.paper_sources',return_value={'lesson':(base,'Lesson','Paper')}),patch('ori.coaching.server.replay'),patch('ori.coaching.vision_worker.WORKER.request') as worker:
                worker.return_value=local_result()
                self.assertEqual(observe_request(body)['provider'],'local-dinov2')
                self.assertEqual(worker.call_args.args[0]['frame'],body['frame'])
                worker.side_effect=RuntimeError('Local model unavailable')
                with self.assertRaises(RuntimeError):
                    observe_request(body)
                self.assertTrue(OBSERVATION_LOCK.acquire(blocking=False))
                OBSERVATION_LOCK.release()
                worker.reset_mock()
                with self.assertRaises(ValueError):
                    observe_request({**body,'step':100})
                worker.assert_not_called()
                for point in [[-1,.5],[float('nan'),.5],[True,.2],'bad']:
                    with self.assertRaises(ValueError):
                        observe_request({**body,'point':point})
                self.assertEqual(sorted(p.name for p in base.iterdir()),['commands.json','playback.json'])

    def test_gemini_response_and_inconsistent_advance_are_rejected(self):
        valid=local_result()
        for changes in [dict(provider='gemini'),dict(advance_allowed=True,verdict='unclear'),dict(instruction='')]:
            with self.assertRaises(ValueError):
                validate_result({**valid,**changes})


if __name__=='__main__':
    unittest.main()
