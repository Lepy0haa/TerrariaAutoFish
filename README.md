# Terraria AutoFish

**English** | [Русский](README.ru.md)

Automatic fishing for **Terraria** (1.4.4, 1.4.5 and newer, tModLoader). The program watches the
bobber on the screen and hooks the fish the moment the bobber goes under water, then casts again.

It works **only with screenshots and mouse clicks**: it does not read or modify game memory or
files, so it does not depend on the game version.

<p>
  <img src="docs/main-en.png" width="360" alt="Main window">
  <img src="docs/settings-en.png" width="360" alt="Settings">
</p>

## Features

- **Watches the bobber itself** — you mark the bobber once, the program remembers what it looks
  like and hooks when it sinks.
- **Auto-calibration** — the hook threshold adapts to your water, weather, time of day and bobber.
- **Pause without losing points** — pause and resume with the same cast point and bobber.
- **Finds a lost bobber** — if the bobber lands off to the side, the program searches around the
  place you marked and remembers the new spot.
- **Ignores distractions** — waves, rain, fish shadows, pets, cursor sparkles, lightning flashes.
- **Clear interface** — what's happening now and what you need to do, a live picture of the
  bobber, stats (hooks, casts, hooks per hour), an event log.
- **Notifications** — a small window over the game, Windows notifications (pause, out of bait,
  errors) and sounds.
- **Two languages** — English and Russian (switch in the settings).

## Download

Download `TerrariaAutoFish.exe` from [Releases](../../releases) and run it — Python is not needed.

Or run it from the source code (see [Running from source](#running-from-source)).

## Quick start

1. In Terraria set the display mode to **Windowed** or **Borderless** (in exclusive fullscreen the
   program cannot see the screen).
2. Hold the fishing rod, keep bait in the inventory. The bobber must **not** be cast.
3. Point the cursor at the water (5+ tiles from the character) and press **HOME**.
   Or click **▶ Start (5 s)** in the program window and switch to the game within 5 seconds.
4. The program casts and beeps: point the cursor at the **bobber** and press **HOME** again.
   Being a bit off is fine — the program finds the bobber near the cursor by itself.
5. That's it: the program waits for a bite, hooks and casts again. Don't touch the mouse.

## Controls

| Key (default) | Action |
|---|---|
| **HOME** | Start · mark the bobber · pause · resume with the same points |
| **END** | Forget the cast point and the bobber and choose new ones |

Both keys can be changed in the settings. If you switch from the game to another window, the
program pauses by itself — come back and press **HOME** to continue.

## Program window

- **Top** — what is happening now and what you need to do.
- **Bobber** — a live picture of what the program is watching, and the remembered bobber.
- **Bobber visible above water** — green bar: everything is calm; when the bar drops below the
  red line, it's a bite and the program hooks.
- **Stats** — hooks, casts, hooks per hour, running time, failed casts in a row.
- **Log** — all events. Green — good, red — pause/problems, yellow — your action is needed.

The small window over the game shows the same things briefly. Drag it with the mouse; clicking it
does not take focus away from the game.

<img src="docs/overlay-en.png" alt="Overlay">

## Settings

| Setting | What it does |
|---|---|
| Language | Auto (as in Windows) / Русский / English |
| Keys | Start/pause/resume key and "new points" key |
| Scale (Zoom) | Set the same value as the Zoom in Terraria's settings |
| Sensitivity | Hook when less than this share of the bobber is visible. Used until auto-calibration has learned (and always if it is off) |
| Auto-calibration | The threshold is tuned automatically (recommended) |
| Wait for a bite | After this time without a bite — reel in and cast again |
| Small window over the game, Windows notifications, sounds | Ways to know what's happening |
| Save debug pictures | Pictures of every search and hook in the `debug` folder — for troubleshooting |
| Record mode | The program casts, you hook yourself; it records how the bobber moved (`record` folder) |

Settings are saved automatically in `%APPDATA%\TerrariaAutoFish\settings.json`.

## How it works

1. **Marking.** You point at the bobber; the program finds the solid bright blob of the bobber near
   the cursor and remembers its image and colors.
2. **Finding the bobber after each cast.** The program looks for the remembered image near the
   mark and checks that there really is a bobber blob there. The image is updated after every
   cast, so sunset, sunrise and weather changes don't matter. If the bobber is not there, the
   program waits a second and searches three times wider around the original mark — by its
   image and by its colors.
3. **Detecting a bite.** The program counts how many pixels of the bobber's colors are visible
   above the water. When a fish bites, the bobber goes under water and fewer of them are visible.
   Frames with a lightning flash are skipped.
4. **Auto-calibration.** While waiting, the program measures how much the bobber "sinks" on waves
   and in rain (ignoring the last second before a hook). After 2 casts the threshold is set just
   below that level (median of the last 8 casts minus 20%, within 35–75%). Calm water gives earlier
   hooks, rough water — fewer false hooks. Choosing new points restarts the calibration.

## Troubleshooting

| Problem | Solution |
|---|---|
| Hooks without a bite | Turn auto-calibration on, or lower the sensitivity (e.g. 45%) |
| Misses bites | Raise the sensitivity (e.g. 65%) |
| "Bobber not found" 3 times → pause | Usually out of bait. If the bobber lands far away — press **END** and choose new points |
| Zoom in the game is not 100% | Set the same scale in the settings |
| No Windows notifications | Check "Do not disturb" / Focus assist in Windows |
| The antivirus complains about the .exe | The .exe is built with PyInstaller and clicks the mouse for you — some antivirus programs react to that. You can run it from the source code instead |

For a detailed analysis turn on **Save debug pictures** — pictures of every search (`poisk`) and
hook (`poklevka`) appear in the `debug` folder next to the program.

## Running from source

Requires Windows 10/11 and Python 3.10+.

```bash
pip install -r requirements.txt
python app.py
```

A console version without a window: `start.bat` (also `start_debug.bat`, `start_record.bat`).
Fine-tuning constants are at the top of `autofish.py`.

To build `TerrariaAutoFish.exe` yourself run `build.bat`.

### Files

| File | Contents |
|---|---|
| `app.py` | The program with a window, overlay and notifications |
| `autofish.py` | Fishing logic: bobber search, bite detection, auto-calibration; console version |
| `i18n.py` | Translations (Russian / English) |
| `build.bat` | Builds `TerrariaAutoFish.exe` with PyInstaller |

## Important

Use it in single player or on your own server. Macros are often prohibited on public servers and
you can be banned for them. This project is not affiliated with Re-Logic.
