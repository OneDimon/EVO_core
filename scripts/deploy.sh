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
    # Прогоняет ВСЕ файлы db/migrations/*.sql по порядку (сортировка по имени,
    # 001..999). Каждая миграция в этом проекте написана идемпотентно
    # (IF NOT EXISTS / IF EXISTS / DO $$ проверка column существования),
    # поэтому безопасно гонять этот список повторно на уже существующей БД —
    # раньше здесь были захардкожены только 001-003, и 004-008 тихо не
    # накатывались на БД, созданные до их появления (они применяются
    # автоматически только при первом создании volume postgres через
    # docker-entrypoint-initdb.d).
    echo "Running migrations..."
    for f in $(ls db/migrations/*.sql | sort); do
      name=$(basename "$f")
      echo "  → $name"
      docker cp "$f" evo_postgres:/tmp/"$name"
      docker exec evo_postgres psql -U evo_user -d evo_core -v ON_ERROR_STOP=1 \
        -f /tmp/"$name"
    done
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
