#!/bin/sh
# Install pi_hifi_ctrl on a Raspberry Pi: system dependencies, a Python venv,
# and (optionally) the cec-stream/pi-hifi-web systemd services.
#
# Self-discovers:
#   - the user to run the services as (whoever invoked sudo, via $SUDO_USER)
#   - the install location (wherever this repo was cloned to)
#
# Usage: sudo ./install.sh

set -eu

if [ "$(id -u)" -ne 0 ]; then
    echo "Please run as root, e.g.: sudo ./install.sh" >&2
    exit 1
fi

RUN_USER="${SUDO_USER:-$(logname 2>/dev/null || true)}"
if [ -z "$RUN_USER" ] || [ "$RUN_USER" = "root" ]; then
    echo "Warning: could not detect a non-root invoking user (\$SUDO_USER unset)." >&2
    echo "Services will run as 'root'. Re-run with 'sudo' from a normal user account to avoid this." >&2
    RUN_USER="root"
fi

REPO_DIR="$(cd "$(dirname "$0")" && pwd)"
VENV_DIR="$REPO_DIR/venv"

echo "Installing pi_hifi_ctrl for user '$RUN_USER' from '$REPO_DIR'..."

export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y git build-essential cec-utils python3-venv

# pigpiod (the pigpio daemon) is not packaged for Debian 13+ - Debian only ships
# the client-side libraries, since upstream pigpio doesn't support Debian's
# generic kernel. Build it from source instead; this only works because this
# Pi runs the Raspberry Pi Foundation's own kernel (with /dev/gpiomem), not
# Debian's generic one.
if [ ! -x /usr/local/bin/pigpiod ]; then
    echo "Building pigpiod from source (github.com/joan2937/pigpio)..."
    PIGPIO_BUILD_DIR="$(mktemp -d)"
    git clone --depth 1 https://github.com/joan2937/pigpio.git "$PIGPIO_BUILD_DIR"
    # build only the daemon + its lib; skip 'make install's python setup.py step,
    # which fails on Python >=3.12 (pigpio's setup.py needs the removed distutils)
    make -C "$PIGPIO_BUILD_DIR" pigpiod
    install -m 0755 -d /usr/local/lib
    install -m 0755 "$PIGPIO_BUILD_DIR/libpigpio.so.1" /usr/local/lib/
    ln -sf libpigpio.so.1 /usr/local/lib/libpigpio.so
    install -m 0755 -d /usr/local/bin
    install -m 0755 "$PIGPIO_BUILD_DIR/pigpiod" /usr/local/bin/pigpiod
    ldconfig
    rm -rf "$PIGPIO_BUILD_DIR"
fi
install -m 0644 "$REPO_DIR/systemd/pigpiod.service" /etc/systemd/system/pigpiod.service
systemctl daemon-reload
systemctl enable --now pigpiod

# let the service user access GPIO without being root
if [ "$RUN_USER" != "root" ]; then
    usermod -aG gpio "$RUN_USER" || true
fi

# Stop the Pi's firmware from doing its own CEC init handshake, which fights
# with cec-stream.service's use of cec-client for CEC control.
CONFIG_TXT=""
for candidate in /boot/firmware/config.txt /boot/config.txt; do
    if [ -f "$candidate" ]; then
        CONFIG_TXT="$candidate"
        break
    fi
done

REBOOT_NEEDED=0
if [ -n "$CONFIG_TXT" ]; then
    if ! grep -q "^hdmi_ignore_cec_init=1" "$CONFIG_TXT"; then
        echo "Adding hdmi_ignore_cec_init=1 to $CONFIG_TXT"
        printf '\n# Added by pi_hifi_ctrl install.sh: avoid the firmware CEC init clashing\n# with cec-stream.service.\nhdmi_ignore_cec_init=1\n' >> "$CONFIG_TXT"
        REBOOT_NEEDED=1
    fi
else
    echo "Warning: could not find config.txt; add 'hdmi_ignore_cec_init=1' to it manually." >&2
fi

python3 -m venv "$VENV_DIR"
"$VENV_DIR/bin/pip" install --upgrade pip
"$VENV_DIR/bin/pip" install "$REPO_DIR"

# ca-amp-ctrl/pi-hifi-web are installed as console-script entry points; cec_stream.py
# has no such entry point (it's a standalone script, not a libamp-based module), so
# it's run directly with the venv's python3 interpreter.
sed \
    -e "s#@@USER@@#$RUN_USER#g" \
    -e "s#@@EXEC@@#$VENV_DIR/bin/python3 $REPO_DIR/cec_stream.py#g" \
    -e "s#@@REPO_DIR@@#$REPO_DIR#g" \
    "$REPO_DIR/systemd/cec-stream.service" > /etc/systemd/system/cec-stream.service

sed \
    -e "s#@@USER@@#$RUN_USER#g" \
    -e "s#@@EXEC@@#$VENV_DIR/bin/pi-hifi-web#g" \
    "$REPO_DIR/systemd/pi-hifi-web.service" > /etc/systemd/system/pi-hifi-web.service

sed \
    -e "s#@@EXEC@@#$REPO_DIR/update.sh#g" \
    "$REPO_DIR/systemd/pi-hifi-ctrl-update.service" > /etc/systemd/system/pi-hifi-ctrl-update.service
cp "$REPO_DIR/systemd/pi-hifi-ctrl-update.timer" /etc/systemd/system/pi-hifi-ctrl-update.timer

systemctl daemon-reload
systemctl enable --now cec-stream.service

echo
echo "Done. cec-stream.service is enabled and running."
echo "pi-hifi-web.service was installed but not enabled by default (no authentication - only"
echo "enable it on a trusted network): sudo systemctl enable --now pi-hifi-web.service"
echo "pi-hifi-ctrl-update.timer was installed but not enabled by default; to auto-update daily:"
echo "  sudo systemctl enable --now pi-hifi-ctrl-update.timer"
echo "Otherwise, update manually any time with: sudo ./update.sh"

if [ "$REBOOT_NEEDED" -eq 1 ]; then
    echo
    echo "hdmi_ignore_cec_init=1 was added to $CONFIG_TXT - a reboot is required for it to take effect."
fi
