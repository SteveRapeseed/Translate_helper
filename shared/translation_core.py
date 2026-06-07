"""Shared translation logic for desktop and future mobile clients."""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class LanguageProfile:
    code: str
    english_name: str
    chinese_name: str


SUPPORTED_SOURCE_LANGUAGES: dict[str, LanguageProfile] = {
    "en": LanguageProfile("en", "English", "英语"),
    "ja": LanguageProfile("ja", "Japanese", "日语"),
    "ko": LanguageProfile("ko", "Korean", "韩语"),
    "vi": LanguageProfile("vi", "Vietnamese", "越南语"),
}

TARGET_LANGUAGE = LanguageProfile("zh-CN", "Chinese", "简体中文")

DEFAULT_SOURCE_LANGS = ("en", "ja", "ko", "vi")

_JA_KANA_RE = re.compile(r"[\u3040-\u309f\u30a0-\u30ff]")
_KO_HANGUL_RE = re.compile(r"[\uac00-\ud7af]")
_VI_DIACRITIC_RE = re.compile(
    r"[àáảãạăằắẳẵặâầấẩẫậèéẻẽẹêềếểễệìíỉĩịòóỏõọôồốổỗộơờớởỡợùúủũụưừứửữựỳýỷỹỵđ]",
    re.IGNORECASE,
)
_CJK_RE = re.compile(r"[\u4e00-\u9fff]")
_LATIN_RE = re.compile(r"[A-Za-z]")


@dataclass(frozen=True)
class TranslationResult:
    source_text: str
    translated_text: str
    source_lang: str
    target_lang: str
    status: str
    from_cache: bool = False
    skipped: bool = False


def parse_source_langs(raw: str | None) -> tuple[str, ...]:
    if not raw or not raw.strip():
        return DEFAULT_SOURCE_LANGS

    codes: list[str] = []
    for part in raw.split(","):
        code = part.strip().lower()
        if not code:
            continue
        if code not in SUPPORTED_SOURCE_LANGUAGES:
            continue
        if code not in codes:
            codes.append(code)
    return tuple(codes) if codes else DEFAULT_SOURCE_LANGS


def language_label(code: str, *, chinese: bool = True) -> str:
    if code == TARGET_LANGUAGE.code:
        return TARGET_LANGUAGE.chinese_name if chinese else TARGET_LANGUAGE.english_name
    profile = SUPPORTED_SOURCE_LANGUAGES.get(code)
    if profile is None:
        return code
    return profile.chinese_name if chinese else profile.english_name


def format_route_label(source_lang: str, target_lang: str = TARGET_LANGUAGE.code) -> str:
    return f"{language_label(source_lang)} → {language_label(target_lang)}"


def detect_source_language(text: str, allowed: tuple[str, ...] = DEFAULT_SOURCE_LANGS) -> str:
    sample = text.strip()
    if not sample:
        return "unknown"

    if _KO_HANGUL_RE.search(sample) and "ko" in allowed:
        return "ko"
    if _JA_KANA_RE.search(sample) and "ja" in allowed:
        return "ja"
    if _VI_DIACRITIC_RE.search(sample) and "vi" in allowed:
        return "vi"

    cjk_count = len(_CJK_RE.findall(sample))
    latin_count = len(_LATIN_RE.findall(sample))

    if cjk_count > 0 and latin_count == 0 and not _JA_KANA_RE.search(sample) and not _KO_HANGUL_RE.search(sample):
        return TARGET_LANGUAGE.code

    if latin_count > 0:
        if "vi" in allowed and _VI_DIACRITIC_RE.search(sample):
            return "vi"
        if "en" in allowed:
            return "en"

    return "unknown"


def should_skip_translation(text: str, detected_lang: str, target_lang: str = TARGET_LANGUAGE.code) -> tuple[bool, str]:
    if detected_lang == target_lang:
        return True, "已是中文，无需翻译"
    if not text.strip():
        return True, "文本为空"
    return False, ""


def build_system_prompt(
    *,
    source_lang: str,
    target_lang: str,
    allowed_sources: tuple[str, ...] = DEFAULT_SOURCE_LANGS,
) -> str:
    allowed_names = "、".join(language_label(code) for code in allowed_sources)
    target_name = language_label(target_lang)

    if source_lang == "unknown":
        source_hint = (
            f"自动识别源语言，优先支持：{allowed_names}。"
            "若文本已是中文则原样返回。"
        )
    elif source_lang == TARGET_LANGUAGE.code:
        source_hint = "源语言是中文，直接返回原文，不要翻译。"
    else:
        source_hint = f"源语言是{language_label(source_lang)}（{source_lang}）。"

    return (
        "你是专业翻译引擎。\n"
        f"{source_hint}\n"
        f"将用户文本翻译为{target_name}（{target_lang}）。\n"
        "要求：\n"
        "1. 只输出译文，不要解释、不要前缀。\n"
        "2. 保留原文中的专有名词、数字、URL、代码片段。\n"
        "3. 译文使用自然流畅的简体中文。"
    )


def build_translation_result(
    *,
    source_text: str,
    translated_text: str,
    source_lang: str,
    target_lang: str,
    from_cache: bool = False,
    skipped: bool = False,
) -> TranslationResult:
    route = format_route_label(source_lang, target_lang)
    if skipped:
        status = "已是中文"
    elif from_cache:
        status = f"{route}（缓存）"
    else:
        status = route
    return TranslationResult(
        source_text=source_text,
        translated_text=translated_text,
        source_lang=source_lang,
        target_lang=target_lang,
        status=status,
        from_cache=from_cache,
        skipped=skipped,
    )
