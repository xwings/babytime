"""User-facing string translations for the gateway web UI.

The set is intentionally small: just the strings rendered by
`templates/base.html` and `templates/index.html`. Config field
identifiers (`activity_types`, `default_volume_ml`, etc.) are not
translated — they're config keys, not labels.

Placeholders use ``{name}`` and are substituted via :func:`t` with a
plain :py:meth:`str.replace`, so any literal braces in other entries
don't trip Python's ``str.format`` machinery.
"""

from __future__ import annotations

from typing import Optional

from fastapi import Request

SUPPORTED = ("en", "zh")
LANG_LABELS = {"en": "English", "zh": "中文"}
DEFAULT_LANG = "en"
LANG_COOKIE = "lang"

# Cookie lifetime: one year. Long enough that returning users keep their
# choice; not infinite so eventual stale browsers reset.
COOKIE_MAX_AGE = 60 * 60 * 24 * 365

TRANSLATIONS: dict[str, dict[str, str]] = {
    "en": {
        "app_tagline": "Little moments, lovingly logged",
        "skip_content": "Skip to content",
        "main_navigation": "Main navigation",
        "language": "Language",
        "daily_care": "THE EVERYDAY, TOGETHER",
        "welcome_heading": "Little moments. A little clearer.",
        "welcome_copy": "A gentle place to keep track of your baby’s day.",
        "today": "Today",
        "quick_log": "What’s happening?",
        "quick_log_hint": "Tap an activity to record a moment",
        "records_eyebrow": "ONE DAY AT A TIME",
        "journal_heading": "Your daily journal",
        "empty_hint": "The little things add up. Start with your first feeding.",
        "first_record": "Log a feeding",
        "make_it_yours": "MAKE IT YOURS",
        "config_intro": "Little adjustments to fit your family’s routine.",
        "config_preferences": "Your preferences",
        "config_auto_stop_minutes": "Feeding duration / timer limit (minutes)",
        "config_feeding_alert_minutes": "Feeding reminder (minutes)",
        "config_default_volume_ml": "Default milk amount (ml)",
        "config_default_feeding_type": "Default feeding type (button 1)",
        "config_timezone": "Time zone",
        "config_ui_show_count": "Days per page",
        "config_trusted_networks": "Trusted networks (CIDR)",
        "config_trusted_proxies": "Trusted proxies (CIDR)",
        "footer_note": "Made for the little moments.",
        # Nav
        "tab_records": "Records",
        "tab_config": "Configuration",
        # Live activity panel
        "last_fed": "Last fed:",
        "last_sleep": "Last sleep:",
        "feeding_alert_due": "Time to feed?",
        "activity_start_btn": "tap to start",
        "activity_stop_btn": "tap to stop",
        "activity_log_btn": "tap to log",
        # Activity display labels (custom types fall back to their raw name)
        "act_feeding": "Milk",
        "act_solid_food": "Solid food",
        "act_sleep": "Sleep",
        "act_poopoo": "Poopoo",
        "act_supplement": "Supplement",
        "act_etc": "Etc",
        # Records section
        "timeline_hint": "A little story of the day. Tap a moment to edit.",
        "edit_record": "Edit moment",
        "edit_day_note": "Edit day note",
        "record_running": "Ongoing",
        "record_now": "now",
        "record_open_hint": "Leave the end time empty while this activity is ongoing.",
        "record_delete_confirm": "Delete this record?",
        "record_save_error": "Couldn't save. Check the date, times and amount, then try again.",
        "unit_times": "×",
        "records_save": "Save changes",
        "records_delete": "Delete",
        "record_duration_invalid": "Stop time must be within {minutes} minutes of start time.",
        "date_poopoo_count": "{n} poopoo",
        "date_milk_summary": "{n} time{plural} {amount} ml milk",
        "date_food_summary": "{n} time{plural} {amount} g food",
        "date_poopoo_summary": "{n} time{plural} poopoo",
        "date_sleep_summary": "{n} time{plural} {duration} sleep",
        "date_sleep_duration": "{hours} hours {minutes} min",
        "col_day_note": "Day note",
        "day_note_placeholder": "Note for this day…",
        # Add-record
        "add_heading": "Add record",
        "add_btn": "Add",
        "sleep_start_btn": "Start sleep",
        "add_cancel": "Cancel",
        "milk_amount": "Milk amount",
        "water_amount": "Water amount",
        "feeding_type": "Feeding type",
        "feeding_type_formula": "Formula milk",
        "feeding_type_breastfeeding": "Breastfeeding",
        "feeding_type_water": "Water",
        "milk_decrease": "Decrease milk amount",
        "milk_increase": "Increase milk amount",
        "solid_food_amount": "Solid food amount",
        "amount_decrease": "Decrease amount",
        "amount_increase": "Increase amount",
        "poopoo_amount": "Amount",
        "poopoo_color": "Color",
        "poopoo_texture": "Texture",
        "poopoo_extra_notes": "Extra notes",
        "poopoo_extra_notes_placeholder": "Anything else to record…",
        "etc_notes_placeholder": "What happened?",
        "poopoo_option_many": "Many",
        "poopoo_option_less": "Less",
        "poopoo_option_yellow": "Yellow",
        "poopoo_option_green": "Green",
        "poopoo_option_soft": "Soft",
        "poopoo_option_hard": "Hard",
        "supplement_type": "Supplement",
        # Table columns
        "col_date": "Date",
        "col_start": "Start",
        "col_stop": "Stop",
        "col_end_time": "End time",
        "col_ml": "ml",
        "col_g": "g",
        "col_amount": "ml/g",
        "col_activity": "Activity",
        "col_notes": "Note",
        # Pagination + empty
        "no_records": "No records yet.",
        "pagination_page": "Page {page} of {total}",
        "pagination_prev": "← Prev",
        "pagination_next": "Next →",
        # Config tab
        "config_heading": "Configuration",
        "config_save": "Save preferences",
        "config_default_language": "Default language",
        "config_activities": "Activities",
        "config_timed": "timed",
        "config_end_time": "end time",
        "config_start_end": "start/end",
        "config_add_activity": "+ Add activity",
        "config_remove_activity": "Remove activity",
        "config_feeding_locked": "Milk is always present and uses an end time",
        "config_solid_food_locked": "Solid food is always present and uses an end time",
        "config_poopoo_options": "Poopoo options",
        "config_poopoo_options_hint": "Add or remove the choices shown in the Poopoo popup.",
        "config_add_option": "+ Add item",
        "config_remove_option": "Remove item",
        "config_supplement_options": "Supplement options",
        "config_supplement_options_hint": "Add or remove the choices shown in the Supplement popup.",
    },
    "zh": {
        "app_tagline": "用心记录每个小瞬间",
        "skip_content": "跳转到内容",
        "main_navigation": "主导航",
        "language": "语言",
        "daily_care": "一起照顾每一天",
        "welcome_heading": "小小日常，清晰记录。",
        "welcome_copy": "在这里，安心记录宝宝一天的点滴。",
        "today": "今天",
        "quick_log": "宝宝在做什么？",
        "quick_log_hint": "轻点一项，记录此刻",
        "records_eyebrow": "一天一点，用心记录",
        "journal_heading": "宝宝的日常",
        "empty_hint": "每个小瞬间都值得记录。从第一次喂奶开始吧。",
        "first_record": "记录喂奶",
        "make_it_yours": "适合你家的小习惯",
        "config_intro": "调整小细节，贴合家人的照顾节奏。",
        "config_preferences": "偏好设置",
        "config_auto_stop_minutes": "喂奶时长 / 计时上限（分钟）",
        "config_feeding_alert_minutes": "喂奶提醒间隔（分钟）",
        "config_default_volume_ml": "默认奶量（毫升）",
        "config_default_feeding_type": "默认喂食类型（按钮 1）",
        "config_timezone": "时区",
        "config_ui_show_count": "每页天数",
        "config_trusted_networks": "可信网络（CIDR）",
        "config_trusted_proxies": "可信代理（CIDR）",
        "footer_note": "用心陪伴每个小瞬间。",
        # Nav
        "tab_records": "记录",
        "tab_config": "设置",
        # Live activity panel
        "last_fed": "上次喂食:",
        "last_sleep": "上次睡眠:",
        "feeding_alert_due": "该喂奶了?",
        "activity_start_btn": "点击开始",
        "activity_stop_btn": "点击停止",
        "activity_log_btn": "点击记录",
        # Activity display labels
        "act_feeding": "奶",
        "act_solid_food": "辅食",
        "act_sleep": "睡眠",
        "act_poopoo": "便便",
        "act_supplement": "补充剂",
        "act_etc": "其他",
        # Records section
        "timeline_hint": "一天的小日常，轻点记录即可修改。",
        "edit_record": "编辑记录",
        "edit_day_note": "编辑每日备注",
        "record_running": "进行中",
        "record_now": "现在",
        "record_open_hint": "活动进行中时，请将结束时间留空。",
        "record_delete_confirm": "删除这条记录？",
        "record_save_error": "保存失败，请检查日期、时间和份量后重试。",
        "unit_times": "次",
        "records_save": "保存更改",
        "records_delete": "删除",
        "record_duration_invalid": "结束时间必须在开始后 {minutes} 分钟内。",
        "date_poopoo_count": "{n} 次便便",
        "date_milk_summary": "奶 {n} 次 {amount} 毫升",
        "date_food_summary": "辅食 {n} 次 {amount} 克",
        "date_poopoo_summary": "便便 {n} 次",
        "date_sleep_summary": "睡眠 {n} 次 {duration}",
        "date_sleep_duration": "{hours} 小时 {minutes} 分钟",
        "col_day_note": "每日备注",
        "day_note_placeholder": "当天备注…",
        # Add-record
        "add_heading": "添加记录",
        "add_btn": "添加",
        "sleep_start_btn": "开始睡眠",
        "add_cancel": "取消",
        "milk_amount": "奶量",
        "water_amount": "水量",
        "feeding_type": "喂食类型",
        "feeding_type_formula": "配方奶",
        "feeding_type_breastfeeding": "母乳喂养",
        "feeding_type_water": "水",
        "milk_decrease": "减少奶量",
        "milk_increase": "增加奶量",
        "solid_food_amount": "辅食量",
        "amount_decrease": "减少份量",
        "amount_increase": "增加份量",
        "poopoo_amount": "数量",
        "poopoo_color": "颜色",
        "poopoo_texture": "软硬",
        "poopoo_extra_notes": "额外备注",
        "poopoo_extra_notes_placeholder": "记录其他情况…",
        "etc_notes_placeholder": "记录发生的事情…",
        "poopoo_option_many": "多",
        "poopoo_option_less": "少",
        "poopoo_option_yellow": "黄色",
        "poopoo_option_green": "绿色",
        "poopoo_option_soft": "软",
        "poopoo_option_hard": "硬",
        "supplement_type": "补充剂",
        # Table columns
        "col_date": "日期",
        "col_start": "开始",
        "col_stop": "结束",
        "col_end_time": "结束时间",
        "col_ml": "毫升",
        "col_g": "克",
        "col_amount": "毫升/克",
        "col_activity": "活动",
        "col_notes": "备注",
        # Pagination + empty
        "no_records": "暂无记录。",
        "pagination_page": "第 {page} / {total} 页",
        "pagination_prev": "← 上一页",
        "pagination_next": "下一页 →",
        # Config tab
        "config_heading": "设置",
        "config_save": "保存设置",
        "config_default_language": "默认语言",
        "config_activities": "活动",
        "config_timed": "计时",
        "config_end_time": "结束时间",
        "config_start_end": "开始/结束",
        "config_add_activity": "+ 添加活动",
        "config_remove_activity": "删除活动",
        "config_feeding_locked": "奶始终存在并使用结束时间",
        "config_solid_food_locked": "辅食始终存在并使用结束时间",
        "config_poopoo_options": "便便选项",
        "config_poopoo_options_hint": "添加或删除便便弹窗中显示的选项。",
        "config_add_option": "+ 添加选项",
        "config_remove_option": "删除选项",
        "config_supplement_options": "补充剂选项",
        "config_supplement_options_hint": "添加或删除补充剂弹窗中显示的选项。",
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


def read_lang(request: Request, default: Optional[str] = None) -> str:
    """Resolve the active language: the per-browser cookie wins, else the
    gateway's configured default (`default`), else :data:`DEFAULT_LANG`."""
    cookie = request.cookies.get(LANG_COOKIE)
    return normalize(cookie) if cookie else normalize(default)


def language_options() -> list[tuple[str, str]]:
    """`(code, display label)` pairs for every supported language — drives
    the language picker on the config page."""
    return [(code, LANG_LABELS.get(code, code)) for code in SUPPORTED]


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


def poopoo_option_label(name: str, lang: str = DEFAULT_LANG) -> str:
    """Translate built-in Poopoo choices; custom choices remain unchanged."""
    if not name:
        return ""
    table = TRANSLATIONS.get(lang) or TRANSLATIONS[DEFAULT_LANG]
    key = "poopoo_option_" + name.strip().lower()
    return table.get(key) or TRANSLATIONS[DEFAULT_LANG].get(key) or name


def html_lang_attr(lang: str) -> str:
    """Value for the top-level ``<html lang="...">`` attribute."""
    return "zh-CN" if lang == "zh" else "en"
