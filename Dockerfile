FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 PIP_NO_CACHE_DIR=1 \
    TRAINER_BIND=0.0.0.0 TRAINER_DATA=/data TRAINER_PORT=47651
WORKDIR /app

COPY requirements.txt .
RUN pip install -r requirements.txt

# Non-root. TrueNAS apps usually use uid 568: build with --build-arg UID=568 or chown the data dir to 1000.
ARG UID=1000
RUN useradd --uid $UID --no-create-home --shell /usr/sbin/nologin trainer \
    && mkdir /data && chown trainer /data
COPY --chown=root:root . .

USER trainer
VOLUME /data
EXPOSE 47651
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
  CMD python -c "import urllib.request as u; u.urlopen('http://127.0.0.1:47651/healthz', timeout=3)" || exit 1
CMD ["python", "app.py"]
