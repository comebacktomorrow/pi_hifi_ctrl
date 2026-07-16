#!/bin/sh
# Update pi_hifi_ctrl to the latest committed code and reinstall it into the
# existing venv, without redoing the one-time system setup that install.sh
# does (apt packages, gpio group, config.txt). Restarts any of cec-stream/
# pi-hifi-web that are currently enabled.
#
# Usage: sudo ./update.sh

set -eu

if [ "$(id -u)" -ne 0 ]; then
    echo "Please run as root, e.g.: sudo ./update.sh" >&2
    exit 1
fi

RUN_USER="${SUDO_USER:-root}"
REPO_DIR="$(cd "$(dirname "$0")" && pwd)"
VENV_DIR="$REPO_DIR/venv"

if [ ! -x "$VENV_DIR/bin/pip" ]; then
    echo "No venv found at $VENV_DIR - run ./install.sh first." >&2
    exit 1
fi

# run git as the repo-owning user, not root, to avoid ownership/permission issues
git_as_user() {
    sudo -u "$RUN_USER" git -C "$REPO_DIR" "$@"
}

echo "Fetching latest changes..."
BEFORE="$(git_as_user rev-parse HEAD)"
git_as_user fetch --quiet origin

if ! git_as_user merge --ff-only '@{u}'; then
    echo "Could not fast-forward - there may be local changes or diverged history." >&2
    echo "Resolve manually in $REPO_DIR (e.g. 'git status'), then re-run ./update.sh." >&2
    exit 1
fi

AFTER="$(git_as_user rev-parse HEAD)"

if [ "$BEFORE" = "$AFTER" ]; then
    echo "Already up to date ($BEFORE)."
    exit 0
fi

echo "Updated $BEFORE -> $AFTER, reinstalling..."
"$VENV_DIR/bin/pip" install --upgrade "$REPO_DIR"

for svc in cec-stream pi-hifi-web; do
    if systemctl is-enabled --quiet "$svc.service" 2>/dev/null; then
        echo "Restarting $svc.service..."
        systemctl restart "$svc.service"
    fi
done

echo "Done."
