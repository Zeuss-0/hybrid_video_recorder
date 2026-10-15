import unittest

from hybrid_video_recorder.recording_state import (
    ERROR,
    IDLE,
    PAUSED,
    RECORDING,
    RecordingState,
)


class RecordingStateTest(unittest.TestCase):
    def test_record_pause_resume_stop(self):
        state = RecordingState()
        self.assertEqual(IDLE, state.value)
        self.assertTrue(state.start())
        self.assertEqual(RECORDING, state.value)
        self.assertTrue(state.pause())
        self.assertEqual(PAUSED, state.value)
        self.assertTrue(state.resume())
        self.assertTrue(state.begin_stop())
        state.finish_stop(True)
        self.assertEqual(IDLE, state.value)

    def test_error_can_start_a_new_session(self):
        state = RecordingState()
        state.value = ERROR
        self.assertTrue(state.start())
        self.assertEqual(RECORDING, state.value)


if __name__ == "__main__":
    unittest.main()
