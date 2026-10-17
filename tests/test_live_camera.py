"""Pair visual checks with the newest actual camera frame, after generation ends."""
import asyncio
import base64
from contextlib import asynccontextmanager
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock,patch
from google.genai import types
from ori.coaching.live_coach import relay


class CameraTests(unittest.IsolatedAsyncioTestCase):
    async def test_generation_complete_is_forwarded_without_waiting_for_turn_complete(self):
        now=[100.0];parts=[];socket_messages=[];response_done=asyncio.Event();responses=asyncio.Queue()
        first=b'\xff\xd8'+b'a'*120;latest=b'\xff\xd8'+b'b'*120
        class Session:
            async def record_turn(self,turns,turn_complete):parts.append(turns.parts)
            async def send_realtime_input(self,**kwargs):
                if 'text' in kwargs:
                    await self.record_turn(types.Content(parts=[types.Part.from_text(text=kwargs['text'])]),'Paper is absent: stay quiet' not in kwargs['text'])
                if kwargs.get('video') and kwargs['video'].data==first:
                    await responses.put(types.LiveServerMessage(server_content=types.LiveServerContent(
                        model_turn=types.Content(parts=[types.Part.from_bytes(data=b'\x00\x00'*100,mime_type='audio/pcm;rate=24000')]))))
                    await responses.put(types.LiveServerMessage(server_content=types.LiveServerContent(generation_complete=True)))
                    await response_done.wait()
            async def receive(self):
                while True:yield await responses.get()
        session=Session()
        @asynccontextmanager
        async def connect(**kwargs):yield session
        client=SimpleNamespace(aio=SimpleNamespace(live=SimpleNamespace(connect=connect),aclose=AsyncMock()))
        class Socket:
            async def send(self,raw):
                import json
                message=json.loads(raw);socket_messages.append(message)
                if message['type']=='response_complete':response_done.set()
            async def __aiter__(self):
                import json
                yield json.dumps(dict(type='stage',step=0,epoch=1))
                for frame_id,frame in enumerate((first,latest),1):
                    now[0]+=1
                    yield json.dumps(dict(type='frame',step=0,epoch=1,frame_id=frame_id,data=base64.b64encode(frame).decode()))
        with patch('google.genai.Client',return_value=client),patch('ori.config.load_settings',return_value=SimpleNamespace(gemini_api_key='test')),patch('ori.coaching.gemini_coach.reference_images',return_value=[]),patch('ori.coaching.live_coach.time',SimpleNamespace(monotonic=lambda:now[0])):
            await asyncio.wait_for(relay(Socket(),{'states':[[]]},[]),3)
        snapshots=[p.inline_data.data for message in parts for p in message if p.inline_data]
        self.assertEqual(snapshots,[])  # No competing periodic Live judge turns.
        self.assertTrue(any(m['type']=='response_complete' for m in socket_messages))
        self.assertFalse(any(m['type']=='turn_complete' for m in socket_messages))
        client.aio.aclose.assert_awaited_once()

    async def test_background_findings_reach_live_and_duplicate_mistakes_stay_quiet(self):
        import json
        now=[100.0];sent=[];responses=asyncio.Queue()
        first_tip=asyncio.Event();second_check=asyncio.Event();absent_context=asyncio.Event();checks=[]
        class Session:
            async def record_turn(self,turns,turn_complete):
                text=' '.join(p.text for p in turns.parts if p.text)
                sent.append((text,turn_complete))
                if turn_complete:
                    await responses.put(types.LiveServerMessage(server_content=types.LiveServerContent(generation_complete=True)))
                if 'VISUAL DIAGNOSIS' in text:
                    if '"paper_visible": false' in text:absent_context.set()
                    else:first_tip.set()
            async def send_realtime_input(self,**kwargs):
                if 'text' in kwargs:
                    await self.record_turn(types.Content(parts=[types.Part.from_text(text=kwargs['text'])]),'Paper is absent: stay quiet' not in kwargs['text'])
            async def receive(self):
                while True:yield await responses.get()
        @asynccontextmanager
        async def connect(**kwargs):yield Session()
        client=SimpleNamespace(aio=SimpleNamespace(live=SimpleNamespace(connect=connect),aclose=AsyncMock()))
        async def check(*args):
            checks.append(args)
            if len(checks)==2:second_check.set()
            return dict(verdict='mistake' if len(checks)<3 else 'unclear',paper_visible=len(checks)<3,
                        visible_evidence='Right corner overshoots center.' if len(checks)<3 else '',
                        observation='Corner too far left.',instruction='Align the right corner with the center crease.')
        class Socket:
            async def send(self,raw):pass
            async def __aiter__(self):
                yield json.dumps(dict(type='stage',step=1,epoch=1))
                for frame_id in (1,2,3):
                    now[0]+=1
                    yield json.dumps(dict(type='frame',step=1,epoch=1,frame_id=frame_id,data=base64.b64encode(b'\xff\xd8'+b'a'*120).decode()))
                    if frame_id==1:await first_tip.wait()
                    elif frame_id==2:
                        await second_check.wait();await asyncio.sleep(.15)
                    else:await absent_context.wait()
        with patch('google.genai.Client',return_value=client),patch('ori.config.load_settings',return_value=SimpleNamespace(gemini_api_key='test')),patch('ori.coaching.gemini_coach.reference_images',return_value=[]),patch('ori.coaching.gemini_coach.snapshot_check',side_effect=check),patch('ori.coaching.live_coach.time',SimpleNamespace(monotonic=lambda:now[0])):
            await asyncio.wait_for(relay(Socket(),{'states':[[],[]]},[{'name':'Fold corner'}]),3)
        diagnoses=[(text,speak) for text,speak in sent if 'VISUAL DIAGNOSIS' in text]
        self.assertEqual(len(checks),3)
        self.assertEqual(len(diagnoses),2)
        self.assertTrue(diagnoses[0][1]);self.assertIn('Right corner overshoots center.',diagnoses[0][0])
        self.assertIn('Align the right corner with the center crease.',diagnoses[0][0])
        self.assertFalse(diagnoses[1][1]);self.assertIn('stay quiet and let them work on the desk',diagnoses[1][0])

    async def test_delayed_match_is_dropped_when_paper_leaves_during_check(self):
        import io,json
        from PIL import Image,ImageDraw
        now=[100.0];responses=asyncio.Queue();events=[]
        checking=asyncio.Event();removed=asyncio.Event();empty_checked=asyncio.Event();passed=asyncio.Event()
        desk=Image.new('RGB',(192,192),'gray');paper=desk.copy()
        ImageDraw.Draw(paper).rectangle((40,40,140,140),fill='white')
        def jpeg(im):
            buf=io.BytesIO();im.save(buf,format='JPEG');return buf.getvalue()
        shown,empty=jpeg(paper),jpeg(desk)
        class Session:
            async def send_realtime_input(self,**kwargs):
                if 'text' in kwargs:
                    await responses.put(types.LiveServerMessage(server_content=types.LiveServerContent(generation_complete=True)))
            async def receive(self):
                while True:yield await responses.get()
        @asynccontextmanager
        async def connect(**kwargs):yield Session()
        client=SimpleNamespace(aio=SimpleNamespace(live=SimpleNamespace(connect=connect),aclose=AsyncMock()))
        calls=[]
        async def check(*args):
            calls.append(args[4])
            if len(calls)==1:
                checking.set();await removed.wait()
            if args[4]==empty:
                empty_checked.set()
                return dict(verdict='unclear',paper_visible=False,observation='Absent',instruction='Wait')
            return dict(verdict='match',paper_visible=True,closest_state='target',before_excluded=True,
                unfolded_excluded=True,target_feature='Flap',camera_feature='Flap',visible_evidence='Flap',observation='Fold')
        class Socket:
            async def send(self,raw):
                event=json.loads(raw);events.append(event)
                if event.get('status')=='matched':passed.set()
            async def __aiter__(self):
                yield json.dumps(dict(type='stage',step=1,epoch=1))
                for n,pixels in [(1,shown),(2,empty),(3,shown)]:
                    now[0]+=1
                    yield json.dumps(dict(type='frame',step=1,epoch=1,frame_id=n,data=base64.b64encode(pixels).decode()))
                    if n==1:await checking.wait()
                    elif n==2:
                        removed.set();await empty_checked.wait()
                        assert not passed.is_set(), 'Old paper frame must not pass after removal'
                    else:await passed.wait()
        with patch('google.genai.Client',return_value=client),patch('ori.config.load_settings',return_value=SimpleNamespace(gemini_api_key='test')),patch('ori.coaching.gemini_coach.reference_images',return_value=[]),patch('ori.coaching.gemini_coach.snapshot_check',side_effect=check),patch('ori.coaching.live_coach.time',SimpleNamespace(monotonic=lambda:now[0])):
            await asyncio.wait_for(relay(Socket(),{'states':[[],[]]},[{'name':'Fold'}]),4)
        self.assertEqual([e['frame_id'] for e in events if e.get('status')=='matched'],[3])

    async def test_intro_correction_advancement_and_final_completion_are_ordered(self):
        import json
        now=[100.0];sent=[];events=[];responses=asyncio.Queue();checks=[]
        intro=asyncio.Event();display=asyncio.Event();absent=asyncio.Event();correction=asyncio.Event();passed=asyncio.Event();finished=asyncio.Event()
        class Session:
            async def record_turn(self,turns,turn_complete):
                text=' '.join(p.text for p in turns.parts if p.text);sent.append(text)
                if turn_complete:
                    await responses.put(types.LiveServerMessage(server_content=types.LiveServerContent(generation_complete=True)))
                    await responses.put(types.LiveServerMessage(server_content=types.LiveServerContent(turn_complete=True)))
                if text.startswith('INTRO:'):intro.set()
                if text.startswith('DISPLAY CONFIRMED:'):display.set()
                if 'VISUAL DIAGNOSIS' in text:
                    (correction if '"paper_visible": true' in text else absent).set()
                if text.startswith('VISUAL VERIFIED:'):passed.set()
                if 'LESSON COMPLETE' in text:finished.set()
            async def send_realtime_input(self,**kwargs):
                if 'text' in kwargs:
                    await self.record_turn(types.Content(parts=[types.Part.from_text(text=kwargs['text'])]),'Paper is absent: stay quiet' not in kwargs['text'])
            async def receive(self):
                while True:yield await responses.get()
        @asynccontextmanager
        async def connect(**kwargs):yield Session()
        client=SimpleNamespace(aio=SimpleNamespace(live=SimpleNamespace(connect=connect),aclose=AsyncMock()))
        async def check(*args):
            checks.append(args);n=len(checks)
            return dict(verdict='unclear' if n==1 else 'before_fold' if n==2 else 'match',paper_visible=n>1,
                closest_state='target',before_excluded=True,unfolded_excluded=True,target_feature='New top flap.',camera_feature='Top flap meets center.',
                visible_evidence='Top flap.',observation='Top flap.',instruction='Move the top corner to the center crease.')
        class Socket:
            async def send(self,raw):events.append(json.loads(raw))
            async def __aiter__(self):
                yield json.dumps(dict(type='stage',step=1,epoch=1,intro=True))
                data=base64.b64encode(b'\xff\xd8'+b'a'*120).decode()
                yield json.dumps(dict(type='frame',step=1,epoch=1,frame_id=1,data=data))
                await asyncio.sleep(.15)
                self_test.assertEqual(checks,[]);self_test.assertFalse(intro.is_set())
                yield json.dumps(dict(type='microphone',enabled=True))
                await intro.wait();self_test.assertFalse(display.is_set())
                yield json.dumps(dict(type='intro_done',epoch=1))
                await display.wait()
                for frame_id,signal in [(1,absent),(2,correction),(3,passed)]:
                    now[0]+=1
                    yield json.dumps(dict(type='frame',step=1,epoch=1,frame_id=frame_id,data=data))
                    await signal.wait()
                yield json.dumps(dict(type='stage',step=2,epoch=2,intro=False,after_frame_id=3))
                now[0]+=1
                yield json.dumps(dict(type='frame',step=2,epoch=2,frame_id=4,data=data))
                await finished.wait()
        self_test=self
        with patch('google.genai.Client',return_value=client),patch('ori.config.load_settings',return_value=SimpleNamespace(gemini_api_key='test')),patch('ori.coaching.gemini_coach.reference_images',return_value=[('TARGET front',b'reference')]),patch('ori.coaching.gemini_coach.snapshot_check',side_effect=check),patch('ori.coaching.live_coach.time',SimpleNamespace(monotonic=lambda:now[0])):
            await asyncio.wait_for(relay(Socket(),{'states':[[],[],[]]},[{'name':'First fold'},{'name':'Final fold'}]),4)
        self.assertTrue(sent[0].startswith('INTRO:'));self.assertTrue(sent[1].startswith('DISPLAY CONFIRMED:'))
        self.assertIn('total_folds=2',sent[1])
        diagnostics=[text for text in sent if text.startswith('VISUAL DIAGNOSIS:')]
        self.assertEqual(len(diagnostics),2);self.assertIn('clear everyday English',diagnostics[-1])
        matches=[e for e in events if e.get('status')=='matched']
        self.assertEqual([(e['step'],e['final']) for e in matches],[(1,False),(2,True)])
        self.assertIn('LESSON COMPLETE',sent[-1]);self.assertIn('No next step',sent[-1])


    async def test_checks_continue_during_speech_and_match_bypasses_correction_cooldown(self):
        import json
        now=[100.0];responses=asyncio.Queue();events=[];checks=[]
        checked=[asyncio.Event() for _ in range(4)];tip=asyncio.Event();passed=asyncio.Event()
        class Session:
            async def send_realtime_input(self,**kwargs):
                if 'text' in kwargs:
                    await responses.put(types.LiveServerMessage(server_content=types.LiveServerContent(generation_complete=True)))
                    if kwargs['text'].startswith('VISUAL DIAGNOSIS'):tip.set()
            async def receive(self):
                while True:yield await responses.get()
        @asynccontextmanager
        async def connect(**kwargs):yield Session()
        client=SimpleNamespace(aio=SimpleNamespace(live=SimpleNamespace(connect=connect),aclose=AsyncMock()))
        async def check(*args):
            n=len(checks);checks.append(args);checked[n].set()
            return dict(verdict='match' if n==3 else 'mistake',paper_visible=True,closest_state='target',
                before_excluded=True,unfolded_excluded=True,target_feature='New flap',camera_feature='New flap',
                visible_evidence='New flap',observation='Fold',instruction='Align the corner')
        class Socket:
            async def send(self,raw):
                event=json.loads(raw);events.append(event)
                if event.get('status')=='matched':passed.set()
            async def __aiter__(self):
                yield json.dumps(dict(type='stage',step=1,epoch=1))
                yield json.dumps(dict(type='playback',step=1,epoch=1,playing=True))
                for n in range(4):
                    if n==2:yield json.dumps(dict(type='playback',step=1,epoch=1,playing=False))
                    now[0]+=1
                    yield json.dumps(dict(type='frame',step=1,epoch=1,frame_id=n+1,data=base64.b64encode(b'\xff\xd8'+b'a'*120).decode()))
                    await checked[n].wait()
                    if n==2:await tip.wait()
                    elif n==3:await passed.wait()
                    else:await asyncio.sleep(.15)
        with patch('google.genai.Client',return_value=client),patch('ori.config.load_settings',return_value=SimpleNamespace(gemini_api_key='test')),patch('ori.coaching.gemini_coach.reference_images',return_value=[]),patch('ori.coaching.gemini_coach.snapshot_check',side_effect=check),patch('ori.coaching.live_coach.time',SimpleNamespace(monotonic=lambda:now[0])):
            await asyncio.wait_for(relay(Socket(),{'states':[[],[]]},[{'name':'Fold'}]),3)
        self.assertEqual(len(checks),4)
        self.assertEqual([e['frame_id'] for e in events if e.get('status')=='matched'],[4])


if __name__=='__main__':unittest.main()
