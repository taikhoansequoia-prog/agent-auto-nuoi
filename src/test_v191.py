# -*- coding: utf-8 -*-
"""Smoke test v1.9.1 — TRỢ LÝ HỎI ĐÁP AI (chỉ đọc, che email/IP) + giải thích profile GPM không còn thấy.

1) Masker: che / ghép lại email + IP, mã ổn định, không che nhầm số phiên bản
2) Nhận ra profile được nhắc đích danh ('warmup 1' không khớp 'warmup 17')
3) build_context: dữ liệu thật của app, KHÔNG sót email/IP, có log khi hỏi 'vì sao'
4) answer_question: lời dặn hệ thống riêng, ghép tên thật, lịch sử, lỗi AI, hàng rào chống lộ
5) GenericLLMBrain.ask_chat
6) antidetect: 'insufficient_permission_profile' có lời giải thích
7) GUI thật: nút trên thanh công cụ, cửa sổ, hỏi -> trả lời, không khóa khi đang chạy, đổi nền

Chạy OFFLINE: python src/test_v191.py
"""
import datetime
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
os.environ["GPM_BOT_DATA_DIR"] = tempfile.mkdtemp(prefix="gpm_v191_")
os.environ["GPM_BOT_ENV_FILE"] = os.path.join(os.environ["GPM_BOT_DATA_DIR"], ".env")

from src import qa_agent  # noqa: E402
from src.database.db_handler import DatabaseHandler  # noqa: E402

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


print("\n== 1. Masker")
m = qa_agent.Masker()
src_txt = "MAIL194 - Mai.thu.nghiem194@gmail.com dùng proxy 103.75.72.166; MAIL201 - b.c@gmail.com cũng 103.75.72.166"
masked = m.mask(src_txt)
check("email + IP biến mất", "@" not in masked and "103.75" not in masked, masked)
check("giữ phần tên không nhạy cảm", masked.startswith("MAIL194 - EMAIL_01 dùng proxy PROXY_01"), masked)
check("cùng giá trị -> cùng mã", masked.count("PROXY_01") == 2 and "EMAIL_02" in masked)
check("không phân biệt hoa thường", m.mask("mai.thu.nghiem194@GMAIL.com") == "EMAIL_01")
check("ghép lại đúng nguyên văn", m.unmask(masked) == src_txt)
check("AI nhắc mã trong câu -> ghép tên thật", m.unmask("Proxy PROXY_01 có 2 acc: EMAIL_01, EMAIL_02.")
      == "Proxy 103.75.72.166 có 2 acc: Mai.thu.nghiem194@gmail.com, b.c@gmail.com.")
check("mã lạ AI tự bịa thì để nguyên", m.unmask("EMAIL_77") == "EMAIL_77")
check("không che nhầm số phiên bản / số quá 255", m.mask("chrome 155.0.8059.85, 999.1.1.1, v1.9.1")
      == "chrome 155.0.8059.85, 999.1.1.1, v1.9.1")
check("leaks() bắt được thứ còn sót", m.leaks("x a@b.co y 10.0.0.1") == ["a@b.co", "10.0.0.1"] and m.leaks(masked) == [])

print("\n== 2. Nhận ra profile được nhắc tới")
P = [{"id": "c7cfd420-40da-451c-804e-c60953ec8326", "name": "Profile warmup 1", "group": "Mail lô đang ngâm"},
     {"id": "e3047d25-9d45-4337-8375-3e3e6bf2bd50", "name": "Profile warmup 17", "group": "Mail lô đang ngâm"},
     {"id": "227e4285-0000-0000-0000-000000000001", "name": "MAIL194 - mai.thu.nghiem194@gmail.com", "group": "G2"},
     {"id": "a2756b32-0000-0000-0000-000000000002", "name": "MAIL201 - mucangchai@gmail.com", "group": "G2"}]
mp = qa_agent.mentioned_profiles
check("'warmup 17' chỉ khớp warmup 17", mp("vì sao warmup 17 đọc 0 bài?", P) == [P[1]["id"]])
check("'warmup 1' KHÔNG khớp warmup 17", mp("warmup 1 hôm nay chạy chưa", P) == [P[0]["id"]])
check("gọi bằng mã MAIL", mp("mail194 lỗi gì", P) == [P[2]["id"]])
check("gọi bằng 8 ký tự id", mp("profile a2756b32 thế nào", P) == [P[3]["id"]])
check("không nhắc ai -> rỗng", mp("hôm nay có gì lỗi", P) == [])

print("\n== 3. build_context trên dữ liệu thật của app (DB tạm)")
db = DatabaseHandler()
now = datetime.datetime.now()


def ts(minutes_ago):
    return (now - datetime.timedelta(minutes=minutes_ago)).strftime("%Y-%m-%dT%H:%M:%S")


db.log_cycle(P[0]["id"], ts(90), ts(78), 731.0, "ok", actions=2, phase="clean", target_s=720)
db.log_cycle(P[1]["id"], ts(60), ts(58), 142.0, "error", actions=1, phase="clean",
             error="Trình duyệt/tab của phiên đã bị đóng giữa chừng — kết thúc phiên sớm.")
db.log_cycle(P[2]["id"], ts(30), ts(30), 0.0, "error", actions=0, phase="mail",
             error="Khong lay duoc WebSocket URL - Arg_NullReferenceException")
db.log_activity(P[0]["id"], "search_google", "Google", "https://www.google.com/search?q=x", "", status="ok", duration_s=227)
db.log_activity(P[1]["id"], "action_search_maps", "GoogleMaps", "", "", status="error", duration_s=3, error="Timeout 50000ms")
db.set_profile_start_date(P[0]["id"], (now - datetime.timedelta(days=2)).strftime("%Y-%m-%d"))
db.set_profile_start_date(P[1]["id"], (now - datetime.timedelta(days=9)).strftime("%Y-%m-%d"))
logs_dir = os.path.join(os.environ["GPM_BOT_DATA_DIR"], "logs")
os.makedirs(logs_dir, exist_ok=True)
with open(os.path.join(logs_dir, P[1]["id"] + ".log"), "w", encoding="utf-8") as f:
    f.write("\n".join(f"dòng cũ {i}" for i in range(200)) + "\n[!] Lỗi vào Maps: Timeout 50000ms — proxy 103.75.72.166\n"
            "[Profile warmup 17] đăng nhập thử lộ.mail@gmail.com\n")
ip_of = {P[0]["id"]: "103.75.72.110", P[1]["id"]: "103.75.72.166", P[2]["id"]: "103.75.72.166", P[3]["id"]: "103.75.72.166"}
big = [{"id": f"x{i:07d}-0000", "name": f"MAIL9{i} - user{i}@gmail.com", "group": "G3"} for i in range(6)]
ip_big = dict(ip_of, **{b["id"]: "103.57.130.4" for b in big})
mk = qa_agent.Masker()
cfg = {"Chế độ ngâm": "1 - Acc mới — chưa có gì", "Số luồng": 4, "Hạn mức phút/ngày (0 = tắt)": 42}
live = {"running": True, "slots": [{"slot": "Slot 1", "pid": P[0]["id"], "elapsed_s": 300, "silent_s": 12}],
        "waiting": {P[3]["id"]: "103.75.72.166"}}
ctx = qa_agent.build_context(db, P + big, ip_big, cfg, live, "vì sao warmup 17 lỗi?", logs_dir, mk, now=now)
check("KHÔNG còn email/IP nào trong dữ liệu gửi đi", mk.leaks(ctx) == [], str(mk.leaks(ctx))[:120])
check("tên profile còn nhận ra được + email thành mã", "MAIL194 - EMAIL_" in ctx and "Profile warmup 17" in ctx)
check("có cấu hình đang đặt", "Hạn mức phút/ngày (0 = tắt) = 42" in ctx)
check("có trạng thái đang chạy + ai đang chờ proxy", "Slot 1: Profile warmup 1 · đã chạy 5m00s · im lặng 12s" in ctx
      and "Đang chờ proxy rảnh: MAIL201 - EMAIL_" in ctx)
check("chu trình gần đây kèm lỗi thật", "đã bị đóng giữa chừng" in ctx and "Arg_NullReferenceException" in ctx
      and "12m11s (mục tiêu 12m00s)" in ctx)
check("hôm nay đã ngâm bao lâu", "hôm nay 12m11s" in ctx)
check("giai đoạn ngâm + cảnh báo quá hạn", "S0" in ctx and "D3/4" in ctx and "D10/4" in ctx and "QUÁ HẠN" in ctx)
check("hành động lỗi", "[HÀNH ĐỘNG LỖI" in ctx and "action_search_maps (GoogleMaps) | Timeout 50000ms" in ctx)
check("proxy: nhóm dùng chung + cờ quá 5 acc", "6 acc  (QUÁ 5 ACC)" in ctx and "3 acc — Profile warmup 17" in ctx)
check("được nhắc đích danh -> kèm log của đúng profile đó", "[LOG Profile warmup 17 — 70 dòng cuối]" in ctx
      and "Lỗi vào Maps: Timeout 50000ms — proxy PROXY_" in ctx)
check("email lọt trong log cũng bị che", "lộ.mail@gmail.com" not in ctx and "đăng nhập thử" in ctx)
check("chỉ lấy đuôi log", "dòng cũ 10\n" not in ctx and "dòng cũ 199" in ctx)
ctx2 = qa_agent.build_context(db, P, ip_of, cfg, {"running": False}, "proxy nào quá tải?", logs_dir, qa_agent.Masker(), now=now)
check("câu hỏi không cần log -> không gửi log", "[LOG " not in ctx2 and "không có lô nào đang chạy" in ctx2)
ctx3 = qa_agent.build_context(db, P, ip_of, cfg, None, "hôm nay cái nào lỗi, vì sao", logs_dir, qa_agent.Masker(), now=now)
check("hỏi 'vì sao' chung chung -> kèm log profile lỗi gần nhất", "[LOG Profile warmup 17" in ctx3)
ctx4 = qa_agent.build_context(db, P, {}, None, None, "x", logs_dir, qa_agent.Masker(), now=now)
check("không đọc được proxy -> nói rõ, không bịa", "chưa đọc được danh sách proxy" in ctx4)
check("dữ liệu có trần độ dài", len(ctx) < qa_agent.MAX_CONTEXT_CHARS + 100, f"{len(ctx)} ký tự")

print("\n== 4. answer_question")


class ChatBrain:
    last_error = ""

    def __init__(self, reply):
        self.reply, self.calls = reply, []

    def ask_chat(self, system, user, timeout=60):
        self.calls.append((system, user, timeout))
        return self.reply


TOK_E = mk.mask("mai.thu.nghiem194@gmail.com")   # mã phụ thuộc thứ tự xuất hiện trong dữ liệu -> hỏi masker
TOK_P = mk.mask("103.75.72.166")
b = ChatBrain(f"Profile warmup 17 lỗi vì trình duyệt bị đóng. MAIL194 - {TOK_E} dùng {TOK_P}.")
ans, raw, err = qa_agent.answer_question("vì sao  warmup 17 lỗi?\n", b, ctx, mk, [])
sys_p, user_p, tmo = b.calls[0]
check("gửi lời dặn hệ thống của trợ lý (chỉ đọc, giữ nguyên mã)", "CHỈ ĐỌC" in sys_p and "EMAIL_01" in sys_p and tmo == 60)
check("mã là mã (không phải email/IP thật)", TOK_E.startswith("EMAIL_") and TOK_P.startswith("PROXY_"), f"{TOK_E} {TOK_P}")
check("prompt gồm dữ liệu + câu hỏi đã gọn", user_p.startswith("DỮ LIỆU:") and user_p.endswith("CÂU HỎI: vì sao warmup 17 lỗi?"))
check("thứ gửi đi không có email/IP", mk.leaks(user_p) == [])
check("câu trả lời được ghép tên thật", "MAIL194 - mai.thu.nghiem194@gmail.com dùng 103.75.72.166." in ans and not err, ans)
check("bản lưu lịch sử vẫn còn mã", TOK_E in raw and "@" not in raw)
b2 = ChatBrain("ok")
qa_agent.answer_question("thế còn mail194 - mai.thu.nghiem194@gmail.com?", b2, ctx, mk, [("vì sao warmup 17 lỗi?", raw)])
check("câu hỏi nối tiếp: kèm hội thoại trước, email trong câu hỏi cũng bị che",
      "HỘI THOẠI TRƯỚC" in b2.calls[0][1] and b2.calls[0][1].endswith(f"CÂU HỎI: thế còn mail194 - {TOK_E}?"))
b3 = ChatBrain("")
b3.last_error = "Error code: 403 - INSUFFICIENT_BALANCE"
a3, r3, e3 = qa_agent.answer_question("x", b3, ctx, mk, [])
check("AI trả rỗng -> báo đúng lý do thật", a3 == "" and "INSUFFICIENT_BALANCE" in e3)


class Boom:
    def ask_chat(self, *a, **k):
        raise RuntimeError("Request timed out.")


check("AI ném lỗi -> không sập", qa_agent.answer_question("x", Boom(), ctx, mk, [])[2] == "Request timed out.")
check("câu hỏi trống -> không gọi AI", qa_agent.answer_question("   ", b, ctx, mk, [])[2] == "Câu hỏi trống." and len(b.calls) == 1)
b4 = ChatBrain("x")
a4, r4, e4 = qa_agent.answer_question("x", b4, "dữ liệu chưa che: a@b.com", qa_agent.Masker(), [])
check("hàng rào cuối: còn sót email thì HỦY, không gửi", b4.calls == [] and "đã hủy lượt hỏi" in e4)


class TextOnly:
    def __init__(self):
        self.got = None

    def ask_text(self, prompt):
        self.got = prompt
        return "tra loi"


t = TextOnly()
check("brain không có ask_chat (Gemini/local) -> ghép chung 1 prompt", qa_agent.ask_brain(t, "SYS", "USER") == "tra loi"
      and t.got == "SYS\n\nUSER")

print("\n== 5. GenericLLMBrain.ask_chat")
from src.agent.openai_brain import GenericLLMBrain  # noqa: E402


class FakeCompletions:
    def __init__(self, script):
        self.script, self.calls = list(script), []

    def create(self, **kw):
        self.calls.append(kw)
        r = self.script.pop(0)
        if isinstance(r, Exception):
            raise r
        msg = type("M", (), {"content": r})()
        return type("R", (), {"choices": [type("C", (), {"message": msg})()]})()


def fake_client(script):
    comp = FakeCompletions(script)
    return type("Cl", (), {"chat": type("Ch", (), {"completions": comp})()})(), comp


g = GenericLLMBrain(api_key="k1", model_name="m", base_url="http://x/v1")
cl, comp = fake_client(["  xin chào  "])
g.client = cl
g._clients = {0: cl}
out = g.ask_chat("SYS", "USER", timeout=33)
kw = comp.calls[0]
check("trả lời + dùng đúng lời dặn hệ thống được truyền vào", out == "xin chào" and kw["messages"][0] == {"role": "system", "content": "SYS"}
      and kw["messages"][1]["content"] == "USER" and kw["timeout"] == 33 and kw["model"] == "m")
check("ask_text vẫn giữ vai 'tạo từ khóa' (không đổi hành vi cũ)", "trợ lý tạo từ khóa" in open(
    os.path.join(SRC, "agent", "openai_brain.py"), encoding="utf-8").read().split("def ask_chat")[0])
cl2, comp2 = fake_client([RuntimeError("Error code: 403 INSUFFICIENT_BALANCE")])
g.client = cl2
g._clients = {0: cl2}
check("lỗi -> '' + ghi last_error, không ném", g.ask_chat("S", "U") == "" and "INSUFFICIENT_BALANCE" in g.last_error)
g2 = GenericLLMBrain(api_key="k1", api_keys=["k1", "k2"], model_name="m", base_url="http://x/v1")
ca, compa = fake_client([RuntimeError("429 quota exceeded")] * 3)
cb, compb = fake_client(["từ key khác"] * 3)
g2._next_key_index = lambda: 0
g2._clients = {0: ca, 1: cb}
check("nhiều key: hết quota thì thử key kế", g2.ask_chat("S", "U") == "từ key khác" and len(compa.calls) == 1 and len(compb.calls) == 1)

print("\n== 6. GPM không còn thấy profile -> có lời giải thích")
import src.browser.antidetect as AD  # noqa: E402


class Resp:
    status_code = 200

    def __init__(self, payload):
        self._p = payload

    def json(self):
        return self._p


def fake_get(url, **k):
    if "/profiles/start/" in url:
        return Resp({"success": False, "data": None, "message": "Arg_NullReferenceException"})
    if url.endswith("/profiles/GONE"):
        return Resp({"success": False, "data": None, "message": "insufficient_permission_profile"})
    return Resp({"success": True, "data": {"name": "Profile warmup 1", "browser": {"name": "chrome", "version": "155"}}})


real_get = AD.requests.get
AD.requests.get = fake_get
try:
    api = AD.AntidetectAPI("http://localhost:1")
    import contextlib
    import io
    with contextlib.redirect_stdout(io.StringIO()):
        ws1 = api.open_profile("GONE")
        e1 = api.last_error
        ws2 = api.open_profile("STILL-THERE")
        e2 = api.last_error
finally:
    AD.requests.get = real_get
check("profile GPM không còn thấy -> nói rõ + chỉ cách sửa", ws1 is None and "không còn thấy profile này" in e1
      and "Tải từ GPM" in e1 and "Arg_NullReferenceException" in e1, e1[:90])
check("profile vẫn còn mà lỗi lạ -> giữ nguyên mã lỗi của GPM", ws2 is None and e2 == "Arg_NullReferenceException", e2)

print("\n== 7. GUI thật")
import tkinter as tk  # noqa: E402
from tkinter import ttk  # noqa: E402
import src.ui_main as ui  # noqa: E402

root = tk.Tk()
app = ui.AutomationApp(root)
sys.stdout = sys.__stdout__
root.update()
app._rebuild_profile_rows([{"id": p["id"], "name": p["name"], "firefox": False, "selected": True, "group": p["group"]} for p in P])
root.update()


def find(w, cls):
    out_ = []
    for c in w.winfo_children():
        if isinstance(c, cls):
            out_.append(c)
        out_ += find(c, cls)
    return out_


check("nút 'Hỏi đáp AI' nằm trên thanh công cụ, cạnh 2 menu", str(app.btn_qa.cget("text")) == "Hỏi đáp AI"
      and app.btn_qa.master is app.mbtn_tools.master and app.btn_qa.winfo_ismapped())
app._set_utils_state("disabled")
check("KHÔNG bị khóa khi app đang chạy (2 menu kia thì khóa)", not app.btn_qa.instate(["disabled"])
      and app.mbtn_tools.instate(["disabled"]))
app._set_utils_state("normal")

asked = {}
gui_brain = ChatBrain("Hôm nay có 2 chu trình lỗi: Profile warmup 17 và MAIL194 - EMAIL_01 (proxy PROXY_01).")
real_pick, real_fetch, real_cands = ui._pick_live_brain, ui.fetch_proxy_map, ui._brain_candidates_from_env
ui._pick_live_brain = lambda cands, log=None: (asked.setdefault("cands", list(cands)) and None) or (gui_brain, "claude-sonnet", "")
ui.fetch_proxy_map = lambda bt, port="": (asked.__setitem__("fetch", asked.get("fetch", 0) + 1) or
                                           {P[2]["id"]: "103.75.72.166:8080:u:p", P[1]["id"]: "103.75.72.166:8080:u:p"}, "")
ui._brain_candidates_from_env = lambda: ["gemini"]
app.cbo_brain.set("claude-sonnet")
app.open_qa_agent()
root.update()
win = app._qa_dialog
check("cửa sổ mở, tiêu đề nói rõ chỉ đọc", win.winfo_exists() and "chỉ đọc" in str(win.title()))
check("ô nhập + nút Hỏi hiện thật (không bị khung hội thoại nuốt chỗ)", app._qa_entry.winfo_ismapped()
      and app._qa_btn_send.winfo_ismapped() and app._qa_btn_send.winfo_height() > 10 and app._qa_text.winfo_height() > 100,
      f"text {app._qa_text.winfo_height()}px, nút {app._qa_btn_send.winfo_height()}px")
texts = [str(l.cget("text")) for l in find(win, ttk.Label)]
check("có dòng nhắc: chỉ đọc + che email/IP + tốn lượt gọi", any("chỉ ĐỌC" in t and "che" in t and "lượt gọi AI" in t for t in texts))
btn_texts = [str(x.cget("text")) for x in find(win, ttk.Button)]
check("có 3 câu gợi ý + nút Xóa hội thoại", all(s in btn_texts for s in app.QA_SAMPLES) and "Xóa hội thoại" in btn_texts)
app.open_qa_agent()
root.update()
check("bấm lần 2 không mở cửa sổ thứ hai", app._qa_dialog is win and
      sum(1 for w in root.winfo_children() if isinstance(w, tk.Toplevel) and "Hỏi đáp" in str(w.title())) == 1)


def wait_done(limit=15.0):
    t_end = time.time() + limit
    while app._qa_busy and time.time() < t_end:
        root.update()
        time.sleep(0.03)
    root.update()


app._qa_var.set("Hôm nay profile nào lỗi?")
app._qa_send()
check("đang hỏi: nút bị khóa + ô nhập được dọn", app._qa_busy and app._qa_btn_send.instate(["disabled"]) and app._qa_var.get() == "")
app._qa_send("câu chen ngang")
wait_done()
body = app._qa_text.get("1.0", "end")
check("hiện câu hỏi + câu trả lời ĐÃ GHÉP tên thật", "Bạn: Hôm nay profile nào lỗi?" in body
      and "MAIL194 - mai.thu.nghiem194@gmail.com (proxy 103.75.72.166)" in body, body.strip()[-120:])
check("đang bận thì không nhận câu chen ngang", "câu chen ngang" not in body and len(gui_brain.calls) == 1)
check("thứ gửi cho AI không có email/IP", app._qa_masker.leaks(gui_brain.calls[0][1]) == [])
check("AI đang chọn ở ô AI Brain được thử trước, rồi tới các AI khác", asked.get("cands") == ["claude-sonnet", "gemini"])
check("xong: nút bật lại + dòng trạng thái nêu AI đã dùng", not app._qa_btn_send.instate(["disabled"])
      and "claude-sonnet" in str(app._qa_status.cget("text")) and "đã che email/IP" in str(app._qa_status.cget("text")))
app._qa_send(app.QA_SAMPLES[2])
wait_done()
check("câu thứ 2: dùng lại AI + proxy đã đọc, kèm hội thoại trước", len(gui_brain.calls) == 2 and asked.get("fetch") == 1
      and "HỘI THOẠI TRƯỚC" in gui_brain.calls[1][1])
gui_brain.reply = ""
gui_brain.last_error = "Error code: 403 - INSUFFICIENT_BALANCE"
app._qa_send("thêm câu nữa")
wait_done()
body = app._qa_text.get("1.0", "end")
check("AI hết số dư -> báo bằng tiếng người, app không treo", "HẾT SỐ DƯ" in body and not app._qa_busy and app._qa_brain is None)
theme0 = app.theme_name
app._toggle_theme()
root.update()
check("đổi nền khi cửa sổ đang mở: không lỗi, màu chữ theo nền mới", app.theme_name != theme0
      and str(app._qa_text.tag_cget("you", "foreground")) == app.C_ACCENT and str(app._qa_text.cget("bg")) == app.C_FIELD)
app._toggle_theme()
for x in find(win, ttk.Button):
    if str(x.cget("text")) == "Xóa hội thoại":
        x.invoke()
root.update()
check("Xóa hội thoại: sạch khung + quên lịch sử", app._qa_text.get("1.0", "end").strip() == "" and app._qa_history == [])
ui._brain_candidates_from_env = lambda: []
app.cbo_brain.set("none")
app._qa_brain = None
app._qa_send("không có AI thì sao")
wait_done()
check("không có AI nào -> chỉ chỗ thêm key, không gọi mạng", "Quản lý API key" in app._qa_text.get("1.0", "end"))
win.destroy()
root.update()
app._toggle_theme()
app._toggle_theme()
check("đóng cửa sổ rồi đổi nền: không lỗi", True)
ui._pick_live_brain, ui.fetch_proxy_map, ui._brain_candidates_from_env = real_pick, real_fetch, real_cands
src_u = open(os.path.join(SRC, "ui_main.py"), encoding="utf-8").read()
qa_src = src_u[src_u.index("    def open_qa_agent"):src_u.index("    def _set_utils_state")]
check("luồng nền không chạm Tk (không .after/.config trong _qa_work)", ".after(" not in qa_src[qa_src.index("def _qa_work"):qa_src.index("def _qa_send")]
      and ".config(" not in qa_src[qa_src.index("def _qa_work"):qa_src.index("def _qa_send")])
check("chỉ đọc: phần hỏi đáp không ghi DB / không lưu cấu hình / không chạm nút chạy",
      all(x not in qa_src for x in ("log_cycle", "log_activity", "save_config", "start_automation", "set_profile_", "STOP_EVENT")))
qa_mod = open(os.path.join(SRC, "qa_agent.py"), encoding="utf-8").read()
check("qa_agent chỉ SELECT, mở DB chế độ chỉ-đọc", "mode=ro" in qa_mod and not any(
    w in qa_mod.upper() for w in ("INSERT ", "UPDATE ", "DELETE ", "DROP ", "ALTER ")))
root.destroy()

print("\n== 8. Đóng cửa sổ -> tiến trình thoát hẳn, kể cả khi có luồng kẹt")
import threading  # noqa: E402


class Clk:
    def __init__(self):
        self.t = 0.0

    def now(self):
        return self.t

    def sleep(self, s):
        self.t += s
        time.sleep(0.01)


def run_shutdown(make_threads, slot_api):
    ui.STOP_EVENT.clear()
    ui.SLOT_API.clear()
    ui.SLOT_THREAD_ALIVE.clear()
    for k, v in slot_api.items():
        ui.SLOT_API[k] = v
        ui.SLOT_THREAD_ALIVE[k] = True
    ths = make_threads()
    for t in ths:
        t.start()
    clk, codes = Clk(), []
    ui.shutdown_after_close(grace_s=20, close_wait_s=10, exit_fn=codes.append, sleep=clk.sleep, now=clk.now)
    return clk.t, codes


t_idle, c_idle = run_shutdown(lambda: [], {})
check("rảnh: thoát NGAY, mã 0", t_idle == 0 and c_idle == [0], f"{t_idle}s")
done = threading.Event()


def polite():
    while not ui.STOP_EVENT.is_set():
        time.sleep(0.005)
    done.set()


t_ok, c_ok = run_shutdown(lambda: [threading.Thread(target=polite)], {})
check("luồng biết dừng: được báo DỪNG, tự xong rồi mới thoát", done.is_set() and c_ok == [0] and t_ok < 20, f"{t_ok}s")
closed = []
wake = threading.Event()


class FakeApi:
    def close_profile(self, pid):
        closed.append(pid)
        wake.set()    # đóng trình duyệt làm lệnh treo ném lỗi -> luồng tỉnh (trường hợp bình thường)


t_hang, c_hang = run_shutdown(lambda: [threading.Thread(target=lambda: wake.wait(30))],
                              {"Slot 1": (FakeApi(), "c980a065-xxxx")})
check("luồng kẹt: chờ đủ 20s rồi đóng profile của slot còn sống, rồi thoát", closed == ["c980a065-xxxx"]
      and c_hang == [0] and 20 <= t_hang < 30, f"{t_hang}s")
stuck = threading.Event()
t_dead, c_dead = run_shutdown(lambda: [threading.Thread(target=lambda: stuck.wait(8))],
                              {"Slot 1": (type("A", (), {"close_profile": lambda s, p: None})(), "p")})
check("kẹt cả sau khi đóng profile (đúng ca 19/11): vẫn THOÁT, không treo ngầm", c_dead == [0] and t_dead >= 30, f"{t_dead}s")
stuck.set()
ui.STOP_EVENT.clear()
ui.SLOT_API.clear()
ui.SLOT_THREAD_ALIVE.clear()
src_main = src_u[src_u.index('if __name__ == "__main__":'):].replace("\r\n", "\n")
check("app gọi bước dọn sau khi cửa sổ đóng", "root.mainloop()\n    shutdown_after_close()" in src_main)

print(f"\nPASS: {PASS}   FAIL: {FAIL}")
print("SMOKE v1.9.1: ALL PASS" if FAIL == 0 else "SMOKE v1.9.1: CO LOI")
os._exit(0 if FAIL == 0 else 1)
