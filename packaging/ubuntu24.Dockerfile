FROM ubuntu:24.04@sha256:33ceb71981b602c1a7443a53469e4dba065f7503eab3078a2d7a57a2ab987517
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3 python3-venv python3-dev binutils curl ca-certificates \
    dpkg-dev apt-utils gnupg desktop-file-utils hicolor-icon-theme \
    libegl1 libgl1 libnss3 libasound2t64 libdbus-1-3 \
    libxcb-cursor0 libxcb-icccm4 libxcb-image0 libxcb-keysyms1 \
    libxcb-render-util0 libxcb-xkb1 libxkbcommon-x11-0 \
    libreoffice-writer xvfb xauth \
    && rm -rf /var/lib/apt/lists/*
COPY requirements.txt requirements-build.txt /tmp/requirements/
RUN python3 -m venv /opt/venv && /opt/venv/bin/pip install --no-cache-dir \
    -r /tmp/requirements/requirements-build.txt
# WebEngine and Qt's optional GTK theme plugin must also be available to freeze.
RUN apt-get update && apt-get install -y --no-install-recommends \
    libxcomposite1 libxdamage1 libxfixes3 libxtst6 libxcb-shape0 libgtk-3-0t64 \
    && rm -rf /var/lib/apt/lists/*
ENV PATH="/opt/venv/bin:$PATH"
WORKDIR /work
