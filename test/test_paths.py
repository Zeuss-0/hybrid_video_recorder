import os
import unittest

from hybrid_video_recorder.paths import resolve_recording_root


class ResolveRecordingRootTest(unittest.TestCase):
    def setUp(self):
        self.package = "/opt/ros_ws/src/hybrid_video_recorder"

    def test_empty_values_use_package_recordings_dir(self):
        resolved = resolve_recording_root("", "", self.package)
        self.assertEqual(
            os.path.join(self.package, "recordings"),
            resolved,
        )

    def test_param_beats_environment(self):
        resolved = resolve_recording_root(
            "/data/from-param",
            "/data/from-env",
            self.package,
        )
        self.assertEqual("/data/from-param", resolved)

    def test_environment_used_when_param_blank(self):
        resolved = resolve_recording_root(
            "   ",
            "/data/from-env",
            self.package,
        )
        self.assertEqual("/data/from-env", resolved)

    def test_relative_path_is_package_relative(self):
        resolved = resolve_recording_root("sessions/today", "", self.package)
        self.assertEqual(
            os.path.join(self.package, "sessions", "today"),
            resolved,
        )

    def test_tilde_is_expanded(self):
        resolved = resolve_recording_root("~/recordings", "", self.package)
        self.assertEqual(os.path.expanduser("~/recordings"), resolved)
        self.assertTrue(os.path.isabs(resolved))

    def test_none_param_falls_through(self):
        resolved = resolve_recording_root(None, None, self.package)
        self.assertEqual(os.path.join(self.package, "recordings"), resolved)


if __name__ == "__main__":
    unittest.main()
