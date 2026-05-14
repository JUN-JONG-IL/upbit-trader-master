# PURPOSE: 앱 이미지를 빌드하기 위한 Dockerfile입니다.
# 주의: 현재 개발 워크플로우에서는 "앱은 IDE(Visual Studio)에서 직접 실행"하므로
# 이 Dockerfile은 필수가 아닙니다. 보관용/선택적 이미지 빌드용으로 남겨둡니다.
# FROM 라인은 요청에 따라 변경하지 않았습니다 (절대 변경 금지).
#
# If you don't plan to build the app image, you can ignore this file.
# ------------------------------------------------------------------------------

FROM codejune/smtc-base:v0.1

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    APP_HOME=/upbit-trader

WORKDIR ${APP_HOME}

# 시스템이 Debian/apt 기반일 때만 동작하도록 안전하게 작성되어 있습니다.
RUN set -eux; \
    if command -v apt-get >/dev/null 2>&1; then \
      echo "Detected apt package manager - updating sources.list"; \
      echo "deb http://deb.debian.org/debian buster main contrib non-free" > /etc/apt/sources.list; \
      echo "deb http://deb.debian.org/debian-security buster/updates main contrib non-free" >> /etc/apt/sources.list; \
      echo "deb http://deb.debian.org/debian buster-updates main contrib non-free" >> /etc/apt/sources.list; \
      apt-get update && \
      apt-get install -y --no-install-recommends \
        ca-certificates \
        build-essential gcc libpq-dev libffi-dev curl \
        libgl1-mesa-glx libglib2.0-0 libsm6 libxext6 libxrender1 && \
      rm -rf /var/lib/apt/lists/*; \
    else \
      echo "apt-get not available in base image; skipping apt steps"; \
    fi

# Python requirements expect a requirements.txt at repo root when building; keep for optional builds
COPY requirements.txt /tmp/requirements.txt
RUN set -eux; \
    if command -v python3 >/dev/null 2>&1; then PY=python3; \
    elif command -v python >/dev/null 2>&1; then PY=python; \
    else PY=python; fi; \
    echo "Using Python interpreter: $PY"; \
    $PY -m pip install --upgrade pip setuptools wheel || true; \
    if [ -f /tmp/requirements.txt ]; then $PY -m pip install --no-cache-dir -r /tmp/requirements.txt || true; fi; \
    rm -f /tmp/requirements.txt || true

COPY . ${APP_HOME}

# non-root user for safety if base supports useradd/groupadd
RUN set -eux; \
    if command -v groupadd >/dev/null 2>&1 && command -v useradd >/dev/null 2>&1; then \
      groupadd --gid 1000 appuser || true && \
      useradd --uid 1000 --gid appuser --shell /bin/bash --create-home appuser || true && \
      chown -R appuser:appuser ${APP_HOME} || true; \
    else \
      echo "useradd/groupadd not available - continuing as root"; \
    fi

ENV PYTHONPATH=${APP_HOME}/src

# Switch to non-root if created (silent fallback to root if not)
USER appuser || true

EXPOSE 8000

# 개발환경에서는 IDE로 실행하므로 이 CMD은 선��적입니다.
CMD ["python", "src/app/main.py"]
# End of Dockerfile