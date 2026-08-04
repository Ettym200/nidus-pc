import json
import os

DEFAULT_CONFIG = {
    "api_key": "",
    "api_provider": "openrouter",
    "custom_base_url": "",
    "model": "",
    "target_language": "Português",
    "region": None,
    "monitor_index": 0,
    "mode": "once",
    "capture_interval": 1.5,
    "overlay_style": "transparent",
    "hotkey_region": "f9",
    "hotkey_translate": "f10",
    "hotkey_toggle": "f11",
    "hotkey_audio": "f12",
    "audio_device": "",
    "audio_capture_mode": "system",
    "audio_target_pid": 0,
    "whisper_model": "tiny",
    "whisper_compute_device": "cpu",
    "audio_source_language": "auto",
    "audio_streaming": True,
    "interview_context": "",
    "interview_type": "Geral",
    "interview_answer_language": "Português",
    "interview_streaming": True,
    "interview_capture_mode": "system",
    "interview_target_pid": 0,
    "interview_audio_device": "",
}

LANGUAGES = [
    "Português", "Inglês", "Espanhol", "Japonês", "Francês", "Alemão",
    "Italiano", "Coreano", "Chinês Simplificado", "Chinês Tradicional",
    "Russo",
]

AUDIO_SOURCE_LANGS = [
    "auto", "Inglês", "Japonês", "Espanhol", "Português", "Francês",
    "Alemão", "Coreano", "Chinês", "Russo",
]

AUDIO_SOURCE_MAP = {
    "auto": "auto",
    "Inglês": "en", "Japonês": "ja", "Espanhol": "es", "Português": "pt",
    "Francês": "fr", "Alemão": "de", "Coreano": "ko", "Chinês": "zh", "Russo": "ru",
}

# Whisper code → possible target language labels (case-insensitive match)
_SOURCE_CODE_ALIASES = {
    "pt": ("português", "portugues", "portuguese", "pt-br", "pt"),
    "en": ("inglês", "ingles", "english", "en"),
    "es": ("espanhol", "spanish", "es"),
    "ja": ("japonês", "japones", "japanese", "ja"),
    "fr": ("francês", "frances", "french", "fr"),
    "de": ("alemão", "alemao", "german", "de"),
    "ko": ("coreano", "korean", "ko"),
    "zh": ("chinês", "chines", "chinese", "zh", "chinês simplificado", "chinês tradicional"),
    "ru": ("russo", "russian", "ru"),
}


def same_audio_language(source_code: str | None, target_label: str | None) -> bool:
    """True when heard language and translate-to language are the same (skip translate)."""
    src = (source_code or "auto").strip().lower()
    target = (target_label or "").strip().lower()
    if not src or src == "auto" or not target:
        return False
    for label, code in AUDIO_SOURCE_MAP.items():
        if label == "auto":
            continue
        if src not in (code, label.lower()):
            continue
        aliases = _SOURCE_CODE_ALIASES.get(code, (label.lower(),))
        if target == label.lower() or target in aliases:
            return True
    return src == target


INTERVIEW_TYPES = ["Geral", "Técnica", "Comportamental", "RH / Cultura"]


def config_path(app_dir: str) -> str:
    return os.path.join(app_dir, "config.json")


def load_config(app_dir: str) -> dict:
    path = config_path(app_dir)
    if os.path.exists(path):
        try:
            with open(path, encoding="utf-8") as f:
                return {**DEFAULT_CONFIG, **json.load(f)}
        except (OSError, ValueError):
            pass
    return dict(DEFAULT_CONFIG)


def save_config(app_dir: str, config: dict) -> None:
    with open(config_path(app_dir), "w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=2)
