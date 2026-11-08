ARG PYTHON_IMAGE=docker.1ms.run/library/python:3.11-slim@sha256:db20d8506e2f15b6db39b40b6015ca46bae855dec6dd326d462cfe79ae972893
FROM ${PYTHON_IMAGE}

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    NODE_ENV=production \
    DEBIAN_FRONTEND=noninteractive

RUN sed -i 's|http://deb.debian.org|https://deb.debian.org|g' /etc/apt/sources.list.d/debian.sources \
    && apt-get -o Acquire::Retries=3 -o Acquire::https::Timeout=30 update \
    && apt-get install -y --no-install-recommends \
      build-essential \
      curl \
      git \
      nodejs \
      npm \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY package.json ./
RUN --mount=type=cache,target=/root/.npm \
    npm install --no-audit --no-fund

COPY requirements.txt ./
COPY requirements-upstream.txt ./
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --disable-pip-version-check -r requirements.txt

COPY apis ./apis
COPY xhs_utils ./xhs_utils
COPY static ./static
COPY server.py ./
COPY tests ./tests

RUN mkdir -p /app/datas/media_datas /app/datas/excel_datas \
    && useradd --create-home --uid 10001 xhs \
    && chown -R xhs:xhs /app

USER xhs
EXPOSE 5000

CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "5000"]

