#!/usr/bin/env bash
# Create .env from .env.example with generated secrets, this user's UID/GID, and the data dir.
set -euo pipefail
cd "$(dirname "$0")/.."

if [[ -e .env ]]; then
  echo ".env already exists; edit it or delete it first" >&2
  exit 1
fi

rand() { python3 -c 'import secrets; print(secrets.token_urlsafe(24))'; }
db_pw=$(rand)
# OpenObserve refuses to start unless the root password has lower, upper, digit and special characters.
oo_pw="$(rand)-Aa1"
oo_email=$(grep -E '^OPENOBSERVE_ROOT_EMAIL=' .env.example | cut -d= -f2-)
oo_auth=$(printf '%s:%s' "$oo_email" "$oo_pw" | base64 | tr -d '\n')

# umask first so .env is never readable by others, even briefly.
umask 077
sed -e "s|^PHOENIX_DB_PASSWORD=.*|PHOENIX_DB_PASSWORD=${db_pw}|" \
    -e "s|^OPENOBSERVE_ROOT_PASSWORD=.*|OPENOBSERVE_ROOT_PASSWORD=${oo_pw}|" \
    -e "s|^OPENOBSERVE_BASIC_AUTH=.*|OPENOBSERVE_BASIC_AUTH=${oo_auth}|" \
    -e "s|^HOST_UID=.*|HOST_UID=$(id -u)|" \
    -e "s|^HOST_GID=.*|HOST_GID=$(id -g)|" \
    .env.example > .env
chmod 600 .env
mkdir -p data/out
echo "wrote .env (mode 600) and created data/out"
