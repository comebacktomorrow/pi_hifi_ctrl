#!/usr/bin/python3

# Monitor HDMI-CEC for volume keys, send RC5-encoded commands.
# Confirmed working with:
#   Cambridge Audio azur 540A v2
#   Sony x8500d TV

import sys
import subprocess
import time

import libamp

#############
# CONSTANTS #
#############
VOL_UP = "key pressed: volume up (41)"
VOL_DN = "key pressed: volume down (42)"
MUTE = "key pressed: mute (43)"
READY = "audio status '7f'"  # message sent by cec-client to TV at end of handshaking

VOL_STEPS = 4

PIN = 4  # CPU GPIO number (not physical IO header pin number)
MODEL = "540A"


def main():
    cmd = libamp.command_table[MODEL]
    pi = libamp.pi

    # generate (or reuse cached) digital manchester-encoded waveforms
    wid_up = libamp.get_wave(libamp.build_rc5(cmd["vol+"]), PIN)
    wid_dn = libamp.get_wave(libamp.build_rc5(cmd["vol-"]), PIN)

    # run cec-client and watch output
    # (because I can't get the damn python API to work!)
    p = subprocess.Popen(
        args=["/usr/bin/cec-client", "--type", "a", "RPI"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        universal_newlines=True,
    )

    while p.poll() is None:
        l = p.stdout.readline()
        print(l)
        if "TV (0): power status changed" in l:
            power = l.split()[-1]
            if power == "'on'":
                cbs = pi.wave_send_once(
                    libamp.get_wave(libamp.build_rc5(cmd["ampon"]), PIN)
                )
                print("Amp on")
                p.stdin.write(
                    "tx 50:72:01 \n"
                )  # tell TV "Audio System Active" (i.e. turn off TV speakers)
                p.stdin.flush()
            elif power == "'standby'":
                cbs = pi.wave_send_once(
                    libamp.get_wave(libamp.build_rc5(cmd["ampoff"]), PIN)
                )
                print("Amp off")
        elif READY in l:
            p.stdin.write("tx 50:7a:08 \n")  # report vol level 08
            p.stdin.flush()  # (TV won't reduce volume if it thinks it's at zero)
        elif VOL_UP in l:
            print("Volume up")
            p.stdin.write("tx 50:7a:10 \n")  # report vol level 16
            p.stdin.flush()
            for i in range(VOL_STEPS):
                cbs = pi.wave_send_once(wid_up)
                time.sleep(0.05)
        elif VOL_DN in l:
            print("Volume down")
            p.stdin.write("tx 50:7a:04 \n")  # report vol level 04
            p.stdin.flush()
            for i in range(VOL_STEPS):
                cbs = pi.wave_send_once(wid_dn)
                time.sleep(0.05)
        elif MUTE in l:
            cbs = pi.wave_send_once(
                libamp.get_wave(libamp.build_rc5(cmd["mute"]), PIN)
            )

    return 0


if __name__ == "__main__":
    sys.exit(main())
