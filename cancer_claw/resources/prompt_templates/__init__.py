

from pathlib import Path

_PROMPTS_DIR = Path(__file__).parent

_cache: dict[str, str] = {}

def load_prompt(prompt_name: str, /, *, use_cache: bool = True, **kwargs) -> str:

    if use_cache and prompt_name in _cache and not kwargs:
        return _cache[prompt_name]

    path = _PROMPTS_DIR / f"{prompt_name}.md"
    if not path.exists():
        raise FileNotFoundError(f"Prompt 文件不存在: {path}")

    text = path.read_text(encoding="utf-8")

    if not kwargs:
        _cache[prompt_name] = text
        return text

    return text.format(**kwargs)

def clear_cache():

    _cache.clear()
