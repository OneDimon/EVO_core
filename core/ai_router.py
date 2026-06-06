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
    def __init__(self, config_path: str = "config/ai_router.json"):
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
            return resp.json()["message"]["content"]

        elif "gemini" in provider:
            api_key = os.getenv(provider_cfg.get("api_key_env", "GEMINI_API_KEY"))
            url = provider_cfg["endpoint"] + f"?key={api_key}"
            resp = await self._client.post(url, json={
                "contents": [{"parts": [{"text": prompt}]}]
            })
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
        """Векторизация текста — для записи и поиска символов."""
        prompt = f"Represent this knowledge entry for semantic search:\n{text}"
        # TODO: использовать dedicated embedding endpoint
        # Для Фазы 0: используем Gemini text + парсим как вектор
        # В продакшне: заменить на sentence-transformers локально
        result = await self._call_with_fallback(
            f"Return ONLY a JSON array of 768 floats representing the semantic vector for: {text}",
            task="vectorization"
        )
        try:
            return json.loads(result)
        except Exception:
            # Fallback: детерминированный хэш-вектор для тестов
            import hashlib
            h = hashlib.sha256(text.encode()).digest()
            return [((b / 255.0) - 0.5) * 2 for b in (h * 24)[:768]]

    async def classify(self, text: str, task: str) -> str:
        """Классификация: макро-корень / Тип А/Б / и др."""
        prompts = {
            "macro_root": f"From the 32 EVO knowledge roots (Φ,Λ,M,γ,ζ,β,η,κ,ε,τ,σ,α,χ,ψ,δ,ξ,Ω,Π,Θ,Ξ,Ψ,Σ,Δ,Γ,μ,ν,ρ,ι,θ,π,ω,λ), which ONE best fits this knowledge? Return ONLY the symbol: {text}",
            "type_ab": f"Is this knowledge update (A) improvement of same approach or (B) different tools/conditions? Return ONLY 'A' or 'B': {text}",
        }
        return await self._call_with_fallback(prompts.get(task, text), task)

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
