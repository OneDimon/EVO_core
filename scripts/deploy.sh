#!/bin/bash
# EVO-core Deploy Script
set -e

echo "=== EVO-core Deploy ==="

case "$1" in
  migrate)
    echo "Running migrations..."
    docker exec evo_postgres psql -U evo_user -d evo_core -f /docker-entrypoint-initdb.d/001_init.sql
    echo "✅ Migrations done"
    ;;
  bootstrap)
    echo "Running bootstrap..."
    python scripts/bootstrap.py
    python scripts/bootstrap_check.py
    ;;
  start)
    echo "Starting services..."
    docker-compose up -d postgres redis
    sleep 5
    docker-compose up -d api
    echo "✅ EVO-core started at http://localhost:8000"
    ;;
  stop)
    docker-compose down
    ;;
  logs)
    docker-compose logs -f api
    ;;
  test)
    echo "Running Phase 0 tests..."
    python tests/test_phase0.py
    ;;
  full)
    $0 start
    sleep 3
    $0 migrate
    $0 bootstrap
    $0 test
    ;;
  *)
    echo "Usage: ./scripts/deploy.sh [migrate|bootstrap|start|stop|logs|test|full]"
    ;;
esac
