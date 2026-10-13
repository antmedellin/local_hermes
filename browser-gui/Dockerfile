FROM debian:trixie-slim

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y --no-install-recommends \
    chromium \
    xvfb \
    openbox \
    x11vnc \
    novnc \
    websockify \
    dbus-x11 \
    at-spi2-core \
    x11-utils \
    x11-xserver-utils \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && useradd -m -u 1000 -s /bin/bash hermes

COPY start.sh /usr/local/bin/start-browser-gui
RUN chmod +x /usr/local/bin/start-browser-gui

EXPOSE 6080

CMD ["/usr/local/bin/start-browser-gui"]