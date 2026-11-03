#!/bin/sh
# Ownership of the mounted run volumes is repaired by the `volumes-init`
# service (docker-compose), which runs as root with default caps.
# This container runs as uid 999 (app) with cap_drop ALL, so it cannot
# chown anything here -- an earlier `if id -u = 0; then chmod 777 ...` here
# never fired and left /app/debate_lab_runs unwritable for months.
# Warn early instead of dying later on a cryptic EACCES.
for d in /app/code_lab_runs /app/debate_lab_runs /app/philosophical_council/storage/raw_data; do
    if [ -d "$d" ] && [ ! -w "$d" ]; then
        echo "[entrypoint] WARNING: $d is not writable by uid $(id -u)." >&2
        echo "[entrypoint] Run: docker compose up -d volumes-init" >&2
    fi
done
exec "$@"
