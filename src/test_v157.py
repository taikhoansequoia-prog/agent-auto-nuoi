# -*- coding: utf-8 -*-
"""Smoke test v1.5.7 — SINH N CHỦ ĐỀ TỪ 1 CHỦ ĐỀ GỐC (AI) + xem trước -> áp dụng.

Yêu cầu user 27/10/2026: ô "Ghim chủ đề" (1 input duy nhất) -> giờ là "Chủ đề gốc" +
nút "Sinh chủ đề (theo số profile)": gõ 1 chủ đề gốc, AI sinh N chủ đề con (N = số profile
đang chọn, có random), xem trước rồi áp dụng vào danh sách "CHỦ ĐỀ XUYÊN SUỐT". Danh sách đó
đi tiếp qua assign_topics_for_run (đã có) -> mỗi profile 1 chủ đề.

Kiểm tra OFFLINE (không cần browser). Chạy:  python src\\test_v157.py
DB test nằm ở thư mục tạm (GPM_BOT_DATA_DIR) — KHÔNG đụng data\\ thật.
"""
import os
import sys
import time
import tempfile

SRC = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(SRC)
for p in (ROOT, SRC):
    if p not in sys.path:
        sys.path.insert(0, p)

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

TMP = tempfile.mkdtemp(prefix="gpm_v157_")
os.environ["GPM_BOT_DATA_DIR"] = TMP

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


import src.ui_main as ui  # noqa: E402

gen = ui.generate_topics_from_seed
loc = ui._local_topic_variants


def goods(topics):
    """list chủ đề Google (lower) để kiểm phân biệt."""
    return [t["google_query"].strip().lower() for t in topics]


# =====================================================================
hr("1. generate_topics_from_seed — OFFLINE (brain=None)")
# =====================================================================
t5 = gen("chạy bộ", 5, brain=None)
check("brain=None, n=5 -> đúng 5 chủ đề", len(t5) == 5, str(len(t5)))
check("5 chủ đề PHÂN BIỆT (Google)", len(set(goods(t5))) == 5, str(goods(t5)))
check("mỗi chủ đề có google_query + youtube_query",
      all(t.get("google_query") and t.get("youtube_query") for t in t5))
check("chủ đề offline có chứa seed 'chạy bộ'",
      all("chạy bộ" in t["google_query"].lower() for t in t5), str(goods(t5)))

# n vượt số template (16) -> vẫn đủ & phân biệt (thêm hậu tố số)
t25 = gen("du lịch", 25, brain=None)
check("n=25 (> số mẫu) vẫn đúng 25", len(t25) == 25, str(len(t25)))
check("25 chủ đề PHÂN BIỆT", len(set(goods(t25))) == 25, str(len(set(goods(t25)))))

# biên an toàn
check("n=0 -> []", gen("x", 0, brain=None) == [])
check("n=-3 -> []", gen("x", -3, brain=None) == [])
check("n='abc' (rác) -> []", gen("x", "abc", brain=None) == [])
t_noseed = gen("", 4, brain=None)
check("seed rỗng + brain=None vẫn ra 4 chủ đề (dùng mặc định)", len(t_noseed) == 4, str(len(t_noseed)))
check("seed rỗng -> chủ đề phân biệt", len(set(goods(t_noseed))) == 4)

# _local_topic_variants trực tiếp
lv = loc("nấu ăn", 10)
check("_local_topic_variants('nấu ăn',10) -> 10 phân biệt",
      len(lv) == 10 and len(set(s.lower() for s in lv)) == 10, str(len(lv)))


# =====================================================================
hr("2. generate_topics_from_seed — CÓ AI Brain (stub) + parse phòng thủ")
# =====================================================================
class FakeBrain:
    def __init__(self, text):
        self.text = text
        self.calls = 0

    def ask_text(self, prompt):
        self.calls += 1
        self.last_prompt = prompt
        return self.text


# AI trả đúng định dạng "Google | YouTube"
ai_ok = FakeBrain(
    "1. tin thế giới hôm nay | world news today\n"
    "- xung đột trung đông | middle east conflict\n"
    "bầu cử mỹ 2026 | us election 2026\n"
    "kinh tế toàn cầu | global economy\n"
)
ta = gen("news the world", 4, brain=ai_ok)
check("AI gọi ask_text đúng 1 lần", ai_ok.calls == 1, str(ai_ok.calls))
check("AI, n=4 -> 4 chủ đề", len(ta) == 4, str(len(ta)))
check("parse bỏ số thứ tự '1.' -> google = 'tin thế giới hôm nay'",
      ta[0]["google_query"] == "tin thế giới hôm nay", ta[0]["google_query"])
check("parse bỏ bullet '- ' -> google = 'xung đột trung đông'",
      ta[1]["google_query"] == "xung đột trung đông", ta[1]["google_query"])
check("tách '|' -> youtube riêng 'world news today'",
      ta[0]["youtube_query"] == "world news today", ta[0]["youtube_query"])
check("prompt có nhắc chủ đề gốc + số lượng",
      "news the world" in ai_ok.last_prompt and "4" in ai_ok.last_prompt)
# v1.6.0/1.6.1: prompt phải ép ngôn ngữ (mặc định English) + từ khóa liên quan thực tế (trộn)
check("prompt sinh chủ đề ép English (mặc định)", "MUST be in English" in ai_ok.last_prompt)
check("prompt nhắc hoạt động thực tế (buy/weather) + học hỏi (review)",
      all(w in ai_ok.last_prompt.lower() for w in ("buy", "weather", "review")))

# AI trả THIẾU (2 dòng) cho n=6 -> offline bù đủ 6, không trùng phần AI
ai_short = FakeBrain("alpha topic | alpha yt\nbeta topic | beta yt\n")
ts = gen("khoa học", 6, brain=ai_short)
check("AI thiếu -> offline bù đủ n=6", len(ts) == 6, str(len(ts)))
check("6 chủ đề vẫn PHÂN BIỆT (AI + offline không trùng)", len(set(goods(ts))) == 6, str(goods(ts)))
check("giữ 2 chủ đề AI ở đầu", goods(ts)[:2] == ["alpha topic", "beta topic"], str(goods(ts)[:2]))

# AI trả TRÙNG dòng -> dedupe theo Google
ai_dup = FakeBrain("same one | a\nSAME ONE | b\nkhac | c\n")
td = gen("x", 5, brain=ai_dup)
check("dedupe dòng AI trùng (same one)", goods(td).count("same one") == 1, str(goods(td)))
check("dedupe xong vẫn đủ n=5 (offline bù)", len(td) == 5 and len(set(goods(td))) == 5)

# dòng không có '|' -> youtube = google
ai_nopipe = FakeBrain("chỉ một vế thôi\n")
tn = gen("seed", 1, brain=ai_nopipe)
check("dòng không có '|' -> youtube = google",
      tn[0]["google_query"] == "chỉ một vế thôi" and tn[0]["youtube_query"] == "chỉ một vế thôi")

# AI NÉM lỗi -> không vỡ, offline bù đủ
class BoomBrain:
    def ask_text(self, prompt):
        raise RuntimeError("API sập")


tb = gen("thể thao", 3, brain=BoomBrain())
check("AI ném exception -> offline bù đủ n=3 (không vỡ)", len(tb) == 3, str(len(tb)))

# AI trả rỗng -> offline bù
tbe = gen("âm nhạc", 3, brain=FakeBrain(""))
check("AI trả '' -> offline bù đủ n=3", len(tbe) == 3, str(len(tbe)))

# cắt query quá dài 90 ký tự
long_q = "a" * 120
tl = gen("x", 1, brain=FakeBrain(long_q + " | " + long_q))
check("query > 90 ký tự bị cắt còn 90",
      len(tl[0]["google_query"]) == 90 and len(tl[0]["youtube_query"]) == 90,
      f"{len(tl[0]['google_query'])}/{len(tl[0]['youtube_query'])}")


# =====================================================================
hr("3. GUI: nút 'Sinh chủ đề' + đếm N theo profile + xem trước + ÁP DỤNG")
# =====================================================================
import tkinter as tk  # noqa: E402

ui_root = tk.Tk()
app = ui.AutomationApp(ui_root)
ui_root.update()

check("Có btn_gen_topics", hasattr(app, "btn_gen_topics"))
check("Nhãn ô đổi thành 'Chủ đề gốc'", hasattr(app, "ent_pinned_theme"))


def _label_texts(widget):
    out = []
    try:
        for w in widget.winfo_children():
            if "Label" in w.winfo_class():
                try:
                    out.append(str(w.cget("text")))
                except Exception:
                    pass
            out.extend(_label_texts(w))
    except Exception:
        pass
    return out


_lbls = _label_texts(app.ent_pinned_theme.master)
check("Có nhãn 'Chủ đề gốc:' cạnh ô nhập", any("Chủ đề gốc" in t for t in _lbls), str(_lbls))

# btn_gen_topics nằm trong tuple disable khi chạy
app._set_utils_state("disabled")
check("btn_gen_topics DISABLE khi _set_utils_state('disabled')",
      app.btn_gen_topics.instate(["disabled"]))
app._set_utils_state("normal")
check("btn_gen_topics bật lại khi 'normal'", not app.btn_gen_topics.instate(["disabled"]))

src = read_src("ui_main.py")
check("btn_gen_topics cũng nằm trong tuple disable của start_automation",
      src.count("self.btn_gen_topics") >= 3,  # tạo + 2 tuple
      f"count={src.count('self.btn_gen_topics')}")

# --- Guard: seed rỗng -> báo, không sinh ---
_msg = {"info": 0, "warn": 0}
_orig_info = ui.messagebox.showinfo
_orig_warn = ui.messagebox.showwarning
ui.messagebox.showinfo = lambda *a, **k: _msg.__setitem__("info", _msg["info"] + 1)
ui.messagebox.showwarning = lambda *a, **k: _msg.__setitem__("warn", _msg["warn"] + 1)

app.var_pinned_theme.set("")
app.on_generate_topics()
check("seed rỗng -> showinfo nhắc + không treo nút", _msg["info"] == 1 and
      not app.btn_gen_topics.instate(["disabled"]))

# --- Đếm N = số profile đang chọn (tick & hiện & không firefox) ---
app.profile_rows = []
for i in range(3):
    app.profile_rows.append({
        "id": f"{i:08d}-0000-0000-0000-000000000000",
        "name": f"P{i}", "firefox": False, "hidden": False,
        "var": tk.BooleanVar(value=True),
    })
# 1 dòng bị ẩn + 1 firefox -> KHÔNG tính
app.profile_rows.append({"id": "ff", "name": "FF", "firefox": True, "hidden": False,
                         "var": tk.BooleanVar(value=True)})
app.profile_rows.append({"id": "hd", "name": "HD", "firefox": False, "hidden": True,
                         "var": tk.BooleanVar(value=True)})

app.var_brain_type.set("none")  # offline -> không gọi mạng, chạy tức thời trong thread
# v1.5.9: ô 'none' giờ TỰ dò brain từ .env; ép trả None để section này thuần offline/tất định.
_orig_detect = ui._detect_brain_type_from_env
ui._detect_brain_type_from_env = lambda: None
app.var_pinned_theme.set("tin thế giới")

captured = {}
_orig_preview = app._show_generated_topics_preview
app._show_generated_topics_preview = lambda seed, topics: captured.update(seed=seed, topics=topics)

app.on_generate_topics()
# chờ thread nền + root.after(0, _after_generate_topics) xử lý
_deadline = time.time() + 5
while "topics" not in captured and time.time() < _deadline:
    ui_root.update()
    time.sleep(0.02)

check("on_generate_topics -> mở xem trước", "topics" in captured)
check("N = đúng số profile đang chọn (3 — bỏ firefox + hidden)",
      len(captured.get("topics", [])) == 3, str(len(captured.get("topics", []))))
check("nút bật lại sau khi sinh xong", not app.btn_gen_topics.instate(["disabled"]))
app._show_generated_topics_preview = _orig_preview
ui._detect_brain_type_from_env = _orig_detect

# --- Dialog xem trước THẬT + bấm 'Áp dụng' -> đổ vào kw_rows + clear chủ đề gốc ---
topics3 = ui.generate_topics_from_seed("tin thế giới", 3, brain=None)
app.var_pinned_theme.set("tin thế giới")  # còn chữ -> sẽ bị clear sau Áp dụng
app._show_generated_topics_preview("tin thế giới", topics3)
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


def find_button(widget, text):
    try:
        for w in widget.winfo_children():
            if isinstance(w, ttk_button_types):
                try:
                    if str(w.cget("text")) == text:
                        return w
                except Exception:
                    pass
            found = find_button(w, text)
            if found is not None:
                return found
    except Exception:
        pass
    return None


from tkinter import ttk  # noqa: E402
ttk_button_types = (ttk.Button,)

win = find_toplevel("Xem trước chủ đề vừa sinh")
check("Dialog xem trước mở được", win is not None)
if win is not None:
    btn_apply = find_button(win, "Áp dụng")
    check("Có nút 'Áp dụng'", btn_apply is not None)
    check("Có nút 'Sinh lại'", find_button(win, "Sinh lại") is not None)
    check("Có nút 'Hủy'", find_button(win, "Hủy") is not None)
    if btn_apply is not None:
        btn_apply.invoke()
        ui_root.update()
        _pairs = app._collect_kw_pairs()  # v1.6.6: nguồn là ô Text, đọc qua _collect_kw_pairs
        g_in_rows = [(p["google_query"] or "").strip().lower() for p in _pairs]
        check("Áp dụng -> danh sách chủ đề có đúng 3 dòng", len(_pairs) == 3, str(len(_pairs)))
        check("danh sách chứa đúng chủ đề đã sinh",
              set(g_in_rows) == set(goods(topics3)), str(g_in_rows))
        check("ô 'Chủ đề gốc' đã được CLEAR sau Áp dụng (không còn ghim)",
              app._pinned_theme_text() == "", repr(app._pinned_theme_text()))

ui.messagebox.showinfo = _orig_info
ui.messagebox.showwarning = _orig_warn


# =====================================================================
hr("4. Regression — plumbing pinned_theme KHÔNG đổi (test_v153 phụ thuộc)")
# =====================================================================
check("run_single_profile vẫn có 'pinned_theme=\"\"' trong chữ ký",
      'pinned_theme="", assigned_theme=None):' in src or 'pinned_theme=""' in src)
check("Thread args kết thúc bằng 'pinned_theme, kw_lang)' (v1.6.1 thêm ngôn ngữ)",
      "daily_seconds, pinned_theme, kw_lang), daemon=True" in src)
check("worker_wrapper submit truyền 'pinned_theme, keyword_lang)' cuối (v1.6.1)",
      "daily_seconds, pinned_theme, keyword_lang) for pid in profiles" in src)
check("assign_topics_for_run vẫn còn (phân bổ chủ đề cho profile)",
      "def assign_topics_for_run(" in src)
check("_collect_kw_pairs vẫn còn (nguồn chủ đề cho phân bổ)",
      "def _collect_kw_pairs(" in src)

try:
    ui_root.destroy()
except Exception:
    pass

# =====================================================================
hr("5. v1.5.9 — tự dò AI Brain từ .env + log callback trong sinh chủ đề")
# =====================================================================
_env_orig = ui.os.getenv


def _fake_env(mapping):
    def _g(k, default=None):
        return mapping.get(k, default)
    return _g


ui.os.getenv = _fake_env({"GEMINI_API_KEY": "x"})
check("có GEMINI_API_KEY -> auto-pick 'gemini'", ui._detect_brain_type_from_env() == "gemini")
ui.os.getenv = _fake_env({"OPENAI_API_KEY": "x"})
check("chỉ có OPENAI_API_KEY -> auto-pick 'openai'", ui._detect_brain_type_from_env() == "openai")
ui.os.getenv = _fake_env({"QWEN_API_KEY": "x"})
check("chỉ có QWEN_API_KEY -> auto-pick 'qwen-max'", ui._detect_brain_type_from_env() == "qwen-max")
ui.os.getenv = _fake_env({})
check("không key nào -> auto-pick None", ui._detect_brain_type_from_env() is None)
ui.os.getenv = _env_orig

# log callback nhận được các bước (offline path)
_lines = []
gen("nấu ăn", 3, brain=None, log=_lines.append)
check("log callback NHẬN dòng offline", any("offline" in l.lower() for l in _lines), str(len(_lines)))

# log callback nhận AI thiếu -> có dòng 'AI' + 'offline bù'
class _Stub:
    def ask_text(self, p):
        return "alpha | a\n"  # chỉ 1 dòng cho n=3


_lines2 = []
gen("khoa học", 3, brain=_Stub(), log=_lines2.append)
check("log có dòng 'hỏi AI'", any("hỏi AI" in l for l in _lines2), str(_lines2))
check("log có dòng AI trả về N dòng", any("AI trả về" in l for l in _lines2))
check("log callback không throw khi log=None", gen("x", 2, brain=None, log=None) is not None)

check("generate_topics_from_seed có tham số 'log'", "log=None" in
      read_src("ui_main.py").split("def generate_topics_from_seed")[1][:120])
check("_detect_brain_type_from_env tồn tại (module-level)",
      "def _detect_brain_type_from_env(" in src)
check("on_generate_topics tự dò brain khi 'none'",
      "_detect_brain_type_from_env()" in src and "auto_pick" in src)
check("worker gom log vào list (không print chéo luồng)",
      "logs.append" in src and "log=logs.append" in src)

# =====================================================================
hr("6. v1.6.8 — chống treo 'Sinh chủ đề' (Gemini timeout + hàng rào deadline UI)")

# (a) Gemini ask_text có timeout per-call (fail-fast thay vì treo 80s+).
_gem = read_src("agent/gemini_brain.py")
_ask = _gem.split("def ask_text")[1].split("def ", 1)[0]
check("gemini_brain: ask_text truyền request_options timeout",
      "request_options" in _ask and "timeout" in _ask)
check("gemini_brain: có hằng số _GEMINI_TIMEOUT_S (env override)",
      "_GEMINI_TIMEOUT_S" in _gem and "GEMINI_TIMEOUT" in _gem)

# (b) _poll_generated có hàng rào deadline + one-shot để không chờ vô hạn.
_poll = src.split("def _poll_generated")[1].split("\n    def ", 1)[0]
check("_poll_generated: dùng _gen_deadline", "_gen_deadline" in _poll)
check("_poll_generated: cờ one-shot _gen_finished", "_gen_finished" in _poll)
check("_poll_generated: nhánh deadline dựng offline (brain=None)",
      "generate_topics_from_seed" in _poll and "brain=None" in _poll)
check("on_generate_topics: lưu ngữ cảnh cho nhánh deadline",
      "_gen_seed" in src and "_gen_token" in src)

# (c) fail-fast -> offline: brain trả rỗng (giả lập Gemini timeout) vẫn ra đủ N.
class _EmptyBrain:
    def ask_text(self, p):
        return ""  # như ask_text khi generate_content raise/timeout


_tp = gen("đi bộ", 4, brain=_EmptyBrain())
check("brain trả rỗng (timeout) -> vẫn ra đủ N offline", len(_tp) == 4, str(len(_tp)))
check("offline topics có google_query phân biệt",
      len({t["google_query"].lower() for t in _tp}) == 4)

# =====================================================================
print("\n" + "=" * 70)
print(f"PASS: {PASS}   FAIL: {FAIL}")
print("SMOKE v1.5.7: ALL PASS" if FAIL == 0 else "SMOKE v1.5.7: CÓ LỖI")
print("=" * 70)
sys.exit(1 if FAIL else 0)
