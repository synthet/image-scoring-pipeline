#!/bin/bash
set -e

echo "Starting Docker Entrypoint Script..."

# 1. Wait for Firebird host if specified
if [ ! -z "$FIREBIRD_HOST" ]; then
    echo "Waiting for Firebird host at $FIREBIRD_HOST:3050..."
    # Simple check for port availability (using timeout and bash /dev/tcp)
    MAX_RETRIES=30
    COUNT=0
    until timeout 1 bash -c "cat < /dev/tcp/$FIREBIRD_HOST/3050" 2>/dev/null || [ $COUNT -eq $MAX_RETRIES ]; do
        echo "Still waiting for Firebird service..."
        sleep 2
        ((COUNT++))
    done
    
    if [ $COUNT -eq $MAX_RETRIES ]; then
        echo "Warning: Firebird host $FIREBIRD_HOST:3050 not reachable. Attempting to proceed anyway..."
    else
        echo "Firebird host is up."
    fi
fi

# 2. Run database migrations/initialization
echo "Initializing database..."
python3 -c "from modules.db import init_db; init_db()"

# 3. Launch the application
echo "Launching application: python launch.py $@"
exec python3 launch.py "$@"
