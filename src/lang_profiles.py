# -*- coding: utf-8 -*-
"""v1.6.1: Hồ sơ NGÔN NGỮ TỪ KHÓA (Việt / Anh / Nhật / Hàn).

Dùng CHUNG cho `ui_main.py` (feature "Sinh chủ đề") và `workflow/warmup.py` (runtime).
AI Brain đa ngôn ngữ xử lý tốt cả 4 thứ tiếng; mẫu offline ở đây chỉ là FALLBACK khi
KHÔNG có API key (ghép thẳng seed vào template nên có thể hơi tối nghĩa — chấp nhận).

Mọi hàm truy cập đều đi qua `norm(lang)` nên lang rác -> rơi về DEFAULT_LANG an toàn.
"""

LANG_CODES = ("vi", "en", "ja", "ko")
DEFAULT_LANG = "en"

# Nhãn nút trên UI (giữ tiếng Việt cho người dùng Việt)
LANG_LABELS = {"vi": "Tiếng Việt", "en": "Tiếng Anh", "ja": "Tiếng Nhật", "ko": "Tiếng Hàn"}
# Tên ngôn ngữ nhét vào prompt cho AI
LANG_PROMPT_NAME = {"vi": "Vietnamese", "en": "English",
                    "ja": "Japanese (日本語)", "ko": "Korean (한국어)"}


def norm(lang):
    lang = (lang or "").strip().lower()
    return lang if lang in LANG_CODES else DEFAULT_LANG


def prompt_lang_clause(lang):
    """Câu ép ngôn ngữ đầu ra cho prompt AI (dùng trong generate/plan/keyword)."""
    name = LANG_PROMPT_NAME[norm(lang)]
    return f"ALL keywords MUST be in {name} (translate the topic to {name} if it is not {name})."


# ---- Mẫu offline SINH CHỦ ĐỀ (embed seed {s}) — trộn hoạt động thực tế + học hỏi ----
TOPIC_TEMPLATES = {
    "vi": ("{s}", "{s} mới nhất", "cách {s}", "{s} cho người mới", "mua {s} ở đâu",
           "cửa hàng {s} gần đây", "{s} giá bao nhiêu", "{s} giảm cân", "lợi ích của {s}",
           "kinh nghiệm {s}", "so sánh {s}", "review {s} 2026", "{s} thời tiết hôm nay",
           "dụng cụ {s}", "sai lầm thường gặp khi {s}", "hướng dẫn {s}"),
    "en": ("{s}", "how to {s}", "best {s} for beginners", "where to buy {s} gear",
           "{s} shoes shopping", "{s} clothes shopping", "{s} shop near me",
           "{s} weather today", "{s} to lose weight", "{s} benefits for health",
           "{s} tips and tricks", "{s} mistakes to avoid", "best {s} equipment",
           "{s} vs alternatives", "{s} review 2026", "{s} for beginners guide"),
    "ja": ("{s}", "{s} とは", "{s} 初心者", "{s} おすすめ", "{s} 買うなら",
           "{s} 近くの店", "{s} 値段", "{s} ダイエット", "{s} 効果",
           "{s} やり方", "{s} 比較", "{s} レビュー 2026", "{s} 今日の天気",
           "{s} 道具", "{s} よくある失敗", "{s} 使い方"),
    "ko": ("{s}", "{s} 초보", "{s} 추천", "{s} 어디서 사", "{s} 근처 매장",
           "{s} 가격", "{s} 다이어트", "{s} 효과", "{s} 방법",
           "{s} 비교", "{s} 후기 2026", "{s} 오늘 날씨", "{s} 장비",
           "{s} 자주 하는 실수", "{s} 사용법", "{s} 입문 가이드"),
}
DEFAULT_SEED = {"vi": "chủ đề thời sự", "en": "daily life", "ja": "日常生活", "ko": "일상생활"}

# ---- Pool BƯỚC KẾ HOẠCH offline (platform, template {s}) ----
PLAN_POOL = {
    "vi": [("google", "{s}"), ("google", "cách {s}"), ("news", "tin tức {s}"), ("wikipedia", "{s}"),
           ("youtube", "{s} cho người mới"), ("google", "dụng cụ cần thiết cho {s}"),
           ("maps", "cửa hàng {s} gần đây"), ("maps", "{s} gần đây"),
           ("google", "{s} thời tiết hôm nay"), ("youtube", "mẹo {s}"),
           ("tiktok", "{s}"), ("news", "{s} giảm cân")],
    "en": [("google", "{s}"), ("google", "how to {s}"), ("news", "{s} news"), ("wikipedia", "{s}"),
           ("youtube", "{s} tutorial for beginners"), ("google", "best {s} gear to buy"),
           ("maps", "{s} shop near me"), ("maps", "{s} places near me"),
           ("google", "{s} weather today"), ("youtube", "{s} tips and tricks"),
           ("tiktok", "{s}"), ("news", "{s} to lose weight")],
    "ja": [("google", "{s}"), ("google", "{s} やり方"), ("news", "{s} ニュース"), ("wikipedia", "{s}"),
           ("youtube", "{s} 初心者向け"), ("google", "{s} おすすめ 道具"),
           ("maps", "{s} 店 近く"), ("maps", "{s} 近くの場所"),
           ("google", "{s} 今日の天気"), ("youtube", "{s} コツ"),
           ("tiktok", "{s}"), ("news", "{s} ダイエット")],
    "ko": [("google", "{s}"), ("google", "{s} 방법"), ("news", "{s} 뉴스"), ("wikipedia", "{s}"),
           ("youtube", "{s} 초보 강의"), ("google", "{s} 추천 장비"),
           ("maps", "{s} 매장 근처"), ("maps", "{s} 근처 장소"),
           ("google", "{s} 오늘 날씨"), ("youtube", "{s} 꿀팁"),
           ("tiktok", "{s}"), ("news", "{s} 다이어트")],
}
PLAN_DEFAULT_BASE = {"vi": "sức khỏe", "en": "healthy lifestyle", "ja": "健康的な生活", "ko": "건강한 생활"}

# ---- Báo theo ngôn ngữ (url, domain) cho cổng Google ----
NEWS_SITES = {
    "vi": [("https://vnexpress.net", "vnexpress.net"), ("https://dantri.com.vn", "dantri.com.vn"),
           ("https://tuoitre.vn", "tuoitre.vn"), ("https://thanhnien.vn", "thanhnien.vn"),
           ("https://vietnamnet.vn", "vietnamnet.vn"), ("https://cafef.vn", "cafef.vn"),
           ("https://tienphong.vn", "tienphong.vn")],
    "en": [("https://edition.cnn.com/", "cnn.com"), ("https://www.bbc.com/news", "bbc.com"),
           ("https://www.nytimes.com/", "nytimes.com"), ("https://www.theguardian.com/international", "theguardian.com"),
           ("https://www.reuters.com/", "reuters.com"), ("https://apnews.com/", "apnews.com"),
           ("https://www.cnbc.com/", "cnbc.com")],
    "ja": [("https://www3.nhk.or.jp/news/", "nhk.or.jp"), ("https://news.yahoo.co.jp/", "yahoo.co.jp"),
           ("https://www.asahi.com/", "asahi.com"), ("https://mainichi.jp/", "mainichi.jp"),
           ("https://www.nikkei.com/", "nikkei.com"), ("https://www.yomiuri.co.jp/", "yomiuri.co.jp")],
    "ko": [("https://news.naver.com/", "naver.com"), ("https://www.chosun.com/", "chosun.com"),
           ("https://www.donga.com/", "donga.com"), ("https://www.joongang.co.kr/", "joongang.co.kr"),
           ("https://www.hani.co.kr/", "hani.co.kr"), ("https://www.yna.co.kr/", "yna.co.kr")],
}

WEATHER_QUERIES = {
    "vi": ["thời tiết hôm nay thế nào", "dự báo thời tiết ngày mai", "hôm nay có mưa không", "nhiệt độ ngoài trời hiện tại"],
    "en": ["weather today", "weather forecast tomorrow", "is it going to rain today", "outdoor temperature now"],
    "ja": ["今日の天気", "明日の天気予報", "今日は雨が降りますか", "現在の気温"],
    "ko": ["오늘 날씨", "내일 날씨 예보", "오늘 비 와요", "현재 바깥 기온"],
}

# ---- Default fallback cho _plan_keyword (hiếm khi chạm) + session_theme ----
DEFAULTS = {
    "vi": {"google": "tin tức thời sự", "news": "tin tức mới nhất", "news2": "thời sự hôm nay",
           "video": "video giải trí", "tiktok": "giải trí", "wiki": "kiến thức", "maps": "địa điểm gần đây"},
    "en": {"google": "latest news today", "news": "latest news today", "news2": "today news headlines",
           "video": "trending videos today", "tiktok": "entertainment", "wiki": "general knowledge", "maps": "places near me"},
    "ja": {"google": "最新ニュース", "news": "最新ニュース", "news2": "今日のニュース",
           "video": "人気の動画", "tiktok": "エンタメ", "wiki": "豆知識", "maps": "近くの場所"},
    "ko": {"google": "최신 뉴스", "news": "최신 뉴스", "news2": "오늘 뉴스",
           "video": "인기 동영상", "tiktok": "엔터테인먼트", "wiki": "상식", "maps": "근처 장소"},
}
SESSION_DEFAULT = {
    "vi": {"google_query": "tin tức mới nhất", "youtube_query": "video giải trí"},
    "en": {"google_query": "latest news today", "youtube_query": "trending videos today"},
    "ja": {"google_query": "最新ニュース", "youtube_query": "人気の動画"},
    "ko": {"google_query": "최신 뉴스", "youtube_query": "인기 동영상"},
}


def topic_templates(lang):
    return TOPIC_TEMPLATES[norm(lang)]


def default_seed(lang):
    return DEFAULT_SEED[norm(lang)]


def plan_pool(lang):
    return list(PLAN_POOL[norm(lang)])


def plan_default_base(lang):
    return PLAN_DEFAULT_BASE[norm(lang)]


def news_sites(lang):
    return list(NEWS_SITES[norm(lang)])


def weather_queries(lang):
    return list(WEATHER_QUERIES[norm(lang)])


def default_kw(lang, kind):
    return DEFAULTS[norm(lang)].get(kind, "")


def session_default(lang):
    return dict(SESSION_DEFAULT[norm(lang)])
