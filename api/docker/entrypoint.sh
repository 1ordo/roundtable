#!/bin/sh
set -e

# A signing key that is not set is generated once and kept in the data
# volume. The alternative shipped a published constant as the default, which
# meant any instance whose operator did not read the docs was signing
# sessions and encrypting its AI key with a value printed in the repository.
#
# Generating beats refusing to start: an operator who has not set one wants
# a working instance, not a lecture, and a random key on disk is strictly
# safer than a shared one. Set WD_SECRET_KEY yourself to override, which you
# should do if you ever run more than one API container.
if [ -z "${WD_SECRET_KEY}" ]; then
  key_file="${WD_DATA_DIR:-/data}/secret_key"
  if [ ! -f "$key_file" ]; then
    mkdir -p "$(dirname "$key_file")"
    python -c "import secrets; print(secrets.token_hex(32))" > "$key_file"
    chmod 600 "$key_file"
    echo "watchpile: generated a signing key at $key_file" >&2
  fi
  WD_SECRET_KEY="$(cat "$key_file")"
  export WD_SECRET_KEY
fi

case "$1" in
  api)
    alembic upgrade head
    exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --proxy-headers --forwarded-allow-ips "*"
    ;;
  worker)
    exec arq app.worker.WorkerSettings
    ;;
  *)
    echo "usage: entrypoint.sh api|worker" >&2
    exit 1
    ;;
esac
