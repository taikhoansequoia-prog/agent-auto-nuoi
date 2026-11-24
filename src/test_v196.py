# -*- coding: utf-8 -*-
"""
Smoke test v1.12.0 — AI QUA TÀI KHOẢN ĐĂNG NHẬP (Claude Code / Codex), không API key.

Chạy:  python test_v196.py
Cô lập: GPM_BOT_DATA_DIR + GPM_BOT_ENV_FILE + CODEX_HOME -> temp. KHÔNG gọi công cụ thật (mọi lệnh đi qua `run` giả).

Phủ:
  [1] Hàm thuần: mask_email, child_env (bỏ biến API key), explain_account_error, work_dir, codex_models, _codex_error
  [2] Trạng thái đăng nhập: claude_status / codex_status (đã đăng nhập, đang dùng API key, chưa đăng nhập, chưa cài)
  [3] ClaudeAccountBrain: dòng lệnh, stdin, môi trường, lỗi -> last_error tiếng Việt
  [4] ChatGPTAccountBrain: lấy câu trả lời từ file -o, tự đổi model khi model không dùng được với tài khoản, nhớ model chạy được
  [5] get_account_brain + BrainManager.get_brain + ask_long/_ask_obj của niche_learner
  [6] Tĩnh: không print, không đụng file đăng nhập
"""
import json
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
for p in (REPO, HERE):
    if p not in sys.path:
        sys.path.insert(0, p)
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

TMP = tempfile.mkdtemp(prefix="gpm_v196_")
DATA_DIR = os.path.join(TMP, "data")
CODEX_HOME = os.path.join(TMP, "codex_home")
os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(CODEX_HOME, exist_ok=True)
ENV_FILE = os.path.join(TMP, ".env")
open(ENV_FILE, "w", encoding="utf-8").write("")
os.environ["GPM_BOT_DATA_DIR"] = DATA_DIR
os.environ["GPM_BOT_ENV_FILE"] = ENV_FILE
os.environ["CODEX_HOME"] = CODEX_HOME
os.environ.pop("CODEX_CLI_MODEL", None)

from src.agent import account_brain as ab  # noqa: E402
from src.agent.brain_manager import BrainManager  # noqa: E402
from src.workflow import niche_learner as nl  # noqa: E402

PASS = FAIL = 0


def check(name, ok, extra=""):
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f"  [OK] {name}")
    else:
        FAIL += 1
        print(f"  [FAIL] {name} {extra}")


REAL_FIND = (ab.find_claude, ab.find_codex)
ab.find_claude = lambda: r"C:\fake\claude.exe"
ab.find_codex = lambda: r"C:\fake\codex.exe"

# ---------------------------------------------------------------- [1]
print("[1] Ham thuan")
check("mask_email", ab.mask_email("seoteam.x@gmail.com") == "se***@gmail.com" and ab.mask_email("") == "" and ab.mask_email("khong phai") == "")
os.environ.update({"ANTHROPIC_API_KEY": "sk-ant-x", "ANTHROPIC_BASE_URL": "http://x", "CLAUDECODE": "1", "CLAUDE_CODE_ENTRYPOINT": "x",
                   "CLAUDE_CODE_OAUTH_TOKEN": "tok", "CLAUDE_LAU": "gw", "OPENAI_API_KEY": "sk-x", "OPENAI_API_KEY_ENDPOINT": "http://y",
                   "OPENAI_BASE_URL": "http://z"})
ec, eg = ab.child_env(ab._CLAUDE_STRIP), ab.child_env(ab._CODEX_STRIP)
check("moi truong cho Claude: bo ANTHROPIC_* + bien phien Claude Code, giu token dang nhap va bien khac",
      not [k for k in ec if k.startswith("ANTHROPIC_") or k in ("CLAUDECODE", "CLAUDE_CODE_ENTRYPOINT")]
      and ec.get("CLAUDE_CODE_OAUTH_TOKEN") == "tok" and ec.get("CLAUDE_LAU") == "gw" and "PATH" in {k.upper() for k in ec})
check("moi truong cho Codex: bo OPENAI_API_KEY* / OPENAI_BASE_URL (de no dung tai khoan, khong tinh tien API)",
      not [k for k in eg if k.startswith("OPENAI_API_KEY") or k == "OPENAI_BASE_URL"] and eg.get("ANTHROPIC_API_KEY") == "sk-ant-x")
for k in ("ANTHROPIC_API_KEY", "ANTHROPIC_BASE_URL", "CLAUDECODE", "CLAUDE_CODE_ENTRYPOINT", "CLAUDE_CODE_OAUTH_TOKEN", "CLAUDE_LAU",
          "OPENAI_API_KEY", "OPENAI_API_KEY_ENDPOINT", "OPENAI_BASE_URL"):
    os.environ.pop(k, None)
ex = ab.explain_account_error
check("explain_account_error", "CHƯA ĐĂNG NHẬP" in ex("Invalid API key · Please run /login") and "CHƯA ĐĂNG NHẬP" in ex("401 Unauthorized")
      and "HẾT HẠN MỨC" in ex("You've hit your usage limit. Try again at 9pm") and "HẾT HẠN MỨC" in ex("Claude usage limit reached")
      and ex("timed out after 150s") == "quá hạn chờ" and ex("") == "" and ex("something else") == "")
wd = ab.work_dir()
check("thu muc lam viec nam trong data cua app, rong", os.path.isdir(wd) and os.path.dirname(wd) == DATA_DIR and os.listdir(wd) == [])
check("chua co cache model cua Codex -> danh sach rong", ab.codex_models() == [])
json.dump({"models": [{"slug": "hidden-x", "visibility": "hide", "priority": 1}, {"slug": "m-b", "visibility": "list", "priority": 4},
                      {"slug": "m-a", "visibility": "list", "priority": 2}, {"visibility": "list"}, "rac"]},
          open(os.path.join(CODEX_HOME, "models_cache.json"), "w", encoding="utf-8"))
check("codex_models: chi model 'list', xep theo uu tien cua Codex", ab.codex_models() == ["m-a", "m-b"], str(ab.codex_models()))
os.environ["CODEX_CLI_MODEL"] = "ep-buoc"
check("CODEX_CLI_MODEL ep model", ab.codex_models() == ["ep-buoc"])
os.environ.pop("CODEX_CLI_MODEL")
check("codex_listed_models khong xet bien ep model; claude_model mac dinh sonnet, ep bang CLAUDE_CLI_MODEL", ab.codex_listed_models() == ["m-a", "m-b"]
      and ab.claude_model() == "sonnet" and ab.CLAUDE_MODEL_CHOICES[:2] == ["sonnet", "opus"])
os.environ["CLAUDE_CLI_MODEL"] = " opus "
check("CLAUDE_CLI_MODEL ep model Claude", ab.claude_model() == "opus" and ab.ClaudeAccountBrain("x").model_name == "opus")
os.environ.pop("CLAUDE_CLI_MODEL")
check("loi model khong dung duoc -> cau tieng Viet chi cach sua",
      "MODEL đã chọn không dùng được" in ex("ERROR: The 'm' model is not supported when using Codex with a ChatGPT account.")
      and "MODEL đã chọn không dùng được" in ex("There's an issue with the selected model (xyz). It may not exist or you may not have access to it.")
      and "CHƯA ĐĂNG NHẬP" in ex("Invalid API key · Please run /login"))
check("chua co ho so dang nhap Codex -> khong co email/goi, khong vo", ab.codex_account_info() == ("", ""))
import base64  # noqa: E402
_claims = {"email": "nguoidung.gpt@gmail.com", "https://api.openai.com/auth": {"chatgpt_plan_type": "plus"}}
_jwt = "aaa." + base64.urlsafe_b64encode(json.dumps(_claims).encode()).decode().rstrip("=") + ".chu-ky"
json.dump({"tokens": {"id_token": _jwt, "access_token": "BI-MAT-1", "refresh_token": "BI-MAT-2"}},
          open(os.path.join(CODEX_HOME, "auth.json"), "w", encoding="utf-8"))
check("codex_account_info: email DAY DU (user yeu cau) + goi, khong lo ma dang nhap", ab.codex_account_info() == ("nguoidung.gpt@gmail.com", "plus"))
_stg = ab.codex_status(lambda *a, **k: (0, "Logged in using ChatGPT\n", ""))
check("trang thai ChatGPT hien goi + email day du", _stg["detail"] == "đã đăng nhập bằng tài khoản ChatGPT · gói plus · nguoidung.gpt@gmail.com"
      and _stg["who"] == "nguoidung.gpt@gmail.com" and _stg["plan"] == "plus" and "BI-MAT" not in str(_stg))
os.remove(os.path.join(CODEX_HOME, "auth.json"))
check("_codex_error lay dong ERROR, khong lay cau hoi bi in lai",
      ab._codex_error("", "user\nPROMPT BI IN LAI\nwarning: x\nERROR: The 'm' model is not supported when using Codex with a ChatGPT account.\n")
      == "ERROR: The 'm' model is not supported when using Codex with a ChatGPT account.")

# ---------------------------------------------------------------- [2]
print("\n[2] Trang thai dang nhap")
CALLS = []


def mk_run(rc=0, out="", err=""):
    def run(cmd, stdin_text="", timeout=120, env=None, cwd=None):
        CALLS.append({"cmd": list(cmd), "stdin": stdin_text, "timeout": timeout, "env": dict(env or {}), "cwd": cwd})
        return rc, out, err
    return run


st = ab.claude_status(mk_run(out=json.dumps({"loggedIn": True, "authMethod": "claude.ai", "email": "nguoidung@gmail.com", "subscriptionType": "max"})))
check("Claude da dang nhap: goi + email day du", st["logged_in"] and st["plan"] == "max" and st["who"] == "nguoidung@gmail.com"
      and st["detail"] == "đã đăng nhập · gói max · nguoidung@gmail.com", str(st))
check("lenh hoi trang thai Claude", CALLS[-1]["cmd"] == [r"C:\fake\claude.exe", "auth", "status"] and CALLS[-1]["cwd"] == wd)
st = ab.claude_status(mk_run(out=json.dumps({"loggedIn": True, "authMethod": "api_key"})))
check("Claude dang dung API key -> KHONG tinh la tai khoan", not st["logged_in"] and "API key chứ KHÔNG phải tài khoản" in st["detail"])
st = ab.claude_status(mk_run(rc=1, out=json.dumps({"loggedIn": False})))
check("Claude chua dang nhap", not st["logged_in"] and st["detail"] == "chưa đăng nhập")
st = ab.claude_status(mk_run(out="khong phai json"))
check("Claude tra rac -> chua dang nhap, khong vo", not st["logged_in"] and st["installed"])


def boom(*a, **k):
    raise OSError("khong chay duoc")


check("lenh trang thai nem loi -> bao ro, khong vo", "không hỏi được trạng thái" in ab.claude_status(boom)["detail"]
      and "không hỏi được trạng thái" in ab.codex_status(boom)["detail"])
st = ab.codex_status(mk_run(out="Logged in using ChatGPT\n"))
check("ChatGPT da dang nhap bang tai khoan", st["logged_in"] and "tài khoản ChatGPT" in st["detail"]
      and CALLS[-1]["cmd"] == [r"C:\fake\codex.exe", "login", "status"])
st = ab.codex_status(mk_run(err="Logged in using an API key - sk-***\n"))
check("Codex dang dung API key -> KHONG tinh la tai khoan", not st["logged_in"] and "API key chứ KHÔNG phải tài khoản" in st["detail"])
check("Codex chua dang nhap", ab.codex_status(mk_run(rc=1, err="Not logged in\n"))["detail"] == "chưa đăng nhập")
ab.find_claude = ab.find_codex = lambda: ""
check("chua cai cong cu", not ab.claude_status(boom)["installed"] and "chưa cài Claude Code" in ab.claude_status(boom)["detail"]
      and "chưa cài Codex" in ab.codex_status(boom)["detail"] and ab.login_command(ab.CLAUDE_ACCOUNT) == [] and not ab.open_login(ab.CHATGPT_ACCOUNT))
ab.find_claude = lambda: r"C:\fake\claude.exe"
ab.find_codex = lambda: r"C:\fake\codex.exe"
check("lenh dang nhap", ab.login_command(ab.CLAUDE_ACCOUNT) == [r"C:\fake\claude.exe", "auth", "login"]
      and ab.login_command(ab.CHATGPT_ACCOUNT) == [r"C:\fake\codex.exe", "login"])

# ---------------------------------------------------------------- [3]
print("\n[3] ClaudeAccountBrain")
os.environ["ANTHROPIC_API_KEY"] = "sk-ant-khong-duoc-dung"
b = ab.ClaudeAccountBrain(r"C:\fake\claude.exe", mk_run(out=json.dumps({"type": "result", "is_error": False, "result": '  {"a": 1}  '})))
r = b.ask_chat("SYSTEM dài có \"nháy\" và % ký tự lạ", "USER câu hỏi", timeout=77, temperature=0.3)
c = CALLS[-1]
check("tra ve cau tra loi (da cat khoang trang)", r == '{"a": 1}' and b.last_error == "")
check("dong lenh: -p, json, model sonnet, KHONG cong cu, khong luu phien", c["cmd"][:2] == [r"C:\fake\claude.exe", "-p"]
      and c["cmd"][c["cmd"].index("--output-format") + 1] == "json" and c["cmd"][c["cmd"].index("--model") + 1] == "sonnet"
      and c["cmd"][c["cmd"].index("--tools") + 1] == "" and "--no-session-persistence" in c["cmd"] and "--strict-mcp-config" in c["cmd"])
check("loi dan he thong that + cau hoi di qua stdin (khong nam tren dong lenh)", c["stdin"].startswith("SYSTEM dài") and c["stdin"].endswith("USER câu hỏi")
      and not any("SYSTEM dài" in a or "USER câu hỏi" in a for a in c["cmd"]) and c["timeout"] == 77)
check("tien trinh con KHONG nhan ANTHROPIC_API_KEY (dung tai khoan, khong tinh tien API)", "ANTHROPIC_API_KEY" not in c["env"] and c["cwd"] == wd)
os.environ.pop("ANTHROPIC_API_KEY")
b = ab.ClaudeAccountBrain("x", mk_run(out="dong rac\n" + json.dumps({"type": "result", "is_error": True, "result": "Invalid API key · Please run /login"})))
check("cong cu bao loi dang nhap -> '' + last_error tieng Viet", b.ask_chat("s", "u") == "" and "CHƯA ĐĂNG NHẬP" in b.last_error)
b = ab.ClaudeAccountBrain("x", mk_run(out=json.dumps({"type": "result", "is_error": True, "result": "Claude usage limit reached. Resets 9pm"})))
check("het han muc goi", b.ask_text("u") == "" and "HẾT HẠN MỨC" in b.last_error)
b = ab.ClaudeAccountBrain("x", mk_run(rc=1, out="", err="Error: something broke badly"))
check("khong co JSON -> lay stderr lam ly do", b.ask_chat("s", "u") == "" and "something broke badly" in b.last_error)


def slow(*a, **k):
    raise TimeoutError("timed out after 150s")


b = ab.ClaudeAccountBrain("x", slow)
check("qua han cho", b.ask_chat("s", "u") == "" and b.last_error == "quá hạn chờ")
check("ask_text khong co loi dan he thong -> stdin chi la cau hoi",
      ab.ClaudeAccountBrain("x", mk_run(out=json.dumps({"result": "OK"}))).ask_text("Reply OK") == "OK" and CALLS[-1]["stdin"] == "Reply OK")

# ---------------------------------------------------------------- [4]
print("\n[4] ChatGPTAccountBrain")
PLAN = {"m-a": ("", "ERROR: The 'm-a' model is not supported when using Codex with a ChatGPT account."), "m-b": ("TRA LOI B", "")}


def codex_run(cmd, stdin_text="", timeout=120, env=None, cwd=None):
    CALLS.append({"cmd": list(cmd), "stdin": stdin_text, "timeout": timeout, "env": dict(env or {}), "cwd": cwd})
    model = cmd[cmd.index("-m") + 1] if "-m" in cmd else ""
    text, err = PLAN.get(model, ("", "ERROR: unknown"))
    if text:
        open(cmd[cmd.index("-o") + 1], "w", encoding="utf-8").write(text + "\n")
    return (0 if text else 1), "", "user\n" + stdin_text + "\n" + err + "\n"


os.environ["OPENAI_API_KEY"] = "sk-khong-duoc-dung"
g = ab.ChatGPTAccountBrain(r"C:\fake\codex.exe", codex_run)
n0 = len(CALLS)
r = g.ask_chat("SYS", "USER hỏi", timeout=88)
c1, c2 = CALLS[n0], CALLS[n0 + 1]
check("model dau khong dung duoc voi tai khoan -> tu thu model ke va lay cau tra loi", r == "TRA LOI B" and len(CALLS) - n0 == 2
      and c1["cmd"][c1["cmd"].index("-m") + 1] == "m-a" and c2["cmd"][c2["cmd"].index("-m") + 1] == "m-b" and g.model_name == "m-b")
check("dong lenh Codex: exec, chi doc, khong luu phien, cau hoi qua stdin", c2["cmd"][:2] == [r"C:\fake\codex.exe", "exec"]
      and c2["cmd"][c2["cmd"].index("-s") + 1] == "read-only" and "--ephemeral" in c2["cmd"] and "--skip-git-repo-check" in c2["cmd"]
      and c2["cmd"][-1] == "-" and c2["cmd"][c2["cmd"].index("-C") + 1] == wd and c2["stdin"].startswith("SYS\n\n")
      and c2["stdin"].endswith("USER hỏi") and "Do not run commands" in c2["stdin"] and c2["timeout"] == 88)
check("tien trinh con KHONG nhan OPENAI_API_KEY", "OPENAI_API_KEY" not in c2["env"])
os.environ.pop("OPENAI_API_KEY")
check("file tam cua Codex da duoc don", os.listdir(wd) == [], str(os.listdir(wd)))
n0 = len(CALLS)
check("lan sau dung luon model da chay duoc (khong thu lai model hong)", g.ask_text("lan 2") == "TRA LOI B" and len(CALLS) - n0 == 1
      and CALLS[-1]["cmd"][CALLS[-1]["cmd"].index("-m") + 1] == "m-b")
PLAN["m-a"] = ("", "ERROR: You've hit your usage limit. Upgrade to Pro or try again at 9:41 PM.")
g2 = ab.ChatGPTAccountBrain("x", codex_run)
n0 = len(CALLS)
check("het han muc -> dung ngay (khong thu model khac) + bao ro", g2.ask_chat("s", "u") == "" and "HẾT HẠN MỨC" in g2.last_error
      and len(CALLS) - n0 == 1, g2.last_error)
PLAN["m-a"] = PLAN["m-b"] = ("", "ERROR: The model is not supported when using Codex with a ChatGPT account.")
g3 = ab.ChatGPTAccountBrain("x", codex_run)
check("moi model deu khong dung duoc -> '' + ly do tieng Viet (khong lo cau hoi)", g3.ask_chat("s", "CAU HOI BI MAT") == ""
      and "MODEL đã chọn không dùng được" in g3.last_error and "CAU HOI BI MAT" not in g3.last_error)
os.remove(os.path.join(CODEX_HOME, "models_cache.json"))
PLAN[""] = ("MAC DINH", "")
g4 = ab.ChatGPTAccountBrain("x", codex_run)
check("khong co cache model -> chay voi model mac dinh cua Codex (khong truyen -m)", g4.ask_text("u") == "MAC DINH" and "-m" not in CALLS[-1]["cmd"])

# ---------------------------------------------------------------- [5]
print("\n[5] get_account_brain + BrainManager + niche_learner")
ok_claude = mk_run(out=json.dumps({"loggedIn": True, "authMethod": "claude.ai", "subscriptionType": "pro"}))
check("get_account_brain: da dang nhap -> brain dung loai", isinstance(ab.get_account_brain(ab.CLAUDE_ACCOUNT, ok_claude), ab.ClaudeAccountBrain)
      and isinstance(ab.get_account_brain(ab.CHATGPT_ACCOUNT, mk_run(out="Logged in using ChatGPT")), ab.ChatGPTAccountBrain))
try:
    ab.get_account_brain(ab.CHATGPT_ACCOUNT, mk_run(rc=1, err="Not logged in"))
    check("chua dang nhap -> AccountError", False)
except ab.AccountError as e:
    check("chua dang nhap -> AccountError co ten + ly do", str(e) == "ChatGPT tài khoản: chưa đăng nhập", str(e))
try:
    ab.get_account_brain("khong-co")
    check("ten la -> ValueError", False)
except ValueError:
    check("ten la -> ValueError", True)
_old = ab.status
ab.status = lambda name, run=None: {"installed": True, "logged_in": True, "path": "p.exe", "detail": "ok", "plan": "", "who": ""}
check("BrainManager.get_brain nhan 2 ten tai khoan", isinstance(BrainManager.get_brain("claude-account"), ab.ClaudeAccountBrain)
      and isinstance(BrainManager.get_brain("chatgpt-account"), ab.ChatGPTAccountBrain))
ab.status = _old
good = ab.ClaudeAccountBrain("x", mk_run(out=json.dumps({"result": '{"keywords": ["a b c"]}'})))
check("niche_learner.ask_long dung ask_chat cua brain tai khoan", nl.ask_long(good, "S", "U") == '{"keywords": ["a b c"]}'
      and CALLS[-1]["timeout"] == nl.AI_TIMEOUT_S and CALLS[-1]["stdin"] == "S\n\nU")
bad = ab.ClaudeAccountBrain("x", mk_run(out=json.dumps({"is_error": True, "result": "Claude usage limit reached"})))
obj, why = nl._ask_obj(bad, "S", "U")
check("_ask_obj: brain tai khoan het han muc -> (None, ly do tieng Viet)", obj is None and "HẾT HẠN MỨC" in why, why)

# ---------------------------------------------------------------- [6]
print("\n[6] Tinh")
SRC = open(os.path.join(HERE, "agent", "account_brain.py"), encoding="utf-8").read()
check("khong print (chay o luong phu / EXE cp1252)", "print(" not in SRC)
check("chi DOC ho so dang nhap Codex o 1 cho (lay email + goi); khong dung toi ma truy cap / khong ghi file do",
      SRC.count("auth.json") == 1 and "access_token" not in SRC and "refresh_token" not in SRC and ".credentials" not in SRC)
check("tim duoc file chay that tren may nay (chi kiem tra duong dan, khong chay)", all(isinstance(f(), str) for f in REAL_FIND))

print(f"\nPASS: {PASS}  FAIL: {FAIL}")
print("SMOKE v1.12.0: ALL PASS" if FAIL == 0 else "SMOKE v1.12.0: CO LOI")
sys.exit(0 if FAIL == 0 else 1)
