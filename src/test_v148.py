"""SMOKE v1.4.8 — Tiện ích QUẢN LÝ API KEY (src/api_vault.py + dialog trong ui_main.py).

Cô lập tuyệt đối:
- .env test   -> GPM_BOT_ENV_FILE = temp\\.env   (api_vault/paths đọc override này)
- config test -> GPM_BOT_DATA_DIR = temp\\data   (app_config CONFIG_PATH resolve lúc import)
File .env THẬT ở repo-root được hash trước/sau — phải y hệt từng byte.

Chạy:  python src/test_v148.py
"""
import hashlib
import io
import os
import shutil
import sys
import tempfile
import tkinter as tk
from tkinter import messagebox, ttk

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
for p in (REPO, HERE):
    if p not in sys.path:
        sys.path.insert(0, p)

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

TMP = tempfile.mkdtemp(prefix="gpm_v148_")
ENV_FILE = os.path.join(TMP, ".env")
DATA_DIR = os.path.join(TMP, "data")
os.makedirs(DATA_DIR, exist_ok=True)

REAL_ENV = os.path.join(REPO, ".env")
real_env_hash_before = ""
if os.path.exists(REAL_ENV):
    real_env_hash_before = hashlib.sha256(open(REAL_ENV, "rb").read()).hexdigest()

# --- cô lập TRƯỚC khi import module (app_config đọc env lúc import) ---
os.environ["GPM_BOT_ENV_FILE"] = ENV_FILE
os.environ["GPM_BOT_DATA_DIR"] = DATA_DIR

PASS, FAIL = [], []


def check(name, cond, extra=""):
    (PASS if cond else FAIL).append(name)
    print(("  [PASS] " if cond else "  [FAIL] ") + name + (f"  ({extra})" if extra else ""))


def hr(t):
    print("\n" + "=" * 68)
    print(t)
    print("=" * 68)


def seed_env(text):
    with io.open(ENV_FILE, "w", encoding="utf-8", newline="") as f:
        f.write(text)


def read_env_raw():
    if not os.path.exists(ENV_FILE):
        return ""
    with io.open(ENV_FILE, "r", encoding="utf-8", newline="") as f:
        return f.read()


def find_all(widget, kind, out=None):
    out = out if out is not None else []
    for c in widget.winfo_children():
        if isinstance(c, kind):
            out.append(c)
        find_all(c, kind, out)
    return out


root = None


def find_toplevel(title_frag):
    for w in root.winfo_children():
        if isinstance(w, tk.Toplevel) and title_frag.lower() in (w.title() or "").lower():
            return w
    return None


def set_entry(en, text):
    """Điền Entry. LƯU Ý: cget("textvariable") trả TÊN biến (str) chứ không phải
    StringVar -> gọi var.set() sẽ AttributeError. delete/insert trên Entry có
    textvariable vẫn cập nhật StringVar (đã dò thật), nên dùng cách này cho cả 2."""
    try:
        en.delete(0, "end")
        en.insert(0, text)
    except Exception:
        pass
    try:
        en.invoke()
    except Exception:
        pass
    root.update()


def click_btn(parent, text):
    for b in find_all(parent, tk.Button):
        if (b.cget("text") or "").strip() == text:
            b.invoke()
            return True
    for b in find_all(parent, ttk.Button):
        try:
            if (b.cget("text") or "").strip() == text:
                b.invoke()
                return True
        except Exception:
            pass
    return False


hr("0. src.paths.env_path() — override GPM_BOT_ENV_FILE")
from src import paths  # noqa: E402

check("env_path() trỏ file temp", os.path.abspath(paths.env_path()) == os.path.abspath(ENV_FILE), paths.env_path())
os.environ.pop("GPM_BOT_ENV_FILE")
check("env_path() không override -> repo-root/.env",
      os.path.abspath(paths.env_path()) == os.path.abspath(REAL_ENV), paths.env_path())
os.environ["GPM_BOT_ENV_FILE"] = ENV_FILE

hr("1. api_vault I/O .env (giữ comment/CRLF/line lạ)")
from src import api_vault  # noqa: E402
from src import app_config  # noqa: E402

SEED = (
    "# comment đầu file\r\n"
    "\r\n"
    "GEMINI_API_KEY=seedgemini\r\n"
    "OPENAI_API_KEY=\"seedopenai\"\n"
    "EMPTY_KEY=\r\n"
    "export OLD_STYLE=abc123\r\n"
    "QUAN_TRONG=tri tri unicode\r\n"
    "line khong phai kv\r\n"
    "MY_CUSTOM_KEY=customvalue999"
)
seed_env(SEED)

pairs = api_vault.list_keys()
names = [k for k, _v in pairs]
check("list_keys đọc đủ 6 key (bỏ comment/rỗng/line rác)",
      names == ["GEMINI_API_KEY", "OPENAI_API_KEY", "EMPTY_KEY", "OLD_STYLE", "QUAN_TRONG", "MY_CUSTOM_KEY"], str(names))
d = dict(pairs)
check("strip dấu ngoặc kép value", d.get("OPENAI_API_KEY") == "seedopenai", repr(d.get("OPENAI_API_KEY")))
check("parse `export KEY=`", d.get("OLD_STYLE") == "abc123", repr(d.get("OLD_STYLE")))
check("get_key đọc từ file", api_vault.get_key("GEMINI_API_KEY") == "seedgemini")
os.environ["GEMINI_API_KEY"] = "fromenviron"
check("get_key ƯU TIÊN file hơn os.environ", api_vault.get_key("GEMINI_API_KEY") == "seedgemini")
del os.environ["GEMINI_API_KEY"]
os.environ["ONLY_ENV_KEY"] = "envonly123"
check("get_key fallback os.environ", api_vault.get_key("ONLY_ENV_KEY") == "envonly123")
del os.environ["ONLY_ENV_KEY"]

check("set_key replace trả True", api_vault.set_key("GEMINI_API_KEY", "newgem") is True)
raw = read_env_raw()
check("set_key thay đúng dòng, giữ CRLF dòng đó", "GEMINI_API_KEY=newgem\r\n" in raw)
check("set_key giữ comment + line rác + LF dòng khác",
      "# comment đầu file\r\n" in raw and "line khong phai kv\r\n" in raw
      and "OPENAI_API_KEY=\"seedopenai\"\n" in raw)
check("set_key đồng bộ os.environ ngay", os.environ.get("GEMINI_API_KEY") == "newgem")

check("set_key key mới trả True", api_vault.set_key("BRAND_NEW", "bn1") is True)
raw = read_env_raw()
check("key mới append CRLF theo lệ file + bù newline dòng cuối cụt",
      raw.endswith("MY_CUSTOM_KEY=customvalue999\r\nBRAND_NEW=bn1\r\n"), repr(raw[-70:]))

check("set_key tên rác bị từ chối", api_vault.set_key("bad key!", "x") is False)
check("set_key tên bắt đầu bằng số bị từ chối", api_vault.set_key("1ABC", "x") is False)
check("os.environ không nhiễm key tên rác", "bad key!" not in os.environ)

seed_env("A=1\nDUP=2\nB=3\nDUP=4\n")
check("delete_key xóa MỌI dòng trùng", api_vault.delete_key("DUP") is True and read_env_raw() == "A=1\nB=3\n", repr(read_env_raw()))
check("delete_key pop os.environ", "DUP" not in os.environ)
check("delete_key key không tồn tại vẫn True", api_vault.delete_key("KHONGCO") is True)
os.remove(ENV_FILE)
check("delete_key khi file mất vẫn True", api_vault.delete_key("A") is True)
check("get_key khi file mất -> ''", api_vault.get_key("A") == "")

seed_env(SEED)
n = api_vault.sync_env_into_process()
check("sync_env_into_process đếm key non-empty = 5", n == 5, str(n))
check("sync nạp value vào os.environ", os.environ.get("MY_CUSTOM_KEY") == "customvalue999")

hr("2. mask()")
check("mask('') = ''", api_vault.mask("") == "")
check("mask None = ''", api_vault.mask(None) == "")
check("mask key ngắn che hết", api_vault.mask("12345678") == "•" * 8, api_vault.mask("12345678"))
check("mask key dài 4 đầu + 6 dots + 4 cuối", api_vault.mask("ABCDEFGHIJKLMNOP") == "ABCD…••••••…MNOP", api_vault.mask("ABCDEFGHIJKLMNOP"))

hr("3. Cổng mật khẩu PBKDF2 (config temp)")
cfg0 = app_config.load_config()
check("config temp chưa có gate", cfg0["api_gate_salt"] == "" and cfg0["api_gate_hash"] == "")
check("has_custom_password False ban đầu", api_vault.has_custom_password() is False)
check("check_password('') False", api_vault.check_password("") is False)
check("check_password(None) False", api_vault.check_password(None) is False)
check("check_password sai False", api_vault.check_password("saimatkhau") is False)
check("lần đầu ĐĂNG KÝ qua default = True", api_vault.check_password(api_vault.DEFAULT_PASSWORD) is True)
check("sau lần đầu has_custom_password True", api_vault.has_custom_password() is True)
cfg1 = app_config.load_config()
check("salt+hash hex được persist",
      len(cfg1["api_gate_salt"]) == 32 and len(cfg1["api_gate_hash"]) == 64,
      f"salt={len(cfg1['api_gate_salt'])} hash={len(cfg1['api_gate_hash'])}")
check("default vẫn đúng sau kích hoạt", api_vault.check_password(api_vault.DEFAULT_PASSWORD) is True)
check("sai vẫn bị từ chối", api_vault.check_password("saimatkhau") is False)
check("set_password(<4 ký tự) False", api_vault.set_password("abc") is False)
check("set_password('MatKhauMoi!4') True", api_vault.set_password("MatKhauMoi!4") is True)
check("mật khẩu mới đúng", api_vault.check_password("MatKhauMoi!4") is True)
check("default cũ BỊ VÔ HIỆU hóa sau đổi", api_vault.check_password(api_vault.DEFAULT_PASSWORD) is False)
cfg2 = app_config.load_config()
check("salt đổi khi set_password lại", cfg2["api_gate_salt"] != cfg1["api_gate_salt"])

hr("4. GUI — dialog mật khẩu / quản lý key / eye per-row")
import ui_main as ui  # noqa: E402

seed_env("GEMINI_API_KEY=geminikey123456\r\nMY_CUSTOM_KEY=customvalue999\r\n")
app = ui.AutomationApp(root := tk.Tk())
root.update()
check("AutomationApp khởi tạo OK (có btn_api_keys)", hasattr(app, "btn_api_keys"))
check("sync lúc mở app nạp .env vào os.environ", os.environ.get("MY_CUSTOM_KEY") == "customvalue999")
check("btn_api_keys enabled khi nghỉ", app.btn_api_keys.instate(["!disabled"]))
check("DEFAULT_PASSWORD = gpm123", api_vault.DEFAULT_PASSWORD == "gpm123")

# 4a. Sai mật khẩu -> không mở dialog
app._ask_api_password(app._open_api_key_dialog)
root.update()
pw = find_toplevel("Mật khẩu tiện ích API")
check("dialog mật khẩu mở", pw is not None)
pw_entries = [e for e in find_all(pw, tk.Entry) if e.cget("show") == "•"]
check("dialog mật khẩu có 1 Entry password", len(pw_entries) == 1, str(len(pw_entries)))
set_entry(pw_entries[0], "SAI")
check("nút Xác nhận tồn tại", click_btn(pw, "Xác nhận"))
root.update()
check("sai mật khẩu -> KHÔNG mở dialog key", find_toplevel("Quản lý API KEY") is None)
check("sai mật khẩu -> hiện nhãn lỗi", "Sai mật khẩu" in " ".join(str(l.cget("text")) for l in find_all(pw, tk.Label)))
click_btn(pw, "Hủy")
root.update()
check("Hủy đóng dialog mật khẩu", find_toplevel("Mật khẩu tiện ích API") is None)

# 4b. Đúng mật khẩu -> mở dialog chính
app._ask_api_password(app._open_api_key_dialog)
root.update()
pw = find_toplevel("Mật khẩu tiện ích API")
set_entry([e for e in find_all(pw, tk.Entry) if e.cget("show") == "•"][0], "MatKhauMoi!4")
click_btn(pw, "Xác nhận")
root.update()
dlg = find_toplevel("Quản lý API KEY")
check("đúng mật khẩu -> mở dialog Quản lý API KEY", dlg is not None)

# 4c. Đủ hàng KNOWN + custom, giá trị mask
def row_labels(win):
    return [l for l in find_all(win, tk.Label) if str(l.cget("width")) == "26"]


labels = row_labels(dlg)
check("dialog có >=4 hàng key (KNOWN 4 + custom)", len(labels) >= 4, str(len(labels)))
texts = [str(l.cget("text")) for l in labels]
check("giá trị hiển thị dạng mask", any("•" in t for t in texts), str(texts))
check("key trống hiện (trống)", any("(trống)" in t for t in texts), str(texts))

# 4d. EYE per-row — chốt bug late-binding (chọn 2 hàng CÓ giá trị thật: GEMINI + MY_CUSTOM_KEY)
def _row_widgets(win, keyname):
    lab = next((l for l in find_all(win, tk.Label) if (l.cget("text") or "") == keyname), None)
    if lab is None:
        return None, None
    node = lab.master  # lbl_fr -> frame hàng
    while node is not None and node is not win:
        eyes = [b for b in find_all(node, tk.Button)
                if (b.cget("text") or "") in ("Hiện", "Ẩn") and str(b.cget("width")) == "5"]
        if eyes:
            return eyes[0], next((l for l in find_all(node, tk.Label)
                                  if str(l.cget("width")) == "26"), None)
        node = node.master
    return None, None


b1, l1 = _row_widgets(dlg, "GEMINI_API_KEY")
b2, l2 = _row_widgets(dlg, "MY_CUSTOM_KEY")
check("tìm được cặp eye/label hàng GEMINI", b1 is not None and l1 is not None)
check("tìm được cặp eye/label hàng MY_CUSTOM_KEY", b2 is not None and l2 is not None)
t1_before = str(l1.cget("text"))
check("hàng GEMINI đang mask", "•" in t1_before, t1_before)
b2.invoke()
root.update()
check("bấm eye hàng MY_CUSTOM -> hiện value THẬT",
      str(l2.cget("text")) == "customvalue999", str(l2.cget("text")))
check("bấm eye hàng 2 -> hàng 1 KHÔNG đổi (chống late-binding)", str(l1.cget("text")) == t1_before)
check("bấm eye hàng 2 -> nhãn nút 2 thành Ẩn", (b2.cget("text") or "") == "Ẩn")
check("nhãn nút 1 vẫn Hiện", (b1.cget("text") or "") == "Hiện")
b2.invoke()
root.update()
check("bấm lần 2 -> hàng 2 về mask", "•" in str(l2.cget("text")), str(l2.cget("text")))
check("bấm lần 2 -> nút về Hiện", (b2.cget("text") or "") == "Hiện")

# 4e. Sửa key QUA NÚT "Sửa" THẬT của dòng GEMINI (on_saved = _refresh -> dialog render lại)
_real_aysno_e = ui.messagebox.askyesno
ui.messagebox.askyesno = lambda *a, **k: True   # không có confirm ở flow này nhưng phòng hờ
sbtn = None
for lab in find_all(dlg, tk.Label):
    if (lab.cget("text") or "") == "GEMINI_API_KEY":
        node = lab.master  # lbl_fr -> đi lên tới frame hàng có nút Sửa
        while node is not None and node is not dlg:
            cand = [b for b in find_all(node, tk.Button) if (b.cget("text") or "") == "Sửa"]
            if cand:
                sbtn = cand[0]
                break
            node = node.master
        break
check("hàng GEMINI có nút Sửa (đúng dòng)", sbtn is not None)
sbtn.invoke()
root.update()
ed = find_toplevel("Sửa GEMINI_API_KEY")
check("dialog sửa key mở đúng tiêu đề", ed is not None)
ents = find_all(ed, ttk.Entry)
check("dialog sửa có 2 Entry (tên + value)", len(ents) == 2, str(len(ents)))
check("Entry tên prefill", ents[0].get() == "GEMINI_API_KEY", ents[0].get())
check("Entry value prefill giá trị thật", ents[1].get() == "geminikey123456", ents[1].get())
set_entry(ents[1], "geminiUPDATED777")
check("nút Lưu tồn tại", click_btn(ed, "Lưu"))
root.update()
check("value mới vào .env", "GEMINI_API_KEY=geminiUPDATED777" in read_env_raw())
check("value mới vào os.environ", os.environ.get("GEMINI_API_KEY") == "geminiUPDATED777")
check("dialog sửa đóng sau lưu", find_toplevel("Sửa GEMINI_API_KEY") is None)
labels = row_labels(dlg)
texts = [str(l.cget("text")) for l in labels]
check("dòng GEMINI trong dialog mask value mới (dialog đã tự render lại)",
      api_vault.mask("geminiUPDATED777") in texts, str(texts))
ui.messagebox.askyesno = _real_aysno_e

# 4f. Thêm key mới qua nút "+ Thêm key" THẬT: tên rác "my new-key" -> MY_NEW_KEY
check("nút + Thêm key tồn tại", click_btn(dlg, "+ Thêm key"))
root.update()
ed = find_toplevel("Thêm API key")
check("dialog thêm key mở", ed is not None)
ents = find_all(ed, ttk.Entry)
set_entry(ents[0], "my new-key")
set_entry(ents[1], "nv42")
click_btn(ed, "Lưu")
root.update()
check("normalize tên key (space -> _, upper)", "MY_NEW_KEY=nv42" in read_env_raw(), repr(read_env_raw()[-80:]))
texts = [str(l.cget("text")) for l in row_labels(dlg)]
check("MY_NEW_KEY xuất hiện trong danh sách dialog (refresh)",
      any("MY_NEW_KEY" in (str(x.cget("text"))) for x in find_all(dlg, tk.Label)))

# 4f2. Thêm TRÙNG key đã có -> askyesno "Ghi đè" False phải CHẶN ghi
_real_aysno_f2 = ui.messagebox.askyesno
ui.messagebox.askyesno = lambda *a, **k: False
check("mở dialog thêm (lần 2)", click_btn(dlg, "+ Thêm key"))
root.update()
ed = find_toplevel("Thêm API key")
ents = find_all(ed, ttk.Entry)
set_entry(ents[0], "MY_NEW_KEY")
set_entry(ents[1], "overwritten")
click_btn(ed, "Lưu")
root.update()
check("từ chối ghi đè -> .env giữ value cũ", "MY_NEW_KEY=nv42" in read_env_raw())
check("từ chối ghi đè -> dialog còn mở", find_toplevel("Thêm API key") is not None)
ed = find_toplevel("Thêm API key")
click_btn(ed, "Hủy")
root.update()
ui.messagebox.askyesno = _real_aysno_f2

# 4g. Value rỗng -> bị chặn (dùng dialog trực tiếp, không qua nút)
app._api_key_edit_dialog("", "", lambda: None, parent=dlg)
root.update()
ed = find_toplevel("Thêm API key")
ents = find_all(ed, ttk.Entry)
set_entry(ents[0], "EMPTYBLOCK")
set_entry(ents[1], "")
click_btn(ed, "Lưu")
root.update()
check("value rỗng -> không ghi vào .env", "EMPTYBLOCK" not in read_env_raw())
ed2 = find_toplevel("Thêm API key")
check("value rỗng -> dialog còn mở + nhãn lỗi",
      ed2 is not None and "Giá trị" in " ".join(str(l.cget("text")) for l in find_all(ed2, tk.Label)))
if ed2:
    click_btn(ed2, "Hủy")
root.update()

# 4h. Xóa key (stub askyesno True) — MỌI hàng đều có nút Xóa nên phải dò đúng hàng theo tên
_real_aysno = ui.messagebox.askyesno
ui.messagebox.askyesno = lambda *a, **k: True
xbtn = None
for lab in find_all(dlg, tk.Label):
    if (lab.cget("text") or "") == "MY_CUSTOM_KEY":
        node = lab.master  # lbl_fr -> đi lên tới frame hàng có nút Xóa
        while node is not None and node is not dlg:
            cand = [b for b in find_all(node, tk.Button) if (b.cget("text") or "") == "Xóa"]
            if cand:
                xbtn = cand[0]
                break
            node = node.master
        break
check("hàng MY_CUSTOM_KEY có nút Xóa (đúng dòng)", xbtn is not None)
xbtn.invoke()
root.update()
check("nút Xóa -> key biến mất khỏi .env", "MY_CUSTOM_KEY" not in read_env_raw())
check("os.environ pop khi xóa", "MY_CUSTOM_KEY" not in os.environ)
ui.messagebox.askyesno = _real_aysno

# 4i. Double-open guard
_real_pw = api_vault.check_password
api_vault.check_password = lambda pw: True
app.open_api_key_manager()
root.update()
app.open_api_key_manager()
root.update()
tops = [w for w in root.winfo_children() if isinstance(w, tk.Toplevel) and "Quản lý API KEY" in (w.title() or "")]
check("guard double-open: đúng 1 dialog", len(tops) == 1, str(len(tops)))
api_vault.check_password = _real_pw

# 4j. Đổi mật khẩu change_mode: 3 Entry, chặn khi mật khẩu hiện tại sai
app._ask_api_password(lambda: None, change_mode=True)
root.update()
cw = find_toplevel("Đổi mật khẩu tiện ích API")
check("dialog đổi mật khẩu mở", cw is not None)
cents = [e for e in find_all(cw, tk.Entry) if e.cget("show") == "•"]
check("dialog đổi có 3 Entry password", len(cents) == 3, str(len(cents)))
_real_info = ui.messagebox.showinfo
ui.messagebox.showinfo = lambda *a, **k: None
set_entry(cents[0], "SAIQUA")
set_entry(cents[1], "batbuoc")
set_entry(cents[2], "batbuoc")
click_btn(cw, "Xác nhận")
root.update()
check("đổi mk: mật khẩu hiện tại sai -> chặn", find_toplevel("Đổi mật khẩu tiện ích API") is not None)
check("đổi mk: hiện nhãn lỗi", "không đúng" in " ".join(str(l.cget("text")) for l in find_all(cw, tk.Label)))
set_entry(cents[0], "MatKhauMoi!4")
set_entry(cents[1], "MatKhauMoi!44")
set_entry(cents[2], "MatKhauMoi!44")
click_btn(cw, "Xác nhận")
root.update()
check("đổi mk thành công -> dialog đóng", find_toplevel("Đổi mật khẩu tiện ích API") is None)
check("mật khẩu mới có hiệu lực", api_vault.check_password("MatKhauMoi!44") is True)
check("mật khẩu cũ bị vô hiệu", api_vault.check_password("MatKhauMoi!4") is False)
ui.messagebox.showinfo = _real_info

# 4k. Theme toggle với dialog đang mở — không crash remap
try:
    app._toggle_theme()
    root.update()
    app._toggle_theme()
    root.update()
    check("toggle theme 2 vòng với dialog mở không crash", True)
except Exception as e:
    check("toggle theme 2 vòng với dialog mở không crash", False, repr(e))

# 4l. Kiểm tĩnh source
src_ui = io.open(os.path.join(HERE, "ui_main.py"), encoding="utf-8").read()
check("ui_main không còn tham chiếu C_STOP_FG", "C_STOP_FG" not in src_ui)
check("eye_btn bind btn=eye_btn (chống late-binding)", "def _toggle(name=name, val_lbl=val_lbl, btn=eye_btn):" in src_ui)
check("btn_api_keys xuất hiện >=3 lần (nút + 2 tuple disable)", src_ui.count("self.btn_api_keys") >= 3)
check("startup sync_env_into_process có wire", "api_vault.sync_env_into_process()" in src_ui)

# dọn GUI
try:
    dlg.destroy()
except Exception:
    pass
root.update()
root.destroy()

hr("5. .env THẬT của repo không bị đụng")
real_env_hash_after = ""
if os.path.exists(REAL_ENV):
    real_env_hash_after = hashlib.sha256(open(REAL_ENV, "rb").read()).hexdigest()
check("hash .env thật trước == sau", real_env_hash_before == real_env_hash_after,
      f"{real_env_hash_before[:12]} vs {real_env_hash_after[:12]}")

shutil.rmtree(TMP, ignore_errors=True)
for k in ("GEMINI_API_KEY", "OPENAI_API_KEY", "EMPTY_KEY", "OLD_STYLE", "QUAN_TRONG",
          "MY_CUSTOM_KEY", "BRAND_NEW", "MY_NEW_KEY", "ONLY_ENV_KEY", "A", "B", "DUP",
          "EMPTYBLOCK", "stillhere"):
    os.environ.pop(k, None)
os.environ.pop("GPM_BOT_ENV_FILE", None)
os.environ.pop("GPM_BOT_DATA_DIR", None)

print("\n" + "=" * 68)
print(f"KẾT QUẢ v1.4.8: PASS={len(PASS)}  FAIL={len(FAIL)}")
if FAIL:
    for f in FAIL:
        print("  [FAIL]", f)
    sys.exit(1)
print("SMOKE v1.4.8: ALL PASS")
