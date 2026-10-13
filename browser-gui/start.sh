#!/bin/bash
set -e

export DISPLAY=:99
export DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/1000/bus

mkdir -p /run/user/1000
chown 1000:1000 /run/user/1000
chmod 700 /run/user/1000

# Start a D-Bus session shared with the Hermes container.
runuser -u hermes -- env \
  DBUS_SESSION_BUS_ADDRESS="$DBUS_SESSION_BUS_ADDRESS" \
  dbus-daemon --session \
  --address="$DBUS_SESSION_BUS_ADDRESS" \
  --fork --nopidfile

# Start an independent virtual X11 display.
Xvfb :99 -screen 0 1440x900x24 -ac -listen tcp &
sleep 2

# Start the desktop window manager and browser.
runuser -u hermes -- env DISPLAY=:99 \
  DBUS_SESSION_BUS_ADDRESS="$DBUS_SESSION_BUS_ADDRESS" \
  openbox-session &

sleep 2

runuser -u hermes -- env DISPLAY=:99 \
  DBUS_SESSION_BUS_ADDRESS="$DBUS_SESSION_BUS_ADDRESS" \
  chromium \
  --no-sandbox \
  --no-first-run \
  --disable-dev-shm-usage \
  --user-data-dir=/home/hermes/chromium-profile \
  about:blank &

# Provide VNC access to the same display.
x11vnc -display :99 -forever -shared -nopw \
  -rfbport 5900 -listen 0.0.0.0 &

exec websockify --web=/usr/share/novnc/ 6080 localhost:5900