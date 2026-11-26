# not-quite-my-tempo

An ASCII animation window for Claude Code on Windows. It opens when you send a prompt, loops an animation with a spinner and your own quotes, and closes when the reply finishes.

```
✻ Optimizing under duress... (4s)
```

This is an unofficial project. It is not affiliated with or endorsed by Anthropic.

**Heads up:** the default quotes include profanity. Edit `quotes.txt` to change them.

## Requirements

- Windows
- Python 3.8 or newer (tested with 3.10 and 3.13), with no extra packages
- [Git for Windows](https://git-scm.com/download/win), so Claude Code can run the hook through Git Bash
- Claude Code

## Install

Keep the folder somewhere permanent, because your quotes are read from it.

```
git clone https://github.com/afpashali/not-quite-my-tempo.git
cd not-quite-my-tempo
python claude_ascii_setup.py install
```

Restart Claude Code. To update, run `git pull` and then the install command again.

## Quotes

Edit `quotes.txt`:

- One quote per line.
- Blank lines and lines starting with `#` are ignored.
- Save as UTF-8. An open window picks up changes at its next quote switch.

A random quote is shown every 4 seconds. To change that, edit `QUOTE_SECONDS` in `claude_ascii_setup.py` and install again.

The installer remembers where `quotes.txt` is. If you move the folder, run the install command again.

The spinner and timer are decoration. They don't reflect what Claude is doing, and the timer counts from when the window opened.

## Play the animation by itself

```
python ascii_gif.py
python ascii_gif.py --once --speed 0.5
```

Press Ctrl+C to stop. This mode doesn't show quotes.

## What the installer changes

- Copies the scripts and quotes to `%USERPROFILE%\.claude\ascii-animation\`.
- Adds `UserPromptSubmit`, `Stop`, `StopFailure` and `SessionEnd` hooks to `%USERPROFILE%\.claude\settings.json`, so it runs in every project.
- Saves a `settings.ascii-backup-*.json` copy of your existing settings whenever installing or uninstalling changes them. These copies contain whatever your settings contain, and are not deleted automatically.

## Privacy and token usage

- The scripts make no network requests and no model calls.
- The hooks print nothing, so they add nothing to Claude's context.
- Claude Code passes hook data, which can include your prompt, to the script. The script uses only the session ID and event name. It creates an empty marker file named with a hash of the session ID and a random suffix.

## Uninstall

```
python claude_ascii_setup.py uninstall
```

This removes the hooks. To remove the copied files and backups too, delete the `ascii-animation` folder and the `settings.ascii-backup-*.json` files in `%USERPROFILE%\.claude\`.

## Known limitations

- The window opens at 101x27 characters in Windows Terminal. Without it, the window uses your console's default size.
- Interrupting a reply with Esc may leave the window open until a later reply finishes or you exit.
- Windows Terminal gives a new window keyboard focus. The animation hands it back, but keys typed in that split second may go to the new window.
- The installer ignores `CLAUDE_CONFIG_DIR` and always uses `%USERPROFILE%\.claude`.
- If you update or move Python, run the install command again.

## Troubleshooting

- **No window appears:** restart Claude Code, check that Git for Windows is installed, and run the install command again. The window may also be behind other windows.
- **Spinner symbols show as boxes:** use Windows Terminal or a console font that includes them.

## Tests

```
python -m unittest -v
```

The tests use temporary folders and open no windows. They don't touch your Claude settings.

## License

The code is released under the [MIT License](LICENSE). The animation data embedded in `ascii_gif.py` is converted from a GIF, and the license grants no rights to that original artwork.
