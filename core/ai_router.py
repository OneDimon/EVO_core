"""
AI Router — единственная точка вызова всех AI-процессов ядра.
Конфиг: config/ai_router.json
Правило: все AI-вызовы только через этот модуль, никогда напрямую.
"""
import json, asyncio, os, logging
from pathlib import Path
import httpx

log = logging.getLogger("evo.ai_router")

class AIRouter:
    def __init__(self, config_path: str = None):
        # fix: путь был чисто относительным (config/ai_router.json) — ломался
        # при запуске скриптов не из корня репо (тесты, bootstrap с другим CWD).
        # В реальном контейнере (Dockerfile WORKDIR /app) это не проявлялось,
        # но хрупко. Резолвим относительно расположения ЭТОГО файла — работает
        # независимо от текущей рабочей директории вызывающего кода.
        if config_path is None:
            repo_root = Path(__file__).resolve().parent.parent
            config_path = str(repo_root / "config" / "ai_router.json")
        with open(config_path) as f:
            self.cfg = json.load(f)["evo_ai_router"]
        self._client = httpx.AsyncClient(timeout=30)

    async def _call(self, provider_cfg: dict, prompt: str, task: str) -> str:
        """Универсальный вызов любого провайдера."""
        provider = provider_cfg["provider"]

        if "ollama" in provider:
            resp = await self._client.post(
                provider_cfg["endpoint"],
                json={"model": provider_cfg["model"],
                      "messages": [{"role": "user", "content": prompt}],
                      "stream": False}
            )
            resp.raise_for_status()  # N11 fix: явная ошибка вместо KeyError при 429/500
            return resp.json()["message"]["content"]

        elif "gemini" in provider:
            api_key = os.getenv(provider_cfg.get("api_key_env", "GEMINI_API_KEY"))
            url = provider_cfg["endpoint"] + f"?key={api_key}"
            resp = await self._client.post(url, json={
                "contents": [{"parts": [{"text": prompt}]}]
            })
            resp.raise_for_status()  # N11 fix: явная ошибка вместо KeyError при 429/500
            return resp.json()["candidates"][0]["content"]["parts"][0]["text"]

        else:
            # OpenAI-совместимый
            api_key = os.getenv(provider_cfg.get("api_key_env", "OPENAI_API_KEY"))
            resp = await self._client.post(
                provider_cfg["endpoint"],
                headers={"Authorization": f"Bearer {api_key}"},
                json={"model": provider_cfg["model"],
                      "messages": [{"role": "user", "content": prompt}]}
            )
            resp.raise_for_status()  # N11 fix: явная ошибка вместо KeyError при 429/500
            return resp.json()["choices"][0]["message"]["content"]

    async def _call_with_fallback(self, prompt: str, task: str) -> str:
        """Вызов с автоматическим fallback по цепочке."""
        retry = self.cfg["retry_policy"]
        chain = [self.cfg["primary"]] + self.cfg["fallback_chain"]

        for i, provider in enumerate(chain):
            for attempt in range(retry["max_retries"] if i == 0 else 1):
                try:
                    return await self._call(provider, prompt, task)
                except Exception as e:
                    log.warning(f"[ai_router] {provider['provider']} attempt {attempt+1}: {e}")
                    if attempt < retry["max_retries"] - 1:
                        backoff = retry["backoff_seconds"][min(attempt, 2)]
                        await asyncio.sleep(backoff)
            log.warning(f"[ai_router] Switching to fallback from {provider['provider']}")

        raise RuntimeError("All AI providers exhausted")

    async def embed(self, text: str) -> list[float]:
        """
        Векторизация текста через Gemini embedContent API.
        P7 fix: заменён LLM-промпт (псевдослучайный массив) на реальный embedding endpoint.
        Модель: embedding-001, dim=768 — совпадает со схемой pgvector.
        Fallback: детерминированный SHA-256 хэш-вектор (для тестов без API-ключа).
        """
        import os, hashlib
        api_key = os.getenv("GEMINI_API_KEY", "")

        def _hash_fallback(t: str) -> list[float]:
            """Детерминированный fallback — для тестов без API."""
            h = hashlib.sha256(t.encode()).digest()
            return [((b / 255.0) - 0.5) * 2 for b in (h * 24)[:768]]

        if not api_key:
            log.warning("[ai_router] GEMINI_API_KEY не задан — используется hash-fallback для embed()")
            return _hash_fallback(text)

        try:
            url = (
                "https://generativelanguage.googleapis.com/v1beta/"
                f"models/embedding-001:embedContent?key={api_key}"
            )
            resp = await self._client.post(url, json={
                "model": "models/embedding-001",
                "content": {"parts": [{"text": text[:2048]}]}
            })
            resp.raise_for_status()
            values = resp.json()["embedding"]["values"]
            # embedding-001 возвращает 768 float — совпадает с pgvector dim
            return values
        except Exception as e:
            log.warning(f"[ai_router] embed() Gemini failed: {e} — hash-fallback")
            return _hash_fallback(text)

    async def classify(self, text: str, task: str) -> str:
        """
        Классификация: макро-корень / Тип А/Б / и др.

        КРИТИЧНЫЙ ФИКС: раньше промпт "macro_root" просил модель вернуть ГОЛЫЙ
        символ (τ, κ...), но весь остальной пайплайн (ROOT_CODES, _get_root_code,
        WHERE science=$1 в knowledge_collector) работает с ПОЛНЫМИ каноническими
        именами ("Технология/Инженерия") как ключами. Из-за расхождения
        _get_root_code("τ") никогда не находил ключ в словаре (там лежит
        "Технология/Инженерия": "τ", а не "τ": "τ") — каждый новый символ
        проваливался в fallback Φ независимо от темы.
        Теперь классификатор возвращает ПОЛНОЕ имя, а короткий символ для ID
        и пути на шарде выводится централизованно через _get_root_code() —
        единственное место преобразования имя→символ во всей системе.
        """
        if task == "macro_root":
            # Список имён строится из ROOT_CODES — единственного источника
            # истины (SCL_FRACTAL_PROTOCOL.md §5) — вместо жёстко прописанного
            # списка символов, который расходился с реальным словарём.
            from core.archivist import ROOT_CODES
            names = "\n".join(f"- {name}" for name in ROOT_CODES.keys())
            prompt = (
                "From these 32 EVO knowledge macro-roots, which ONE best fits "
                f"this knowledge? Return ONLY the exact name, nothing else:\n{names}\n\n"
                f"Knowledge: {text}"
            )
            # fix: раньше call_with_fallback не был обёрнут в try/except —
            # если ВСЕ провайдеры недоступны (нет ключа + нет сети + нет
            # локальной Ollama), _call_with_fallback бросает RuntimeError
            # ДО того как срабатывала логика безопасного дефолта ниже.
            # Найдено живым тестовым прогоном 2026-07-07 (все провайдеры были
            # недоступны в песочнице без реальных ключей — классификация
            # падала с необработанным исключением вместо возврата дефолта).
            try:
                result = await self._call_with_fallback(prompt, task)
            except Exception as e:
                log.warning(f"[ai_router] classify(macro_root) все провайдеры "
                            f"недоступны: {e} — дефолт 'Философия/Логика'")
                return "Философия/Логика"
            candidate = result.strip()
            if candidate in ROOT_CODES:
                return candidate
            # Модель могла вернуть с лишним текстом — ищем точное совпадение внутри ответа
            for name in ROOT_CODES.keys():
                if name in candidate:
                    return name
            log.warning(
                f"[ai_router] classify(macro_root) вернул нераспознанное "
                f"'{candidate[:80]}' — используется дефолт 'Философия/Логика'"
            )
            return "Философия/Логика"

        if task == "personal_context":
            # Определяет: описывает ли текст УНИВЕРСАЛЬНЫЙ технический факт
            # (годится для всех пользователей) или ЧАСТНЫЙ случай (личное
            # предпочтение конкретного пользователя/агента: стиль, вкус,
            # разовое нетиповое ограничение).
            #
            # БЕЗОПАСНЫЙ ДЕФОЛТ: при любой неуверенности/сбое классификатора
            # результат — "personal" (условное решение), НЕ "universal".
            # Обоснование: ложно-универсальное решение УТЕКАЕТ в чужие
            # картриджи (риск приватности/качества для всех пользователей).
            # Ложно-условное решение просто не попадёт в общую выдачу —
            # безопасный отказ, не вред. Асимметрия рисков требует
            # асимметричного дефолта.
            prompt = (
                "Does this text describe a UNIVERSAL technical fact/solution "
                "applicable to any user (e.g. 'rate limit via Redis incr'), or "
                "a PERSONAL/individual preference specific to one user's context "
                "(e.g. 'user prefers dark theme', 'this user's legacy API version', "
                "'client wants blue buttons')? "
                "Return ONLY one word: 'universal' or 'personal'.\n\n"
                f"Text: {text[:600]}"
            )
            try:
                result = await self._call_with_fallback(prompt, task)
                answer = result.strip().lower()
                if "universal" in answer and "personal" not in answer:
                    return "universal"
                return "personal"  # включая любой неоднозначный/пустой ответ
            except Exception as e:
                log.warning(f"[ai_router] classify(personal_context) сбой: {e} "
                            f"— безопасный дефолт 'personal'")
                return "personal"

        prompts = {
            "type_ab": f"Is this knowledge update (A) improvement of same approach or (B) different tools/conditions? Return ONLY 'A' or 'B': {text}",
        }
        # fix: как и macro_root — не было try/except вокруг вызова.
        # Безопасный дефолт при сбое — "B" (новая ветка), НЕ "A" (перезапись):
        # A стирает предыдущую версию в legacy, B просто добавляет новую
        # запись рядом со старой. При неуверенности не терять информацию —
        # соответствует принципу "хронология неприкосновенна" (§17 протокола).
        try:
            return await self._call_with_fallback(prompts.get(task, text), task)
        except Exception as e:
            if task == "type_ab":
                log.warning(f"[ai_router] classify(type_ab) все провайдеры "
                            f"недоступны: {e} — безопасный дефолт 'B' (не перезаписывать)")
                return "B"
            raise

    async def generate(self, context: str, task: str) -> str:
        """Генерация текста: evolution_note, concierge вопросы и др."""
        prompts = {
            "evolution_note": f"Write a ONE-LINE evolution note 'было [old] → стало [new]' for: {context}",
            "concierge": f"Ask 3 short questions to understand: tech stack, task type (new/extend), constraints. Context: {context}",
        }
        return await self._call_with_fallback(prompts.get(task, context), task)

    async def verify(self, output: str, cartridge: str, task: str = "yms") -> dict:
        """YMS-MMM верификация вывода флагмана."""
        prompt = f"""YMS-MMM Verification. Check ALL:
1. Output matches original task 100%
2. Instructions from cartridge applied correctly
3. No version mismatches
4. No generation artifacts
Cartridge: {cartridge[:500]}
Output: {output[:1000]}
Return JSON: {{"passed": bool, "score": float, "failures": [str]}}"""
        result = await self._call_with_fallback(prompt, task)
        try:
            return json.loads(result)
        except Exception:
            return {"passed": False, "score": 0.0, "failures": ["parse_error"]}


# Singleton
ai_router = AIRouter()
