"""User-facing string translations for the gateway web UI.

The set is intentionally small: just the strings rendered by
`templates/base.html` and `templates/index.html`. Config field
identifiers (`webhook_url`, `default_volume_ml`, etc.) are not
translated — they're config keys, not labels.

Placeholders use ``{name}`` and are substituted via :func:`t` with a
plain :py:meth:`str.replace` so literal braces in other entries
(e.g. ``{records}`` in the template hint) don't trip Python's
``str.format`` machinery.
"""

from __future__ import annotations

from typing import Optional

from fastapi import Request

SUPPORTED = ("en", "zh")
DEFAULT_LANG = "en"
LANG_COOKIE = "lang"

# Cookie lifetime: one year. Long enough that returning users keep their
# choice; not infinite so eventual stale browsers reset.
COOKIE_MAX_AGE = 60 * 60 * 24 * 365

TRANSLATIONS: dict[str, dict[str, str]] = {
    "en": {
        # Nav
        "tab_records": "Records",
        "tab_config": "Configuration",
        # Live activity panel
        "feed_since": "since",
        "feed_last_fed_at": "last activity at",
        "feed_none": "Nothing recorded yet.",
        "feed_ago_suffix": " ago",
        "activity_stop_btn": "Stop",
        "activity_start_btn": "Start",
        "activity_none_active": "Nothing in progress.",
        # Activity display labels (custom types fall back to their raw name)
        "act_feeding": "Feeding",
        "act_sleep": "Sleep",
        "act_poopoo": "Poopoo",
        # Records section
        "records_heading": "Records ({n} across {d} day{plural})",
        "records_select_all": "Select all on page",
        "records_save": "Save",
        "records_delete": "Delete",
        "records_upload": "Upload",
        "records_delete_confirm": "Delete the selected record(s)?",
        "records_toggle_aria": "Toggle",
        "records_select_all_on": "Select all on {date}",
        # Add-record
        "add_heading": "Add record",
        "add_btn": "Add",
        # Table columns
        "col_date": "Date",
        "col_start": "Start",
        "col_stop": "Stop",
        "col_duration": "Duration",
        "col_ml": "ml",
        "col_activity": "Activity",
        "col_notes": "Notes",
        # Pagination + empty
        "no_records": "No records yet.",
        "pagination_page": "Page {page} of {total}",
        "pagination_prev": "← Prev",
        "pagination_next": "Next →",
        # Config tab
        "config_heading": "Configuration",
        "config_save": "Save",
        "config_template_hint_html": (
            "Template placeholders: <code>{records}</code> in message, and "
            "<code>{date}</code> <code>{start_time}</code> <code>{stop_time}</code> "
            "<code>{duration}</code> <code>{volume}</code> <code>{activity}</code> "
            "<code>{notes}</code> <code>{device_id}</code> in each record line."
        ),
        # Sync banner
        "sync_banner_ok": "Sync ok",
        "sync_banner_fail": "Sync error",
        # Time units (read by the live-elapsed JS in index.html)
        "unit_hour": "h",
        "unit_minute": "m",
        "unit_second": "s",
    },
    "zh": {
        # Nav
        "tab_records": "记录",
        "tab_config": "设置",
        # Live activity panel
        "feed_since": "开始于",
        "feed_last_fed_at": "上次活动于",
        "feed_none": "尚无记录。",
        "feed_ago_suffix": "前",
        "activity_stop_btn": "停止",
        "activity_start_btn": "开始",
        "activity_none_active": "暂无进行中的活动。",
        # Activity display labels
        "act_feeding": "喂食",
        "act_sleep": "睡眠",
        "act_poopoo": "便便",
        # Records section
        "records_heading": "记录（共 {n} 条,{d} 天）",
        "records_select_all": "选中本页全部",
        "records_save": "保存",
        "records_delete": "删除",
        "records_upload": "上传",
        "records_delete_confirm": "确认删除所选记录?",
        "records_toggle_aria": "折叠",
        "records_select_all_on": "选中 {date} 全部",
        # Add-record
        "add_heading": "添加记录",
        "add_btn": "添加",
        # Table columns
        "col_date": "日期",
        "col_start": "开始",
        "col_stop": "结束",
        "col_duration": "时长",
        "col_ml": "毫升",
        "col_activity": "活动",
        "col_notes": "备注",
        # Pagination + empty
        "no_records": "暂无记录。",
        "pagination_page": "第 {page} / {total} 页",
        "pagination_prev": "← 上一页",
        "pagination_next": "下一页 →",
        # Config tab
        "config_heading": "设置",
        "config_save": "保存",
        "config_template_hint_html": (
            "模板占位符:消息体中的 <code>{records}</code>,以及每条记录行中的 "
            "<code>{date}</code> <code>{start_time}</code> <code>{stop_time}</code> "
            "<code>{duration}</code> <code>{volume}</code> <code>{activity}</code> "
            "<code>{notes}</code> <code>{device_id}</code>。"
        ),
        # Sync banner
        "sync_banner_ok": "同步成功",
        "sync_banner_fail": "同步失败",
        # Time units
        "unit_hour": "时",
        "unit_minute": "分",
        "unit_second": "秒",
    },
}


def normalize(code: Optional[str]) -> str:
    """Coerce an arbitrary lang code (cookie value, URL segment) to a
    supported one. Falls back to :data:`DEFAULT_LANG` on anything we
    don't recognise."""
    if not code:
        return DEFAULT_LANG
    code = code.strip().lower()
    return code if code in SUPPORTED else DEFAULT_LANG


def read_lang(request: Request) -> str:
    return normalize(request.cookies.get(LANG_COOKIE))


def t(key: str, lang: str = DEFAULT_LANG, **kwargs) -> str:
    table = TRANSLATIONS.get(lang) or TRANSLATIONS[DEFAULT_LANG]
    s = table.get(key) or TRANSLATIONS[DEFAULT_LANG].get(key, key)
    for k, v in kwargs.items():
        s = s.replace("{" + k + "}", str(v))
    return s


def activity_label(name: str, lang: str = DEFAULT_LANG) -> str:
    """Display label for an activity type. Known types are translated;
    user-defined ones fall back to their raw name."""
    if not name:
        return ""
    table = TRANSLATIONS.get(lang) or TRANSLATIONS[DEFAULT_LANG]
    key = "act_" + name
    return table.get(key) or TRANSLATIONS[DEFAULT_LANG].get(key) or name


def html_lang_attr(lang: str) -> str:
    """Value for the top-level ``<html lang="...">`` attribute."""
    return "zh-CN" if lang == "zh" else "en"
