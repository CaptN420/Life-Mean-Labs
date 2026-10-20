#!/bin/sh
# Grant the app user write access to run directories before starting.
if [ "$(id -u)" = "0" ]; then
    chmod 777 /app/code_lab_runs /app/debate_lab_runs /app/philosophical_council/storage/raw_data 2>/dev/null || true
fi
exec "$@"
