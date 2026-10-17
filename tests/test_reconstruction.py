"""Offline checks for chronological clip coverage and fold continuity."""
import unittest
from unittest.mock import patch, Mock
from ori.reconstruction.extract import windows, video_duration

class StaticTests(unittest.TestCase):
    def test_duration_reads_player_metadata_without_media_download(self):
        response=Mock(text='var ytInitialPlayerResponse = {"videoDetails":{"lengthSeconds":"401"}};')
        with patch('ori.reconstruction.extract.httpx.get',return_value=response) as get:
            self.assertEqual(video_duration('https://www.youtube.com/watch?v=GC_Szxdqh2Y'),401)
            self.assertEqual(get.call_count,1)

    def test_unavailable_duration_fails_instead_of_guessing(self):
        for html in ['consent page', 'var ytInitialPlayerResponse = {"videoDetails":{"lengthSeconds":"0"}};']:
            with patch('ori.reconstruction.extract.httpx.get',return_value=Mock(text=html)):
                with self.assertRaisesRegex(ValueError,'--duration'):
                    video_duration('https://www.youtube.com/watch?v=GC_Szxdqh2Y')

    def test_resume_overlap_and_short_final_window(self):
        self.assertEqual(list(windows(95,30,5,30)),[(25,60,30),(55,90,60),(85,95,90)])
        self.assertEqual(list(windows(30,30,5,30)),[])
        self.assertEqual(list(windows(12)),[(0,12,0)])

    def test_native_request_carries_executed_geometry_and_previous_steps(self):
        from ori.reconstruction.animation import build_request
        previous=[{'description':'First diagonal.','commands':'by2d p0 p2\nt 1500 r s4 180 p1'}]
        request=build_request('https://www.youtube.com/watch?v=GC_Szxdqh2Y','gemini-3.5-flash',previous,25,60,30,1)
        prompt=request['input'][1]['text']
        self.assertIn('First diagonal.',prompt)
        self.assertIn('first new action is step 2',prompt)
        self.assertIn('"material"',prompt)
        self.assertEqual(request['input'][0]['processing']['start_offset'],'25s')

if __name__=='__main__':unittest.main()
