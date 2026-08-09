FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /srv/api

COPY pyproject.toml ./
COPY app ./app
COPY alembic ./alembic
COPY alembic.ini ./
COPY docker ./docker

RUN pip install . && chmod +x docker/entrypoint.sh

EXPOSE 8000
CMD ["./docker/entrypoint.sh", "api"]
