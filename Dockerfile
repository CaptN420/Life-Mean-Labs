# syntax=docker/dockerfile:1

FROM python:3.12-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    VIRTUAL_ENV=/opt/venv \
    PATH="/opt/venv/bin:$PATH"

RUN python -m venv "$VIRTUAL_ENV"

WORKDIR /build
COPY pyproject.toml README.md ./
COPY analysis ./analysis
COPY autopilot ./autopilot
COPY code_lab ./code_lab
COPY compare ./compare
COPY core ./core
COPY debate_lab ./debate_lab
COPY experiments ./experiments
COPY experimental ./experimental
COPY library ./library
COPY philosophical_council ./philosophical_council
COPY protocols ./protocols
COPY role_templates ./role_templates

RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir .

FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    VIRTUAL_ENV=/opt/venv \
    PATH="/opt/venv/bin:$PATH" \
    PORT=8080

RUN groupadd --system app \
    && useradd --system --gid app --create-home --home-dir /home/app app \
    && mkdir -p /app /app/data /app/overrides \
    && chown -R app:app /app /home/app

WORKDIR /app
COPY --from=builder /opt/venv /opt/venv
COPY --chown=app:app . .

USER app
EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "from urllib.request import urlopen; urlopen('http://127.0.0.1:8080/dashboard', timeout=3)"

ENTRYPOINT ["/app/docker-entrypoint.sh"]
CMD ["sh", "-c", "python -m experiments.dashboard --host 0.0.0.0 --port ${PORT}"]
