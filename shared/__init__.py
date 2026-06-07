"""Shared translation logic for desktop and mobile clients."""

from translation_core import (
    DEFAULT_SOURCE_LANGS,
    TARGET_LANGUAGE,
    SUPPORTED_SOURCE_LANGUAGES,
    LanguageProfile,
    TranslationResult,
    build_system_prompt,
    build_translation_result,
    detect_source_language,
    format_route_label,
    language_label,
    parse_source_langs,
    should_skip_translation,
)

__all__ = [
    "DEFAULT_SOURCE_LANGS",
    "TARGET_LANGUAGE",
    "SUPPORTED_SOURCE_LANGUAGES",
    "LanguageProfile",
    "TranslationResult",
    "build_system_prompt",
    "build_translation_result",
    "detect_source_language",
    "format_route_label",
    "language_label",
    "parse_source_langs",
    "should_skip_translation",
]
