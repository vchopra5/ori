import copy
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from ori.reconstruction.lego_design import revise, test_steps, database


class DesignTests(unittest.TestCase):
    def setUp(self):
        self.plan = json.loads(Path('examples/lego/tent.json').read_text())

    def test_restart_keeps_prefix(self):
        suffix = copy.deepcopy(self.plan)
        suffix['steps'] = suffix['steps'][4:]
        self.assertEqual(revise(self.plan, dict(restart_from_step=5, plan=suffix)), self.plan)

    def test_restart_cannot_change_kept_parts(self):
        suffix = copy.deepcopy(self.plan)
        suffix['pieces'][0]['color'] = 'red'
        with self.assertRaisesRegex(ValueError, 'already placed'):
            revise(self.plan, dict(restart_from_step=2, plan=suffix))

    def test_restart_range(self):
        for index in (0, -1, 100, True):
            with self.assertRaises(ValueError):
                revise(self.plan, dict(restart_from_step=index, plan=self.plan))

    def test_returns_exact_failed_step(self):
        self.plan['steps'][3]['attach']['to'] = 'missing'
        result = test_steps(self.plan)
        self.assertFalse(result['passed'])
        self.assertEqual(result['failed_step'], 4)
        self.assertEqual(len(result['checks']), 3)

    def test_validates_each_placement(self):
        result = test_steps(self.plan)
        self.assertTrue(result['passed'])
        self.assertEqual(len(result['checks']), 10)

    def test_database_roundtrip(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp)/'builds.sqlite3'
            with database(path) as db:
                db.execute('INSERT INTO lego_trials(build_id,attempt,proposal,feedback) VALUES(?,?,?,?)', ('demo',1,'{}','{}'))
            with database(path) as db:
                self.assertEqual(db.execute('SELECT build_id FROM lego_trials').fetchone()[0], 'demo')
                self.assertEqual(db.execute('SELECT count(*) FROM lego_builds').fetchone()[0], 0)


if __name__ == '__main__':
    unittest.main()
