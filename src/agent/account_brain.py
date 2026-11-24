# -*- coding: utf-8 -*-
"""v1.12.0: AI qua TÀI KHOẢN ĐĂNG NHẬP — không dùng API key, không tốn credit API.

- Claude  : Claude Code CLI  (`claude -p`)   — đăng nhập tài khoản claude.ai (gói Pro/Max).
- ChatGPT : Codex CLI        (`codex exec`)  — "Sign in with ChatGPT" (gói Plus/Pro/Team).

Cả hai là công cụ CHÍNH THỨC của Anthropic / OpenAI, có chế độ chạy 1 câu hỏi rồi thoát. Module này chỉ: tìm file chạy,
hỏi trạng thái đăng nhập, gửi câu hỏi qua stdin và đọc câu trả lời. Không đọc/ghi file đăng nhập, không in key.

Giao diện brain giống các brain khác: `ask_chat(system, user, timeout, temperature)`, `ask_text(prompt, timeout)`,
`last_error`, `model_name`. Không import Tk, không print (được gọi từ luồng phụ).
"""
import base64
import glob
import json
import os
import re
import shutil
import subprocess
import uuid

CLAUDE_ACCOUNT = "claude-account"
CHATGPT_ACCOUNT = "chatgpt-account"
ACCOUNT_LABELS = {CLAUDE_ACCOUNT: "Claude tài khoản", CHATGPT_ACCOUNT: "ChatGPT tài khoản"}

CLAUDE_MODEL = "sonnet"          # bí danh của Claude Code: luôn là Sonnet mới nhất mà gói của user được dùng
CLAUDE_MODEL_CHOICES = ["sonnet", "opus", "fable", "haiku"]      # bí danh `claude --model` nhận; gõ tên đầy đủ cũng được


def claude_model():
    """Model Claude sẽ dùng: user chọn (biến CLAUDE_CLI_MODEL, UI đặt từ config) > mặc định sonnet."""
    return (os.environ.get("CLAUDE_CLI_MODEL") or "").strip() or CLAUDE_MODEL
_NEUTRAL_SYSTEM = ("You are a careful analyst. Follow the instructions in the user's message exactly and reply with "
                   "only what is asked. Do not use tools.")
_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
_NEW_CONSOLE = getattr(subprocess, "CREATE_NEW_CONSOLE", 0)


class AccountError(RuntimeError):
    """Lỗi đã có câu tiếng Việt đọc là hiểu (chưa cài, chưa đăng nhập...)."""


# ----------------------------------------------------------------------------------------------- tìm file chạy
def _first_file(paths):
    for p in paths:
        if p and os.path.isfile(p):
            return p
    return ""


def _newest(pattern):
    hits = [p for p in glob.glob(pattern) if os.path.isfile(p)]
    hits.sort(key=lambda p: os.path.getmtime(p), reverse=True)
    return hits[0] if hits else ""


def find_claude():
    """-> đường dẫn file chạy Claude Code ('' nếu chưa cài). Ưu tiên file .exe thật (shim .cmd giới hạn 8k ký tự lệnh)."""
    home, appdata = os.path.expanduser("~"), os.environ.get("APPDATA", "")
    exe = _first_file([
        os.environ.get("CLAUDE_CLI_PATH", ""),
        os.path.join(appdata, "npm", "node_modules", "@anthropic-ai", "claude-code", "bin", "claude.exe"),
        os.path.join(home, ".local", "bin", "claude.exe"),
        shutil.which("claude.exe") or "",
    ])
    if exe:
        return exe
    w = shutil.which("claude") or ""
    if w:
        near = os.path.join(os.path.dirname(w), "node_modules", "@anthropic-ai", "claude-code", "bin", "claude.exe")
        if os.path.isfile(near):
            return near
        if not w.lower().endswith(".ps1"):
            return w
    return _newest(os.path.join(home, ".vscode", "extensions", "anthropic.claude-code-*", "resources", "native-binary",
                                "claude.exe"))


def find_codex():
    """-> đường dẫn file chạy Codex CLI ('' nếu chưa cài)."""
    home, appdata, local = os.path.expanduser("~"), os.environ.get("APPDATA", ""), os.environ.get("LOCALAPPDATA", "")
    exe = _first_file([
        os.environ.get("CODEX_CLI_PATH", ""),
        shutil.which("codex.exe") or "",
        os.path.join(local, "Programs", "OpenAI", "Codex", "bin", "codex.exe"),
    ])
    if exe:
        return exe
    w = shutil.which("codex") or ""
    if w and not w.lower().endswith(".ps1"):
        return w
    cmd = os.path.join(appdata, "npm", "codex.cmd")
    if os.path.isfile(cmd):
        return cmd
    return _newest(os.path.join(home, ".vscode", "extensions", "openai.chatgpt-*", "bin", "windows-x86_64", "codex.exe"))


# ----------------------------------------------------------------------------------------------- chạy tiến trình con
_CLAUDE_STRIP = re.compile(r"^(ANTHROPIC_.*|CLAUDECODE|CLAUDE_PID|CLAUDE_AGENT_SDK_VERSION|CLAUDE_CODE_(?!OAUTH_TOKEN$).*)$")
_CODEX_STRIP = re.compile(r"^(OPENAI_API_KEY.*|OPENAI_BASE_URL|OPENAI_ORG.*|CODEX_API_KEY)$")


def child_env(strip):
    """Môi trường cho tiến trình con, BỎ các biến API key: có ANTHROPIC_API_KEY / OPENAI_API_KEY trong môi trường thì công
    cụ sẽ tính tiền API thay vì dùng tài khoản đăng nhập — đúng điều user không muốn."""
    env = {k: v for k, v in os.environ.items() if not strip.match(k.upper())}
    env["NO_COLOR"] = "1"
    return env


def work_dir():
    """Thư mục RỖNG làm chỗ đứng cho công cụ (để nó không đọc CLAUDE.md / AGENTS.md / mã nguồn nào). Nằm trong data của app."""
    try:
        from src.paths import data_dir
        base = data_dir()
    except Exception:
        base = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
    d = os.path.join(base, "ai_account_work")
    os.makedirs(d, exist_ok=True)
    return d


def _kill_tree(proc):
    try:
        subprocess.run(["taskkill", "/T", "/F", "/PID", str(proc.pid)], capture_output=True, timeout=15,
                       creationflags=_NO_WINDOW)
    except Exception:
        try:
            proc.kill()
        except Exception:
            pass


def run_cli(cmd, stdin_text="", timeout=120, env=None, cwd=None):
    """-> (mã thoát, stdout, stderr). Quá hạn -> diệt cả cây tiến trình rồi ném TimeoutError."""
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            env=env, cwd=cwd, creationflags=_NO_WINDOW)
    try:
        out, err = proc.communicate((stdin_text or "").encode("utf-8"), timeout=timeout)
    except subprocess.TimeoutExpired:
        _kill_tree(proc)
        try:
            proc.communicate(timeout=5)
        except Exception:
            pass
        raise TimeoutError(f"timed out after {int(timeout)}s")
    return proc.returncode, out.decode("utf-8", "replace"), err.decode("utf-8", "replace")


# ----------------------------------------------------------------------------------------------- trạng thái đăng nhập
def mask_email(email):
    m = re.match(r"^([^@]{1,2})[^@]*(@.+)$", str(email or "").strip())
    return f"{m.group(1)}***{m.group(2)}" if m else ""


def claude_status(run=run_cli):
    """-> {installed, logged_in, plan, who, path, detail}. `detail` = câu tiếng Việt cho người dùng."""
    exe = find_claude()
    st = {"installed": bool(exe), "logged_in": False, "plan": "", "who": "", "path": exe, "detail": ""}
    if not exe:
        st["detail"] = "chưa cài Claude Code"
        return st
    try:
        rc, out, err = run([exe, "auth", "status"], timeout=30, env=child_env(_CLAUDE_STRIP), cwd=work_dir())
    except Exception as e:
        st["detail"] = f"không hỏi được trạng thái ({str(e)[:80]})"
        return st
    try:
        info = json.loads(out[out.index("{"):out.rindex("}") + 1])
    except Exception:
        info = {}
    if info.get("loggedIn") and str(info.get("authMethod", "")).lower() in ("claude.ai", "oauth", "oauth_token"):
        st.update(logged_in=True, plan=str(info.get("subscriptionType") or ""), who=str(info.get("email") or "").strip())      # v1.13.1: user muốn thấy ĐẦY ĐỦ email để biết đang dùng tài khoản nào
        st["detail"] = "đã đăng nhập" + (f" · gói {st['plan']}" if st["plan"] else "") + (f" · {st['who']}" if st["who"] else "")
    elif info.get("loggedIn"):
        st["detail"] = "đang dùng API key chứ KHÔNG phải tài khoản — bấm Đăng nhập để chuyển sang tài khoản claude.ai"
    else:
        st["detail"] = "chưa đăng nhập"
    return st


def codex_status(run=run_cli):
    exe = find_codex()
    st = {"installed": bool(exe), "logged_in": False, "plan": "", "who": "", "path": exe, "detail": ""}
    if not exe:
        st["detail"] = "chưa cài Codex (công cụ của ChatGPT)"
        return st
    try:
        rc, out, err = run([exe, "login", "status"], timeout=30, env=child_env(_CODEX_STRIP), cwd=work_dir())
    except Exception as e:
        st["detail"] = f"không hỏi được trạng thái ({str(e)[:80]})"
        return st
    low = (out + " " + err).lower()
    if "logged in using chatgpt" in low:
        who, plan = codex_account_info()
        st.update(logged_in=True, who=who, plan=plan,
                  detail="đã đăng nhập bằng tài khoản ChatGPT" + (f" · gói {plan}" if plan else "") + (f" · {who}" if who else ""))
    elif "logged in" in low and "not logged in" not in low:
        st["detail"] = "đang dùng API key chứ KHÔNG phải tài khoản — bấm Đăng nhập để chuyển sang tài khoản ChatGPT"
    else:
        st["detail"] = "chưa đăng nhập"
    return st


def status(name, run=run_cli):
    return claude_status(run) if name == CLAUDE_ACCOUNT else codex_status(run)


def login_command(name):
    """-> danh sách lệnh mở màn hình đăng nhập (trình duyệt) của công cụ; [] nếu chưa cài."""
    if name == CLAUDE_ACCOUNT:
        exe = find_claude()
        return [exe, "auth", "login"] if exe else []
    exe = find_codex()
    return [exe, "login"] if exe else []


def open_login(name):
    """Mở 1 cửa sổ dòng lệnh chạy lệnh đăng nhập (công cụ tự mở trình duyệt). -> True nếu mở được."""
    cmd = login_command(name)
    if not cmd:
        return False
    env = child_env(_CLAUDE_STRIP if name == CLAUDE_ACCOUNT else _CODEX_STRIP)
    env.pop("NO_COLOR", None)
    subprocess.Popen(cmd, env=env, cwd=work_dir(), creationflags=_NEW_CONSOLE)
    return True


def explain_account_error(text):
    """Lỗi thô của công cụ -> câu ngắn tiếng Việt ('' nếu không nhận ra)."""
    low = str(text or "").lower()
    if not low.strip():
        return ""
    if "model" in low and any(x in low for x in ("not supported", "not found", "does not exist", "may not exist", "invalid model",
                                                 "not available", "do not have access")):
        return "MODEL đã chọn không dùng được với tài khoản này — chọn model khác ở 'Tài khoản AI…'"
    if "/login" in low or "not logged in" in low or "please log in" in low or "login required" in low \
            or "authentication_error" in low or "oauth token" in low or "401" in low or "unauthorized" in low:
        return "CHƯA ĐĂNG NHẬP hoặc phiên đăng nhập đã hết hạn — bấm 'Tài khoản AI…' để đăng nhập lại"
    if "usage limit" in low or "limit reached" in low or "hit your" in low or "rate limit" in low or "429" in low \
            or "quota" in low or "too many requests" in low:
        return "HẾT HẠN MỨC của gói tài khoản (chờ tới giờ đặt lại rồi chạy lại)"
    if "timed out" in low or "timeout" in low:
        return "quá hạn chờ"
    return ""


# ----------------------------------------------------------------------------------------------- brain
class _AccountBrain:
    name = ""
    label = ""
    model_name = ""
    supports_images = True      # v1.16.0: gửi kèm được ảnh (đã thử thật 24/11 với cả Claude Code lẫn Codex)

    def __init__(self, exe, run=run_cli):
        self.exe, self._run, self.last_error = exe, run, ""

    def _ask(self, system, user, timeout, images=None):
        raise NotImplementedError

    def ask_chat(self, system, user, timeout=150, temperature=None, images=None):
        """-> câu trả lời ('' khi lỗi, lý do nằm ở last_error). `temperature` bị bỏ qua (công cụ không cho chỉnh).
        `images` = danh sách đường dẫn ảnh (jpg/png) gửi kèm; file không tồn tại thì bỏ qua."""
        self.last_error = ""
        imgs = [str(x) for x in (images or []) if x and os.path.isfile(str(x))]
        try:
            if imgs:
                return (self._ask(str(system or ""), str(user or ""), timeout, images=imgs) or "").strip()
            return (self._ask(str(system or ""), str(user or ""), timeout) or "").strip()
        except Exception as e:
            raw = str(e)
            self.last_error = explain_account_error(raw) or raw.strip().replace("\n", " ")[:300] or type(e).__name__
            return ""

    def ask_text(self, prompt, timeout=90):
        return self.ask_chat("", prompt, timeout=timeout)


class ClaudeAccountBrain(_AccountBrain):
    name, label, model_name = CLAUDE_ACCOUNT, ACCOUNT_LABELS[CLAUDE_ACCOUNT], CLAUDE_MODEL

    def __init__(self, exe, run=run_cli):
        super().__init__(exe, run)
        self.model_name = claude_model()

    def _ask(self, system, user, timeout, images=None):
        # Lời dặn hệ thống thật đi cùng câu hỏi qua stdin (dài bao nhiêu cũng được, không vướng ký tự lạ trên dòng lệnh);
        # --system-prompt chỉ để THAY lời dặn "trợ lý lập trình" mặc định của Claude Code. --tools "" = không công cụ nào.
        cmd = [self.exe, "-p", "--output-format", "json", "--model", self.model_name, "--system-prompt", _NEUTRAL_SYSTEM,
               "--tools", "", "--no-session-persistence", "--disable-slash-commands", "--strict-mcp-config"]
        prompt = (system + "\n\n" + user) if system else user
        if images:
            # v1.16.0: có ảnh -> gửi 1 tin nhắn dạng stream-json (ảnh base64 + câu hỏi); kết quả là dòng {"type":"result"} cuối.
            cmd[cmd.index("json")] = "stream-json"
            cmd += ["--input-format", "stream-json", "--verbose"]
            blocks = []
            for path in images:
                with open(path, "rb") as f:
                    data = base64.b64encode(f.read()).decode("ascii")
                kind = "image/png" if str(path).lower().endswith(".png") else "image/jpeg"
                blocks.append({"type": "image", "source": {"type": "base64", "media_type": kind, "data": data}})
            blocks.append({"type": "text", "text": prompt})
            prompt = json.dumps({"type": "user", "message": {"role": "user", "content": blocks}}, ensure_ascii=False) + "\n"
        rc, out, err = self._run(cmd, prompt, timeout=timeout, env=child_env(_CLAUDE_STRIP), cwd=work_dir())
        obj = None
        for line in reversed([x for x in out.splitlines() if x.strip().startswith("{")] or [out.strip()]):
            try:
                obj = json.loads(line)
            except Exception:
                continue
            if not images or (isinstance(obj, dict) and obj.get("type") == "result"):
                break
            obj = None
        if isinstance(obj, dict) and "result" in obj:
            if obj.get("is_error"):
                raise RuntimeError(str(obj.get("result") or obj.get("subtype") or "lỗi không rõ"))
            return str(obj.get("result") or "")
        raise RuntimeError((err.strip() or out.strip() or f"claude thoát với mã {rc}")[-600:])


def codex_models():
    """-> model mà TÀI KHOẢN ChatGPT này dùng được trong Codex, cái Codex xếp đầu đứng trước (đọc models_cache.json do chính
    Codex ghi). Model đặt trong config.toml của user có thể là model chỉ dành cho API key -> không tin vào mặc định đó."""
    forced = (os.environ.get("CODEX_CLI_MODEL") or "").strip()
    return [forced] if forced else codex_listed_models()


def _codex_home():
    return os.environ.get("CODEX_HOME") or os.path.join(os.path.expanduser("~"), ".codex")


def codex_account_info():
    """-> (email, tên gói) của tài khoản ChatGPT đang đăng nhập Codex (v1.13.1: email đầy đủ theo yêu cầu của user). `codex login status` không in email, nên đọc phần
    HỒ SƠ (claim) của id_token trong hồ sơ đăng nhập Codex. Chỉ lấy email + gói; KHÔNG trả về / ghi lại mã đăng nhập nào.
    Lỗi -> ('', '')."""
    try:
        with open(os.path.join(_codex_home(), "auth.json"), encoding="utf-8") as f:
            part = str((json.load(f).get("tokens") or {}).get("id_token") or "").split(".")[1]
        claims = json.loads(base64.urlsafe_b64decode(part + "=" * (-len(part) % 4)))
        plan = str((claims.get("https://api.openai.com/auth") or {}).get("chatgpt_plan_type") or "")
        return str(claims.get("email") or "").strip(), plan
    except Exception:
        return "", ""


def codex_listed_models():
    """-> model Codex liệt kê cho tài khoản này, cái Codex xếp đầu đứng trước (không xét CODEX_CLI_MODEL)."""
    home = _codex_home()
    try:
        with open(os.path.join(home, "models_cache.json"), encoding="utf-8") as f:
            models = json.load(f).get("models") or []
    except Exception:
        return []
    rows = [m for m in models if isinstance(m, dict) and m.get("slug") and str(m.get("visibility", "list")) == "list"]
    rows.sort(key=lambda m: m.get("priority") if isinstance(m.get("priority"), (int, float)) else 999)
    return [str(m["slug"]) for m in rows]


def _codex_error(out, err):
    """Codex in lại cả câu hỏi ra stderr -> chỉ lấy dòng lỗi thật."""
    lines = [x.strip() for x in (str(out) + "\n" + str(err)).splitlines() if x.strip()]
    errs = [x for x in lines if x.upper().startswith("ERROR")]
    return (errs[-1] if errs else " ".join(lines[-3:]))[-400:]


class ChatGPTAccountBrain(_AccountBrain):
    name, label, model_name = CHATGPT_ACCOUNT, ACCOUNT_LABELS[CHATGPT_ACCOUNT], ""

    def _ask(self, system, user, timeout, images=None):
        wd = work_dir()
        pics = []
        for path in images or []:           # v1.16.0: ảnh gửi kèm (-i). Đặt TRƯỚC các tham số khác: -i nhận nhiều giá trị.
            pics += ["-i", str(path)]
        head = (system + "\n\n") if system else ""
        prompt = (head + "Answer directly from the information below. Do not run commands, do not read or write files.\n\n"
                  + user)
        models = ([self.model_name] if self.model_name else codex_models()) or [""]     # "" = mặc định trong config của user
        last = ""
        for model in models[:4]:
            out_file = os.path.join(wd, f"codex_{uuid.uuid4().hex}.txt")
            # read-only: Codex là công cụ tự hành, không cho nó ghi/chạy gì; --ephemeral: không lưu phiên; -o: chỉ lấy câu cuối.
            cmd = [self.exe, "exec", "--skip-git-repo-check", "--ephemeral", "-s", "read-only", "--color", "never",
                   "-c", "model_reasoning_effort=medium"] + pics + (["-m", model] if model else []) \
                + ["-C", wd, "-o", out_file, "-"]
            try:
                rc, out, err = self._run(cmd, prompt, timeout=timeout, env=child_env(_CODEX_STRIP), cwd=wd)
                text = ""
                if os.path.isfile(out_file):
                    with open(out_file, encoding="utf-8", errors="replace") as f:
                        text = f.read().strip()
            finally:
                try:
                    os.remove(out_file)
                except OSError:
                    pass
            if text:
                self.model_name = model
                return text
            last = _codex_error(out, err) or f"codex thoát với mã {rc}"
            if "not supported" not in last.lower() and "model" not in last.lower():
                break                                   # lỗi không phải do model -> thử model khác cũng vô ích
        raise RuntimeError(last)


def get_account_brain(name, run=run_cli):
    """-> brain đã sẵn sàng. Chưa cài / chưa đăng nhập -> AccountError kèm câu hướng dẫn."""
    if name not in ACCOUNT_LABELS:
        raise ValueError(f"không có AI tài khoản tên '{name}'")
    st = status(name, run)
    if not st["installed"] or not st["logged_in"]:
        raise AccountError(f"{ACCOUNT_LABELS[name]}: {st['detail']}")
    return (ClaudeAccountBrain if name == CLAUDE_ACCOUNT else ChatGPTAccountBrain)(st["path"], run)
