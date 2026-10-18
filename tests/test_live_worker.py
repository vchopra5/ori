"""Starting another browser/test cannot tear down the active demo session."""
from pathlib import Path
import unittest
from tempfile import TemporaryDirectory
from unittest.mock import MagicMock,patch
from ori.coaching.live_worker import LiveWorker


class OwnershipTests(unittest.TestCase):
    def setUp(self):
        self.worker=LiveWorker();self.current=MagicMock();self.current.poll.return_value=None
        self.worker.process=self.current;self.worker.owner='the-demo-tab'

    def tearDown(self):self.worker.close()

    def test_other_tab_or_legacy_caller_cannot_replace_demo(self):
        with patch('ori.coaching.live_worker.subprocess.Popen') as spawn:
            for owner in ['another-agent',None]:
                with self.assertRaisesRegex(RuntimeError,'left connected'):
                    self.worker.start(Path('/tmp/example'),'http://127.0.0.1:8766',owner)
            spawn.assert_not_called();self.current.terminate.assert_not_called()
            self.assertIs(self.worker.process,self.current)

    def test_same_tab_can_replace_its_own_transport_when_reconnecting(self):
        process=MagicMock();process.stdout.readline.return_value='{"port":12345,"token":"secret"}\n'
        with TemporaryDirectory() as directory, patch('ori.coaching.live_worker.subprocess.Popen',return_value=process) as spawn,patch('ori.coaching.live_worker.selectors.DefaultSelector') as selector:
            selector.return_value.__enter__.return_value.select.return_value=[object()]
            info=self.worker.start(Path(directory),'http://127.0.0.1:8766','the-demo-tab')
            self.assertTrue(self.worker.log_path.exists())
            self.assertEqual(Path(spawn.call_args.kwargs['stderr'].name),self.worker.log_path)
            self.assertTrue(spawn.call_args.kwargs['stderr'].closed)
        self.current.terminate.assert_called_once()
        self.assertIs(self.worker.process,process)
        self.assertEqual(self.worker.owner,'the-demo-tab')
        self.assertIn('12345',info['url'])


if __name__=='__main__':unittest.main()
