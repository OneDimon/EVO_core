#!/bin/bash
# EVO-core Deploy Script
set -e
echo "=== EVO-core Deploy ==="

# Проверка .env
check_env() {
  if [ ! -f .env ]; then
    echo "❌ .env не найден. Скопируй .env.example и заполни."
    exit 1
  fi
  for key in EVO_HMAC_SECRET EVO_API_SECRET EVO_ENCRYPTION_KEY GEMINI_API_KEY; do
    val=$(grep "^${key}=" .env | cut -d= -f2-)
    if [ -z "$val" ] || echo "$val" | grep -q "generate_random"; then
      echo "❌ Не заполнен $key в .env"
      exit 1
    fi
  done
  echo "✅ .env проверен"
}

case "$1" in
  check)
    check_env
    ;;
  migrate)
    echo "Running migrations..."
    docker exec evo_postgres psql -U evo_user -d evo_core \
      -f /docker-entrypoint-initdb.d/001_init.sql
    docker exec evo_postgres psql -U evo_user -d evo_core \
      -f /tmp/002_config.sql 2>/dev/null || true
    docker cp db/migrations/002_config.sql evo_postgres:/tmp/
    docker exec evo_postgres psql -U evo_user -d evo_core \
      -f /tmp/002_config.sql
    docker cp db/migrations/003_users_security.sql evo_postgres:/tmp/
    docker exec evo_postgres psql -U evo_user -d evo_core \
      -f /tmp/003_users_security.sql
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
    EVO_ENV=development python tests/test_phase0.py
    ;;
  test1)
    echo "Running Phase 1+2 tests..."
    EVO_ENV=development python tests/test_phase1.py
    ;;
  gen-secrets)
    echo "Генерация секретов для .env:"
    echo "EVO_HMAC_SECRET=$(python3 -c "import secrets; print(secrets.token_hex(32))")"
    echo "EVO_API_SECRET=$(python3 -c "import secrets; print(secrets.token_hex(32))")"
    echo "EVO_ENCRYPTION_KEY=$(python3 -c "import secrets; print(secrets.token_hex(32))")"
    echo "EVO_MASTER_KEY=$(python3 -c "import secrets; print(secrets.token_hex(16))")"
    ;;
  full)
    check_env
    $0 start
    sleep 5
    $0 migrate
    $0 bootstrap
    EVO_ENV=development $0 test
    ;;
  *)
    echo "Usage: ./scripts/deploy.sh [check|migrate|bootstrap|start|stop|logs|test|test1|gen-secrets|full]"
    ;;
esac
