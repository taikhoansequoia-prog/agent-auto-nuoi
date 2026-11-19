# -*- coding: utf-8 -*-
"""Smoke test v1.7.1 + v1.7.2 — SINH CHỦ ĐỀ THEO TỪNG DÒNG GỐC + XOAY VÒNG NHIỀU API KEY
(Gemini & brain tương thích OpenAI) + brain Claude qua cổng tự đặt.

Bối cảnh (user báo 28/10/2026): gõ 4 dòng "Health / Buy clothes / go to the party /
headache" rồi bấm "Sinh chủ đề" -> mọi chủ đề con đều vác NGUYÊN CỤM
"Health, Buy clothes, go to the party, headache ..." vì v1.7.0 nối hết các dòng
(`", ".join(...)`) thành 1 hạt giống. v1.7.1: mỗi DÒNG là 1 chủ đề riêng, chia hạn ngạch
round-robin; đồng thời nạp được NHIỀU key Gemini và bot tự xoay vòng.

Chạy OFFLINE (không mạng, không browser):  python src\\test_v171.py
DB + .env test nằm ở thư mục tạm (GPM_BOT_DATA_DIR / GPM_BOT_ENV_FILE) — KHÔNG đụng
data\\ và .env THẬT (section 8 đối chiếu hash .env thật trước/sau).
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

TMP = tempfile.mkdtemp(prefix="gpm_v171_")
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


def file_hash(path):
    try:
        with open(path, "rb") as f:
            return hashlib.sha256(f.read()).hexdigest()[:12]
    except Exception:
        return "(không có file)"


REAL_ENV = os.path.join(ROOT, ".env")
REAL_ENV_HASH_BEFORE = file_hash(REAL_ENV)

import src.ui_main as ui  # noqa: E402

gen_seeds = ui.generate_topics_for_seeds
USER_SEEDS = ["Health", "Buy clothes", "go to the party", "headache"]


def gq(items):
    return [t["google_query"] for t in items]


# =====================================================================
hr("1. Hạn ngạch round-robin theo TỪNG DÒNG gốc")

logs = []
out4 = gen_seeds(USER_SEEDS, 4, brain=None, log=logs.append)
check("4 dòng / cần 4 -> đúng 4 chủ đề", len(out4) == 4, str(len(out4)))
check("4 dòng / cần 4 -> mỗi dòng đúng 1 chủ đề",
      sorted(t["seed"] for t in out4) == sorted(USER_SEEDS),
      str([t["seed"] for t in out4]))

out10 = gen_seeds(USER_SEEDS, 10, brain=None)
cnt = {s: 0 for s in USER_SEEDS}
for t in out10:
    cnt[t["seed"]] += 1
check("4 dòng / cần 10 -> đúng 10 chủ đề", len(out10) == 10, str(len(out10)))
check("4 dòng / cần 10 -> chia 3,3,2,2",
      [cnt[s] for s in USER_SEEDS] == [3, 3, 2, 2], str([cnt[s] for s in USER_SEEDS]))

logs2 = []
out2 = gen_seeds(USER_SEEDS, 2, brain=None, log=logs2.append)
check("4 dòng / cần 2 -> đúng 2 chủ đề", len(out2) == 2, str(len(out2)))
check("4 dòng / cần 2 -> lấy 2 dòng ĐẦU",
      [t["seed"] for t in out2] == USER_SEEDS[:2], str([t["seed"] for t in out2]))
check("4 dòng / cần 2 -> có log nhắc bỏ bớt dòng",
      any("chỉ sinh cho 2 dòng ĐẦU" in l for l in logs2), str(logs2[:2]))

out1 = gen_seeds(["tin thế giới"], 3, brain=None)
check("1 dòng / cần 3 -> vẫn 3 chủ đề của đúng dòng đó",
      len(out1) == 3 and all(t["seed"] == "tin thế giới" for t in out1))
check("seeds rỗng -> vẫn ra đủ n (mẫu mặc định)",
      len(gen_seeds([], 3, brain=None)) == 3)
check("n<=0 -> []", gen_seeds(USER_SEEDS, 0, brain=None) == [])
check("bỏ qua dòng trống/toàn khoảng trắng",
      {t["seed"] for t in gen_seeds(["Health", "   ", ""], 2, brain=None)} == {"Health"})

# =====================================================================
hr("2. CHỐT BUG: không còn gộp các dòng vào 1 chuỗi")

merged = [g for g in gq(out4) + gq(out10) + gq(out2)
          if "Health" in g and "Buy clothes" in g]
check("KHÔNG chủ đề nào chứa cả 'Health' lẫn 'Buy clothes'", not merged, str(merged[:2]))
check("KHÔNG chủ đề nào chứa 'go to the party, headache'",
      not [g for g in gq(out10) if "go to the party, headache" in g])
check("mỗi chủ đề CHỨA đúng dòng gốc của nó",
      all(t["seed"].lower() in t["google_query"].lower() for t in out10),
      str([t["google_query"] for t in out10[:2]]))
check("mọi 'seed' đều thuộc danh sách dòng gốc",
      all(t["seed"] in USER_SEEDS for t in out10))
check("Google phân biệt toàn cục (không trùng giữa các dòng)",
      len({g.lower() for g in gq(out10)}) == len(out10))

# đối chứng: hàm CŨ (gộp) vẫn còn và vẫn gộp -> chứng minh khác biệt là do hàm mới
old = ui.generate_topics_from_seed(", ".join(USER_SEEDS), 2, brain=None)
check("(đối chứng) hàm cũ trên chuỗi gộp VẪN ra chuỗi gộp — nên phải dùng hàm mới",
      any("Health" in g and "headache" in g for g in gq(old)), str(gq(old)[:1]))

# =====================================================================
hr("3. Có AI: gọi riêng từng dòng, thiếu thì bù offline ĐÚNG dòng")


class _Brain:
    """AI giả: trả đúng seed được hỏi -> chứng minh mỗi dòng được hỏi RIÊNG."""

    def __init__(self, lines_per_call=None):
        self.prompts = []
        self.lines_per_call = lines_per_call

    def ask_text(self, prompt):
        self.prompts.append(prompt)
        seed = ""
        for line in prompt.splitlines():
            if line.startswith("Seed topic(s):"):
                seed = line.split(":", 1)[1].strip()
        k = self.lines_per_call if self.lines_per_call is not None else 9
        return "\n".join(f"AI {seed} idea {i} | AI {seed} video {i}" for i in range(1, k + 1))


b = _Brain()
outb = gen_seeds(USER_SEEDS, 4, brain=b)
check("mỗi dòng gốc được hỏi AI 1 lượt riêng", len(b.prompts) == 4, str(len(b.prompts)))
check("prompt mang ĐÚNG 1 dòng gốc (không phải chuỗi gộp)",
      all(sum(1 for s in USER_SEEDS if f"Seed topic(s): {s}" in p) == 1 for p in b.prompts))
check("chủ đề lấy từ AI (có tiền tố 'AI ')", all(g.startswith("AI ") for g in gq(outb)),
      str(gq(outb)[:2]))
check("youtube_query giữ vế phải của AI",
      all(t["youtube_query"].startswith("AI ") and "video" in t["youtube_query"] for t in outb))

b2 = _Brain(lines_per_call=1)  # AI chỉ trả 1 dòng dù cần 3 -> phải bù offline
out_fill = gen_seeds(["Health", "headache"], 6, brain=b2)
check("AI trả thiếu -> vẫn đủ n", len(out_fill) == 6, str(len(out_fill)))
check("phần bù offline vẫn gắn ĐÚNG dòng gốc",
      all(t["seed"].lower() in t["google_query"].lower() for t in out_fill),
      str([t["google_query"] for t in out_fill]))
check("mỗi dòng vẫn đúng hạn ngạch 3",
      sum(1 for t in out_fill if t["seed"] == "Health") == 3 and
      sum(1 for t in out_fill if t["seed"] == "headache") == 3)


class _SameBrain:
    """AI trả y hệt nhau cho mọi dòng -> kiểm dedupe toàn cục."""

    def ask_text(self, prompt):
        return "\n".join(f"same idea {i} | same video {i}" for i in range(1, 4))


out_dup = gen_seeds(USER_SEEDS, 4, brain=_SameBrain())
check("AI trả trùng nhau -> dedupe + bù cho đủ n",
      len(out_dup) == 4 and len({g.lower() for g in gq(out_dup)}) == 4, str(gq(out_dup)))

# =====================================================================
hr("4. Hàng rào thời gian (deadline_ts) — không bao giờ chờ quá hạn")

b3 = _Brain()
out_dl = gen_seeds(USER_SEEDS, 4, brain=b3, deadline_ts=time.time() - 1)
check("deadline đã qua -> KHÔNG gọi AI lần nào", len(b3.prompts) == 0, str(len(b3.prompts)))
check("deadline đã qua -> vẫn đủ n bằng mẫu offline", len(out_dl) == 4)
check("deadline đã qua -> mỗi dòng vẫn 1 chủ đề riêng",
      sorted(t["seed"] for t in out_dl) == sorted(USER_SEEDS))

b4 = _Brain()
out_ok = gen_seeds(USER_SEEDS, 4, brain=b4, deadline_ts=time.time() + 600)
check("deadline còn dư -> vẫn gọi AI đủ 4 dòng", len(b4.prompts) == 4)

prog = []
gen_seeds(USER_SEEDS, 4, brain=None, progress=lambda i, m: prog.append((i, m)))
check("progress báo tiến trình từng dòng", prog == [(1, 4), (2, 4), (3, 4), (4, 4)], str(prog))

# =====================================================================
hr("5. api_vault.get_keys — gom nhiều key để xoay vòng")

import src.api_vault as api_vault  # noqa: E402

check("env_path trỏ vào file test (không đụng .env thật)",
      os.path.abspath(api_vault.env_path()) == os.path.abspath(TEST_ENV),
      api_vault.env_path())


def seed_env(text):
    with open(TEST_ENV, "w", encoding="utf-8", newline="") as f:
        f.write(text)


seed_env("GEMINI_API_KEY=k1,k2 , k3\r\nOPENAI_API_KEY=solo\r\n")
check("tách nhiều key trong 1 biến theo dấu phẩy",
      api_vault.get_keys("GEMINI_API_KEY") == ["k1", "k2", "k3"],
      str(api_vault.get_keys("GEMINI_API_KEY")))
check("1 key -> list 1 phần tử", api_vault.get_keys("OPENAI_API_KEY") == ["solo"])

seed_env("GEMINI_API_KEY=base\r\nGEMINI_API_KEY_3=three\r\nGEMINI_API_KEY_2=two\r\n")
check("gom biến đánh số, sắp theo SỐ (2 trước 3)",
      api_vault.get_keys("GEMINI_API_KEY") == ["base", "two", "three"],
      str(api_vault.get_keys("GEMINI_API_KEY")))

seed_env("GEMINI_API_KEY=a,b\r\nGEMINI_API_KEY_2=b\r\nGEMINI_API_KEY_3=c\r\n"
         "GEMINI_API_KEY_ENDPOINT=https://gw.example.com/v1\r\n")
keys = api_vault.get_keys("GEMINI_API_KEY")
check("trộn 2 cách + dedupe giữ thứ tự", keys == ["a", "b", "c"], str(keys))
check("KHÔNG nuốt nhầm biến *_ENDPOINT",
      "https://gw.example.com/v1" not in keys, str(keys))
check("endpoint vẫn đọc được như cũ",
      api_vault.get_endpoint("GEMINI_API_KEY") == "https://gw.example.com/v1")

seed_env("OPENAI_API_KEY=x\r\n")
# brain_manager gọi load_dotenv() lúc import -> key THẬT của máy có thể đang nằm trong
# os.environ, mà get_key có fallback environ (đúng thiết kế). Dọn sạch rồi mới đo.
_saved_env = {k: v for k, v in os.environ.items() if k.startswith("GEMINI_API_KEY")}
for _k in list(_saved_env):
    os.environ.pop(_k, None)
check("không có key (file lẫn environ) -> []", api_vault.get_keys("GEMINI_API_KEY") == [],
      str(api_vault.get_keys("GEMINI_API_KEY")))
os.environ["GEMINI_API_KEY"] = "only-in-environ"
check("file không có nhưng environ có -> vẫn lấy được",
      api_vault.get_keys("GEMINI_API_KEY") == ["only-in-environ"])
os.environ.pop("GEMINI_API_KEY", None)
for _k, _v in _saved_env.items():
    os.environ[_k] = _v
check("tên rỗng -> []", api_vault.get_keys("") == [])
os.environ["ZZZ_TEST_KEY_2"] = "fromenv2"
os.environ["ZZZ_TEST_KEY"] = "fromenv1"
check("đọc được cả key chỉ có trong os.environ",
      api_vault.get_keys("ZZZ_TEST_KEY") == ["fromenv1", "fromenv2"],
      str(api_vault.get_keys("ZZZ_TEST_KEY")))
os.environ.pop("ZZZ_TEST_KEY_2", None)
os.environ.pop("ZZZ_TEST_KEY", None)

# =====================================================================
hr("6. GeminiBrain xoay vòng key (SDK giả)")

CFG = []
GEN_CALLS = []
RAISE_NEXT = {}


class _FakeResp:
    def __init__(self, text):
        self.text = text


class _FakeModel:
    def __init__(self, model_name=None, *a, **k):
        self.model_name = model_name
        # Key ĐANG hiệu lực lúc model được tạo (SDK thật: model cache client lúc gọi đầu).
        self.key = CFG[-1]["api_key"] if CFG else None

    def generate_content(self, prompt, **kw):
        GEN_CALLS.append(self.key)
        err = RAISE_NEXT.get(self.key)
        if err:
            raise RuntimeError(err)
        return _FakeResp(f"reply from {self.key}")


class _FakeGenai:
    GenerativeModel = _FakeModel

    @staticmethod
    def configure(api_key=None, **kw):
        CFG.append({"api_key": api_key, **kw})

    @staticmethod
    def upload_file(path=None):
        return object()


GOOGLE_MOD = type(sys)("google")
GOOGLE_MOD.generativeai = _FakeGenai
sys.modules["google"] = GOOGLE_MOD
sys.modules["google.generativeai"] = _FakeGenai

import importlib  # noqa: E402

gemini_mod = importlib.import_module("agent.gemini_brain")
importlib.reload(gemini_mod)
GeminiBrain = gemini_mod.GeminiBrain

CFG.clear()
g1 = GeminiBrain(api_key="only")
check("1 key -> configure đúng 1 lần ở constructor (hành vi cũ)",
      len(CFG) == 1 and CFG[0]["api_key"] == "only", str(CFG))
GEN_CALLS.clear()
check("1 key -> ask_text trả lời bình thường", g1.ask_text("hi") == "reply from only")
check("1 key -> không configure lại", len(CFG) == 1, str(len(CFG)))

CFG.clear()
GEN_CALLS.clear()
gemini_mod._rr_index = 0
g3 = GeminiBrain(api_key="k1", api_keys=["k1", "k2", "k3"])
check("nhiều key -> constructor vẫn chỉ configure 1 lần", len(CFG) == 1, str(len(CFG)))
r1, r2, r3, r4 = (g3.ask_text("p") for _ in range(4))
check("3 key -> 3 lượt gọi dùng 3 key khác nhau theo vòng",
      GEN_CALLS[:3] == ["k1", "k2", "k3"], str(GEN_CALLS))
check("lượt thứ 4 quay lại key #1 (round-robin)", GEN_CALLS[3] == "k1", str(GEN_CALLS))
check("mỗi lượt đều dựng lại model sau configure (key mới có hiệu lực)",
      r1 == "reply from k1" and r2 == "reply from k2" and r3 == "reply from k3")

# Failover: key đang tới lượt bị 429 -> nhảy key kế
CFG.clear()
GEN_CALLS.clear()
RAISE_NEXT.clear()
gemini_mod._rr_index = 0
RAISE_NEXT["k1"] = "429 Resource has been exhausted (quota)"
g4 = GeminiBrain(api_key="k1", api_keys=["k1", "k2", "k3"])
ans = g4.ask_text("p")
check("key hết quota -> tự nhảy sang key kế", ans == "reply from k2", ans)
check("failover có thử lại đúng thứ tự", GEN_CALLS == ["k1", "k2"], str(GEN_CALLS))

# Timeout -> KHÔNG đổi key (đổi key không chữa được chậm)
GEN_CALLS.clear()
RAISE_NEXT.clear()
gemini_mod._rr_index = 0
RAISE_NEXT["k1"] = "504 Deadline Exceeded: timeout of 15s"
g5 = GeminiBrain(api_key="k1", api_keys=["k1", "k2", "k3"])
check("timeout -> trả rỗng (để caller bù offline)", g5.ask_text("p") == "")
# v1.7.3: timeout nay được thử thêm ĐÚNG 1 MODEL dự phòng (bệnh gemini-flash-latest treo
# >120s), nhưng vẫn TUYỆT ĐỐI không đổi KEY — đó mới là điều assert này canh.
check("timeout -> KHÔNG thử key khác", set(GEN_CALLS) == {"k1"}, str(GEN_CALLS))
check("timeout -> thử tối đa 1 model dự phòng (không đốt hết danh sách)",
      len(GEN_CALLS) <= 2, str(GEN_CALLS))

# Mọi key đều hỏng -> rỗng, không ném
GEN_CALLS.clear()
RAISE_NEXT.clear()
gemini_mod._rr_index = 0
for k in ("k1", "k2", "k3"):
    RAISE_NEXT[k] = "429 quota exceeded"
g6 = GeminiBrain(api_key="k1", api_keys=["k1", "k2", "k3"])
check("mọi key hết quota -> trả rỗng, không ném", g6.ask_text("p") == "")
check("thử tối đa 3 lượt", len(GEN_CALLS) == 3, str(GEN_CALLS))
RAISE_NEXT.clear()

# analyze_screen có xoay key mà KHÔNG deadlock (lock không reentrant)
GEN_CALLS.clear()
gemini_mod._rr_index = 0
g7 = GeminiBrain(api_key="k1", api_keys=["k1", "k2"])
res = g7.analyze_screen("p", os.path.join(TMP, "x.png"))
check("analyze_screen nhiều key chạy xong (không treo vì lock lồng nhau)",
      isinstance(res, dict), str(type(res)))

# brain_manager gom key
os.environ["GEMINI_API_KEY"] = "env1,env2"
os.environ.pop("GEMINI_API_KEY_ENDPOINT", None)
bm = importlib.import_module("agent.brain_manager")
importlib.reload(bm)
CFG.clear()
GEN_CALLS.clear()
brain = bm.BrainManager.get_brain("gemini")
check("brain_manager gom được 2 key từ 1 biến", getattr(brain, "_keys", []) == ["env1", "env2"],
      str(getattr(brain, "_keys", None)))
check("brain_manager: vẫn configure 1 lần lúc tạo brain", len(CFG) == 1, str(CFG))
os.environ["GEMINI_API_KEY"] = ""
try:
    bm.BrainManager.get_brain("gemini")
    _raised = False
except ValueError:
    _raised = True
check("không có key -> vẫn báo lỗi rõ như cũ", _raised)
os.environ.pop("GEMINI_API_KEY", None)

# =====================================================================
hr("7. GUI thật — nhiều dòng -> xem trước -> Áp dụng")

import tkinter as tk  # noqa: E402

ui_root = tk.Tk()
ui_root.withdraw()
app = ui.AutomationApp(ui_root)

_orig_detect = ui._detect_brain_type_from_env
ui._detect_brain_type_from_env = lambda: None  # ép offline, tất định, không gọi mạng
app.var_brain_type.set("none")
app.var_kw_lang.set("en")
app.var_pinned_theme.set("Health\nBuy clothes\ngo to the party")

check("_seed_themes tách đúng 3 dòng",
      [p["google_query"] for p in app._seed_themes()] == ["Health", "Buy clothes", "go to the party"],
      str([p["google_query"] for p in app._seed_themes()]))

app.profile_rows = []
for i in range(3):
    app.profile_rows.append({
        "id": f"{i:08d}-0000-0000-0000-000000000000",
        "name": f"P{i}", "firefox": False, "hidden": False,
        "var": tk.BooleanVar(value=True),
    })

captured = {}
_orig_preview = app._show_generated_topics_preview
app._show_generated_topics_preview = lambda seed, topics: captured.update(seed=seed, topics=topics)
app.on_generate_topics()
_dl = time.time() + 5
while "topics" not in captured and time.time() < _dl:
    ui_root.update()
    time.sleep(0.02)
app._show_generated_topics_preview = _orig_preview

tp = captured.get("topics", [])
# v1.7.3 VÁ CÓ CHỦ ĐÍCH: số chủ đề nay = số DÒNG GỐC × ô "Số chủ đề/dòng" (mặc định 5),
# sàn = số profile đang tick. Assert cũ ("== 3 = số profile") chính là hành vi bị báo lỗi.
_per171 = app._topics_per_seed()
_exp171 = max(3, 3 * _per171)
check("GUI: sinh 3 dòng gốc × N chủ đề (v1.7.3, không còn = số profile)",
      len(tp) == _exp171, f"{len(tp)} (chờ {_exp171})")
check("GUI: chủ đề trải ĐỦ 3 DÒNG GỐC KHÁC NHAU",
      sorted(set(t.get("seed", "") for t in tp)) == ["Buy clothes", "Health", "go to the party"],
      str(sorted(set(t.get("seed", "") for t in tp))))
check("GUI: mỗi dòng gốc được ĐÚNG N chủ đề (hạn ngạch chia đều)",
      all(sum(1 for t in tp if t.get("seed") == _s) == _per171
          for _s in ("Health", "Buy clothes", "go to the party")),
      str([(_s, sum(1 for t in tp if t.get("seed") == _s))
           for _s in ("Health", "Buy clothes", "go to the party")]))
check("GUI: không chủ đề nào gộp nhiều dòng",
      not [t for t in tp if "Health" in t["google_query"] and "Buy clothes" in t["google_query"]],
      str(gq(tp)))
check("GUI: nút bật lại sau khi sinh", not app.btn_gen_topics.instate(["disabled"]))
check("GUI: _gen_seeds lưu từng dòng cho nhánh deadline",
      app._gen_seeds == ["Health", "Buy clothes", "go to the party"], str(app._gen_seeds))
check("GUI: _gen_seed (chuỗi hiển thị) vẫn còn cho tương thích",
      isinstance(app._gen_seed, str) and "Health" in app._gen_seed, app._gen_seed)

# Dialog xem trước THẬT: có cột "Từ dòng gốc" + bấm Áp dụng
app._show_generated_topics_preview(app._gen_seed, tp)
ui_root.update()


def find_toplevel(title):
    for w in ui_root.winfo_children():
        if isinstance(w, tk.Toplevel):
            try:
                if str(w.title()) == title:
                    return w
            except Exception:
                pass
    return None


dlg = find_toplevel("Xem trước chủ đề vừa sinh")
check("mở được dialog xem trước", dlg is not None)

from tkinter import ttk  # noqa: E402


def walk(w, out=None):
    out = out if out is not None else []
    for c in w.winfo_children():
        out.append(c)
        walk(c, out)
    return out


tree = None
btn_apply = None
if dlg is not None:
    for w in walk(dlg):
        if isinstance(w, ttk.Treeview) and tree is None:
            tree = w
        if isinstance(w, ttk.Button) and "Áp dụng" in (w.cget("text") or ""):
            btn_apply = w

check("dialog có cột 'Từ dòng gốc'",
      tree is not None and "seed" in tuple(tree.cget("columns")) and
      tree.heading("seed")["text"] == "Từ dòng gốc",
      str(tree.cget("columns")) if tree else "(không có tree)")
if tree is not None:
    col_seeds = [tree.set(iid, "seed") for iid in tree.get_children()]
    # v1.7.3: mỗi dòng gốc nay có N chủ đề nên cột lặp lại tên dòng -> so trên TẬP hợp.
    check("cột 'Từ dòng gốc' hiện đủ 3 dòng khác nhau",
          sorted(set(col_seeds)) == ["Buy clothes", "Health", "go to the party"], str(col_seeds))

check("dialog có nút Áp dụng", btn_apply is not None)
if btn_apply is not None:
    btn_apply.invoke()
    ui_root.update()
    applied = app._collect_kw_pairs()
    check("Áp dụng -> đổ đúng 3 chủ đề vào danh sách CHỦ ĐỀ XUYÊN SUỐT",
          [p["google_query"] for p in applied] == gq(tp),
          str([p["google_query"] for p in applied]))
    check("Áp dụng -> ô 'Chủ đề gốc' được clear", app._pinned_theme_text() == "",
          app._pinned_theme_text())
    check("dialog đóng sau khi Áp dụng", find_toplevel("Xem trước chủ đề vừa sinh") is None)

ui._detect_brain_type_from_env = _orig_detect
try:
    ui_root.destroy()
except Exception:
    pass

# =====================================================================
hr("8. Kiểm tra tĩnh + .env thật không bị đụng")

src = read_src("ui_main.py")
check("ui_main: KHÔNG còn nối các dòng gốc bằng ', '.join",
      '", ".join(p["google_query"] for p in self._seed_themes())' not in src)
check("ui_main: có hàm generate_topics_for_seeds", "def generate_topics_for_seeds(" in src)
check("ui_main: chữ ký generate_topics_from_seed GIỮ NGUYÊN (test cũ ghim)",
      'def generate_topics_from_seed(seed, n, brain=None, rng=None, log=None, lang="en")' in src)
_og = src.split("def on_generate_topics")[1].split("\n    def ", 1)[0]
check("on_generate_topics: dùng generate_topics_for_seeds", "generate_topics_for_seeds(" in _og)
check("on_generate_topics: lưu _gen_seeds", "_gen_seeds" in _og)
check("on_generate_topics: hàng rào co giãn theo số dòng", "_ai_seeds" in _og)
_poll = src.split("def _poll_generated")[1].split("\n    def ", 1)[0]
check("_poll_generated: nhánh deadline chia theo từng dòng",
      "generate_topics_for_seeds(" in _poll and "brain=None" in _poll)
check("_poll_generated: có cập nhật tiến trình nút", "_gen_progress" in _poll)

_vault = read_src("api_vault.py")
check("api_vault: có get_keys", "def get_keys(" in _vault)
check("api_vault: chỉ nhận hậu tố SỐ cho biến đánh số", "_NUMBERED_SUFFIX_RE" in _vault)

_gem = read_src("agent/gemini_brain.py")
check("gemini_brain: nhận api_keys", "api_keys=None" in _gem)
check("gemini_brain: dựng lại model sau khi configure (bắt buộc)",
      "genai.GenerativeModel(self.model_name)" in _gem)
check("gemini_brain: giữ timeout per-call v1.6.8",
      "_GEMINI_TIMEOUT_S" in _gem and "request_options" in _gem)
check("gemini_brain: không xoay key khi lỗi timeout",
      "_ROTATE_ON" in _gem and "timeout" not in _gem.split("_ROTATE_ON = ")[1].split(")")[0])

_bm = read_src("agent/brain_manager.py")
check("brain_manager: gom nhiều key cho gemini", "_collect_keys(\"GEMINI_API_KEY\")" in _bm)
check("brain_manager: import api_vault có bọc try", "except Exception:" in _bm and "_get_keys" in _bm)

check(".env THẬT không bị suite này đụng tới",
      file_hash(REAL_ENV) == REAL_ENV_HASH_BEFORE,
      f"{REAL_ENV_HASH_BEFORE} -> {file_hash(REAL_ENV)}")

# =====================================================================
hr("9. v1.7.2 — brain Claude qua cổng tương thích OpenAI + xoay key cho brain đó")

OAI_CTORS = []
OAI_CALLS = []
OAI_RAISE = {}


class _FakeChoiceMsg:
    def __init__(self, content):
        self.message = type("M", (), {"content": content})()


class _FakeCompletions:
    def __init__(self, key):
        self.key = key

    def create(self, model=None, messages=None, **kw):
        OAI_CALLS.append({"key": self.key, "model": model})
        err = OAI_RAISE.get(self.key)
        if err:
            raise RuntimeError(err)
        return type("R", (), {"choices": [_FakeChoiceMsg(f"reply from {self.key}")]})()


class _FakeOpenAI:
    def __init__(self, **kwargs):
        OAI_CTORS.append(kwargs)
        self.chat = type("C", (), {"completions": _FakeCompletions(kwargs.get("api_key"))})()


OPENAI_MOD = type(sys)("openai")
OPENAI_MOD.OpenAI = _FakeOpenAI
sys.modules["openai"] = OPENAI_MOD

ob = importlib.import_module("agent.openai_brain")
importlib.reload(ob)
GenericLLMBrain = ob.GenericLLMBrain

OAI_CTORS.clear()
g = GenericLLMBrain(api_key="only", model_name="m1", base_url="https://gw/v1")
check("1 key -> dựng đúng 1 client lúc tạo (hành vi cũ)",
      len(OAI_CTORS) == 1 and OAI_CTORS[0].get("base_url") == "https://gw/v1", str(OAI_CTORS))
check("1 key -> ask_text trả lời bình thường", g.ask_text("p") == "reply from only")

OAI_CTORS.clear()
OAI_CALLS.clear()
ob._rr_index = 0
g3 = GenericLLMBrain(api_key="c1", api_keys=["c1", "c2", "c3"], model_name="claude-sonnet-5-5",
                     base_url="https://api.mwapi.dev/v1")
check("nhiều key -> vẫn chỉ dựng 1 client lúc tạo (còn lại dựng lười)",
      len(OAI_CTORS) == 1, str(len(OAI_CTORS)))
for _ in range(4):
    g3.ask_text("p")
check("3 key -> xoay vòng c1,c2,c3 rồi quay lại c1",
      [c["key"] for c in OAI_CALLS] == ["c1", "c2", "c3", "c1"], str([c["key"] for c in OAI_CALLS]))
check("model đúng model Claude", all(c["model"] == "claude-sonnet-5-5" for c in OAI_CALLS))
check("mỗi key 1 client riêng, dựng lười đủ 3", len(OAI_CTORS) == 3, str(len(OAI_CTORS)))

OAI_CALLS.clear()
OAI_RAISE.clear()
ob._rr_index = 0
OAI_RAISE["c1"] = "Error code: 429 - insufficient_quota: no credits remaining"
g4 = GenericLLMBrain(api_key="c1", api_keys=["c1", "c2"], model_name="m")
check("hết credit -> tự nhảy key kế", g4.ask_text("p") == "reply from c2")
check("failover đúng thứ tự", [c["key"] for c in OAI_CALLS] == ["c1", "c2"],
      str([c["key"] for c in OAI_CALLS]))

OAI_CALLS.clear()
OAI_RAISE.clear()
ob._rr_index = 0
OAI_RAISE["c1"] = "Request timed out."
g5 = GenericLLMBrain(api_key="c1", api_keys=["c1", "c2"], model_name="m")
check("timeout -> KHÔNG đổi key, trả rỗng",
      g5.ask_text("p") == "" and [c["key"] for c in OAI_CALLS] == ["c1"],
      str([c["key"] for c in OAI_CALLS]))
OAI_RAISE.clear()

# brain_manager: nhánh Claude
bm2 = importlib.import_module("agent.brain_manager")
importlib.reload(bm2)
for _k in ("CLAUDE_API_KEY", "CLAUDE_LAU", "CLAUDE_API_KEY_ENDPOINT", "CLAUDE_LAU_ENDPOINT"):
    os.environ.pop(_k, None)
seed_env("CLAUDE_LAU=lau1,lau2\r\nCLAUDE_LAU_ENDPOINT=https://api.mwapi.dev/v1\r\n")
os.environ["CLAUDE_LAU"] = "lau1,lau2"
os.environ["CLAUDE_LAU_ENDPOINT"] = "https://api.mwapi.dev/v1"

OAI_CTORS.clear()
b = bm2.BrainManager.get_brain("claude-sonnet")
check("get_brain('claude-sonnet') -> model claude-sonnet-5-5",
      b.model_name == "claude-sonnet-5-5", b.model_name)
check("dùng endpoint của key (cổng tương thích OpenAI)",
      OAI_CTORS and OAI_CTORS[-1].get("base_url") == "https://api.mwapi.dev/v1", str(OAI_CTORS[-1:]))
check("gom được 2 key Claude để xoay vòng", b._keys == ["lau1", "lau2"], str(b._keys))
b2 = bm2.BrainManager.get_brain("claude-haiku")
check("get_brain('claude-haiku') -> model claude-haiku-5-5",
      b2.model_name == "claude-haiku-5-5", b2.model_name)

os.environ.pop("CLAUDE_LAU_ENDPOINT", None)
seed_env("CLAUDE_LAU=lau1\r\n")
try:
    bm2.BrainManager.get_brain("claude-sonnet")
    _msg = ""
except ValueError as e:
    _msg = str(e)
check("thiếu Endpoint -> báo lỗi CHỈ RÕ cách sửa",
      "Endpoint" in _msg and "QUẢN LÝ API KEY" in _msg, _msg[:80])

for _k in ("CLAUDE_LAU", "CLAUDE_API_KEY"):
    os.environ.pop(_k, None)
seed_env("")
try:
    bm2.BrainManager.get_brain("claude-haiku")
    _msg2 = ""
except ValueError as e:
    _msg2 = str(e)
check("không có key Claude -> báo thiếu key", "Thiếu key Claude" in _msg2, _msg2[:60])

# auto-pick: claude đứng đầu, nhưng CHỈ khi có cả key lẫn endpoint
_env_orig = ui.os.getenv


def _fake_env(mapping):
    def _g(k, default=None):
        return mapping.get(k, default)
    return _g


ui.os.getenv = _fake_env({"CLAUDE_LAU": "x", "CLAUDE_LAU_ENDPOINT": "https://gw/v1",
                          "GEMINI_API_KEY": "y"})
check("có key+endpoint Claude -> auto-pick 'claude-sonnet' (trước gemini)",
      ui._detect_brain_type_from_env() == "claude-sonnet", str(ui._detect_brain_type_from_env()))
ui.os.getenv = _fake_env({"CLAUDE_LAU": "x", "GEMINI_API_KEY": "y"})
check("Claude thiếu endpoint -> bỏ qua, quay về 'gemini'",
      ui._detect_brain_type_from_env() == "gemini")
ui.os.getenv = _fake_env({"CLAUDE_API_KEY": "x", "CLAUDE_API_KEY_ENDPOINT": "https://gw/v1"})
check("tên chuẩn CLAUDE_API_KEY cũng nhận", ui._detect_brain_type_from_env() == "claude-sonnet")
ui.os.getenv = _fake_env({})
check("không key nào -> None (không đổi)", ui._detect_brain_type_from_env() is None)
ui.os.getenv = _env_orig

_um = read_src("ui_main.py")
check("ô AI Brain có claude-sonnet + claude-haiku",
      '"claude-sonnet", "claude-haiku"' in _um, "combobox")
check("hint cho 2 brain Claude", '"claude-sonnet": "(claude-sonnet-5-5' in _um)
_bm2 = read_src("agent/brain_manager.py")
check("brain_manager có CLAUDE_MODELS", "CLAUDE_MODELS = {" in _bm2)
check("brain_manager thử cả 2 tên key Claude",
      'CLAUDE_KEY_NAMES = ("CLAUDE_API_KEY", "CLAUDE_LAU")' in _bm2)
_ob = read_src("agent/openai_brain.py")
check("openai_brain: nhận api_keys", "api_keys=None" in _ob)
check("openai_brain: không xoay key khi timeout",
      "_ROTATE_ON" in _ob and "timeout" not in _ob.split("_ROTATE_ON = ")[1].split(")")[0])

# =====================================================================
print("\n" + "=" * 70)
print(f"PASS: {PASS}   FAIL: {FAIL}")
print("SMOKE v1.7.1+v1.7.2: ALL PASS" if FAIL == 0 else "SMOKE v1.7.1+v1.7.2: CÓ LỖI")
print("=" * 70)
sys.exit(1 if FAIL else 0)
