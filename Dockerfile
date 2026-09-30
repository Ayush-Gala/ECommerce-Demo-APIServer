FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /srv/apiserver

COPY requirements.txt .
# The ibm_db wheel bundles the Db2 CLI driver (clidriver); fail the build if it cannot load.
RUN pip install -r requirements.txt \
    && python -c "import ibm_db; print('ibm_db', ibm_db.__version__, 'imported OK')"

COPY app ./app
COPY sql ./sql

RUN useradd --system --uid 10001 --no-create-home apiserver
USER apiserver

ENV APP_PORT=8000
EXPOSE 8000

HEALTHCHECK --interval=15s --timeout=3s --start-period=10s \
    CMD python -c "import os, urllib.request; urllib.request.urlopen(f'http://127.0.0.1:{os.environ.get(\"APP_PORT\", \"8000\")}/healthz', timeout=2)"

CMD ["python", "-m", "app.main"]
