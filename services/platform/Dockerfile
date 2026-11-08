ARG PYTHON_IMAGE=docker.1ms.run/library/python:3.11-slim@sha256:db20d8506e2f15b6db39b40b6015ca46bae855dec6dd326d462cfe79ae972893
FROM ${PYTHON_IMAGE}

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app \
    TZ=Asia/Taipei

WORKDIR /app

COPY requirements.txt ./
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --disable-pip-version-check -r requirements.txt

COPY app.py ./
COPY features.py ./
COPY calendar_queries.py ./
COPY calendar_events.py ./
COPY agent_policy.py ./
COPY advisor_queries.py ./
COPY advisor_contract.py ./
COPY mail_templates.py ./
COPY mail_oauth.py ./
COPY tests ./tests

RUN useradd --uid 10001 --create-home platform
USER platform
EXPOSE 8080
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8080"]

