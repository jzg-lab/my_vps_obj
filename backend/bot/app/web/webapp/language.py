"""Shared browser language choice for initial pages and new email accounts."""

from aiohttp import web

from bot.middlewares.i18n import is_valid_locale_language_code, normalize_locale_language_code

from .common import _normalize_language

WEBAPP_LANGUAGE_COOKIE = "minishop_lang"


def match_webapp_language(raw_language: object, locales_data: object) -> str:
    if not raw_language or not isinstance(locales_data, dict):
        return ""
    language = normalize_locale_language_code(str(raw_language), prefer_known_base=False)
    if not is_valid_locale_language_code(language):
        return ""
    if language in locales_data:
        return language
    base_language = language.split("-", 1)[0]
    return base_language if base_language in locales_data else ""


def initial_webapp_language(
    request: web.Request, locales_data: object, default_language: str
) -> str:
    query = getattr(request, "query", {}) or {}
    cookies = getattr(request, "cookies", {}) or {}
    headers = getattr(request, "headers", {}) or {}
    accepted = str(headers.get("Accept-Language") or "").split(",")
    for candidate in (
        query.get("lang"),
        cookies.get(WEBAPP_LANGUAGE_COOKIE),
        *(entry.split(";", 1)[0].strip() for entry in accepted),
        default_language,
    ):
        language = match_webapp_language(candidate, locales_data)
        if language:
            return language
    if isinstance(locales_data, dict) and locales_data:
        return sorted(str(key) for key in locales_data)[0]
    return _normalize_language(default_language)
