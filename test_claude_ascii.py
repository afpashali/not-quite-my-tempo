"""Tests that never touch your real Claude settings or open windows.

Run with: python -m unittest -v
"""
import base64, contextlib, io, json, os, pathlib, re, shlex, tempfile, time, unittest, zlib
from unittest import mock

import ascii_gif
import claude_ascii_setup as app

PROJECT = pathlib.Path(__file__).resolve().parent


class TempProfile(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        claude = pathlib.Path(folder.name) / "O'Brien (test)" / '.claude'
        self.root = claude / 'ascii-animation'
        self.root.mkdir(parents=True)
        self.settings = claude / 'settings.json'
        for name, value in (('ROOT', self.root), ('SETTINGS', self.settings)):
            patcher = mock.patch.object(app, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)


@unittest.skipUnless(os.name == 'nt', 'Windows only')
class HookTests(TempProfile):
    def setUp(self):
        super().setUp()
        patcher = mock.patch.object(app.subprocess, 'Popen')
        self.popen = patcher.start()
        self.addCleanup(patcher.stop)

    def fire(self, event, session='a', **extra):
        payload = dict(session_id=session, hook_event_name=event, **extra)
        raw = json.dumps(payload, ensure_ascii=False).encode('utf-8')
        stdin = io.TextIOWrapper(io.BytesIO(raw), encoding='cp1252')
        with mock.patch.object(app.sys, 'stdin', stdin):
            app.hook()

    def markers(self):
        return list(self.root.glob('*.active'))

    def test_non_ascii_payload(self):
        text = 'thumbs \U0001F44D quote ”'
        self.fire('UserPromptSubmit', prompt=text)
        self.assertEqual(len(self.markers()), 1)
        self.fire('Stop', last_assistant_message=text)
        self.assertEqual(self.markers(), [])

    def test_one_window_per_session(self):
        self.fire('UserPromptSubmit')
        self.fire('UserPromptSubmit')
        self.assertEqual(self.popen.call_count, 1)
        self.fire('UserPromptSubmit', session='b')
        self.assertEqual(self.popen.call_count, 2)
        self.fire('SessionEnd')
        self.assertEqual(len(self.markers()), 1)

    def test_each_window_gets_a_new_marker(self):
        self.fire('UserPromptSubmit')
        first = self.markers()
        self.fire('Stop')
        self.fire('UserPromptSubmit')
        self.assertNotEqual(first, self.markers())

    def test_reopens_after_window_was_closed(self):
        self.fire('UserPromptSubmit')
        old = time.time() - app.STALE_SECONDS - 1
        os.utime(self.markers()[0], (old, old))
        self.fire('UserPromptSubmit')
        self.assertEqual(self.popen.call_count, 2)
        self.assertEqual(len(self.markers()), 1)

    def test_failed_launch_leaves_no_marker(self):
        self.popen.side_effect = OSError
        self.fire('UserPromptSubmit')
        self.assertEqual(self.markers(), [])

    def test_prints_nothing(self):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            self.fire('UserPromptSubmit')
            self.fire('Stop')
        self.assertEqual(output.getvalue(), '')


@unittest.skipUnless(os.name == 'nt', 'Windows only')
class InstallTests(TempProfile):
    OTHER = {'hooks': [{'type': 'command', 'command': 'echo keep'}]}

    def run_setup(self, remove=False):
        with contextlib.redirect_stdout(io.StringIO()):
            app.setup(remove)

    def read(self):
        return json.loads(self.settings.read_text(encoding='utf-8'))

    def backups(self):
        return list(self.settings.parent.glob('settings.ascii-backup-*.json'))

    def test_install_twice_then_uninstall(self):
        original = {'name': 'café', 'hooks': {'Stop': [self.OTHER], 'PreToolUse': [{'matcher': 'x'}]}}
        self.settings.write_text(json.dumps(original), encoding='utf-8')
        self.run_setup()
        self.run_setup()
        hooks = self.read()['hooks']
        self.assertEqual([len(hooks[e]) for e in app.EVENTS], [1, 2, 1, 1])
        self.assertEqual(len(self.backups()), 1)
        self.run_setup(remove=True)
        self.assertEqual(self.read(), original)

    def test_command_survives_awkward_paths(self):
        self.run_setup()
        command = self.read()['hooks']['Stop'][0]['hooks'][0]['command']
        parts = shlex.split(command)
        self.assertEqual(parts[1:], [(self.root / 'controller.py').as_posix(), 'hook'])
        self.assertNotIn('\\\\', parts[0])

    def test_invalid_settings_are_left_alone(self):
        self.settings.write_text('{ broken', encoding='utf-8')
        with self.assertRaises(SystemExit):
            self.run_setup()
        self.assertEqual(self.settings.read_text(encoding='utf-8'), '{ broken')

    def test_empty_settings(self):
        self.settings.write_text('', encoding='utf-8')
        self.run_setup()
        self.assertIn('Stop', self.read()['hooks'])

    def test_uninstall_without_install_creates_nothing(self):
        self.run_setup(remove=True)
        self.assertFalse(self.settings.exists())


class QuoteTests(TempProfile):
    def test_comments_blanks_bom_and_control_characters(self):
        (self.root / 'quotes.txt').write_text('# note\n\n  one \x1b[31m\ntwo\n', encoding='utf-8-sig')
        self.assertEqual(app.load_quotes(), ['one [31m', 'two'])

    def test_user_file_then_installed_copy_then_default(self):
        user = self.root / 'mine.txt'
        copy = self.root / 'quotes.txt'
        (self.root / 'quotes_path.txt').write_text(str(user), encoding='utf-8')
        user.write_text('mine\n', encoding='utf-8')
        copy.write_text('copy\n', encoding='utf-8')
        self.assertEqual(app.load_quotes(), ['mine'])
        user.write_text('# nothing\n', encoding='utf-8')
        self.assertEqual(app.load_quotes(), ['copy'])
        copy.unlink()
        self.assertEqual(app.load_quotes(), ['Thinking...'])

    def test_shipped_quotes_load(self):
        (self.root / 'quotes_path.txt').write_text(str(PROJECT / 'quotes.txt'), encoding='utf-8')
        self.assertIn('Not quite my tempo...', app.load_quotes())

    def test_status_line_fits(self):
        for cols in (5, 12, 40, 120):
            plain = re.sub('\x1b\\[[0-9;]*m', '', app.status_line('x' * 60, 12, cols))
            self.assertLess(len(plain), cols)


class FocusTests(unittest.TestCase):
    def check(self, current, title):
        user = mock.Mock()
        user.GetForegroundWindow.return_value = current
        user.GetWindowTextW.side_effect = lambda hwnd, buffer, size: setattr(buffer, 'value', title)
        result = app.give_back_focus(user, 1)
        return result, user.SetForegroundWindow.called

    def test_restores_only_when_our_window_has_focus(self):
        self.assertEqual(self.check(2, app.TITLE), (True, True))
        self.assertEqual(self.check(2, 'Browser'), (False, False))
        self.assertEqual(self.check(1, app.TITLE), (False, False))
        self.assertEqual(self.check(None, ''), (False, False))


class WindowTests(unittest.TestCase):
    def test_sized_terminal_window(self):
        with mock.patch.object(app.shutil, 'which', return_value='wt.exe'):
            command = app.window_command(['python', 'a;b'])
        self.assertEqual(command, ['wt.exe', '-w', 'new', '--size', '101,27', 'python', 'a\;b'])

    def test_without_windows_terminal(self):
        with mock.patch.object(app.shutil, 'which', return_value=None):
            self.assertEqual(app.window_command(['python']), ['python'])


class AnimationTests(unittest.TestCase):
    def test_frames_are_plain_text_of_the_expected_size(self):
        frames = json.loads(zlib.decompress(base64.b85decode(ascii_gif.DATA)))
        self.assertTrue(frames)
        for delay, frame in frames:
            self.assertGreater(delay, 0)
            lines = frame.splitlines()
            self.assertEqual(len(lines), 25)
            self.assertTrue(all(len(line) == 100 and line.isprintable() for line in lines))


if __name__ == '__main__':
    unittest.main()
