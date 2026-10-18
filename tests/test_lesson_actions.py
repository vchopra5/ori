import unittest
from ori.coaching.lesson_actions import lesson_action
from ori.coaching.live_coach import stage_instruction


class LessonActionTests(unittest.TestCase):
    def test_saved_rehearsal_is_neutral_in_voice_instruction(self):
        command = {'name': 'Oh no, the ear points inward — correct the right ear crease',
                   'angle_degrees': -180, 'moving_side': 'right'}
        instruction = stage_instruction(1, 2, [command])
        self.assertIn('Fold the right ear', instruction)
        self.assertNotIn('inward', instruction)
        self.assertNotIn('Oh no', instruction)
        self.assertTrue(command['name'].startswith('Oh no'))
        self.assertEqual(lesson_action(command)['angle_degrees'], -180)

    def test_normal_instruction_is_preserved(self):
        command = {'name': 'Fold the corner to the center'}
        self.assertEqual(lesson_action(command), command)
