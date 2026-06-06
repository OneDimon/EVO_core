"""
SCL Symbol — Pydantic модели
Нотация: τ^{auto^2}_{zp_0047}
Правило: метаданные статичны, вектор = смысл задачи, расшифровка ВСЕГДА по нотации
"""
from pydantic import BaseModel
from typing import Optional
from datetime import datetime


class ShardLink(BaseModel):
    host: str
    path: str
    mirror: Optional[str] = None


class SCLSymbol(BaseModel):
    # Адрес по нотации SCL_SYMBOLIC_NOTATION.md
    id: str                          # τ^{auto^2}_{zp_0047}
    label: str                       # "задача: авторизация ZP HSR | лекарство: куки+крипто"
    vector: list[float]              # эмбеддинг (label+science+section+subsection)

    # Фрактальная классификация (СТАТИЧНЫ после создания)
    science: str                     # "Технология"
    section: str                     # "Автоматизация"
    subsection: str                  # "ZennoPoster"

    # Рейтинги
    rating_frequency: int = 0        # R_f: только +1, никогда не сбрасывается
    confirmed_by: int = 1
    confirmed_in: list[str] = []     # ["τ","κ","η"] — макро-корни подтвердившие

    # Эволюция (НЕПРИКОСНОВЕННА)
    evolved_from: Optional[str] = None
    evolution_note: Optional[str] = None
    last_updated: datetime = None

    # Хранилище
    shard_link: ShardLink = ShardLink(host="", path="")

    # Альтернативы под разные стеки
    legacy_symbols: list[str] = []
    applicable_stacks: list[str] = []
    hyperlinks: list[str] = []       # только уточняющие детали проекта

    # Legacy версионирование
    is_legacy: bool = False
    superseded_by: Optional[str] = None
    supersedes: Optional[str] = None

    # Фоновая ассимиляция
    hypothesis: bool = False

    version_ts: Optional[datetime] = None


class SearchRequest(BaseModel):
    query_vector: list[float]
    top_k: int = 5
    stack_filter: Optional[list[str]] = None
    exclude_legacy: bool = True


class ArchiveRequest(BaseModel):
    session_id: str
    symbol: SCLSymbol
    solution_quality: str           # "ideal" | "adapted" | "gap_filled"
    deviations: Optional[str] = None
    applied_stack: list[str] = []
