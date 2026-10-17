"""Progress from streaming video must remain tied to fresh, current camera evidence."""
from ori.coaching.live_coach import CorrectionCooldown
import unittest
import base64
from ori.coaching.live_coach import ProgressGuard, decode_audio_packet, visual_feedback, stage_instruction, confirmation_instruction, camera_view_continues, CameraEvidence


class ProgressTests(unittest.TestCase):
    def setUp(self):
        self.now=100
        self.guard=ProgressGuard(4,lambda:self.now)
        self.guard.select(1,3)

    def report(self,status='matched',**kwargs):
        return self.guard.report(dict(step=1,epoch=3,status=status,observation='Top edge is folded.',instruction='Align the corners.',fold_location='Top edge',**kwargs))

    def check(self,evidence,**kwargs):
        return self.guard.accept_check(dict(verdict='match',paper_visible=True,closest_state='target',before_excluded=True,unfolded_excluded=True,target_feature='New top flap.',camera_feature='Top flap meets center.',visible_evidence='Top flap meets center.',observation='Top edge is folded.',**kwargs),evidence)

    def test_completion_requires_independent_visible_evidence_and_cannot_repeat(self):
        self.assertIsNone(self.report(paper_visible=True))
        frame=self.guard.capture(1,3,1,b'paper')
        self.assertIsNone(self.report(paper_visible=True))
        event=self.check(frame)
        self.assertEqual(event['status'],'matched');self.assertTrue(event['verified']);self.assertEqual(event['frame_id'],1)
        self.assertIsNone(self.check(frame))

    def test_old_step_epoch_or_frame_cannot_complete(self):
        frame=self.guard.capture(1,3,1,b'paper')
        self.now+=13
        self.assertIsNone(self.check(frame))
        self.guard.select(2,4,1)
        self.assertIsNone(self.check(frame))
        for step,epoch,frame_id in [(1,3,2),(2,3,2),(2,4,1),(True,4,2)]:
            self.assertIsNone(self.guard.capture(step,epoch,frame_id,b'paper'))
        current=self.guard.capture(2,4,2,b'paper')
        self.assertEqual(self.check(current)['status'],'matched')

    def test_previous_pass_and_live_praise_cannot_pass_next_unshown_fold(self):
        previous=self.guard.capture(1,3,1,b'paper')
        self.assertIsNotNone(self.check(previous))
        self.guard.select(2,4,1)
        empty=self.guard.capture(2,4,2,b'empty-camera')
        self.assertIsNone(self.guard.report(dict(step=2,epoch=4,status='matched',paper_visible=True)))
        self.assertIsNone(self.check(previous))
        for result in [dict(verdict='unclear',paper_visible=False,visible_evidence=''),
                       dict(verdict='match',paper_visible=False,visible_evidence='a face'),
                       dict(verdict='match',paper_visible=True,visible_evidence='')]:
            self.assertIsNone(self.guard.accept_check(result,empty))
        self.assertFalse(self.guard.completed)
        shown=self.guard.capture(2,4,3,b'new-paper-result')
        self.assertIsNotNone(self.check(shown))

    def test_paper_presence_and_generic_match_cannot_prove_current_fold(self):
        frame=self.guard.capture(1,3,1,b'paper')
        good=dict(verdict='match',paper_visible=True,closest_state='target',before_excluded=True,
                  unfolded_excluded=True,target_feature='New folded corner.',camera_feature='New corner flap.',visible_evidence='Corner flap.')
        for missing in ['closest_state','before_excluded','unfolded_excluded','target_feature','camera_feature']:
            incomplete={k:v for k,v in good.items() if k!=missing}
            self.assertIsNone(self.guard.accept_check(incomplete,frame),missing)
        for patch in [dict(closest_state='unfolded'),dict(closest_state='before'),dict(closest_state='other'),
                      dict(before_excluded=False),dict(unfolded_excluded=False),dict(camera_feature='')]:
            self.assertIsNone(self.guard.accept_check({**good,**patch},frame))
        self.assertFalse(self.guard.completed)
        self.assertIsNotNone(self.guard.accept_check(good,frame))

    def test_paper_out_of_view_does_not_complete_or_trigger_failure(self):
        self.guard.frame_at=self.now
        self.assertEqual(self.report('out_of_view')['status'],'out_of_view')
        self.assertFalse(self.guard.completed)
        self.assertEqual(self.report('need_view')['status'],'need_view')
        self.assertFalse(self.guard.completed)

    def test_off_camera_work_does_not_trigger_desk_requests_or_timed_nagging(self):
        self.guard.frame_at=self.now
        event=self.guard.report(dict(step=1,epoch=3,status='need_view',paper_visible=False,instruction='Show me your desk'))
        self.assertEqual(event['status'],'out_of_view')
        self.assertEqual(event['instruction'],'Work on your desk; hold the paper up whenever you’re ready.')
        self.assertIsNone(self.report('out_of_view'))
        self.now+=120;self.guard.frame_at=self.now
        self.assertIsNone(self.report('check_in'))
        self.assertIsNone(self.guard.report(dict(step=1,epoch=3,status='matched',paper_visible=False)))
        # When paper is held up again, visible evidence can still complete the fold.
        self.assertEqual(self.check(self.guard.capture(1,3,1,b'paper'))['status'],'matched')

    def test_timed_check_ins_stay_silent(self):
        for elapsed in [0,46,107,500]:
            self.now=100+elapsed;self.guard.frame_at=self.now
            self.assertIsNone(self.report('check_in'))

    def test_spoken_corrections_have_25_second_cooldown(self):
        gate=CorrectionCooldown(lambda:self.now)
        mistake=dict(verdict='mistake',paper_visible=True)
        self.assertTrue(gate.allow(mistake))
        gate.delivered()
        for elapsed in [0,8,24.99]:
            self.now=100+elapsed
            self.assertFalse(gate.allow(mistake))
            self.assertFalse(gate.allow(dict(verdict='unclear',paper_visible=True)))
        self.now=125
        self.assertTrue(gate.allow(mistake))
        self.assertFalse(gate.allow(dict(verdict='unclear',paper_visible=False)))
        self.assertTrue(gate.allow(dict(verdict='before_fold',paper_visible=True)))
        # This gate never handles successful checks; those bypass it entirely.
        self.assertFalse(gate.allow(dict(verdict='match',paper_visible=True)))

    def test_stage_cannot_be_selected_with_a_stale_epoch(self):
        for step,epoch in [(9,4),(1,3),(True,4),(1,True)]:
            with self.assertRaises(ValueError):self.guard.select(step,epoch)

    def test_diagnostics_share_visible_correction_without_authorizing_completion(self):
        frame=self.guard.capture(1,3,1,b'paper')
        text=visual_feedback(dict(verdict='mistake',paper_visible=True,visible_evidence='Right corner overshoots center.',observation='Flap is too far left.',instruction='Move the right corner to the center crease.'),frame)
        self.assertIn('stage=1, epoch=3, camera frame=1',text)
        self.assertIn('Right corner overshoots center.',text)
        self.assertIn('Move the right corner to the center crease.',text)
        self.assertIn('ONE brief reversible correction',text)
        self.assertIn('does NOT pass',text)
        self.assertFalse(self.guard.completed)
        self.guard.select(2,4,1)
        self.assertFalse(self.guard.current_evidence(frame))

    def test_absent_and_ambiguous_diagnostics_do_not_nag_or_invent_mistakes(self):
        frame=self.guard.capture(1,3,1,b'camera')
        absent=visual_feedback(dict(verdict='unclear',paper_visible=False),frame)
        self.assertIn('stay quiet and let them work on the desk',absent)
        ambiguous=visual_feedback(dict(verdict='unclear',paper_visible=True),frame)
        self.assertIn('Ambiguous evidence is not a mistake',ambiguous)
        self.assertIsNone(visual_feedback(dict(verdict='match',paper_visible=True),frame))

    def test_explicit_stage_count_and_final_acknowledgment(self):
        commands=[{'name':'First fold'},{'name':'Final fold'}]
        self.assertIn('total_folds=2, is_final=False',stage_instruction(1,3,commands))
        self.assertIn('total_folds=2, is_final=True',stage_instruction(2,4,commands))
        first=self.guard.capture(1,3,1,b'paper')
        self.assertNotIn('LESSON COMPLETE',confirmation_instruction(first,{'visible_evidence':'flap'},2))
        self.guard.select(2,4,1);last=self.guard.capture(2,4,2,b'paper')
        text=confirmation_instruction(last,{'visible_evidence':'final corner'},2)
        self.assertIn('LESSON COMPLETE',text);self.assertIn('No next step',text)

    def test_departure_invalidates_inflight_positive_even_after_return(self):
        frame=self.guard.capture(1,3,1,b'paper')
        self.guard.capture(1,3,2,b'empty')
        self.report('out_of_view',paper_visible=False)
        self.assertIsNone(self.check(frame))
        returned=self.guard.capture(1,3,3,b'paper')
        self.assertIsNone(self.check(frame))
        self.assertIsNotNone(self.check(returned))

    def test_motion_gate_rejects_removed_moving_and_blurred_paper(self):
        import io
        from PIL import Image,ImageDraw,ImageFilter
        def evidence(image,n):
            buf=io.BytesIO();image.save(buf,format='JPEG')
            return CameraEvidence(1,3,n,100,buf.getvalue())
        desk=Image.new('RGB',(192,192),(50,55,60))
        shown=desk.copy();draw=ImageDraw.Draw(shown)
        draw.rectangle((60,40,130,140),fill='white')
        draw.line((60,40,130,140),fill='black',width=3)
        frame=evidence(shown,1)
        self.assertTrue(camera_view_continues(frame,evidence(shown,2)))
        self.assertFalse(camera_view_continues(frame,evidence(desk,2)))
        self.assertFalse(camera_view_continues(frame,evidence(shown.filter(ImageFilter.GaussianBlur(10)),2)))
        moved=desk.copy();ImageDraw.Draw(moved).rectangle((100,90,170,190),fill='white')
        self.assertFalse(camera_view_continues(frame,evidence(moved,2)))
        self.assertFalse(camera_view_continues(frame,CameraEvidence(1,3,2,100,b'bad-image')))

    def test_microphone_packets_require_bounded_pcm16(self):
        packet=b'\x00\x00'*1600
        self.assertEqual(decode_audio_packet(base64.b64encode(packet).decode()),packet)
        for value in [None,'not-base64!',base64.b64encode(b'x').decode(),base64.b64encode(b'x'*6402).decode()]:
            with self.assertRaises(ValueError):decode_audio_packet(value)


if __name__=='__main__':unittest.main()
