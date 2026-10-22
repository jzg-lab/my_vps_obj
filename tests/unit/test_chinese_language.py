"""Chinese preferences use the same catalog throughout the existing i18n path."""

from pathlib import Path

import pytest
from aiohttp.test_utils import make_mocked_request

from bot.app.web.webapp import assets
from bot.app.web.webapp.common import _normalize_language
from bot.middlewares.i18n import JsonI18n, normalize_locale_language_code


@pytest.mark.parametrize("code", ["zh", "zh-CN", "zh_SG", "zh-Hans", "zh-Hans-CN"])
def test_simplified_language_tags(code: str) -> None:
    assert normalize_locale_language_code(code) == "zh-hans"
    assert _normalize_language(code) == "zh-hans"
    assert assets._match_webapp_language(code, {"en": {}, "zh-hans": {}}) == "zh-hans"


def test_traditional_language_is_not_silently_mapped_to_simplified() -> None:
    assert assets._match_webapp_language("zh-TW", {"en": {}, "zh-hans": {}}) == ""
    assert normalize_locale_language_code("zh-Hant") == "zh-hant"


def test_chinese_cookie_and_browser_bootstrap_catalog() -> None:
    i18n = JsonI18n(str(Path(__file__).resolve().parents[2] / "locales"))
    request = make_mocked_request(
        "GET", "/", headers={"Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8"}
    )
    assert assets._initial_webapp_language(request, i18n.locales_data, "en") == "zh-hans"
    request = make_mocked_request(
        "GET", "/", headers={"Cookie": "minishop_lang=en", "Accept-Language": "zh-CN"}
    )
    assert assets._initial_webapp_language(request, i18n.locales_data, "ru") == "en"
    request = make_mocked_request(
        "GET", "/", headers={"Cookie": "minishop_lang=zh-hans", "Accept-Language": "ru"}
    )
    assert assets._initial_webapp_language(request, i18n.locales_data, "ru") == "zh-hans"
    assert i18n.gettext("zh-CN", "wa_services_title") == "我的服务"
    assert any(option["label"] == "简体中文" for option in i18n.language_options())
    for scope, key in (("webapp", "wa_services_title"), ("admin", "admin_services_title")):
        assert assets._filter_webapp_i18n_payload(i18n.locales_data, scope, "zh-hans")["zh-hans"][
            key
        ]
