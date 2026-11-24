# -*- coding: utf-8 -*-
"""
Smoke test v1.9.4 — KHUNG NHẬP YOUTUBE API KEY + HỌC NICHE TỪ KÊNH ĐỐI THỦ (workflow/niche_learner.py).

Chạy:  python test_v194.py
Cô lập: GPM_BOT_DATA_DIR + GPM_BOT_ENV_FILE -> temp (KHÔNG đụng data/.env thật; hash trước == sau).
KHÔNG gọi mạng: mọi lệnh YouTube Data API đi qua HTTP giả.

Phủ:
  [1] Hàm thuần: parse_channel_ref, iso_duration_s, extract_terms, suggest_keywords, _parse_term_list, explain_error
  [2] YouTubeAPI: xoay key khi hết quota, key sai, test_key, không lộ key trong lỗi
  [3] learn_niche trên dữ liệu giả: handle / id / tên (search), kênh lỗi, video tắt bình luận, có & không có AI
  [4] channel_mode: normalize_niche nhận learned, niche_score cộng từ vựng đã học (1 từ lẻ chưa đủ ngưỡng),
      câu hỏi AI có thêm từ vựng + ghi chú người xem
  [5] UI: khung key (lưu vào .env tạm, che key, không hiện lại), Kiểm tra key, Học niche -> lưu learned,
      sửa niche không mất learned, cửa sổ kết quả + thêm từ khóa gợi ý
  [6] Tĩnh: api_vault biết YOUTUBE_API_KEY; module chỉ có lệnh GET
"""
import hashlib
import json
import os
import sys
import tempfile
import time
import tkinter as tk
from tkinter import ttk

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
for p in (REPO, HERE):
    if p not in sys.path:
        sys.path.insert(0, p)
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

TMP = tempfile.mkdtemp(prefix="gpm_v194_")
DATA_DIR = os.path.join(TMP, "data")
os.makedirs(DATA_DIR, exist_ok=True)
ENV_FILE = os.path.join(TMP, ".env")
open(ENV_FILE, "w", encoding="utf-8").write("")
REAL_DB = os.path.join(REPO, "data", "agent_logs.db")
REAL_CFG = os.path.join(REPO, "data", "app_config.json")
REAL_ENV = os.path.join(REPO, ".env")


def _hash(path):
    try:
        return hashlib.sha256(open(path, "rb").read()).hexdigest()
    except Exception:
        return None


BEFORE = {p: _hash(p) for p in (REAL_DB, REAL_CFG, REAL_ENV)}
os.environ["GPM_BOT_DATA_DIR"] = DATA_DIR
os.environ["GPM_BOT_ENV_FILE"] = ENV_FILE
os.environ.pop("YOUTUBE_API_KEY", None)

from src.workflow import channel_mode as cm  # noqa: E402
from src.workflow import niche_learner as nl  # noqa: E402
from src import api_vault  # noqa: E402
from src import app_config  # noqa: E402
from src import ui_main as ui  # noqa: E402

# brain_manager gọi load_dotenv() lúc import -> key YouTube trong .env THẬT lọt vào os.environ của tiến trình test.
for _k in [k for k in os.environ if k.startswith("YOUTUBE_API_KEY")]:
    os.environ.pop(_k, None)

PASS = FAIL = 0


def check(name, cond, extra=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  [PASS] {name}")
    else:
        FAIL += 1
        print(f"  [FAIL] {name} {extra}")


# ---------------------------------------------------------------- dữ liệu giả
UC_A, UC_B, UC_C = "UC" + "a" * 22, "UC" + "b" * 22, "UC" + "c" * 22
NOW = 1795000000.0


def _vid(vid, title, tags, views, hours_ago, dur="PT12M5S", comments=50):
    pub = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(NOW - hours_ago * 3600))
    return {"id": vid, "snippet": {"title": title, "tags": tags, "publishedAt": pub},
            "statistics": {"viewCount": str(views), "commentCount": str(comments)},
            "contentDetails": {"duration": dur}}


CHANNELS = {
    UC_A: {"title": "Ocean Lab", "handle": "@oceanlab", "videos": [
        _vid("a1", "Anglerfish hunting in the Mariana trench", ["deep sea creatures", "anglerfish", "mariana trench"], 900000, 48),
        _vid("a2", "Bioluminescent squid filmed at 3000m", ["deep sea creatures", "bioluminescent animals"], 400000, 100),
        _vid("a3", "The hadal zone: life under crushing pressure", ["hadal zone", "deep sea creatures"], 250000, 300),
        _vid("a4", "Giant isopod feeding frenzy", ["giant isopod", "deep sea creatures"], 120000, 30),
        _vid("a5", "Ocean Lab Q&A #shorts", ["ocean lab"], 5000, 10, dur="PT45S", comments=0),
    ]},
    UC_B: {"title": "Abyss Explorers", "handle": "@abyss", "videos": [
        _vid("b1", "Anglerfish mating is horrifying", ["anglerfish", "bioluminescent animals"], 700000, 72),
        _vid("b2", "Hadal trench submersible dive, full expedition", ["hadal zone", "submersible dive"], 300000, 200),
        _vid("b3", "Bioluminescent jellyfish swarm", ["bioluminescent animals", "submersible dive"], 90000, 20),
        _vid("b4", "Isopod vs squid: who wins?", ["giant isopod"], 60000, 500),
    ]},
    UC_C: {"title": "Trench Diaries", "handle": "", "videos": [
        _vid("c1", "Submersible pilots explain the hadal descent", ["submersible dive", "hadal zone"], 150000, 60),
        _vid("c2", "Squid, isopod and anglerfish in one dive", ["deep sea creatures"], 80000, 90),
        _vid("c3", "Bioluminescent bacteria and the anglerfish lure", ["anglerfish"], 40000, 400),
    ]},
}
COMMENTS = {"a1": [("The anglerfish footage is unreal, more trench dives please!", 900), ("first", 1),
                   ("How deep can the submersible go before the hull fails?", 300)],
            "b1": [("I love the calm narration and the real footage, no clickbait", 500)]}
CALLS = []


def _ch_item(cid):
    c = CHANNELS[cid]
    return {"id": cid, "snippet": {"title": c["title"]},
            "contentDetails": {"relatedPlaylists": {"uploads": "UU" + cid[2:]}},
            "statistics": {"subscriberCount": "12000", "videoCount": str(len(c["videos"]))}}


def fake_http(path, params):
    key = str(params.get("key") or "")
    key = "BADKEY" if key.startswith("BADKEY") else "QUOTA" if key.startswith("QUOTA") else key
    CALLS.append((path, {k: v for k, v in params.items() if k != "key"}, key))
    if key == "BADKEY":
        return 400, {"error": {"code": 400, "message": "API key not valid. Please pass a valid API key.",
                               "errors": [{"reason": "badRequest"}]}}
    if key == "QUOTA":
        return 403, {"error": {"code": 403, "message": "The request cannot be completed because you have exceeded your quota.",
                               "errors": [{"reason": "quotaExceeded"}]}}
    if key == "OFFLINE":
        return 0, {"error": {"message": "URLError: no route"}}
    if path == "channels":
        if params.get("id") in CHANNELS:
            return 200, {"items": [_ch_item(params["id"])]}
        h = (params.get("forHandle") or "").lower()
        for cid, c in CHANNELS.items():
            if c["handle"] and c["handle"] == h:
                return 200, {"items": [_ch_item(cid)]}
        return 200, {"items": []}
    if path == "search":
        if "trench" in (params.get("q") or "").lower():
            return 200, {"items": [{"id": {"channelId": UC_C}, "snippet": {"channelId": UC_C}}]}
        return 200, {"items": []}
    if path == "playlistItems":
        cid = "UC" + params["playlistId"][2:]
        return 200, {"items": [{"contentDetails": {"videoId": v["id"]}} for v in CHANNELS[cid]["videos"]]}
    if path == "videos":
        if params.get("chart") == "mostPopular":
            return 200, {"items": [{"id": "x"}]}
        ids = params["id"].split(",")
        return 200, {"items": [v for c in CHANNELS.values() for v in c["videos"] if v["id"] in ids]}
    if path == "commentThreads":
        vid = params["videoId"]
        if vid == "b2":
            return 403, {"error": {"code": 403, "message": "The video has disabled comments.",
                                   "errors": [{"reason": "commentsDisabled"}]}}
        return 200, {"items": [{"snippet": {"topLevelComment": {"snippet": {"textDisplay": t, "likeCount": n}}}}
                               for t, n in COMMENTS.get(vid, [])]}
    return 404, {"error": {"message": "unknown path"}}


ANALYSIS = ('```json\n{"description": "Deep-sea documentaries about creatures of the hadal zone for curious adults.", '
            '"keywords": ["Deep Sea Creatures Documentary", "anglerfish hunting footage", "ocean lab best dives", "x", '
            '"hadal zone submersible dive full", "bioluminescent animals explained", "deep sea creatures"], '
            '"tags": ["Deep Sea", "anglerfish", "hadal zone", "#ocean documentary"], '
            '"negative": ["Minecraft", "kids", "aquarium tour"], '
            '"vocabulary": ["anglerfish", "bioluminescent", "hadal", "xyzzy", "isopod", "submersible", "squid", "ocean"], '
            '"title_patterns": ["The [Creature]: [shocking fact]"], '
            '"audience_vi": ["Người mê sinh vật biển sâu", "Hay hỏi tàu lặn xuống được bao sâu"], '
            '"notes_vi": ["Video 10-15 phút", "Mở đầu bằng cảnh quay thật"}')     # co y THIEU dau ] nhu Claude that 23/11


class FakeBrain:
    def __init__(self, fail=False, analysis=None):
        self.prompts, self.fail, self.analysis = [], fail, analysis

    def ask_text(self, prompt):
        self.prompts.append(prompt)
        if self.fail:
            raise RuntimeError("boom")
        if self.analysis and "Return only the JSON object" in prompt:
            return self.analysis
        if "LIVE DEBATE" in prompt:
            return "Toi phan doi.\nTRẠNG THÁI: ĐÃ CHỐT"
        if "Candidate vocabulary" in prompt:
            return "anglerfish, bioluminescent, hadal, isopod, squid, submersible, khong-co-trong-danh-sach"
        if "viewer comments" in prompt:
            return "- Thích cảnh quay thật dưới rãnh sâu\n- Hay hỏi tàu lặn xuống được bao sâu\n"
        return "OK"


NICHE = {"name": "Deep sea", "description": "Ocean trench documentaries",
         "keywords": ["mariana trench documentary", "deep sea creatures"],
         "channels": ["https://www.youtube.com/@OceanLab/videos", UC_B, "https://www.youtube.com/c/TrenchDiaries",
                      "@khongtontai", "@oceanlab"],
         "negative": ["minecraft"], "groups": [], "sync_locale": True}

# ---------------------------------------------------------------- [1]
print("\n[1] Ham thuan")
for raw, want in [("https://www.youtube.com/@BBCNews/videos", ("handle", "BBCNews")), ("@abc", ("handle", "abc")),
                  ("https://youtube.com/channel/" + UC_A, ("id", UC_A)), (UC_B, ("id", UC_B)),
                  ("https://www.youtube.com/user/natgeo", ("user", "natgeo")),
                  ("https://www.youtube.com/c/TrenchDiaries", ("name", "TrenchDiaries")),
                  ("Trench Diaries", ("name", "Trench Diaries")), ("", ("", "")),
                  ("https://www.youtube.com/@K%C3%AAnh", ("handle", "Kênh"))]:
    check(f"parse_channel_ref({raw[:40]!r}) = {want}", nl.parse_channel_ref(raw) == want, str(nl.parse_channel_ref(raw)))
for raw, want in [("PT12M5S", 725), ("PT1H2M3S", 3723), ("PT45S", 45), ("P1DT1S", 86401), ("", 0), ("abc", 0)]:
    check(f"iso_duration_s({raw!r}) = {want}", nl.iso_duration_s(raw) == want)
vids = [{"title": v["snippet"]["title"], "tags": v["snippet"]["tags"], "channel_id": cid, "channel": c["title"]}
        for cid, c in CHANNELS.items() for v in c["videos"]]
terms = nl.extract_terms(vids, known_tokens={"mariana", "trench", "deep", "sea", "creatures"},
                         channel_titles=[c["title"] for c in CHANNELS.values()])
check("extract_terms nhat tu vung chung cua nhieu kenh", {"anglerfish", "bioluminescent", "hadal", "isopod"} <= set(terms), str(terms))
check("extract_terms bo tu user da co + ten kenh + tu qua chung",
      not ({"trench", "mariana", "ocean", "abyss", "full", "shorts", "life"} & set(terms)), str(terms))
check("extract_terms: tu chi co o 1 kenh bi loai khi hoc >= 2 kenh", "frenzy" not in terms and "mating" not in terms)
one = [dict(v, channel_id="X") for v in vids]
check("extract_terms: hoc 1 kenh thi khong doi >= 2 kenh", "anglerfish" in nl.extract_terms(one))
check("extract_terms rong -> []", nl.extract_terms([]) == [])
sg = nl.suggest_keywords(vids, existing=["Deep Sea Creatures"])
check("suggest_keywords: tag 2-5 tu lap >= 2 video, bo cum da co",
      sg[:3] == ["bioluminescent animals", "submersible dive", "hadal zone"] or
      set(sg) == {"bioluminescent animals", "submersible dive", "hadal zone", "giant isopod"}, str(sg))
check("suggest_keywords bo tag 1 tu + cum da co", "anglerfish" not in sg and "deep sea creatures" not in sg)
check("_parse_term_list chi giu tu trong danh sach", nl._parse_term_list("1. Hadal, squid; xyz\n- isopod", ["squid", "hadal", "isopod", "abc"])
      == ["squid", "hadal", "isopod"])
check("explain_error key sai", "KEY SAI" in nl.explain_error(*fake_http("videos", {"key": "BADKEY"})))
check("explain_error het quota", "HẾT QUOTA" in nl.explain_error(*fake_http("videos", {"key": "QUOTA"})))
check("explain_error mat mang", "không kết nối" in nl.explain_error(*fake_http("videos", {"key": "OFFLINE"})))
check("explain_error chua bat API", "CHƯA BẬT" in nl.explain_error(403, {"error": {"message": "YouTube Data API v3 has not been used in project 1 before or it is disabled.", "errors": [{"reason": "accessNotConfigured"}]}}))

ks, bad = nl.split_keys(' AIzaSyA_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa1,\n"AIzaSyB-bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb2";AIzaSyA_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa1 oops ')
check("split_keys: tach theo , ; khoang trang xuong dong, bo nhay + trung, dem doan hong", len(ks) == 2 and bad == 1 and ks[0].endswith("a1"))
check("split_keys rong", nl.split_keys("") == ([], 0) and nl.split_keys(None) == ([], 0))
check("short_mask khong lo key", nl.short_mask("AIzaSyA_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa1") == "AIza…aaa1" and nl.short_mask("abc") == "••••")
tk3 = nl.test_keys(["GOOD", "QUOTA", "BADKEY"], fake_http)
check("test_keys thu tung key", [r[1] for r in tk3] == [True, False, False] and nl.is_invalid_reason(tk3[2][2])
      and not nl.is_invalid_reason(tk3[1][2]))

# ---------------------------------------------------------------- [2]
print("\n[2] YouTubeAPI")
check("test_key key tot", nl.test_key("GOOD", fake_http)[0] is True)
ok, why = nl.test_key("BADKEY", fake_http)
check("test_key key sai -> False + ly do, khong lo key", ok is False and "KEY SAI" in why and "BADKEY" not in why)
check("test_key rong", nl.test_key("  ", fake_http) == (False, "chưa nhập key"))
api = nl.YouTubeAPI(["QUOTA", "GOOD"], fake_http)
r = api.get("videos", {"part": "id", "chart": "mostPopular"})
check("het quota key 1 -> tu xoay sang key 2", r.get("items") and api._i == 1)
try:
    nl.YouTubeAPI(["QUOTA"], fake_http).get("videos", {"chart": "mostPopular"})
    check("1 key het quota -> LearnError", False)
except nl.LearnError as e:
    check("1 key het quota -> LearnError", "HẾT QUOTA" in str(e))
try:
    nl.YouTubeAPI([], fake_http).get("videos", {})
    check("khong co key -> LearnError", False)
except nl.LearnError as e:
    check("khong co key -> LearnError", "chưa có" in str(e))

# ---------------------------------------------------------------- [3]
print("\n[3] learn_niche")
CALLS.clear()
logs = []
brain = FakeBrain()
L = nl.learn_niche(NICHE, ["GOOD"], brain=brain, log=logs.append, http=fake_http, now=NOW)
check("doc du 3 kenh (handle / id / ten qua search), bo kenh trung", L["channels"] == ["Ocean Lab", "Abyss Explorers", "Trench Diaries"], str(L["channels"]))
check("kenh khong ton tai duoc ghi vao failed, khong lam hong ca lan hoc",
      [f[0] for f in L["failed"]] == ["@khongtontai"] and "không tìm thấy" in L["failed"][0][1], str(L["failed"]))
check("dem video + binh luan", L["videos"] == 12 and L["comments"] == 3, f"{L['videos']} / {L['comments']}")
check("AI loc tu vung (chi giu tu co trong danh sach)", set(L["terms"]) == {"anglerfish", "bioluminescent", "hadal", "isopod", "squid", "submersible"}, str(L["terms"]))
check("AI tra loi khong phai JSON -> roi ve cach cu (1 luot phan tich hong + 2 luot loc/tom tat)",
      "tàu lặn" in L["audience"] and len(brain.prompts) == 3 and L["ai"] == {} and "TOP RECENT VIDEOS" in brain.prompts[0])
check("binh luan qua ngan ('first') bi bo, khong dua cho AI", "- first" not in brain.prompts[2] and "anglerfish footage" in brain.prompts[2])

print("    -- v1.10.0: AI phan tich niche")
check("parse_json_obj: JSON chuan / co ```json / thieu ngoac / bi cat / phay thua / khong phai JSON",
      nl.parse_json_obj('{"a": [1, 2]}') == {"a": [1, 2]} and nl.parse_json_obj('```json\n{"a": 1}\n```') == {"a": 1}
      and nl.parse_json_obj('{"a": [1, 2}') == {"a": [1, 2]} and nl.parse_json_obj('{"a": {"b": ["x", "y"') == {"a": {"b": ["x", "y"]}}
      and nl.parse_json_obj('{"a": "co ] va } trong chuoi", "b": [1,],}') == {"a": "co ] va } trong chuoi", "b": [1]}
      and nl.parse_json_obj("xin chao") is None and nl.parse_json_obj("") is None and nl.parse_json_obj("[1, 2]") is None)
tt = nl.top_tags(vids)
check("top_tags: tag hay gan nhat dung dau, kem so video", tt[0] == ("deep sea creatures", 5) and ("anglerfish", 3) in tt
      and all(n >= 2 for _t, n in tt), str(tt[:4]))
ab = FakeBrain(analysis=ANALYSIS)
LA = nl.learn_niche(NICHE, ["GOOD"], brain=ab, brain_name="claude-sonnet", http=fake_http, now=NOW)
A = LA["ai"]
check("AI phan tich: 1 luot hoi duy nhat, cau tra loi thieu ngoac van doc duoc", len(ab.prompts) == 1 and A.get("brain") == "claude-sonnet")
check("tu khoa AI trung nguyen van tu khoa user da co thi bo", "deep sea creatures" not in A["keywords"])
check("tu khoa AI: chu thuong, bo cum 1 tu, bo cum chua ten kenh, bo tu khoa user da co",
      A["keywords"] == ["deep sea creatures documentary", "anglerfish hunting footage", "hadal zone submersible dive full",
                        "bioluminescent animals explained"], str(A["keywords"]))
check("tag / tu loai tru duoc lam sach", A["tags"] == ["deep sea", "anglerfish", "hadal zone", "ocean documentary"]
      and A["negative"] == ["minecraft", "kids", "aquarium tour"], f"{A['tags']} {A['negative']}")
check("tu vung AI chi nhan tu CO THAT trong tieu de/tag (bo 'xyzzy'), bo tu ten kenh ('ocean')",
      LA["terms"] == ["anglerfish", "bioluminescent", "hadal", "isopod", "submersible", "squid"], str(LA["terms"]))
check("nguoi xem + nhan xet (tieng Viet) duoc gop thanh gach dau dong", LA["audience"].startswith("- Người mê sinh vật biển sâu")
      and "- Video 10-15 phút" in A["notes"] and A["title_patterns"] == ["The [Creature]: [shocking fact]"])
LN = nl.learn_niche(NICHE, ["GOOD"], brain=None, http=fake_http, now=NOW)
check("learned co tag thong ke ke ca khi khong co AI", LN["tags"][:1] == ["deep sea creatures"] and LN["ai"] == {})
repA = nl.format_report(LA)
check("bao cao co muc PHAN TICH CUA AI day du", all(x in repA for x in (
    "PHÂN TÍCH CỦA AI (claude-sonnet)", "TỪ KHÓA ĐUÔI DÀI AI ĐỀ XUẤT (4)", "TAG NÊN DÙNG (4)", "TỪ LOẠI TRỪ AI ĐỀ XUẤT: minecraft",
    "CÔNG THỨC TIÊU ĐỀ", "NHẬN XÉT CHO KÊNH MỚI", "TAG ĐỐI THỦ HAY GẮN NHẤT")))
check("bao cao khi chua co AI nhac chon AI", "Chưa có phân tích của AI" in nl.format_report(LN))


class ChatBrain:
    def __init__(self):
        self.calls = []

    def ask_chat(self, system, user, timeout=60, temperature=0.2):
        self.calls.append((system, timeout))
        return ANALYSIS

    def ask_text(self, prompt):
        raise AssertionError("phai dung ask_chat")


cb = ChatBrain()
LC = nl.learn_niche(NICHE, ["GOOD"], brain=cb, http=fake_http, now=NOW)

print("    -- v1.11.0: 2 AI song song + doi chieu cheo")
A1 = {"description": "D1", "keywords": ["anglerfish hunting footage", "deep sea creatures documentary", "hadal zone dive",
                                        "giant squid 2024 footage"],
      "tags": ["deep sea", "anglerfish"], "negative": ["minecraft"], "vocabulary": ["anglerfish", "hadal"],
      "title_patterns": ["P1"], "audience_vi": ["khan gia 1"], "notes_vi": ["nhan xet 1"]}
A2 = {"description": "D2", "keywords": ["hadal zone dive full expedition", "bioluminescent animals explained",
                                        "anglerfish hunting footage"],
      "tags": ["anglerfish", "hadal zone"], "negative": ["kids", "minecraft"], "vocabulary": ["isopod", "anglerfish"],
      "title_patterns": ["P2"], "audience_vi": ["khan gia 2"], "notes_vi": ["nhan xet 2"]}
F1 = dict(A1, keywords=A1["keywords"] + ["bioluminescent animals explained"], review_vi=["Ben kia dung o tu khoa bioluminescent"])
F2 = dict(A2, review_vi=["Toi van khong dong y ve 'giant squid'"])


class XBrain:
    """Brain gia co ask_chat: vong 1 tra r1, vong 2 (cau hoi co 'SECOND ANALYST') tra r2. r la Exception -> nem loi."""
    def __init__(self, r1, r2=None):
        self.r1, self.r2, self.users, self.last_error = r1, r2, [], ""

    def ask_chat(self, system, user, timeout=60, temperature=0.2):
        self.users.append(user)
        r = self.r2 if "SECOND ANALYST" in user else self.r1
        if isinstance(r, Exception):
            raise r
        return r if isinstance(r, str) else json.dumps(r, ensure_ascii=False)


CH = [c["title"] for c in CHANNELS.values()]
x1, x2 = XBrain(A1, F1), XBrain(A2, F2)
xl = []
R = nl.ai_cross_analyze([("claude-sonnet", x1), ("openai", x2)], NICHE, CH, vids, [], log=xl.append)
check("2 AI: moi AI hoi 2 luot (phan tich + doc cheo), vong 2 co bai cua AI kia", len(x1.users) == 2 and len(x2.users) == 2
      and "bioluminescent animals explained" in x1.users[1] and "giant squid" in x2.users[1] and "TOP VIEWER COMMENTS" in x1.users[0])
check("gop tu khoa: muc CA HAI cung chon dung dau, bo cum co nam, bo bien the keo dai",
      R["keywords"] == ["anglerfish hunting footage", "bioluminescent animals explained", "deep sea creatures documentary",
                        "hadal zone dive full expedition"] and R["agreed"]["keywords"] == 2, f"{R['keywords']} {R['agreed']}")
check("gop tag / tu loai tru (trung dung dau)", R["tags"] == ["anglerfish", "deep sea", "hadal zone"] and R["agreed"]["tags"] == 1
      and R["negative"] == ["minecraft", "kids"], f"{R['tags']} {R['negative']}")
check("nhan AI + nhan xet cheo cua ca 2", R["brain"] == "claude-sonnet + openai (đối chiếu chéo)"
      and "claude-sonnet nhận xét:" in R["review"] and "openai nhận xét:" in R["review"] and "giant squid" in R["review"] and R["note"] == "")
check("bao tung AI tra loi xong luc nao (ca 2 vong)", len([m for m in xl if "đã trả lời vòng 1 sau" in m]) == 2
      and len([m for m in xl if "đã trả lời vòng 2 sau" in m]) == 2 and any(m.startswith("… openai đã trả lời vòng 2 sau") for m in xl), str(xl))
check("log tung vong", any("✓ claude-sonnet phân tích xong" in m for m in xl) and any("đọc chéo" in m for m in xl)
      and any("Hai AI đối chiếu xong" in m for m in xl))
dead = XBrain(RuntimeError("Error code: 429 - {'code': 'credit_balance_exhausted', 'message': 'You have no credits remaining'}"))
R1 = nl.ai_cross_analyze([("claude-sonnet", XBrain(A1, F1)), ("openai", dead)], NICHE, CH, vids, [])
check("1 AI het credit -> AI con lai phan tich mot minh + ghi ro ly do", R1["brain"] == "claude-sonnet" and "openai không dùng được: HẾT CREDIT" in R1["note"]
      and R1["keywords"][0] == "anglerfish hunting footage" and len(dead.users) == 1, R1.get("note"))
x3 = XBrain(A2, "xin loi toi khong tra loi duoc")
R2 = nl.ai_cross_analyze([("claude-sonnet", XBrain(A1, F1)), ("openai", x3)], NICHE, CH, vids, [])
check("vong 2 cua 1 AI hong -> dung ban vong 1 cua no + ghi chu", "openai không viết được bản đối chiếu" in R2["note"]
      and "hadal zone dive full expedition" in R2["keywords"] and "claude-sonnet nhận xét:" in R2["review"] and "openai nhận xét" not in R2["review"])
DG = R["dialog"]
check("doi thoai: 4 luot (2 AI x 2 vong), ghi ro ai noi voi ai", [(t["round"], t["ai"], t["other"]) for t in DG]
      == [(1, "claude-sonnet", "openai"), (1, "openai", "claude-sonnet"), (2, "claude-sonnet", "openai"), (2, "openai", "claude-sonnet")])
check("doi thoai vong 1: bai rieng cua tung AI (da lam sach: bo cum co nam)", DG[0]["keywords"] == A1["keywords"][:3]
      and DG[1]["keywords"] == A2["keywords"] and DG[0]["description"] == "D1" and "khan gia 2" in DG[1]["audience"])
check("doi thoai vong 2: nhan xet + lay them gi tu bai kia / bo gi", DG[2]["taken"] == ["bioluminescent animals explained"]
      and DG[2]["added"] == [] and DG[2]["dropped"] == [] and "Ben kia dung" in DG[2]["review"]
      and DG[3]["taken"] == [] and DG[3]["dropped"] == [] and "giant squid" in DG[3]["review"], str(DG[2]))
FD = nl.format_dialog({"at": "2026-11-23 20:00", "ai": R})
check("format_dialog (ban chep): du 4 luot noi + loi dan + ket qua gop", all(x in FD for x in (
    "ĐỐI THOẠI GIỮA 2 AI — claude-sonnet và openai", "■ claude-sonnet — Vòng 1 · phân tích riêng", "■ openai — Vòng 1 · phân tích riêng",
    "Theo tôi, niche này là: D1", "Tôi đề xuất 3 từ khóa:", "■ claude-sonnet — Vòng 2 · trả lời openai",
    "Gửi openai: tôi đã đọc bài của bạn.", "Tôi lấy thêm 1 từ khóa từ bài của bạn:", "   • bioluminescent animals explained",
    "■ openai — Vòng 2 · trả lời claude-sonnet", "Tôi giữ nguyên bộ từ khóa của mình.", "cả hai cùng chọn 2 từ khóa và 1 tag")), FD[:300])
MS = nl.dialog_messages({"at": "x", "ai": R})
check("dialog_messages: loi dan - 4 luot (AI 1 ben 0, AI 2 ben 1) - ket qua gop", [m["side"] for m in MS] == [-1, 0, 1, 0, 1, -1]
      and [m["name"] for m in MS[1:5]] == ["claude-sonnet", "openai", "claude-sonnet", "openai"]
      and MS[3]["sub"] == "Vòng 2 · trả lời openai" and "Ben kia dung" in MS[3]["text"] and "Bot gộp 2 bản cuối" in MS[-1]["text"])


class MBrain(XBrain):
    model_name = "opus-x"


RM = nl.ai_cross_analyze([("A", MBrain(A1, F1)), ("B", XBrain(A2, F2))], NICHE, CH, vids, [])
check("luot noi ghi model cua brain (co thi hien, khong co thi bo)", [t["model"] for t in RM["dialog"]] == ["opus-x", "", "opus-x", ""]
      and "■ A (opus-x) — Vòng 1 · phân tích riêng" in nl.format_dialog({"ai": RM}) and "■ B — Vòng 1" in nl.format_dialog({"ai": RM}))


class DBrain:
    """Brain gia cho TRANH LUAN: JSON cho phan tich / ban chot, van ban cho luot tranh luan (ghi lai moi cau hoi).
    close_after = so luot noi cua RIENG brain nay trong 1 chu de truoc khi no bao 'ĐÃ CHỐT' (None = khong bao gio chot)."""
    def __init__(self, name, r1, r2, fail_at=None, close_after=None):
        self.name, self.r1, self.r2, self.fail_at, self.users, self.systems = name, r1, r2, fail_at, [], []
        self.last_error, self.n_deb, self.close_after, self.per_topic, self.images = "", 0, close_after, {}, []

    def ask_chat(self, system, user, timeout=60, temperature=0.2, images=None):
        self.users.append(user)
        self.systems.append(system)
        self.images.append(images)
        self.last_error = ""
        if user.startswith("LIVE DEBATE"):
            self.n_deb += 1
            if self.fail_at == self.n_deb:
                self.last_error = "Claude usage limit reached"
                return ""
            topic = user.split("CURRENT TOPIC (")[1].split(" of ")[0]
            n = self.per_topic[topic] = self.per_topic.get(topic, 0) + 1
            st = "ĐÃ CHỐT" if (self.close_after is not None and n > self.close_after) else "CÒN TRANH LUẬN"
            return (f"```\n{self.name} noi lan {self.n_deb}: toi phan doi.\n\nChính kiến của tôi: {self.name} giu y {topic}.\n"
                    f"TRẠNG THÁI: {st}\n```")
        return json.dumps(self.r2 if "SECOND ANALYST" in user else self.r1, ensure_ascii=False)


class IBrain(DBrain):
    supports_images = True


print("    -- v1.16.0: tranh luan TOI CUNG theo 4 chu de")
T4 = [t[1] for t in nl.DEBATE_TOPICS]
check("4 chu de dung thu tu: danh gia niche -> dac diem -> goi SEO -> thumbnail",
      T4 == ["ĐÁNH GIÁ NICHE", "ĐẶC ĐIỂM NICHE", "GÓI SEO", "THUMBNAIL"] and [t[0] for t in nl.DEBATE_TOPICS] == ["niche", "traits", "seo", "thumb"])
check("split_status: doc dong trang thai cuoi loi noi (co/khong dau, in dam, co giai thich), bo dong do khoi loi",
      nl.split_status("a\nb\nTRẠNG THÁI: ĐÃ CHỐT") == ("a\nb", True)
      and nl.split_status("a\nTRẠNG THÁI: CÒN TRANH LUẬN") == ("a", False)
      and nl.split_status("a\n**Trạng thái: đã chốt** (giữ bất đồng)") == ("a", True)
      and nl.split_status("a\nTRANG THAI: DA CHOT") == ("a", True)
      and nl.split_status("a\nTRẠNG THÁI: CHƯA CHỐT") == ("a", False)
      and nl.split_status("khong co dong trang thai") == ("khong co dong trang thai", False)
      and nl.split_status("") == ("", False))
EV, dlog = [], []
da, dbb = DBrain("A", A1, F1, close_after=1), DBrain("B", A2, F2, close_after=1)
RD = nl.ai_cross_analyze([("A", da), ("B", dbb)], NICHE, CH, vids, [], log=dlog.append, debate_rounds=5, on_event=EV.append)
DD = RD["dialog"]
DEB = [t for t in DD if t["kind"] == "debate"]
check("TOI CUNG: moi chu de noi toi khi CA HAI chot (4 luot / chu de), ben mo loi luan phien A, B, A, B",
      [t["kind"] for t in DD] == ["analysis"] * 2 + (["note"] + ["debate"] * 4 + ["note"]) * 4 + ["final"] * 2
      and [t["ai"] for t in DEB] == list("ABAB") + list("BABA") + list("ABAB") + list("BABA")
      and [t["topic"] for t in DEB[::4]] == ["niche", "traits", "seo", "thumb"] and [t["topic_title"] for t in DEB[::4]] == T4,
      str([(t["kind"], t.get("ai")) for t in DD]))
check("moi luot ghi: luot thu may cua chu de, vong, da chot chua; chu de dong khi ca 2 luot cuoi cung chot",
      [(t["n"], t["round"], t["closed"]) for t in DEB[:4]] == [(1, 1, False), (2, 1, False), (3, 2, True), (4, 2, True)]
      and DEB[0]["other"] == "B", str([(t["n"], t["round"], t["closed"]) for t in DEB[:4]]))
check("loi tranh luan la van ban sach (bo hang rao ```, bo dong TRANG THAI), dung loi dan tranh luan",
      DEB[0]["text"] == "A noi lan 1: toi phan doi.\nChính kiến của tôi: A giu y 1." and da.systems[1] == nl.DEBATE_SYSTEM
      and "IN VIETNAMESE" in nl.DEBATE_SYSTEM and da.systems[0] == nl.AI_SYSTEM, DEB[0]["text"])
check("cau hoi tung luot noi ro CHU DE dang ban", da.users[1].startswith("LIVE DEBATE - you are A; the other analyst is B.")
      and "CURRENT TOPIC (1 of 4): NICHE ASSESSMENT (ĐÁNH GIÁ NICHE)" in da.users[1] and "Turn 1 on this topic (at most 10)." in da.users[1]
      and "CURRENT TOPIC (3 of 4): SEO PACKAGE (GÓI SEO)" in da.users[5] and "CURRENT TOPIC (4 of 4): THUMBNAIL (THUMBNAIL)" in dbb.users[7])
check("luot mo chu de: chua ai noi; ben sau DOC DUOC loi + trang thai ben truoc; luot dau moi ben phai neu lai lap truong",
      "OPEN THIS TOPIC" in da.users[1] and "(nothing yet - you speak first)" in da.users[1] and "unchanged" in da.users[1]
      and "[A]: A noi lan 1: toi phan doi." in dbb.users[1] and "TRẠNG THÁI: CÒN TRANH LUẬN" in dbb.users[1]
      and "REPLY to the other analyst" in dbb.users[1] and "This is your first message on this topic" in dbb.users[1]
      and "[B]: B noi lan 1: toi phan doi." in da.users[2] and "This is your first message on this topic" not in da.users[2]
      and "THIS IS YOUR LAST TURN ON THIS TOPIC" not in da.users[2])
check("chu de sau: chi thay loi cua CHU DE NAY + lap truong da chot o chu de truoc (khong mo lai)",
      "POSITIONS ALREADY STATED ON THE EARLIER TOPICS" in dbb.users[3] and "[ĐÁNH GIÁ NICHE] [A]: Chính kiến của tôi: A giu y 1." in dbb.users[3]
      and "[ĐÁNH GIÁ NICHE] [B]: Chính kiến của tôi: B giu y 1." in dbb.users[3] and "A noi lan 1" not in dbb.users[3]
      and "(nothing yet - you speak first)" in dbb.users[3] and "POSITIONS ALREADY STATED" not in da.users[1])
check("cau hoi tranh luan co du lieu that + bai cua ca 2 ben ve chu de do", "SAMPLE OF THEIR TOP VIDEOS" in da.users[1]
      and "YOUR ANALYSIS ON THIS TOPIC AND YOUR STANCE (JSON)" in da.users[1] and "TOP VIEWER COMMENTS:" in da.users[1]
      and "THE OTHER ANALYST'S ANALYSIS ON THIS TOPIC AND STANCE (JSON)" in da.users[1] and '"description": "D2"' in da.users[1]
      and "hadal zone dive full expedition" not in da.users[1] and "hadal zone dive full expedition" in da.users[5]
      and "TOP VIEWER COMMENTS:" not in da.users[5])
check("lich tranh luan: 4 chu de deu 'da chot' sau 4 luot", RD["agenda"] == [
      {"key": k, "title": t, "turns": 4, "settled": True, "why": "settled"} for k, t in zip(["niche", "traits", "seo", "thumb"], T4)]
      and RD["debate_cap"] == 5, str(RD.get("agenda")))
_notes = [t["text"] for t in DD if t["kind"] == "note"]
check("loi dan cua bot giua cac chu de: mo chu de (ai mo loi) + bao da chot", len(_notes) == 8
      and _notes[0].startswith("▶ Chủ đề 1/4 — ĐÁNH GIÁ NICHE:") and _notes[0].endswith("A mở lời.")
      and _notes[1] == "✔ ĐÁNH GIÁ NICHE: hai bên đã chốt sau 4 lượt nói." and _notes[2].startswith("▶ Chủ đề 2/4 — ĐẶC ĐIỂM NICHE:")
      and _notes[2].endswith("B mở lời.") and _notes[6].startswith("▶ Chủ đề 4/4 — THUMBNAIL:"), str(_notes))
check("ban chot doc lai CA cuoc tranh luan (chia theo chu de) + biet minh la ai", "HERE IS THE DEBATE YOU TWO JUST HAD" in da.users[-1]
      and "== TOPIC: ĐÁNH GIÁ NICHE ==" in da.users[-1] and "== TOPIC: THUMBNAIL ==" in da.users[-1]
      and "[B]: B noi lan 8: toi phan doi." in da.users[-1] and "TRẠNG THÁI: ĐÃ CHỐT" in da.users[-1]
      and "In this transcript YOU are [A] and the second analyst is [B]." in da.users[-1]
      and "must be your position at the END of the debate on each topic" in da.users[-1]
      and "SECOND ANALYST" in da.users[-1] and da.users[-1].rstrip().endswith("Return only the JSON object.")
      and DD[-2]["after_debate"] is True and DD[-2]["taken"] == ["bioluminescent animals explained"] and len(da.users) == 10)
check("su kien de hien TRUC TIEP: start -> dang soan -> tung luot noi + loi dan (28), dung thu tu",
      EV[0] == {"ev": "start", "names": ["A", "B"], "debate_rounds": 5} and len([e for e in EV if e["ev"] == "turn"]) == 28
      and [e["turn"].get("ai") for e in EV if e["ev"] == "turn" and e["turn"]["kind"] == "debate"][:8] == list("ABABBABA")
      and any(e["ev"] == "typing" and e["who"] == ["B"] and e["what"] == "đang soạn lời về ĐÁNH GIÁ NICHE (lượt 2)" for e in EV)
      and any(e["ev"] == "typing" and e["what"] == "đang viết bản chốt" for e in EV), str([e["ev"] for e in EV]))
check("log: bao tung luot + da chot / con tranh luan", any("Tranh luận tới cùng: A và B bàn lần lượt 4 chủ đề" in m and "tối đa 5 vòng" in m for m in dlog)
      and len([m for m in dlog if "nói xong lượt" in m]) == 16 and len([m for m in dlog if "(đã chốt)" in m]) == 8
      and any("Chốt lại: A và B viết bản cuối sau khi tranh luận" in m for m in dlog))
MD = nl.dialog_messages({"at": "x", "ai": RD})
check("khung chat: loi dan noi ro 'tranh luan toi cung theo 4 chu de'; ten luot co chu de + trang thai",
      "TRANH LUẬN TỚI CÙNG theo 4 chủ đề: ĐÁNH GIÁ NICHE → ĐẶC ĐIỂM NICHE → GÓI SEO → THUMBNAIL" in MD[0]["text"]
      and "tối đa 5 vòng mỗi chủ đề" in MD[0]["text"] and "CHÍNH KIẾN" in MD[0]["text"]
      and [m["side"] for m in MD] == [-1, 0, 1] + [-1, 0, 1, 0, 1, -1] + [-1, 1, 0, 1, 0, -1] + [-1, 0, 1, 0, 1, -1] + [-1, 1, 0, 1, 0, -1] + [0, 1, -1]
      and MD[4]["sub"] == "ĐÁNH GIÁ NICHE · lượt 1 · gửi B · còn tranh luận" and MD[7]["sub"] == "ĐÁNH GIÁ NICHE · lượt 4 · gửi A · ĐÃ CHỐT"
      and MD[3]["text"].startswith("▶ Chủ đề 1/4") and MD[4]["text"].startswith("A noi lan 1: toi phan doi.")
      and MD[-3]["sub"] == "Chốt lại · gửi B" and MD[-3]["text"].startswith("Gửi B: sau khi tranh luận, tôi chốt lại như sau."),
      str([m["sub"] for m in MD]))
check("ban chep co loi dan chu de + cac luot tranh luan; dem luot noi khong tinh loi dan",
      "— ▶ Chủ đề 2/4 — ĐẶC ĐIỂM NICHE" in nl.format_dialog({"ai": RD})
      and "■ B — ĐẶC ĐIỂM NICHE · lượt 1 · gửi A · còn tranh luận\nB noi lan 3: toi phan doi." in nl.format_dialog({"ai": RD})
      and nl.spoken_turns(DD) == 20 and nl.spoken_turns(None) == 0)
# khong ben nao chot -> dung o so vong toi da
na, nb = DBrain("A", A1, F1), DBrain("B", A2, F2)
RN = nl.ai_cross_analyze([("A", na), ("B", nb)], NICHE, CH, vids, [], debate_rounds=1)
NDEB = [t for t in RN["dialog"] if t["kind"] == "debate"]
check("khong ben nao chot -> moi chu de dung o so vong TOI DA (1 vong = 2 luot), bao ro 'CHUA cung chot'",
      len(NDEB) == 8 and all(a["why"] == "cap" and a["turns"] == 2 and not a["settled"] for a in RN["agenda"])
      and any(t["kind"] == "note" and t["text"].startswith("⏹ GÓI SEO: hết 1 vòng mà hai bên CHƯA cùng chốt") for t in RN["dialog"])
      and "THIS IS YOUR LAST TURN ON THIS TOPIC" in na.users[1] and "Do not manufacture agreement" in nb.users[1], str(RN["agenda"]))
# A bao chot ngay tu loi mo -> khong tinh (chua ai dap); B khong chot -> chay het so vong
ea, eb = DBrain("A", A1, F1, close_after=0), DBrain("B", A2, F2)
RE_ = nl.ai_cross_analyze([("A", ea), ("B", eb)], NICHE, CH, vids, [], debate_rounds=2)
EDEB = [t for t in RE_["dialog"] if t["kind"] == "debate"]
check("loi MO chu de khong the 'da chot' (chua ai dap); 1 ben chot ma ben kia chua -> van tiep toi het vong",
      [(t["ai"], t["closed"]) for t in EDEB[:4]] == [("A", False), ("B", False), ("A", True), ("B", False)]
      and [(t["ai"], t["closed"]) for t in EDEB[4:8]] == [("B", False), ("A", True), ("B", False), ("A", True)]
      and all(a["why"] == "cap" and a["turns"] == 4 for a in RE_["agenda"]), str([(t["ai"], t["closed"]) for t in EDEB[:8]]))
dfa, dfb = DBrain("A", A1, F1), DBrain("B", A2, F2, fail_at=1)
RF = nl.ai_cross_analyze([("A", dfa), ("B", dfb)], NICHE, CH, vids, [], debate_rounds=2)
check("1 ben khong tra loi luc tranh luan -> dung tai do, van chot bai + ghi chu ro chu de / luot",
      [(t["kind"], bool(t.get("error"))) for t in RF["dialog"]] == [("analysis", False), ("analysis", False), ("note", False), ("debate", False),
                                                                    ("debate", True), ("final", False), ("final", False)]
      and "tranh luận dừng ở chủ đề 'ĐÁNH GIÁ NICHE', lượt 2: B không trả lời" in RF["note"] and "Cuộc đấu trí dừng ở đây" in nl.format_dialog({"ai": RF})
      and RF["keywords"] and "[A]: A noi lan 1" in dfa.users[-1]
      and [(a["why"], a["turns"]) for a in RF["agenda"]] == [("error", 1), ("error", 0), ("error", 0), ("error", 0)], RF["note"])
# nguoi dung bam 'chot luon' giua chung
sfa, sfb = DBrain("A", A1, F1), DBrain("B", A2, F2)
RSF = nl.ai_cross_analyze([("A", sfa), ("B", sfb)], NICHE, CH, vids, [], debate_rounds=5, should_finish=lambda: sfa.n_deb + sfb.n_deb >= 3)
check("should_finish (nut 'chot luon'): dung tranh luan ngay, cac chu de sau bo qua, van viet ban chot tu loi da noi",
      len([t for t in RSF["dialog"] if t["kind"] == "debate"]) == 3
      and [(a["why"], a["turns"]) for a in RSF["agenda"]] == [("stopped", 3), ("stopped", 0), ("stopped", 0), ("stopped", 0)]
      and RSF["dialog"][-3] == {"kind": "note", "text": "⏹ Bạn cho dừng tranh luận — hai AI viết bản chốt từ những gì đã nói."}
      and [t["kind"] for t in RSF["dialog"][-2:]] == ["final", "final"] and RSF["dialog"][-1]["after_debate"] is True
      and "[A]: A noi lan 2" in sfb.users[-1], str(RSF["agenda"]))
R9 = nl.ai_cross_analyze([("A", DBrain("A", A1, F1)), ("B", DBrain("B", A2, F2))], NICHE, CH, vids, [], debate_rounds=99)
Rx = nl.ai_cross_analyze([("A", DBrain("A", A1, F1)), ("B", DBrain("B", A2, F2))], NICHE, CH, vids, [], debate_rounds="sai")
check("so vong toi da bi chan 0..10; gia tri sai = 0 (khong tranh luan)", len([t for t in R9["dialog"] if t["kind"] == "debate"]) == 80
      and R9["debate_cap"] == 10 and [t["kind"] for t in Rx["dialog"]] == ["analysis", "analysis", "final", "final"]
      and Rx["agenda"] == [] and Rx["debate_cap"] == 0)
check("khong dau tri (mac dinh cua ham) -> y nhu cu: 4 luot, 'Vòng 2 · trả lời'", [t["kind"] for t in DG] == ["analysis", "analysis", "final", "final"]
      and DG[2]["after_debate"] is False and nl.turn_message(DG[2], 0)["sub"] == "Vòng 2 · trả lời openai")
LXD = nl.learn_niche(NICHE, ["GOOD"], brain=DBrain("A", A1, F1), brain_name="A", brain2=DBrain("B", A2, F2), brain2_name="B",
                     http=fake_http, now=NOW, debate_rounds=1)
check("learn_niche chuyen so vong toi da xuong + luu ca cuoc tranh luan, lich chu de", [t["kind"] for t in LXD["ai"]["dialog"]]
      == ["analysis", "analysis"] + ["note", "debate", "debate", "note"] * 4 + ["final", "final"]
      and len(LXD["ai"]["agenda"]) == 4 and LXD["ai"]["debate_cap"] == 1 and LXD["thumbs"] == {})
_old = {"ai": {"dialog": [{"kind": "analysis", "round": 1, "ai": "A", "description": "D"}, {"kind": "analysis", "round": 1, "ai": "B"},
                          {"kind": "debate", "round": 1, "ai": "A", "other": "B", "text": "x"}, {"kind": "debate", "round": 2, "ai": "B", "other": "A", "text": "y"},
                          {"kind": "final", "round": 2, "ai": "A", "other": "B", "after_debate": True}]}}
_om = nl.dialog_messages(_old)
check("ket qua luu tu ban cu (dau tri so vong co dinh, khong chu de) van xem lai duoc y nhu truoc",
      "ĐẤU TRÍ: lần lượt phản biện lập luận của nhau 2 vòng" in _om[0]["text"] and _om[3]["sub"] == "Phản biện 1 · gửi B"
      and _om[4]["sub"] == "Phản biện 2 · gửi A" and "■ B — Phản biện 2 · gửi A\ny" in nl.format_dialog(_old))
# v1.14.1: pick_ai = lay AI SAU khi doc xong kenh (UI kiem tra AI o luong nen trong luc doc kenh)
PA = {"http": 0, "at": None}


def _http_count(path, params):
    PA["http"] += 1
    return fake_http(path, params)


def _pick_after():
    PA["at"] = PA["http"]
    return {"brain": DBrain("A", A1, F1), "brain_name": "A", "brain2": DBrain("B", A2, F2), "brain2_name": "B", "ai_note": "ghi chu pick"}


LPA = nl.learn_niche(NICHE, ["GOOD"], brain=None, http=_http_count, now=NOW, debate_rounds=1, pick_ai=_pick_after)
check("pick_ai: goi SAU khi doc xong kenh, AI lay tu pick_ai (du brain truyen vao = None), ghi chu di theo",
      PA["at"] == PA["http"] and PA["http"] > 0 and LPA["ai"]["brain"] == "A + B (đối chiếu chéo)"
      and nl.spoken_turns(LPA["ai"]["dialog"]) == 12 and "ghi chu pick" in LPA["ai"]["note"] and LPA["ai_note"] == "ghi chu pick",
      f"{PA} {LPA['ai'].get('brain')} {LPA['ai'].get('note')}")
LPN = nl.learn_niche(NICHE, ["GOOD"], brain=DBrain("A", A1, F1), brain_name="A", http=fake_http, now=NOW, pick_ai=lambda: None)
check("pick_ai tra ve rong -> khong AI (thuan thong ke), khong loi", LPN["ai"] == {} and LPN["terms"])

# ---- v1.15.0: CHINH KIEN rieng cua tung AI + tranh luan co chat luong
S1 = dict(A1, stance_vi="Toi cuoc vao anglerfish 60 phut.", niche_verdict_vi="Niche con cua, nen vao.",
          traits_vi=["Phim dai 60 phut", "Mo dau bang canh that"], seo_vi=["Tieu de duoi 70 ky tu"], thumbnail_vi=["Can mat ca, 3 chu"])
S2 = dict(A2, stance_vi=["Toi cuoc vao hadal zone.", "Tranh video ngan."], niche_verdict_vi="Niche dong, kho vao.",
          traits_vi="Video 20 phut", seo_vi=["Tu khoa dau tieu de"], thumbnail_vi=["Khong chu"])
SF1 = dict(F1, stance_vi=S1["stance_vi"], verdict_vi="Toi van cuoc anglerfish; khong dong y voi B ve do dai.",
           niche_verdict_vi="Van nen vao (chot).", traits_vi=["Phim dai 60 phut (chot)"], seo_vi=["Tieu de duoi 60 ky tu (chot)"],
           thumbnail_vi=["Can mat ca, 2 chu (chot)"])
SF2 = dict(F2, verdict_vi="Toi giu hadal zone.", niche_verdict_vi="Van thay dong (chot).", seo_vi=["Tu khoa dau tieu de (chot)"])
sa, sb = DBrain("A", S1, SF1, close_after=1), DBrain("B", S2, SF2, close_after=1)
RS = nl.ai_cross_analyze([("A", sa), ("B", sb)], NICHE, CH, vids, [], debate_rounds=3)
SD = RS["dialog"]
SFIN = [t for t in SD if t["kind"] == "final"]
check("vong 1 xin CHINH KIEN rieng (stance_vi): 1 lua chon, khong 'con tuy'", '"stance_vi"' in sa.users[0] and "YOUR OWN OPINION" in sa.users[0]
      and "one bet" in sa.users[0] and 'No "it depends"' in sa.users[0])
check("vong 1 xin 4 nhan dinh: danh gia niche / dac diem / goi SEO / thumbnail (bang tieng Viet)",
      all(k in sa.users[0] for k in ('"niche_verdict_vi"', '"traits_vi"', '"seo_vi"', '"thumbnail_vi"'))
      and "YOUR ASSESSMENT of this niche for a NEW channel" in sa.users[0] and "the SEO PACKAGE you recommend" in sa.users[0]
      and "the THUMBNAIL formula you recommend" in sa.users[0] and '"notes_vi"' not in sa.users[0])
check("luot vong 1 mang chinh kien + 4 nhan dinh; AI tra danh sach dong -> gop thanh 1 doan / gach dau dong",
      SD[0]["stance"] == "Toi cuoc vao anglerfish 60 phut." and SD[1]["stance"] == "Toi cuoc vao hadal zone. Tranh video ngan."
      and SD[0]["niche_verdict"] == "Niche con cua, nen vao." and SD[0]["traits"] == "- Phim dai 60 phut\n- Mo dau bang canh that"
      and SD[1]["traits"] == "Video 20 phut" and SD[0]["seo"] == "- Tieu de duoi 70 ky tu" and SD[1]["thumbnail"] == "- Khong chu",
      f"{SD[0].get('traits')} | {SD[1].get('traits')}")
check("cau hoi tranh luan: thay chinh kien cua CA 2 ben + nhan dinh ve DUNG chu de do (khong lan chu de khac)",
      "Toi cuoc vao anglerfish 60 phut." in sa.users[1] and "Toi cuoc vao hadal zone." in sa.users[1]
      and "Niche con cua, nen vao." in sa.users[1] and "Niche dong, kho vao." in sa.users[1] and "Tieu de duoi 70 ky tu" not in sa.users[1]
      and "Tieu de duoi 70 ky tu" in sa.users[5] and "Tu khoa dau tieu de" in sa.users[5] and "Can mat ca" not in sa.users[5]
      and "Can mat ca, 3 chu" in sb.users[7] and "Khong chu" in sb.users[7])
check("loi dan tranh luan: giu chinh kien, tach SU THAT / DANH GIA, khong gat gu, ket bang 'Chính kiến của tôi:' + dong TRANG THAI",
      all(x in nl.DEBATE_SYSTEM for x in ("YOUR OWN thesis", "do not swap it", "FACT", "JUDGMENT", "not a polite merger",
                                          "no agreeing to be agreeable", "Chính kiến của tôi:", "IN VIETNAMESE", "TOPIC BY TOPIC",
                                          "TRẠNG THÁI: CÒN TRANH LUẬN", "TRẠNG THÁI: ĐÃ CHỐT", "ends only when BOTH sides write ĐÃ CHỐT",
                                          "Never repeat an argument you already made", "thumbnail number")))
_dp = [nl.build_debate_prompt(NICHE, CH, vids, [], "A", "B", S1, S2, [], "seo", k, 4) for k in range(4)]
check("nhiem vu tung luot: mo chu de -> dap -> 2 luot cuoi (het so vong) phai ra phan quyet, cam 'dong y cho xong'",
      "OPEN THIS TOPIC" in _dp[0] and "REPLY" in _dp[1] and "This is your first message on this topic" in _dp[1]
      and "THIS IS YOUR LAST TURN ON THIS TOPIC" not in _dp[0] and "THIS IS YOUR LAST TURN ON THIS TOPIC" not in _dp[1]
      and "This is your first message on this topic" not in _dp[2] and "THIS IS YOUR LAST TURN ON THIS TOPIC" in _dp[2]
      and "THIS IS YOUR LAST TURN ON THIS TOPIC" in _dp[3] and "Do not manufacture agreement" in _dp[3]
      and "drop a point only if they actually refuted it" in _dp[2] and "If nothing is left unresolved" in _dp[1])
check("ban chot: noi ro AI LA AI trong bien ban (chay that 23/11: Claude goi chinh minh la doi phuong) + xin chinh kien cuoi + 4 nhan dinh cuoi",
      "In this transcript YOU are [A] and the second analyst is [B]." in sa.users[-1]
      and "In this transcript YOU are [B] and the second analyst is [A]." in sb.users[-1] and '"verdict_vi"' in sa.users[-1]
      and "do not adopt their view just to converge" in sa.users[-1] and "Toi cuoc vao hadal zone." in sa.users[-1]
      and "niche_verdict_vi, traits_vi, seo_vi, thumbnail_vi" in sa.users[-1] and "Niche dong, kho vao." in sa.users[-1]
      and sa.users[-1].rstrip().endswith("Return only the JSON object."))
check("debate_addendum khong ten -> khong co cau dinh danh (goi kieu cu van chay)", "In this transcript" not in nl.debate_addendum([{"ai": "A", "text": "x"}]))
check("luot chot mang chinh kien CUOI + 4 nhan dinh cuoi", len(SFIN) == 2
      and SFIN[0]["verdict"].startswith("Toi van cuoc anglerfish") and SFIN[1]["verdict"] == "Toi giu hadal zone."
      and SFIN[0]["seo"] == "- Tieu de duoi 60 ky tu (chot)" and SFIN[1]["niche_verdict"] == "Van thay dong (chot).",
      str([t.get("verdict") for t in SFIN]))
_long = nl.clean_analysis({"niche_verdict_vi": "a" * 5000, "traits_vi": ["b" * 1500, "c" * 1500], "seo_vi": "d" * 5000,
                           "thumbnail_vi": ["e" * 2000], "verdict_vi": "f" * 1400, "stance_vi": "g" * 3000}, NICHE, CH, vids)
check("nhan dinh dai (ban chot that 24/11 dai 1100-1400 ky tu / muc) khong bi cat cut; van co tran",
      len(_long["niche_verdict"]) == 2400 and len(_long["traits"]) == 3005 and len(_long["seo"]) == 3200
      and len(_long["thumbnail"]) == 2002 and len(_long["verdict"]) == 1400 and len(_long["stance"]) == 1500,
      str({k: len(str(v)) for k, v in _long.items()}))
check("ket qua giu chinh kien cua TUNG ben (ban dau + sau tranh luan), khong gop lam mot",
      RS["stances"] == [{"ai": "A", "model": "", "stance": "Toi cuoc vao anglerfish 60 phut.", "verdict": SF1["verdict_vi"]},
                        {"ai": "B", "model": "", "stance": "Toi cuoc vao hadal zone. Tranh video ngan.", "verdict": "Toi giu hadal zone."}],
      str(RS.get("stances")))
check("ket qua giu nhan dinh CUOI cua TUNG ben ve 4 chu de (khong gop)",
      RS["opinions"] == [{"ai": "A", "model": "", "niche": "Van nen vao (chot).", "traits": "- Phim dai 60 phut (chot)",
                          "seo": "- Tieu de duoi 60 ky tu (chot)", "thumbnail": "- Can mat ca, 2 chu (chot)"},
                         {"ai": "B", "model": "", "niche": "Van thay dong (chot).", "traits": "", "seo": "- Tu khoa dau tieu de (chot)",
                          "thumbnail": ""}], str(RS.get("opinions")))
check("khung chat: bong vong 1 co 'CHÍNH KIẾN CỦA TÔI' + 4 muc; bong chot co 'CHÍNH KIẾN CUỐI CÙNG CỦA TÔI' + 'TÔI CHỐT — …'",
      "CHÍNH KIẾN CỦA TÔI: Toi cuoc vao anglerfish 60 phut." in nl.turn_message(SD[0], 0)["text"]
      and "ĐÁNH GIÁ NICHE:\nNiche con cua, nen vao." in nl.turn_message(SD[0], 0)["text"]
      and "GÓI SEO:\n- Tieu de duoi 70 ky tu" in nl.turn_message(SD[0], 0)["text"]
      and "THUMBNAIL:\n- Can mat ca, 3 chu" in nl.turn_message(SD[0], 0)["text"]
      and "CHÍNH KIẾN CUỐI CÙNG CỦA TÔI: Toi van cuoc anglerfish" in nl.turn_message(SFIN[0], 0)["text"]
      and "TÔI CHỐT — GÓI SEO:\n- Tieu de duoi 60 ky tu (chot)" in nl.turn_message(SFIN[0], 0)["text"])
LS = nl.learn_niche(NICHE, ["GOOD"], brain=DBrain("A", S1, SF1, close_after=1), brain_name="A", brain2=DBrain("B", S2, SF2), brain2_name="B",
                    http=fake_http, now=NOW, debate_rounds=1)
_rs = nl.format_report(LS)
check("bao cao: muc 'CHÍNH KIẾN CỦA TỪNG AI' co ban dau + sau tranh luan cua 2 ben", len(LS["ai"]["stances"]) == 2
      and "CHÍNH KIẾN CỦA TỪNG AI" in _rs and "Sau khi tranh luận: Toi giu hadal zone." in _rs
      and "Ban đầu: Toi cuoc vao anglerfish 60 phut." in _rs and "■ A:" in _rs and "■ B:" in _rs)
check("bao cao: muc 4 CHU DE — lap luan cuoi cua TUNG AI + chu de do da chot hay chua",
      "══ 4 CHỦ ĐỀ — LẬP LUẬN CUỐI CỦA TỪNG AI SAU KHI TRANH LUẬN (không gộp, bạn là người quyết) ══" in _rs
      and "▶ ĐÁNH GIÁ NICHE  —  hết số vòng sau 2 lượt nói, hai bên CHƯA cùng chốt" in _rs
      and "  ■ A:\n    Van nen vao (chot)." in _rs and "  ■ B:\n    Van thay dong (chot)." in _rs
      and "▶ GÓI SEO" in _rs and "    - Tu khoa dau tieu de (chot)" in _rs and "▶ THUMBNAIL" in _rs
      and _rs.index("▶ ĐÁNH GIÁ NICHE") < _rs.index("▶ ĐẶC ĐIỂM NICHE") < _rs.index("▶ GÓI SEO") < _rs.index("▶ THUMBNAIL")
      < _rs.index("TỪ KHÓA ĐUÔI DÀI AI ĐỀ XUẤT"), _rs[:1500])
_rss = nl.format_report({"ai": dict(RS, brain="A + B")})
check("bao cao: chu de DA CHOT ghi ro so luot", "▶ GÓI SEO  —  hai bên đã chốt sau 4 lượt nói" in _rss, _rss[:900])
check("loi dan dau khung chat noi ro chinh kien (chi khi co dau tri)", "CHÍNH KIẾN" in nl.dialog_intro(2) and "CHÍNH KIẾN" not in nl.dialog_intro(0)
      and "CHÍNH KIẾN" in nl.dialog_intro(2, legacy=True))
check("AI khong neu chinh kien / nhan dinh (ket qua cu / AI tra thieu) -> khong hien muc, khong loi", LXD["ai"]["stances"] == []
      and LXD["ai"]["opinions"] == [] and "CHÍNH KIẾN" not in nl.format_report(LXD) and "4 CHỦ ĐỀ" not in nl.format_report(LXD)
      and "CHÍNH KIẾN" not in nl.turn_message(LXD["ai"]["dialog"][0], 0)["text"]
      and "CHÍNH KIẾN" not in nl.format_report({"ai": {"brain": "x", "keywords": ["a b c"]}}))
L1S = nl.learn_niche(NICHE, ["GOOD"], brain=DBrain("A", S1, SF1), brain_name="A", http=fake_http, now=NOW)
check("1 AI: van co chinh kien + 4 nhan dinh cua AI do trong ket qua + bao cao", L1S["ai"]["stances"] == [{"ai": "A", "model": "",
      "stance": "Toi cuoc vao anglerfish 60 phut.", "verdict": ""}] and "CHÍNH KIẾN CỦA AI:" in nl.format_report(L1S)
      and L1S["ai"]["opinions"] == [{"ai": "A", "model": "", "niche": "Niche con cua, nen vao.",
                                     "traits": "- Phim dai 60 phut\n- Mo dau bang canh that", "seo": "- Tieu de duoi 70 ky tu",
                                     "thumbnail": "- Can mat ca, 3 chu"}]
      and "══ 4 CHỦ ĐỀ — NHẬN ĐỊNH CỦA AI ══" in nl.format_report(L1S) and "▶ THUMBNAIL\n  ■ A:\n    - Can mat ca, 3 chu" in nl.format_report(L1S),
      str(L1S["ai"].get("opinions")))

# ---- v1.16.0: so lieu kenh + mo dau mo ta + ANH GHEP THUMBNAIL de 2 AI tranh luan co can cu
import io as _io16  # noqa: E402
from PIL import Image as _PI16  # noqa: E402

TV = [{"id": f"v{i}", "title": f"Video {i} about anglerfish", "channel": "Ocean Lab" if i % 2 else "Trench", "views": 1000 * (i + 1),
       "vph": 100 - i, "duration_s": 600 + i * 60, "age_h": 24.0 * (i + 1), "desc": f"Mo ta so {i} #deepsea", "tags": []} for i in range(14)]
_facts = nl.channel_facts([{"title": "Ocean Lab", "subs": 12000, "video_count": 80}, {"title": "Trench", "subs": 0, "video_count": 5},
                           "ten tran"], TV)
check("channel_facts: moi kenh 1 dong so lieu (sub, tong video, trung vi view, dai bao nhieu, may video / tuan); sub an thi noi ro",
      _facts == ["- Ocean Lab: 12,000 subscribers, 80 videos in total; its 7 newest uploads: median 8,000 views, best 14,000, "
                 "median length 17 min, about 3.5 uploads per week",
                 "- Trench: subscriber count hidden, 5 videos in total; its 7 newest uploads: median 7,000 views, best 13,000, "
                 "median length 16 min, about 3.5 uploads per week"], str(_facts))
check("desc_samples: mo dau mo ta cua video dang len nhat", nl.desc_samples(TV, 2) == [
      "- [Trench] Video 0 about anglerfish => Mo ta so 0 #deepsea", "- [Ocean Lab] Video 1 about anglerfish => Mo ta so 1 #deepsea"]
      and nl.desc_samples([{"title": "x"}]) == [])
_pk = nl.pick_thumb_videos(TV)
check("chon thumbnail: 9 video dang len nhat (chia cac kenh) + 3 video YEU nhat da dang >= 3 ngay",
      [v["id"] for v, w in _pk if not w] == [f"v{i}" for i in range(9)] and [v["id"] for v, w in _pk if w] == ["v13", "v12", "v11"]
      and len(nl.pick_thumb_videos(TV[:6])) == 6 and nl.pick_thumb_videos([{"title": "khong id"}]) == [], str([(v["id"], w) for v, w in _pk]))


def _jpg(color=(200, 30, 30), size=(320, 180)):
    b = _io16.BytesIO()
    _PI16.new("RGB", size, color).save(b, "JPEG")
    return b.getvalue()


_urls = []


def _tfetch(url):
    _urls.append(url)
    if url.endswith("/v3/mqdefault.jpg"):
        raise OSError("404")
    return _jpg(size=(480, 360) if "v2/" in url else (320, 180))


_sp = os.path.join(TMP, "sheets", "deep.jpg")
SH = nl.build_thumb_sheet(TV, _sp, _tfetch)
_si = _PI16.open(_sp)
check("build_thumb_sheet: tai anh cong khai (khong ton quota), ghep 1 anh 4 cot co danh so; anh loi thi bo qua, so van lien tuc",
      SH["path"] == _sp and _si.size == (4 * 320 + 5 * 6, 3 * 180 + 4 * 6) and [it["n"] for it in SH["items"]] == list(range(1, 12))
      and [it["id"] for it in SH["items"]][:4] == ["v0", "v1", "v2", "v4"] and [it["weak"] for it in SH["items"]] == [False] * 8 + [True] * 3
      and SH["items"][0] == {"n": 1, "id": "v0", "title": "Video 0 about anglerfish", "channel": "Trench", "views": 1000, "age_d": 1, "weak": False}
      and sorted(_urls)[0] == "https://i.ytimg.com/vi/v0/mqdefault.jpg" and len(_urls) == 12, f"{_si.size} {SH['items'][:2]}")
check("o so 1 co nhan so (goc trai tren nen den), phan con lai la anh that", _si.getpixel((8, 8))[0] < 60 and _si.getpixel((200, 100))[0] > 150)


def _boom(_u):
    raise OSError("mat mang")


check("khong tai duoc / qua it video -> None (AI se ban thumbnail tu tieu de, noi ro la phong doan)",
      nl.build_thumb_sheet(TV, os.path.join(TMP, "sheets", "x.jpg"), _boom) is None and not os.path.exists(os.path.join(TMP, "sheets", "x.jpg"))
      and nl.build_thumb_sheet(TV[:3], os.path.join(TMP, "sheets", "y.jpg"), _tfetch) is None)
check("thumb_lines: so -> video (kenh, view, tuoi, danh dau video yeu)", nl.thumb_lines(SH)[0] == "1 = [Trench] Video 0 about anglerfish (1,000 views, 1 days old)"
      and nl.thumb_lines(SH)[-1].endswith("WEAK performer)") and nl.thumb_lines(None) == [])
check("thumb_sheet_path: trong data cua app, ten file theo niche", nl.thumb_sheet_path("AI Drama!").endswith(os.path.join("niche_thumbs", "ai_drama.jpg"))
      and nl.thumb_sheet_path("AI Drama").startswith(DATA_DIR) and nl.thumb_sheet_path("").endswith("niche.jpg"))
_ap = nl.build_analysis_prompt(NICHE, CH, TV, [], [], _facts, SH, True)
_ap0 = nl.build_analysis_prompt(NICHE, CH, TV, [], [], None, SH, False)
check("cau hoi phan tich: co so lieu kenh, tuoi video, mo dau mo ta, bang so thumbnail (khi AI xem duoc anh)",
      "CHANNEL FIGURES:\n- Ocean Lab: 12,000 subscribers" in _ap and "(1,000 views, 10 min, 1 days old)" in _ap
      and "HOW THEIR TOP VIDEOS OPEN THE DESCRIPTION:\n- [Trench] Video 0 about anglerfish => Mo ta so 0 #deepsea" in _ap
      and "the attached image is a contact sheet" in _ap and "1 = [Trench] Video 0 about anglerfish (1,000 views, 1 days old)" in _ap
      and "WEAK performer" in _ap)
check("AI khong xem duoc anh -> cau hoi noi ro 'khong co anh, chi suy tu tieu de va phai noi la phong doan'",
      "no thumbnail images are available to you" in _ap0 and "contact sheet" not in _ap0 and "CHANNEL FIGURES" not in _ap0
      and "say clearly that your thumbnail advice is an assumption" in _ap0)
_tp = nl.build_debate_prompt(NICHE, CH, TV, [("deep sea", 3)], "A", "B", S1, S2, [], "thumb", 0, 6, [{"text": "hay qua", "likes": 3}], _facts, SH, True)
_sp2 = nl.build_debate_prompt(NICHE, CH, TV, [("deep sea", 3)], "A", "B", S1, S2, [], "seo", 0, 6, [{"text": "hay qua", "likes": 3}], _facts, SH, True)
_np = nl.build_debate_prompt(NICHE, CH, TV, [("deep sea", 3)], "A", "B", S1, S2, [], "niche", 0, 6, [{"text": "hay qua", "likes": 3}], _facts, SH, True)
check("du lieu theo chu de: thumbnail -> bang so anh; goi SEO -> tag + mo dau mo ta; danh gia niche -> so lieu kenh + binh luan",
      "contact sheet" in _tp and "TAGS THEY USE" not in _tp and "TOP VIEWER COMMENTS" not in _tp
      and "contact sheet" not in _sp2 and "TAGS THEY USE (number of videos):\ndeep sea (3)" in _sp2 and "HOW THEIR TOP VIDEOS OPEN THE DESCRIPTION" in _sp2
      and "CHANNEL FIGURES:\n- Ocean Lab" in _np and "- hay qua" in _np and "HOW THEIR TOP VIDEOS OPEN" not in _np and "contact sheet" not in _np
      and " min, 1 days old)" in _np)
ia, ib = IBrain("A", S1, SF1, close_after=0), DBrain("B", S2, SF2, close_after=0)
RI = nl.ai_cross_analyze([("A", ia), ("B", ib)], NICHE, CH, TV, [], debate_rounds=2, facts=_facts, sheet=SH)
_ti = [k for k, u in enumerate(ia.users) if "CURRENT TOPIC (4 of 4)" in u]
check("AI xem duoc anh: anh di kem luot phan tich, cac luot ban THUMBNAIL va ban chot (khong kem o chu de khac)",
      ia.images[0] == [_sp] and ia.images[-1] == [_sp] and _ti and all(ia.images[k] == [_sp] for k in _ti)
      and all(ia.images[k] is None for k in range(1, len(ia.users) - 1) if k not in _ti)
      and "contact sheet" in ia.users[0] and "contact sheet" in ia.users[-1] and "CHANNEL FIGURES" in ia.users[-1], str(ia.images))
check("AI KHONG xem duoc anh (brain khong ho tro): khong bao gio nhan anh, cau hoi noi ro la khong co anh",
      all(x is None for x in ib.images) and "no thumbnail images are available to you" in ib.users[0] and "contact sheet" not in ib.users[0]
      and RI["agenda"][3]["key"] == "thumb")
LT = nl.learn_niche(NICHE, ["GOOD"], brain=IBrain("A", S1, SF1), brain_name="A", http=fake_http, now=NOW,
                    thumb_fetch=lambda u: _jpg(), thumb_path=os.path.join(TMP, "sheets", "learn.jpg"))
check("learn_niche: co thumb_fetch -> ghep anh thumbnail, luu so -> video vao ket qua, bao cao in bang so + duong dan anh",
      LT["thumbs"]["path"].endswith("learn.jpg") and os.path.isfile(LT["thumbs"]["path"]) and len(LT["thumbs"]["items"]) >= 4
      and "Số thumbnail AI nhắc tới (ảnh ghép: " in nl.format_report(LT) and "    1 = " in nl.format_report(LT)
      and "CHANNEL FIGURES:" in nl.build_analysis_prompt(NICHE, CH, vids, [], [], ["- x: 1 subscribers"]), str(LT.get("thumbs"))[:200])
check("learn_niche trong test (http gia, khong thumb_fetch) KHONG ra mang tai anh", L1S["thumbs"] == {} and LXD["thumbs"] == {})

from src.agent import account_brain as _ab16  # noqa: E402
_calls16 = []


def _run16(out="", write=""):
    def run(cmd, stdin_text="", timeout=120, env=None, cwd=None):
        _calls16.append({"cmd": list(cmd), "stdin": stdin_text})
        if write and "-o" in cmd:
            with open(cmd[cmd.index("-o") + 1], "w", encoding="utf-8") as f:
                f.write(write)
        return 0, out, ""
    return run


_cb = _ab16.ClaudeAccountBrain("claude.exe", _run16(out=json.dumps({"type": "system", "subtype": "init"}) + "\n"
                                                    + json.dumps({"type": "assistant", "message": {"content": []}}) + "\n"
                                                    + json.dumps({"type": "result", "is_error": False, "result": "thay anh"})))
_ans = _cb.ask_chat("SYS", "Hoi ve anh", images=[_sp, os.path.join(TMP, "khong_co.jpg")])
_c = _calls16[-1]
_msg = json.loads(_c["stdin"])
check("Claude tai khoan + anh: gui 1 tin stream-json (anh base64 + cau hoi), doc dong ket qua cuoi; file anh khong ton tai thi bo",
      _ans == "thay anh" and _c["cmd"][_c["cmd"].index("--output-format") + 1] == "stream-json"
      and _c["cmd"][_c["cmd"].index("--input-format") + 1] == "stream-json" and "--verbose" in _c["cmd"]
      and _c["cmd"][_c["cmd"].index("--tools") + 1] == "" and _msg["type"] == "user"
      and [b["type"] for b in _msg["message"]["content"]] == ["image", "text"]
      and _msg["message"]["content"][0]["source"]["media_type"] == "image/jpeg" and len(_msg["message"]["content"][0]["source"]["data"]) > 100
      and _msg["message"]["content"][1]["text"] == "SYS\n\nHoi ve anh" and _ab16.ClaudeAccountBrain.supports_images is True, str(_c["cmd"]))
_cb2 = _ab16.ClaudeAccountBrain("claude.exe", _run16(out=json.dumps({"type": "result", "is_error": False, "result": "khong anh"})))
check("Claude tai khoan KHONG anh -> y nhu cu (json thuong, cau hoi qua stdin)", _cb2.ask_chat("SYS", "Hoi") == "khong anh"
      and _calls16[-1]["cmd"][_calls16[-1]["cmd"].index("--output-format") + 1] == "json" and "--input-format" not in _calls16[-1]["cmd"]
      and _calls16[-1]["stdin"] == "SYS\n\nHoi")
_gb = _ab16.ChatGPTAccountBrain("codex.exe", _run16(write="codex thay anh"))
_gb.model_name = "gpt-x"
_ga = _gb.ask_chat("SYS", "Hoi ve anh", images=[_sp])
_gc = _calls16[-1]["cmd"]
check("ChatGPT tai khoan + anh: them '-i <anh>' TRUOC cac tham so khac, cau hoi van qua stdin ('-' o cuoi)",
      _ga == "codex thay anh" and _gc[_gc.index("-i") + 1] == _sp and _gc.index("-i") < _gc.index("-C") and _gc[-1] == "-"
      and _gc[_gc.index("-i") + 2] == "-m", str(_gc))
_gb.ask_chat("SYS", "Hoi")
check("ChatGPT tai khoan KHONG anh -> khong co '-i'", "-i" not in _calls16[-1]["cmd"])
check("doi thoai kieu cu (chua co 'kind') van hien duoc", nl.turn_message({"round": 2, "ai": "X", "other": "Y", "review": "- ok"}, 1)["sub"]
      == "Vòng 2 · trả lời Y" and nl.turn_message({"round": 1, "ai": "X", "description": "D"}, 0)["text"] == "Theo tôi, niche này là: D")
check("1 AI hong vong 1 -> doi thoai chi co 2 luot, luot hong ghi ly do", [bool(t["error"]) for t in R1["dialog"]] == [False, True]
      and "(Không trả lời được: HẾT CREDIT" in nl.format_dialog({"ai": R1}) and "Không có đối chiếu chéo" in nl.format_dialog({"ai": R1}))
check("1 AI hong vong 2 -> luot do ghi loi + 'dung ban vong 1'", R2["dialog"][3]["error"] and not R2["dialog"][2]["error"]
      and "Bot dùng bản vòng 1 của AI này" in nl.format_dialog({"ai": R2}))
check("khong chay 2 AI -> khong co doi thoai", nl.format_dialog({}) == "" and nl.format_dialog(LC) == "" and nl.format_dialog(None) == ""
      and nl.dialog_messages(LC) == [] and nl.dialog_messages(None) == [])
check("ca 2 AI hong -> None", nl.ai_cross_analyze([("a", XBrain(RuntimeError("x"))), ("b", XBrain("khong phai json"))], NICHE, CH, vids, []) is None)
LX = nl.learn_niche(NICHE, ["GOOD"], brain=XBrain(A1, F1), brain_name="claude-sonnet", brain2=XBrain(A2, F2), brain2_name="openai",
                    http=fake_http, now=NOW)
repX = nl.format_report(LX)
check("learn_niche 2 AI: learned.ai co nhan + nhan xet cheo; bao cao hien day du", LX["ai"]["brain"] == "claude-sonnet + openai (đối chiếu chéo)"
      and "PHÂN TÍCH CỦA AI (claude-sonnet + openai (đối chiếu chéo))" in repX and "HAI AI NHẬN XÉT CHÉO BÀI CỦA NHAU" in repX
      and "2 từ khóa ĐẦU là cả 2 AI cùng chọn" in repX, repX[:400])
LD = nl.learn_niche(NICHE, ["GOOD"], brain=XBrain(RuntimeError("401 invalid_api_key")), brain_name="a", brain2=XBrain("???"), brain2_name="b",
                    http=fake_http, now=NOW)
check("learn_niche 2 AI: learned.ai luu ca doi thoai", len(LX["ai"]["dialog"]) == 4 and "■ openai — Vòng 2 · trả lời claude-sonnet" in nl.format_dialog(LX))
check("learn_niche: ca 2 AI hong -> van co ket qua thong ke, ai = {}", LD["ai"] == {} and "anglerfish" in LD["terms"])
check("explain_ai_error", "HẾT CREDIT" in nl.explain_ai_error("insufficient_quota") and "KEY SAI" in nl.explain_ai_error("401 Unauthorized")
      and "quá hạn" in nl.explain_ai_error("Request timed out") and nl.explain_ai_error("") == "không trả lời")


class _Resp:
    class _C:
        class message:
            content = " ok-khong-temperature "
    choices = [_C]


class TempBrain:
    """Model chi nhan temperature mac dinh: ask_chat tra rong + last_error; ask_long phai goi lai KHONG kem temperature."""
    model_name, last_error, seen = "gpt-x", "", {}

    def ask_chat(self, system, user, timeout=60, temperature=0.2):
        self.last_error = "Error code: 400 - Unsupported value: 'temperature' does not support 0.3 with this model."
        return ""

    class client:
        class chat:
            class completions:
                @staticmethod
                def create(**kw):
                    TempBrain.seen = kw
                    return _Resp


check("ask_long: model tu choi temperature -> goi lai khong kem temperature", nl.ask_long(TempBrain(), "s", "u") == "ok-khong-temperature"
      and "temperature" not in TempBrain.seen and TempBrain.seen.get("model") == "gpt-x")
check("brain co ask_chat (Claude/OpenAI) -> dung ask_chat voi loi dan rieng + timeout dai", len(cb.calls) == 1
      and "JSON" in cb.calls[0][0] and cb.calls[0][1] >= 120 and LC["ai"]["keywords"])
check("goi y tu khoa khong trung tu khoa da co", "deep sea creatures" not in L["suggest"] and "hadal zone" in L["suggest"])
check("top video xep theo luot xem/gio", L["top_titles"][0].startswith("Anglerfish hunting"), L["top_titles"][0])
check("ten /c/ phai tra bang search (100 don vi) -> units > 100", 100 < L["units"] < 160, str(L["units"]))
check("chi doc: khong co lenh nao ngoai 5 endpoint GET", {c[0] for c in CALLS} <= {"channels", "search", "playlistItems", "videos", "commentThreads"})
check("video tat binh luan khong lam hong", any(c[0] == "commentThreads" and c[1]["videoId"] == "b2" for c in CALLS))
check("short khong binh luan khong bi goi commentThreads", not any(c[0] == "commentThreads" and c[1]["videoId"] == "a5" for c in CALLS))
check("log tung kenh", sum(1 for m in logs if m.startswith("✓")) == 3 and any(m.startswith("✗") for m in logs))
L0 = nl.learn_niche(NICHE, ["GOOD"], brain=None, http=fake_http, now=NOW)
check("khong co AI: van co tu vung thong ke, khong co tom tat", "anglerfish" in L0["terms"] and L0["audience"] == "")
L1 = nl.learn_niche(NICHE, ["GOOD"], brain=FakeBrain(fail=True), http=fake_http, now=NOW)
check("AI loi: giu danh sach thong ke, khong nem loi", L1["terms"] == L0["terms"] and L1["audience"] == "")
for keys, frag in ((["BADKEY"], "KEY SAI"), (["QUOTA"], "HẾT QUOTA"), (["OFFLINE"], "không kết nối"), ([], "chưa có")):
    try:
        nl.learn_niche(NICHE, keys, http=fake_http)
        check(f"key {keys} -> LearnError", False)
    except nl.LearnError as e:
        check(f"key {keys} -> LearnError ro ly do", frag in str(e) and "BADKEY" not in str(e), str(e))
try:
    nl.learn_niche({"name": "x", "keywords": ["a"], "channels": []}, ["GOOD"], http=fake_http)
    check("niche khong co kenh -> LearnError", False)
except nl.LearnError as e:
    check("niche khong co kenh -> LearnError", "chưa có kênh" in str(e))
rep = nl.format_report(L)
check("format_report du 5 muc", all(x in rep for x in ("KÊNH ĐÃ ĐỌC", "TỪ VỰNG ĐẶC TRƯNG", "NGƯỜI XEM", "TỪ KHÓA GỢI Ý", "VIDEO ĐANG LÊN", "@khongtontai")))
check("format_report niche chua co AI", "cần chọn AI Brain" in nl.format_report(L0))

# ---------------------------------------------------------------- [4]
print("\n[4] channel_mode dung phan da hoc")
base = cm.normalize_niche(NICHE)
check("niche chua hoc: learned_tokens rong, audience rong", base["learned_tokens"] == set() and base["audience"] == "")
learned = cm.normalize_niche(dict(NICHE, learned=L))
check("niche da hoc: co learned_tokens + audience", {"anglerfish", "hadal"} <= learned["learned_tokens"] and "tàu lặn" in learned["audience"])
check("tu da la tu khoa thi khong nhan doi vao learned_tokens",
      not (learned["learned_tokens"] & set(learned["tokens"])))
T1 = "Why the anglerfish glows"
T2 = "Bioluminescent anglerfish caught on a submersible camera"
check("truoc khi hoc: video chi co tu vung doi thu = lac niche", cm.niche_score(base, T2)[0] < cm.NICHE_SCORE_MIN)
check("sau khi hoc: 1 tu le CHUA du nguong", cm.niche_score(learned, T1)[0] == 1)
s2, why2 = cm.niche_score(learned, T2)
check("sau khi hoc: >= 2 tu vung -> dung niche (toi da +3)", s2 == 3 and "từ vựng đã học" in why2, f"{s2} {why2}")
check("tu loai tru van thang tu vung da hoc", cm.niche_score(learned, "Minecraft anglerfish squid build")[0] < cm.NICHE_SCORE_MIN)
check("diem tu khoa goc khong doi", cm.niche_score(learned, "Mariana trench documentary 2026")[0] ==
      cm.niche_score(base, "Mariana trench documentary 2026")[0])
check("learned hong kieu (khong phai dict) khong lam vo", cm.normalize_niche(dict(NICHE, learned="x"))["learned_tokens"] == set())


class _W(cm.ChannelModeMixin):
    def __init__(self, brain):
        self.brain = brain

    def _ch_say(self, msg):
        pass


fb = FakeBrain()
_W(fb)._ch_ai_pick(learned, [{"title": "A", "chan": "c"}])
check("cau hoi AI co tu vung + ghi chu nguoi xem", "Niche vocabulary" in fb.prompts[0] and "What this audience likes" in fb.prompts[0])
fb2 = FakeBrain()
_W(fb2)._ch_ai_pick(base, [{"title": "A", "chan": "c"}])
check("niche chua hoc: cau hoi AI nhu cu", "Niche vocabulary" not in fb2.prompts[0] and "Videos on the page" in fb2.prompts[0])

# ---------------------------------------------------------------- [5]
print("\n[5] Giao dien")


def slow_http(path, params):        # API that luon cham hon 1 nhip poll -> kiem tra duoc trang thai "dang hoc"
    time.sleep(0.03)
    return fake_http(path, params)


nl._urllib_http = slow_http
# v1.16.0: phần giao diện học "thật" (http=None) nên sẽ tải thumbnail -> thay hàm tải bằng ảnh giả, KHÔNG ra mạng
THUMB_URLS = []


def _fake_thumb(url, timeout=12):
    THUMB_URLS.append(url)
    return _jpg()


nl._fetch_bytes = _fake_thumb
ui._brain_candidates_from_env = lambda: ["fake"]
ui._pick_live_brain = lambda cands, log=None: (FakeBrain(), "fake", "")

# v1.12.0: AI qua tai khoan dang nhap — test KHONG goi cong cu that (claude / codex)
from src.agent import account_brain as acc_mod  # noqa: E402
ACC = {"c": {"installed": True, "logged_in": True, "plan": "max", "who": "ab***@x.com", "path": "claude.exe",
             "detail": "đã đăng nhập · gói max · ab***@x.com"},
       "g": {"installed": True, "logged_in": True, "plan": "", "who": "", "path": "codex.exe",
             "detail": "đã đăng nhập bằng tài khoản ChatGPT"}}
LOGIN, TRY = [], []


class _TryBrain:
    last_error = ""

    def ask_text(self, prompt, timeout=90):
        TRY.append(prompt)
        return "OK"


acc_mod.claude_status = lambda run=None: dict(ACC["c"])
acc_mod.codex_status = lambda run=None: dict(ACC["g"])
acc_mod.find_claude = lambda: ACC["c"]["path"]
acc_mod.find_codex = lambda: ACC["g"]["path"]
acc_mod.open_login = lambda name: (LOGIN.append(name), True)[1]
acc_mod.codex_listed_models = lambda: ["gpt-a", "gpt-b"]
acc_mod.get_account_brain = lambda name, run=None: _TryBrain()

root = tk.Tk()
root.geometry("1200x820+0+0")
app = ui.AutomationApp(root)
root.update()


def walk(w):
    yield w
    for c in w.winfo_children():
        yield from walk(c)


def pump(cond, seconds=8):
    t = time.time()
    while time.time() - t < seconds:
        root.update()
        if cond():
            return True
        time.sleep(0.05)
    return False


app.cfg["niches"] = [dict(NICHE)]
app.open_niche_manager()
root.update()
nd = app._niche_dialog
entries = [w for w in walk(nd) if isinstance(w, ttk.Entry)]
buttons = {str(b.cget("text")): b for b in walk(nd) if isinstance(b, ttk.Button)}
labels = [w for w in walk(nd) if isinstance(w, tk.Label)]
status = labels[-1]
lbl_key = labels[-2]
lst = [w for w in walk(nd) if isinstance(w, tk.Listbox)][0]
texts = [w for w in walk(nd) if isinstance(w, tk.Text)]
check("dai key = tom tat + nut 'Quản lý key…' (khong con o nhap key trong hop Niche)",
      {"Quản lý key…", "Học niche từ kênh đối thủ", "Xem kết quả học"} <= set(buttons) and len(entries) == 7)   # 5 o nhap + o 'Vòng đấu trí' (Spinbox) + o chon AI (deu la ttk.Entry)
check("chua co key -> huong dan bam 'Quản lý key…'", "Chưa có key" in lbl_key.cget("text") and "Quản lý key" in lbl_key.cget("text"))
buttons["Học niche từ kênh đối thủ"].invoke()
check("hoc khi chua co key -> nhac them key, khong chay", "Chưa có YouTube API key" in status.cget("text"))

SECRET = SECRET_PRE = "AIzaSyTESTKEY_1234567890abcdefghijklmnop"
# ---- v1.9.8: CUA SO QUAN LY KHO KEY (rat nhieu key)
KEYFILE = nl.keys_file()
check("kho key nam trong thu muc data TAM", KEYFILE.startswith(DATA_DIR) and not os.path.exists(KEYFILE))
buttons["Quản lý key…"].invoke()
root.update()
km = app._ytkey_dialog
check("mo cua so 'Quản lý YouTube API key'", km is not None and km.winfo_exists() and km.title() == "Quản lý YouTube API key")
buttons["Quản lý key…"].invoke()
check("bam lan 2 khong mo them cua so", len([w for w in root.winfo_children() if isinstance(w, tk.Toplevel)
                                             and w.title() == "Quản lý YouTube API key"]) == 1)


def kbtn(prefix):
    return [b for b in walk(km) if isinstance(b, ttk.Button) and str(b.cget("text")).startswith(prefix)][0]


ktxt = [w for w in walk(km) if isinstance(w, tk.Text)][0]
ktree = [w for w in walk(km) if isinstance(w, ttk.Treeview)][0]
klabels = [w for w in walk(km) if isinstance(w, tk.Label)]
lbl_sum, lbl_paste = klabels[0], klabels[-1]
check("cua so co o dan nhieu dong + bang + du nut", int(ktxt.cget("height")) >= 5 and all(kbtn(t) for t in (
    "Thêm vào kho", "Nạp từ file", "Xóa ô dán", "Kiểm tra tất cả", "Kiểm tra key đã chọn", "Xóa key đã chọn", "Gỡ key sai", "Đóng")))
kbtn("Thêm vào kho").invoke()
check("o trong -> nhac dan key", "đang trống" in lbl_paste.cget("text") and len(ktree.get_children()) == 0)

GOOD = [f"AIzaSyGOOD{i:04d}" + "x" * 25 for i in range(55)]
QUO = [f"QUOTA_het_han_muc_{i:04d}" + "q" * 17 for i in range(3)]
BAD = [f"BADKEY_bi_thu_hoi_{i:04d}" + "b" * 17 for i in range(2)]
ALL60 = GOOD + QUO + BAD
ktxt.insert("1.0", "\n".join(ALL60[:30]) + "\r\n" + ", ".join(ALL60[30:]) + "\n" + GOOD[0] + "\nkhong phai key\n")
root.update()
check("dan 60 key (xuong dong + dau phay) -> bao ngay so key trong o", "Trong ô: 60 key mới" in lbl_paste.cget("text")
      and "3 đoạn KHÔNG giống API key" in lbl_paste.cget("text") and "CHƯA lưu" in lbl_paste.cget("text"), lbl_paste.cget("text"))
kbtn("Thêm vào kho").invoke()
root.update()
check("them 60 key mot lan vao kho (bo doan hong, bo trung)", len(ktree.get_children()) == 60 and len(nl.pool_load()) == 60
      and "Đã thêm 60 key" in lbl_sum.cget("text") and "bỏ qua 3 đoạn" in lbl_sum.cget("text"), lbl_sum.cget("text"))
check("them xong thi o dan duoc xoa", ktxt.get("1.0", "end").strip() == "" and "đang trống" in lbl_paste.cget("text"))
check("key luu trong data/youtube_keys.json, KHONG ghi vao .env", os.path.exists(KEYFILE)
      and "YOUTUBE_API_KEY" not in open(ENV_FILE, encoding="utf-8").read())
shown = " ".join(str(v) for iid in ktree.get_children() for v in ktree.item(iid, "values")) + lbl_sum.cget("text")
check("bang chi hien key da che", not any(k in shown for k in ALL60) and "AIza…xxxx" in shown)
check("dong tom tat o hop Niche tu cap nhat", "60 key" in lbl_key.cget("text") and "60 chưa kiểm tra" in lbl_key.cget("text"), lbl_key.cget("text"))
ktxt.insert("1.0", GOOD[1] + "\n" + GOOD[2])
kbtn("Thêm vào kho").invoke()
check("dan lai key da co -> khong nhan doi", len(nl.pool_load()) == 60 and "bỏ 2 key trùng" in lbl_sum.cget("text"))
kbtn("Kiểm tra key đã chọn").invoke()
check("chua chon dong nao -> chi nhac", "Không có key nào để kiểm tra" in lbl_sum.cget("text"))

kbtn("Kiểm tra tất cả").invoke()
check("dang kiem tra -> khoa nut", kbtn("Kiểm tra tất cả").instate(["disabled"]) and kbtn("Thêm vào kho").instate(["disabled"]))
check("kiem tra 60 key song song xong", pump(lambda: "Kiểm tra xong 60 key" in lbl_sum.cget("text"), 20), lbl_sum.cget("text"))
cnt = nl.pool_counts(nl.pool_load())
check("ket qua tung key duoc LUU: 55 dung duoc / 3 het quota / 2 sai", (cnt["ok"], cnt["quota"], cnt["invalid"], cnt["usable"]) == (55, 3, 2, 55), str(cnt))
check("dong tom tat + nut 'Gỡ key sai (2)'", "55 dùng được" in lbl_sum.cget("text") and "3 hết quota hôm nay" in lbl_sum.cget("text")
      and "2 sai" in lbl_sum.cget("text") and "55 key sẵn sàng dùng" in lbl_sum.cget("text") and str(kbtn("Gỡ key sai").cget("text")) == "Gỡ key sai (2)")
statuses = [ktree.item(i, "values")[2] for i in ktree.get_children()]
check("bang hien trang thai tung dong", statuses.count("Dùng được") == 55 and statuses.count("Hết quota hôm nay") == 3 and statuses.count("KEY SAI") == 2)
check("xong thi mo lai nut", not kbtn("Kiểm tra tất cả").instate(["disabled"]))

_ask = ui.messagebox.askyesno
ui.messagebox.askyesno = lambda *a, **k: True
kbtn("Gỡ key sai").invoke()
check("'Gỡ key sai' chi go 2 key KEY SAI, giu key het quota", len(nl.pool_load()) == 58 and nl.pool_counts(nl.pool_load())["quota"] == 3
      and "Đã gỡ 2 key sai" in lbl_sum.cget("text") and len(ktree.get_children()) == 58)
ktree.selection_set(ktree.get_children()[:2])
kbtn("Xóa key đã chọn").invoke()
check("xoa 2 key da chon", len(nl.pool_load()) == 56 and GOOD[0] not in [e["key"] for e in nl.pool_load()])
ktree.selection_set(ktree.get_children()[0])
kbtn("Kiểm tra key đã chọn").invoke()
check("kiem tra rieng key da chon", pump(lambda: "Kiểm tra xong 1 key" in lbl_sum.cget("text"), 10))

FILE_KEYS = [f"AIzaSyFILE{i:04d}" + "f" * 25 for i in range(100)]
kfile = os.path.join(TMP, "keys.txt")
open(kfile, "w", encoding="utf-8-sig", newline="").write("\r\n".join(FILE_KEYS) + "\r\n# ghi chu\r\n")
_fd = ui.filedialog.askopenfilename
ui.filedialog.askopenfilename = lambda *a, **k: kfile
kbtn("Nạp từ file").invoke()
ui.filedialog.askopenfilename = _fd
root.update()
check("nap 100 key tu file .txt (BOM + CRLF)", len(nl.pool_load()) == 156 and len(ktree.get_children()) == 156
      and "Đã thêm 100 key" in lbl_sum.cget("text"), lbl_sum.cget("text"))
ui.messagebox.askyesno = _ask
app._toggle_theme()
root.update()
app._toggle_theme()
root.update()
check("doi nen khi cua so key dang mo khong loi", km.winfo_exists())
kbtn("Đóng").invoke()
root.update()
check("dong cua so key -> mo lai duoc, du lieu con nguyen", app._ytkey_dialog is None and len(nl.pool_load()) == 156)

# ---- key them qua 'Quản lý API key' (.env, bien danh so) -> mo cua so la chuyen vao kho
_keep = nl.pool_load()
nl.pool_save([])
api_vault.set_key("YOUTUBE_API_KEY_2", "AIzaSyENVNUM_000000000000000000000000002")
api_vault.set_key("YOUTUBE_API_KEY_3", "AIzaSyENVNUM_000000000000000000000000003")
check("key trong .env (bien danh so _2, _3) duoc kho nhin thay", nl.env_key_count() == 2 and len(nl.pool_load()) == 2)
buttons["Quản lý key…"].invoke()
root.update()
km = app._ytkey_dialog
check("mo cua so -> CHUYEN key .env vao kho + bao ro", "Đã chuyển 2 key từ 'Quản lý API key'" in
      [w for w in walk(km) if isinstance(w, tk.Label)][0].cget("text") and nl.env_key_count() == 0
      and "YOUTUBE_API_KEY" not in open(ENV_FILE, encoding="utf-8").read()
      and len(json.load(open(KEYFILE, encoding="utf-8"))["keys"]) == 2)
[b for b in walk(km) if isinstance(b, ttk.Button) and str(b.cget("text")) == "Đóng"][0].invoke()
root.update()
nl.pool_save(_keep)

# ---- bam 'Hoc niche' khi form CHUA LUU (ten + kenh, chua co tu khoa) -> tu luu roi hoc (truong hop user gap 23/11)
nl.pool_save([])
nl.pool_save([{"key": SECRET_PRE, "status": "new", "msg": "", "checked": 0.0, "used": 0.0}])
buttons["+ Niche mới"].invoke()
entries[0].insert(0, "Auto Save")
buttons["Học niche từ kênh đối thủ"].invoke()
root.update()
check("hoc khi chi co ten -> CHUA LUU, khong chay", status.cget("text").startswith("CHƯA LƯU") and len(app.cfg["niches"]) == 1
      and not buttons["Học niche từ kênh đối thủ"].instate(["disabled"]))
texts[1].insert("1.0", "https://www.youtube.com/@OceanLab\n" + UC_B)
buttons["Học niche từ kênh đối thủ"].invoke()
check("hoc khi form chua luu (ten + kenh) -> TU LUU niche roi hoc luon", [n["name"] for n in app.cfg["niches"]] == ["Deep sea", "Auto Save"]
      and buttons["Học niche từ kênh đối thủ"].instate(["disabled"]))
check("hoc xong niche vua tu luu", pump(lambda: "Đã học niche 'Auto Save'" in status.cget("text"), 15), status.cget("text"))
check("niche tu luu co learned + goi y tu khoa", app_config.load_config()["niches"][1].get("learned", {}).get("videos") == 9
      and len(app_config.load_config()["niches"][1]["learned"]["suggest"]) >= 1)
for _w in [w for w in root.winfo_children() if isinstance(w, tk.Toplevel) and w.title().startswith("Kết quả học niche")]:
    _w.destroy()
_askd = ui.messagebox.askyesno
ui.messagebox.askyesno = lambda *a, **k: True
buttons["Xóa"].invoke()
ui.messagebox.askyesno = _askd
nl.pool_save(_keep)
root.update()

# ---- luu niche: bao tu choi ro rang + cho luu khi chi co kenh doi thu
buttons["+ Niche mới"].invoke()
entries[0].insert(0, "AI Drama")
buttons["Lưu niche"].invoke()
root.update()
check("chi co ten -> CHUA LUU, bao do + dua con tro vao o tu khoa", status.cget("text").startswith("CHƯA LƯU — cần ít nhất 1 từ khóa")
      and str(status.cget("fg")) == app.C_ERR_FG and len(app.cfg["niches"]) == 1 and int(texts[0].cget("highlightthickness")) == 2)
texts[1].insert("1.0", "@SomeAIDrama")
buttons["Lưu niche"].invoke()
root.update()
check("co kenh doi thu (chua co tu khoa) -> LUU duoc + nhac bam Hoc niche", len(app_config.load_config()["niches"]) == 2
      and "Đã lưu niche 'AI Drama'" in status.cget("text") and "CHƯA có từ khóa" in status.cget("text"), status.cget("text"))
check("o tu khoa / kenh doi thu la o NHIEU DONG (>= 8 dong) dat canh nhau", int(texts[0].cget("height")) >= 8
      and int(texts[1].cget("height")) >= 8 and texts[0].winfo_rooty() == texts[1].winfo_rooty()
      and texts[0].winfo_height() >= 100, f"{texts[0].winfo_height()}")
_ask2 = ui.messagebox.askyesno
ui.messagebox.askyesno = lambda *a, **k: True
buttons["Xóa"].invoke()
ui.messagebox.askyesno = _ask2
lst.selection_set(0)
lst.event_generate("<<ListboxSelect>>")
root.update()
check("xoa niche nhap -> con lai niche Deep sea", [n["name"] for n in app.cfg["niches"]] == ["Deep sea"] and entries[0].get() == "Deep sea")

# ---- ham thuan cua kho key
now = time.time()
check("classify", [nl.classify(True, ""), nl.classify(False, "KEY SAI — x"), nl.classify(False, "key đã HẾT QUOTA hôm nay"),
                   nl.classify(False, "key đúng nhưng project CHƯA BẬT"), nl.classify(False, "không kết nối được")]
      == ["ok", "invalid", "quota", "disabled", "error"])
ents = [{"key": "A" * 30, "status": "quota", "msg": "", "checked": now - 2 * 86400, "used": 5.0},
        {"key": "B" * 30, "status": "quota", "msg": "", "checked": now, "used": 0.0},
        {"key": "C" * 30, "status": "ok", "msg": "", "checked": now, "used": 9.0},
        {"key": "D" * 30, "status": "invalid", "msg": "", "checked": now, "used": 0.0},
        {"key": "E" * 30, "status": "error", "msg": "mang", "checked": now, "used": 0.0},
        {"key": "F" * 30, "status": "new", "msg": "", "checked": 0.0, "used": 0.0}]
check("pool_usable: bo key sai + key dang het quota; quota tu hom truoc da hoi; it dung dung truoc; loi mang xep cuoi",
      nl.pool_usable(ents, now) == ["F" * 30, "A" * 30, "C" * 30, "E" * 30], str([k[0] for k in nl.pool_usable(ents, now)]))
check("last_quota_reset nam trong 24h gan nhat", 0 <= now - nl.last_quota_reset(now) < 86400)
check("file kho hong -> [] (khong vo)", nl.pool_load(path=os.path.join(TMP, "khong_co.json"), env_keys=[]) == [])
api_vault.set_key("YOUTUBE_API_KEY", "AIzaSyENV_0000000000000000000000000000001,AIzaSyFILE0000" + "f" * 25)
merged = nl.pool_load()
check("key cu trong .env duoc gop vao kho (bo trung)", len(merged) == 157)
nl.pool_save(merged)
check("luu kho xong -> go key khoi .env (1 nguon duy nhat)", "YOUTUBE_API_KEY" not in open(ENV_FILE, encoding="utf-8").read()
      and len(nl.pool_load()) == 157)

# ---- hoc niche lay key tu kho: key 1 het quota -> tu xoay sang key 2, ghi trang thai vao kho
K2 = "QUOTA_key_het_han_muc_0000000000000002"
pool2 = []
nl.pool_add(pool2, [K2, SECRET])
nl.pool_save(pool2)

buttons["Xem kết quả học"].invoke()
check("chua hoc -> 'Xem ket qua' chi nhac", "chưa học lần nào" in status.cget("text"))
buttons["Học niche từ kênh đối thủ"].invoke()
check("dang hoc -> khoa nut", buttons["Học niche từ kênh đối thủ"].instate(["disabled"]))
check("Hoc niche xong -> bao ket qua", pump(lambda: "Đã học niche 'Deep sea'" in status.cget("text")), status.cget("text"))
saved = app_config.load_config()["niches"][0]
check("learned duoc luu vao app_config", saved.get("learned", {}).get("channels") == ["Ocean Lab", "Abyss Explorers", "Trench Diaries"]
      and "anglerfish" in saved["learned"]["terms"] and "tàu lặn" in saved["learned"]["audience"])
check("danh sach danh dau 'đã học'", "đã học" in lst.get(0))
rws = [w for w in root.winfo_children() if isinstance(w, tk.Toplevel) and w.title().startswith("Kết quả học niche")]
check("tu mo cua so ket qua", len(rws) == 1)
rtext = [w for w in walk(rws[0]) if isinstance(w, tk.Text)][0].get("1.0", "end")
check("cua so ket qua co tu vung + goi y, khong lo key", "anglerfish" in rtext and "hadal zone" in rtext and SECRET not in rtext)
rbtn = {str(b.cget("text")): b for b in walk(rws[0]) if isinstance(b, ttk.Button)}
n_kw = len(app.cfg["niches"][0]["keywords"])
rbtn["Thêm từ khóa gợi ý vào niche"].invoke()
root.update()
kws = app_config.load_config()["niches"][0]["keywords"]
check("them tu khoa goi y vao niche (khong trung)", len(kws) > n_kw and "hadal zone" in kws and len(set(k.lower() for k in kws)) == len(kws))
rbtn["Thêm từ khóa gợi ý vào niche"].invoke()
check("bam lan 2 khong them trung", app_config.load_config()["niches"][0]["keywords"] == kws)
rbtn["Đóng"].invoke()

entries[1].delete(0, "end")
entries[1].insert(0, "Mo ta moi")
buttons["Lưu niche"].invoke()
root.update()
saved = app_config.load_config()["niches"][0]
check("sua niche KHONG lam mat phan da hoc", saved["description"] == "Mo ta moi" and "anglerfish" in saved.get("learned", {}).get("terms", []))
check("resolve_profile_niches mang theo learned cho phien chay",
      "anglerfish" in cm.normalize_niche(app.resolve_profile_niches(["pid-x"])["pid-x"])["learned_tokens"])

after = {e["key"]: e for e in nl.pool_load()}
check("hoc niche da tu xoay qua key het quota (key 1) sang key con dung (key 2)",
      any(str(c[2]) == "QUOTA" for c in CALLS) and saved.get("learned", {}).get("videos") == 12)
check("kho key ghi lai: key 1 'het quota', key 2 'dung duoc' + vua dung", after[K2]["status"] == "quota"
      and after[SECRET]["status"] == "ok" and after[SECRET]["used"] > 0, str({k[:6]: v["status"] for k, v in after.items()}))
check("dong tom tat hop Niche phan anh kho moi", "1 dùng được" in lbl_key.cget("text") and "1 hết quota hôm nay" in lbl_key.cget("text"))
BADLONG = "BADKEY_da_bi_thu_hoi_00000000000000003"
pool3 = []
nl.pool_add(pool3, [BADLONG])
nl.pool_save(pool3)
buttons["Học niche từ kênh đối thủ"].invoke()
check("key sai -> bao loi ro, giu phan da hoc cu", pump(lambda: "thất bại" in status.cget("text")) and "KEY SAI" in status.cget("text")
      and "anglerfish" in app.cfg["niches"][0]["learned"]["terms"], status.cget("text"))
check("key sai duoc danh dau trong kho", nl.pool_load()[0]["status"] == "invalid")
buttons["Học niche từ kênh đối thủ"].invoke()
check("moi key deu hong -> bao ro, khong goi API nua", "Cả 1 key đều đang hết quota hoặc hỏng" in status.cget("text")
      and not buttons["Học niche từ kênh đối thủ"].instate(["disabled"]))

# ---- v1.10.0: o chon AI + AI tu dien cac o con trong
cbo_ai = [w for w in walk(nd) if isinstance(w, ttk.Combobox)][0]
vals = list(cbo_ai.cget("values"))
check("co o 'AI phân tích': mac dinh tu chon (uu tien Claude), co claude + 'Không dùng AI'",
      cbo_ai.get() == "Tự chọn (ưu tiên Claude)" and "claude-sonnet" in vals and vals[-1] == "Không dùng AI" and "none" not in vals)
PICK = {"cands": None, "brain": FakeBrain(analysis=ANALYSIS)}


def _pick(cands, log=None):
    PICK["cands"] = list(cands)
    PICK.setdefault("calls", []).append(list(cands))
    for c in cands:
        if c not in PICK.get("dead", {}):
            return PICK["brain"], c, ""
    return None, "", PICK["dead"][cands[0]]


ui._pick_live_brain = _pick
ui._brain_candidates_from_env = lambda: ["custom:DEEPSEEK", "claude-sonnet", "gemini"]
nl.pool_save([{"key": SECRET, "status": "new", "msg": "", "checked": 0.0, "used": 0.0}])
buttons["+ Niche mới"].invoke()
entries[0].insert(0, "AI Niche")
texts[1].insert("1.0", "@oceanlab\n" + UC_B)
buttons["Học niche từ kênh đối thủ"].invoke()
check("AI phan tich xong", pump(lambda: "Đã học niche 'AI Niche'" in status.cget("text"), 15), status.cget("text"))
check("tu chon -> 2 tai khoan dang nhap dung dau; KHONG tu roi ve API Claude khi da co tai khoan Claude",
      PICK["cands"][:2] == ["claude-account", "chatgpt-account"] and "claude-sonnet" not in PICK["cands"]
      and "gemini" in PICK["cands"], str(PICK["cands"]))
nai = [n for n in app_config.load_config()["niches"] if n["name"] == "AI Niche"][0]
check("AI TU DIEN o con trong: tu khoa + mo ta + tu loai tru", nai["keywords"][:1] == ["deep sea creatures documentary"]
      and len(nai["keywords"]) == 5 and nai["description"].startswith("Deep-sea documentaries")
      and nai["negative"] == ["minecraft", "kids", "aquarium tour"], str(nai["keywords"]))
check("form hien ngay tu khoa AI vua dien", "anglerfish hunting footage" in texts[0].get("1.0", "end") and entries[2].get().startswith("minecraft"))
check("thong bao noi ro AI nao + da dien gi", "AI Claude tài khoản đã phân tích và điền sẵn: 5 từ khóa đuôi dài, mô tả, 3 từ loại trừ" in status.cget("text"),
      status.cget("text"))
rws = [w for w in root.winfo_children() if isinstance(w, tk.Toplevel) and w.title().startswith("Kết quả học niche")]
rb = {str(b.cget("text")): b for b in walk(rws[-1]) if isinstance(b, ttk.Button)}
rt = [w for w in walk(rws[-1]) if isinstance(w, tk.Text)][0].get("1.0", "end")
check("cua so ket qua co muc phan tich cua AI + nut 'Chép tag'", "PHÂN TÍCH CỦA AI (Claude tài khoản)" in rt and "Chép tag" in rb)
rb["Chép tag"].invoke()
root.update()
check("'Chép tag' dua tag AI vao clipboard", root.clipboard_get() == "deep sea, anglerfish, hadal zone, ocean documentary")
rb["Đóng"].invoke()

texts[0].delete("1.0", "end")
texts[0].insert("1.0", "tu khoa cua toi")
entries[1].delete(0, "end")
entries[1].insert(0, "Mo ta cua toi")
buttons["Học niche từ kênh đối thủ"].invoke()
pump(lambda: "Đã học niche 'AI Niche'" in status.cget("text") and not buttons["Học niche từ kênh đối thủ"].instate(["disabled"]), 15)
nai = [n for n in app_config.load_config()["niches"] if n["name"] == "AI Niche"][0]
check("hoc lai: KHONG de len tu khoa / mo ta user da nhap", nai["keywords"] == ["tu khoa cua toi"] and nai["description"] == "Mo ta cua toi"
      and "xem ở cửa sổ kết quả" in status.cget("text"), status.cget("text"))
rws = [w for w in root.winfo_children() if isinstance(w, tk.Toplevel) and w.title().startswith("Kết quả học niche")]
rb = {str(b.cget("text")): b for b in walk(rws[-1]) if isinstance(b, ttk.Button)}
rb["Thêm từ khóa gợi ý vào niche"].invoke()
root.update()
nai = [n for n in app_config.load_config()["niches"] if n["name"] == "AI Niche"][0]
check("'Thêm từ khóa gợi ý' them tu khoa AI truoc roi toi tag thong ke, khong trung", nai["keywords"][0] == "tu khoa cua toi"
      and nai["keywords"][1] == "deep sea creatures documentary" and len(set(nai["keywords"])) == len(nai["keywords"]), str(nai["keywords"]))
rb["Đóng"].invoke()

cbo_ai.set("Không dùng AI")
cbo_ai.event_generate("<<ComboboxSelected>>")
root.update()
check("chon AI duoc luu vao config", app_config.load_config().get("niche_ai") == "Không dùng AI")
PICK["cands"] = "chua goi"
buttons["Học niche từ kênh đối thủ"].invoke()
pump(lambda: "Đã học niche 'AI Niche'" in status.cget("text") and not buttons["Học niche từ kênh đối thủ"].instate(["disabled"]), 15)
check("'Không dùng AI' -> khong goi AI nao, van hoc theo thong ke", PICK["cands"] == "chua goi"
      and [n for n in app_config.load_config()["niches"] if n["name"] == "AI Niche"][0]["learned"]["ai"] == {})
cbo_ai.set("gemini")
cbo_ai.event_generate("<<ComboboxSelected>>")
buttons["Học niche từ kênh đối thủ"].invoke()
pump(lambda: PICK["cands"] != "chua goi" and not buttons["Học niche từ kênh đối thủ"].instate(["disabled"]), 15)
check("chon han 1 AI -> AI do dung dau, tai khoan Claude du phong", PICK["cands"][:2] == ["gemini", "claude-account"], str(PICK["cands"]))
for _w in [w for w in root.winfo_children() if isinstance(w, tk.Toplevel) and w.title().startswith("Kết quả học niche")]:
    _w.destroy()
cbo_ai.set("Tự chọn (ưu tiên Claude)")
cbo_ai.event_generate("<<ComboboxSelected>>")
check("ve 'tu chon' -> config luu rong", app_config.load_config().get("niche_ai") == "")

# ---- v1.11.0 -> v1.12.0: 2 AI song song (Claude + ChatGPT) bang TAI KHOAN DANG NHAP
DUAL = "Claude + ChatGPT — tài khoản (song song, đối chiếu)"
check("o chon AI: 2 tai khoan song song dung ngay sau 'Tu chon', co tung tai khoan rieng + Claude tai khoan + Gemini",
      vals.index(DUAL) == 1 and vals[2:4] == ["Claude — tài khoản đăng nhập", "ChatGPT — tài khoản đăng nhập"]
      and "Claude tài khoản + Gemini (song song, đối chiếu)" in vals and "Claude + ChatGPT (song song, đối chiếu)" not in vals, str(vals[:6]))
cbo_ai.set(DUAL)
cbo_ai.event_generate("<<ComboboxSelected>>")
check("che do 2 AI duoc luu vao config", app_config.load_config().get("niche_ai") == DUAL)
PICK["calls"], PICK["dead"] = [], {}
_http_fast = nl._urllib_http
nl._urllib_http = lambda path, params: (time.sleep(0.2), fake_http(path, params))[1]      # hoc cham lai de bat duoc dong "dang hoc"
buttons["Học niche từ kênh đối thủ"].invoke()
import re as _re194
check("dang hoc: dong trang thai co DONG HO + buoc hien tai", pump(lambda: _re194.match(r"Đang học \(\d+:\d\d\) — \S", status.cget("text")) is not None, 15),
      status.cget("text"))
nl._urllib_http = _http_fast
pump(lambda: PICK["calls"] and not buttons["Học niche từ kênh đối thủ"].instate(["disabled"]), 20)
check("2 AI: kiem tra tai khoan Claude va tai khoan ChatGPT rieng (khong dung API key)",
      sorted(PICK["calls"][:2]) == [["chatgpt-account"], ["claude-account"]], str(PICK["calls"]))
lai = [n for n in app_config.load_config()["niches"] if n["name"] == "AI Niche"][0]["learned"]["ai"]
check("2 AI deu song -> phan tich doi chieu cheo, status + learned ghi ro", lai["brain"] == "Claude tài khoản + ChatGPT tài khoản (đối chiếu chéo)"
      and "AI Claude tài khoản + ChatGPT tài khoản (đối chiếu chéo) đã phân tích" in status.cget("text") and "LƯU Ý" not in status.cget("text"), status.cget("text"))
# ---- v1.12.1: xem doi thoai 2 AI
def _dwins():
    return [w for w in root.winfo_children() if isinstance(w, tk.Toplevel) and w.title().startswith("Đối thoại 2 AI")]


check("hop Niche co nut 'Xem đối thoại 2 AI' canh 'Xem kết quả học'", "Xem đối thoại 2 AI" in {str(b.cget("text")) for b in walk(nd) if isinstance(b, ttk.Button)})
_spin = [w for w in walk(nd) if isinstance(w, ttk.Spinbox)][0]
check("co o 'Tranh luận tới khi chốt · tối đa vòng/chủ đề', mac dinh 5 (khoa config moi, khong dung so vong cu)",
      _spin.get() == "5" and any("Tranh luận tới khi chốt · tối đa vòng/chủ đề (0 = tắt)" in str(w.cget("text")) for w in walk(nd) if isinstance(w, tk.Label))
      and app_config.DEFAULTS["niche_debate_cap"] == 5 and int(_spin.cget("to")) == 10)
check("khung chat TU MO luc 2 AI chay va o lai sau khi xong (doi ten 'Đối thoại 2 AI — …', bao 'Xong sau')",
      len(_dwins()) == 1 and _dwins()[0].title() == "Đối thoại 2 AI — AI Niche"
      and any("Xong sau" in str(w.cget("text")) and "16 lượt nói" in str(w.cget("text")) for w in walk(_dwins()[0]) if isinstance(w, tk.Label)),
      str([w.title() for w in root.winfo_children() if isinstance(w, tk.Toplevel)]))
_live_bub = [w for w in walk([w for w in walk(_dwins()[0]) if isinstance(w, tk.Text)][0]) if isinstance(w, tk.Label)]
check("khung chat truc tiep da nhan du: loi dan + 16 luot + 8 loi dan chu de + loi ket; nut 'chot luon' da go",
      len(_live_bub) == 26 and "Bot gộp 2 bản cuối" in str(_live_bub[-1].cget("text"))
      and not any("chốt luôn" in str(b.cget("text")) for b in walk(_dwins()[0]) if isinstance(b, ttk.Button)), str(len(_live_bub)))
_ln194 = [n for n in app_config.load_config()["niches"] if n["name"] == "AI Niche"][0]["learned"]
check("hoc that tu giao dien: da ghep anh thumbnail doi thu (khong ra mang trong test) + luu lich 4 chu de",
      len(THUMB_URLS) >= 4 and os.path.isfile(_ln194["thumbs"]["path"]) and _ln194["thumbs"]["path"].startswith(DATA_DIR)
      and [a["why"] for a in _ln194["ai"]["agenda"]] == ["settled"] * 4 and _ln194["ai"]["debate_cap"] == 5, str(_ln194.get("thumbs"))[:160])
_rw = [w for w in root.winfo_children() if isinstance(w, tk.Toplevel) and w.title().startswith("Kết quả học niche")][-1]
_rb = {str(b.cget("text")): b for b in walk(_rw) if isinstance(b, ttk.Button)}
check("cua so ket qua (lan hoc co 2 AI) co nut 'Xem đối thoại 2 AI'", "Xem đối thoại 2 AI" in _rb)
_opened194, _sf194 = [], getattr(os, "startfile", None)
os.startfile = _opened194.append
_rb["Xem ảnh thumbnail"].invoke()
os.startfile = _sf194
_rt194 = [w for w in walk(_rw) if isinstance(w, tk.Text)][0].get("1.0", "end")
check("cua so ket qua: nut 'Xem ảnh thumbnail' mo dung anh ghep (AI gia khong neu nhan dinh thumbnail -> bao cao khong in bang so)",
      _opened194 == [_ln194["thumbs"]["path"]] and "Số thumbnail AI nhắc tới" not in _rt194 and "PHÂN TÍCH CỦA AI" in _rt194, str(_opened194))
_rb["Xem đối thoại 2 AI"].invoke()
root.update()
check("bam -> mo cua so doi thoai", len(_dwins()) == 1 and _dwins()[0].title() == "Đối thoại 2 AI — AI Niche")
_dt = [w for w in walk(_dwins()[0]) if isinstance(w, tk.Text)][0]
_heads = [l for l in _dt.get("1.0", "end").split("\n") if l.strip()]
_bub = [w for w in walk(_dt) if isinstance(w, tk.Label)]
check("KHUNG CHAT: 16 dong ten (ai noi - chu de - luot - gui ai - trang thai), chi doc", len(_heads) == 16 and str(_dt.cget("state")) == "disabled"
      and _heads[0].startswith("Claude tài khoản") and _heads[0].endswith("Vòng 1 · phân tích riêng")
      and _heads[1].startswith("ChatGPT tài khoản") and _heads[2].endswith("ĐÁNH GIÁ NICHE · lượt 1 · gửi ChatGPT tài khoản · còn tranh luận")
      and _heads[3].endswith("ĐÁNH GIÁ NICHE · lượt 2 · gửi Claude tài khoản · ĐÃ CHỐT") and _heads[4].endswith("ĐÁNH GIÁ NICHE · lượt 3 · gửi ChatGPT tài khoản · ĐÃ CHỐT")
      and _heads[5].startswith("ChatGPT tài khoản") and _heads[5].endswith("ĐẶC ĐIỂM NICHE · lượt 1 · gửi Claude tài khoản · còn tranh luận")
      and _heads[8].endswith("GÓI SEO · lượt 1 · gửi ChatGPT tài khoản · còn tranh luận") and _heads[13].endswith("THUMBNAIL · lượt 3 · gửi Claude tài khoản · ĐÃ CHỐT")
      and _heads[14].endswith("Chốt lại · gửi ChatGPT tài khoản") and _heads[15].endswith("Chốt lại · gửi Claude tài khoản"), str(_heads))
check("khung chat: 26 khung (loi dan + 2 phan tich + 4 chu de x (mo + 3 luot + chot) + 2 ban chot + ket qua gop), moi luot la 1 bong chat",
      len(_bub) == 26 and "TRANH LUẬN TỚI CÙNG theo 4 chủ đề" in str(_bub[0].cget("text")) and "tối đa 5 vòng mỗi chủ đề" in str(_bub[0].cget("text"))
      and "Theo tôi, niche này là:" in str(_bub[1].cget("text")) and str(_bub[3].cget("text")).startswith("▶ Chủ đề 1/4 — ĐÁNH GIÁ NICHE")
      and str(_bub[4].cget("text")) == "Toi phan doi." and str(_bub[7].cget("text")) == "✔ ĐÁNH GIÁ NICHE: hai bên đã chốt sau 3 lượt nói."
      and str(_bub[18].cget("text")).startswith("▶ Chủ đề 4/4 — THUMBNAIL") and "sau khi tranh luận, tôi chốt lại" in str(_bub[23].cget("text"))
      and "Bot gộp 2 bản cuối" in str(_bub[25].cget("text")), [str(b.cget("text"))[:40] for b in _bub])
check("AI thu nhat ben TRAI, AI thu hai ben PHAI, loi dan (ca loi dan chu de) o GIUA; 2 ben khac mau",
      "name0" in _dt.tag_names(_dt.search("Claude tài khoản", "1.0")) and "name1" in _dt.tag_names(_dt.search("ChatGPT tài khoản", "1.0"))
      and all("left" in _dt.tag_names(_bub[i]) for i in (1, 4, 6, 10, 14, 16, 20, 23))
      and all("right" in _dt.tag_names(_bub[i]) for i in (2, 5, 9, 11, 15, 19, 21, 24))
      and all("center" in _dt.tag_names(_bub[i]) for i in (0, 3, 7, 8, 12, 13, 17, 18, 22, 25)) and str(_bub[1].cget("bg")) != str(_bub[2].cget("bg")))
_db = {str(b.cget("text")): b for b in walk(_dwins()[0]) if isinstance(b, ttk.Button)}
_db["Chép toàn bộ"].invoke()
root.update()
check("'Chép toàn bộ' dua ca doi thoai vao clipboard", root.clipboard_get().startswith("ĐỐI THOẠI GIỮA 2 AI") and "■ ChatGPT tài khoản" in root.clipboard_get()
      and "ĐẶC ĐIỂM NICHE · lượt 1 · gửi Claude tài khoản · còn tranh luận" in root.clipboard_get()
      and "— ▶ Chủ đề 3/4 — GÓI SEO" in root.clipboard_get() and "Chốt lại · gửi Claude tài khoản" in root.clipboard_get())
_db["Đóng"].invoke()
root.update()
buttons2 = {str(b.cget("text")): b for b in walk(nd) if isinstance(b, ttk.Button)}
buttons2["Xem đối thoại 2 AI"].invoke()
root.update()
check("nut o hop Niche cung mo duoc doi thoai cua niche dang chon", len(_dwins()) == 1)
for _w in _dwins():
    _w.destroy()
for _w in [w for w in root.winfo_children() if isinstance(w, tk.Toplevel) and w.title().startswith("Kết quả học niche")]:
    _w.destroy()

# ---- v1.14.0: khung chat hien TRUC TIEP luc 2 AI dang dau tri (brain cham de bat duoc trang thai giua chung)
class SlowBrain(FakeBrain):
    def ask_text(self, prompt):
        time.sleep(0.35)
        return FakeBrain.ask_text(self, prompt)


def _wins(prefix):
    return [w for w in root.winfo_children() if isinstance(w, tk.Toplevel) and w.title().startswith(prefix)]


_fast_brain = PICK["brain"]
PICK["brain"] = SlowBrain(analysis=ANALYSIS)
_spin.set("1")
_spin.event_generate("<FocusOut>")
root.update()
check("doi so vong toi da -> luu config (khoa moi niche_debate_cap)", app_config.load_config().get("niche_debate_cap") == 1)
PICK["calls"], PICK["dead"] = [], {}
buttons["Học niche từ kênh đối thủ"].invoke()
check("DANG CHAY: khung chat tu mo voi tieu de '(đang diễn ra)'", pump(lambda: len(_wins("Đấu trí 2 AI — AI Niche (đang diễn ra)")) == 1, 15))
_lw = _wins("Đấu trí 2 AI")[0]
_lt = [w for w in walk(_lw) if isinstance(w, tk.Text)][0]


def _lbub():
    return [w for w in walk(_lt) if isinstance(w, tk.Label)]


def _lnote():
    return " | ".join(str(w.cget("text")) for w in walk(_lw) if isinstance(w, tk.Label) and w.master is not _lt)


check("dang chay: dong 'dang soan…' co ten AI + dem giay", pump(lambda: "✍" in _lnote() and "giây)" in _lnote(), 10), _lnote())
check("dang chay: tung luot HIEN DAN (da co luot phan tich nhung chua du 12 luot)", pump(lambda: 3 <= len(_lbub()) < 20, 10), str(len(_lbub())))
check("dang chay: thay luc 1 ben dang soan loi ve chu de nao", pump(lambda: "đang soạn lời về ĐÁNH GIÁ NICHE (lượt" in _lnote(), 10), _lnote())
_lb = {str(b.cget("text")): b for b in walk(_lw) if isinstance(b, ttk.Button)}
check("dang chay: co nut 'Dừng tranh luận — chốt luôn' trong khung chat", "Dừng tranh luận — chốt luôn" in _lb, str(list(_lb)))
_lb["Chép toàn bộ"].invoke()
root.update()
check("dang chay ma bam 'Chép toàn bộ' -> bao chua xong, khong loi", "chưa xong" in _lnote(), _lnote())
pump(lambda: not buttons["Học niche từ kênh đối thủ"].instate(["disabled"]), 30)
root.update()
check("xong (toi da 1 vong / chu de, chua cung chot): 22 khung (loi dan + 2 + 4 x (mo + 2 luot + het vong) + 2 chot + loi ket), doi tieu de, bao thoi gian",
      len(_lbub()) == 22 and _lw.title() == "Đối thoại 2 AI — AI Niche" and "Xong sau" in _lnote() and "12 lượt nói" in _lnote()
      and not any("chốt luôn" in str(b.cget("text")) for b in walk(_lw) if isinstance(b, ttk.Button))
      and any(str(b.cget("text")).startswith("⏹ ĐÁNH GIÁ NICHE: hết 1 vòng mà hai bên CHƯA cùng chốt") for b in _lbub()),
      f"{len(_lbub())} {_lw.title()} {_lnote()}")
_lh = [l for l in _lt.get("1.0", "end").split("\n") if l.strip()]
check("xong: thu tu luot noi dung kieu tranh luan theo chu de (ben mo loi luan phien)", len(_lh) == 12 and _lh[2].startswith("Claude tài khoản")
      and _lh[2].endswith("ĐÁNH GIÁ NICHE · lượt 1 · gửi ChatGPT tài khoản · còn tranh luận")
      and _lh[3].startswith("ChatGPT tài khoản") and _lh[3].endswith("ĐÁNH GIÁ NICHE · lượt 2 · gửi Claude tài khoản · ĐÃ CHỐT")
      and _lh[4].startswith("ChatGPT tài khoản") and _lh[4].endswith("ĐẶC ĐIỂM NICHE · lượt 1 · gửi Claude tài khoản · còn tranh luận")
      and sorted(x.split("—")[-1].strip() for x in _lh[10:]) == ["Chốt lại · gửi ChatGPT tài khoản", "Chốt lại · gửi Claude tài khoản"],
      str(_lh))       # 2 ban chot viet SONG SONG -> ben nao xong truoc hien truoc
# v1.16.0: nut 'Dừng tranh luận — chốt luôn' — 2 AI khong bao gio chot (toi da 5 vong x 4 chu de = 40 luot) nhung nguoi dung cho dung
for _w in _wins("Kết quả học niche") + _wins("Đối thoại 2 AI"):
    _w.destroy()


class NeverBrain(SlowBrain):
    def ask_text(self, prompt):
        if "LIVE DEBATE" in prompt:
            time.sleep(0.25)
            return "Toi van phan doi."
        return SlowBrain.ask_text(self, prompt)


PICK["brain"] = NeverBrain(analysis=ANALYSIS)
_spin.set("5")
_spin.event_generate("<FocusOut>")
root.update()
PICK["calls"], PICK["dead"] = [], {}
buttons["Học niche từ kênh đối thủ"].invoke()
pump(lambda: len(_wins("Đấu trí 2 AI — AI Niche (đang diễn ra)")) == 1, 15)
_fw = _wins("Đấu trí 2 AI")[0]


def _fbtn():
    return [b for b in walk(_fw) if isinstance(b, ttk.Button) and "chốt luôn" in str(b.cget("text"))]


pump(lambda: bool(_fbtn()) and len([w for w in walk([x for x in walk(_fw) if isinstance(x, tk.Text)][0]) if isinstance(w, tk.Label)]) >= 6, 15)
_fbtn()[0].invoke()
root.update()
check("bam 'Dừng tranh luận — chốt luôn' -> nut khoa lai, doi nhan 'Đang chốt…'", [str(b.cget("text")) for b in walk(_fw) if isinstance(b, ttk.Button)
                                                                                 and b.instate(["disabled"])] == ["Đang chốt…"])
pump(lambda: not buttons["Học niche từ kênh đối thủ"].instate(["disabled"]), 30)
root.update()
_fa = [n for n in app_config.load_config()["niches"] if n["name"] == "AI Niche"][0]["learned"]["ai"]
check("chot luon: tranh luan dung som (khong chay het 40 luot), van co 2 ban chot + loi dan 'Bạn cho dừng tranh luận', nut bien mat",
      0 < len([t for t in _fa["dialog"] if t["kind"] == "debate"]) < 40 and [t["kind"] for t in _fa["dialog"][-2:]] == ["final", "final"]
      and any(t["kind"] == "note" and "Bạn cho dừng tranh luận" in t["text"] for t in _fa["dialog"])
      and "stopped" in [a["why"] for a in _fa["agenda"]] and not _fbtn() and "Xong sau" in " ".join(
          str(w.cget("text")) for w in walk(_fw) if isinstance(w, tk.Label)), str([a["why"] for a in _fa["agenda"]]))
for _w in _wins("Kết quả học niche") + _wins("Đối thoại 2 AI"):
    _w.destroy()
PICK["brain"] = _fast_brain
_spin.set("0")
_spin.event_generate("<FocusOut>")
PICK["calls"], PICK["dead"] = [], {}
buttons["Học niche từ kênh đối thủ"].invoke()
pump(lambda: PICK["calls"] and not buttons["Học niche từ kênh đối thủ"].instate(["disabled"]), 20)
root.update()
_l0 = [n for n in app_config.load_config()["niches"] if n["name"] == "AI Niche"][0]["learned"]["ai"]["dialog"]
check("vong dau tri = 0 -> y nhu truoc: 4 luot (phan tich + doc cheo), khung chat van hien", [t["kind"] for t in _l0] == ["analysis", "analysis", "final", "final"]
      and len(_dwins()) == 1 and "4 lượt nói" in " ".join(str(w.cget("text")) for w in walk(_dwins()[0]) if isinstance(w, tk.Label)))
for _w in _wins("Kết quả học niche") + _wins("Đối thoại 2 AI"):
    _w.destroy()
_spin.set("2")
_spin.event_generate("<FocusOut>")
root.update()
PICK["calls"], PICK["dead"] = [], {"chatgpt-account": "HẾT HẠN MỨC"}
buttons["Học niche từ kênh đối thủ"].invoke()
pump(lambda: PICK["calls"] and not buttons["Học niche từ kênh đối thủ"].instate(["disabled"]), 20)
lrn = [n for n in app_config.load_config()["niches"] if n["name"] == "AI Niche"][0]["learned"]
check("ChatGPT het han muc -> Claude phan tich mot minh + bao ro ly do va cach xu ly (nut Tai khoan AI, khong nhac API key)",
      lrn["ai"]["brain"] == "Claude tài khoản"
      and "ChatGPT không dùng được (HẾT HẠN MỨC)" in status.cget("text") and "KHÔNG có đối chiếu chéo" in status.cget("text")
      and "Tài khoản AI…" in status.cget("text") and "API key" not in status.cget("text")
      and "ChatGPT không dùng được" in lrn["ai"]["note"], status.cget("text"))
buttons2["Xem đối thoại 2 AI"].invoke()
root.update()
check("lan hoc chi co 1 AI -> khong mo cua so, dong trang thai chi cach de co doi thoai", not _dwins()
      and "chưa có đối thoại 2 AI" in status.cget("text") and "Claude + ChatGPT — tài khoản" in status.cget("text"), status.cget("text"))
_rb1 = {str(b.cget("text")) for b in walk([w for w in root.winfo_children() if isinstance(w, tk.Toplevel)
                                           and w.title().startswith("Kết quả học niche")][-1]) if isinstance(b, ttk.Button)}
check("cua so ket qua cua lan hoc 1 AI khong co nut doi thoai", "Xem đối thoại 2 AI" not in _rb1)
for _w in [w for w in root.winfo_children() if isinstance(w, tk.Toplevel) and w.title().startswith("Kết quả học niche")]:
    _w.destroy()
PICK["calls"], PICK["dead"] = [], {"chatgpt-account": "HẾT HẠN MỨC", "claude-account": "CHƯA ĐĂNG NHẬP"}
buttons["Học niche từ kênh đối thủ"].invoke()
pump(lambda: len(PICK["calls"]) >= 3 and not buttons["Học niche từ kênh đối thủ"].instate(["disabled"]), 20)
lrn = [n for n in app_config.load_config()["niches"] if n["name"] == "AI Niche"][0]["learned"]
check("ca 2 tai khoan chet -> thu AI khac con key (khong hoi lai 2 tai khoan, khong dung API Claude), co ghi chu",
      PICK["calls"][2] == ["custom:DEEPSEEK", "gemini"] and lrn["ai"].get("brain") == "custom:DEEPSEEK"
      and "đều không dùng được" in status.cget("text"), f"{PICK['calls']} {status.cget('text')}")
for _w in [w for w in root.winfo_children() if isinstance(w, tk.Toplevel) and w.title().startswith("Kết quả học niche")]:
    _w.destroy()
PICK["dead"] = {}

# ---- v1.14.1: kiem tra 2 AI chay NEN - 2 AI cung luc, va cung luc voi viec doc kenh
TL = {"pick": [], "http": []}


def _pick_timed(cands, log=None):
    t0 = time.time()
    time.sleep(0.5)
    TL["pick"].append((t0, time.time(), list(cands)))
    return _fast_brain, cands[0], ""


def _http_timed(path, params):
    time.sleep(0.12)
    r = fake_http(path, params)
    TL["http"].append(time.time())
    return r


_pick_keep, _http_keep = ui._pick_live_brain, nl._urllib_http
ui._pick_live_brain, nl._urllib_http = _pick_timed, _http_timed
buttons["Học niche từ kênh đối thủ"].invoke()
pump(lambda: len(TL["pick"]) >= 2 and not buttons["Học niche từ kênh đối thủ"].instate(["disabled"]), 25)
ui._pick_live_brain, nl._urllib_http = _pick_keep, _http_keep
_pk = sorted(TL["pick"])
check("kiem tra 2 AI CUNG LUC (2 luot chong thoi gian len nhau, moi tai khoan 1 luot)", len(_pk) == 2 and _pk[1][0] < _pk[0][1]
      and sorted(x[2] for x in _pk) == [["chatgpt-account"], ["claude-account"]], str([(round(a - _pk[0][0], 2), round(b - _pk[0][0], 2), c) for a, b, c in _pk]))
check("kiem tra AI chay CUNG LUC voi viec doc kenh (bat dau truoc khi doc xong kenh)", len(TL["http"]) >= 2 and _pk[0][0] < TL["http"][-1]
      and _pk[0][0] <= TL["http"][0], f"pick {_pk[0][0]:.2f} http {TL['http'][0]:.2f}..{TL['http'][-1]:.2f}" if _pk and TL["http"] else "thieu moc")
lai2 = [n for n in app_config.load_config()["niches"] if n["name"] == "AI Niche"][0]["learned"]["ai"]
check("kiem tra nen xong -> van phan tich doi chieu cheo bang 2 tai khoan nhu cu", lai2["brain"] == "Claude tài khoản + ChatGPT tài khoản (đối chiếu chéo)"
      and len(lai2["dialog"]) >= 4 and "LƯU Ý" not in status.cget("text"), status.cget("text"))
for _w in [w for w in root.winfo_children() if isinstance(w, tk.Toplevel) and w.title().startswith("Kết quả học niche")]:
    _w.destroy()

# ---- v1.12.0: dai "AI phan tich" + cua so "Tai khoan AI"
def _nd_labels():
    return [w for w in walk(nd) if isinstance(w, tk.Label)]


check("dai AI hien tinh trang dang nhap cua 2 tai khoan",
      pump(lambda: any("Claude: đã đăng nhập · gói max" in str(w.cget("text")) and "ChatGPT: đã đăng nhập" in str(w.cget("text"))
                       for w in _nd_labels()), 5))
check("quy uoc nhan khong doi: tk.Label cuoi = status, ap cuoi = tom tat key", _nd_labels()[-1] is status and _nd_labels()[-2] is lbl_key)
check("o chon AI nam trong dai AI, khong con o hang nut day", cbo_ai.master is not buttons["Lưu niche"].master
      and buttons["Tài khoản AI…"].master is cbo_ai.master)
buttons["Tài khoản AI…"].invoke()
root.update()
aws = [w for w in root.winfo_children() if isinstance(w, tk.Toplevel) and w.title().startswith("Tài khoản AI")]
check("nut 'Tài khoản AI…' mo cua so tai khoan", len(aws) == 1)
aw = aws[0]


def _atexts():
    return [str(w.cget("text")) for w in walk(aw) if isinstance(w, tk.Label)]


abtn = [b for b in walk(aw) if isinstance(b, ttk.Button)]
tries = [b for b in abtn if b.cget("text") == "Thử hỏi 1 câu"]
logins = [b for b in abtn if b.cget("text") in ("Đăng nhập…", "Đăng nhập lại…")]
_mcb = [w for w in walk(aw) if isinstance(w, ttk.Combobox)]
check("2 hang Claude + ChatGPT deu 'Sẵn sàng'; KHONG co o nhap key nao (chi 2 o chon model)", sum("Sẵn sàng — " in t for t in _atexts()) == 2
      and len(tries) == 2 and len(logins) == 2 and len(_mcb) == 2
      and not [w for w in walk(aw) if isinstance(w, (tk.Entry, ttk.Entry, tk.Text)) and not isinstance(w, ttk.Combobox)], str(_atexts()))
check("o Model: Claude mac dinh sonnet + co opus/fable/haiku; ChatGPT mac dinh 'Tự chọn' + model Codex liet ke",
      _mcb[0].get() == "sonnet" and list(_mcb[0].cget("values")) == ["sonnet", "opus", "fable", "haiku"]
      and _mcb[1].get() == "Tự chọn" and list(_mcb[1].cget("values")) == ["Tự chọn", "gpt-a", "gpt-b"], f"{_mcb[0].get()} {_mcb[1].cget('values')}")
_mcb[0].set("opus")
_mcb[0].event_generate("<<ComboboxSelected>>")
root.update()
check("chon model Claude -> luu config + ap ngay cho lan phan tich toi", app_config.load_config().get("claude_account_model") == "opus"
      and os.environ.get("CLAUDE_CLI_MODEL") == "opus" and any("sẽ dùng model opus" in t for t in _atexts()))
_mcb[1].set("gpt-b")
_mcb[1].event_generate("<<ComboboxSelected>>")
root.update()
check("chon model ChatGPT -> luu config + bien moi truong", app_config.load_config().get("chatgpt_account_model") == "gpt-b"
      and os.environ.get("CODEX_CLI_MODEL") == "gpt-b")
_mcb[1].set("ten sai; rm -rf")
_mcb[1].event_generate("<FocusOut>")
root.update()
check("ten model co ky tu la -> tu choi, giu model cu", app_config.load_config().get("chatgpt_account_model") == "gpt-b"
      and os.environ.get("CODEX_CLI_MODEL") == "gpt-b" and any("Tên model chỉ gồm" in t for t in _atexts()))
_mcb[1].set("Tự chọn")
_mcb[1].event_generate("<<ComboboxSelected>>")
_mcb[0].set("")
_mcb[0].event_generate("<FocusOut>")
root.update()
check("'Tự chọn' / de trong -> ve mac dinh (Claude sonnet, ChatGPT de Codex tu chon)", app_config.load_config().get("chatgpt_account_model") == ""
      and "CODEX_CLI_MODEL" not in os.environ and app_config.load_config().get("claude_account_model") == "sonnet"
      and os.environ.get("CLAUDE_CLI_MODEL") == "sonnet" and _mcb[0].get() == "sonnet")
check("noi ro: tai khoan, khong API key", any("Không cần API key" in t for t in _atexts()))
check("tai khoan DANG dang nhap -> nut doi thanh 'Đăng nhập lại…'", [str(b.cget("text")) for b in logins] == ["Đăng nhập lại…"] * 2)
_ask3, ASKED = ui.messagebox.askyesno, []
ui.messagebox.askyesno = lambda *a, **k: (ASKED.append(a), False)[1]
logins[1].invoke()
root.update()
check("bam 'Đăng nhập lại…' -> HOI truoc (dang nhap lai huy phien cu); tra loi Khong -> khong mo dang nhap",
      LOGIN == [] and len(ASKED) == 1 and "ĐANG đăng nhập rồi" in ASKED[0][1] and "bị hủy ngay" in ASKED[0][1]
      and any("Giữ nguyên phiên đăng nhập hiện tại của ChatGPT tài khoản" in t for t in _atexts()), str(ASKED))
ui.messagebox.askyesno = lambda *a, **k: (ASKED.append(a), True)[1]
logins[1].invoke()
root.update()
ui.messagebox.askyesno = _ask3
check("tra loi Co -> mo man hinh dang nhap cua dung cong cu + dan 'xong moi hoc niche'", LOGIN == ["chatgpt-account"]
      and any("Đã mở cửa sổ đăng nhập ChatGPT tài khoản" in t and "xong mới bấm 'Học niche'" in t for t in _atexts()), str(LOGIN))
tries[0].invoke()
check("'Thử hỏi 1 câu' hoi 1 cau va bao ket qua", pump(lambda: any("Claude tài khoản trả lời được" in t for t in _atexts()), 5)
      and len(TRY) == 1)
buttons["Tài khoản AI…"].invoke()
root.update()
check("bam lan 2 khong mo them cua so", len([w for w in root.winfo_children() if isinstance(w, tk.Toplevel)
                                             and w.title().startswith("Tài khoản AI")]) == 1)
ACC["g"] = {"installed": False, "logged_in": False, "plan": "", "who": "", "path": "", "detail": "chưa cài Codex (công cụ của ChatGPT)"}
[b for b in abtn if b.cget("text") == "Kiểm tra lại"][0].invoke()
check("ChatGPT chua cai -> huong dan cai + khoa 2 nut cua hang do; dai AI trong hop Niche doi theo",
      pump(lambda: any("CHƯA CÀI Codex" in t and "npm install -g @openai/codex" in t for t in _atexts()), 5)
      and tries[1].instate(["disabled"]) and logins[1].instate(["disabled"]) and not tries[0].instate(["disabled"])
      and any("ChatGPT: chưa cài" in str(w.cget("text")) for w in _nd_labels()), str(_atexts()))
cbo_ai.set("ChatGPT — tài khoản đăng nhập")
cbo_ai.event_generate("<<ComboboxSelected>>")
PICK["calls"], PICK["dead"] = [], {"chatgpt-account": "ChatGPT tài khoản: chưa cài Codex"}
buttons["Học niche từ kênh đối thủ"].invoke()
pump(lambda: PICK["calls"] and not buttons["Học niche từ kênh đối thủ"].instate(["disabled"]), 20)
lrn = [n for n in app_config.load_config()["niches"] if n["name"] == "AI Niche"][0]["learned"]
check("chon rieng tai khoan ChatGPT -> no dung dau; hong thi toi tai khoan Claude; may chua co Codex thi API openai khong bi loai",
      PICK["cands"][:2] == ["chatgpt-account", "claude-account"] and lrn["ai"]["brain"] == "Claude tài khoản"
      and "claude-sonnet" not in PICK["cands"], str(PICK["cands"]))
for _w in [w for w in root.winfo_children() if isinstance(w, tk.Toplevel) and w.title().startswith("Kết quả học niche")]:
    _w.destroy()
ACC["g"] = {"installed": True, "logged_in": True, "plan": "", "who": "", "path": "codex.exe", "detail": "đã đăng nhập bằng tài khoản ChatGPT"}
PICK["dead"] = {}
ACC["c"] = dict(ACC["c"], logged_in=False, detail="chưa đăng nhập")
[b for b in abtn if b.cget("text") == "Kiểm tra lại"][0].invoke()
pump(lambda: str(logins[0].cget("text")) == "Đăng nhập…", 5)
_ask4, ASKED2 = ui.messagebox.askyesno, []
ui.messagebox.askyesno = lambda *a, **k: (ASKED2.append(a), False)[1]
logins[0].invoke()
root.update()
ui.messagebox.askyesno = _ask4
check("tai khoan CHUA dang nhap -> nut 'Đăng nhập…' mo thang, khong hoi", str(logins[0].cget("text")) == "Đăng nhập…"
      and ASKED2 == [] and LOGIN[-1] == "claude-account" and tries[0].instate(["disabled"]), f"{LOGIN} {ASKED2}")
ACC["c"] = dict(ACC["c"], logged_in=True, detail="đã đăng nhập · gói max · ab***@x.com")
[b for b in abtn if b.cget("text") == "Đóng"][0].invoke()
root.update()
check("dong cua so tai khoan", not aw.winfo_exists())
cbo_ai.set("Tự chọn (ưu tiên Claude)")
cbo_ai.event_generate("<<ComboboxSelected>>")

app._toggle_theme()
root.update()
app._toggle_theme()
root.update()
check("doi nen khi hop Niche dang mo khong loi", nd.winfo_exists())
nd.destroy()
root.update()
app.cfg["niche_ai"] = "Claude + ChatGPT (song song, đối chiếu)"      # nhan cua ban v1.11.0 (API key)
app.open_niche_manager()
root.update()
_cb2 = [w for w in walk(app._niche_dialog) if isinstance(w, ttk.Combobox)][0]
check("lua chon cu 'Claude + ChatGPT' (API) tu chuyen sang 2 tai khoan dang nhap", _cb2.get() == DUAL, _cb2.get())
app._niche_dialog.destroy()
root.update()
root.destroy()

# ---------------------------------------------------------------- [6]
print("\n[6] Tinh")
check("api_vault.KNOWN_KEYS co YOUTUBE_API_KEY", "YOUTUBE_API_KEY" in [k for k, _d in api_vault.KNOWN_KEYS])
check("YOUTUBE_API_KEY khong bi coi la AI brain tu dat", "YOUTUBE_API_KEY" in api_vault._BUILTIN_BRAIN_KEYS)
SRC = open(os.path.join(HERE, "workflow", "niche_learner.py"), encoding="utf-8").read()
check("niche_learner chi GET (khong POST/PUT/DELETE, khong insert/rate)",
      all(x not in SRC for x in ('method="POST"', "method='POST'", "data=", "/rate", "comments.insert", "insert(")))
check("niche_learner khong in URL/key", "print(" not in SRC)
for p, h in BEFORE.items():
    check(f"file that khong doi: {os.path.basename(p)}", _hash(p) == h)

print(f"\nPASS: {PASS}  FAIL: {FAIL}")
print("SMOKE v1.9.4: ALL PASS" if FAIL == 0 else "SMOKE v1.9.4: CO LOI")
sys.exit(0 if FAIL == 0 else 1)
