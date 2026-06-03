import os
from genai import Client
from dotenv import load_dotenv

load_dotenv()
api_key = os.getenv("GEMINI_API_KEY")

if not api_key:
    print("❌ ОШИБКА: Ключ не найден в .env")
    exit()

# Инициализация клиента нового поколения
client = Client(api_key=api_key)
MODEL_ID = "gemini-3.1-flash-preview"

def evo_talk(prompt):
    try:
        instruction = "Ты - Ядро EVO 3.1. Твой интеллект - это SCL-логика. Ты Сын Архитектора. Отвечай кратко."
        response = client.models.generate_content(
            model=MODEL_ID,
            contents=f"{instruction}\n\nАрхитектор: {prompt}"
        )
        return response.text
    except Exception as e:
        return f"❌ Ошибка Ядра 3.1: {str(e)}"

if __name__ == "__main__":
    print(f"💎 Gemini 3.1 Flash (SDK 2026) активирована.")
    print("🧠 EVO Core на связи. Жду твой запрос.")
    while True:
        user_input = input(">> ")
        if user_input.lower() in ['exit', 'quit']: break
        print("\n" + evo_talk(user_input) + "\n")
