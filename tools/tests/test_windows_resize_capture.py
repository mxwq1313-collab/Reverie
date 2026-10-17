"""Failures must never masquerade as a successful native-window recording."""
import ctypes
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, patch
from tools.windows_resize_capture import WindowRecording


@unittest.skipUnless(sys.platform == 'win32', 'Windows recorder')
class WindowRecordingTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.output = Path(self.folder.name)/'capture.mkv'
        self.api = MagicMock()
        self.api.IsWindowVisible.return_value = True
        self.api.IsIconic.return_value = False
        def dimensions(hwnd, pointer):
            pointer._obj.right = 100
            pointer._obj.bottom = 80
            return True
        self.api.GetClientRect.side_effect = dimensions
        with patch.object(ctypes, 'WinDLL', return_value=self.api):
            self.recording = WindowRecording(123, self.output)

    def test_hidden_or_minimized_target_is_rejected_before_spawning(self):
        for visible, iconic in ((False, False), (True, True)):
            with self.subTest(visible=visible, iconic=iconic):
                self.api.IsWindowVisible.return_value = visible
                self.api.IsIconic.return_value = iconic
                with patch('subprocess.Popen') as spawn:
                    with self.assertRaises(RuntimeError):
                        self.recording.start()
                    spawn.assert_not_called()
                self.assertFalse(self.output.exists())

    def test_zero_client_pixels_are_rejected(self):
        self.api.GetClientRect.side_effect = lambda hwnd, pointer: True
        with self.assertRaisesRegex(RuntimeError, 'pixels'):
            self.recording.target_size()

    def test_existing_video_is_never_overwritten(self):
        self.output.write_bytes(b'prior recording')
        with self.assertRaises(FileExistsError):
            self.recording.start()
        self.assertEqual(self.output.read_bytes(), b'prior recording')

    def test_readiness_requires_encoded_frame_and_live_process(self):
        recording = self.recording
        recording.process = MagicMock()
        recording.process.poll.return_value = None
        recording.log_path = self.output.with_suffix('.txt')
        self.output.write_bytes(b'synthetic first packet')
        for log, expected in (('frame=0\n', False), ('frame=2\n', True)):
            recording.log_path.write_text(log)
            self.assertEqual(recording.ready(), expected)
        recording.process.poll.return_value = 1
        with self.assertRaisesRegex(RuntimeError, 'exited'):
            recording.ready()

    def test_target_failure_is_preserved_for_final_result(self):
        self.api.IsIconic.return_value = True
        with self.assertRaises(RuntimeError):
            self.recording.check_target()
        self.assertIn('minimized', self.recording.failure)

    def test_abnormal_encoder_exit_is_failure_even_with_video_bytes(self):
        recording = self.recording
        recording.process = MagicMock()
        recording.process.poll.return_value = 1
        recording.process.returncode = 1
        recording.log = MagicMock()
        recording.started = 0
        self.output.write_bytes(b'partial video')
        with patch('subprocess.run') as decode:
            result = recording.stop()
            self.assertFalse(result['passed'])
            self.assertEqual(result['returncode'], 1)
            decode.assert_not_called()
        self.assertFalse(recording.stop()['passed'])

    def test_valid_video_does_not_override_a_prior_hidden_window_failure(self):
        recording = self.recording
        recording.executable = 'synthetic-ffmpeg'
        decoded = '#tb 0: 1/1000\n0, 0, 0, 17, 120, first\n0, 17, 17, 17, 120, second\n'
        with patch('subprocess.run', return_value=subprocess.CompletedProcess([], 0, decoded, '')):
            result = recording.verify_video({'passed':False,'error':'Target minimized after valid frames'})
        self.assertEqual(result['decoded_frames'], 2)
        self.assertFalse(result['passed'])
        self.assertIn('minimized', result['error'])

    def test_successful_exit_still_requires_successful_nonempty_decode(self):
        recording = self.recording
        recording.process = MagicMock()
        recording.process.poll.return_value = 0
        recording.process.returncode = 0
        recording.log = MagicMock()
        recording.started = 0
        recording.executable = 'synthetic-ffmpeg'
        self.output.write_bytes(b'synthetic video')
        with patch('subprocess.run', return_value=subprocess.CompletedProcess([], 1, '', 'corrupt video')):
            result = recording.stop()
        self.assertFalse(result['passed'])
        self.assertEqual(result['decoded_frames'], 0)
        self.assertIn('corrupt', result['decode_error'])


if __name__ == '__main__':
    unittest.main()
