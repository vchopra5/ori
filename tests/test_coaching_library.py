"""Delete exactly the selected saved run, keeping recoverable artifacts."""
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch, MagicMock
from ori.coaching import server


class LibraryDeleteTests(unittest.TestCase):
    def setUp(self):
        self.tmp=TemporaryDirectory()
        self.root=Path(self.tmp.name)
        self.base=self.root/'output/fold_commands_fox'
        self.base.mkdir(parents=True)
        (self.base/'commands.json').write_text(json.dumps({'commands':[]}))
        (self.base/'report.json').write_text('{}')
        self.root_patch=patch.object(server,'ROOT',self.root)
        self.root_patch.start()
        self.job_patch=patch.object(server,'JOB_PROCESS',None)
        self.job_patch.start()

    def tearDown(self):
        self.job_patch.stop();self.root_patch.stop();self.tmp.cleanup()

    def test_delete_moves_only_selected_run_and_survives_relisting(self):
        untouched=self.root/'output/unrelated';untouched.mkdir();(untouched/'keep.txt').write_text('keep')
        item=server.library()[0]
        self.assertTrue(server.delete_run(item['delete_token'])['deleted'])
        self.assertFalse(self.base.exists())
        self.assertEqual(server.library(),[])
        self.assertEqual((untouched/'keep.txt').read_text(),'keep')
        trash=self.root/'output/.trash'
        metadata=list(trash.glob('*.json'))
        self.assertEqual(len(metadata),1)
        self.assertEqual(json.loads(metadata[0].read_text())['original_path'],'output/fold_commands_fox')
        self.assertTrue((trash/metadata[0].stem/'commands.json').is_file())
        with self.assertRaises(ValueError):server.delete_run(item['delete_token'])

    def test_untrusted_tokens_and_active_job_do_not_touch_files(self):
        for token in [None,'../output','x'*64,'0'*64]:
            with self.assertRaises(ValueError):server.delete_run(token)
        process=MagicMock();process.poll.return_value=None
        with patch.object(server,'JOB_PROCESS',process),self.assertRaises(RuntimeError):
            server.delete_run(server.library()[0]['delete_token'])
        self.assertTrue(self.base.exists())

    def test_multiple_completed_runs_for_same_video_have_distinct_ids(self):
        video=self.root/'output/fold_trials/runs/abcdefghijk'
        for name in ['run1','run2']:
            base=video/name;base.mkdir(parents=True)
            (base/'result.json').write_text(json.dumps(dict(status='model_claimed_done',accepted_folds=1)))
            (base/'commands.json').write_text('{"commands":[]}')
        runs=[item for item in server.library() if item['id'].startswith('trial-')]
        self.assertEqual(len(runs),2)
        self.assertNotEqual(runs[0]['id'],runs[1]['id'])
        server.delete_run(runs[0]['delete_token'])
        remaining=[item for item in server.library() if item['id'].startswith('trial-')]
        self.assertEqual([item['id'] for item in remaining],[runs[1]['id']])


if __name__=='__main__':unittest.main()
