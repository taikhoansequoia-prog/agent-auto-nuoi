# -*- coding: utf-8 -*-
"""
SMOKE v1.5.6 — ENDPOINT TỰ ĐẶT cho API KEY (trống = cổng chính, điền = ghi đè).

Cô lập tuyệt đối:
  GPM_BOT_ENV_FILE  = <tmp>/.env   (api_vault không bao giờ đụng .env thật)
  GPM_BOT_DATA_DIR  = <tmp>/data   (DB + app_config tạm)
Hash .env THẬT của repo trước == sau khi chạy.

Phủ 6 tầng:
  0 src/paths.py env override
  1 api_vault: endpoint_name / is_endpoint_key / get_endpoint / delete_endpoint /
              known_keys_with_endpoints + round-trip .env giữ CRLF
  2 agent/brain_manager + gemini_brain + openai_brain với SDK giả (dotenv/openai/google)
  3 GUI: _open_api_key_dialog — dòng "_ENDPOINT" bị ẩn, nhãn "Cổng: ..." đúng màu,
         dialog sửa có 3 Entry, ents[2] nạp endpoint cũ, lưu có endpoint -> ghi biến phụ,
         lưu trống -> xoá biến phụ, Xoá key -> xoá luôn biến phụ
  4 toggle theme 2 vòng khi dialog đang mở (remap màu không crash)
  5 hash .env thật không đổi
  6 assert tĩnh trên nguồn (chuỗi verbatim)
"""
import hashlib
import io
import os
import shutil
import sys
import tempfile
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

TMP = tempfile.mkdtemp(prefix="gpm_v156_")
ENV_FILE = os.path.join(TMP, ".env")
DATA_DIR = os.path.join(TMP, "data")
REAL_ENV = os.path.join(REPO, ".env")

os.environ["GPM_BOT_ENV_FILE"] = ENV_FILE
os.environ["GPM_BOT_DATA_DIR"] = DATA_DIR


def env_hash(path):
    if not os.path.exists(path):
        return "(absent)"
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()[:12]


REAL_ENV_HASH_BEFORE = env_hash(REAL_ENV)

PASS, FAIL = [], []


def check(name, cond, extra=""):
    if cond:
        PASS.append(name)
        print("  [PASS] " + name)
    else:
        FAIL.append(name + ("  :: " + str(extra) if extra else ""))
        print("  [FAIL] " + name + ("  -> " + str(extra) if extra else ""))


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
    with io.open(ENV_FILE, "r", encoding="utf-8-sig", newline="") as f:
        return f.read()


def find_all(widget, kind, out=None):
    out = [] if out is None else out
    for w in widget.winfo_children():
        if isinstance(w, kind):
            out.append(w)
        find_all(w, kind, out)
    return out


def find_toplevel(title_frag):
    for w in root.winfo_children():
        if isinstance(w, tk.Toplevel) and title_frag.lower() in str(w.title()).lower():
            return w
    return None


def set_entry(en, text):
    en.delete(0, "end")
    en.insert(0, text)
    try:
        en.invoke()
    except Exception:
        pass
    root.update()


def click_btn(parent, text):
    for b in find_all(parent, tk.Button):
        try:
            if str(b.cget("text")) == text:
                b.invoke()
                return True
        except Exception:
            pass
    for b in find_all(parent, ttk.Button):
        try:
            if str(b.cget("text")) == text:
                b.invoke()
                return True
        except Exception:
            pass
    return False


def labels_with_prefix(win, prefix):
    return [l for l in find_all(win, tk.Label) if str(l.cget("text")).startswith(prefix)]


root = None

# ---------------------------------------------------------------- harness smoke
hr("HARNESS: cô lập .env/DB tạm")
check("GPM_BOT_ENV_FILE trỏ tmp", os.environ.get("GPM_BOT_ENV_FILE") == ENV_FILE)
check("tmp khác .env thật", os.path.abspath(ENV_FILE) != os.path.abspath(REAL_ENV))

# ---------------------------------------------------------------- section 0
hr("SECTION 0 — src.paths.env_path() tôn trọng GPM_BOT_ENV_FILE")
from src import paths

check("env_path() == ENV_FILE tạm",
      os.path.abspath(paths.env_path()) == os.path.abspath(ENV_FILE),
      paths.env_path())
_saved_env_override = os.environ.pop("GPM_BOT_ENV_FILE")
check("không override -> repo-root .env",
      os.path.abspath(paths.env_path()) == os.path.abspath(REAL_ENV),
      paths.env_path())
os.environ["GPM_BOT_ENV_FILE"] = _saved_env_override

# ---------------------------------------------------------------- section 1
hr("SECTION 1 — api_vault: helper endpoint")
from src import api_vault

check("endpoint_name('OPENAI_API_KEY')",
      api_vault.endpoint_name("OPENAI_API_KEY") == "OPENAI_API_KEY_ENDPOINT")
check("endpoint_name strip + UPPER + rỗng",
      api_vault.endpoint_name("  gemini_api_key ") == "GEMINI_API_KEY_ENDPOINT"
      and api_vault.endpoint_name("") == "_ENDPOINT")
check("is_endpoint_key đúng",
      api_vault.is_endpoint_key("OPENAI_API_KEY_ENDPOINT") is True
      and api_vault.is_endpoint_key("openai_api_key_endpoint") is True)
check("is_endpoint_key KHÔNG nhầm key chính",
      api_vault.is_endpoint_key("OPENAI_API_KEY") is False
      and api_vault.is_endpoint_key("MY_ENDPOINT_HACK") is False
      and api_vault.is_endpoint_key("") is False
      and api_vault.is_endpoint_key(None) is False)
_kk = api_vault.known_keys_with_endpoints()
check("known_keys_with_endpoints phủ KNOWN_KEYS",
      len(_kk) == len(api_vault.KNOWN_KEYS)
      and all(n == api_vault.endpoint_name(k) for k, _d, n in _kk), str(_kk))

SEED = (
    "GEMINI_API_KEY=gemkey-aaaa\r\n"
    "GEMINI_API_KEY_ENDPOINT=https://gemini-proxy.example.com\r\n"
    "# comment giữ nguyên\r\n"
    "OPENAI_API_KEY=okey-bbbb\n"
    "MY_CUSTOM_KEY=ckey-cccc\r\n"
    "EMPTY_ENDPOINT_KEY=\r\n"
    "EMPTY_ENDPOINT_KEY_ENDPOINT=\r\n"
)
seed_env(SEED)
check("get_endpoint đọc biến phụ từ .env",
      api_vault.get_endpoint("GEMINI_API_KEY") == "https://gemini-proxy.example.com",
      api_vault.get_endpoint("GEMINI_API_KEY"))
check("get_endpoint key không có endpoint -> rỗng",
      api_vault.get_endpoint("OPENAI_API_KEY") == "")
check("get_endpoint tên thường cũng khớp (upper nội bộ)",
      api_vault.get_endpoint("gemini_api_key") == "https://gemini-proxy.example.com")
os.environ["FALLBACK_ENDPOINT_KEY_ENDPOINT"] = "https://from-process-only"
check("get_endpoint fallback os.environ",
      api_vault.get_endpoint("FALLBACK_ENDPOINT_KEY") == "https://from-process-only")
os.environ.pop("FALLBACK_ENDPOINT_KEY_ENDPOINT")

check("set_key endpoint giữ CRLF + comment",
      api_vault.set_key("OPENAI_API_KEY", "okey-NEW") is True)
_raw = read_env_raw()
check(".env vẫn giữ comment + CRLF sau set_key",
      "# comment giữ nguyên" in _raw and "\r\n" in _raw)
check("endpoint của OPENAI đổi khi set_key key chính",
      api_vault.get_endpoint("OPENAI_API_KEY") == "")
check("set_key tên sai -> False", api_vault.set_key("bad key!", "x") is False)

check("delete_endpoint xoá đúng biến phụ",
      api_vault.delete_endpoint("GEMINI_API_KEY") is True)
check("get_endpoint rỗng sau khi xoá", api_vault.get_endpoint("GEMINI_API_KEY") == "")
check("key chính GEMINI_API_KEY CÒN sau khi xoá endpoint",
      api_vault.get_key("GEMINI_API_KEY") == "gemkey-aaaa")
check("xoá endpoint lần 2 vẫn True (idempotent)",
      api_vault.delete_endpoint("GEMINI_API_KEY") is True)
check("endpoint rỗng cũng xoá được",
      api_vault.delete_endpoint("EMPTY_ENDPOINT_KEY") is True
      and "EMPTY_ENDPOINT_KEY=" in read_env_raw())
check("key chính EMPTY_ENDPOINT_KEY vẫn còn",
      api_vault.get_key("EMPTY_ENDPOINT_KEY") == "")

# ---------------------------------------------------------------- section 2
hr("SECTION 2 — brain wiring với SDK giả (không cài google/openai/dotenv)")


class _FakeDotenvModule(object):
    @staticmethod
    def load_dotenv(*a, **k):
        return False


sys.modules["dotenv"] = _FakeDotenvModule()

CFG_CALLS = []


class _FakeGenerativeModel(object):
    def __init__(self, model_name=None, *a, **k):
        self.model_name = model_name


class _FakeGenai(object):
    # SDK thật có GenerativeModel; gemini_brain.py dùng nó NGOÀI try/except
    # nên stub phải có thuộc tính này.
    GenerativeModel = _FakeGenerativeModel

    @staticmethod
    def configure(api_key=None):
        # CHỮ TÌNH CỐ: không nhận api_endpoint -> mọi lần truyền endpoint phải
        # rơi vào nhánh except TypeError (đúng hành vi SDK cũ).
        CFG_CALLS.append({"api_key": api_key})


GOOGLE_MOD = type(sys)("google")
GOOGLE_MOD.generativeai = _FakeGenai
sys.modules["google"] = GOOGLE_MOD
sys.modules["google.generativeai"] = _FakeGenai

OPENAI_CALLS = []


class _FakeOpenAI(object):
    def __init__(self, **kwargs):
        OPENAI_CALLS.append(kwargs)


OPENAI_MOD = type(sys)("openai")
OPENAI_MOD.OpenAI = _FakeOpenAI
sys.modules["openai"] = OPENAI_MOD

from agent.gemini_brain import GeminiBrain
from agent.openai_brain import OpenAIBrain, GenericLLMBrain

check("OpenAIBrain là alias GenericLLMBrain (không phải bug có sẵn)",
      OpenAIBrain is GenericLLMBrain)

CFG_CALLS.clear()
g1 = GeminiBrain(api_key="gk", endpoint="https://my-gemini-gateway/v1")
check("Gemini truyền api_endpoint -> SDK giả raise TypeError -> fallback cổng chính",
      len(CFG_CALLS) == 1 and CFG_CALLS[0] == {"api_key": "gk"}, str(CFG_CALLS))
check("Gemini fallback vẫn tạo được model",
      getattr(g1, "model", None) is not None)

CFG_CALLS.clear()
g2 = GeminiBrain(api_key="gk", endpoint="   ")
check("Gemini endpoint khoảng trắng = cổng chính (không gọi api_endpoint)",
      len(CFG_CALLS) == 1 and CFG_CALLS[0] == {"api_key": "gk"})
CFG_CALLS.clear()
g3 = GeminiBrain(api_key="gk")
check("Gemini không truyền endpoint = cổng chính",
      len(CFG_CALLS) == 1 and CFG_CALLS[0] == {"api_key": "gk"})

OPENAI_CALLS.clear()
o1 = OpenAIBrain(api_key="ok", model_name="gpt-5-mini", base_url="https://proxy/v1")
check("OpenAI base_url có -> kwargs base_url",
      len(OPENAI_CALLS) == 1 and OPENAI_CALLS[0].get("base_url") == "https://proxy/v1",
      str(OPENAI_CALLS))
OPENAI_CALLS.clear()
o2 = OpenAIBrain(api_key="ok", model_name="gpt-5-mini", base_url=None)
check("OpenAI base_url None -> KHÔNG có key base_url (SDK tự về cổng chính)",
      len(OPENAI_CALLS) == 1 and "base_url" not in OPENAI_CALLS[0], str(OPENAI_CALLS))
OPENAI_CALLS.clear()
o3 = OpenAIBrain(api_key="ok", model_name="gpt-5-mini", base_url="")
check("OpenAI base_url rỗng -> cũng về cổng chính",
      len(OPENAI_CALLS) == 1 and "base_url" not in OPENAI_CALLS[0], str(OPENAI_CALLS))

from agent.brain_manager import BrainManager

_ENV_BACKUP = {}
for _k in ("GEMINI_API_KEY", "GEMINI_API_KEY_ENDPOINT", "OPENAI_API_KEY",
           "OPENAI_API_KEY_ENDPOINT", "QWEN_API_KEY", "QWEN_API_KEY_ENDPOINT",
           "DASHSCOPE_API_KEY"):
    _ENV_BACKUP[_k] = os.environ.get(_k)


def _restore_env():
    for k, v in _ENV_BACKUP.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v


# gemini: blank -> cổng chính
os.environ["GEMINI_API_KEY"] = "brain-gem"
os.environ.pop("GEMINI_API_KEY_ENDPOINT", None)
CFG_CALLS.clear()
b = BrainManager.get_brain("gemini")
check("[gemini] endpoint TRỐNG -> configure(api_key) không api_endpoint",
      len(CFG_CALLS) == 1 and "api_endpoint" not in CFG_CALLS[0], str(CFG_CALLS))

os.environ["GEMINI_API_KEY_ENDPOINT"] = "https://gem-gw/v1"
CFG_CALLS.clear()
b = BrainManager.get_brain("gemini")
check("[gemini] endpoint CÓ -> vẫn trả về brain hợp lệ (TypeError được nuốt có chủ đích)",
      b.__class__.__name__ == "GeminiBrain" and len(CFG_CALLS) == 1, str(CFG_CALLS))

# openai
os.environ["OPENAI_API_KEY"] = "brain-oai"
OPENAI_CALLS.clear()
os.environ.pop("OPENAI_API_KEY_ENDPOINT", None)
b = BrainManager.get_brain("openai")
check("[openai] endpoint TRỐNG -> không base_url (cổng chính)",
      len(OPENAI_CALLS) == 1 and "base_url" not in OPENAI_CALLS[0], str(OPENAI_CALLS))
OPENAI_CALLS.clear()
os.environ["OPENAI_API_KEY_ENDPOINT"] = "https://oai-proxy/v1"
b = BrainManager.get_brain("openai")
check("[openai] endpoint CÓ -> base_url = endpoint tự đặt",
      len(OPENAI_CALLS) == 1 and OPENAI_CALLS[0].get("base_url") == "https://oai-proxy/v1",
      str(OPENAI_CALLS))

# qwen
os.environ["QWEN_API_KEY"] = "brain-qwen"
OPENAI_CALLS.clear()
os.environ.pop("QWEN_API_KEY_ENDPOINT", None)
b = BrainManager.get_brain("qwen-max")
check("[qwen-max] endpoint TRỐNG -> DashScope mặc định",
      len(OPENAI_CALLS) == 1
      and OPENAI_CALLS[0].get("base_url") == "https://dashscope.aliyuncs.com/compatible-mode/v1",
      str(OPENAI_CALLS))
OPENAI_CALLS.clear()
os.environ["QWEN_API_KEY_ENDPOINT"] = "https://qwen-selfhost/v1"
b = BrainManager.get_brain("qwen-flash")
check("[qwen-flash] endpoint CÓ -> ghi đè DashScope",
      len(OPENAI_CALLS) == 1 and OPENAI_CALLS[0].get("base_url") == "https://qwen-selfhost/v1",
      str(OPENAI_CALLS))

_bad = None
try:
    BrainManager.get_brain("khong_co_thuc_tu_nay")
except Exception as e:
    _bad = e
check("brain_type sai vẫn raise ValueError (không đổi hành vi)",
      isinstance(_bad, ValueError), repr(_bad))
_restore_env()

# ---------------------------------------------------------------- section 3
hr("SECTION 3 — GUI: danh sách key + dialog sửa có Endpoint")
import ui_main as ui

SEED3 = (
    "GEMINI_API_KEY=gui-gem-123456\r\n"
    "GEMINI_API_KEY_ENDPOINT=https://gem-custom.example/v1\r\n"
    "OPENAI_API_KEY=gui-oai-123456\r\n"
    "MY_CUSTOM_KEY=gui-custom-1\r\n"
    "TELEGRAM_API_BASE=https://tg-selfhost.example\r\n"
)
seed_env(SEED3)
for _n in ("GEMINI_API_KEY", "GEMINI_API_KEY_ENDPOINT", "OPENAI_API_KEY",
           "OPENAI_API_KEY_ENDPOINT", "MY_CUSTOM_KEY", "MY_CUSTOM_KEY_ENDPOINT",
           "TELEGRAM_BOT_TOKEN", "TELEGRAM_API_BASE", "NEW_KEY_9",
           "NEW_KEY_9_ENDPOINT", "EMPTYBLOCK"):
    os.environ.pop(_n, None)
api_vault.sync_env_into_process()

app = ui.AutomationApp(root := tk.Tk())
root.update()
root.withdraw()

check("app có _open_api_key_dialog", callable(getattr(app, "_open_api_key_dialog", None)))
check("app có _api_key_edit_dialog", callable(getattr(app, "_api_key_edit_dialog", None)))
check("palette có C_ACCENT_2 (màu cổng tự đặt)",
      isinstance(getattr(app, "C_ACCENT_2", None), str) and app.C_ACCENT_2.startswith("#"),
      repr(getapp := getattr(app, "C_ACCENT_2", None)))

app._open_api_key_dialog()
root.update()
win = find_toplevel("Quản lý API KEY")
check("mở dialog Quản lý API KEY", win is not None)

row_names = [str(l.cget("text")) for l in find_all(win, tk.Label)
             if str(l.cget("text")) in ("GEMINI_API_KEY", "OPENAI_API_KEY",
                                        "MY_CUSTOM_KEY", "TELEGRAM_API_BASE",
                                        "GEMINI_API_KEY_ENDPOINT")]
check("dòng GEMINI/OPENAI/MY_CUSTOM_KEY hiển thị",
      "GEMINI_API_KEY" in row_names and "OPENAI_API_KEY" in row_names
      and "MY_CUSTOM_KEY" in row_names, str(row_names))
check("BIẾN PHỤ GEMINI_API_KEY_ENDPOINT bị ẩn (không thành dòng riêng)",
      "GEMINI_API_KEY_ENDPOINT" not in row_names, str(row_names))
check("TELEGRAM_API_BASE vẫn là dòng riêng (key thường, không phải *_ENDPOINT)",
      "TELEGRAM_API_BASE" in row_names, str(row_names))

cong = labels_with_prefix(win, "Cổng:")
check("có nhãn Cổng cho MỖI dòng key", len(cong) >= 3, str(len(cong)))


def _cong_text_for(keyname):
    for l in find_all(win, tk.Label):
        if str(l.cget("text")) != keyname:
            continue
        fr = l.master
        for _up in range(4):
            if fr is None:
                break
            for sub in find_all(fr, tk.Label):
                if str(sub.cget("text")).startswith("Cổng:"):
                    return sub
            fr = fr.master
    return None


g_lbl = _cong_text_for("GEMINI_API_KEY")
o_lbl = _cong_text_for("OPENAI_API_KEY")
check("GEMINI hiện cổng tự đặt",
      g_lbl is not None and str(g_lbl.cget("text")) == "Cổng: https://gem-custom.example/v1",
      str(g_lbl.cget("text")) if g_lbl else None)
check("GEMINI dùng màu accent (C_ACCENT_2)",
      g_lbl is not None and str(g_lbl.cget("fg")).lower() == app.C_ACCENT_2.lower(),
      str(g_lbl.cget("fg")) if g_lbl else None)
check("OPENAI (không endpoint) hiện 'Cổng: chính (mặc định)'",
      o_lbl is not None and str(o_lbl.cget("text")) == "Cổng: chính (mặc định)",
      str(o_lbl.cget("text")) if o_lbl else None)
check("OPENAI dùng màu muted",
      o_lbl is not None and str(o_lbl.cget("fg")).lower() == app.C_MUTED.lower(),
      str(o_lbl.cget("fg")) if o_lbl else None)

# --- dialog sửa GEMINI: 3 Entry, ents[2] nạp endpoint cũ
saved = []
app._api_key_edit_dialog("GEMINI_API_KEY", "khoá Gemini", lambda: saved.append(1), parent=win)
root.update()
ed = find_toplevel("Sửa GEMINI_API_KEY")
check("mở dialog Sửa GEMINI_API_KEY", ed is not None)
ents = find_all(ed, ttk.Entry)
check("dialog sửa có 3 Entry (tên + value + endpoint)", len(ents) == 3, str(len(ents)))
if len(ents) == 3:
    check("ents[0] = tên key", ents[0].get() == "GEMINI_API_KEY", ents[0].get())
    check("ents[2] = endpoint NẠP SẴN giá trị cũ",
          ents[2].get() == "https://gem-custom.example/v1", ents[2].get())
    ep_lbls = [str(l.cget("text")) for l in find_all(ed, tk.Label)
               if "Endpoint" in str(l.cget("text"))]
    check("có nhãn 'Endpoint của GEMINI_API_KEY (để trống = cổng chính)'",
          any("Endpoint của GEMINI_API_KEY" in t and "cổng chính" in t for t in ep_lbls),
          str(ep_lbls))
    hint = [str(l.cget("text")) for l in find_all(ed, tk.Label)
            if "dashscope" in str(l.cget("text")).lower()]
    check("có hint ví dụ endpoint", len(hint) >= 1, str(hint))
    # đổi cả value lẫn endpoint -> lưu
    set_entry(ents[1], "geminiUPDATED-999")
    set_entry(ents[2], "https://gem-NEW-gateway/v1")
    check("bấm Lưu", click_btn(ed, "Lưu"))
    root.update()
    _raw = read_env_raw()
    check("lưu: value key chính đổi", api_vault.get_key("GEMINI_API_KEY") == "geminiUPDATED-999",
          api_vault.get_key("GEMINI_API_KEY"))
    check("lưu: BIẾN PHỤ GEMINI_API_KEY_ENDPOINT ghi đè trong .env",
          "GEMINI_API_KEY_ENDPOINT=https://gem-NEW-gateway/v1" in _raw, _raw)
    check("lưu: os.environ cũng có endpoint ngay",
          os.environ.get("GEMINI_API_KEY_ENDPOINT") == "https://gem-NEW-gateway/v1")
    check("lưu: callback on_saved chạy", saved == [1], str(saved))
    check("lưu: dialog đóng", find_toplevel("Sửa GEMINI_API_KEY") is None)
    check("lưu: CRLF + comment dòng khác không phá", "\r\n" in _raw)
else:
    check("ents[0] = tên key", False, "không đủ 3 Entry")
    check("ents[2] = endpoint NẠP SẴN giá trị cũ", False, "không đủ 3 Entry")
    check("có nhãn 'Endpoint của GEMINI_API_KEY (để trống = cổng chính)'", False, "không đủ 3 Entry")
    check("có hint ví dụ endpoint", False, "không đủ 3 Entry")
    check("bấm Lưu", False, "không đủ 3 Entry")
    check("lưu: value key chính đổi", False, "không đủ 3 Entry")
    check("lưu: BIẾN PHỤ GEMINI_API_KEY_ENDPOINT ghi đè trong .env", False, "không đủ 3 Entry")
    check("lưu: os.environ cũng có endpoint ngay", False, "không đủ 3 Entry")
    check("lưu: callback on_saved chạy", False, "không đủ 3 Entry")
    check("lưu: dialog đóng", False, "không đủ 3 Entry")
    check("lưu: CRLF + comment dòng khác không phá", False, "không đủ 3 Entry")

# --- lưu TRỐNG endpoint -> xoá biến phụ (về cổng chính)
saved2 = []
app._api_key_edit_dialog("GEMINI_API_KEY", "", lambda: saved2.append(1), parent=win)
root.update()
ed = find_toplevel("Sửa GEMINI_API_KEY")
ents = find_all(ed, ttk.Entry)
check("mở lại dialog: ents[2] nạp endpoint MỚI",
      len(ents) == 3 and ents[2].get() == "https://gem-NEW-gateway/v1",
      ents[2].get() if len(ents) == 3 else str(len(ents)))
if len(ents) == 3:
    set_entry(ents[2], "   ")  # khoảng trắng = trống
    click_btn(ed, "Lưu")
    root.update()
    check("lưu trống -> xoá biến phụ khỏi .env",
          "GEMINI_API_KEY_ENDPOINT" not in read_env_raw(), read_env_raw())
    check("lưu trống -> xoá khỏi os.environ",
          "GEMINI_API_KEY_ENDPOINT" not in os.environ)
    check("lưu trống -> key chính VẪN CÒN",
          api_vault.get_key("GEMINI_API_KEY") == "geminiUPDATED-999",
          api_vault.get_key("GEMINI_API_KEY"))
else:
    check("lưu trống -> xoá biến phụ khỏi .env", False, "không đủ 3 Entry")
    check("lưu trống -> xoá khỏi os.environ", False, "không đủ 3 Entry")
    check("lưu trống -> key chính VẪN CÒN", False, "không đủ 3 Entry")

# --- dialog THÊM key mới: endpoint trống -> không sinh biến phụ
app._api_key_edit_dialog("", "", lambda: None, parent=win)
root.update()
nd = find_toplevel("Thêm API key")
check("mở dialog Thêm API key", nd is not None)
nents = find_all(nd, ttk.Entry)
check("dialog thêm cũng có 3 Entry", len(nents) == 3, str(len(nents)))
if len(nents) == 3:
    check("dialog thêm: ents[2] trống mặc định", nents[2].get() == "", nents[2].get())
    set_entry(nents[0], "new key-9")
    set_entry(nents[1], "nv42")
    set_entry(nents[2], "https://only-endpoint/v1")
    click_btn(nd, "Lưu")
    root.update()
    _raw = read_env_raw()
    check("thêm key: chuẩn hoá tên NEW_KEY_9", api_vault.get_key("NEW_KEY_9") == "nv42", _raw)
    check("thêm key: ghi kèm NEW_KEY_9_ENDPOINT",
          "NEW_KEY_9_ENDPOINT=https://only-endpoint/v1" in _raw, _raw)
else:
    check("dialog thêm: ents[2] trống mặc định", False, "không đủ 3 Entry")
    check("thêm key: chuẩn hoá tên NEW_KEY_9", False, "không đủ 3 Entry")
    check("thêm key: ghi kèm NEW_KEY_9_ENDPOINT", False, "không đủ 3 Entry")

# --- Xóa key phải xoá luôn endpoint đi kèm
_real_aysno = ui.messagebox.askyesno
ui.messagebox.askyesno = lambda *a, **k: True
app._api_key_edit_dialog("NEW_KEY_9", "", lambda: None, parent=win)
root.update()
ed9 = find_toplevel("Sửa NEW_KEY_9")
check("NEW_KEY_9 có dialog sửa (key tự đặt)", ed9 is not None)
if ed9 is not None:
    ed9.destroy()
    root.update()
app._open_api_key_dialog()
root.update()
# Dialog API KEY là NON-MODAL và production không chặn mở 2 cửa sổ cùng lúc -> ở đây
# có 2 Toplevel "Quản lý API KEY": bản CŨ (win, vẽ trước khi NEW_KEY_9 được ghi) và
# bản MỚI (tự _render_rows từ .env nên CÓ dòng NEW_KEY_9). Quét theo tiêu đề sẽ ăn
# bản cũ -> FAIL oan. Duyệt MỌI cửa sổ manager đang tồn tại, lấy bản có dòng key.
mgrs = [w for w in root.winfo_children()
        if isinstance(w, tk.Toplevel) and "Quản lý API KEY" in str(w.title())]
win2 = None
target = None
xbtn = None
for w in mgrs:
    for l in find_all(w, tk.Label):
        if str(l.cget("text")) == "NEW_KEY_9":
            win2, target = w, l
            break
    if target is not None:
        break
check("có cửa sổ manager vẽ lại đủ NEW_KEY_9", target is not None,
      "mgr=%d so=%d" % (len(mgrs), len(find_all(mgrs[-1], tk.Label)) if mgrs else 0))
if target is not None:
    fr = target.master
    for _up in range(4):
        if fr is None:
            break
        for b in find_all(fr, tk.Button):
            if str(b.cget("text")) == "Xóa":
                xbtn = b
                break
        if xbtn is None:
            for b in find_all(fr, ttk.Button):
                if str(b.cget("text")) == "Xóa":
                    xbtn = b
                    break
        if xbtn is not None:
            break
        fr = fr.master
check("tìm thấy nút Xóa của NEW_KEY_9", xbtn is not None)
if xbtn is not None:
    xbtn.invoke()
    root.update()
    check("Xóa key -> xoá luôn NEW_KEY_9_ENDPOINT",
          "NEW_KEY_9_ENDPOINT" not in read_env_raw(), read_env_raw())
    check("Xóa key -> key chính cũng mất", api_vault.get_key("NEW_KEY_9") == "")
    check("Xóa key -> os.environ sạch cả 2",
          "NEW_KEY_9" not in os.environ and "NEW_KEY_9_ENDPOINT" not in os.environ)
else:
    check("Xóa key -> xoá luôn NEW_KEY_9_ENDPOINT", False, "không tìm thấy nút Xóa")
    check("Xóa key -> key chính cũng mất", False, "không tìm thấy nút Xóa")
    check("Xóa key -> os.environ sạch cả 2", False, "không tìm thấy nút Xóa")
ui.messagebox.askyesno = _real_aysno

# ---------------------------------------------------------------- section 4
hr("SECTION 4 — toggle theme khi dialog API KEY đang mở")
try:
    theme0 = getattr(app, "theme_name", "dark")
    app._toggle_theme()
    root.update()
    app._toggle_theme()
    root.update()
    check("toggle theme 2 vòng với dialog mở không crash", True)
    cong_after = labels_with_prefix(find_toplevel("Quản lý API KEY") or win, "Cổng:")
    check("sau toggle vẫn còn nhãn Cổng", len(cong_after) >= 3, str(len(cong_after)))
except Exception as e:
    check("toggle theme 2 vòng với dialog mở không crash", False, repr(e))
    check("sau toggle vẫn còn nhãn Cổng", False, "exception")

# ---------------------------------------------------------------- section 5
hr("SECTION 5 — .env THẬT của repo không bị đụng")
try:
    root.update()
    for w in root.winfo_children():
        if isinstance(w, tk.Toplevel):
            w.destroy()
    root.update()
    root.destroy()
except Exception:
    pass

# ---------------------------------------------------------------- section 6
hr("SECTION 6 — assert tĩnh trên nguồn")


def src_of(rel):
    with io.open(os.path.join(REPO, rel), encoding="utf-8") as f:
        return f.read()


av = src_of("src/api_vault.py")
check("api_vault.endpoint_name trả <NAME>_ENDPOINT (UPPER)",
      'return f"{(name or \'\').strip().upper()}_ENDPOINT"' in av)
check("api_vault.is_endpoint_key dùng endswith",
      'endswith("_ENDPOINT")' in av)
check("api_vault.get_endpoint strip",
      'return (get_key(endpoint_name(name), path) or "").strip()' in av)
check("api_vault.delete_endpoint delegate delete_key",
      "return delete_key(endpoint_name(name), path)" in av)

bm = src_of("src/agent/brain_manager.py")
check("brain_manager gemini đọc GEMINI_API_KEY_ENDPOINT",
      'endpoint=os.getenv("GEMINI_API_KEY_ENDPOINT") or None' in bm)
check("brain_manager openai đọc OPENAI_API_KEY_ENDPOINT",
      'base_url=os.getenv("OPENAI_API_KEY_ENDPOINT") or None' in bm)
check("brain_manager qwen giữ fallback DashScope",
      'base_url=os.getenv("QWEN_API_KEY_ENDPOINT") or "https://dashscope.aliyuncs.com/compatible-mode/v1"' in bm)
check("brain_manager không còn hardcode DashScope mà không đọc env",
      bm.count("dashscope.aliyuncs.com/compatible-mode/v1") == 1)

gb = src_of("src/agent/gemini_brain.py")
check("gemini_brain nhận endpoint=None",
      "def __init__(self, api_key: str, model_name=\"gemini-1.5-flash\", endpoint=None):" in gb)
check("gemini_brain thử api_endpoint", "api_endpoint=endpoint" in gb)
check("gemini_brain có fallback TypeError", "except TypeError:" in gb)

ob = src_of("src/agent/openai_brain.py")
check("openai_brain threading base_url vào kwargs", 'kwargs["base_url"] = base_url' in ob)

um = src_of("src/ui_main.py")
check("ui_main: dòng _ENDPOINT bị ẩn",
      "and not api_vault.is_endpoint_key(k)]" in um)
check("ui_main: nhãn Cổng tự đặt/mặc định",
      'text=("Cổng: " + endpoint) if endpoint else "Cổng: chính (mặc định)",' in um)
check("ui_main: màu accent khi có endpoint",
      "fg=(self.C_ACCENT_2 if endpoint else self.C_MUTED)," in um)
check("ui_main: _delete xoá kèm endpoint", "api_vault.delete_endpoint(name)" in um)
check("ui_main: log xóa kèm endpoint",
      "Đã xóa {name} (kèm endpoint nếu có) khỏi .env." in um)
check("ui_main: Entry endpoint trong dialog sửa",
      "ep_var = tk.StringVar(value=api_vault.get_endpoint(name) if name else \"\")" in um)
check("ui_main: lưu endpoint khi không trống",
      "api_vault.set_key(api_vault.endpoint_name(key_name), ep)" in um)
check("ui_main: lưu trống -> clear endpoint",
      "api_vault.delete_endpoint(key_name)" in um)
check("ui_main: _do_start truyền api_base cho bot",
      "api_base=api_vault.get_key(\"TELEGRAM_API_BASE\") or None" in um)
check("ui_main: _peek_chat cũng tôn trọng TELEGRAM_API_BASE",
      'base = (api_vault.get_key("TELEGRAM_API_BASE") or "https://api.telegram.org").rstrip("/")' in um)
check("ui_main: không còn hardcode api.telegram.org trong _peek_chat/_do_start",
      um.count("https://api.telegram.org") <= 2, str(um.count("https://api.telegram.org")))
check("ui_main: giữ late-binding fix của nút mắt",
      "def _toggle(name=name, val_lbl=val_lbl, btn=eye_btn):" in um)
check("ui_main: không dùng grab_local (bẫy đã biết)", "grab_local" not in um)

ex = src_of(".env.example")
check(".env.example tài liệu hoá GEMINI_API_KEY_ENDPOINT",
      "GEMINI_API_KEY_ENDPOINT" in ex)
check(".env.example tài liệu hoá OPENAI/QWEN endpoint",
      "OPENAI_API_KEY_ENDPOINT" in ex and "QWEN_API_KEY_ENDPOINT" in ex)
check(".env.example tài liệu hoá TELEGRAM_API_BASE", "TELEGRAM_API_BASE" in ex)
# File .env.example của repo viết KHÔNG DẤU (quy ước ASCII) -> assert phải khớp chữ thật.
check(".env.example nói rõ de TRONG = dung cong chinh mac dinh",
      "cong chinh" in ex and "mac dinh" in ex)

check("hash .env THẬT không đổi sau cả suite",
      env_hash(REAL_ENV) == REAL_ENV_HASH_BEFORE,
      "%s -> %s" % (REAL_ENV_HASH_BEFORE, env_hash(REAL_ENV)))

shutil.rmtree(TMP, ignore_errors=True)
for _k in ("GEMINI_API_KEY", "GEMINI_API_KEY_ENDPOINT", "OPENAI_API_KEY",
           "OPENAI_API_KEY_ENDPOINT", "MY_CUSTOM_KEY", "MY_CUSTOM_KEY_ENDPOINT",
           "NEW_KEY_9", "NEW_KEY_9_ENDPOINT", "TELEGRAM_API_BASE",
           "QWEN_API_KEY", "QWEN_API_KEY_ENDPOINT", "DASHSCOPE_API_KEY",
           "FALLBACK_ENDPOINT_KEY_ENDPOINT", "OPENAI_API_KEY",
           "GPM_BOT_ENV_FILE", "GPM_BOT_DATA_DIR"):
    os.environ.pop(_k, None)
for _m in ("dotenv", "openai", "google", "google.generativeai"):
    sys.modules.pop(_m, None)

print("\n" + "=" * 68)
print("KẾT QUẢ v1.5.6: PASS=%d  FAIL=%d" % (len(PASS), len(FAIL)))
if FAIL:
    for f in FAIL:
        print("   - " + f)
    print("SMOKE v1.5.6: CÓ LỖI")
    sys.exit(1)
print("SMOKE v1.5.6: ALL PASS")
