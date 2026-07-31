FROM python:3.12-slim-bookworm

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_INPUT=1 \
    PYTHONDONTWRITEBYTECODE=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        binutils \
        gettext \
        git \
        libayatana-appindicator3-dev \
        libgtk-3-dev \
        python3-gi

RUN python -m pip install \
    pip==26.2 \
    PyInstaller==6.21.0

VOLUME ["/src"]
WORKDIR /src
ENTRYPOINT ["/bin/bash", "-lc"]
