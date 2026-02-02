# Nighttime-Daytime Theme Switcher

A Python utility that automatically switches your system theme between light and dark modes based on the calculated position of the sun at your location.

## Features

- **Solar Calculation:** Accurately calculates sunrise and sunset times for your specific latitude and longitude (no API required).
- **Automated Switching:** Automatically applies a random theme from your configured collection when day transitions to night (and vice versa).
- **Systemd Integration:** Includes built-in commands to install itself as a systemd user service for "set and forget" operation.
- **Logging:** Keeps a log of operations in `omarchy_nighttime_daytime.log`.

## Prerequisites

- **Python 3**
- **Omarchy Theme Manager:** This script expects themes to be located at `~/.local/share/omarchy/themes` and the switcher utility at `~/.local/share/omarchy/bin/omarchy-theme-set`.

## Configuration

Edit the top of `omarchy_nighttime_daytime.py` to set your location:

```python
LATITUDE = -36.8485
LONGITUDE = 174.7635
```

## Usage

### Manual Run

To run the script manually (keeps running in the foreground/background depending on how you invoke it):

```bash
./omarchy_nighttime_daytime.py
```

Options:
- `--dry-run`: Calculate state and select a theme but do not apply it.
- `--one-shot`: Check state, apply theme if changed, and exit immediately.

### Automatic Startup (Systemd)

To install the script as a background service that starts on login:

```bash
./omarchy_nighttime_daytime.py install
```

To remove the service and stop the background process:

```bash
./omarchy_nighttime_daytime.py disable
```

## Logs

Logs are written to `omarchy_nighttime_daytime.log` in the same directory as the script.
