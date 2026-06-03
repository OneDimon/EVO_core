import os
import psycopg2
from google.oauth2 import service_account
from googleapiclient.discovery import build

def run_audit():
    print("🚀 Запуск комплексного аудита YMS-MMM...")
    base_path = "/root/evo_core"

    # 1. Проверка файлов
    files = {
        "Config": "config/config.yaml",
        "Credentials": "config/credentials.json",
        "Manifest": "manifest.py"
    }
    for name, path in files.items():
        if os.path.exists(os.path.join(base_path, path)):
            print(f"✅ {name}: На месте.")
        else:
            print(f"❌ {name}: Отсутствует.")

    # 2. Проверка БД с тестовым паролем
    try:
        conn = psycopg2.connect(
            dbname="postgres", 
            user="postgres", 
            password="admin123", 
            host="localhost",
            port="5432"
        )
        cur = conn.cursor()
        # Проверяем расширение vector (важно для YMS-MMM)
        cur.execute("SELECT extname FROM pg_extension WHERE extname = 'vector';")
        if cur.fetchone():
            print("✅ DB: PostgreSQL активен, расширение Vector установлено.")
        else:
            print("⚠️  DB: PostgreSQL активен, но расширение pgvector НЕ найдено.")
        cur.close()
        conn.close()
    except Exception as e:
        print(f"❌ DB: Ошибка подключения — {e}")

    # 3. Проверка Google Drive
    try:
        creds_path = os.path.join(base_path, "config/credentials.json")
        creds = service_account.Credentials.from_service_account_file(creds_path)
        service = build('drive', 'v3', credentials=creds)
        service.about().get(fields="user").execute()
        print("✅ Google: Доступ к API подтвержден.")
    except Exception as e:
        print(f"❌ Google: Ошибка доступа.")

if __name__ == "__main__":
    run_audit()
