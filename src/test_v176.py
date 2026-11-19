# -*- coding: utf-8 -*-
"""Smoke test v1.7.6 — CỔNG TỰ ĐẶT CHO MỌI KEY (key + Endpoint + Model -> AI Brain).

Bối cảnh: user thêm key của gateway https://kiraai.vn/api/v1 (tương thích OpenAI, 112
model) và gõ "deepseek-v4.1-flash" vào ô Tên key -> bị từ chối "Tên key không hợp lệ"
(dấu '.'), và kể cả lưu được thì app cũng không có brain nào dùng key đó.

v1.7.6:
  - tên key: mọi ký tự lạ -> '_'  (deepseek-v4.1-flash -> DEEPSEEK_V4_1_FLASH)
  - dialog thêm ô Model (<TEN>_MODEL); gõ tên model vào ô Tên + có Endpoint -> tự hiểu là model
  - mọi key có Endpoint + Model -> brain 'custom:<TEN>' (combobox + chuỗi dự phòng Sinh chủ đề)

Chạy: python src\\test_v175.py  (.env + DB ở thư mục tạm; hash .env THẬT đối chiếu cuối)
Phần 5 gọi THẬT kiraai.vn bằng key GIẢ -> chỉ kiểm tra đường đi tới server (mong lỗi 401).
"""
import hashlib
import io
import os
import sys
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

TMP = tempfile.mkdtemp(prefix="gpm_v176_")
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


def sha(path):
    try:
        with open(path, "rb") as f:
            return hashlib.sha256(f.read()).hexdigest()[:12]
    except Exception:
        return "(none)"


def read_env():
    if not os.path.exists(TEST_ENV):
        return ""
    with io.open(TEST_ENV, "r", encoding="utf-8-sig", newline="") as f:
        return f.read()


REAL_ENV = os.path.join(ROOT, ".env")
H0 = sha(REAL_ENV)

import tkinter as tk  # noqa: E402
from tkinter import ttk  # noqa: E402
import src.ui_main as ui  # noqa: E402
from src import api_vault  # noqa: E402
from src.agent.brain_manager import BrainManager  # noqa: E402

print("\n== 1. sanitize_key_name")
for raw, exp in [("deepseek-v4.1-flash", "DEEPSEEK_V4_1_FLASH"), ("my new-key", "MY_NEW_KEY"),
                 ("GEMINI_API_KEY", "GEMINI_API_KEY"), ("4o.mini", "KEY_4O_MINI"),
                 ("  a..b  ", "A_B"), ("", "")]:
    got = api_vault.sanitize_key_name(raw)
    check(f"{raw!r} -> {exp!r}", got == exp, got)
check("tên đã chuẩn hoá qua được _KEY_RE",
      api_vault._KEY_RE.match("DEEPSEEK_V4_1_FLASH=") is not None)

print("\n== 2. custom_providers / companion")
with io.open(TEST_ENV, "w", encoding="utf-8", newline="") as f:
    f.write("GEMINI_API_KEY=g\nGEMINI_API_KEY_ENDPOINT=https://g/v1\n"
            "CLAUDE_LAU=c\nCLAUDE_LAU_ENDPOINT=https://c/v1\n"
            "KIRA=k1\nKIRA_ENDPOINT=https://kiraai.vn/api/v1\nKIRA_MODEL=deepseek-v4.1-flash\n"
            "NOMODEL=x\nNOMODEL_ENDPOINT=https://n/v1\n"
            "PLAIN=p\nGEMINI_MODEL=gemini-3-flash-preview\n")
cp = api_vault.custom_providers()
names = [k for k, _e, _m in cp]
check("KIRA là cổng tự đặt", ("KIRA", "https://kiraai.vn/api/v1", "deepseek-v4.1-flash") in cp, str(cp))
check("NOMODEL vẫn liệt kê (model rỗng)", "NOMODEL" in names)
check("GEMINI/CLAUDE_LAU KHÔNG bị coi là custom", "GEMINI_API_KEY" not in names and "CLAUDE_LAU" not in names)
check("PLAIN (không endpoint) không vào", "PLAIN" not in names)
check("KIRA_MODEL không thành provider riêng", "KIRA_MODEL" not in names)
env = dict(api_vault.list_keys())
check("KIRA_MODEL là biến đi kèm", api_vault.is_companion_key("KIRA_MODEL", env))
check("GEMINI_MODEL KHÔNG bị ẩn (không có key GEMINI)", not api_vault.is_companion_key("GEMINI_MODEL", env))
check("ui._custom_brain_types chỉ lấy key có model", ui._custom_brain_types() == ["custom:KIRA"],
      str(ui._custom_brain_types()))
check("chuỗi dự phòng: custom đứng ĐẦU", ui._brain_candidates_from_env()[:1] == ["custom:KIRA"],
      str(ui._brain_candidates_from_env()))
check("auto-pick 'none' -> custom:KIRA", ui._detect_brain_type_from_env() == "custom:KIRA")

print("\n== 3. BrainManager custom:")
api_vault.sync_env_into_process()
b = BrainManager.get_brain("custom:KIRA")
check("dựng GenericLLMBrain", type(b).__name__ == "GenericLLMBrain", type(b).__name__)
check("model đúng", getattr(b, "model_name", "") == "deepseek-v4.1-flash", getattr(b, "model_name", ""))
check("base_url đúng", getattr(b, "base_url", "") == "https://kiraai.vn/api/v1", getattr(b, "base_url", ""))
for bt, frag in (("custom:NOMODEL", "Model"), ("custom:PLAIN", "endpoint"), ("custom:NOPE", "Thiếu key")):
    try:
        BrainManager.get_brain(bt)
        check(f"{bt} báo lỗi", False, "không raise")
    except ValueError as e:
        check(f"{bt} báo lỗi chỉ cách sửa", frag in str(e), str(e)[:90])

print("\n== 4. GUI: dialog thêm key + combobox")
root = tk.Tk()
root.withdraw()
app = ui.AutomationApp(root)
sys.stdout = sys.__stdout__
root.update()
check("combobox AI Brain có custom:KIRA", "custom:KIRA" in list(app.cbo_brain.cget("values")))
app.var_brain_type.set("custom:KIRA")
app._on_brain_type_changed()
check("hint hiện cổng + model", "kiraai.vn" in app.lbl_brain_hint.cget("text")
      and "deepseek" in app.lbl_brain_hint.cget("text"), app.lbl_brain_hint.cget("text"))


def find_all(w, kind, out=None):
    out = [] if out is None else out
    for c in w.winfo_children():
        if isinstance(c, kind):
            out.append(c)
        find_all(c, kind, out)
    return out


def top(title):
    for w in root.winfo_children():
        if isinstance(w, tk.Toplevel) and title.lower() in str(w.title()).lower():
            return w
    return None


def setv(en, v):
    en.delete(0, "end")
    en.insert(0, v)


def press(w, text):
    for b in find_all(w, ttk.Button) + find_all(w, tk.Button):
        if str(b.cget("text")) == text:
            b.invoke()
            return True
    return False


app._api_dialog = None
# Đúng thao tác của user trong ảnh: tên = tên model, ô Model bỏ trống
app._api_key_edit_dialog("", "", lambda: None, parent=root)
root.update()
ed = top("Thêm API key")
ents = find_all(ed, ttk.Entry)
check("dialog có 4 Entry", len(ents) == 4, str(len(ents)))
setv(ents[0], "deepseek-v4.1-flash")
setv(ents[1], "fake_key_123")
setv(ents[2], "https://kiraai.vn/api/v1")
press(ed, "Lưu")
root.update()
raw = read_env()
check("tên có dấu '.' được chấp nhận -> DEEPSEEK_V4_1_FLASH", "DEEPSEEK_V4_1_FLASH=fake_key_123" in raw)
check("ghi endpoint", "DEEPSEEK_V4_1_FLASH_ENDPOINT=https://kiraai.vn/api/v1" in raw)
check("tự hiểu tên gốc là model", "DEEPSEEK_V4_1_FLASH_MODEL=deepseek-v4.1-flash" in raw)
check("dialog đóng sau Lưu", top("Thêm API key") is None)
check("combobox cập nhật ngay", "custom:DEEPSEEK_V4_1_FLASH" in list(app.cbo_brain.cget("values")))

# Ô Model điền tay thắng suy luận; không endpoint thì KHÔNG đoán model
app._api_key_edit_dialog("", "", lambda: None, parent=root)
root.update()
ents = find_all(top("Thêm API key"), ttk.Entry)
setv(ents[0], "MY_GW")
setv(ents[1], "v")
setv(ents[2], "https://gw/v1")
setv(ents[3], "glm-5.3-flash")
press(top("Thêm API key"), "Lưu")
root.update()
check("model điền tay lưu đúng", "MY_GW_MODEL=glm-5.3-flash" in read_env())
app._api_key_edit_dialog("", "", lambda: None, parent=root)
root.update()
ents = find_all(top("Thêm API key"), ttk.Entry)
setv(ents[0], "some-key.x")
setv(ents[1], "v")
press(top("Thêm API key"), "Lưu")
root.update()
check("không endpoint -> không tạo _MODEL", "SOME_KEY_X_MODEL" not in read_env() and "SOME_KEY_X=v" in read_env())

# Sửa key: ô Model nạp sẵn; xoá trống -> gỡ _MODEL
app._api_key_edit_dialog("MY_GW", "", lambda: None, parent=root)
root.update()
ents = find_all(top("Sửa MY_GW"), ttk.Entry)
check("sửa: ô Model nạp sẵn", ents[3].get() == "glm-5.3-flash", ents[3].get())
setv(ents[3], "")
press(top("Sửa MY_GW"), "Lưu")
root.update()
check("sửa: model trống -> gỡ MY_GW_MODEL", "MY_GW_MODEL" not in read_env())

# Danh sách key: hàng _MODEL bị ẩn, có nhãn Model
ui.messagebox.showerror = lambda *a, **k: None
app._open_api_key_dialog()
root.update()
dlg = top("API KEY")
txt = [str(l.cget("text")) for l in find_all(dlg, tk.Label)] if dlg else []
check("danh sách mở", dlg is not None)
check("không có hàng riêng KIRA_MODEL", "KIRA_MODEL" not in txt)
check("có nhãn 'Model: deepseek-v4.1-flash'", any("Model: deepseek-v4.1-flash" in t for t in txt))

print("\n== 5. Gọi THẬT kiraai.vn bằng key GIẢ (kiểm tra đường đi)")
try:
    api_vault.sync_env_into_process()
    b = BrainManager.get_brain("custom:DEEPSEEK_V4_1_FLASH")
    r = b.ask_text("Reply OK")
    err = getattr(b, "last_error", "") or ""
    check("key giả -> không có trả lời", not r, repr(r)[:60])
    check("lỗi tới từ server (401/auth)", ui._explain_brain_error(err) == "KEY SAI hoặc đã bị thu hồi"
          or "401" in err, err[:120])
except Exception as e:
    check("gọi thật không ném lỗi", False, str(e)[:120])

root.destroy()
print("\n== 6. .env THẬT không đổi")
check("hash .env thật trước == sau", sha(REAL_ENV) == H0, H0)

print(f"\nPASS: {PASS}   FAIL: {FAIL}")
print("SMOKE v1.7.6: ALL PASS" if FAIL == 0 else "SMOKE v1.7.6: CO LOI")
sys.exit(0 if FAIL == 0 else 1)
