# -*- coding: utf-8 -*-
"""v1.9.3 — CHẾ ĐỘ 4 "NGÂM KÊNH THEO NICHE" (phase = "channel").

Theo "SOP Ngâm kênh YouTube mới (A–Z)" — Giai đoạn 3 (Ngày 8–30), một phiên 45–60 phút, 5 bước:
  1. Đồng bộ tín hiệu : YouTube Location = United States + Display language = English;
                        Google gõ 1 câu hỏi thuộc niche -> đọc 1 bài ~2 phút -> tab "Video" -> bấm sang YouTube.
  2. Gieo từ khóa     : gõ từ khóa đuôi dài vào ô tìm kiếm YouTube, lọc "Tuần này/Hôm nay" + "Mức độ phổ biến",
                        tính lượt xem/giờ (VPH) từ số liệu trên trang để chọn video đang lên.
  3. Xem sâu          : 3–5 video dài (video 1 xem 70–90%, các video sau 50–60%) + thỉnh thoảng 2–3 Shorts;
                        bỏ qua quảng cáo (10% để quảng cáo ngắn chạy), không tắt tiếng, âm lượng >30%, tua ±10s.
  4. Luyện trang chủ  : bấm logo về trang chủ, CHỈ bấm 1–2 video đúng niche, xem vài phút.
  5. Đóng phiên       : đóng tab (đóng profile do tầng gọi lo).

User chốt 23/11/2026: KHÔNG viết bình luận. Like video / like bình luận người khác / Subscribe đều ở mức
RẤT THƯA và ngẫu nhiên (bốc 1 lần đầu phiên + trần theo ngày/tuần đọc từ activity_history). Kiểm tra IP: user tự làm.

Selector trong file này đều chốt từ DOM thật (diag 23/11/2026, Profile warmup 17 + MAIL241) — KHÔNG đoán:
  - ytcfg.get('GL'/'HL'/'LOGGED_IN') đọc vùng/ngôn ngữ/đăng nhập.
  - Menu: `button#avatar-btn` (đã đăng nhập) | `ytd-topbar-menu-button-renderer button` (khách);
    mục menu = `ytd-popup-container ytd-compact-link-renderer` ("Location: | United States").
  - Bộ lọc: `#filter-button button` -> `ytd-search-filter-group-renderer` (5 nhóm; nhóm 2 = ngày tải lên,
    nhóm 4 = ưu tiên) -> `ytd-search-filter-renderer a#endpoint`. Mỗi lần bấm 1 mục là trang tải lại + hộp đóng.
  - Kết quả: `ytd-video-renderer` + `a#video-title` + `#metadata-line span.inline-metadata-item` ("34 N", "2 ngày trước").
  - Like video: `like-button-view-model button`; like bình luận: `ytd-comment-thread-renderer #like-button button`.
  - Google tab Video: `a[href*='udm=vids']`; kết quả là `a:has(h3)` có chữ "www.youtube.com › watch" (href là /goto?url=).
  - Shorts: chip `yt-chip-cloud-chip-renderer button[role=tab]` "Shorts" -> `a[href^='/shorts/'].reel-item-endpoint`;
    nút kế: `#navigation-button-down button`.

Phần đầu file là HÀM THUẦN (không đụng trình duyệt) -> test offline được.
"""
import random
import re
import time

# ============================================================================
# 1. HÀM THUẦN: đọc số liệu trên trang + chấm điểm niche
# ============================================================================

_COUNT_SUFFIX = {
    "k": 1e3, "m": 1e6, "b": 1e9,                       # en: 34K / 1.2M / 3B
    "n": 1e3, "tr": 1e6, "t": 1e9,                      # vi: 34 N / 2,9 Tr / 1 T
    "nghìn": 1e3, "ngàn": 1e3, "triệu": 1e6, "tỷ": 1e9, "tỉ": 1e9,
    "thousand": 1e3, "million": 1e6, "billion": 1e9,
}
_COUNT_RE = re.compile(r"(\d[\d.,]*)\s*([^\W\d_]+)?", re.UNICODE)


def parse_count(text):
    """'34 N' / '2,9 Tr' / '1.2M views' / '1,234 views' / '1.234 lượt xem' -> int. Không đọc được -> None."""
    m = _COUNT_RE.search((text or "").replace("\xa0", " "))
    if not m:
        return None
    num, word = m.group(1), (m.group(2) or "").lower()
    mult = _COUNT_SUFFIX.get(word)
    try:
        if mult:
            return int(round(float(num.replace(",", ".").rstrip(".")) * mult))
        return int(re.sub(r"[.,]", "", num))
    except ValueError:
        return None


_AGE_UNITS_H = (
    (("second", "sec", "s", "giây"), 1 / 3600.0), (("minute", "min", "m", "phút"), 1 / 60.0),
    (("hour", "hr", "h", "giờ"), 1.0), (("day", "d", "ngày"), 24.0), (("week", "wk", "w", "tuần"), 168.0),
    (("month", "mo", "tháng"), 730.0), (("year", "yr", "y", "năm"), 8760.0),
)
# Giao diện English của YouTube viết TẮT ở trang kết quả: "34K" + "2d ago" / "20h ago" / "2mo ago" (đo thật 23/11).
# Thứ tự trong nhóm: dạng dài trước, "mo" trước "m" để "2mo" không bị đọc thành 2 phút.
# Dạng 1 chữ cái (s/m/h/d/w/y, mo) CHỈ được tính khi theo sau là "ago" — nếu không "1.2M" (lượt xem) sẽ bị đọc
# thành "2 phút". Số đứng sau dấu . , cũng bị loại (phần thập phân của lượt xem).
_AGE_RE = re.compile(
    r"(?<![\d.,])(\d+)\s*(?:"
    r"(seconds?|secs?|minutes?|mins?|hours?|hrs?|days?|weeks?|wks?|months?|mos?|years?|yrs?"
    r"|giây|phút|giờ|ngày|tuần|tháng|năm)(?![^\W\d_])"
    r"|(mo|[smhdwy])\s+ago\b)",
    re.IGNORECASE | re.UNICODE)


def parse_age_hours(text):
    """'2 days ago' / '19 giờ trước' / 'Streamed 3 weeks ago' -> số giờ (float). Không đọc được -> None."""
    m = _AGE_RE.search((text or "").replace("\xa0", " "))
    if not m:
        return None
    n, unit = int(m.group(1)), (m.group(2) or m.group(3)).lower()
    for names, hours in _AGE_UNITS_H:
        if unit in names or (len(unit) > 2 and unit.rstrip("s") in names):
            return max(n * hours, 1 / 60.0)
    return None


def parse_duration(text):
    """'18:41' / '1:00:45' -> giây. Rỗng/sai -> 0."""
    m = re.search(r"(\d{1,2}):(\d{2})(?::(\d{2}))?", text or "")
    if not m:
        return 0
    a, b, c = int(m.group(1)), int(m.group(2)), m.group(3)
    return a * 3600 + b * 60 + int(c) if c is not None else a * 60 + b


def views_per_hour(views, age_hours):
    """Lượt xem mỗi giờ (VPH). Thiếu số liệu -> 0.0. Video < 1 giờ tính như 1 giờ (tránh chia số bé)."""
    if not views or not age_hours:
        return 0.0
    return float(views) / max(float(age_hours), 1.0)


def _norm(s):
    """Chuẩn hóa để so tên kênh/handle: chữ thường, chỉ giữ chữ + số ('BBC News' == '@BBCNews')."""
    return re.sub(r"[\W_]+", "", (s or "").lower(), flags=re.UNICODE)


_STOP = set("""
a an the and or of in on at to for from with by is are was were be been it its this that these those
how what why when where who which can could should would will do does did not no yes you your we our
my me i they their he she his her as if so than then there here about into over under up down out
vs best top new video videos full official hd 4k part episode ep
là và của cho các những một cách như thế nào tại sao khi nào ở đâu có không được với trong trên về
""".split())


def _tokens(text):
    return [w for w in re.findall(r"[^\W_]+", (text or "").lower(), flags=re.UNICODE)
            if len(w) >= 3 and w not in _STOP and not w.isdigit()]


def _split_lines(value):
    if isinstance(value, (list, tuple)):
        items = [str(x) for x in value]
    else:
        items = re.split(r"[\r\n;]+", str(value or ""))
    out, seen = [], set()
    for it in items:
        it = it.strip()
        if it and it.lower() not in seen:
            seen.add(it.lower())
            out.append(it)
    return out


def channel_key(raw):
    """Link/handle/tên kênh -> khóa so sánh. 'https://www.youtube.com/@BBCNews/videos' -> 'bbcnews'."""
    s = (raw or "").strip()
    m = re.search(r"youtube\.com/(?:@|c/|user/|channel/)?([^/?#\s]+)", s, re.IGNORECASE)
    if m:
        s = m.group(1)
    try:
        from urllib.parse import unquote
        s = unquote(s)
    except Exception:
        pass
    return _norm(s.lstrip("@"))


def normalize_niche(raw):
    """Chuẩn hóa cấu hình niche (từ app_config) thành dict dùng trong phiên.
    Trả về: name, description, keywords[list], channels[list gốc], channel_keys{set}, negative[list],
            tokens{token: trọng số}, sync_locale(bool)."""
    raw = dict(raw or {})
    keywords = _split_lines(raw.get("keywords"))
    channels = _split_lines(raw.get("channels"))
    negative = [n.lower() for n in _split_lines(raw.get("negative"))]
    name = str(raw.get("name") or "").strip()
    desc = str(raw.get("description") or "").strip()
    # Trọng số token: xuất hiện ở >= 2 từ khóa hoặc trong tên/mô tả niche = token "lõi" (2 điểm), còn lại 1.
    freq = {}
    for kw in keywords:
        for t in set(_tokens(kw)):
            freq[t] = freq.get(t, 0) + 1
    core = set(_tokens(name)) | set(_tokens(desc))
    tokens = {}
    for t, n in freq.items():
        tokens[t] = 2 if (n >= 2 or t in core) else 1
    for t in core:
        tokens.setdefault(t, 2)
    # v1.9.4: hiểu biết học từ kênh đối thủ (niche_learner) — từ vựng phụ (1 điểm/từ, tối đa 3) + ghi chú người xem.
    learned = raw.get("learned") if isinstance(raw.get("learned"), dict) else {}
    learned_tokens = set()
    for term in learned.get("terms") or []:
        learned_tokens.update(t for t in _tokens(str(term)) if t not in tokens)
    # v1.9.5: độ dài video điển hình của đối thủ -> quyết định nhịp phiên. Số user nhập thắng số học qua API.
    typical, typical_src = 0, ""
    try:
        manual = float(str(raw.get("video_minutes") or "0").replace(",", "."))
    except Exception:
        manual = 0.0
    if manual > 0:
        typical, typical_src = int(manual * 60), "bạn nhập"
    else:
        try:
            typical = int(float(learned.get("typical_len_s") or 0))
        except Exception:
            typical = 0
        typical_src = "học từ kênh đối thủ" if typical > 0 else ""
    return {
        "name": name, "description": desc, "keywords": keywords, "channels": channels,
        "channel_keys": {k for k in (channel_key(c) for c in channels) if k},
        "negative": negative, "tokens": tokens,
        "learned_tokens": learned_tokens,
        "audience": str(learned.get("audience") or "").strip(),
        "typical_len_s": max(0, typical), "typical_src": typical_src,
        "sync_locale": bool(raw.get("sync_locale", True)),
    }


def pick_niche(niches, group="", niche_name=""):
    """Chọn niche cho 1 profile: tên niche ghi riêng cho profile > niche có nhóm trùng nhóm GPM của profile
    > niche không giới hạn nhóm (áp cho mọi nhóm). Không có -> {} (niche có ghi nhóm thì KHÔNG áp cho nhóm khác)."""
    niches = [n for n in (niches or []) if isinstance(n, dict) and str(n.get("name") or "").strip()]
    if not niches:
        return {}
    want = (niche_name or "").strip().lower()
    if want:
        for n in niches:
            if str(n.get("name") or "").strip().lower() == want:
                return n
    g = (group or "").strip().lower()
    if g:
        for n in niches:
            if g in [str(x).strip().lower() for x in (n.get("groups") or [])]:
                return n
    for n in niches:
        if not [x for x in (n.get("groups") or []) if str(x).strip()]:
            return n
    return {}


NICHE_SCORE_MIN = 2   # từ mức này trở lên coi là "đúng niche"


def niche_score(niche, title, channel="", channel_href=""):
    """Chấm 1 video theo niche (không cần AI). -> (điểm, lý do ngắn).
    +6 kênh nằm trong danh sách đối thủ · +2/+1 mỗi token niche có trong tiêu đề · +2 nếu tiêu đề chứa nguyên
    1 từ khóa · -5 nếu dính từ loại trừ."""
    if not niche:
        return 0, ""
    t = (title or "").lower()
    score, why = 0, []
    keys = niche.get("channel_keys") or set()
    if keys and (channel_key(channel_href) in keys or _norm(channel) in keys):
        score += 6
        why.append("kênh đối thủ")
    hits = []
    for tok, w in (niche.get("tokens") or {}).items():
        if re.search(r"(?<![^\W_])" + re.escape(tok) + r"(?:s|es)?(?![^\W_])", t, flags=re.UNICODE):
            score += w
            hits.append(tok)
    if hits:
        why.append("khớp: " + ", ".join(sorted(hits)[:4]))
    lhits = [tok for tok in (niche.get("learned_tokens") or ())
             if re.search(r"(?<![^\W_])" + re.escape(tok) + r"(?:s|es)?(?![^\W_])", t, flags=re.UNICODE)]
    if lhits:                       # từ vựng học từ kênh đối thủ: 1 điểm/từ, tối đa 3 (1 từ lẻ chưa đủ ngưỡng)
        score += min(len(lhits), 3)
        why.append("từ vựng đã học: " + ", ".join(sorted(lhits)[:4]))
    for kw in niche.get("keywords") or []:
        if len(kw) >= 6 and kw.lower() in t:
            score += 2
            why.append("chứa từ khóa")
            break
    for neg in niche.get("negative") or []:
        if neg and neg in t:
            score -= 5
            why.append(f"loại trừ: {neg}")
            break
    return score, "; ".join(why)


SESSION_MIN_S = 45 * 60     # SOP: phiên tối thiểu ~45 phút (video ngắn thì xem thêm video cho đủ)
SESSION_MAX_S = 150 * 60    # không ngồi quá 2 tiếng rưỡi dù video đối thủ rất dài
LONG_MIN_S = 180            # dưới 3 phút coi là Shorts/clip, không tính vào "video dài"


def median_len(values):
    """Trung vị các độ dài (giây) >= LONG_MIN_S. Ít hơn 3 mẫu -> 0 (chưa đủ tin)."""
    xs = sorted(int(v) for v in (values or []) if v and int(v) >= LONG_MIN_S)
    if len(xs) < 3:
        return 0
    m = len(xs) // 2
    return xs[m] if len(xs) % 2 else (xs[m - 1] + xs[m]) // 2


def _session_est_s(T, n, deep_cap, mid_cap):
    """Ước lượng thời lượng phiên: ~16 phút cố định (đồng bộ + Google + trang chủ) + ~2 phút/lần tìm + thời gian xem."""
    return (16 + 2 * n) * 60 + min(0.8 * T, deep_cap) + (n - 1) * min(0.55 * T, mid_cap)


def plan_session(typical_s, n_long=4, max_s=0, rng=random):
    """Lập nhịp phiên theo ĐỘ DÀI VIDEO ĐIỂN HÌNH của đối thủ (giây).
    - Trần xem: video 1 (sâu 70–90%) tới ~1.2 lần độ dài điển hình (12–75 phút); video sau (50–60%) tới ~0.75 lần
      (5–40 phút) -> video dài cỡ đối thủ được xem đủ tỉ lệ SOP, chỉ video dài bất thường mới bị bỏ dở.
    - Video ngắn: thêm video (tối đa 8) cho phiên đủ ~45 phút. Video dài: bớt video (tối thiểu 3), rồi mới hạ trần xem.
    - Trần phiên: ước lượng + ~10% dư, không quá SESSION_MAX_S và không quá max_s (hạn mức còn lại / trần người dùng ghim).
    -> {typical_s, n_long, deep_cap_s, mid_cap_s, fit(lo, hi), session_s, est_s, squeezed}"""
    T = min(max(float(typical_s or 0), float(LONG_MIN_S)), 3 * 3600.0)
    deep_cap = int(min(max(12 * 60, 1.2 * T), 75 * 60))
    mid_cap = int(min(max(5 * 60, 0.75 * T), 40 * 60))
    n = max(1, int(n_long))
    limit = SESSION_MAX_S if not max_s or max_s <= 0 else min(SESSION_MAX_S, float(max_s))
    while _session_est_s(T, n, deep_cap, mid_cap) < min(SESSION_MIN_S, limit) and n < 8:
        n += 1
    while _session_est_s(T, n, deep_cap, mid_cap) > limit and n > 3:
        n -= 1
    squeezed = False
    if _session_est_s(T, n, deep_cap, mid_cap) > limit:          # vẫn quá -> hạ trần xem, ưu tiên giữ video xem sâu
        squeezed = True
        room = max(300.0, limit - (16 + 2 * n) * 60)
        deep_cap = int(max(180, min(min(0.8 * T, deep_cap), 0.5 * room)))
        mid_cap = int(max(120, (room - deep_cap) / max(1, n - 1)))
    est = _session_est_s(T, n, deep_cap, mid_cap)
    session = min(limit, max(est * rng.uniform(1.05, 1.15), min(SESSION_MIN_S, limit)))
    return {"typical_s": int(T), "n_long": n, "deep_cap_s": deep_cap, "mid_cap_s": mid_cap,
            "fit": (int(max(LONG_MIN_S, 0.5 * T)), int(max(1500, 1.6 * T))),
            "session_s": int(session), "est_s": int(est), "squeezed": squeezed}


class _MidRng:
    @staticmethod
    def uniform(a, b):
        return (a + b) / 2.0


def session_range_min(typical_s, max_s=0):
    """(ít nhất, nhiều nhất) số phút trần phiên ứng với 3 và 5 video dài — để báo trước cho người dùng."""
    lo = plan_session(typical_s, 3, max_s, _MidRng)["session_s"]
    hi = plan_session(typical_s, 5, max_s, _MidRng)["session_s"]
    return int(round(min(lo, hi) / 60.0)), int(round(max(lo, hi) / 60.0))


def pick_by_vph(cands, k=4, rng=random):
    """Chọn 1 ứng viên, ưu tiên VPH cao: lấy top-k theo VPH rồi bốc có trọng số (căn bậc hai cho đỡ dồn 1 video)."""
    if not cands:
        return None
    top = sorted(cands, key=lambda c: c.get("vph", 0.0), reverse=True)[:max(1, k)]
    weights = [max(c.get("vph", 0.0), 1.0) ** 0.5 for c in top]
    return rng.choices(top, weights=weights, k=1)[0]


def parse_ai_numbers(raw, n):
    """Câu trả lời AI kiểu '2, 5, 7' / 'none' -> list chỉ số 0-based hợp lệ (< n). Không đọc được -> None."""
    s = (raw or "").strip().lower()
    if not s:
        return None
    if re.search(r"\b(none|không có|khong co|no video)\b", s) and not re.search(r"\d", s):
        return []
    nums = [int(x) for x in re.findall(r"\d+", s)]
    out = []
    for x in nums:
        if 1 <= x <= n and (x - 1) not in out:
            out.append(x - 1)
    return out if nums else None


# ============================================================================
# 2. MIXIN chạy trên trình duyệt (WarmupWorkflow kế thừa)
# ============================================================================

_JS_RESULTS = """() => Array.from(document.querySelectorAll('ytd-video-renderer')).slice(0, 24).map((e, i) => {
  const a = e.querySelector('a#video-title');
  const ch = e.querySelector('ytd-channel-name a');
  const d = e.querySelector('ytd-thumbnail-overlay-time-status-renderer, badge-shape');
  const r = e.getBoundingClientRect();
  return {idx: i, title: a ? (a.innerText || a.getAttribute('title') || '').trim() : '',
          href: a ? (a.getAttribute('href') || '') : '',
          chan: ch ? (ch.innerText || '').trim() : '', chanHref: ch ? (ch.getAttribute('href') || '') : '',
          meta: Array.from(e.querySelectorAll('#metadata-line span.inline-metadata-item')).map(s => (s.innerText || '').trim()),
          dur: d ? (d.innerText || '').trim().split('\\n')[0].trim() : '', h: Math.round(r.height)};
})"""

# Thẻ video ở trang chủ / cột gợi ý: lấy theo anchor tiêu đề rồi leo lên khung chứa (không phụ thuộc 1 kiểu thẻ).
_JS_TILES = """(scope) => {
  const root = scope ? document.querySelector(scope) : document;
  if (!root) return [];
  const out = [], seen = new Set();
  root.querySelectorAll("a[href^='/watch?v=']").forEach(a => {
    if (!a.offsetParent) return;
    const isTitle = a.id === 'video-title' || a.id === 'video-title-link' || /MetadataViewModelTitle/.test(String(a.className));
    if (!isTitle) return;
    const m = (a.getAttribute('href') || '').match(/[?&]v=([\\w-]{6,})/);
    if (!m || seen.has(m[1])) return;
    const box = a.closest('ytd-rich-item-renderer, yt-lockup-view-model, ytd-compact-video-renderer, ytd-video-renderer, ytd-rich-grid-media');
    if (!box) return;
    seen.add(m[1]);
    const ch = box.querySelector("a[href^='/@'], a[href^='/channel/']");
    const lines = (box.innerText || '').split('\\n').map(s => s.trim()).filter(Boolean);
    out.push({vid: m[1], title: (a.innerText || a.getAttribute('title') || '').trim(), lines: lines.slice(0, 8),
              chan: ch ? (ch.innerText || '').trim() : '', chanHref: ch ? (ch.getAttribute('href') || '') : ''});
  });
  return out.slice(0, 30);
}"""

_JS_PLAYER = """() => { const v = document.querySelector('video.html5-main-video') || document.querySelector('video');
  return v ? {vol: v.volume, muted: v.muted, dur: v.duration || 0, cur: v.currentTime || 0, paused: v.paused} : null; }"""


class ChannelModeMixin:
    # --- nhịp phiên (SOP: 1 phiên 45–60 phút) ---
    CH_SESSION_MIN = (45, 60)
    CH_LONG_VIDEOS = (3, 5)                 # số video dài mỗi phiên
    CH_DEEP_PCT = (0.70, 0.90)              # video 1: xem sâu
    CH_MID_PCT = (0.50, 0.60)               # video 2-3: xem trung bình
    CH_DEEP_CAP_S = (12 * 60, 18 * 60)      # trần giây cho video xem sâu (video quá dài thì bỏ dở)
    CH_MID_CAP_S = (5 * 60, 9 * 60)
    CH_LIGHT_S = (120, 300)                 # video trang chủ / đến từ Google: "xem thêm vài phút"
    CH_HOME_RESERVE_S = 8 * 60              # chừa lại cho bước 4 (trang chủ)
    CH_SHORTS_P = 0.40                      # xác suất phiên có lướt Shorts
    CH_AD_LET_RUN_P = 0.10                  # SOP: ~10% để 1 quảng cáo ngắn < 15s chạy hết
    CH_READ_COMMENTS_P = 0.35               # xác suất cuộn đọc bình luận trong 1 video
    # --- tương tác: RẤT THƯA + ngẫu nhiên (user chốt 23/11) ---
    CH_LIKE_VIDEO_P = 0.28                  # ~1 lần / 3-4 phiên
    CH_LIKE_COMMENT_P = 0.12                # ~1 lần / 8 phiên
    CH_SUB_P = 0.12
    CH_LIKE_VIDEO_DAY_CAP = 1
    CH_LIKE_COMMENT_DAY_CAP = 1
    CH_SUB_WEEK_CAP = 2                     # 7 ngày ngâm 1 niche -> tối đa 2 kênh
    # --- nhãn giao diện (vi + en; bước 1 đưa giao diện về English) ---
    CH_LANG_PARENT = ("Display language", "Language", "Ngôn ngữ hiển thị", "Ngôn ngữ", "言語", "언어")
    CH_LANG_CHILD = ("English (US)",)
    CH_LOC_PARENT = ("Location", "Địa điểm", "Vị trí", "場所", "위치")
    CH_LOC_CHILD = ("United States", "Hoa Kỳ", "アメリカ合衆国", "미국")
    CH_F_WEEK = ("This week", "Tuần này")
    CH_F_TODAY = ("Today", "Hôm nay")
    CH_F_POPULAR = ("Popularity", "Mức độ phổ biến", "View count", "Lượt xem")

    # ------------------------------------------------------------------ tiện ích
    def _ch_say(self, msg):
        print(f"      [Ngâm kênh] {msg}")

    def _ch_left(self):
        end_ts = getattr(self, "_session_end_ts", 0) or 0
        return (end_ts - time.time()) if end_ts else 9e9

    def _ch_guard(self, page):
        """Dừng êm khi user bấm Dừng; ném lỗi khi trình duyệt đã chết (giống run_random_session)."""
        if self._browser_gone(page):
            raise RuntimeError("Trình duyệt/tab của phiên đã bị đóng giữa chừng — kết thúc phiên sớm.")
        return not self.stop_requested

    def _ch_rest(self, page, lo, hi):
        end = time.time() + random.uniform(lo, hi)
        while time.time() < end and not self.stop_requested:
            time.sleep(0.5)

    def _ch_js(self, page, code, arg=None):
        try:
            return page.evaluate(code, arg)
        except Exception:
            return None

    def _ch_yt_cfg(self, page):
        cfg = self._ch_js(page, "() => (window.ytcfg ? {GL: ytcfg.get('GL'), HL: ytcfg.get('HL'), "
                                "LOGGED_IN: ytcfg.get('LOGGED_IN')} : null)")
        return cfg if isinstance(cfg, dict) else {}

    def _ch_goto(self, page, url):
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=45000)
        except Exception as e:
            if "interrupted" not in str(e).lower():
                raise
            try:
                page.evaluate("window.stop()")
            except Exception:
                pass
            self.random_sleep(2, 4)
            page.goto(url, wait_until="domcontentloaded", timeout=45000)

    def _ch_hover_click(self, page, loc, timeout=5000):
        """Rê chuột Bezier rồi bấm bằng Locator.click() (dùng cho link/menu — click toạ độ thô hay trượt)."""
        try:
            loc.scroll_into_view_if_needed(timeout=3000)
        except Exception:
            pass
        try:
            self.move_mouse_bezier(page, loc)
            self.random_sleep(0.3, 1.0)
        except Exception:
            pass
        loc.click(timeout=timeout)

    def _ch_count_recent(self, action, days):
        """Số lần đã làm `action` trong `days` ngày gần nhất (đọc activity_history). Không DB -> 0."""
        try:
            if self.db and self.profile_id and hasattr(self.db, "count_activity"):
                return int(self.db.count_activity(self.profile_id, action, days) or 0)
        except Exception:
            pass
        return 0

    # ------------------------------------------------------------------ kế hoạch tương tác (bốc 1 lần / phiên)
    def _ch_roll_engagement(self, logged_in):
        plan = {"like_video": False, "like_comment": False, "subscribe": False}
        if not logged_in:
            self._ch_say("Chưa đăng nhập YouTube trên profile này — phiên chỉ XEM (không like/sub). "
                         "Muốn ngâm kênh thật thì đăng nhập Gmail của kênh trước.")
            return plan
        if random.random() < self.CH_LIKE_VIDEO_P and self._ch_count_recent("like_video", 1) < self.CH_LIKE_VIDEO_DAY_CAP:
            plan["like_video"] = True
        if random.random() < self.CH_LIKE_COMMENT_P and self._ch_count_recent("like_comment", 1) < self.CH_LIKE_COMMENT_DAY_CAP:
            plan["like_comment"] = True
        if random.random() < self.CH_SUB_P and self._ch_count_recent("subscribe", 7) < self.CH_SUB_WEEK_CAP:
            ok = True
            try:
                if self.db and self.profile_id:
                    ok = bool(self.db.can_subscribe_today(self.profile_id))
            except Exception:
                ok = True
            plan["subscribe"] = ok
        tick = lambda b: "CÓ" if b else "không"
        self._ch_say(f"Tương tác phiên này (bốc ngẫu nhiên, rất thưa): like video {tick(plan['like_video'])} · "
                     f"like bình luận {tick(plan['like_comment'])} · đăng ký kênh {tick(plan['subscribe'])} · "
                     f"viết bình luận: KHÔNG BAO GIỜ.")
        return plan

    # ------------------------------------------------------------------ BƯỚC 1a: Location + Language
    def _ch_open_account_menu(self, page):
        for sel in ("button#avatar-btn", "ytd-topbar-menu-button-renderer button"):
            try:
                loc = page.locator(sel).first
                if loc.count() and loc.is_visible():
                    self._ch_hover_click(page, loc, timeout=4000)
                    self._pump_wait(page, random.uniform(1.5, 2.5))
                    return True
            except Exception:
                continue
        return False

    def _ch_pick_menu(self, page, parent_kws, child_names):
        """Mở menu tài khoản -> bấm mục bắt đầu bằng parent_kws -> bấm mục con có dòng đầu ∈ child_names."""
        if not self._ch_open_account_menu(page):
            return False
        items = page.locator("ytd-popup-container ytd-compact-link-renderer")
        parent = None
        for i in range(min(items.count(), 40)):
            it = items.nth(i)
            try:
                if not it.is_visible():
                    continue
                txt = (it.inner_text(timeout=1000) or "").strip()
            except Exception:
                continue
            if any(txt.startswith(k) for k in parent_kws):
                parent = it
                break
        if parent is None:
            try:
                page.keyboard.press("Escape")
            except Exception:
                pass
            return False
        self._ch_hover_click(page, parent, timeout=4000)
        self._pump_wait(page, random.uniform(1.5, 2.5))
        subs = page.locator("ytd-popup-container ytd-compact-link-renderer")
        for i in range(min(subs.count(), 200)):
            it = subs.nth(i)
            try:
                first = (it.inner_text(timeout=1000) or "").strip().split("\n")[0].strip()
            except Exception:
                continue
            if first in child_names:
                self.random_sleep(0.6, 1.6)          # "đọc danh sách" trước khi bấm
                self._ch_hover_click(page, it, timeout=4000)
                self._pump_wait(page, random.uniform(6, 8))   # YouTube tải lại trang sau khi đổi
                return True
        try:
            page.keyboard.press("Escape")
        except Exception:
            pass
        return False

    def _ch_sync_locale(self, page):
        """SOP bước 1.3 [BẮT BUỘC]: Display language = English, Location = United States. Đúng rồi thì không đụng."""
        cfg = self._ch_yt_cfg(page)
        if not cfg:
            self._ch_say("Không đọc được cấu hình YouTube — bỏ qua bước đồng bộ vùng/ngôn ngữ.")
            return cfg
        hl, gl = str(cfg.get("HL") or ""), str(cfg.get("GL") or "")
        if hl.lower().startswith("en") and gl.upper() == "US":
            self._ch_say(f"Vùng/ngôn ngữ YouTube đã đúng (Location {gl}, ngôn ngữ {hl}) — không cần đổi.")
            return cfg
        self._ch_say(f"YouTube đang để Location {gl or '?'} / ngôn ngữ {hl or '?'} — đổi sang United States + English.")
        try:
            if not hl.lower().startswith("en"):
                if self._ch_pick_menu(page, self.CH_LANG_PARENT, self.CH_LANG_CHILD):
                    self._ch_say("Đã chọn Display language: English (US).")
                else:
                    self._ch_say("Không tìm thấy mục ngôn ngữ trong menu — giữ nguyên ngôn ngữ.")
            if gl.upper() != "US" and self._ch_guard(page):
                if self._ch_pick_menu(page, self.CH_LOC_PARENT, self.CH_LOC_CHILD):
                    self._ch_say("Đã chọn Location: United States.")
                else:
                    self._ch_say("Không tìm thấy mục Location trong menu — giữ nguyên vùng.")
        except Exception as e:
            self._ch_say(f"Lỗi khi đổi vùng/ngôn ngữ ({str(e)[:90]}) — chạy tiếp với cấu hình hiện tại.")
        after = self._ch_yt_cfg(page) or cfg
        ok = str(after.get("HL") or "").lower().startswith("en") and str(after.get("GL") or "").upper() == "US"
        self._ch_say(f"Sau khi đồng bộ: Location {after.get('GL')}, ngôn ngữ {after.get('HL')} — "
                     + ("ĐẠT." if ok else "CHƯA ĐẠT (kiểm tra tay nếu lặp lại)."))
        return after

    # ------------------------------------------------------------------ BƯỚC 1b: Google -> đọc bài -> tab Video -> YouTube
    def _ch_google_results(self, page, want_youtube):
        """Các kết quả Google đang hiện (a:has(h3), bỏ anchor ẩn 0×0). want_youtube=True chỉ lấy link video YouTube."""
        out = []
        for a in page.locator("a:has(h3)").all()[:25]:
            try:
                box = self._safe_bbox(a)
                if not box or box["width"] < 10 or box["height"] < 10:
                    continue
                text = (a.inner_text(timeout=1000) or "").lower()
                href = (a.get_attribute("href") or "").lower()
            except Exception:
                continue
            is_yt = "youtube.com" in text or "youtube.com" in href
            if want_youtube:
                if is_yt and "shorts" not in text:
                    out.append(a)
            elif not is_yt and not any(d in text for d in ("facebook.com", "tiktok.com", "instagram.com", "x.com")):
                out.append(a)
        return out

    def _ch_wait_url(self, page, pred, seconds=12):
        """Chờ URL thỏa `pred` (kể cả khi Google mở tab mới -> kéo về tab phiên). True nếu tới nơi."""
        end = time.time() + seconds
        while time.time() < end:
            try:
                if pred(page.url or ""):
                    return True
                for p in page.context.pages:
                    if p is not page and pred(p.url or ""):
                        new_url = p.url
                        try:
                            p.close()
                        except Exception:
                            pass
                        page.goto(new_url, wait_until="domcontentloaded", timeout=20000)
                        return True
            except Exception:
                pass
            self._pump_wait(page, random.uniform(0.4, 0.9))
        return False

    def _ch_cross_signal(self, page, query):
        """SOP bước 1.4–1.5: tín hiệu chéo Google -> YouTube. Trả True nếu đã đáp vào 1 video YouTube."""
        self._ch_say(f"Bước 1 — Google: tìm '{query}', đọc 1 bài rồi sang tab Video.")
        t0 = time.time()
        self._ch_goto(page, "https://www.google.com")
        self.random_sleep(1, 2)
        box = page.locator("textarea[name='q'], input[name='q']").first
        box.wait_for(state="visible", timeout=8000)
        self.human_type(box, query)
        self.random_sleep(0.6, 1.5)
        page.keyboard.press("Enter")
        try:
            page.wait_for_load_state("domcontentloaded", timeout=45000)
        except Exception:
            pass
        self.random_sleep(2, 4)
        serp_url = page.url
        end = time.time() + random.randint(10, 22)
        while time.time() < end and not self.stop_requested:
            self.smooth_scroll(page, random.randint(250, 600))
            self.random_sleep(2, 4)
        if random.random() < 0.6:
            self.smooth_scroll(page, -random.randint(300, 800))
            self.random_sleep(1, 3)

        # 1) đọc 1 bài (Wiki / trang kiến thức) ~2 phút
        arts = self._ch_google_results(page, want_youtube=False)
        if arts and self._ch_guard(page):
            wiki = [a for a in arts[:6] if "wikipedia" in ((a.inner_text(timeout=1000) or "").lower())]
            target = random.choice(wiki) if wiki and random.random() < 0.6 else random.choice(arts[:5])
            try:
                self._ch_hover_click(page, target, timeout=10000)
            except Exception as e:
                print(f"      + [Google] click() trả lời: {str(e)[:80]} (bỏ qua, poll URL)")
            if self._ch_wait_url(page, lambda u: u.startswith("http") and "google." not in u.split("/")[2]):
                self.random_sleep(1, 2)
                self._simulate_scroll_and_read(page, 90, 150)
                self._log_activity(page, "channel_read_article", status="ok",
                                   duration_s=round(time.time() - t0, 1))
            else:
                self._ch_say("Bấm bài viết nhưng chưa rời Google — bỏ qua phần đọc bài.")
        else:
            self._ch_say("Trang kết quả không có bài viết phù hợp — bỏ qua phần đọc bài.")
        if not self._ch_guard(page):
            return False

        # 2) quay lại trang kết quả Google
        try:
            if "google." not in (page.url or "") or "/search" not in (page.url or ""):
                page.go_back(wait_until="domcontentloaded", timeout=30000)
                self._pump_wait(page, random.uniform(1.5, 3))
        except Exception:
            pass
        if "/search" not in (page.url or "") or "google." not in (page.url or ""):
            if serp_url and "/search" in serp_url:
                self._ch_say("Không lùi được về trang kết quả — mở lại đúng trang kết quả vừa xem.")
                self._ch_goto(page, serp_url)
                self.random_sleep(2, 4)
        self.smooth_scroll(page, -3000)
        self.random_sleep(1, 2.5)

        # 3) tab "Video" -> bấm 1 kết quả YouTube
        tabs = page.locator("a[href*='udm=vids'], a[href*='udm=7'], a[href*='tbm=vid']")
        tab = None
        for i in range(min(tabs.count(), 6)):
            try:
                if tabs.nth(i).is_visible():
                    tab = tabs.nth(i)
                    break
            except Exception:
                continue
        if tab is None:
            self._ch_say("Không thấy tab Video trên Google — bỏ qua tín hiệu chéo, sang YouTube tìm trực tiếp.")
            return False
        try:
            self._ch_hover_click(page, tab, timeout=8000)
        except Exception as e:
            print(f"      + [Google] click() tab Video: {str(e)[:80]} (bỏ qua, poll URL)")
        if not self._ch_wait_url(page, lambda u: "udm=vids" in u or "udm=7" in u or "tbm=vid" in u, seconds=10):
            self._ch_say("Bấm tab Video nhưng trang không đổi — bỏ qua tín hiệu chéo.")
            return False
        self.random_sleep(2, 4)
        for _ in range(random.randint(1, 3)):
            self.smooth_scroll(page, random.randint(250, 550))
            self.random_sleep(2, 4)
        vids = self._ch_google_results(page, want_youtube=True)
        if not vids:
            self._ch_say("Tab Video không có kết quả YouTube — bỏ qua tín hiệu chéo.")
            return False
        target = random.choice(vids[:4])
        try:
            self._ch_hover_click(page, target, timeout=10000)
        except Exception as e:
            print(f"      + [Google] click() trả lời: {str(e)[:80]} (bỏ qua, poll URL)")
        landed = self._ch_wait_url(page, lambda u: "youtube.com/watch" in u)
        self._ch_say("Đã sang YouTube từ tab Video của Google (tín hiệu chéo)." if landed
                     else f"Bấm kết quả nhưng chưa tới YouTube (URL: {page.url[:70]}).")
        return landed

    # ------------------------------------------------------------------ BƯỚC 2: tìm kiếm + lọc + VPH
    def _ch_apply_filter(self, page, names, group_idx, item_idx):
        """Mở 'Bộ lọc' và bấm 1 mục. Khớp theo CHỮ (vi/en) trước; không thấy thì theo VỊ TRÍ (chỉ khi đủ 5 nhóm)."""
        btn = page.locator("#filter-button button").first
        if not (btn.count() and btn.is_visible()):
            return False
        self._ch_hover_click(page, btn, timeout=5000)
        self._pump_wait(page, random.uniform(1.5, 2.5))
        target = None
        items = page.locator("ytd-search-filter-renderer")
        for i in range(min(items.count(), 45)):
            it = items.nth(i)
            try:
                if (it.inner_text(timeout=800) or "").strip() in names:
                    target = it
                    break
            except Exception:
                continue
        if target is None:
            groups = page.locator("ytd-search-filter-group-renderer")
            if groups.count() == 5:
                g = groups.nth(group_idx).locator("ytd-search-filter-renderer")
                n = g.count()
                if n:
                    target = g.nth(item_idx if item_idx >= 0 else n - 1)
        if target is None:
            page.keyboard.press("Escape")
            return False
        try:
            if "selected" in (target.get_attribute("class") or ""):
                page.keyboard.press("Escape")
                return True
            self.random_sleep(0.6, 1.8)
            self._ch_hover_click(page, target.locator("a#endpoint").first, timeout=5000)
            self._pump_wait(page, random.uniform(4, 6))
            return True
        except Exception:
            try:
                page.keyboard.press("Escape")
            except Exception:
                pass
            return False

    def _ch_search(self, page, keyword, use_filter):
        """Gõ từ khóa vào ô tìm kiếm YouTube (như người), tùy chọn lọc 'Tuần này/Hôm nay' + 'Mức độ phổ biến'."""
        if "youtube.com" not in (page.url or ""):
            self._ch_goto(page, "https://www.youtube.com")
            self.random_sleep(2, 4)
        box = page.locator("input[name='search_query']").first
        box.wait_for(state="visible", timeout=15000)
        try:
            if (box.input_value(timeout=2000) or "").strip():
                box.click()
                self.random_sleep(0.3, 0.8)
                page.keyboard.press("Control+A")
                self.random_sleep(0.2, 0.5)
                page.keyboard.press("Backspace")
                self.random_sleep(0.4, 1.0)
        except Exception:
            pass
        self.human_type(box, keyword)
        self.random_sleep(0.8, 1.8)
        page.keyboard.press("Enter")
        try:
            page.wait_for_load_state("domcontentloaded", timeout=30000)
        except Exception:
            pass
        self._pump_wait(page, random.uniform(3, 5))
        try:
            if self.db and self.profile_id:
                self.db.log_keyword_used(self.profile_id, keyword)
        except Exception:
            pass
        filtered = False
        if use_filter and self._ch_guard(page):
            today = random.random() < 0.30
            ok1 = self._ch_apply_filter(page, self.CH_F_TODAY if today else self.CH_F_WEEK, 2, 0 if today else 1)
            ok2 = self._ch_apply_filter(page, self.CH_F_POPULAR, 4, -1) if ok1 else False
            filtered = ok1 and ok2
            self._ch_say(f"Bộ lọc: {'Hôm nay' if today else 'Tuần này'} {'✓' if ok1 else '✗'} · "
                         f"Mức độ phổ biến {'✓' if ok2 else '✗'}.")
        end = time.time() + random.randint(8, 16)       # lướt kết quả "từ tốn"
        while time.time() < end and not self.stop_requested:
            self.smooth_scroll(page, random.randint(250, 600))
            self.random_sleep(2, 4)
        if random.random() < 0.6:
            self.smooth_scroll(page, -random.randint(400, 900))
            self.random_sleep(1.5, 3)
        return filtered

    def _ch_read_results(self, page, niche):
        """Đọc kết quả tìm kiếm -> list dict (title, chan, views, age_h, vph, dur_s, score...)."""
        rows = self._ch_js(page, _JS_RESULTS) or []
        out = []
        for r in rows:
            title = (r.get("title") or "").strip()
            if not title or "/watch" not in (r.get("href") or "") or (r.get("h") or 0) < 20:
                continue
            meta = r.get("meta") or []
            views = age = None
            for m in meta:
                a = parse_age_hours(m)
                if a is not None and age is None:
                    age = a
                elif views is None:
                    views = parse_count(m)
            score, why = niche_score(niche, title, r.get("chan", ""), r.get("chanHref", ""))
            out.append({"idx": r["idx"], "title": title, "chan": r.get("chan", ""), "views": views,
                        "age_h": age, "vph": views_per_hour(views, age), "dur_s": parse_duration(r.get("dur")),
                        "score": score, "why": why})
        return out

    def _ch_choose_result(self, rows, deep, seen_titles):
        """Chọn video: đúng niche trước, rồi ưu tiên VPH cao. Video xem sâu ưu tiên dài cỡ video đối thủ
        (khoảng `fit` của kế hoạch phiên; chưa có kế hoạch thì 6–25 phút)."""
        rows = [r for r in rows if r["title"] not in seen_titles and (r["dur_s"] == 0 or r["dur_s"] >= LONG_MIN_S)]
        if not rows:
            return None, "không còn kết quả mới"
        pool = [r for r in rows if r["score"] >= NICHE_SCORE_MIN]
        note = "đúng niche"
        if not pool:
            pool, note = rows[:6], "chưa chấm được niche — lấy theo thứ hạng tìm kiếm"
        if deep:
            lo, hi = (getattr(self, "_ch_sess", None) or {}).get("fit") or (360, 1500)
            fit = [r for r in pool if lo <= r["dur_s"] <= hi]
            if fit:
                pool = fit
        return pick_by_vph(pool, k=4), note

    # ------------------------------------------------------------------ trình phát: quảng cáo, âm lượng, tua
    def _ch_handle_ads(self, page, max_s=90):
        """Quảng cáo: bấm Skip ngay khi nút hiện; ~10% để 1 quảng cáo ngắn < 15s chạy hết (SOP)."""
        try:
            if page.locator(".ad-showing").count() == 0:
                return
        except Exception:
            return
        let_run = random.random() < self.CH_AD_LET_RUN_P
        told = False
        end = time.time() + max_s
        while time.time() < end and not self.stop_requested:
            try:
                if page.locator(".ad-showing").count() == 0:
                    break
            except Exception:
                break
            if let_run:
                st = self._ch_js(page, _JS_PLAYER) or {}
                dur = float(st.get("dur") or 0)
                if 0 < dur <= 15:
                    if not told:
                        self._ch_say(f"Quảng cáo ngắn {dur:.0f}s — để chạy hết (kiểu người thật, ~10% số lần).")
                        told = True
                else:
                    let_run = False
            if not let_run:
                self.random_sleep(0.3, 1.2)        # phản xạ người: không bấm ngay mili-giây đầu
                self._check_and_skip_ad(page)
            time.sleep(1.5)

    def _ch_ensure_audio(self, page):
        """Không tắt tiếng, âm lượng > 30% (SOP). Chỉnh bằng phím (m / mũi tên khi trình phát đang được chọn)."""
        st = self._ch_js(page, _JS_PLAYER)
        if not st:
            return
        try:
            if st.get("muted"):
                page.keyboard.press("m")
                self._ch_say("Trình phát đang tắt tiếng — bật tiếng lại.")
                self.random_sleep(0.4, 1.0)
                st = self._ch_js(page, _JS_PLAYER) or st
            vol = float(st.get("vol") or 0)
            if vol < 0.30:
                want = random.uniform(0.40, 0.65)
                page.locator("#movie_player").first.focus(timeout=2000)
                for _ in range(int((want - vol) / 0.05) + 1):
                    page.keyboard.press("ArrowUp")
                    time.sleep(random.uniform(0.12, 0.35))
                st2 = self._ch_js(page, _JS_PLAYER) or {}
                self._ch_say(f"Âm lượng {vol * 100:.0f}% < 30% — tăng lên {float(st2.get('vol') or 0) * 100:.0f}%.")
        except Exception:
            pass

    def _ch_fidget(self, page):
        """Thỉnh thoảng tua lại/tua đi 10s hoặc chỉnh âm lượng lên xuống (không mute, không tụt dưới 30%)."""
        try:
            if page.locator(".ad-showing").count():
                return                      # đang quảng cáo: phím tua/âm lượng không ăn (đo thật 23/11)
            r = random.random()
            if r < 0.35:
                page.keyboard.press("j")
                self._ch_say("Tua lại 10s.")
            elif r < 0.55:
                st = self._ch_js(page, _JS_PLAYER) or {}
                if float(st.get("dur") or 0) - float(st.get("cur") or 0) > 60:
                    page.keyboard.press("l")
                    self._ch_say("Tua đi 10s.")
            else:
                st = self._ch_js(page, _JS_PLAYER) or {}
                vol = float(st.get("vol") or 0.5)
                key = "ArrowDown" if (vol > 0.45 and random.random() < 0.5) else "ArrowUp"
                page.locator("#movie_player").first.focus(timeout=2000)
                for _ in range(random.randint(1, 2)):
                    page.keyboard.press(key)
                    time.sleep(random.uniform(0.15, 0.4))
                st2 = self._ch_js(page, _JS_PLAYER) or {}
                vol2 = float(st2.get("vol") or 0)
                if abs(vol2 - vol) >= 0.01:
                    self._ch_say(f"Chỉnh âm lượng {vol * 100:.0f}% -> {vol2 * 100:.0f}%.")
        except Exception:
            pass

    def _ch_ensure_playing(self, page, quiet=False):
        """Video đang dừng (trình duyệt chặn tự phát, hoặc hộp 'Bạn vẫn đang xem?') -> bấm phím k cho chạy tiếp.
        Không làm gì khi đang quảng cáo. Trả True nếu vừa phải bấm phát."""
        try:
            if page.locator(".ad-showing").count():
                return False
            st = self._ch_js(page, _JS_PLAYER) or {}
            if st.get("paused") and float(st.get("dur") or 0) - float(st.get("cur") or 0) > 3:
                page.locator("#movie_player").first.focus(timeout=2000)
                page.keyboard.press("k")
                if not quiet:
                    self._ch_say("Video đang dừng — bấm phát tiếp.")
                return True
        except Exception:
            pass
        return False

    # ------------------------------------------------------------------ tương tác thưa: like / sub / đọc bình luận
    def _ch_like_video(self, page):
        try:
            btns = page.locator("like-button-view-model button")
            for i in range(min(btns.count(), 4)):
                b = btns.nth(i)
                if not b.is_visible():
                    continue
                if (b.get_attribute("aria-pressed") or "").lower() == "true":
                    self._ch_say("Video này đã like từ trước — không bấm lại.")
                    return False
                self._smooth_scroll_to_element(page, b)
                self.random_sleep(0.8, 2.0)
                self.human_click(page, b)
                self.random_sleep(1.2, 2.5)
                pressed = (b.get_attribute("aria-pressed") or "").lower() == "true"
                self._ch_say("Đã bấm Like video." + ("" if pressed else " (nút chưa đổi trạng thái — có thể chưa ăn)"))
                self._log_activity(page, "like_video", platform="YouTube",
                                   title=(page.title() or "").replace(" - YouTube", "").strip(),
                                   status="ok" if pressed else "unconfirmed")
                return pressed
        except Exception as e:
            self._ch_say(f"Không like được video ({str(e)[:80]}).")
        return False

    def _ch_subscribe(self, page):
        try:
            if page.locator("ytd-subscribe-button-renderer[subscribed]").count():
                return False
            btn = page.locator("ytd-subscribe-button-renderer button, yt-subscribe-button-view-model button").first
            if not (btn.count() and btn.is_visible()):
                return False
            label = (btn.inner_text(timeout=1500) or "").strip()
            if not label or len(label) > 20:          # nút chuông / nút khác — không phải "Subscribe"
                return False
            self._smooth_scroll_to_element(page, btn)
            self.random_sleep(1.0, 2.5)
            self.human_click(page, btn)
            self.random_sleep(2, 4)
            self._ch_say("Đã bấm Đăng ký kênh (thưa: tối đa 1/ngày, 2/tuần).")
            try:
                if self.db and self.profile_id:
                    self.db.log_sub_success(self.profile_id)
            except Exception:
                pass
            self._log_activity(page, "subscribe", platform="YouTube",
                               title=(page.title() or "").replace(" - YouTube", "").strip())
            return True
        except Exception as e:
            self._ch_say(f"Không đăng ký được kênh ({str(e)[:80]}).")
            return False

    def _ch_read_comments(self, page, may_like):
        """Cuộn xuống đọc lướt bình luận rồi cuộn về trình phát. may_like=True: like 1 bình luận của người khác."""
        liked = False
        try:
            threads = page.locator("ytd-comment-thread-renderer")
            for _ in range(10):
                if threads.count() > 0 or self.stop_requested:
                    break
                # khung bình luận đã vào màn hình -> đứng chờ nó tải, KHÔNG cuộn lố xuống dưới (đo thật 23/11:
                # video 0 bình luận làm bản cũ cuộn tuột 6000px)
                top = self._ch_js(page, "() => { const c = document.querySelector('ytd-comments#comments'); "
                                        "return c ? c.getBoundingClientRect().top : null; }")
                if isinstance(top, (int, float)) and top < 500:
                    self._pump_wait(page, random.uniform(2.5, 4))
                    break
                self.smooth_scroll(page, random.randint(350, 600))
                self.random_sleep(1.2, 2.5)
            n = threads.count()
            if n == 0:
                cnt = self._ch_js(page, "() => { const m = document.querySelector('ytd-comments-header-renderer #count'); "
                                        "return m ? (m.innerText || '').trim() : ''; }") or ""
                if parse_count(cnt) == 0:
                    self._ch_say("Video này không có bình luận nào — bỏ qua phần đọc bình luận.")
                else:
                    self._ch_say("Video này chưa tải được phần bình luận — bỏ qua.")
            else:
                self._ch_say("Cuộn xuống đọc lướt bình luận...")
                end = time.time() + random.uniform(12, 35)
                while time.time() < end and not self.stop_requested:
                    self.smooth_scroll(page, random.randint(150, 420))
                    self.random_sleep(2.5, 6)
                if may_like:
                    vis = []
                    for i in range(min(threads.count(), 12)):
                        b = threads.nth(i).locator("#like-button button").first
                        try:
                            if b.count() and b.is_visible() and (b.get_attribute("aria-pressed") or "") == "false":
                                box = self._safe_bbox(b)
                                if box and 80 < box["y"] < 900:
                                    vis.append(b)
                        except Exception:
                            continue
                    if vis:
                        b = random.choice(vis)
                        self.random_sleep(1.0, 3.0)
                        self.human_click(page, b)
                        self.random_sleep(1.0, 2.0)
                        liked = (b.get_attribute("aria-pressed") or "").lower() == "true"
                        self._ch_say("Đã like 1 bình luận của người khác." + ("" if liked else " (chưa xác nhận được)"))
                        self._log_activity(page, "like_comment", platform="YouTube",
                                           title=(page.title() or "").replace(" - YouTube", "").strip(),
                                           status="ok" if liked else "unconfirmed")
            # cuộn về đầu trang (trình phát)
            for _ in range(14):
                y = self._ch_js(page, "() => window.scrollY") or 0
                if y <= 40 or self.stop_requested:
                    break
                self.smooth_scroll(page, -random.randint(600, 1100))
                self.random_sleep(0.5, 1.2)
        except Exception as e:
            self._ch_say(f"Bỏ qua đọc bình luận ({str(e)[:80]}).")
        return liked

    # ------------------------------------------------------------------ BƯỚC 3: xem 1 video
    def _ch_watch(self, page, role, in_niche=True):
        """Xem video đang mở. role: 'deep' (70–90%) | 'mid' (50–60%) | 'light' (vài phút).
        Trả dict {title, watched_s, ratio} hoặc None nếu không xem được."""
        t0 = time.time()
        logged = False
        try:
            try:
                page.wait_for_load_state("domcontentloaded", timeout=30000)
            except Exception:
                pass
            self.random_sleep(3, 6)
            self._ch_handle_ads(page)
            self.random_sleep(1, 2.5)
            self._ch_ensure_playing(page)
            self._ch_ensure_audio(page)

            total = 0
            try:
                total = self._parse_time(page.locator(".ytp-time-duration").first.inner_text(timeout=5000))
            except Exception:
                total = 0
            if total <= 0:
                st = self._ch_js(page, _JS_PLAYER) or {}
                d = float(st.get("dur") or 0)
                total = int(d) if 0 < d < 86400 else random.randint(240, 420)

            sess = getattr(self, "_ch_sess", None) or {}
            if role == "deep":
                pct = random.uniform(*self.CH_DEEP_PCT)
                cap = int(sess["deep_cap_s"] * random.uniform(0.9, 1.0)) if sess else random.randint(*self.CH_DEEP_CAP_S)
            elif role == "mid":
                pct = random.uniform(*self.CH_MID_PCT)
                cap = int(sess["mid_cap_s"] * random.uniform(0.85, 1.0)) if sess else random.randint(*self.CH_MID_CAP_S)
            else:
                pct, cap = random.uniform(0.40, 0.60), random.randint(*self.CH_LIGHT_S)
            want = int(total * pct)
            capped = want > cap
            if capped:
                want = cap
            left = self._ch_left()
            if left < want + 30:
                want = max(30, int(left - 20))
            label = {"deep": "XEM SÂU", "mid": "xem trung bình", "light": "xem thêm vài phút"}[role]
            self._ch_say(f"{label}: video dài {total}s, sẽ xem ~{want}s "
                         f"({want * 100 // max(total, 1)}%{' — chạm trần, bỏ dở như người thật' if capped else ''}).")

            plan = getattr(self, "_ch_plan", {}) or {}
            do_comments = role != "light" and want > 150 and random.random() < self.CH_READ_COMMENTS_P
            # like bình luận cần phải cuộn tới bình luận -> nếu phiên này "được" like bình luận thì chắc chắn đọc
            if plan.get("like_comment") and in_niche and role != "light" and want > 150:
                do_comments = True
            comments_at = random.uniform(0.35, 0.75) * want if do_comments else None

            end_time = time.time() + want
            watched, beat = 0.0, 0.0
            while time.time() < end_time:
                if self.stop_requested:
                    print("      + [Stop] Nhận yêu cầu dừng - kết thúc sớm video đang xem.")
                    break
                if self._browser_gone(page):
                    raise RuntimeError("Trình duyệt/tab của phiên đã bị đóng giữa chừng — kết thúc phiên sớm.")
                self._ch_handle_ads(page, max_s=60)
                remaining = end_time - time.time()
                if remaining <= 0:
                    break
                nap = min(random.uniform(4, 8), remaining)
                time.sleep(nap)
                watched += nap
                if watched >= beat:
                    print(f"         ...đang xem video YouTube ({watched:.0f}/{want}s)")
                    beat = watched + random.uniform(20, 30)
                    self._ch_ensure_playing(page)
                if comments_at is not None and watched >= comments_at:
                    comments_at = None
                    c0 = time.time()
                    may_like = bool(plan.get("like_comment")) and in_niche
                    if self._ch_read_comments(page, may_like):
                        plan["like_comment"] = False
                    watched += time.time() - c0
                elif random.random() < 0.07:
                    self._ch_fidget(page)

            ratio = watched / max(total, 1)
            title = ""
            try:
                title = (page.title() or "").replace(" - YouTube", "").strip()
            except Exception:
                pass
            # Like video / Sub: CHỈ ở video xem sâu, đúng niche, đã xem >= 70% (hoặc chạm trần xem sâu)
            if role == "deep" and in_niche and not self.stop_requested and (ratio >= 0.70 or capped):
                if plan.get("like_video"):
                    plan["like_video"] = False
                    self._ch_like_video(page)
                if plan.get("subscribe"):
                    plan["subscribe"] = False
                    self._ch_subscribe(page)
            self._log_activity(page, "watch_video", platform="YouTube", url=page.url, title=title,
                               status="ok", duration_s=round(time.time() - t0, 1))
            logged = True
            return {"title": title, "watched_s": watched, "ratio": ratio}
        except RuntimeError:
            raise
        except Exception as e:
            self._ch_say(f"Lỗi khi xem video: {str(e)[:120]}")
            if not logged:
                try:
                    self._log_activity(page, "watch_video", platform="YouTube", url=page.url, title="",
                                       status="error", duration_s=round(time.time() - t0, 1), error=str(e))
                except Exception:
                    pass
            return None

    def _ch_open_search_result(self, page, row):
        loc = page.locator("ytd-video-renderer").nth(row["idx"]).locator("a#video-title").first
        self._smooth_scroll_to_element(page, loc)
        self.random_sleep(2, 5)           # đọc tiêu đề trước khi bấm
        self.human_click(page, loc)
        self.restore_mouse_position(page)
        if self._ch_wait_url(page, lambda u: "youtube.com/watch" in u, seconds=10):
            return True
        try:                               # bấm toạ độ trượt -> bấm chuẩn 1 lần
            loc.click(timeout=5000)
        except Exception:
            pass
        return self._ch_wait_url(page, lambda u: "youtube.com/watch" in u, seconds=8)

    # ------------------------------------------------------------------ Shorts (tùy phiên)
    def _ch_shorts(self, page):
        """Từ trang kết quả đang mở: bấm chip Shorts -> xem 2–3 Shorts cùng chủ đề."""
        try:
            chip = page.locator("yt-chip-cloud-chip-renderer button[role=tab]", has_text="Shorts").first
            if not (chip.count() and chip.is_visible()):
                self._ch_say("Trang kết quả không có chip Shorts — bỏ qua Shorts.")
                return 0
            self.smooth_scroll(page, -3000)
            self.random_sleep(1, 2)
            self._ch_hover_click(page, chip, timeout=5000)
            self._pump_wait(page, random.uniform(4, 6))
            links = [a for a in page.locator("a[href^='/shorts/'].reel-item-endpoint").all()[:8]
                     if self._safe_bbox(a)]
            if not links:
                self._ch_say("Không thấy Shorts nào trong kết quả — bỏ qua.")
                return 0
            target = random.choice(links[:4])
            self._smooth_scroll_to_element(page, target)
            self.random_sleep(1.5, 3.5)
            self.human_click(page, target)
            if not self._ch_wait_url(page, lambda u: "/shorts/" in u, seconds=10):
                try:
                    target.click(timeout=5000)
                except Exception:
                    pass
                if not self._ch_wait_url(page, lambda u: "/shorts/" in u, seconds=8):
                    return 0
            n = random.randint(2, 3)
            self._ch_say(f"Lướt {n} video Shorts cùng chủ đề.")
            done = 0
            for i in range(n):
                if not self._ch_guard(page) or self._ch_left() < 120:
                    break
                t0 = time.time()
                self._pump_wait(page, random.uniform(2, 3))
                st = self._ch_js(page, _JS_PLAYER) or {}
                dur = float(st.get("dur") or 0)
                stay = min(dur if 0 < dur < 180 else 40, random.uniform(15, 45))
                # Short đầu đến từ kết quả tìm kiếm (đúng niche); các short kế do YouTube tự đưa -> chấm lại theo
                # tiêu đề, lạc niche thì lướt qua nhanh 2-4s như người không hứng thú (đo thật 23/11: short thứ 2 lạc đề)
                s_title = ""
                try:
                    s_title = (page.title() or "").replace(" - YouTube", "").strip()
                except Exception:
                    pass
                niche = getattr(self, "_ch_niche", None) or {}
                if i > 0 and niche.get("tokens") and niche_score(niche, s_title)[0] < NICHE_SCORE_MIN:
                    stay = random.uniform(2, 4)
                    self._ch_say(f"Short lạc niche ('{s_title[:50]}') — lướt qua nhanh.")
                end = time.time() + stay
                while time.time() < end and not self.stop_requested:
                    time.sleep(1.0)
                done += 1
                self._log_activity(page, "watch_shorts", platform="YouTube", url=page.url,
                                   title=(page.title() or "").replace(" - YouTube", "").strip(),
                                   duration_s=round(time.time() - t0, 1))
                if i < n - 1:
                    nxt = page.locator("#navigation-button-down button").first
                    if nxt.count() and nxt.is_visible():
                        self.human_click(page, nxt)
                    else:
                        page.keyboard.press("ArrowDown")
            return done
        except RuntimeError:
            raise
        except Exception as e:
            self._ch_say(f"Bỏ qua Shorts ({str(e)[:80]}).")
            return 0

    # ------------------------------------------------------------------ BƯỚC 4: trang chủ — chỉ bấm video đúng niche
    def _ch_ai_pick(self, niche, tiles):
        """Nhờ AI (nếu có) chọn các video đúng niche trong danh sách tiêu đề. Lỗi/không có AI -> None."""
        if not self.brain or not tiles:
            return None
        try:
            lines = "\n".join(f"{i + 1}. {t['title'][:110]} — {t.get('chan') or 'unknown channel'}"
                              for i, t in enumerate(tiles))
            prompt = (
                "You help a YouTube viewer who ONLY watches one niche.\n"
                f"Niche: {niche.get('name') or '(unnamed)'}. {niche.get('description') or ''}\n"
                f"Typical search keywords: {'; '.join((niche.get('keywords') or [])[:12])}\n"
                f"Channels in this niche: {'; '.join((niche.get('channels') or [])[:10]) or 'n/a'}\n"
                + (f"Niche vocabulary (from competitor channels): "
                   f"{', '.join(sorted(niche.get('learned_tokens') or ())[:30])}\n"
                   if niche.get("learned_tokens") else "")
                + (f"What this audience likes (from comments):\n{niche['audience'][:700]}\n"
                   if niche.get("audience") else "")
                + f"\nVideos on the page:\n{lines}\n\n"
                "Reply ONLY with the numbers of the videos that clearly belong to this niche, "
                "comma-separated (e.g. 2, 5). If none belong, reply: none."
            )
            return parse_ai_numbers(self.brain.ask_text(prompt), len(tiles))
        except Exception as e:
            self._ch_say(f"AI không chấm được danh sách ({str(e)[:80]}) — dùng bộ chấm điểm tại chỗ.")
            return None

    def _ch_score_tiles(self, niche, tiles, use_ai=True):
        """Gắn score/why cho từng thẻ; trả list thẻ đúng niche (đã sắp theo điểm)."""
        for t in tiles:
            t["score"], t["why"] = niche_score(niche, t.get("title", ""), t.get("chan", ""), t.get("chanHref", ""))
        picked = self._ch_ai_pick(niche, tiles) if use_ai else None
        if picked is not None:
            for i, t in enumerate(tiles):
                if i in picked:
                    t["score"] = max(t["score"], NICHE_SCORE_MIN + 2)
                    t["why"] = (t["why"] + "; " if t["why"] else "") + "AI chọn"
                elif "kênh đối thủ" not in t["why"]:      # AI loại, và không phải kênh đối thủ
                    t["score"] = min(t["score"], NICHE_SCORE_MIN - 1)
        good = [t for t in tiles if t["score"] >= NICHE_SCORE_MIN]
        good.sort(key=lambda t: t["score"], reverse=True)
        return good

    def _ch_home_training(self, page, niche, seen_titles):
        """SOP bước 4: bấm logo về trang chủ, cuộn, bấm 1–2 video ĐÚNG NICHE xem thêm vài phút."""
        self._ch_say("Bước 4 — Luyện trang chủ: về Home, chỉ bấm video đúng niche.")
        watched = 0
        want = random.randint(1, 2)
        for round_i in range(want):
            if not self._ch_guard(page) or self._ch_left() < 150:
                break
            try:
                logo = None
                for a in page.locator("ytd-masthead a#logo").all()[:3]:
                    if self._safe_bbox(a):
                        logo = a
                        break
                if logo is not None:
                    self.human_click(page, logo)
                    self._pump_wait(page, random.uniform(3, 5))
                url = (page.url or "").split("?")[0].rstrip("/")
                if not url.endswith("youtube.com"):
                    print("      + [YouTube] Đích là youtube.com — vào thẳng (site đích, cố ý).")
                    self._ch_goto(page, "https://www.youtube.com")
                    self._pump_wait(page, random.uniform(3, 5))
                for _ in range(random.randint(2, 4)):
                    self.smooth_scroll(page, random.randint(400, 750))
                    self.random_sleep(2, 4)
                tiles = [t for t in (self._ch_js(page, _JS_TILES, None) or [])
                         if t.get("title") and t["title"] not in seen_titles]
                if not tiles:
                    self._ch_say("Trang chủ chưa có video đề xuất (acc mới / chưa có lịch sử xem) — "
                                 "thuật toán chưa nhả đề xuất, bỏ qua bước này ở phiên này.")
                    break
                good = self._ch_score_tiles(niche, tiles)
                self._ch_say(f"Trang chủ có {len(tiles)} video, {len(good)} video đúng niche.")
                if not good:
                    self._ch_say("Không bấm video lạc niche (giữ lịch sử xem sạch). Cuộn xem thêm rồi thôi.")
                    for _ in range(random.randint(1, 3)):
                        self.smooth_scroll(page, random.randint(400, 750))
                        self.random_sleep(2, 4)
                    break
                tile = random.choice(good[:3])
                self._ch_say(f"Chọn: '{tile['title'][:70]}' ({tile['why'] or 'đúng niche'}).")
                loc = None
                for a in page.locator(f"a[href*='v={tile['vid']}']").all()[:4]:
                    if self._safe_bbox(a):
                        loc = a
                        break
                if loc is None:
                    continue
                self._smooth_scroll_to_element(page, loc)
                self.random_sleep(1.5, 4)
                self.human_click(page, loc)
                self.restore_mouse_position(page)
                if not self._ch_wait_url(page, lambda u: "youtube.com/watch" in u, seconds=10):
                    try:
                        loc.click(timeout=5000)
                    except Exception:
                        pass
                    if not self._ch_wait_url(page, lambda u: "youtube.com/watch" in u, seconds=8):
                        continue
                seen_titles.add(tile["title"])
                if self._ch_watch(page, "light", in_niche=True):
                    watched += 1
                self._ch_rest(page, 6, 18)
            except RuntimeError:
                raise
            except Exception as e:
                self._ch_say(f"Lỗi ở bước trang chủ ({str(e)[:100]}) — bỏ qua.")
                break
        self._log_activity(page, "channel_home_training", platform="YouTube",
                           title=f"{watched} video đúng niche")
        return watched

    # ------------------------------------------------------------------ chọn từ khóa cho phiên
    def _ch_keyword_order(self, niche):
        """Từ khóa chưa dùng / dùng lâu nhất lên trước (đọc keyword_usage), trong nhóm thì xáo ngẫu nhiên."""
        kws = list(niche.get("keywords") or [])
        if not kws:
            # Chưa cấu hình niche -> lấy tạm từ khóa của phiên để chế độ vẫn chạy được
            theme = self.session_theme or {}
            for c in (self.keyword_cluster or []):
                kws.append(c.get("youtube_query") or c.get("google_query") or "")
            kws += [theme.get("youtube_query", ""), theme.get("google_query", "")]
            kws = [k for k in dict.fromkeys(k.strip() for k in kws) if k]
        last = {}
        try:
            if self.db and self.profile_id:
                last = self.db.get_keyword_last_used(self.profile_id, kws) or {}
        except Exception:
            last = {}
        random.shuffle(kws)
        kws.sort(key=lambda k: last.get(k.strip().lower(), ""))
        return kws

    # ------------------------------------------------------------------ PHIÊN NGÂM KÊNH
    def _ch_replan(self, typical_s, n_long, t0, source):
        """Lập (lại) nhịp phiên theo độ dài video điển hình. Trần do caller ghim thì giữ nguyên, chỉ chỉnh số video +
        trần xem cho vừa. -> số video dài của phiên."""
        limit = float(self.session_deadline_s) if self._ch_fixed_deadline else self._ch_max_s
        sess = plan_session(typical_s, n_long, limit)
        self._ch_sess = sess
        if not self._ch_fixed_deadline:
            self.session_deadline_s = float(sess["session_s"])
            self._session_end_ts = t0 + float(sess["session_s"])
        self._ch_say(f"Video đối thủ dài ~{sess['typical_s'] / 60:.0f} phút ({source}) → {sess['n_long']} video dài, "
                     f"xem sâu tối đa {sess['deep_cap_s'] // 60} phút, các video sau tối đa {sess['mid_cap_s'] // 60} phút"
                     + (" — đã hạ mức xem cho vừa trần phiên." if sess["squeezed"] else "."))
        print(f"      [Giới hạn] Phiên ngâm kênh chạy tối đa {int(self.session_deadline_s // 60)} phút "
              f"({'caller' if self._ch_fixed_deadline else 'tính theo độ dài video đối thủ'}).")
        return sess["n_long"]

    def run_channel_session(self):
        """Một phiên ngâm kênh theo niche (5 bước của SOP). Gọi từ run_random_session khi phase == 'channel'."""
        page = self.context.new_page()
        self.enable_virtual_cursor(page)
        niche = normalize_niche(getattr(self, "niche", None))
        self._ch_niche = niche
        self.actions_done = 0
        print(f"[*] Bắt đầu phiên NGÂM KÊNH theo niche: "
              f"{niche['name'] or '(chưa đặt tên)'} — {len(niche['keywords'])} từ khóa, "
              f"{len(niche['channels'])} kênh đối thủ.")
        if niche["learned_tokens"] or niche["audience"]:
            self._ch_say(f"Niche đã học từ kênh đối thủ: {len(niche['learned_tokens'])} từ vựng đặc trưng"
                         + (" + ghi chú người xem (đưa cho AI khi chấm trang chủ)." if niche["audience"] else "."))
        if not niche["keywords"]:
            self._ch_say("CHƯA cấu hình niche cho profile này (nút '🎯 Niche ngâm kênh') — "
                         "tạm dùng từ khóa của phiên. Nên nhập 15–20 từ khóa đuôi dài + 5–10 kênh đối thủ.")
        keywords = self._ch_keyword_order(niche)
        if not keywords:
            self._ch_say("Không có từ khóa nào để ngâm — kết thúc phiên.")
            page.close()
            return

        # v1.9.5: nhịp phiên theo ĐỘ DÀI VIDEO ĐỐI THỦ. Biết sẵn (user nhập / đã học qua API) thì lập kế hoạch ngay;
        # chưa biết thì tạm theo SOP 45–60 phút rồi đo độ dài video ở lần tìm đầu tiên (_ch_replan).
        self._ch_sess = None
        self._ch_fixed_deadline = bool(self.session_deadline_s and self.session_deadline_s > 0)
        self._ch_max_s = float(getattr(self, "channel_max_s", 0) or 0)
        n_long = random.randint(*self.CH_LONG_VIDEOS)
        t0 = time.time()
        if self._ch_fixed_deadline:
            deadline_s, src = float(self.session_deadline_s), "caller"
        else:
            deadline_s, src = random.uniform(*self.CH_SESSION_MIN) * 60, "SOP 45–60 phút, sẽ đo lại theo độ dài video"
            if self._ch_max_s > 0:
                deadline_s = min(deadline_s, self._ch_max_s)
            self.session_deadline_s = deadline_s
        self._session_end_ts = t0 + deadline_s
        if niche["typical_len_s"] > 0:
            n_long = self._ch_replan(niche["typical_len_s"], n_long, t0, niche["typical_src"])
        else:
            print(f"      [Giới hạn] Phiên ngâm kênh chạy tối đa {int(deadline_s // 60)} phút ({src}).")
        print("      [Phase] Chế độ ngâm: CHANNEL (5 bước: đồng bộ tín hiệu → gieo từ khóa → xem sâu → luyện trang chủ → đóng phiên).")

        seen = set()
        kw_i = 0
        try:
            # ===== BƯỚC 1: đồng bộ tín hiệu =====
            print("\n[*] Bước 1/5 — Đồng bộ tín hiệu (Location/Language + Google → YouTube):")
            print("      + [YouTube] Đích là youtube.com — vào thẳng (site đích, cố ý).")
            self._ch_goto(page, "https://www.youtube.com")
            self._pump_wait(page, random.uniform(4, 6))
            self._close_popups(page)
            cfg = self._ch_sync_locale(page) if niche["sync_locale"] else self._ch_yt_cfg(page)
            if not niche["sync_locale"]:
                self._ch_say("Niche này tắt đồng bộ vùng/ngôn ngữ — giữ nguyên cấu hình YouTube.")
            self._ch_plan = self._ch_roll_engagement(bool(cfg.get("LOGGED_IN")))
            self._log_activity(page, "channel_sync_locale", platform="YouTube",
                               title=f"GL={cfg.get('GL')} HL={cfg.get('HL')} login={bool(cfg.get('LOGGED_IN'))}")
            self.actions_done += 1
            self._ch_rest(page, 3, 8)

            landed = False
            if self._ch_guard(page):
                try:
                    landed = self._ch_cross_signal(page, keywords[kw_i % len(keywords)])
                    kw_i += 1
                except RuntimeError:
                    raise
                except Exception as e:
                    self._ch_say(f"Bước Google lỗi ({str(e)[:100]}) — sang YouTube tìm trực tiếp.")
                self.actions_done += 1
            if landed and self._ch_guard(page):
                r = self._ch_watch(page, "light", in_niche=True)
                if r and r.get("title"):
                    seen.add(r["title"])
                self._ch_rest(page, 8, 20)

            # ===== BƯỚC 2 + 3: gieo từ khóa, lọc VPH, xem sâu =====
            do_shorts = random.random() < self.CH_SHORTS_P
            shorts_after = random.randint(1, max(1, n_long - 1))
            print(f"\n[*] Bước 2-3/5 — Gieo từ khóa + xem sâu: {n_long} video dài"
                  f"{' + lướt Shorts' if do_shorts else ''}.")
            watched_long = 0
            fails = 0
            while watched_long < n_long and fails < 4 and self._ch_guard(page):
                if self._ch_left() < self.CH_HOME_RESERVE_S + 150:
                    self._ch_say("Sắp hết giờ phiên — dừng xem video dài, chừa thời gian cho trang chủ.")
                    break
                kw = keywords[kw_i % len(keywords)]
                kw_i += 1
                role = "deep" if watched_long == 0 else "mid"
                try:
                    # Lần tìm đầu luôn lọc (SOP); các lần sau ~60% có lọc để không lặp y một khuôn
                    filtered = self._ch_search(page, kw, use_filter=(watched_long == 0 or random.random() < 0.6))
                    rows = self._ch_read_results(page, niche)
                    if filtered and len([r for r in rows if r["title"] not in seen]) < 2:
                        self._ch_say("Lọc xong còn quá ít video — tìm lại không lọc.")
                        self._ch_search(page, kw, use_filter=False)
                        rows = self._ch_read_results(page, niche)
                    if self._ch_sess is None and watched_long == 0:
                        # chưa biết độ dài video đối thủ -> đo trên trang kết quả (ưu tiên video đúng niche)
                        med = (median_len([r["dur_s"] for r in rows if r["score"] >= NICHE_SCORE_MIN])
                               or median_len([r["dur_s"] for r in rows]))
                        if med:
                            n_long = self._ch_replan(med, n_long, t0, "đo trên trang kết quả")
                            shorts_after = min(shorts_after, max(1, n_long - 1))
                    row, note = self._ch_choose_result(rows, role == "deep", seen)
                    if not row:
                        self._ch_say(f"'{kw}': {note} — thử từ khóa khác.")
                        fails += 1
                        continue
                    vph_txt = f"{row['vph']:.0f} lượt xem/giờ" if row["vph"] else "chưa rõ VPH"
                    self._ch_say(f"Chọn video {watched_long + 1}/{n_long}: '{row['title'][:70]}' — "
                                 f"{row['chan'] or '?'} · {vph_txt} · {note}.")
                    if not self._ch_open_search_result(page, row):
                        self._ch_say("Bấm video nhưng trang không mở — thử lại với từ khóa khác.")
                        fails += 1
                        continue
                    seen.add(row["title"])
                    res = self._ch_watch(page, role, in_niche=(row["score"] >= NICHE_SCORE_MIN or not niche["tokens"]))
                    if res:
                        watched_long += 1
                        self.actions_done += 1
                    else:
                        fails += 1
                    self._ch_rest(page, 8, 25)
                    if do_shorts and watched_long == shorts_after and self._ch_guard(page) \
                            and self._ch_left() > self.CH_HOME_RESERVE_S + 240:
                        do_shorts = False
                        try:
                            page.go_back(wait_until="domcontentloaded", timeout=30000)
                            self._pump_wait(page, random.uniform(2, 4))
                        except Exception:
                            pass
                        if "/results" in (page.url or ""):
                            if self._ch_shorts(page):
                                self.actions_done += 1
                            self._ch_rest(page, 5, 15)
                except RuntimeError:
                    raise
                except Exception as e:
                    self._ch_say(f"Lỗi vòng tìm + xem ({str(e)[:110]}) — thử từ khóa khác.")
                    fails += 1
                    self._ch_rest(page, 5, 12)

            # ===== BƯỚC 4: luyện trang chủ =====
            if self._ch_guard(page) and self._ch_left() > 150:
                print("\n[*] Bước 4/5 — Luyện AI đề xuất (trang chủ):")
                self._ch_home_training(page, niche, seen)
                self.actions_done += 1
        finally:
            # ===== BƯỚC 5: đóng phiên =====
            elapsed = time.time() - t0
            print(f"\n[*] Bước 5/5 — Đóng phiên: đã chạy {int(elapsed // 60)} phút {int(elapsed % 60)} giây, "
                  f"{len(seen)} video đã xem. Đóng tab (profile đóng đúng cách để lưu cookie).")
            try:
                page.close()
            except Exception:
                pass
        print("[+] Kết thúc phiên ngâm kênh.")
