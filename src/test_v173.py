# -*- coding: utf-8 -*-
"""Smoke test v1.7.3 — SỐ CHỦ ĐỀ THEO DÒNG GỐC + CHUỖI DỰ PHÒNG AI + MẪU OFFLINE KHÁ HƠN.

Bối cảnh (user báo 31/10/2026): nạp 4 dòng gốc "Camping / mountain / christmast /
autumn fashion", bấm "Sinh chủ đề" -> ra ĐÚNG 4 chủ đề, và cả 4 đều là template ghép seed
("Camping vs alternatives", "best mountain for beginners"...). HAI lỗi độc lập:

  (1) SỐ LƯỢNG: n = số profile đang tick. 4 dòng + 4 profile = hạn ngạch 1/dòng -> prompt
      gửi AI ghi "List exactly 1" nên nút Sinh chỉ CHÉP LẠI thứ user vừa gõ. Tệ hơn: tick
      1 profile thì 3 trong 4 dòng bị VỨT ÂM THẦM (quotas [1,0,0,0]).
      -> v1.7.3: n = số DÒNG GỐC × ô "Số chủ đề/dòng" (mặc định 5), sàn = số profile.
  (2) CHẤT LƯỢNG: cả 3 key AI đều chết (đo thật: claude 403 INSUFFICIENT_BALANCE,
      gemini 504, openai 429 credit_balance_exhausted) nhưng app chỉ chọn MỘT brain rồi
      rơi thẳng xuống offline, lý do thật bị ask_text nuốt thành "".
      -> v1.7.3: thử CẢ CHUỖI brain + nêu thẳng lý do bằng tiếng người.

Chạy OFFLINE (không mạng, không browser):  python src\\test_v173.py
DB + .env test nằm ở thư mục tạm (GPM_BOT_DATA_DIR / GPM_BOT_ENV_FILE) — KHÔNG đụng
data\\ và .env THẬT (section 9 đối chiếu hash .env thật trước/sau).
"""
import hashlib
import os
import sys
import tempfile
import time

SRC = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(SRC)
for p in (ROOT, SRC):
    if p not in sys.path:
        sys.path.insert(0, p)

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

TMP = tempfile.mkdtemp(prefix="gpm_v173_")
os.environ["GPM_BOT_DATA_DIR"] = TMP
TEST_ENV = os.path.join(TMP, ".env")
os.environ["GPM_BOT_ENV_FILE"] = TEST_ENV

PASS = 0
FAIL = 0


def check(label, cond, extra=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  [PASS] {label}" + (f"  ({extra})" if extra else ""))
    else:
        FAIL += 1
        print(f"  [FAIL] {label}" + (f"  ({extra})" if extra else ""))


def hr(t):
    print("\n" + "=" * 70)
    print(t)
    print("=" * 70)


def read_src(name):
    with open(os.path.join(SRC, name), "r", encoding="utf-8") as f:
        return f.read()


def sha(path):
    try:
        with open(path, "rb") as f:
            return hashlib.sha256(f.read()).hexdigest()[:12]
    except Exception:
        return "(không đọc được)"


REAL_ENV = os.path.join(ROOT, ".env")
ENV_HASH_BEFORE = sha(REAL_ENV)

import src.ui_main as ui  # noqa: E402
from src import lang_profiles as L  # noqa: E402
import src.app_config as app_config  # noqa: E402

SEEDS = ["Camping", "mountain", "christmast", "autumn fashion"]

# =====================================================================
hr("1. SỐ LƯỢNG — n = số dòng gốc × N (sàn = số profile), không còn = số profile")


def quota_of(out):
    return [sum(1 for t in out if t.get("seed") == s) for s in SEEDS]


for profiles, per in ((4, 5), (1, 5), (52, 5), (4, 1), (10, 3), (2, 20)):
    n = max(profiles, len(SEEDS) * per)
    out = ui.generate_topics_for_seeds(SEEDS, n, brain=None, lang="en")
    q = quota_of(out)
    check(f"{profiles} profile × {per}/dòng -> {n} chủ đề, chia đều {q}",
          len(out) == n and min(q) >= 1 and max(q) - min(q) <= 1, str(q))

# Chính ca user báo lỗi: 4 dòng + 4 profile KHÔNG còn ra 4 chủ đề.
out4 = ui.generate_topics_for_seeds(SEEDS, max(4, 4 * 5), brain=None, lang="en")
check("CA USER: 4 dòng + 4 profile -> 20 chủ đề (trước fix: 4)", len(out4) == 20, str(len(out4)))
check("CA USER: mỗi dòng gốc được 5 chủ đề", quota_of(out4) == [5, 5, 5, 5], str(quota_of(out4)))
check("CA USER: mọi chủ đề đều PHÂN BIỆT",
      len({t["google_query"].lower() for t in out4}) == 20)
check("CA USER: mỗi chủ đề chứa đúng dòng gốc sinh ra nó",
      all(t["seed"].lower() in t["google_query"].lower() for t in out4))

# Bẫy cũ: tick 1 profile -> quotas [1,0,0,0] -> 3 dòng bị vứt âm thầm.
out1 = ui.generate_topics_for_seeds(SEEDS, max(1, 4 * 5), brain=None, lang="en")
check("HẾT BẪY: tick 1 profile vẫn dùng ĐỦ 4 dòng gốc (trước fix chỉ dùng 1)",
      sorted(set(t["seed"] for t in out1)) == sorted(SEEDS),
      str(sorted(set(t["seed"] for t in out1))))

# =====================================================================
hr("2. MẪU OFFLINE — khá hơn, không còn câu vô nghĩa")

check("en >= 10 mẫu và MỌI mẫu có {s} (giữ ràng buộc test_v160:72)",
      len(L.topic_templates("en")) >= 10 and all("{s}" in t for t in L.topic_templates("en")),
      str(len(L.topic_templates("en"))))
_en = " | ".join(L.topic_templates("en"))
for bad in ("to lose weight", "shoes shopping", "clothes shopping", "vs alternatives"):
    check(f"bỏ mẫu ghép máy móc: '{bad}'", bad not in _en)
check("mọi mẫu en PHÂN BIỆT", len(set(L.topic_templates("en"))) == len(L.topic_templates("en")))
for c in L.LANG_CODES:
    check(f"topic_templates[{c}] vẫn >=10 mẫu + có {{s}}",
          len(L.topic_templates(c)) >= 10 and all("{s}" in t for t in L.topic_templates(c)))

# =====================================================================
hr("3. _explain_brain_error — dịch lỗi SDK sang câu người đọc hiểu")

for raw, want in (
    ("Error code: 403 - {'code': 'INSUFFICIENT_BALANCE', 'message': 'Insufficient account balance'}", "HẾT SỐ DƯ"),
    ("Error code: 429 - {'code': 'credit_balance_exhausted'}", "HẾT CREDIT"),
    ("504 Deadline expired before operation could complete.", "quá hạn chờ"),
    ("Error code: 401 - invalid_api_key", "KEY SAI"),
    ("Error code: 404 - model not found", "không tồn tại"),
    ("Connection refused WinError 10061", "không kết nối được"),
):
    got = ui._explain_brain_error(raw)
    check(f"'{raw[:34]}...' -> {got}", want in got, got)
check("lỗi rỗng -> 'không rõ lý do'", ui._explain_brain_error("") == "không rõ lý do")
check("lỗi lạ -> trả nguyên văn (cắt ngắn)",
      ui._explain_brain_error("something weird happened").startswith("something weird"))

# =====================================================================
hr("4. _brain_candidates_from_env — cả hàng chờ, đúng thứ tự ưu tiên")

_KEYS = ("CLAUDE_API_KEY", "CLAUDE_API_KEY_ENDPOINT", "CLAUDE_LAU", "CLAUDE_LAU_ENDPOINT",
         "GEMINI_API_KEY", "OPENAI_API_KEY", "QWEN_API_KEY", "DASHSCOPE_API_KEY")
_snap = {k: os.environ.get(k) for k in _KEYS}
for k in _KEYS:
    os.environ.pop(k, None)

check("không key nào -> hàng chờ rỗng", ui._brain_candidates_from_env() == [])
os.environ["GEMINI_API_KEY"] = "g"
check("chỉ gemini", ui._brain_candidates_from_env() == ["gemini"])
os.environ["OPENAI_API_KEY"] = "o"
check("gemini + openai đúng thứ tự", ui._brain_candidates_from_env() == ["gemini", "openai"])
os.environ["CLAUDE_LAU"] = "c"
check("claude THIẾU endpoint -> không vào hàng chờ",
      ui._brain_candidates_from_env() == ["gemini", "openai"])
os.environ["CLAUDE_LAU_ENDPOINT"] = "https://x/v1"
check("claude ĐỦ key+endpoint -> đứng ĐẦU",
      ui._brain_candidates_from_env() == ["claude-sonnet", "gemini", "openai"])
os.environ["QWEN_API_KEY"] = "q"
check("qwen đứng cuối",
      ui._brain_candidates_from_env() == ["claude-sonnet", "gemini", "openai", "qwen-max"])
check("hàng chờ KHỚP thứ tự với _detect_brain_type_from_env (brain đầu tiên)",
      ui._brain_candidates_from_env()[0] == ui._detect_brain_type_from_env())
check("không bao giờ trùng lặp trong hàng chờ",
      len(set(ui._brain_candidates_from_env())) == len(ui._brain_candidates_from_env()))

for k, v in _snap.items():
    if v is None:
        os.environ.pop(k, None)
    else:
        os.environ[k] = v

# =====================================================================
hr("5. _pick_live_brain — brain chết thì NHẢY brain kế, nêu rõ lý do")


class FakeBrain:
    def __init__(self, reply="", err=""):
        self._reply, self.last_error = reply, err

    def ask_text(self, prompt):
        return self._reply


class FakeMgr:
    table = {}
    raise_for = set()

    @staticmethod
    def get_brain(bt):
        if bt in FakeMgr.raise_for:
            raise RuntimeError("Thiếu QWEN_API_KEY")
        return FakeMgr.table[bt]


_real_mgr = ui.BrainManager
ui.BrainManager = FakeMgr

# (a) brain đầu chết -> nhảy brain thứ 2 đang sống
FakeMgr.table = {
    "claude-sonnet": FakeBrain("", "Error code: 403 - {'code': 'INSUFFICIENT_BALANCE'}"),
    "gemini": FakeBrain("OK"),
    "openai": FakeBrain("OK"),
}
FakeMgr.raise_for = set()
logs = []
brain, bt, why = ui._pick_live_brain(["claude-sonnet", "gemini", "openai"], log=logs.append)
check("brain đầu hết số dư -> dùng brain thứ 2", bt == "gemini", str(bt))
check("trả về đúng đối tượng brain sống", brain is FakeMgr.table["gemini"])
check("không còn lý do lỗi khi đã tìm được brain", why == "")
check("log nêu RÕ 'HẾT SỐ DƯ' của brain đầu",
      any("HẾT SỐ DƯ" in l and "claude-sonnet" in l for l in logs), str(logs))
check("log báo brain nào được dùng", any("gemini" in l and "trả lời được" in l for l in logs))
check("KHÔNG thử brain thứ 3 khi brain thứ 2 đã sống",
      not any("openai" in l for l in logs), str(logs))

# (b) tất cả đều chết -> (None, "", lý do CUỐI)
FakeMgr.table = {
    "claude-sonnet": FakeBrain("", "403 INSUFFICIENT_BALANCE"),
    "gemini": FakeBrain("", "504 Deadline expired"),
    "openai": FakeBrain("", "429 credit_balance_exhausted"),
}
logs2 = []
brain2, bt2, why2 = ui._pick_live_brain(["claude-sonnet", "gemini", "openai"], log=logs2.append)
check("tất cả chết -> brain None", brain2 is None and bt2 == "")
check("trả lý do của brain CUỐI", "HẾT CREDIT" in why2, why2)
check("log đủ 3 dòng lý do (mỗi brain 1 dòng)",
      sum(1 for l in logs2 if "KHÔNG dùng được" in l) == 3, str(len(logs2)))

# (c) get_brain ném lỗi -> vẫn nhảy tiếp, không vỡ
FakeMgr.raise_for = {"qwen-max"}
FakeMgr.table["gemini"] = FakeBrain("OK")
logs3 = []
brain3, bt3, _ = ui._pick_live_brain(["qwen-max", "gemini"], log=logs3.append)
check("get_brain ném lỗi -> bỏ qua, dùng brain kế", bt3 == "gemini", str(bt3))
check("log ghi lý do không khởi tạo được",
      any("không khởi tạo được" in l for l in logs3), str(logs3))

# (d) ask_text ném exception -> coi như chết, không vỡ


class BoomBrain:
    last_error = ""

    def ask_text(self, prompt):
        raise RuntimeError("boom 401 unauthorized")


FakeMgr.raise_for = set()
FakeMgr.table = {"openai": BoomBrain(), "gemini": FakeBrain("OK")}
logs4 = []
brain4, bt4, _ = ui._pick_live_brain(["openai", "gemini"], log=logs4.append)
check("ask_text ném exception -> nhảy brain kế, không vỡ", bt4 == "gemini", str(bt4))
check("lý do exception được dịch (KEY SAI)",
      any("KEY SAI" in l for l in logs4), str(logs4))

# (e) hàng chờ rỗng -> không gọi gì
check("hàng chờ rỗng -> (None, '', '')", ui._pick_live_brain([], log=None) == (None, "", ""))

ui.BrainManager = _real_mgr

# =====================================================================
hr("6. Brain ghi lại last_error (lý do thật của lượt gọi hỏng)")

from src.agent.openai_brain import GenericLLMBrain  # noqa: E402


class _BadClient:
    class chat:
        class completions:
            @staticmethod
            def create(**kw):
                raise RuntimeError("Error code: 403 - {'code': 'INSUFFICIENT_BALANCE'}")


class _GoodClient:
    class chat:
        class completions:
            @staticmethod
            def create(**kw):
                class M:
                    content = "  hello  "

                class C:
                    message = M()

                class R:
                    choices = [C()]

                return R()


b = object.__new__(GenericLLMBrain)
b.model_name = "x"
check("GenericLLMBrain có last_error mặc định rỗng", b.last_error == "")
text, err = b._ask_raw(_BadClient, "hi")
check("lỗi -> _ask_raw trả ('', err)", text == "" and "INSUFFICIENT_BALANCE" in err)
check("lỗi -> last_error lưu nguyên văn", "INSUFFICIENT_BALANCE" in b.last_error)
check("last_error dịch được sang câu người đọc",
      "HẾT SỐ DƯ" in ui._explain_brain_error(b.last_error))
text2, err2 = b._ask_raw(_GoodClient, "hi")
check("thành công -> trả text đã strip", text2 == "hello" and err2 == "")
check("thành công -> last_error được XÓA (không giữ lỗi cũ)", b.last_error == "")

try:
    from src.agent.gemini_brain import GeminiBrain  # noqa: E402

    class _BadModel:
        @staticmethod
        def generate_content(*a, **kw):
            # Lỗi KHÔNG thuộc nhóm "đổi model may ra khỏi" -> _ask_raw dừng NGAY, không
            # dựng model dự phòng (nếu dùng 504 thì nó sẽ dựng GenerativeModel thật và
            # gọi mạng — section này phải offline tuyệt đối). Nhánh fallback: section 10.
            raise RuntimeError("401 unauthorized - invalid api key")

    g = object.__new__(GeminiBrain)
    g.model_name = "gemini-3-flash-preview"  # __init__ thật luôn đặt; ở đây dựng tay
    g.model = _BadModel
    check("GeminiBrain có last_error mặc định rỗng", g.last_error == "")
    gt, ge = g._ask_raw("hi")
    check("Gemini lỗi -> last_error lưu lý do", gt == "" and "401" in g.last_error)
    check("Gemini last_error dịch được", "KEY SAI" in ui._explain_brain_error(g.last_error))
except ImportError as e:
    check("bỏ qua GeminiBrain (SDK chưa cài)", True, str(e)[:60])

# =====================================================================
hr("7. GUI thật — Spinbox 'Số chủ đề/dòng' + sinh end-to-end")

import tkinter as tk  # noqa: E402

ui_root = tk.Tk()
ui_root.withdraw()
app = ui.AutomationApp(ui_root)

_orig_detect = ui._detect_brain_type_from_env
ui._detect_brain_type_from_env = lambda: None  # ép offline: không gọi mạng, tất định

check("có Spinbox spin_topics_per_seed", hasattr(app, "spin_topics_per_seed"))
check("mặc định 5 chủ đề/dòng", app._topics_per_seed() == 5, str(app._topics_per_seed()))
for raw, want in ((1, 1), (3, 3), (20, 20), (0, 1), (-7, 1), (999, 20)):
    app.spin_topics_per_seed.set(raw)
    check(f"_topics_per_seed({raw}) -> {want}", app._topics_per_seed() == want,
          str(app._topics_per_seed()))
app.spin_topics_per_seed.set("abc")
check("_topics_per_seed('abc') -> 5 (nhập rác không ném)", app._topics_per_seed() == 5)
app.spin_topics_per_seed.delete(0, "end")
check("_topics_per_seed(rỗng) -> 5", app._topics_per_seed() == 5)
app.spin_topics_per_seed.set(5)


def _label_texts(w):
    out = []
    for ch in w.winfo_children():
        try:
            if "Label" in ch.winfo_class():
                out.append(str(ch.cget("text")))
        except Exception:
            pass
        out.extend(_label_texts(ch))
    return out


check("có nhãn 'Số chủ đề/dòng' cạnh Spinbox",
      any("Số chủ đề/dòng" in t for t in _label_texts(app.spin_topics_per_seed.master)),
      str(_label_texts(app.spin_topics_per_seed.master))[:120])
check("KHÔNG reparent ô gốc: nhãn 'Chủ đề gốc' vẫn thấy được (test_v157:202)",
      any("Chủ đề gốc" in t for t in _label_texts(app.ent_pinned_theme.master)))


def _count_lang_radios(w):
    import tkinter.ttk as ttk
    n = 0
    for ch in w.winfo_children():
        try:
            if isinstance(ch, ttk.Radiobutton) and str(ch.cget("value")) in L.LANG_CODES:
                n += 1
        except Exception:
            pass
        n += _count_lang_radios(ch)
    return n


check("vẫn ĐÚNG 4 radio ngôn ngữ (test_v160:211)", _count_lang_radios(ui_root) == 4,
      str(_count_lang_radios(ui_root)))

app._set_utils_state("disabled")
check("Spinbox mới DISABLE khi đang chạy", str(app.spin_topics_per_seed.cget("state")) == "disabled",
      str(app.spin_topics_per_seed.cget("state")))
app._set_utils_state("normal")
check("Spinbox mới bật lại khi xong", str(app.spin_topics_per_seed.cget("state")) != "disabled")

# --- sinh end-to-end: 3 dòng gốc × 4 = 12 ---
app.profile_rows = []
for i in range(2):
    app.profile_rows.append({
        "id": f"{i:08d}-0000-0000-0000-000000000000",
        "name": f"P{i}", "firefox": False, "hidden": False,
        "var": tk.BooleanVar(value=True),
    })
app.var_brain_type.set("none")
app.var_kw_lang.set("en")
app.spin_topics_per_seed.set(4)
app.var_pinned_theme.set("Camping\nmountain\nautumn fashion")

captured = {}
_orig_preview = app._show_generated_topics_preview
app._show_generated_topics_preview = lambda seed, topics: captured.update(seed=seed, topics=topics)
app.on_generate_topics()
_dl = time.time() + 10
while "topics" not in captured and time.time() < _dl:
    ui_root.update()
    time.sleep(0.02)

tp = captured.get("topics", [])
check("sinh end-to-end: 3 dòng × 4 = 12 chủ đề (2 profile KHÔNG còn quyết định)",
      len(tp) == 12, str(len(tp)))
check("mỗi dòng gốc đúng 4 chủ đề",
      all(sum(1 for t in tp if t.get("seed") == s) == 4
          for s in ("Camping", "mountain", "autumn fashion")),
      str([(s, sum(1 for t in tp if t.get("seed") == s))
           for s in ("Camping", "mountain", "autumn fashion")]))
check("không chủ đề nào gộp nhiều dòng gốc",
      not [t for t in tp if "Camping" in t["google_query"] and "mountain" in t["google_query"]])
check("nút bật lại sau khi sinh", not app.btn_gen_topics.instate(["disabled"]))
check("nhãn nút về 'Sinh chủ đề con'",
      "Sinh chủ đề con" in str(app.btn_gen_topics.cget("text")),
      str(app.btn_gen_topics.cget("text")))

# sàn: nhiều profile hơn số chủ đề -> nâng lên cho đủ
app.profile_rows = [{
    "id": f"{i:08d}-0000-0000-0000-000000000000", "name": f"P{i}",
    "firefox": False, "hidden": False, "var": tk.BooleanVar(value=True)} for i in range(30)]
app.spin_topics_per_seed.set(2)
captured.clear()
app.on_generate_topics()
_dl = time.time() + 10
while "topics" not in captured and time.time() < _dl:
    ui_root.update()
    time.sleep(0.02)
check("SÀN: 3 dòng × 2 = 6 < 30 profile -> nâng lên 30 chủ đề",
      len(captured.get("topics", [])) == 30, str(len(captured.get("topics", []))))

app._show_generated_topics_preview = _orig_preview
ui._detect_brain_type_from_env = _orig_detect

# --- config round-trip ---
app.spin_topics_per_seed.set(7)
app.save_current_config()
check("app_config.DEFAULTS có topics_per_seed = 5",
      app_config.DEFAULTS.get("topics_per_seed") == 5,
      str(app_config.DEFAULTS.get("topics_per_seed")))
_cfg = app_config.load_config()
check("lưu được topics_per_seed = 7", _cfg.get("topics_per_seed") == 7, str(_cfg.get("topics_per_seed")))
for k in ("daily_minutes", "pinned_theme", "keyword_lang", "pane_sash"):
    check(f"không làm mất key cũ '{k}'", k in _cfg)
app.spin_topics_per_seed.set(5)
app.save_current_config()

try:
    ui_root.destroy()
except Exception:
    pass
sys.stdout = sys.__stdout__

# =====================================================================
hr("8. Assert tĩnh trên source")

um = read_src("ui_main.py")
# Chỉ cấm NHÃN NÚT cũ — cụm "theo số profile" vẫn còn trong comment giải thích vì sao bỏ.
check("bỏ nhãn nút cũ '(theo số profile)'",
      '"Sinh chủ đề (theo số profile)"' not in um)
check("nút mang nhãn mới 'Sinh chủ đề con'", um.count('"Sinh chủ đề con"') >= 2,
      str(um.count('"Sinh chủ đề con"')))
check("n = max(len(profiles), len(seeds) * per_seed)",
      "n = max(len(profiles), len(seeds) * per_seed)" in um)
# Comment lịch sử có nhắc "Cũ: n = len(profiles)" -> chỉ cấm DÒNG GÁN thật.
check("KHÔNG còn dòng gán 'n = len(profiles)'",
      "\n        n = len(profiles)" not in um.replace("\r\n", "\n"))
check("có hàm _topics_per_seed", "def _topics_per_seed(self)" in um)
check("có hàm _brain_candidates_from_env", "def _brain_candidates_from_env()" in um)
check("có hàm _pick_live_brain", "def _pick_live_brain(" in um)
check("có hàm _explain_brain_error", "def _explain_brain_error(" in um)
_og = um.split("def on_generate_topics")[1].split("def _flush_gen_logs")[0]
check("on_generate_topics dựng 'candidates'", "candidates = " in _og)
check("on_generate_topics giữ _detect_brain_type_from_env + auto_pick (test_v157:389)",
      "_detect_brain_type_from_env()" in _og and "auto_pick" in _og)
check("worker dùng _pick_live_brain", "_pick_live_brain(_cands" in _og)
check("hàng rào deadline cộng thời gian dò brain", "18 * len(candidates)" in _og)
check("giữ _ai_seeds (test_v171:526)", "_ai_seeds" in _og)
check("chữ ký generate_topics_from_seed GIỮ NGUYÊN (test_v160:175 + test_v171:522 ghim)",
      'def generate_topics_from_seed(seed, n, brain=None, rng=None, log=None, lang="en")' in um)
check("KHÔNG quay lại nối chuỗi các dòng gốc (test_v171:518)",
      '", ".join(p["google_query"] for p in self._seed_themes())' not in um)
check("app_config có topics_per_seed", '"topics_per_seed": 5' in read_src("app_config.py"))
_ob = read_src(os.path.join("agent", "openai_brain.py"))
check("openai_brain ghi last_error ở cả 2 nhánh",
      'self.last_error = ""' in _ob and "self.last_error = str(e)" in _ob)
_gb = read_src(os.path.join("agent", "gemini_brain.py"))
check("gemini_brain ghi last_error ở cả 2 nhánh",
      'self.last_error = ""' in _gb and
      ("self.last_error = str(e)" in _gb or "self.last_error = err" in _gb))

# =====================================================================
hr("10. Gemini — model mặc định SỐNG + chuỗi dự phòng khi Google gỡ model")

import src.agent.gemini_brain as gbm  # noqa: E402

check("có danh sách _GEMINI_MODELS", isinstance(gbm._GEMINI_MODELS, tuple)
      and len(gbm._GEMINI_MODELS) >= 2, str(gbm._GEMINI_MODELS))
check("model mặc định = gemini-3-flash-preview (ĐO: 1.4s; cũ gemini-flash-latest TREO >120s)",
      gbm._GEMINI_MODELS[0] == "gemini-3-flash-preview", gbm._GEMINI_MODELS[0])
check("vẫn giữ gemini-flash-latest làm phương án chót",
      "gemini-flash-latest" in gbm._GEMINI_MODELS)
check("_MODEL_FALLBACK_ON bắt cả model-bị-gỡ LẪN treo",
      all(k in gbm._MODEL_FALLBACK_ON for k in ("404", "503", "deadline", "timeout")),
      str(gbm._MODEL_FALLBACK_ON))
check("lỗi quota/key KHÔNG kích fallback model (đổi model vô ích)",
      not any(k in gbm._MODEL_FALLBACK_ON for k in ("429", "quota", "api key")))


class _FakeResp:
    def __init__(self, t):
        self.text = t


class _FakeModelFactory:
    """Model đầu 404 (bị gỡ), model thứ 2 trả lời được."""
    built = []

    def __init__(self, name):
        self.name = name
        _FakeModelFactory.built.append(name)

    def generate_content(self, prompt, **kw):
        if self.name == "gemini-3-flash-preview":
            raise RuntimeError("404 This model is no longer available")
        return _FakeResp("  OK  ")


_real_genai = gbm.genai


class _FakeGenai:
    GenerativeModel = _FakeModelFactory


gbm.genai = _FakeGenai
g = object.__new__(gbm.GeminiBrain)
g.model_name = "gemini-3-flash-preview"
g.model = _FakeModelFactory("gemini-3-flash-preview")
_FakeModelFactory.built = []
txt, err = g._ask_raw("hi")
check("model bị gỡ -> tự nhảy sang model kế, vẫn có kết quả", txt == "OK" and err == "",
      f"txt={txt!r} err={err[:40]!r}")
check("NHỚ model chạy được cho lượt sau", g.model_name == "gemini-flash-lite-latest",
      g.model_name)
check("chỉ dựng đúng model dự phòng cần thiết", _FakeModelFactory.built == ["gemini-flash-lite-latest"],
      str(_FakeModelFactory.built))
check("thành công -> last_error rỗng", g.last_error == "")


class _AllQuota:
    def __init__(self, name):
        _FakeModelFactory.built.append(name)

    def generate_content(self, prompt, **kw):
        raise RuntimeError("429 You exceeded your current quota")


_FakeGenai.GenerativeModel = _AllQuota
g2 = object.__new__(gbm.GeminiBrain)
g2.model_name = "gemini-3-flash-preview"
g2.model = _AllQuota("gemini-3-flash-preview")
_FakeModelFactory.built = []
txt2, err2 = g2._ask_raw("hi")
check("lỗi 429 -> DỪNG ngay, không thử model khác (nhường cho xoay key)",
      txt2 == "" and "429" in err2 and _FakeModelFactory.built == [],
      f"built={_FakeModelFactory.built}")
check("lỗi quota -> last_error giữ nguyên văn để UI dịch",
      "HẾT" in ui._explain_brain_error(g2.last_error) or
      "giới hạn" in ui._explain_brain_error(g2.last_error),
      ui._explain_brain_error(g2.last_error))

gbm.genai = _real_genai

_gb_src = read_src(os.path.join("agent", "gemini_brain.py"))
check("env GEMINI_MODEL ghi đè được model", 'os.getenv("GEMINI_MODEL")' in _gb_src)
check("chữ ký ghim ở test_v156 đã khớp model mới",
      'def __init__(self, api_key: str, model_name="gemini-3-flash-preview", endpoint=None'
      in _gb_src)

# =====================================================================
hr("9. .env THẬT không bị đụng")

check(f"hash .env trước == sau ({ENV_HASH_BEFORE})", sha(REAL_ENV) == ENV_HASH_BEFORE,
      f"{ENV_HASH_BEFORE} -> {sha(REAL_ENV)}")
check("DB/config test nằm ở thư mục tạm", os.environ.get("GPM_BOT_DATA_DIR") == TMP)

print("\n" + "=" * 70)
print(f"PASS: {PASS}   FAIL: {FAIL}")
print("SMOKE v1.7.3: " + ("ALL PASS" if FAIL == 0 else f"CÓ {FAIL} LỖI"))
print("=" * 70)
sys.exit(1 if FAIL else 0)
