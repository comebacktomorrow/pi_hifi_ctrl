#!/usr/bin/python3

# Monitor HDMI-CEC for volume keys, send RC5-encoded commands.
# Confirmed working with:
#   Cambridge Audio azur CX60A
#   Sony EX600 TV

#############
# CONSTANTS #
#############
VOL_UP = "key pressed: volume up (41)"
VOL_DN = "key pressed: volume down (42)"
MUTE = "key pressed: mute (43)"
READY = "audio status '7f'"  # message sent by cec-client to TV at end of handshaking

VOL_STEPS = 4

PIN = 4  # CPU GPIO number (not physical IO header pin number)

RC5_PER = 889  # half-bit period (microseconds)
CA_RC5_SYS = 16

# dictionary of possible commands, mapped to the code we need to send
cmd = {
    "vol-": 17,
    "vol+": 16,
    "mute": 13,
    "standby": 12,
    "bright": 72,
    "source+": 99,
    "source-": 126,
    "clipoff": 21,
    "clipon": 22,
    "muteon": 50,
    "muteoff": 51,
    "ampon": 110,
    "ampoff": 111,
}

#############
# Functions #
#############

# build RC5 message, return as int
def build_rc5(sys, cmd):
    RC5_START = 0b100 + (0b010 * (cmd < 64))
    RC5_SYS = int(sys)
    RC5_CMD = int(cmd)

    # RC-5 message has a 3-bit start sequence, a 5-bit system ID, and a 6-bit command.
    RC5_MSG = (
        ((RC5_START & 0b111) << 11) | ((RC5_SYS & 0b11111) << 6) | (RC5_CMD & 0b111111)
    )

    return RC5_MSG


# manchester encode waveform. Period is the half-bit period in microseconds.
def wave_mnch(DATA, PIN, PERIOD):
    pi.set_mode(PIN, pigpio.OUTPUT)  # set GPIO pin to output.

    # create msg
    # syntax: pigpio.pulse(gpio_on, gpio_off, delay us)
    msg = []
    for i in bin(DATA)[
        2:
    ]:  # this is a terrible way to iterate over bits... but it works.
        if i == "1":
            msg.append(pigpio.pulse(0, 1 << PIN, PERIOD))  # L
            msg.append(pigpio.pulse(1 << PIN, 0, PERIOD))  # H
        else:
            msg.append(pigpio.pulse(1 << PIN, 0, PERIOD))  # H
            msg.append(pigpio.pulse(0, 1 << PIN, PERIOD))  # L

    msg.append(pigpio.pulse(0, 1 << PIN, PERIOD))  # return line to idle condition.
    pi.wave_add_generic(msg)
    wid = pi.wave_create()
    return wid


##############
# Start here #
##############

import pigpio
import sys
import subprocess
import time

pi = pigpio.pi()


# generate RC5 message (int)
rc5_msg_up = build_rc5(CA_RC5_SYS, cmd["vol+"])
rc5_msg_dn = build_rc5(CA_RC5_SYS, cmd["vol-"])
# generate digital manchester-encoded waveform
wid_up = wave_mnch(rc5_msg_up, PIN, RC5_PER)
wid_dn = wave_mnch(rc5_msg_dn, PIN, RC5_PER)


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
    # Handle TV power state changes
    if "TV (0): power status changed" in l:
        # Extract the final state by taking the last quoted string
        parts = l.split("'")
        final_state = parts[-2] if len(parts) >= 2 else ""
        
        # Turn amp on for 'on' state or transition to on
        if final_state == "on" or final_state == "in transition from standby to on":
            for _ in range(4):  # Send command 4 times
                cbs = pi.wave_send_once(
                    wave_mnch(build_rc5(CA_RC5_SYS, cmd["ampon"]), PIN, RC5_PER)
                )
                time.sleep(0.1)  # Small delay between sends
            print("Amp on")
            p.stdin.write(
                "tx 50:72:01 \n"  # tell TV "Audio System Active" (i.e. turn off TV speakers)
            )
            p.stdin.flush()
            
        # Turn amp off for standby state
        elif final_state == "standby":
            for _ in range(4):  # Send command 4 times
                cbs = pi.wave_send_once(
                    wave_mnch(build_rc5(CA_RC5_SYS, cmd["ampoff"]), PIN, RC5_PER)
                )
                time.sleep(0.1)  # Small delay between sends
            print("Amp off")
    
     # Handle any playback device power status changes
    elif ": power status changed from" in l:
        print("DEBUG: Detect power status change:", l) #Trying to nail this down for ATV
        if "from 'on' to 'standby'" in l:
            for _ in range(4):  # Send command 4 times
                cbs = pi.wave_send_once(
                    wave_mnch(build_rc5(CA_RC5_SYS, cmd["ampoff"]), PIN, RC5_PER)
                )
                time.sleep(0.1)  # Small delay between sends
            print("Amp off")
        elif "from 'standby' to 'on'" in l:
            for _ in range(4):  # Send command 4 times
                cbs = pi.wave_send_once(
                    wave_mnch(build_rc5(CA_RC5_SYS, cmd["ampon"]), PIN, RC5_PER)
                )
                time.sleep(0.1)  # Small delay between sends
            print("Amp on")
            p.stdin.write(
                "tx 50:72:01 \n"  # tell TV "Audio System Active" (i.e. turn off TV speakers)
            )
            p.stdin.flush()
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
            wave_mnch(build_rc5(CA_RC5_SYS, cmd["mute"]), PIN, RC5_PER)
        )


sys.exit(0)
