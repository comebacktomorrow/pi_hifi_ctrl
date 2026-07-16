# pi\_hifi\_ctrl
# Raspberry Pi Hi-Fi Amplifier Control

This project aims to breathe new life into old Hi-Fi amplifiers/receivers, by adding network (or automatic) control via a Raspberry Pi.

## Supported Amplifiers:

* Cambridge Audio azur 540A/640A v2, 840A v2, CXA60 (CXA81?)

If you have another Cambridge Audio amplifier, please contact me, I'll do my best to find the relevant documentation and add support for it.

## Installation:

1. Clone this repo onto the Pi (anywhere you like, e.g. your home directory):

       git clone https://github.com/andrew-bolin/pi_hifi_ctrl.git
       cd pi_hifi_ctrl

2. Run the installer as root:

       sudo ./install.sh

   [`install.sh`](install.sh) self-discovers the user to run the services as (whoever invoked `sudo`, via
   `$SUDO_USER`) and the install location (wherever you cloned the repo), then:
   * installs `cec-utils` (for `cec-client`), `git`/`build-essential`, and `python3-venv`
   * builds and installs `pigpiod` **from source** (github.com/joan2937/pigpio) and enables it as a systemd
     service — as of Debian 13 (trixie)/Raspberry Pi OS, `pigpiod` is no longer packaged for apt (Debian only
     ships the pigpio client libraries, since upstream pigpio doesn't support Debian's generic kernel); this only
     works because the Pi runs the Raspberry Pi Foundation's own kernel, which still exposes `/dev/gpiomem`
   * adds that user to the `gpio` group
   * adds `hdmi_ignore_cec_init=1` to `config.txt` (if not already present) so the Pi's own firmware CEC
     init handshake doesn't fight with `cec-stream.service` — this needs a reboot to take effect
   * creates a Python virtual environment in the repo directory and `pip install`s this package (declared in
     [`pyproject.toml`](pyproject.toml), depends on `pigpio`) into it — a venv is required on modern Raspberry Pi OS
     (Bookworm+), which blocks `pip install` into the system Python
   * installs and enables the `cec-stream` systemd service (see [`systemd/`](systemd/)); `pi-hifi-web` is installed
     but left disabled since it has no authentication — enable it yourself if you want it:
     `sudo systemctl enable --now pi-hifi-web.service`
   * installs (but leaves disabled) a `pi-hifi-ctrl-update.timer` — see [Staying up to date](#staying-up-to-date)

   This installs two console commands into the venv: `ca-amp-ctrl` and `pi-hifi-web`. `cec_stream.py` has no
   console command — it's run directly with the venv's `python3` by `cec-stream.service`, since (unlike the other
   two scripts) it's a self-contained script rather than a `libamp`-based module.
   Check status/logs with `systemctl status cec-stream.service` and `journalctl -u cec-stream.service -f`.

## Staying up to date:

To pick up new commits later, either run it manually whenever you like:

    sudo ./update.sh

or enable the timer installed by `install.sh` to check for and apply updates automatically once a day:

    sudo systemctl enable --now pi-hifi-ctrl-update.timer

Either way, [`update.sh`](update.sh) fast-forwards the repo to the latest commit on its tracked branch (it
deliberately refuses to update if the checkout has diverged/local changes, rather than discarding anything),
reinstalls the pip package into the existing venv, and restarts whichever of `cec-stream`/`pi-hifi-web` are
currently enabled. It does not redo the one-time system setup (apt packages, `gpio` group, `config.txt`) — re-run
`./install.sh` if you need that repeated.

## Wiring:
* Pick an unused GPIO pin on your Pi (the default is GPIO 4). 
* Connect your pin to the signal wire of an RCA cable, and a ground to the shield.
* Plug the RCA cable in to the "Ctrl In" socket on your Cambridge Audio amplifier.

## ca\_amp\_ctrl.py Usage:

`ca_amp_ctrl.py` is used to send a command to the amplifier.

    ca_amp_ctrl.py [-h] [--pin [GPIO number]] [--repeat [positive integer]] [--model [model number]] command

Exactly one command must be specified. 
Commands differ between amplifier models, for the 540A/640A they are:

| Command        | Function     | 
| ------------- |-------------| 
| **ampon**      | power on | 
| **ampoff**, **standby** | power off |
| **aux**, **av**, **cd**, **dvd**, **tapemon**, **tuner** | source selections ("av" is the "DMP/MP3" input) |
| **source+**, **source-** | select next/previous source |
| **tapemon** | toggle tape monitoring |
| **vol+**, **vol-** | increase/decrease volume (a small increment) |
| **mute**, **muteon**, **muteoff** | mute toggle/on/off |
| **clipon**, **clipoff** | probably turns on/off clipping protection (untested) |
| **bright** | *maybe display brightness?* |

The other optional arguments are:

**-h** merely shows brief usage help (including a full list of available commands and amplifier models)  
**--pin [GPIO number]** to specify the GPIO pin to transmit on (default: 4)  
**--repeat [positive integer]** to repeat the command (e.g. vol+/vol- only move the volume a very small amount)  
**--model [model number]** to select your amplifier model, available choices are: CXA60, 840A, or 540A.
The default is 540A, which should also be compatible with the 640A. 
CXA60 may also be compatible with CXA81. 

## cec\_stream.py Usage:

`cec_stream.py` is used to receive commands from a TV via HDMI and forward them on to the amplifier.
The amplifier will turn on & off when the TV does, and will respond to the TV's volume & mute buttons.

Run it directly (`./cec_stream.py`, or `<venv>/bin/python3 cec_stream.py` if installed via [Installation](#installation)),
or see [Installation](#installation) for running it automatically at boot via systemd.
Plug an HDMI cable from your pi into the TV, preferably via the "ARC" HDMI port.

## web.py Usage:

`web.py` (installed as `pi-hifi-web`) runs a small HTTP server so the amplifier can be controlled from any device on
your network, e.g. `GET http://<pi>:9696/?cmd=vol%2B&repeat=3`. It accepts the same `--pin`/`--model` options as
`ca_amp_ctrl.py`, plus `--port` (default `9696`). It has no authentication, so only expose it on a trusted network.
