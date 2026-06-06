"""
CLI Layer — БЛОК 04, Фаза 2
Скелетонизатор контекста: сжимает файлы проекта до сигнала.
~44 000 токенов → ~1 300 токенов (экономия 95%).
Интегрируется с Cursor / VS Code / Claude Code через LiteLLM proxy.
Правила: BLOCK_04_cli_layer.md
"""
import ast, re, json, os, logging
from pathlib import Path

log = logging.getLogger("evo.cli")


def skeletonize_python(source: str) -> str:
    """Убирает тела функций, оставляет сигнатуры + docstrings."""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return source[:500]  # fallback: первые 500 символов

    lines = source.splitlines()
    keep = set()

    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            keep.add(node.lineno)
            # Сохранить docstring если есть
            if (node.body and isinstance(node.body[0], ast.Expr)
                    and isinstance(node.body[0].value, ast.Constant)):
                for ln in range(node.body[0].lineno, node.body[0].end_lineno + 1):
                    keep.add(ln)

    result = []
    for i, line in enumerate(lines, 1):
        stripped = line.strip()
        if i in keep:
            result.append(line)
        elif stripped.startswith(("import ", "from ", "class ", "def ", "async def ",
                                   "@", "    pass", "#")):
            result.append(line)

    return "\n".join(result)


def skeletonize_json(source: str) -> str:
    """Оставляет только ключи верхнего уровня."""
    try:
        data = json.loads(source)
        if isinstance(data, dict):
            return json.dumps({k: "..." for k in list(data.keys())[:20]}, indent=2)
        if isinstance(data, list):
            return f"[... {len(data)} items ...]"
    except Exception:
        pass
    return source[:300]


def skeletonize_file(path: str) -> str:
    """Скелетонизирует файл по его типу."""
    p = Path(path)
    try:
        content = p.read_text(encoding='utf-8', errors='ignore')
    except Exception:
        return ""

    if p.suffix == '.py':
        return skeletonize_python(content)
    elif p.suffix in ('.json', '.jsonc'):
        return skeletonize_json(content)
    elif p.suffix in ('.yaml', '.yml', '.toml', '.env', '.env.example'):
        # Конфиги: только ключи без значений-секретов
        result = []
        for line in content.splitlines()[:40]:
            if '=' in line or ':' in line:
                key = line.split('=')[0].split(':')[0].strip()
                result.append(f"{key}: ...")
        return "\n".join(result)
    elif p.suffix in ('.md', '.txt'):
        return content[:800]  # первые 800 символов
    else:
        return content[:300]


def skeletonize_project(project_root: str, max_files: int = 30) -> dict:
    """
    Сканирует проект, скелетонизирует все файлы.
    Возвращает сжатый контекст для передачи в ядро.
    """
    root = Path(project_root)
    skip_dirs = {'.git', 'node_modules', '__pycache__', '.venv', 'venv',
                 'dist', 'build', '.next', 'coverage'}
    important_first = ['requirements.txt', 'package.json', 'docker-compose.yml',
                        'pyproject.toml', '.env.example']

    files_found = []
    for f in root.rglob('*'):
        if f.is_file() and not any(d in f.parts for d in skip_dirs):
            files_found.append(f)

    # Сортируем: важные файлы первыми
    def priority(p: Path) -> int:
        if p.name in important_first:
            return 0
        if p.suffix in ('.py', '.ts', '.js'):
            return 1
        if p.suffix in ('.json', '.yaml', '.yml', '.toml'):
            return 2
        return 3

    files_found.sort(key=priority)
    files_found = files_found[:max_files]

    skeletons = {}
    total_original = 0
    total_skeleton = 0

    for f in files_found:
        try:
            original = f.read_text(errors='ignore')
            skeleton = skeletonize_file(str(f))
            rel = str(f.relative_to(root))
            skeletons[rel] = skeleton
            total_original += len(original)
            total_skeleton += len(skeleton)
        except Exception:
            pass

    compression = (1 - total_skeleton / max(total_original, 1)) * 100
    log.info(f"[CLI] Skeletonized {len(skeletons)} files, "
             f"compression: {compression:.1f}% "
             f"({total_original}→{total_skeleton} chars)")

    return {
        "files": skeletons,
        "stats": {
            "files_count": len(skeletons),
            "original_chars": total_original,
            "skeleton_chars": total_skeleton,
            "compression_pct": round(compression, 1)
        }
    }


def detect_stack_from_project(project_root: str) -> dict:
    """
    Автоматически определяет стек из файлов проекта.
    Флагман вызывает это до обращения к ядру.
    """
    root = Path(project_root)
    stack = []
    frameworks = []
    databases = []
    infra = []

    # requirements.txt
    req = root / "requirements.txt"
    if req.exists():
        content = req.read_text()
        if "fastapi" in content:   frameworks.append("fastapi")
        if "flask" in content:     frameworks.append("flask")
        if "django" in content:    frameworks.append("django")
        if "asyncpg" in content:   databases.append("postgresql")
        if "redis" in content:     databases.append("redis")
        if "motor" in content:     databases.append("mongodb")
        if "sqlalchemy" in content: frameworks.append("sqlalchemy")
        stack.append("python")

    # package.json
    pkg = root / "package.json"
    if pkg.exists():
        try:
            data = json.loads(pkg.read_text())
            deps = {**data.get("dependencies", {}), **data.get("devDependencies", {})}
            if "next" in deps:     frameworks.append("nextjs")
            if "react" in deps:    frameworks.append("react")
            if "express" in deps:  frameworks.append("express")
            if "prisma" in deps:   databases.append("prisma")
            stack.append("nodejs")
        except Exception:
            pass

    # docker-compose
    dc = root / "docker-compose.yml"
    if dc.exists():
        content = dc.read_text()
        if "postgres" in content:  databases.append("postgresql")
        if "redis" in content:     databases.append("redis")
        if "nginx" in content:     infra.append("nginx")
        infra.append("docker")

    # .env / .env.example
    for envf in [root / ".env", root / ".env.example"]:
        if envf.exists():
            content = envf.read_text()
            if "n8n" in content.lower():    infra.append("n8n")
            if "telegram" in content.lower(): infra.append("telegram")

    return {
        "detected_stack": list(set(stack + frameworks + databases)),
        "frameworks": frameworks,
        "databases": databases,
        "infra": infra,
        "project_type": _infer_project_type(frameworks, databases)
    }


def _infer_project_type(frameworks: list, databases: list) -> str:
    if "fastapi" in frameworks or "flask" in frameworks:
        return "backend_api"
    if "nextjs" in frameworks or "react" in frameworks:
        return "frontend"
    if "django" in frameworks:
        return "fullstack"
    return "unknown"
