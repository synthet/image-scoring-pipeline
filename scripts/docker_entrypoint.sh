#!/bin/bash
set -e

echo "Starting Docker Entrypoint Script..."

# 1. Wait for Firebird on the Windows host (exposed as host.docker.internal)
FB_HOST="${FIREBIRD_HOST:-host.docker.internal}"
FB_PORT=3050
echo "Waiting for Firebird at $FB_HOST:$FB_PORT..."
MAX_RETRIES=30
COUNT=0
until bash -c ": > /dev/tcp/$FB_HOST/$FB_PORT" 2>/dev/null || [ $COUNT -eq $MAX_RETRIES ]; do
    echo "Still waiting for Firebird..."
    sleep 2
    COUNT=$(( COUNT + 1 ))
done

if [ $COUNT -eq $MAX_RETRIES ]; then
    echo "Warning: Firebird at $FB_HOST:$FB_PORT not reachable. Attempting to proceed anyway..."
else
    echo "Firebird is up."
fi

# 2. Run database migrations/initialization
echo "Initializing database..."
python3 -c "from modules.db import init_db; init_db()"

# 3. Launch the application
echo "Launching application: python launch.py $@"
exec python3 launch.py "$@"
