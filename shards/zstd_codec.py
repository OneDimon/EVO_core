"""zstd компрессия/декомпрессия на лету в памяти — без файлов на диске.

Поддержка обученного словаря (dictionary compression):
маленькие ячейки (сотни–тысячи байт) плохо сжимаются поодиночке — zstd не
успевает построить полезные таблицы совпадений на таком объёме. Обученный
словарь на корпусе одного макро-корня даёт словарю общие паттерны раздела
(термины стека, структуру [[EVO:...]]-ссылок, типовые обороты инструкций) —
и каждая новая маленькая ячейка сжимается ощутимо эффективнее, сохраняя
при этом byte-exact восстановление и независимый точечный доступ к ячейке
(словарь общий на раздел, но каждая ячейка — свой независимый zstd-фрейм).
"""
import zstandard as zstd
import re

def compress(content: str, dict_data: bytes = None) -> bytes:
    """
    Сжимает контент. Если передан dict_data (обученный словарь раздела) —
    использует его для лучшего сжатия маленьких ячеек.
    """
    if dict_data:
        zdict = zstd.ZstdCompressionDict(dict_data)
        cctx = zstd.ZstdCompressor(level=3, dict_data=zdict)
    else:
        cctx = zstd.ZstdCompressor(level=3)
    return cctx.compress(content.encode('utf-8'))

def decompress(data: bytes, dict_data: bytes = None) -> str:
    """
    Разжимает контент. Если передан dict_data — использует его.
    ВАЖНО: словарь должен ТОЧНО совпадать с тем, что использовался при сжатии —
    иначе zstd вернёт ошибку декомпрессии (не тихий мусор, а явное исключение).
    Вызывающий код (shard_client.py) обязан ловить это и делать fallback
    на decompress без словаря для старых ячеек, записанных до обучения словаря.
    """
    if dict_data:
        zdict = zstd.ZstdCompressionDict(dict_data)
        dctx = zstd.ZstdDecompressor(dict_data=zdict)
    else:
        dctx = zstd.ZstdDecompressor()
    return dctx.decompress(data).decode('utf-8')

def train_dictionary(samples: list[bytes], dict_size: int = 32768) -> bytes:
    """
    Обучает zstd-словарь на корпусе ячеек одного макро-корня.
    dict_size по умолчанию 32 КБ — разумный размер для корпуса из
    небольших текстовых ячеек (согласно рекомендациям zstd для малых файлов).
    Требует минимум ~20-30 образцов для осмысленного результата — вызывающий
    код (shard_client.train_dictionary_for_root) отвечает за проверку порога.
    """
    zdict = zstd.train_dictionary(dict_size, samples)
    return zdict.as_bytes()

def parse_hyperlinks(content: str) -> list[dict]:
    """
    Парсинг гиперлинков из тела ячейки.
    Формат: [[EVO:τ^{auto}_{zp_0047} | описание задачи]]
    """
    pattern = r'\[\[EVO:([^\]|]+?)(?:\s*\|\s*([^\]]*))?\]\]'
    links = []
    for m in re.finditer(pattern, content):
        symbol_id = m.group(1).strip()
        description = m.group(2).strip() if m.group(2) else ""
        links.append({"symbol_id": symbol_id, "description": description})
    return links
