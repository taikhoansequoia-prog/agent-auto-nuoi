# -*- coding: utf-8 -*-
"""v1.9.4 — HỌC NICHE TỪ KÊNH ĐỐI THỦ qua YouTube Data API v3 (chỉ ĐỌC dữ liệu công khai).

Dùng cho chế độ 4 "Ngâm kênh": từ danh sách kênh đối thủ của 1 niche, đọc video mới + bình luận nổi bật rồi rút ra
  - terms     : từ vựng đặc trưng của niche (xuất hiện ở nhiều video / nhiều kênh) -> bộ chấm điểm nhận thêm video đúng niche
  - suggest   : cụm từ khóa gợi ý (lấy từ tag các kênh hay gắn) -> user bấm thêm vào danh sách từ khóa
  - audience  : (có AI Brain) vài dòng tóm tắt người xem niche này thích/hỏi gì, đọc từ bình luận -> đưa vào câu hỏi AI
  - top_titles: các video đang lên của đối thủ (để user tham khảo)

Chi phí quota: ~8 đơn vị / kênh (channels 1 + playlistItems 1 + videos 1 + commentThreads 5) trên hạn mức 10 000/ngày.
Kênh dạng /c/Tên hoặc chỉ ghi tên phải tra bằng search (100 đơn vị) -> nên nhập link @handle.

KHÔNG ghi gì lên YouTube (không like, không bình luận) — toàn bộ là lệnh GET đọc dữ liệu công khai.
Key KHÔNG BAO GIỜ được in ra log (lỗi chỉ in lý do, không in URL).
"""
import json
import math
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request

from src.workflow.channel_mode import _tokens, _split_lines, median_len, session_range_min

API_BASE = "https://www.googleapis.com/youtube/v3"
KEY_NAME = "YOUTUBE_API_KEY"
KEY_DESC = "YouTube Data API v3 — quản lý ở nút 'Niche ngâm kênh' → 'Quản lý key' (kho key riêng)"

MAX_CHANNELS = 12          # số kênh đối thủ đọc tối đa mỗi lần học
VIDEOS_PER_CHANNEL = 30    # số video mới nhất đọc mỗi kênh
COMMENT_VIDEOS = 5         # số video (nổi nhất) lấy bình luận mỗi kênh
COMMENTS_PER_VIDEO = 30
MAX_TERMS = 40
MAX_SUGGEST = 15

# Từ quá chung trong tiêu đề YouTube — không coi là từ vựng của niche.
_LEARN_STOP = set("""
shorts short live watch ever every most more just like after before inside world real made make making first last
year years day days time times people life story stories thing things really never still back biggest best worst
they them here there going know want need good great amazing incredible crazy insane shocking facts fact explained
explain review reaction update news today week month viral trending subscribe channel youtube video videos series
season episode full part with without from into over about your this that these those have been will would could
""".split())


class LearnError(Exception):
    """Lỗi có lời giải thích tiếng Việt cho người dùng (không chứa key)."""


# ---------------------------------------------------------------------------- HTTP
def _urllib_http(path, params, timeout=20):
    """GET API_BASE/path -> (status, dict). Lỗi mạng -> (0, {"error": {"message": ...}})."""
    url = f"{API_BASE}/{path}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers={"Accept": "application/json", "User-Agent": "niche-learner/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, json.loads(r.read().decode("utf-8", "replace") or "{}")
    except urllib.error.HTTPError as e:
        try:
            body = json.loads(e.read().decode("utf-8", "replace") or "{}")
        except Exception:
            body = {}
        return e.code, body if isinstance(body, dict) else {}
    except Exception as e:
        return 0, {"error": {"message": f"{type(e).__name__}: {str(e)[:120]}"}}


def _error_reason(status, body):
    err = (body or {}).get("error") or {}
    reason = ""
    for it in err.get("errors") or []:
        reason = str(it.get("reason") or "")
        if reason:
            break
    return reason, str(err.get("message") or "")


def explain_error(status, body):
    """(status, body lỗi) -> câu tiếng Việt ngắn cho người dùng."""
    reason, msg = _error_reason(status, body)
    low = (reason + " " + msg).lower()
    if status == 0:
        return f"không kết nối được tới Google ({msg[:100]})"
    if "api key not valid" in low or "keyinvalid" in low or "api_key_invalid" in low:
        return "KEY SAI — kiểm tra lại key đã dán"
    if "quotaexceeded" in low or "dailylimitexceeded" in low or "quota" in low:
        return "key đã HẾT QUOTA hôm nay (10 000 đơn vị/ngày, tự hồi lúc 15h giờ VN)"
    if "accessnotconfigured" in low or "has not been used" in low or "is disabled" in low:
        return "key đúng nhưng project CHƯA BẬT 'YouTube Data API v3' (bật trong Google Cloud Console → APIs & Services)"
    if "iprefererblocked" in low or "referer" in low or "ip address" in low or "are blocked" in low:
        return "key bị giới hạn theo IP/website — vào Google Cloud bỏ giới hạn hoặc thêm IP máy này"
    if "commentsdisabled" in low:
        return "video tắt bình luận"
    return f"lỗi {status}: {(msg or reason or 'không rõ')[:140]}"


def _is_key_dead(status, body):
    """Lỗi do KEY (sai/hết quota/chưa bật API) -> nên đổi sang key kế tiếp."""
    reason, msg = _error_reason(status, body)
    low = (reason + " " + msg).lower()
    return status in (400, 403) and any(s in low for s in (
        "api key not valid", "keyinvalid", "api_key_invalid", "quotaexceeded", "dailylimitexceeded",
        "accessnotconfigured", "has not been used", "is disabled", "iprefererblocked", "are blocked"))


class YouTubeAPI:
    """Bọc lệnh GET của YouTube Data API. Nhiều key -> tự xoay khi 1 key chết (sai/hết quota)."""

    def __init__(self, keys, http=None, on_dead=None):
        if isinstance(keys, str):
            keys = [keys]
        self.keys = [k.strip() for k in (keys or []) if k and k.strip()]
        self.http = http or _urllib_http
        self.units = 0          # quota ước tính đã tiêu
        self._i = 0
        self.on_dead = on_dead  # on_dead(key, lý do) mỗi khi 1 key chết (sai/hết quota/chưa bật API)

    def get(self, path, params, cost=1):
        """-> dict kết quả. Lỗi -> raise LearnError (câu tiếng Việt)."""
        if not self.keys:
            raise LearnError("chưa có YouTube API key")
        last = "không rõ"
        while self._i < len(self.keys):
            p = dict(params)
            p["key"] = self.keys[self._i]
            status, body = self.http(path, p)
            self.units += cost
            if status == 200 and isinstance(body, dict):
                return body
            last = explain_error(status, body)
            if _is_key_dead(status, body):
                if callable(self.on_dead):
                    try:
                        self.on_dead(self.keys[self._i], last)
                    except Exception:
                        pass
                if self._i + 1 < len(self.keys):
                    self._i += 1
                    continue
            raise LearnError(last)
        raise LearnError(last)


def test_key(key, http=None):
    """Thử 1 key bằng lệnh rẻ nhất (1 đơn vị). -> (True, "…") | (False, lý do)."""
    key = (key or "").strip()
    if not key:
        return False, "chưa nhập key"
    try:
        body = YouTubeAPI([key], http).get("videos", {"part": "id", "chart": "mostPopular", "maxResults": 1,
                                                      "regionCode": "US"})
        return True, f"key dùng được ({len(body.get('items') or [])} kết quả thử)"
    except LearnError as e:
        return False, str(e)


# v1.9.6: NHIỀU KEY — dán 1 lần nhiều key (ngăn bằng dấu phẩy / chấm phẩy / khoảng trắng / xuống dòng) hoặc thêm dần.
_KEY_SHAPE = re.compile(r"[A-Za-z0-9_\-]{20,120}")


def split_keys(raw):
    """Chuỗi dán vào -> (danh sách key hợp dạng, số mảnh bị loại). Bỏ trùng, giữ thứ tự."""
    good, bad = [], 0
    for part in re.split(r"[,;\s]+", str(raw or "")):
        part = part.strip().strip("\"'`")
        if not part:
            continue
        if _KEY_SHAPE.fullmatch(part):
            if part not in good:
                good.append(part)
        else:
            bad += 1
    return good, bad


def short_mask(key):
    """'AIzaSy...wxyz' -> 'AIza…wxyz' (đủ để người dùng nhận ra key nào, không lộ key)."""
    key = str(key or "")
    return (key[:4] + "…" + key[-4:]) if len(key) >= 12 else "••••"


def test_keys(keys, http=None):
    """Thử TỪNG key (1 đơn vị quota/key). -> [(key, ok, lý do)]."""
    return [(k,) + test_key(k, http) for k in (keys or [])]


def is_invalid_reason(msg):
    """Lý do thuộc loại key hỏng hẳn (sai/bị thu hồi) — khác với hết quota (mai hồi) hay mất mạng."""
    return "KEY SAI" in str(msg or "")

# ---------------------------------------------------------------------------- v1.9.8: KHO KEY (rất nhiều key)
# Key nằm trong data/youtube_keys.json (KHÔNG để trong .env: 1 biến môi trường Windows tối đa 32 767 ký tự ~ 800 key,
# và cần nhớ trạng thái từng key). Mỗi mục: {key, status, msg, checked, used}. Key cũ trong .env (YOUTUBE_API_KEY) được
# gộp vào kho ở lần nạp đầu rồi gỡ khỏi .env khi lưu.
ST_NEW, ST_OK, ST_QUOTA, ST_INVALID, ST_DISABLED, ST_ERROR = "new", "ok", "quota", "invalid", "disabled", "error"
STATUS_LABEL = {ST_NEW: "Chưa kiểm tra", ST_OK: "Dùng được", ST_QUOTA: "Hết quota hôm nay", ST_INVALID: "KEY SAI",
                ST_DISABLED: "Chưa bật API / bị chặn", ST_ERROR: "Lỗi khác"}
_STATUSES = set(STATUS_LABEL)


def keys_file():
    from src.paths import data_dir
    return os.path.join(data_dir(), "youtube_keys.json")


def classify(ok, msg):
    """(ok, lý do của test_key/explain_error) -> mã trạng thái."""
    if ok:
        return ST_OK
    m = str(msg or "")
    if "KEY SAI" in m:
        return ST_INVALID
    if "HẾT QUOTA" in m:
        return ST_QUOTA
    if "CHƯA BẬT" in m or "giới hạn theo IP" in m:
        return ST_DISABLED
    return ST_ERROR


def last_quota_reset(now=None):
    """Mốc reset quota gần nhất (nửa đêm giờ Thái Bình Dương; tính cố định UTC-8 — mùa hè lệch 1 giờ, chỉ làm chậm dùng lại)."""
    now = float(now if now is not None else time.time())
    return ((now - 8 * 3600) // 86400) * 86400 + 8 * 3600


def _env_keys():
    try:
        from src import api_vault
        return list(api_vault.get_keys(KEY_NAME))
    except Exception:
        return []


def env_key_count():
    """Số key YouTube còn nằm trong .env (thêm qua 'Quản lý API key': YOUTUBE_API_KEY, YOUTUBE_API_KEY_2...)."""
    return len([k for k in _env_keys() if _KEY_SHAPE.fullmatch(k or "")])


def pool_load(path=None, env_keys=None):
    """-> list mục key (đã bỏ trùng, đúng dạng). File hỏng/chưa có -> []. Key còn trong .env được gộp vào (status new)."""
    path = path or keys_file()
    out, seen = [], set()
    try:
        with open(path, "r", encoding="utf-8") as f:
            raw = json.load(f)
        items = raw.get("keys") if isinstance(raw, dict) else raw
    except Exception:
        items = []
    for it in items or []:
        if isinstance(it, str):
            it = {"key": it}
        if not isinstance(it, dict):
            continue
        k = str(it.get("key") or "").strip()
        if not _KEY_SHAPE.fullmatch(k) or k in seen:
            continue
        seen.add(k)
        st = it.get("status") if it.get("status") in _STATUSES else ST_NEW
        out.append({"key": k, "status": st, "msg": str(it.get("msg") or "")[:200],
                    "checked": float(it.get("checked") or 0), "used": float(it.get("used") or 0)})
    for k in (_env_keys() if env_keys is None else env_keys):
        if _KEY_SHAPE.fullmatch(k or "") and k not in seen:
            seen.add(k)
            out.append({"key": k, "status": ST_NEW, "msg": "", "checked": 0.0, "used": 0.0})
    return out


def pool_save(entries, path=None):
    """Ghi kho key (atomic). Ghi xong thì gỡ YOUTUBE_API_KEY (+ biến đánh số) khỏi .env để chỉ còn 1 nguồn. -> True/False."""
    path = path or keys_file()
    try:
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump({"keys": list(entries or [])}, f, ensure_ascii=False, indent=0)
        os.replace(tmp, path)
    except Exception:
        return False
    try:
        from src import api_vault
        for name, _v in api_vault.list_keys():
            if name == KEY_NAME or re.fullmatch(re.escape(KEY_NAME) + r"_\d+", name):
                api_vault.delete_key(name)
    except Exception:
        pass
    return True


def pool_add(entries, keys):
    """Thêm key mới vào kho (tại chỗ). -> (số thêm, số đã có sẵn)."""
    have = {e["key"] for e in entries}
    added = dup = 0
    for k in keys or []:
        if k in have:
            dup += 1
            continue
        have.add(k)
        entries.append({"key": k, "status": ST_NEW, "msg": "", "checked": 0.0, "used": 0.0})
        added += 1
    return added, dup


def pool_remove(entries, keys):
    """Xóa các key khỏi kho (tại chỗ). -> số đã xóa."""
    kill = set(keys or [])
    n = len(entries)
    entries[:] = [e for e in entries if e["key"] not in kill]
    return n - len(entries)


def pool_mark(entries, key, ok, msg="", now=None, used=False):
    """Ghi kết quả kiểm tra/sử dụng của 1 key."""
    now = float(now if now is not None else time.time())
    for e in entries:
        if e["key"] == key:
            e["status"], e["msg"], e["checked"] = classify(ok, msg), ("" if ok else str(msg)[:200]), now
            if used:
                e["used"] = now
            return True
    return False


def _effective(e, now=None):
    """Trạng thái hiện tại: key 'hết quota' từ trước mốc reset gần nhất coi như chưa kiểm tra (quota đã hồi)."""
    if e["status"] == ST_QUOTA and e.get("checked", 0) < last_quota_reset(now):
        return ST_NEW
    return e["status"]


def pool_usable(entries, now=None):
    """Danh sách key đem đi dùng: bỏ key sai / chưa bật API / đang hết quota; key ít dùng gần đây đứng trước (chia đều tải);
    key 'lỗi khác' (thường do mạng) xếp cuối."""
    good = [e for e in entries if _effective(e, now) in (ST_OK, ST_NEW)]
    soso = [e for e in entries if _effective(e, now) == ST_ERROR]
    good.sort(key=lambda e: e.get("used", 0))
    return [e["key"] for e in good + soso]


def pool_counts(entries, now=None):
    c = {s: 0 for s in STATUS_LABEL}
    for e in entries:
        c[_effective(e, now)] += 1
    c["total"] = len(entries)
    c["usable"] = len(pool_usable(entries, now))
    return c


def pool_summary(entries, now=None):
    """Một dòng tóm tắt kho key cho giao diện."""
    c = pool_counts(entries, now)
    if not c["total"]:
        return "Chưa có key nào."
    parts = [f"{c['total']} key"]
    for st, label in ((ST_OK, "dùng được"), (ST_NEW, "chưa kiểm tra"), (ST_QUOTA, "hết quota hôm nay"),
                      (ST_INVALID, "sai"), (ST_DISABLED, "chưa bật API/bị chặn"), (ST_ERROR, "lỗi khác")):
        if c[st]:
            parts.append(f"{c[st]} {label}")
    return " · ".join(parts)


def check_keys(keys, http=None, workers=6, on_result=None, should_stop=None):
    """Kiểm tra NHIỀU key song song (1 đơn vị quota/key). on_result(key, ok, lý do) được gọi từ luồng phụ.
    -> [(key, ok, lý do)] theo thứ tự hoàn thành."""
    from concurrent.futures import ThreadPoolExecutor, as_completed
    _stop = should_stop if callable(should_stop) else (lambda: False)
    out = []

    def _one(k):
        if _stop():
            return None
        ok, why = test_key(k, http)
        return k, ok, why
    keys = list(keys or [])
    if not keys:
        return out
    with ThreadPoolExecutor(max_workers=max(1, min(int(workers), len(keys)))) as ex:
        for fut in as_completed([ex.submit(_one, k) for k in keys]):
            try:
                r = fut.result()
            except Exception as e:
                r = None
                _ = e
            if r is None:
                continue
            out.append(r)
            if callable(on_result):
                try:
                    on_result(*r)
                except Exception:
                    pass
    return out


# ---------------------------------------------------------------------------- đọc kênh
def parse_channel_ref(raw):
    """Link/handle/tên kênh -> (kiểu, giá trị): id | handle | user | name. Rỗng -> ("", "")."""
    s = (raw or "").strip()
    if not s:
        return "", ""
    m = re.search(r"youtube\.com/(channel/|user/|c/|@)?([^/?#\s]+)", s, re.IGNORECASE)
    if m:
        kind, val = (m.group(1) or "").lower(), urllib.parse.unquote(m.group(2))
        if kind == "channel/":
            return "id", val
        if kind == "user/":
            return "user", val
        if kind == "@":
            return "handle", val
        return "name", val          # /c/Tên hoặc youtube.com/Tên
    if re.fullmatch(r"UC[\w-]{22}", s):
        return "id", s
    if s.startswith("@"):
        return "handle", s[1:]
    return "name", s


_CH_PARTS = "snippet,contentDetails,statistics"


def _channel_from_item(it):
    sn, st = it.get("snippet") or {}, it.get("statistics") or {}
    return {"id": it.get("id") or "", "title": sn.get("title") or "",
            "uploads": (((it.get("contentDetails") or {}).get("relatedPlaylists") or {}).get("uploads")) or "",
            "subs": int(st.get("subscriberCount") or 0), "video_count": int(st.get("videoCount") or 0)}


def resolve_channel(api, raw):
    """-> dict kênh {id, title, uploads, subs, video_count}. Không tìm thấy -> raise LearnError."""
    kind, val = parse_channel_ref(raw)
    if not kind:
        raise LearnError("dòng trống")
    tries = []
    if kind == "id":
        tries.append({"id": val})
    elif kind == "user":
        tries.append({"forUsername": val})
        tries.append({"forHandle": "@" + val})
    elif kind == "handle":
        tries.append({"forHandle": "@" + val})
    else:
        tries.append({"forHandle": "@" + re.sub(r"\s+", "", val)})
    for extra in tries:
        p = {"part": _CH_PARTS}
        p.update(extra)
        items = api.get("channels", p).get("items") or []
        if items:
            return _channel_from_item(items[0])
    if kind in ("name", "user"):        # /c/Tên, tên trần: phải tra bằng search (100 đơn vị)
        found = api.get("search", {"part": "snippet", "type": "channel", "q": val, "maxResults": 1}, cost=100)
        for it in found.get("items") or []:
            cid = ((it.get("id") or {}).get("channelId")) or ((it.get("snippet") or {}).get("channelId"))
            if cid:
                items = api.get("channels", {"part": _CH_PARTS, "id": cid}).get("items") or []
                if items:
                    return _channel_from_item(items[0])
    raise LearnError("không tìm thấy kênh")


_DUR_RE = re.compile(r"P(?:(\d+)D)?T?(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?")


def iso_duration_s(text):
    """'PT1H2M3S' -> 3723. Không đọc được -> 0."""
    m = _DUR_RE.fullmatch((text or "").strip())
    if not m:
        return 0
    d, h, mi, s = (int(x or 0) for x in m.groups())
    return d * 86400 + h * 3600 + mi * 60 + s


def _age_hours(published_at, now=None):
    try:
        t = time.strptime((published_at or "")[:19], "%Y-%m-%dT%H:%M:%S")
        import calendar
        return max(1.0, ((now or time.time()) - calendar.timegm(t)) / 3600.0)
    except Exception:
        return 0.0


def fetch_channel_videos(api, channel, limit=VIDEOS_PER_CHANNEL, now=None):
    """Video mới nhất của kênh -> [{id, title, tags, views, comments, duration_s, vph, channel, channel_id}]."""
    if not channel.get("uploads"):
        return []
    items = api.get("playlistItems", {"part": "contentDetails", "playlistId": channel["uploads"],
                                      "maxResults": min(50, max(1, limit))}).get("items") or []
    ids = [((it.get("contentDetails") or {}).get("videoId")) for it in items]
    ids = [i for i in ids if i][:limit]
    if not ids:
        return []
    out = []
    for it in api.get("videos", {"part": "snippet,statistics,contentDetails", "id": ",".join(ids),
                                 "maxResults": 50}).get("items") or []:
        sn, st = it.get("snippet") or {}, it.get("statistics") or {}
        views = int(st.get("viewCount") or 0)
        age = _age_hours(sn.get("publishedAt"), now)
        out.append({"id": it.get("id") or "", "title": (sn.get("title") or "").strip(),
                    "tags": [str(t) for t in (sn.get("tags") or [])][:40],
                    "views": views, "comments": int(st.get("commentCount") or 0),
                    "duration_s": iso_duration_s((it.get("contentDetails") or {}).get("duration")),
                    "vph": round(views / age, 2) if age else 0.0,
                    "channel": channel.get("title") or "", "channel_id": channel.get("id") or "",
                    # v1.16.0: tuổi video (giờ) + mở đầu mô tả -> AI đánh giá niche / gói SEO có căn cứ
                    "age_h": round(age, 1), "desc": " ".join(str(sn.get("description") or "").split())[:300]})
    return out


def fetch_comments(api, video_id, limit=COMMENTS_PER_VIDEO):
    """Bình luận nổi bật của 1 video -> [{text, likes}]. Video tắt bình luận / lỗi lẻ -> []."""
    try:
        body = api.get("commentThreads", {"part": "snippet", "videoId": video_id, "order": "relevance",
                                          "maxResults": min(100, max(1, limit)), "textFormat": "plainText"})
    except LearnError as e:
        if "KEY SAI" in str(e) or "HẾT QUOTA" in str(e) or "CHƯA BẬT" in str(e):
            raise
        return []
    out = []
    for it in body.get("items") or []:
        sn = (((it.get("snippet") or {}).get("topLevelComment") or {}).get("snippet")) or {}
        text = " ".join(str(sn.get("textDisplay") or sn.get("textOriginal") or "").split())
        if len(text) >= 12:
            out.append({"text": text[:240], "likes": int(sn.get("likeCount") or 0)})
    return out


# ---------------------------------------------------------------------------- rút hiểu biết (hàm thuần)
def extract_terms(videos, known_tokens=(), channel_titles=(), max_terms=MAX_TERMS):
    """Từ vựng đặc trưng: token có trong tiêu đề/tag của >= ~4% số video (ít nhất 3 video) và — khi học từ 2 kênh
    trở lên — phải xuất hiện ở >= 2 kênh (tránh nhặt tên riêng của 1 kênh). Bỏ token user đã có sẵn trong từ khóa."""
    known = set(known_tokens or ())
    own = set()
    for t in channel_titles or ():
        own.update(_tokens(t))
    df, chans = {}, {}
    for v in videos or []:
        toks = set(_tokens(v.get("title", "")))
        for tag in v.get("tags") or []:
            toks.update(_tokens(tag))
        for t in toks:
            df[t] = df.get(t, 0) + 1
            chans.setdefault(t, set()).add(v.get("channel_id") or v.get("channel") or "")
    n_ch = len({v.get("channel_id") or v.get("channel") or "" for v in videos or []})
    min_df = max(3, int(math.ceil(0.04 * len(videos or []))))
    need_ch = 2 if n_ch >= 2 else 1
    cand = [t for t, n in df.items()
            if n >= min_df and len(chans[t]) >= need_ch and len(t) >= 4
            and t not in known and t not in own and t not in _LEARN_STOP]
    cand.sort(key=lambda t: (len(chans[t]), df[t], t), reverse=True)
    return cand[:max_terms]


def suggest_keywords(videos, existing=(), max_items=MAX_SUGGEST):
    """Cụm từ khóa gợi ý: tag 2–5 từ được gắn ở >= 2 video, xếp theo độ phổ biến; bỏ cụm đã có."""
    have = {str(k).strip().lower() for k in existing or ()}
    df = {}
    for v in videos or []:
        for tag in {str(t).strip() for t in (v.get("tags") or [])}:
            low = " ".join(tag.lower().split())
            if not (2 <= len(low.split()) <= 5) or len(low) > 60 or low in have:
                continue
            if not re.fullmatch(r"[^\W_][\w '&\-]*", low, flags=re.UNICODE):
                continue
            df[low] = df.get(low, 0) + 1
    out = [k for k, n in df.items() if n >= 2]
    out.sort(key=lambda k: (df[k], k), reverse=True)
    return out[:max_items]


def _parse_term_list(raw, allowed):
    """Câu trả lời AI 'a, b, c' -> các từ có trong `allowed` (giữ thứ tự của allowed)."""
    got = {t.strip().lower() for t in re.split(r"[,;\n]+", raw or "") if t.strip()}
    got = {re.sub(r"^[\-\*\d\.\)\s]+", "", t).strip("\"'` ") for t in got}
    return [t for t in allowed if t in got]


# ---------------------------------------------------------------------------- v1.10.0: AI (Claude...) PHÂN TÍCH NICHE
AI_SYSTEM = ("You are a senior YouTube niche analyst. You study competitor channels for a creator who wants to enter the same "
             "niche. You answer with ONE valid JSON object only: no markdown, no code fences, no commentary.")
AI_TIMEOUT_S = 150


def ask_long(brain, system, user, timeout=AI_TIMEOUT_S, images=None):
    """Hỏi AI 1 câu DÀI. Brain cổng OpenAI/Claude có ask_chat (lời dặn hệ thống riêng, timeout dài) thì dùng; không thì
    ask_text (thử truyền timeout; brain cũ không nhận tham số đó thì gọi kiểu cũ). Lỗi -> raise.
    v1.16.0: `images` = đường dẫn ảnh gửi kèm — chỉ brain có `supports_images` mới nhận (brain khác: bỏ qua ảnh)."""
    if hasattr(brain, "ask_chat"):
        kw = {"images": list(images)} if images and _can_see(brain) else {}
        out = brain.ask_chat(system, user, timeout=timeout, temperature=0.3, **kw)
        err = str(getattr(brain, "last_error", "") or "")
        if not out and "temperature" in err.lower() and hasattr(brain, "client") and hasattr(brain, "model_name"):
            # v1.11.0: vài model (dòng GPT suy luận) chỉ nhận temperature mặc định -> gọi lại không kèm tham số đó
            resp = brain.client.chat.completions.create(
                model=brain.model_name, timeout=timeout,
                messages=[{"role": "system", "content": system}, {"role": "user", "content": user}])
            return (resp.choices[0].message.content or "").strip()
        if not out and err:
            raise RuntimeError(err[:300])
        return out or ""
    prompt = system + "\n\n" + user
    try:
        return brain.ask_text(prompt, timeout=timeout) or ""
    except TypeError:
        return brain.ask_text(prompt) or ""


def top_tags(videos, max_items=60):
    """Tag đối thủ hay gắn nhất -> [(tag chữ thường, số video)]. Bỏ tag quá dài / chỉ gắn ở 1 video (khi có >= 8 video)."""
    df = {}
    for v in videos or []:
        for tag in {" ".join(str(t).lower().split()) for t in (v.get("tags") or [])}:
            if tag and len(tag) <= 50:
                df[tag] = df.get(tag, 0) + 1
    need = 2 if len(videos or []) >= 8 else 1
    out = [(t, n) for t, n in df.items() if n >= need]
    out.sort(key=lambda x: (x[1], x[0]), reverse=True)
    return out[:max_items]


def _repair_json(s):
    """Vá JSON do AI viết ẩu: thiếu ngoặc đóng (đo thật 23/11: Claude bỏ sót 1 dấu ']' ở mảng cuối), bị cắt giữa chừng,
    dấu phẩy thừa trước ngoặc đóng. Chỉ thêm/bớt ngoặc, không đụng nội dung chuỗi."""
    out, stack, in_str, esc = [], [], False, False
    for ch in s:
        if in_str:
            out.append(ch)
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
            out.append(ch)
        elif ch in "{[":
            stack.append("}" if ch == "{" else "]")
            out.append(ch)
        elif ch in "}]":
            while stack and stack[-1] != ch:      # ngoặc đóng không khớp -> đóng hộ các ngoặc còn mở bên trong
                out.append(stack.pop())
            if stack:
                stack.pop()
                out.append(ch)
        else:
            out.append(ch)
    if in_str:
        out.append('"')
    while stack:
        out.append(stack.pop())
    return re.sub(r",\s*([}\]])", r"\1", "".join(out))


def parse_json_obj(raw):
    """Câu trả lời AI -> dict (chịu được ```json ... ```, chữ thừa trước/sau, thiếu ngoặc đóng). Không đọc được -> None."""
    s = str(raw or "").strip()
    a = s.find("{")
    if a < 0:
        return None
    b = s.rfind("}")
    for cand in ((s[a:b + 1] if b > a else ""), s[a:]):
        for fix in (False, True):
            if not cand:
                continue
            try:
                obj = json.loads(_repair_json(cand) if fix else cand)
            except Exception:
                continue
            if isinstance(obj, dict):
                return obj
    return None


def _str_list(value, max_items, max_len=80, lower=True):
    out, seen = [], set()
    if isinstance(value, str):
        value = re.split(r"[\n;]+", value)
    for it in value if isinstance(value, (list, tuple)) else []:
        t = " ".join(str(it).split()).strip(" -•*\"'`#")
        if lower:
            t = t.lower()
        if t and len(t) <= max_len and t.lower() not in seen:
            seen.add(t.lower())
            out.append(t)
    return out[:max_items]


def _bullets(value, max_chars=900):
    if isinstance(value, (list, tuple)):
        value = "\n".join("- " + " ".join(str(x).split()).lstrip("-• ") for x in value if str(x).strip())
    return "\n".join(l.rstrip() for l in str(value or "").strip().splitlines() if l.strip())[:max_chars]


# ---------------------------------------------------------------------------- v1.16.0: dữ liệu để TRANH LUẬN có căn cứ
# 4 chủ đề 2 AI tranh luận lần lượt: (khóa, tên, tên tiếng Anh, tóm tắt cho người xem, đề bài cho AI, các trường liên quan)
DEBATE_TOPICS = (
    ("niche", "ĐÁNH GIÁ NICHE", "NICHE ASSESSMENT",
     "niche này có đáng vào không, đông đối thủ cỡ nào, khe hở ở đâu, rủi ro lớn nhất",
     "Is this niche worth entering for a NEW channel right now? How crowded is it (use the channel figures: subscribers, "
     "median views, uploads per week), where exactly is the opening for a newcomer, how big is the upside and what is the "
     "biggest risk.",
     ("niche_verdict_vi", "description")),
    ("traits", "ĐẶC ĐIỂM NICHE", "NICHE CHARACTERISTICS",
     "video thắng trong niche này có đặc điểm gì: mô típ, định dạng, độ dài, nhịp kể, người xem",
     "What defines a video that works in this niche: story motifs, format, length, structure and pacing (hook, middle, "
     "ending), upload cadence, and who the viewer is and what they come for. Which characteristics are mandatory and which "
     "are optional.",
     ("traits_vi", "audience_vi")),
    ("seo", "GÓI SEO", "SEO PACKAGE",
     "tiêu đề, mô tả, tag / hashtag và từ khóa nên đánh trước",
     "The exact SEO package a new channel should use: title formula (length, where the main keyword sits, emotional "
     "trigger), description (what the first 2 lines say, structure, length), tags and hashtags (how many, which kind), and "
     "which search keywords to target first versus avoid.",
     ("seo_vi", "title_patterns", "keywords", "tags", "negative")),
    ("thumb", "THUMBNAIL", "THUMBNAIL",
     "thumbnail nên trông ra sao: bố cục, khuôn mặt / cảm xúc, chữ trên ảnh, màu sắc",
     "What the thumbnail must look like: composition, people / faces and their emotion, text on the thumbnail (how many "
     "words, what kind), colours and contrast, how it pairs with the title, and what to avoid. Compare the thumbnails of "
     "the strong videos with the weak ones.",
     ("thumbnail_vi",)),
)
TOPIC_FIELD = {"niche": "niche", "traits": "traits", "seo": "seo", "thumb": "thumbnail"}   # khóa chủ đề -> trường trong 'opinions'
THUMB_URL = "https://i.ytimg.com/vi/{id}/mqdefault.jpg"       # 320x180, không viền đen, không tốn quota API
THUMB_TOP, THUMB_WEAK = 9, 3


def _can_see(brain):
    return bool(getattr(brain, "supports_images", False))


def _video_line(v, title_len=110):
    age = float(v.get("age_h") or 0)
    return (f"- [{v.get('channel', '?')}] {v.get('title', '')[:title_len]} ({int(v.get('views', 0)):,} views, "
            f"{int(v.get('duration_s', 0)) // 60} min" + (f", {int(age // 24)} days old" if age >= 24 else "") + ")")


def channel_facts(channels, videos):
    """[dict kênh {title, subs, video_count}] -> mỗi kênh 1 dòng số liệu (để AI đánh giá niche đông / thoáng cỡ nào)."""
    out = []
    for ch in channels or []:
        if not isinstance(ch, dict):
            continue
        name = ch.get("title") or "?"
        subs = int(ch.get("subs") or 0)
        line = (f"- {name}: " + (f"{subs:,} subscribers" if subs else "subscriber count hidden")
                + f", {int(ch.get('video_count') or 0):,} videos in total")
        vs = [v for v in videos or [] if (v.get("channel") or "") == name]
        if vs:
            views = sorted(int(v.get("views") or 0) for v in vs)
            mins = sorted(int(v.get("duration_s") or 0) // 60 for v in vs)
            line += (f"; its {len(vs)} newest uploads: median {views[len(views) // 2]:,} views, best {views[-1]:,}, "
                     f"median length {mins[len(mins) // 2]} min")
            ages = [float(v["age_h"]) for v in vs if v.get("age_h")]
            if len(ages) >= 3 and max(ages) - min(ages) >= 24:
                line += f", about {(len(ages) - 1) / ((max(ages) - min(ages)) / 168.0):.1f} uploads per week"
        out.append(line)
    return out


def desc_samples(videos, max_items=6):
    """Mở đầu phần mô tả của các video đang lên nhất (để AI bàn về gói SEO)."""
    top = [v for v in sorted(videos or [], key=lambda x: x.get("vph", 0), reverse=True) if v.get("desc")][:max_items]
    return [f"- [{v.get('channel', '?')}] {v.get('title', '')[:70]} => {v['desc'][:220]}" for v in top]


def pick_thumb_videos(videos):
    """-> [(video, yếu?)]: 9 video đang lên nhất (chia đều các kênh) + 3 video YẾU nhất đã đăng >= 3 ngày, để AI so
    thumbnail của video thắng với video thua."""
    ranked = sorted([v for v in videos or [] if v.get("id")], key=lambda x: x.get("vph", 0), reverse=True)
    n_ch = max(1, len({v.get("channel") or "?" for v in ranked}))
    cap, per, top = max(3, -(-THUMB_TOP // n_ch)), {}, []
    for v in ranked:
        c = v.get("channel") or "?"
        if per.get(c, 0) < cap and len(top) < THUMB_TOP:
            per[c] = per.get(c, 0) + 1
            top.append(v)
    ids = {v["id"] for v in top}
    old = [v for v in ranked if v["id"] not in ids and float(v.get("age_h") or 0) >= 72 and int(v.get("duration_s") or 0) >= 180]
    weak = old[::-1][:THUMB_WEAK] if len(old) >= THUMB_WEAK else []
    return [(v, False) for v in top] + [(v, True) for v in weak]


def _fetch_bytes(url, timeout=12):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def build_thumb_sheet(videos, out_path, fetch=None):
    """Tải thumbnail (ảnh công khai, không tốn quota) của các video chọn bởi pick_thumb_videos rồi ghép thành 1 ẢNH có đánh
    số ở góc trái trên mỗi ô. -> {"path", "items": [{n, id, title, channel, views, age_d, weak}]}; None nếu máy không có
    Pillow hoặc tải được dưới 4 ảnh (khi đó AI chỉ suy từ tiêu đề và phải nói rõ là phỏng đoán)."""
    try:
        from PIL import Image, ImageDraw, ImageFont
    except Exception:
        return None
    import io as _io
    from concurrent.futures import ThreadPoolExecutor
    picks = pick_thumb_videos(videos)
    if len(picks) < 4:
        return None
    get = fetch if callable(fetch) else _fetch_bytes

    def _one(v):
        try:
            im = Image.open(_io.BytesIO(get(THUMB_URL.format(id=v["id"])))).convert("RGB")
            return im if im.size == (320, 180) else im.resize((320, 180))
        except Exception:
            return None
    with ThreadPoolExecutor(max_workers=6) as ex:
        ims = list(ex.map(_one, [v for v, _w in picks]))
    got = [(v, w, im) for (v, w), im in zip(picks, ims) if im is not None]
    if len(got) < 4:
        return None
    cols, W, H, G = 4, 320, 180, 6
    rows = (len(got) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * W + (cols + 1) * G, rows * H + (rows + 1) * G), (24, 24, 24))
    draw = ImageDraw.Draw(sheet)
    try:
        font = ImageFont.load_default(size=26)
    except Exception:
        font = ImageFont.load_default()
    items = []
    for i, (v, weak, im) in enumerate(got):
        x, y = G + (i % cols) * (W + G), G + (i // cols) * (H + G)
        sheet.paste(im, (x, y))
        draw.rectangle([x, y, x + 46, y + 36], fill=(0, 0, 0))
        draw.text((x + 8, y + 3), str(i + 1), fill=(255, 255, 255), font=font)
        items.append({"n": i + 1, "id": v["id"], "title": str(v.get("title") or "")[:100], "channel": v.get("channel") or "",
                      "views": int(v.get("views") or 0), "age_d": int(float(v.get("age_h") or 0) // 24), "weak": bool(weak)})
    try:
        os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
        sheet.save(out_path, "JPEG", quality=86)
    except Exception:
        return None
    return {"path": out_path, "items": items}


def thumb_sheet_path(niche_name):
    """Chỗ lưu ảnh ghép thumbnail của 1 niche (trong data của app; mỗi lần học ghi đè)."""
    try:
        from src.paths import data_dir
        base = data_dir()
    except Exception:
        base = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
    slug = re.sub(r"[^a-z0-9]+", "_", str(niche_name or "").lower()).strip("_")[:40] or "niche"
    return os.path.join(base, "niche_thumbs", slug + ".jpg")


def thumb_lines(sheet):
    return [f"{it['n']} = [{it.get('channel', '?')}] {str(it.get('title', ''))[:80]} ({int(it.get('views', 0)):,} views"
            + (f", {it['age_d']} days old" if it.get("age_d") else "") + (", WEAK performer" if it.get("weak") else "") + ")"
            for it in (sheet or {}).get("items") or []]


def _thumb_block(sheet, see):
    if sheet and see:
        return ("THUMBNAILS - the attached image is a contact sheet with the thumbnails of the videos below; each thumbnail "
                "has its number in its top-left corner (the ones marked WEAK are their worst recent videos, for contrast):\n"
                + "\n".join(thumb_lines(sheet)))
    return ("THUMBNAILS: (no thumbnail images are available to you - infer from the titles only and say clearly that your "
            "thumbnail advice is an assumption)")


def build_analysis_prompt(niche, channels, videos, comments, tags, facts=None, sheet=None, see_sheet=False):
    """Gói dữ liệu đối thủ thành 1 câu hỏi cho AI. v1.16.0: thêm số liệu kênh, mở đầu mô tả, thumbnail + 4 nhận định
    (đánh giá niche / đặc điểm / gói SEO / thumbnail)."""
    by_ch = {}
    for v in sorted(videos, key=lambda x: x.get("vph", 0), reverse=True):
        by_ch.setdefault(v.get("channel") or "?", []).append(v)
    picked = []
    for name, vs in by_ch.items():                      # mỗi kênh tối đa 12 video đang lên nhất
        picked.extend(vs[:12])
    picked = sorted(picked, key=lambda x: x.get("vph", 0), reverse=True)[:60]
    v_lines = "\n".join(_video_line(v) for v in picked)
    t_line = ", ".join(f"{t} ({n})" for t, n in tags[:60]) or "(channels use no tags)"
    c_top = sorted(comments or [], key=lambda c: c.get("likes", 0), reverse=True)[:40]
    c_lines = "\n".join(f"- {c['text'][:180]}" for c in c_top) or "(no comments available)"
    d_lines = "\n".join(desc_samples(videos))
    have = _split_lines(niche.get("keywords"))
    return (
        f"NICHE NAME (given by the creator): {niche.get('name') or '(unnamed)'}\n"
        f"CREATOR'S NOTE: {niche.get('description') or '(none)'}\n"
        f"KEYWORDS THE CREATOR ALREADY HAS: {'; '.join(have[:25]) or '(none)'}\n"
        f"COMPETITOR CHANNELS: {'; '.join(channels)}\n"
        + ("CHANNEL FIGURES:\n" + "\n".join(facts) + "\n" if facts else "") + "\n"
        f"TOP RECENT VIDEOS OF THESE CHANNELS (by views per hour):\n{v_lines}\n\n"
        f"TAGS THEY USE (number of videos):\n{t_line}\n\n"
        + (f"HOW THEIR TOP VIDEOS OPEN THE DESCRIPTION:\n{d_lines}\n\n" if d_lines else "")
        + _thumb_block(sheet, see_sheet) + "\n\n"
        f"TOP VIEWER COMMENTS:\n{c_lines}\n\n"
        "Analyse what niche these channels are really in (judge by the videos, not by the niche name) and reply with ONE "
        "JSON object with exactly these keys:\n"
        '  "description": 1-2 English sentences: what the niche is and who watches it;\n'
        '  "keywords": 18-20 long-tail YouTube search queries in English (3-7 words, lowercase) that a real fan of this '
        "niche would type to find such videos; cover the different sub-topics; no channel names, no hashtags, no years;\n"
        '  "tags": 25-30 lowercase tags a new channel in this niche should use (mix of broad and specific);\n'
        '  "negative": 6-10 lowercase words or short phrases that appear in titles of videos which look related but are '
        "NOT this niche (so a bot can avoid them);\n"
        '  "vocabulary": 20-30 single lowercase words that are specific to this niche and appear in the titles/tags above;\n'
        '  "title_patterns": 3-5 short title formulas the top videos follow (English, with placeholders in brackets);\n'
        '  "audience_vi": 3-5 short lines IN VIETNAMESE: who watches, what they love, what they ask for in comments;\n'
        '  "niche_verdict_vi": 3-4 sentences IN VIETNAMESE - YOUR ASSESSMENT of this niche for a NEW channel: is it worth '
        "entering now, how crowded it is (use the channel figures), where the opening is, the biggest risk. Commit to a "
        "verdict;\n"
        '  "traits_vi": 4-6 short lines IN VIETNAMESE - the CHARACTERISTICS of a video that works in this niche: story '
        "motifs, format, length, structure and pacing (hook / middle / ending), upload cadence; say which are mandatory;\n"
        '  "seo_vi": 4-6 short lines IN VIETNAMESE - the SEO PACKAGE you recommend: title formula (length, where the main '
        "keyword sits, emotional trigger), description (what the first 2 lines say, structure), tags and hashtags (how many, "
        "which kind), which keywords to target first;\n"
        '  "thumbnail_vi": 3-5 short lines IN VIETNAMESE - the THUMBNAIL formula you recommend: composition, people / faces '
        "and emotion, text on the thumbnail (how many words, what kind), colours and contrast, what to avoid; refer to the "
        "thumbnails by their number;\n"
        '  "stance_vi": YOUR OWN OPINION, 3-4 sentences IN VIETNAMESE, first person ("tôi"): if you were launching a new '
        "channel in this niche tomorrow, which ONE story motif, format and video length would you bet on, and what would you "
        "deliberately avoid? Commit to a clear position and justify it with specific videos and view counts from the data. "
        'No "it depends", no list of options - one bet. Facts must come from the data; the bet itself is your professional '
        "judgment.\n"
        "Return only the JSON object.")


def ai_analyze(brain, niche, channels, videos, comments, log=None, facts=None, sheet=None):
    """Nhờ AI phân tích niche từ dữ liệu đối thủ. -> dict {description, keywords, tags, negative, terms, title_patterns,
    audience, notes} hoặc None (AI lỗi / trả lời không đọc được)."""
    _log = log if callable(log) else (lambda _m: None)
    if brain is None or not videos:
        return None
    tags = top_tags(videos)
    try:
        see = bool(sheet) and _can_see(brain)
        raw = ask_long(brain, AI_SYSTEM, build_analysis_prompt(niche, channels, videos, comments, tags, facts, sheet, see),
                       images=[sheet["path"]] if see else None)
    except Exception as e:
        _log(f"AI không phân tích được ({str(e)[:100]}) — dùng cách thống kê.")
        return None
    obj = parse_json_obj(raw)
    if not obj:
        _log("AI trả lời không đúng định dạng — dùng cách thống kê.")
        return None
    out = clean_analysis(obj, niche, channels, videos)
    if not out["keywords"] and not out["tags"] and not out["terms"]:
        _log("AI trả lời thiếu nội dung — dùng cách thống kê.")
        return None
    _log(f"AI đã phân tích: {len(out['keywords'])} từ khóa đuôi dài, {len(out['tags'])} tag, "
         f"{len(out['negative'])} từ loại trừ, {len(out['terms'])} từ vựng đặc trưng.")
    return out


# ---------------------------------------------------------------------------- v1.11.0: 2 AI SONG SONG + ĐỐI CHIẾU CHÉO
def explain_ai_error(err):
    """Lỗi của AI -> câu ngắn tiếng Việt."""
    low = str(err or "").lower()
    if "credit_balance_exhausted" in low or "insufficient_quota" in low or "no credits" in low or "billing" in low:
        return "HẾT CREDIT (nạp thêm tiền API hoặc đổi key khác)"
    if "401" in low or "invalid_api_key" in low or "unauthorized" in low or "incorrect api key" in low:
        return "KEY SAI hoặc đã bị thu hồi"
    if "429" in low or "rate limit" in low:
        return "bị giới hạn tần suất"
    if "timeout" in low or "timed out" in low or "deadline" in low:
        return "quá hạn chờ"
    return (str(err or "không trả lời").strip().replace("\n", " ")[:120]) or "không trả lời"


def _ask_obj(brain, system, prompt, images=None):
    """-> (dict | None, lý do lỗi). Không ném lỗi (chạy trong luồng phụ)."""
    try:
        raw = ask_long(brain, system, prompt, images=images)
    except Exception as e:
        return None, explain_ai_error(e)
    obj = parse_json_obj(raw)
    if not obj:
        return None, explain_ai_error(getattr(brain, "last_error", "")) if not raw else "trả lời không đúng định dạng"
    return obj, ""


_ANALYSIS_KEYS = ("description", "keywords", "tags", "negative", "vocabulary", "title_patterns", "audience_vi",
                  "niche_verdict_vi", "traits_vi", "seo_vi", "thumbnail_vi", "notes_vi", "stance_vi")


def build_review_prompt(niche, channels, videos, tags, mine, theirs, facts=None, sheet=None, see_sheet=False):
    """Vòng 2: mỗi AI đọc bài của AI kia, đối chiếu với dữ liệu rồi viết bản cuối + nhận xét."""
    top = sorted(videos, key=lambda x: x.get("vph", 0), reverse=True)[:25]
    v_lines = "\n".join(_video_line(v, 100) for v in top)
    t_line = ", ".join(f"{t} ({n})" for t, n in tags[:30]) or "(no tags)"

    def _dump(o):
        return json.dumps({k: o.get(k) for k in _ANALYSIS_KEYS if o.get(k)}, ensure_ascii=False)[:9000]
    return (
        f"NICHE NAME: {niche.get('name') or '(unnamed)'}\nCOMPETITOR CHANNELS: {'; '.join(channels)}\n"
        + ("CHANNEL FIGURES:\n" + "\n".join(facts) + "\n" if facts else "") + "\n"
        f"SAMPLE OF THEIR TOP VIDEOS:\n{v_lines}\n\nTAGS THEY USE (number of videos):\n{t_line}\n\n"
        + _thumb_block(sheet, see_sheet) + "\n\n"
        f"YOUR OWN FIRST ANALYSIS (JSON):\n{_dump(mine)}\n\n"
        f"A SECOND ANALYST'S INDEPENDENT ANALYSIS OF THE SAME CHANNELS (JSON):\n{_dump(theirs)}\n\n"
        "Compare the two analyses critically against the data. Then reply with ONE JSON object holding your FINAL, improved "
        "version with the SAME keys (description, keywords, tags, negative, vocabulary, title_patterns, audience_vi, "
        "niche_verdict_vi, traits_vi, seo_vi, thumbnail_vi) and the same size limits (18-20 keywords, 25-30 tags, 6-10 "
        "negative, 20-30 vocabulary words). For the lists: keep what both analyses agree on, adopt items from the second "
        "analyst that are better than yours (copy them verbatim), and drop any item - yours or theirs - that the data does "
        "not support. For niche_verdict_vi, traits_vi, seo_vi and thumbnail_vi write YOUR final view on each topic, concrete "
        "enough to act on, and name inside it any point where you still disagree with the second analyst.\n"
        'Add one more key "review_vi": 2-4 short lines IN VIETNAMESE: what the second analyst got right that you had missed, '
        "and where you still disagree with them and why.\n"
        'Add a key "verdict_vi": YOUR FINAL OPINION, 3-4 sentences IN VIETNAMESE, first person ("tôi"): the one bet you now '
        "recommend to the channel owner (story motif, format, video length), what to avoid, and the point where you STILL "
        "disagree with the second analyst and why. Keep your own judgment: do not adopt their view just to converge and do "
        "not hide a remaining disagreement; if they really changed your mind, say on which point.\n"
        "Return only the JSON object.")


DEBATE_SYSTEM = (
    "You are a senior YouTube strategist in a live debate with another strategist about the SAME competitor data. The channel "
    "owner is reading and wants two real, independent opinions - not a polite merger. The debate goes TOPIC BY TOPIC (the "
    "current topic is named in each request): stay on the current topic. Rules:\n"
    "1. You have YOUR OWN thesis: what you wrote in your analysis (your stance_vi and your view on the current topic). "
    "Defend it. Do not give it up because the other side disagrees, and do not swap it for a different one to look "
    "original: change your mind only when they show specific data that refutes it, and then say exactly which point you "
    "drop and which you keep.\n"
    "2. Separate FACT (what is in the data: titles, view counts, minutes, channel figures, tags, descriptions, comments, "
    "what is visible on the numbered thumbnails) from JUDGMENT (your professional inference). You are expected to make "
    "judgments and bets: mark them (\"tôi đánh giá\", \"tôi cược\") and give the reasoning. \"The data does not prove "
    "it\" is not a rebuttal by itself - say what you believe instead and why.\n"
    "3. Every claim points at something concrete: a video (a few words of its title) with its view count, a channel "
    "figure, a tag count, a viewer comment or a thumbnail number. Check numbers before you use them.\n"
    "4. No pleasantries, no summary of what the other said, no agreeing to be agreeable. Where you do agree, say it in one "
    "short clause and move on to where you differ. Never repeat an argument you already made: bring new evidence or a new "
    "angle, or concede the point.\n"
    "5. End the body of every message with one sentence that starts with \"Chính kiến của tôi:\" - your current position "
    "on the current topic, concrete enough for the owner to act on.\n"
    "6. After that sentence, the LAST line of every message is exactly one of these two status lines:\n"
    "TRẠNG THÁI: CÒN TRANH LUẬN   (you raised an objection the other side has not answered yet, or you still have a new "
    "argument)\n"
    "TRẠNG THÁI: ĐÃ CHỐT   (you have nothing new on this topic: either you two now agree, or your position is final and "
    "the remaining disagreement is for the owner to decide - say which in the message)\n"
    "The debate on a topic ends only when BOTH sides write ĐÃ CHỐT. So never write it to be polite or to finish early "
    "while one of your objections is still unanswered, and never keep arguing when you have nothing new.\n"
    "Write IN VIETNAMESE, plain text, no markdown, no JSON, no headings: 5-9 sentences, at most 200 words, then the status "
    "line. Speak in the first person and address the other analyst as 'bạn'.")

_STATUS_RE = re.compile(r"^\W*TR[ẠA]NG\s+TH[ÁA]I\s*[:\-–—]\s*(.*)$", re.IGNORECASE)


def split_status(text):
    """Lời phản biện -> (lời đã bỏ dòng 'TRẠNG THÁI: …', đã chốt?). Không có dòng trạng thái = còn tranh luận."""
    import unicodedata
    lines = [l for l in unicodedata.normalize("NFC", str(text or "")).splitlines() if l.strip()]
    closed = False
    for i in range(len(lines) - 1, max(-1, len(lines) - 4), -1):
        m = _STATUS_RE.match(lines[i].strip())
        if m:
            st = m.group(1).upper()
            closed = ("CHỐT" in st or "CHOT" in st) and "CÒN" not in st and "CON TRANH" not in st and "CHƯA" not in st
            del lines[i]
            break
    return "\n".join(lines), closed


def _position(text, max_chars=420):
    """Câu 'Chính kiến của tôi: …' trong 1 lời phản biện (không có -> đoạn cuối)."""
    t = " ".join(str(text or "").split())
    i = t.lower().rfind("chính kiến của tôi")
    return (t[i:] if i >= 0 else t[-300:])[:max_chars]


def _talk(said):
    out, cur = [], None
    for t in said:
        if not t.get("text"):
            continue
        if t.get("topic_title") and t["topic_title"] != cur:
            cur = t["topic_title"]
            out.append(f"== TOPIC: {cur} ==")
        st = "" if "closed" not in t else ("\nTRẠNG THÁI: ĐÃ CHỐT" if t["closed"] else "\nTRẠNG THÁI: CÒN TRANH LUẬN")
        out.append(f"[{t.get('ai', '?')}]: {t.get('text', '')}{st}")
    return "\n".join(out)


def build_debate_prompt(niche, channels, videos, tags, me, other, mine, theirs, said, topic, k, cap, comments=None,
                        facts=None, sheet=None, see_sheet=False, earlier=None):
    """v1.16.0: lượt nói thứ k (0 = mở lời) của `me` với `other` về CHỦ ĐỀ `topic` (khóa trong DEBATE_TOPICS). `said` = các
    lượt đã nói VỀ CHỦ ĐỀ NÀY; `cap` = số lượt tối đa của chủ đề; `earlier` = [{title, positions[(tên, chính kiến)]}] của
    các chủ đề đã xong. Mỗi bên giữ chính kiến riêng, chỉ đổi ý khi bị số liệu bác bỏ; lượt nào cũng kết bằng dòng trạng thái."""
    idx = next((i for i, t in enumerate(DEBATE_TOPICS) if t[0] == topic), 0)
    key, title_vi, title_en, _vi, brief, fields = DEBATE_TOPICS[idx]
    top = sorted(videos, key=lambda x: x.get("vph", 0), reverse=True)[:25]
    data = (["CHANNEL FIGURES:\n" + "\n".join(facts)] if facts else []) + [
        "SAMPLE OF THEIR TOP VIDEOS:\n" + "\n".join(_video_line(v, 100) for v in top)]
    if key != "thumb":
        data.append("TAGS THEY USE (number of videos):\n" + (", ".join(f"{t} ({n})" for t, n in tags[:30]) or "(no tags)"))
    if key == "seo":
        d_lines = desc_samples(videos)
        if d_lines:
            data.append("HOW THEIR TOP VIDEOS OPEN THE DESCRIPTION:\n" + "\n".join(d_lines))
    if key == "thumb":
        data.append(_thumb_block(sheet, see_sheet))
    if key in ("niche", "traits"):
        c_top = sorted(comments or [], key=lambda c: c.get("likes", 0), reverse=True)[:15]
        data.append("TOP VIEWER COMMENTS:\n" + ("\n".join(f"- {str(c.get('text', ''))[:160]}" for c in c_top)
                                                or "(no comments available)"))

    def _dump(o):
        return json.dumps({x: o.get(x) for x in ("stance_vi",) + tuple(fields) if o.get(x)}, ensure_ascii=False)[:4500]
    done = ""
    if earlier:
        done = ("POSITIONS ALREADY STATED ON THE EARLIER TOPICS (context only - do not reopen them):\n" + "\n".join(
            f"[{e.get('title', '?')}] [{n}]: {p}" for e in earlier for n, p in e.get("positions") or []) + "\n\n")
    if k == 0:
        task = ("OPEN THIS TOPIC. State YOUR position on it in 1-2 sentences - the one from your own analysis, unchanged. "
                "Then attack the 2 points in the other analyst's view on this topic where following their advice would cost "
                "the channel owner the most, citing the data. If your two positions are close, say so in one clause and go "
                "straight to the real differences. The other side has not answered yet, so your status line is "
                "TRẠNG THÁI: CÒN TRANH LUẬN.")
    else:
        first = ("This is your first message on this topic: begin by restating YOUR position on it in 1-2 sentences - the "
                 "one from your own analysis, unchanged. ") if k == 1 else ""
        task = ("REPLY to the other analyst's latest message. " + first + "Answer their objections one by one: hold your "
                "ground with data or reasoning where you are right; drop a point only if they actually refuted it (say "
                "which). Then press the strongest disagreement that is still unresolved on this topic: say what the owner "
                "would lose by following their advice instead of yours. If nothing is left unresolved, or everything has "
                "been said and neither side will move, give your final position on this topic and write "
                "TRẠNG THÁI: ĐÃ CHỐT.")
    if k >= cap - 2:
        task += (" THIS IS YOUR LAST TURN ON THIS TOPIC: finish with your verdict on it - what you still hold against the "
                 "other analyst, what (if anything) they genuinely changed your mind about, and the single most important "
                 "action for the owner. Do not manufacture agreement: if you still disagree, say so. Your status line is "
                 "TRẠNG THÁI: ĐÃ CHỐT.")
    return (f"LIVE DEBATE - you are {me}; the other analyst is {other}.\n"
            f"CURRENT TOPIC ({idx + 1} of {len(DEBATE_TOPICS)}): {title_en} ({title_vi}) - {brief}\n"
            f"Turn {k + 1} on this topic (at most {cap}).\n"
            f"NICHE NAME: {niche.get('name') or '(unnamed)'}\nCOMPETITOR CHANNELS: {'; '.join(channels)}\n\n"
            + "\n\n".join(data) + "\n\n"
            f"YOUR ANALYSIS ON THIS TOPIC AND YOUR STANCE (JSON):\n{_dump(mine)}\n\n"
            f"THE OTHER ANALYST'S ANALYSIS ON THIS TOPIC AND STANCE (JSON):\n{_dump(theirs)}\n\n"
            + done +
            f"DEBATE SO FAR ON THIS TOPIC:\n{_talk(said) or '(nothing yet - you speak first)'}\n\nYOUR TASK: {task}\n"
            "Reply with your message only.")


def debate_addendum(said, me="", other=""):
    """Phần nối vào câu hỏi 'bản cuối' khi 2 AI vừa đấu trí xong. `me`/`other` = tên 2 bên trong biên bản (để AI không nhầm
    lời mình với lời đối phương)."""
    who = (f"In this transcript YOU are [{me}] and the second analyst is [{other}]. " if me and other else "")
    return ("\n\nBEFORE YOU WRITE THE FINAL VERSION, HERE IS THE DEBATE YOU TWO JUST HAD:\n" + _talk(said) + "\n\n" + who +
            "Your final JSON must drop what you were actually refuted on and KEEP what you successfully defended - do not "
            "adopt the other analyst's items merely to converge. Your niche_verdict_vi, traits_vi, seo_vi and thumbnail_vi "
            "must be your position at the END of the debate on each topic. In "
            '"review_vi" (3-5 lines) say what the debate made you change and what you still dispute; "verdict_vi" is your '
            "final position after this debate.\nReturn only the JSON object.")


def _ask_text(brain, system, prompt, images=None):
    """-> (câu trả lời văn bản, lý do lỗi). Không ném lỗi (dùng cho lượt đấu trí)."""
    try:
        raw = ask_long(brain, system, prompt, images=images)
    except Exception as e:
        return "", explain_ai_error(e)
    text = re.sub(r"^```[a-zA-Z]*\s*|\s*```$", "", str(raw or "").strip())
    text = "\n".join(l.rstrip() for l in text.splitlines() if l.strip())[:2600]
    if not text:
        return "", explain_ai_error(getattr(brain, "last_error", ""))
    return text, ""


def _merge_lists(a, b, cap):
    """Gộp 2 danh sách: mục CẢ HAI cùng có đứng đầu, phần còn lại xen kẽ. -> (danh sách, số mục trùng)."""
    la, lb = [x.lower() for x in a], [x.lower() for x in b]
    both = [x for x in a if x.lower() in lb]
    ra, rb = [x for x in a if x.lower() not in lb], [x for x in b if x.lower() not in la]
    rest = []
    for i in range(max(len(ra), len(rb))):
        rest += ra[i:i + 1] + rb[i:i + 1]
    return (both + rest)[:cap], len(both)


def _para(value, max_chars=900):
    """Đoạn văn ý kiến của AI (chuỗi hoặc danh sách dòng) -> 1 đoạn gọn."""
    if isinstance(value, (list, tuple)):
        value = " ".join(str(x).strip() for x in value if str(x).strip())
    return " ".join(str(value or "").split())[:max_chars]


def clean_analysis(obj, niche, channels, videos):
    """Làm sạch câu trả lời JSON của AI -> dict chuẩn (xem ai_analyze)."""
    ch_tokens = set()
    for c in channels:
        ch_tokens.update(_tokens(c))
    chan_low = [c.lower() for c in channels if len(c) >= 4]
    kws = [k for k in _str_list(obj.get("keywords"), 24, 70)
           if 2 <= len(k.split()) <= 9 and not any(c in k for c in chan_low) and not re.search(r"\b(19|20)\d\d\b", k)]
    df = {}                                              # từ vựng AI nêu phải CÓ THẬT trong tiêu đề/tag (>= 2 video)
    for v in videos:
        toks = set(_tokens(v.get("title", "")))
        for tag in v.get("tags") or []:
            toks.update(_tokens(tag))
        for t in toks:
            df[t] = df.get(t, 0) + 1
    terms = []
    for w in _str_list(obj.get("vocabulary"), 40, 30):
        for t in _tokens(w):
            if df.get(t, 0) >= 2 and t not in ch_tokens and t not in terms:
                terms.append(t)
    return {"description": " ".join(str(obj.get("description") or "").split())[:700],
            "keywords": kws[:20], "tags": _str_list(obj.get("tags"), 30, 50),
            "negative": _str_list(obj.get("negative"), 10, 30), "terms": terms[:MAX_TERMS],
            "title_patterns": _str_list(obj.get("title_patterns"), 5, 140, lower=False),
            "audience": _bullets(obj.get("audience_vi")), "notes": _bullets(obj.get("notes_vi")),
            "stance": _para(obj.get("stance_vi"), 1500), "verdict": _para(obj.get("verdict_vi"), 1500),
            # v1.16.0: 4 nhận định theo chủ đề tranh luận
            # (chạy thật 24/11: bản chốt sau tranh luận dài 1100-1400 ký tự mỗi mục -> mức cắt cũ làm cụt câu)
            "niche_verdict": _para(obj.get("niche_verdict_vi"), 2400), "traits": _bullets(obj.get("traits_vi"), 3200),
            "seo": _bullets(obj.get("seo_vi"), 3200), "thumbnail": _bullets(obj.get("thumbnail_vi"), 2600)}


def _opinion(name, model, c):
    """Nhận định của 1 AI về 4 chủ đề (c = kết quả clean_analysis)."""
    return {"ai": name, "model": model, "niche": c.get("niche_verdict", ""), "traits": c.get("traits", ""),
            "seo": c.get("seo", ""), "thumbnail": c.get("thumbnail", "")}


def ai_cross_analyze(pair, niche, channels, videos, comments, log=None, debate_rounds=0, on_event=None, facts=None,
                     sheet=None, should_finish=None):
    """2 AI cùng phân tích SONG SONG, (v1.16.0) TRANH LUẬN TỚI CÙNG theo 4 chủ đề DEBATE_TOPICS, rồi mỗi AI viết bản cuối; gộp
    2 bản cuối (mục cả hai cùng chọn đứng đầu). pair = [(tên, brain), (tên, brain)]. 1 AI hỏng -> dùng AI còn lại. Cả 2 hỏng
    -> None. `debate_rounds` = số VÒNG TỐI ĐA mỗi chủ đề (0 = không tranh luận, chỉ đọc chéo): mỗi chủ đề 2 bên lần lượt nói
    cho tới khi CẢ HAI báo 'ĐÃ CHỐT' hoặc hết số vòng. `facts` = dòng số liệu kênh; `sheet` = ảnh ghép thumbnail
    (build_thumb_sheet) — brain nào có `supports_images` thì được xem ảnh; `should_finish()` True = người dùng cho dừng tranh
    luận, viết bản chốt luôn.
    -> dict như ai_analyze + brain, review, agreed {keywords, tags}, note, dialog, stances, opinions, agenda, debate_cap."""
    from concurrent.futures import ThreadPoolExecutor
    _log = log if callable(log) else (lambda _m: None)
    _fin = should_finish if callable(should_finish) else (lambda: False)
    (n1, b1), (n2, b2) = pair
    if not videos:
        return None
    see = {n1: bool(sheet) and _can_see(b1), n2: bool(sheet) and _can_see(b2)}
    imgs = {n: ([sheet["path"]] if see[n] else None) for n in (n1, n2)}

    def _rv(r):       # AI có lúc trả review_vi là 1 chuỗi nhiều dòng thay vì danh sách -> đưa về cùng 1 kiểu gạch đầu dòng
        v = (r or {}).get("review_vi")
        return _bullets(v.splitlines() if isinstance(v, str) else v, 1000)

    def _model(name):
        return str(getattr({n1: b1, n2: b2}.get(name), "model_name", "") or "")

    def _turn(rnd, name, obj, err="", mine=None, theirs=None, other="", after_debate=False):
        """v1.12.1: 1 LƯỢT NÓI của 1 AI (để cửa sổ 'Đối thoại 2 AI' hiện lại). Vòng 2 có thêm nhận xét + bài đã sửa ra sao."""
        model, kind = _model(name), ("analysis" if rnd == 1 else "final")
        if not obj:
            return {"kind": kind, "round": rnd, "ai": name, "other": other, "model": model, "after_debate": after_debate,
                    "error": err or "không trả lời"}
        c = clean_analysis(obj, niche, channels, videos)
        t = {"kind": kind, "round": rnd, "ai": name, "other": other, "model": model, "after_debate": after_debate,
             "error": "", "description": c["description"],
             "keywords": c["keywords"], "tags": c["tags"], "negative": c["negative"], "audience": c["audience"],
             "notes": c["notes"], "stance": c["stance"], "niche_verdict": c["niche_verdict"], "traits": c["traits"],
             "seo": c["seo"], "thumbnail": c["thumbnail"]}
        if rnd == 2:
            t["verdict"] = c["verdict"]
            m = {k.lower() for k in (mine or {}).get("keywords") or []}
            o = {k.lower() for k in (theirs or {}).get("keywords") or []}
            now = {k.lower() for k in c["keywords"]}
            t.update(review=_rv(obj),
                     taken=[k for k in c["keywords"] if k.lower() not in m and k.lower() in o],
                     added=[k for k in c["keywords"] if k.lower() not in m and k.lower() not in o],
                     dropped=[k for k in (mine or {}).get("keywords") or [] if k.lower() not in now])
        return t
    tags = top_tags(videos)

    def _ev(e):
        if callable(on_event):
            try:
                on_event(e)
            except Exception:
                pass

    def _both(p1, p2, what, mk):
        """Hỏi 2 AI song song; AI nào xong trước thì báo + đưa lượt nói ra trước (để người dùng thấy đang tới đâu)."""
        t0 = time.time()

        def _one(name, brain, p):
            r = _ask_obj(brain, AI_SYSTEM, p, imgs[name])
            _log(f"… {name} {'đã trả lời' if r[0] else 'KHÔNG trả lời được'} {what} sau {time.time() - t0:.0f} giây.")
            t = mk(name, r)
            _ev({"ev": "turn", "turn": t})
            return r, t
        with ThreadPoolExecutor(max_workers=2) as ex:
            fa, fb = ex.submit(_one, n1, b1, p1), ex.submit(_one, n2, b2, p2)
            return fa.result(), fb.result()
    try:
        rounds = max(0, min(int(debate_rounds or 0), 10))
    except (TypeError, ValueError):
        rounds = 0
    other_of = {n1: n2, n2: n1}
    _ev({"ev": "start", "names": [n1, n2], "debate_rounds": rounds})
    _ev({"ev": "typing", "who": [n1, n2], "what": "đang phân tích riêng (vòng 1)"})
    ((o1, e1), t1), ((o2, e2), t2) = _both(
        build_analysis_prompt(niche, channels, videos, comments, tags, facts, sheet, see[n1]),
        build_analysis_prompt(niche, channels, videos, comments, tags, facts, sheet, see[n2]), "vòng 1",
        lambda name, r: _turn(1, name, r[0], r[1], other=other_of[name]))
    for name, o, e in ((n1, o1, e1), (n2, o2, e2)):
        _log(f"✓ {name} phân tích xong ({len(_str_list(o.get('keywords'), 30, 70))} từ khóa)." if o else f"✗ {name}: {e}.")
    if not o1 and not o2:
        return None
    if not (o1 and o2):
        out = clean_analysis(o1 or o2, niche, channels, videos)
        ok_name, bad_name, bad_err = (n1, n2, e2) if o1 else (n2, n1, e1)
        out.update(brain=ok_name, review="", agreed={}, dialog=[t1, t2],
                   stances=[{"ai": ok_name, "model": _model(ok_name), "stance": out.get("stance", ""), "verdict": ""}],
                   opinions=[_opinion(ok_name, _model(ok_name), out)], agenda=[], debate_cap=0,
                   note=f"Chỉ có {ok_name} phân tích — {bad_name} không dùng được: {bad_err}.")
        return out if (out["keywords"] or out["tags"] or out["terms"]) else None
    # v1.16.0: TRANH LUẬN TỚI CÙNG theo từng chủ đề — 2 AI lần lượt nói, bên sau đọc được lời bên trước; 1 chủ đề chỉ đóng
    # khi CẢ HAI báo 'ĐÃ CHỐT' (hoặc hết số vòng tối đa). Lời dẫn của bot (kind='note') nằm chung trong dialog.
    debate, debate_note, agenda = [], "", []

    def _note(text):
        t = {"kind": "note", "text": text}
        debate.append(t)
        _ev({"ev": "turn", "turn": t})
    if rounds:
        cap, n_top = rounds * 2, len(DEBATE_TOPICS)
        seat = {n1: (b1, o1, o2), n2: (b2, o2, o1)}
        earlier, stopped = [], False
        _log(f"Tranh luận tới cùng: {n1} và {n2} bàn lần lượt {n_top} chủ đề, mỗi chủ đề tới khi cả hai chốt "
             f"(tối đa {rounds} vòng / chủ đề)…")
        for ti, (key, title, _en, brief_vi, _brief, _fields) in enumerate(DEBATE_TOPICS):
            if debate_note or stopped or _fin():
                stopped = stopped or not debate_note
                agenda.append({"key": key, "title": title, "turns": 0, "settled": False,
                               "why": "error" if debate_note else "stopped"})
                continue
            order = (n1, n2) if ti % 2 == 0 else (n2, n1)
            _note(f"▶ Chủ đề {ti + 1}/{n_top} — {title}: {brief_vi}. {order[0]} mở lời.")
            said_t, last, why = [], {}, "cap"
            for k in range(cap):
                if _fin():
                    why, stopped = "stopped", True
                    break
                name = order[k % 2]
                brain, mine, theirs = seat[name]
                _ev({"ev": "typing", "who": [name], "what": f"đang soạn lời về {title} (lượt {k + 1})"})
                t0 = time.time()
                raw, err = _ask_text(brain, DEBATE_SYSTEM, build_debate_prompt(
                    niche, channels, videos, tags, name, other_of[name], mine, theirs, said_t, key, k, cap, comments,
                    facts, sheet, see[name], earlier), imgs[name] if key == "thumb" else None)
                text, closed = split_status(raw)
                text = text or raw
                closed = bool(text) and closed and k > 0          # lời mở chủ đề chưa ai đáp -> chưa thể chốt
                turn = {"kind": "debate", "topic": key, "topic_title": title, "round": k // 2 + 1, "n": k + 1, "ai": name,
                        "other": other_of[name], "model": _model(name), "error": "" if text else (err or "không trả lời"),
                        "text": text, "closed": closed}
                debate.append(turn)
                _ev({"ev": "turn", "turn": turn})
                if not text:
                    why = "error"
                    debate_note = f"tranh luận dừng ở chủ đề '{title}', lượt {k + 1}: {name} không trả lời ({turn['error']})"
                    _log("✗ " + debate_note + ".")
                    break
                said_t.append(turn)
                last[name] = closed
                _log(f"… {name} nói xong lượt {k + 1} về {title} sau {time.time() - t0:.0f} giây "
                     f"({'đã chốt' if closed else 'còn tranh luận'}).")
                if last.get(n1) and last.get(n2):
                    why = "settled"
                    break
            agenda.append({"key": key, "title": title, "turns": len(said_t), "settled": why == "settled", "why": why})
            if said_t:
                earlier.append({"title": title, "positions": [
                    (n, _position([t["text"] for t in said_t if t["ai"] == n][-1])) for n in order
                    if any(t["ai"] == n for t in said_t)]})
            if why == "settled":
                _note(f"✔ {title}: hai bên đã chốt sau {len(said_t)} lượt nói.")
            elif why == "cap":
                _note(f"⏹ {title}: hết {rounds} vòng mà hai bên CHƯA cùng chốt — bất đồng còn lại nằm ở bản chốt của từng bên.")
        if stopped:
            _note("⏹ Bạn cho dừng tranh luận — hai AI viết bản chốt từ những gì đã nói.")
    said = [t for t in debate if t.get("kind") == "debate" and t.get("text")]
    add1 = debate_addendum(said, n1, n2) if said else ""
    add2 = debate_addendum(said, n2, n1) if said else ""
    _log((f"Chốt lại: {n1} và {n2} viết bản cuối sau khi tranh luận…") if said else f"Vòng 2: {n1} và {n2} đọc chéo bài của nhau…")
    _ev({"ev": "typing", "who": [n1, n2], "what": "đang viết bản chốt" if said else "đang đọc bài của nhau (vòng 2)"})
    ((r1, x1), f1), ((r2, x2), f2) = _both(
        build_review_prompt(niche, channels, videos, tags, o1, o2, facts, sheet, see[n1]) + add1,
        build_review_prompt(niche, channels, videos, tags, o2, o1, facts, sheet, see[n2]) + add2,
        "bản chốt" if said else "vòng 2",
        lambda name, r: _turn(2, name, r[0], r[1], mine=(t1 if name == n1 else t2), theirs=(t2 if name == n1 else t1),
                              other=other_of[name], after_debate=bool(said)))
    notes = [debate_note] if debate_note else []
    for name, r, x in ((n1, r1, x1), (n2, r2, x2)):
        if not r:
            notes.append(f"{name} không viết được bản đối chiếu ({x}) — dùng bản vòng 1 của nó")
    c1 = clean_analysis(r1 or o1, niche, channels, videos)
    c2 = clean_analysis(r2 or o2, niche, channels, videos)
    kws, n_kw = _merge_lists(c1["keywords"], c2["keywords"], 40)
    kept = []
    for k in kws:        # 2 AI hay đưa 2 biến thể của cùng 1 câu ("x y z" và "x y z full movie") -> giữ câu đứng trước
        if not any(k.startswith(o + " ") or o.startswith(k + " ") for o in kept):
            kept.append(k)
    n_kw = len([k for k in kept[:20] if k in kws[:n_kw]])
    kws = kept[:20]
    tgs, n_tag = _merge_lists(c1["tags"], c2["tags"], 30)
    neg, _n = _merge_lists(c1["negative"], c2["negative"], 10)
    trm, _n = _merge_lists(c1["terms"], c2["terms"], MAX_TERMS)
    pat, _n = _merge_lists(c1["title_patterns"], c2["title_patterns"], 6)
    review = "\n".join(f"{name} nhận xét:\n" + _rv(r)
                       for name, r in ((n1, r1), (n2, r2)) if r and (r or {}).get("review_vi"))
    out = {"description": c1["description"] or c2["description"], "keywords": kws, "tags": tgs, "negative": neg,
           "terms": trm, "title_patterns": pat, "audience": c1["audience"] or c2["audience"],
           "notes": c1["notes"] or c2["notes"], "brain": f"{n1} + {n2} (đối chiếu chéo)", "review": review,
           "agreed": {"keywords": n_kw, "tags": n_tag}, "note": "; ".join(notes)}
    out["dialog"] = [t1, t2] + debate + [f1, f2]
    # v1.15.0: chính kiến của TỪNG bên (ban đầu + sau tranh luận) — không gộp, để chủ kênh tự cân
    out["stances"] = [{"ai": name, "model": _model(name), "stance": t.get("stance", ""), "verdict": (c["verdict"] if r else "")}
                      for name, t, c, r in ((n1, t1, c1, r1), (n2, t2, c2, r2))]
    # v1.16.0: nhận định CUỐI của từng bên về 4 chủ đề + chủ đề nào đã chốt / còn bất đồng
    out["opinions"] = [_opinion(n1, _model(n1), c1), _opinion(n2, _model(n2), c2)]
    out["agenda"], out["debate_cap"] = agenda, (rounds if said else 0)
    _log(f"Hai AI đối chiếu xong: {len(kws)} từ khóa ({n_kw} từ khóa cả hai cùng chọn), {len(tgs)} tag ({n_tag} trùng), "
         f"{len(neg)} từ loại trừ.")
    return out


def ai_refine(brain, niche, terms, comments, log=None):
    """Có AI: lọc bớt từ chung khỏi `terms` + tóm tắt người xem từ bình luận. -> (terms, audience). Lỗi -> giữ nguyên."""
    _log = log if callable(log) else (lambda _m: None)
    audience = ""
    if brain is None:
        return terms, audience
    head = (f"Niche: {niche.get('name') or '(unnamed)'}. {niche.get('description') or ''}\n"
            f"Seed keywords: {'; '.join(_split_lines(niche.get('keywords'))[:12])}\n")
    if len(terms) >= 8:
        try:
            raw = ask_long(
                brain, "You filter vocabulary lists. Reply with a comma-separated list only.",
                head + "\nCandidate vocabulary taken from competitor video titles/tags:\n" + ", ".join(terms) +
                "\n\nReply ONLY with the terms from this list that are SPECIFIC to this niche (drop generic words, "
                "brand-neutral filler and words that fit any topic). Comma-separated, no explanations.", timeout=60)
            kept = _parse_term_list(raw, terms)
            if len(kept) >= 5:
                _log(f"AI giữ {len(kept)}/{len(terms)} từ vựng đặc trưng.")
                terms = kept
        except Exception as e:
            _log(f"AI không lọc được từ vựng ({str(e)[:80]}) — giữ danh sách thống kê.")
    if comments:
        try:
            top = sorted(comments, key=lambda c: c.get("likes", 0), reverse=True)[:60]
            lines = "\n".join(f"- {c['text'][:200]}" for c in top)
            raw = ask_long(
                brain, "Bạn là chuyên gia phân tích khán giả YouTube. Trả lời ngắn gọn bằng tiếng Việt.",
                head + "\nTop viewer comments on competitor videos:\n" + lines +
                "\n\nTrả lời bằng tiếng Việt, tối đa 5 gạch đầu dòng ngắn: người xem niche này thích gì, hay hỏi gì, "
                "kiểu video nào được khen, và kiểu video nào KHÔNG thuộc niche. Không mở bài, không kết luận.", timeout=60)
            audience = "\n".join(l.rstrip() for l in (raw or "").strip().splitlines() if l.strip())[:900]
        except Exception as e:
            _log(f"AI không tóm tắt được bình luận ({str(e)[:80]}).")
    return terms, audience


def learn_niche(niche, keys, brain=None, log=None, http=None, should_stop=None, now=None, on_key_dead=None,
                brain_name="", brain2=None, brain2_name="", ai_note="", debate_rounds=0, on_event=None, pick_ai=None,
                thumb_fetch=None, thumb_path=None, should_finish=None):
    """Đọc các kênh đối thủ của `niche` -> dict `learned` để lưu vào niche. Không đọc được kênh nào -> raise LearnError.

    v1.14.1: `pick_ai` = hàm không tham số trả {brain, brain_name, brain2, brain2_name, ai_note}, gọi SAU khi đọc xong kênh
    (UI kiểm tra AI ở luồng nền trong lúc đọc kênh, tới đây mới chờ lấy kết quả). Có `pick_ai` thì bỏ qua brain truyền vào.

    v1.16.0: `debate_rounds` = số vòng TỐI ĐA mỗi chủ đề tranh luận (xem ai_cross_analyze); `should_finish()` True = dừng
    tranh luận, chốt luôn. Ảnh ghép thumbnail đối thủ được tải khi chạy thật (http=None) hoặc khi truyền `thumb_fetch`
    (hàm url -> bytes; test dùng để không ra mạng); lưu ở `thumb_path` (mặc định data/niche_thumbs/<niche>.jpg).

    learned = {at, channels[tên], failed[(dòng, lý do)], videos, comments, terms[], suggest[], audience, top_titles[],
               units, thumbs{path, items}}"""
    _log = log if callable(log) else (lambda _m: None)
    _stop = should_stop if callable(should_stop) else (lambda: False)
    refs = _split_lines((niche or {}).get("channels"))
    if not refs:
        raise LearnError("niche chưa có kênh đối thủ nào — nhập link kênh rồi bấm 'Lưu niche' trước")
    api = YouTubeAPI(keys, http, on_dead=on_key_dead)
    channels, failed, videos, comments = [], [], [], []
    seen_ids = set()
    for raw in refs[:MAX_CHANNELS]:
        if _stop():
            break
        try:
            ch = resolve_channel(api, raw)
            if ch["id"] in seen_ids:
                continue
            seen_ids.add(ch["id"])
            vids = fetch_channel_videos(api, ch, now=now)
        except LearnError as e:
            failed.append((raw, str(e)))
            _log(f"✗ {raw[:60]} — {e}")
            if not channels and ("KEY SAI" in str(e) or "HẾT QUOTA" in str(e) or "CHƯA BẬT" in str(e)
                                 or "không kết nối" in str(e) or "giới hạn theo IP" in str(e)):
                raise LearnError(str(e))
            continue
        channels.append(ch)
        videos.extend(vids)
        n_c = 0
        pool = [v for v in vids if v["duration_s"] >= 180 and v["comments"] > 0] or [v for v in vids if v["comments"] > 0]
        for v in sorted(pool, key=lambda x: x["vph"], reverse=True)[:COMMENT_VIDEOS]:
            if _stop():
                break
            got = fetch_comments(api, v["id"])
            comments.extend(got)
            n_c += len(got)
        _log(f"✓ {ch['title']} — {len(vids)} video, {n_c} bình luận.")
    if not channels:
        why = failed[0][1] if failed else "không có kênh hợp lệ"
        raise LearnError(f"không đọc được kênh nào ({why})")
    if len(refs) > MAX_CHANNELS:
        _log(f"Chỉ đọc {MAX_CHANNELS} kênh đầu (niche có {len(refs)} kênh).")

    known = set()
    for kw in _split_lines(niche.get("keywords")):
        known.update(_tokens(kw))
    known.update(_tokens(niche.get("name") or ""))
    known.update(_tokens(niche.get("description") or ""))
    terms = extract_terms(videos, known, [c["title"] for c in channels])
    suggest = suggest_keywords(videos, _split_lines(niche.get("keywords")))
    # v1.10.0: có AI -> 1 lượt phân tích đầy đủ (từ khóa đuôi dài, tag, từ loại trừ, từ vựng, người xem, nhận xét).
    # AI lỗi/trả lời hỏng -> cách cũ (lọc từ vựng + tóm tắt bình luận); không có AI -> thuần thống kê.
    ai, audience = None, ""
    if callable(pick_ai) and not _stop():
        _p = pick_ai() or {}
        brain, brain2 = _p.get("brain"), _p.get("brain2")
        brain_name, brain2_name = str(_p.get("brain_name") or ""), str(_p.get("brain2_name") or "")
        ai_note = str(_p.get("ai_note") or "")
    facts, sheet = channel_facts(channels, videos), None
    if brain is not None and not _stop() and (callable(thumb_fetch) or http is None):
        try:
            sheet = build_thumb_sheet(videos, thumb_path or thumb_sheet_path(niche.get("name")), thumb_fetch)
        except Exception as e:
            _log(f"Không ghép được ảnh thumbnail ({type(e).__name__}: {str(e)[:80]}).")
        _log(f"Đã ghép {len(sheet['items'])} thumbnail của đối thủ thành 1 ảnh để AI xem."
             if sheet else "Không tải được thumbnail đối thủ — AI sẽ bàn về thumbnail chỉ từ tiêu đề (phỏng đoán).")
    if brain is not None and not _stop():
        if brain2 is not None:          # v1.11.0: 2 AI chạy song song rồi đọc chéo bài của nhau
            _log(f"Đang nhờ 2 AI ({brain_name} + {brain2_name}) phân tích SONG SONG {len(videos)} video + "
                 f"{len(comments)} bình luận…")
            ai = ai_cross_analyze([(brain_name or "AI 1", brain), (brain2_name or "AI 2", brain2)], niche,
                                  [c["title"] for c in channels], videos, comments, _log,
                                  debate_rounds=debate_rounds, on_event=on_event, facts=facts, sheet=sheet,
                                  should_finish=should_finish)
            if ai:
                brain_name = ai["brain"]
        else:
            _log(f"Đang nhờ AI{' ' + brain_name if brain_name else ''} phân tích {len(videos)} video + "
                 f"{len(comments)} bình luận…")
            ai = ai_analyze(brain, niche, [c["title"] for c in channels], videos, comments, _log, facts, sheet)
    if ai:
        audience = ai["audience"]
        if len(ai["terms"]) >= 5:
            terms = ai["terms"]
        have = {k.lower() for k in _split_lines(niche.get("keywords"))}
        suggest = [k for k in suggest if k not in ai["keywords"]]
        ai["keywords"] = [k for k in ai["keywords"] if k not in have]
    elif not _stop():
        terms, audience = ai_refine(brain, niche, terms, comments, _log)
    top = sorted(videos, key=lambda v: v["vph"], reverse=True)[:10]
    return {
        "at": time.strftime("%Y-%m-%d %H:%M", time.localtime(now) if now else time.localtime()),
        "channels": [c["title"] for c in channels],
        "failed": [[r, w] for r, w in failed],
        "videos": len(videos), "comments": len(comments),
        # v1.9.5: trung vị độ dài video DÀI (>= 3 phút) của đối thủ -> channel_mode tính nhịp phiên theo số này
        "typical_len_s": median_len([v["duration_s"] for v in videos]),
        "long_videos": len([v for v in videos if v["duration_s"] >= 180]),
        "terms": terms, "suggest": suggest, "audience": audience,
        "tags": [t for t, _n in top_tags(videos, 30)],
        "ai": ({"brain": brain_name or "AI", "description": ai["description"], "keywords": ai["keywords"],
                "tags": ai["tags"], "negative": ai["negative"], "title_patterns": ai["title_patterns"],
                "notes": ai["notes"], "review": ai.get("review", ""), "agreed": ai.get("agreed") or {},
                "dialog": ai.get("dialog") or [],
                "stances": [x for x in (ai.get("stances") or [{"ai": brain_name or "AI", "model": "", "stance": ai.get("stance", ""),
                                                               "verdict": ""}]) if x.get("stance") or x.get("verdict")],
                # v1.16.0: nhận định của từng AI về 4 chủ đề + chủ đề nào đã chốt
                "opinions": [x for x in (ai.get("opinions") or [_opinion(brain_name or "AI", "", ai)])
                             if any(x.get(f) for f in TOPIC_FIELD.values())],
                "agenda": ai.get("agenda") or [], "debate_cap": int(ai.get("debate_cap") or 0),
                "note": "; ".join(x for x in (ai.get("note", ""), ai_note) if x)} if ai else {}),
        "ai_note": ai_note,
        "thumbs": ({"path": sheet["path"], "items": sheet["items"]} if (sheet and ai) else {}),
        "top_titles": [f"{v['title'][:90]} — {v['channel']} ({v['views']:,} lượt xem)" for v in top],
        "units": api.units,
    }


def dialog_intro(debate_rounds=0, legacy=False):
    """Lời dẫn đầu khung chat. `legacy` = cuộc đấu trí kiểu cũ (v1.14-1.15: số vòng cố định, không chia chủ đề)."""
    if debate_rounds and legacy:
        return ("Hai AI nhận cùng một bộ dữ liệu kênh đối thủ. Vòng 1 mỗi bên nói phân tích và CHÍNH KIẾN của mình (chưa thấy "
                f"bài của nhau). Sau đó hai bên ĐẤU TRÍ: lần lượt phản biện lập luận của nhau {debate_rounds} vòng — mỗi bên phải "
                "bảo vệ quan điểm riêng, chỉ đổi ý khi bị số liệu bác bỏ. Cuối cùng mỗi bên chốt lại bài và chính kiến cuối của mình.")
    if debate_rounds:
        return ("Hai AI nhận cùng một bộ dữ liệu kênh đối thủ (số liệu kênh, video, tag, mô tả, bình luận, ảnh thumbnail). "
                "Vòng 1 mỗi bên tự viết phân tích và CHÍNH KIẾN của mình (chưa thấy bài của nhau). Sau đó hai bên TRANH LUẬN "
                "TỚI CÙNG theo 4 chủ đề: " + " → ".join(t[1] for t in DEBATE_TOPICS) + ". Ở mỗi chủ đề hai bên lần lượt "
                "phản biện cho tới khi CẢ HAI báo 'đã chốt' (hết lý lẽ mới: hoặc đã đồng ý, hoặc giữ bất đồng để bạn quyết) — "
                f"tối đa {debate_rounds} vòng mỗi chủ đề. Cuối cùng mỗi bên viết bản chốt của mình.")
    return ("Hai AI nhận cùng một bộ dữ liệu kênh đối thủ. Vòng 1 mỗi bên nói phân tích của mình (chưa thấy bài của nhau). "
            "Vòng 2 mỗi bên đọc bài của bên kia rồi trả lời: đồng ý gì, phản đối gì, sửa bài mình ra sao.")


def _topic_lines(t, lead=""):
    """4 nhận định (đánh giá niche / đặc điểm / gói SEO / thumbnail) của 1 lượt phân tích hoặc bản chốt -> các dòng."""
    out = []
    for key, title, *_rest in DEBATE_TOPICS:
        val = str(t.get("niche_verdict" if key == "niche" else TOPIC_FIELD[key]) or "").strip()
        if val:
            out += [f"{lead}{title}:"] + val.splitlines() + [""]
    return out


def turn_message(t, side=0):
    """1 lượt nói (analysis / debate / final / note) -> 1 tin nhắn của khung chat {side, name, model, sub, text}. Lời ở ngôi
    thứ nhất; kind='note' = lời dẫn của bot (side -1)."""
    t = t or {}
    kind = t.get("kind") or ("analysis" if t.get("round") == 1 else "final")
    if kind == "note":
        return {"side": -1, "name": "", "model": "", "sub": "", "text": str(t.get("text") or "")}
    name, other = t.get("ai") or "?", t.get("other") or "AI kia"

    def _lst(items):
        return ["   • " + str(x) for x in items]

    lines = []
    if kind == "debate":
        if t.get("topic_title"):
            sub = f"{t['topic_title']} · lượt {t.get('n', '?')} · gửi {other}"
            if not t.get("error"):
                sub += " · ĐÃ CHỐT" if t.get("closed") else " · còn tranh luận"
        else:
            sub = f"Phản biện {t.get('round', '?')} · gửi {other}"
        lines = str(t.get("text") or "").splitlines() if not t.get("error") else \
            [f"(Không trả lời được: {t['error']}.) Cuộc đấu trí dừng ở đây."]
    elif kind == "analysis":
        sub = "Vòng 1 · phân tích riêng"
        if t.get("error"):
            lines = [f"(Không trả lời được: {t['error']}.)"]
        else:
            if t.get("description"):
                lines += ["Theo tôi, niche này là: " + t["description"], ""]
            if t.get("stance"):
                lines += ["CHÍNH KIẾN CỦA TÔI: " + t["stance"], ""]
            lines += _topic_lines(t)
            if t.get("audience"):
                lines += ["Người xem:"] + str(t["audience"]).splitlines() + [""]
            if t.get("notes"):
                lines += ["Nhận xét của tôi:"] + str(t["notes"]).splitlines() + [""]
            kws = t.get("keywords") or []
            if kws:
                lines += [f"Tôi đề xuất {len(kws)} từ khóa:"] + _lst(kws)
            if t.get("tags"):
                lines += ["", f"Tag ({len(t['tags'])}): " + ", ".join(t["tags"])]
            if t.get("negative"):
                lines += ["Từ loại trừ: " + "; ".join(t["negative"])]
    else:
        after = bool(t.get("after_debate"))
        sub = f"Chốt lại · gửi {other}" if after else f"Vòng 2 · trả lời {other}"
        if t.get("error"):
            lines = [f"(Không trả lời được: {t['error']}.) Bot dùng bản vòng 1 của AI này."]
        else:
            lines += [f"Gửi {other}: sau khi tranh luận, tôi chốt lại như sau." if after else f"Gửi {other}: tôi đã đọc bài của bạn."]
            lines += str(t.get("review") or "(Tôi không có nhận xét gì thêm.)").splitlines() + [""]
            if t.get("verdict"):
                lines += ["CHÍNH KIẾN CUỐI CÙNG CỦA TÔI: " + t["verdict"], ""]
            lines += _topic_lines(t, "TÔI CHỐT — ")
            taken, added, dropped = t.get("taken") or [], t.get("added") or [], t.get("dropped") or []
            if taken:
                lines += [f"Tôi lấy thêm {len(taken)} từ khóa từ bài của bạn:"] + _lst(taken)
            if added:
                lines += [f"Đọc xong tôi tự thêm {len(added)} từ khóa mới:"] + _lst(added)
            if dropped:
                lines += [f"Tôi bỏ {len(dropped)} từ khóa trong bài cũ của mình:"] + _lst(dropped)
            if not (taken or added or dropped):
                lines += ["Tôi giữ nguyên bộ từ khóa của mình."]
            if t.get("negative"):
                lines += ["", "Từ loại trừ tôi chốt: " + "; ".join(t["negative"])]
    while lines and not lines[-1]:
        lines.pop()
    return {"side": 1 if side == 1 else 0, "name": name, "model": str(t.get("model") or ""), "sub": sub, "text": "\n".join(lines)}


def spoken_turns(dialog):
    """Số lượt NÓI của 2 AI trong 1 cuộc đối thoại (không tính lời dẫn của bot)."""
    return len([t for t in dialog or [] if isinstance(t, dict) and t.get("kind") != "note"])


def dialog_messages(learned):
    """v1.13.0: cuộc đối chiếu / đấu trí 2 AI kể lại như một CUỘC TRÒ CHUYỆN -> [{side, name, model, sub, text}] (side 0/1 = 2 AI,
    -1 = lời dẫn của bot). [] nếu lần học đó không chạy 2 AI."""
    L = learned or {}
    A = L.get("ai") or {}
    turns = [t for t in (A.get("dialog") or []) if isinstance(t, dict)]
    if not turns:
        return []
    names = []
    for t in turns:
        if t.get("ai") and t["ai"] not in names:
            names.append(t["ai"])

    def _sys(text):
        return {"side": -1, "name": "", "model": "", "sub": "", "text": text}

    deb = [t for t in turns if t.get("kind") == "debate"]
    n_deb = max([int(t.get("round") or 0) for t in deb] or [0])
    by_topic = any(t.get("topic") for t in deb)
    out = [_sys(dialog_intro(int(A.get("debate_cap") or 0) or n_deb, legacy=not by_topic))]
    out += [turn_message(t, names.index(t["ai"]) if t.get("ai") in names else 0) for t in turns]
    out.append(_sys(dialog_outro(A)))
    return out


def dialog_outro(A):
    """Lời kết của bot ở cuối khung chat (A = learned['ai'])."""
    A = A or {}
    ag = A.get("agreed") or {}
    end = (f"Bot gộp 2 bản cuối: cả hai cùng chọn {ag.get('keywords', 0)} từ khóa và {ag.get('tags', 0)} tag — các mục này đứng đầu "
           f"ở 'Xem kết quả học', phần còn lại lấy xen kẽ của từng bên." if ag
           else f"Không có đối chiếu chéo — kết quả là bài của {A.get('brain', 'AI còn lại')}.")
    if A.get("note"):
        end += "\nLƯU Ý: " + A["note"]
    return end


def format_dialog(learned):
    """Cuộc trò chuyện 2 AI dạng văn bản thuần (để chép). '' nếu lần học đó không chạy 2 AI."""
    msgs = dialog_messages(learned)
    if not msgs:
        return ""
    names = []
    for m in msgs:
        if m["side"] >= 0 and m["name"] not in names:
            names.append(m["name"])
    out = [f"ĐỐI THOẠI GIỮA 2 AI — {' và '.join(names)}  (học lúc {(learned or {}).get('at', '?')})"]
    for m in msgs:
        if m["side"] < 0:
            out += ["", "— " + m["text"]]
        else:
            out += ["", f"■ {m['name']}" + (f" ({m['model']})" if m["model"] else "") + f" — {m['sub']}", m["text"]]
    return "\n".join(out)


AGENDA_LABEL = {"settled": "hai bên đã chốt sau {n} lượt nói", "cap": "hết số vòng sau {n} lượt nói, hai bên CHƯA cùng chốt",
                "stopped": "bạn cho dừng sớm ({n} lượt nói)", "error": "dừng vì 1 AI không trả lời ({n} lượt nói)"}


def topic_report(A, thumbs=None):
    """v1.16.0: phần báo cáo theo 4 CHỦ ĐỀ — nhận định cuối của TỪNG AI (không gộp) + chủ đề đó đã chốt hay còn bất đồng.
    A = learned['ai']; thumbs = learned['thumbs']. [] nếu lần học đó AI không nêu nhận định nào."""
    ops = [x for x in (A or {}).get("opinions") or [] if isinstance(x, dict)]
    if not any(x.get(f) for x in ops for f in TOPIC_FIELD.values()):
        return []
    ag = {a.get("key"): a for a in (A.get("agenda") or []) if isinstance(a, dict)}
    out = ["", "══ 4 CHỦ ĐỀ — " + ("LẬP LUẬN CUỐI CỦA TỪNG AI SAU KHI TRANH LUẬN (không gộp, bạn là người quyết)" if ag
                                   else ("NHẬN ĐỊNH CỦA TỪNG AI" if len(ops) > 1 else "NHẬN ĐỊNH CỦA AI")) + " ══"]
    for key, title, *_rest in DEBATE_TOPICS:
        rows = [x for x in ops if x.get(TOPIC_FIELD[key])]
        if not rows:
            continue
        st = ag.get(key)
        tail = ""
        if st:
            tail = "  —  " + (AGENDA_LABEL.get(st.get("why"), "").format(n=st.get("turns", 0)) if st.get("turns")
                              else "chưa tranh luận chủ đề này")
        out += ["", f"▶ {title}{tail}"]
        for x in rows:
            out += [f"  ■ {x.get('ai', 'AI')}" + (f" ({x['model']})" if x.get("model") else "") + ":",
                    "    " + str(x[TOPIC_FIELD[key]]).replace("\n", "\n    ")]
        items = (thumbs or {}).get("items") or []
        if key == "thumb" and items:
            out += ["", f"  Số thumbnail AI nhắc tới (ảnh ghép: {(thumbs or {}).get('path', '')}):"]
            out += [f"    {it.get('n')} = {str(it.get('title', ''))[:70]} — {it.get('channel', '')} ({int(it.get('views', 0)):,} lượt xem)"
                    + (" [video YẾU, để so sánh]" if it.get("weak") else "") for it in items]
    return out


def format_report(learned):
    """dict learned -> đoạn văn bản cho cửa sổ kết quả."""
    L = learned or {}
    out = [f"Học lúc {L.get('at', '?')} — {len(L.get('channels') or [])} kênh, {L.get('videos', 0)} video, "
           f"{L.get('comments', 0)} bình luận (tốn ~{L.get('units', 0)} đơn vị quota).", ""]
    out.append("KÊNH ĐÃ ĐỌC: " + ("; ".join(L.get("channels") or []) or "-"))
    for raw, why in L.get("failed") or []:
        out.append(f"  ✗ không đọc được: {raw} — {why}")
    typ = int(L.get("typical_len_s") or 0)
    if typ:
        lo, hi = session_range_min(typ)
        out += ["", f"ĐỘ DÀI VIDEO ĐỐI THỦ: khoảng {typ / 60:.0f} phút (trung vị của {L.get('long_videos', 0)} video dài) "
                    f"→ mỗi phiên ngâm sẽ dài khoảng {lo}–{hi} phút."]
    else:
        out += ["", "ĐỘ DÀI VIDEO ĐỐI THỦ: chưa đủ video dài để tính — bot sẽ tự đo ở lần tìm đầu của phiên."]
    A = L.get("ai") or {}
    if A:
        out += ["", f"══ PHÂN TÍCH CỦA AI ({A.get('brain', 'AI')}) ══"]
        if A.get("description"):
            out += ["Niche này là: " + A["description"]]
        if A.get("note"):
            out += ["LƯU Ý: " + A["note"]]
        _st = [x for x in (A.get("stances") or []) if isinstance(x, dict) and (x.get("stance") or x.get("verdict"))]
        if _st:
            out += ["", "CHÍNH KIẾN CỦA TỪNG AI (ý kiến riêng, có thể KHÁC nhau — bạn là người quyết):" if len(_st) > 1
                    else "CHÍNH KIẾN CỦA AI:"]
            for x in _st:
                out += [f"  ■ {x.get('ai', 'AI')}" + (f" ({x['model']})" if x.get("model") else "") + ":"]
                if x.get("verdict"):
                    out += ["    Sau khi tranh luận: " + x["verdict"]]
                    if x.get("stance"):
                        out += ["    Ban đầu: " + x["stance"]]
                else:
                    out += ["    " + x.get("stance", "")]
        out += topic_report(A, L.get("thumbs") or {})
        _agree = (A.get("agreed") or {}).get("keywords")
        out += ["", f"TỪ KHÓA ĐUÔI DÀI AI ĐỀ XUẤT ({len(A.get('keywords') or [])})"
                    + (f" — {_agree} từ khóa ĐẦU là cả 2 AI cùng chọn:" if _agree else ":")]
        out += [f"  • {k}" for k in (A.get("keywords") or [])] or ["  (không có từ khóa mới)"]
        out += ["", f"TAG NÊN DÙNG ({len(A.get('tags') or [])}) — bấm 'Chép tag' để dán vào YouTube:",
                "  " + (", ".join(A.get("tags") or []) or "-")]
        out += ["", "TỪ LOẠI TRỪ AI ĐỀ XUẤT: " + ("; ".join(A.get("negative") or []) or "-")]
        if A.get("title_patterns"):
            out += ["", "CÔNG THỨC TIÊU ĐỀ CỦA VIDEO ĐANG LÊN:"] + [f"  • {t}" for t in A["title_patterns"]]
        if A.get("notes"):
            out += ["", "NHẬN XÉT CHO KÊNH MỚI VÀO NICHE:", "  " + A["notes"].replace("\n", "\n  ")]
        if A.get("review"):
            out += ["", "HAI AI NHẬN XÉT CHÉO BÀI CỦA NHAU:", "  " + A["review"].replace("\n", "\n  ")]
        out += ["", "══ SỐ LIỆU THỐNG KÊ ══"]
    else:
        out += ["", "(Chưa có phân tích của AI — chọn AI ở ô 'AI phân tích' rồi bấm 'Học niche từ kênh đối thủ'.)"]
    out += ["", f"TỪ VỰNG ĐẶC TRƯNG ({len(L.get('terms') or [])}) — bot dùng để nhận thêm video đúng niche:",
            "  " + (", ".join(L.get("terms") or []) or "(chưa đủ dữ liệu)")]
    out += ["", "NGƯỜI XEM NICHE NÀY (AI đọc bình luận):",
            ("  " + (L.get("audience") or "").replace("\n", "\n  ")) if L.get("audience")
            else "  (chưa có — cần chọn AI Brain hoặc có API key AI để tóm tắt bình luận)"]
    out += ["", f"TỪ KHÓA GỢI Ý ({len(L.get('suggest') or [])}) — bấm 'Thêm từ khóa gợi ý' nếu muốn dùng:"]
    out += [f"  • {k}" for k in (L.get("suggest") or [])] or ["  (không có tag lặp lại đủ nhiều)"]
    if L.get("tags"):
        out += ["", f"TAG ĐỐI THỦ HAY GẮN NHẤT (thống kê, {len(L['tags'])}):", "  " + ", ".join(L["tags"])]
    out += ["", "VIDEO ĐANG LÊN CỦA ĐỐI THỦ:"]
    out += [f"  • {t}" for t in (L.get("top_titles") or [])] or ["  -"]
    return "\n".join(out)
