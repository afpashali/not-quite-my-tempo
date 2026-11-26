"""Install/remove a Claude Code ASCII animation hook on Windows."""
import hashlib, json, os, pathlib, secrets, shlex, shutil, subprocess, sys, time

ROOT = pathlib.Path.home() / '.claude' / 'ascii-animation'
SETTINGS = ROOT.parent / 'settings.json'
EVENTS = ('UserPromptSubmit', 'Stop', 'StopFailure', 'SessionEnd')
FILES = ('ascii_gif.py', 'quotes.txt')
SPINNER = '·✢*✶✻✽✻✶*✢'
QUOTE_SECONDS = 4
STALE_SECONDS = 5  # a window that hasn't checked in for this long is gone
SHOW_WITHOUT_FOCUS = 4  # Win32 SW_SHOWNOACTIVATE
TITLE = 'Claude is locked in'
COLUMNS, ROWS = 101, 27  # 100x25 art, a blank row and the status line

def remove_marker(marker):
    # Windows refuses the delete if the player is touching the file right then.
    for _ in range(20):
        try: return marker.unlink(missing_ok=True)
        except PermissionError: time.sleep(0.05)

def is_alive(marker):
    try: return time.time() - marker.stat().st_mtime < STALE_SECONDS
    except OSError: return False

def user32():
    import ctypes
    from ctypes import wintypes
    user = ctypes.WinDLL('user32')
    user.GetForegroundWindow.restype = wintypes.HWND
    user.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    user.SetForegroundWindow.argtypes = [wintypes.HWND]
    return user

def give_back_focus(user, previous):
    """If our window took the focus, return it to the window that had it."""
    import ctypes
    current = user.GetForegroundWindow()
    if not previous or not current or current == previous: return False
    title = ctypes.create_unicode_buffer(len(TITLE)+2)
    user.GetWindowTextW(current, title, len(title))
    if title.value != TITLE: return False  # the user switched somewhere else
    return bool(user.SetForegroundWindow(previous))

def window_command(command):
    """Open the player in a Windows Terminal window of the right size, if available."""
    terminal = shutil.which('wt')
    if not terminal: return command
    # Windows Terminal reads a bare semicolon as the start of another command.
    return [terminal, '-w', 'new', '--size', f'{COLUMNS},{ROWS}'] + [part.replace(';', '\;') for part in command]

def hook():
    # Claude Code sends UTF-8; sys.stdin would decode it with the Windows code page.
    data = json.loads(sys.stdin.buffer.read().decode('utf-8', errors='replace'))
    sid = hashlib.sha256(data['session_id'].encode()).hexdigest()
    markers = list(ROOT.glob(sid + '*.active'))
    if data['hook_event_name'] != 'UserPromptSubmit':
        for marker in markers: remove_marker(marker)
        return
    if any(is_alive(m) for m in markers):
        return
    for marker in markers: remove_marker(marker)
    # A new name per window, so a closing window can't affect its replacement.
    marker = ROOT / f'{sid}.{secrets.token_hex(4)}.active'
    marker.touch()
    try:
        startup = subprocess.STARTUPINFO()
        startup.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startup.wShowWindow = SHOW_WITHOUT_FOCUS
        previous = str(user32().GetForegroundWindow() or 0)
        command = [sys.executable, str(ROOT/'controller.py'), 'play', str(marker), previous]
        subprocess.Popen(window_command(command),
                         creationflags=subprocess.CREATE_NEW_CONSOLE, startupinfo=startup, close_fds=True)
    except Exception:
        remove_marker(marker)

def load_quotes():
    """Read the user's quotes.txt, falling back to the installed copy."""
    paths = []
    try: paths.append(pathlib.Path((ROOT/'quotes_path.txt').read_text(encoding='utf-8').strip()))
    except (OSError, UnicodeError): pass
    paths.append(ROOT/'quotes.txt')
    for path in paths:
        try: text = path.read_text(encoding='utf-8-sig', errors='replace')
        except OSError: continue
        lines = (''.join(c for c in line if c.isprintable()).strip() for line in text.splitlines())
        quotes = [line for line in lines if line and not line.startswith('#')]
        if quotes: return quotes
    return ['Thinking...']

def status_line(quote, elapsed, cols):
    """Spinner, quote and timer, cut to fit on one row."""
    glyph = SPINNER[int(elapsed/0.12) % len(SPINNER)]
    text = quote[:max(0, cols-3)]
    timer = f' ({int(elapsed)}s)'
    if len(text)+len(timer)+3 > cols: timer = ''
    return f'\x1b[38;2;215;119;87m{glyph} {text}\x1b[90m{timer}\x1b[0m'

def play(marker, previous=0):
    import ascii_gif
    import base64, ctypes, random, zlib
    path = pathlib.Path(marker)
    frames = json.loads(zlib.decompress(base64.b85decode(ascii_gif.DATA)))
    k = ctypes.windll.kernel32
    k.SetConsoleTitleW(TITLE)
    user = user32()
    h = k.GetStdHandle(-11); mode = ctypes.c_uint32()
    if k.GetConsoleMode(h, ctypes.byref(mode)): k.SetConsoleMode(h, mode.value | 4)
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        # Hide the cursor, turn off line wrapping (wide characters in quotes), clear.
        sys.stdout.write('\x1b[?25l\x1b[?7l\x1b[2J'); sys.stdout.flush()
        start = time.monotonic(); quote = None; next_quote = start; next_beat = start
        while path.exists():
            for delay, frame in frames:
                if not path.exists(): return
                cols, rows = shutil.get_terminal_size((COLUMNS, ROWS))
                w = max(1, min(100, cols-1, (rows-2)*4)); ht = max(1, min(25, round(w/4)))
                lines = frame.splitlines()
                art = '\x1b[K\n'.join(''.join(lines[y*25//ht][x*100//w] for x in range(w)) for y in range(ht))
                now = time.monotonic()
                # Windows Terminal ignores SHOW_WITHOUT_FOCUS, so hand focus back once.
                if previous and now-start < 3 and give_back_focus(user, previous): previous = 0
                if now >= next_beat:
                    try: os.utime(path)
                    except OSError: pass
                    next_beat = now + 1
                if now >= next_quote:
                    quotes = load_quotes()
                    quote = random.choice([q for q in quotes if q != quote] or quotes)
                    next_quote = now + QUOTE_SECONDS
                status = status_line(quote, now-start, cols)
                sys.stdout.write(f'\x1b[H{art}\x1b[K\n\x1b[K\n{status}\x1b[J'); sys.stdout.flush()
                time.sleep(delay/1000)
    finally:
        sys.stdout.write('\x1b[?7h\x1b[?25h'); sys.stdout.flush()
        remove_marker(path)

def is_ours(entry):
    command = entry.get('command', '')
    return 'ascii-animation' in command and 'controller.py' in command

def read_settings():
    if not SETTINGS.exists(): return {}
    try:
        text = SETTINGS.read_text(encoding='utf-8-sig')
        config = json.loads(text) if text.strip() else {}
    except ValueError as error:
        raise SystemExit(f'Nothing changed: {SETTINGS} is not valid JSON ({error}).')
    if not isinstance(config, dict) or not isinstance(config.get('hooks', {}), dict):
        raise SystemExit(f'Nothing changed: unexpected structure in {SETTINGS}.')
    return config

def update_hooks(config, command):
    """Return config with our hooks replaced by command, or removed if it is None."""
    config = json.loads(json.dumps(config))
    hooks = config.get('hooks', {})
    removed = False
    for event in EVENTS:
        groups = []
        for group in hooks.get(event, []):
            entries = group.get('hooks', [])
            kept = [e for e in entries if not is_ours(e)]
            if len(kept) == len(entries): groups.append(group)
            else:
                removed = True
                if kept: groups.append(dict(group, hooks=kept))
        if command:
            groups.append({'hooks': [{'type': 'command', 'command': command, 'timeout': 5}]})
        if groups: hooks[event] = groups
        else: hooks.pop(event, None)
    if hooks: config['hooks'] = hooks
    elif removed: config.pop('hooks', None)
    return config

def setup(remove=False):
    if os.name != 'nt': raise SystemExit('This installer targets Windows.')
    config = read_settings()
    command = None
    if not remove:
        source = pathlib.Path(__file__).resolve().parent
        if source == ROOT.resolve():
            raise SystemExit('Run the installer from the downloaded project folder.')
        missing = [name for name in FILES if not (source/name).is_file()]
        if missing: raise SystemExit('Nothing changed: missing ' + ', '.join(missing))
        ROOT.mkdir(parents=True, exist_ok=True)
        shutil.copy2(__file__, ROOT/'controller.py')
        for name in FILES: shutil.copy2(source/name, ROOT/name)
        (ROOT/'quotes_path.txt').write_text(str(source/'quotes.txt'), encoding='utf-8')
        # Forward slashes and shell quoting, because Git Bash runs the hook.
        parts = [pathlib.Path(sys.executable).as_posix(), (ROOT/'controller.py').as_posix(), 'hook']
        command = ' '.join(shlex.quote(part) for part in parts)
    updated = update_hooks(config, command)
    if updated != config:
        if SETTINGS.exists():
            shutil.copy2(SETTINGS, SETTINGS.with_name(f'settings.ascii-backup-{time.time_ns()}.json'))
        SETTINGS.parent.mkdir(parents=True, exist_ok=True)
        tmp = SETTINGS.with_suffix('.ascii-tmp')
        tmp.write_text(json.dumps(updated, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
        tmp.replace(SETTINGS)
    if remove:
        for marker in ROOT.glob('*.active'): remove_marker(marker)
        print('Removed hooks.' if updated != config else 'No hooks to remove.')
    else:
        print('Installed! Restart Claude Code.')

if __name__ == '__main__':
    action = sys.argv[1] if len(sys.argv) > 1 else 'install'
    if action == 'hook':
        try: hook()
        except Exception: pass  # cosmetic hooks must never block Claude
    elif action == 'play': play(sys.argv[2], int(sys.argv[3]) if len(sys.argv) > 3 else 0)
    elif action in ('install', 'uninstall'): setup(action == 'uninstall')
    else: raise SystemExit('Use install or uninstall.')
