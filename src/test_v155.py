# -*- coding: utf-8 -*-
"""
test_v155.py - Smoke test offline cho ban va loi "go y nguyen dau ngoac" cua bot Telegram.

BOI CANH (loi that gap khi chay live 21/10/2026):
    CMD_HELP cu in ra:  /confirm <ma> <mat_khau_moi>
    Nguoi dung copy y nguyen => go "/confirm <683145> <061099Giang@>"
    => rest.split(None, 1) tra ve "<683145>" / "<061099Giang@>"
    => secrets.compare_digest("<683145>", "683145") = False
    => "Ma khong dung. Con 2 lan thu."  (mat 1 luot trong 3)

FIX v1.5.5 (2 tang):
  1. CMD_HELP + moi cau tra loi: cum lenh khong con dau < >, chi con placeholder HOA.
  2. Helper module-level _clean_arg(): tu boc <>, "", '', [], () o tham so truyen vao.

Test nay chung minh: go y nguyen kieu CU (co ngoac) VAN chay dung,
va kieu MOI (khong ngoac) van chay dung, va ma sai van bi tu choi.

Chay: python src\\test_v155.py
Khong dung mang, khong cham DB that (GPM_BOT_DATA_DIR = thu muc tam).
"""
import os
import shutil
import sys
import tempfile
import time

TMP = tempfile.mkdtemp(prefix="gpm_v155_")
os.environ["GPM_BOT_DATA_DIR"] = TMP

SRC = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(SRC)
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

import src.api_vault as v        # noqa: E402
import src.telegram_bot as t     # noqa: E402

PASS = 0
FAIL = 0


def hr(title=""):
    print("\n" + "=" * 68)
    if title:
        print(title)
        print("=" * 68)


def chk(name, cond, extra=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"[OK]   {name} {extra}")
    else:
        FAIL += 1
        print(f"[FAIL] {name} {extra}")


def new_bot():
    """Bot offline: khong mang, khong log, http gia luon tra ok."""
    return t.TelegramPasswordBot(
        "x:y", "0",
        log=lambda m: None,
        http=lambda *a, **k: {"ok": True},
    )


def placeholder_part(line):
    """Bo phan canh bao '(khong go dau < >)' truoc khi kiem tra ngoac."""
    return line.split("(không gõ")[0]


hr("v1.5.5 - TELEGRAM BOT: FIX LOI GO Y NGUYEN DAU NGOAC < >")

# --- 0. Moi truong sach: mat khau mac dinh dang hieu luc
chk("default password active", v.check_password("gpm123") is True)

bot = new_bot()
now = time.time()

# --- 1. _clean_arg: don tung cap vo ngoac
chk("clean <abc>", t._clean_arg("<abc>") == "abc", repr(t._clean_arg("<abc>")))
chk('clean "abc"', t._clean_arg('"abc"') == "abc")
chk("clean 'abc'", t._clean_arg("'abc'") == "abc")
chk("clean [abc]", t._clean_arg("[abc]") == "abc")
chk("clean (abc)", t._clean_arg("(abc)") == "abc")
chk("clean plain", t._clean_arg("abc") == "abc")
chk("clean spaces", t._clean_arg("  abc  ") == "abc")
chk("clean only <", t._clean_arg("<") == "<")
chk("clean empty", t._clean_arg("") == "")

# --- 2. DUNG CA LOI THAT: ngoac o CA ma lan mat khau
r = bot.handle_text("/reset", now)
code = bot._reset_code
chk("reset gives 6-digit code", len(code) == 6 and code.isdigit(), code)
chk("reset reply has no '<'", "<" not in r and ">" not in r)

r_bad = bot.handle_text(f"/confirm <{code}> <Giang@061099>", now + 1)
chk("BRACKETED confirm now WORKS", "Đã đặt lại mật khẩu" in r_bad, r_bad.splitlines()[0])
chk("new password really set", v.check_password("Giang@061099") is True)
chk("old password rejected", v.check_password("gpm123") is False)

# --- 3. Kieu MOI (khong ngoac) van chay
bot2 = new_bot()
bot2.handle_text("/reset", now)
c2 = bot2._reset_code
r3 = bot2.handle_text(f"/confirm {c2} matkhaumoi2", now + 1)
chk("plain confirm works", "Đã đặt lại mật khẩu" in r3)

# --- 4. Ma sai van bi tu choi (khong noi long bao mat)
bot3 = new_bot()
bot3.handle_text("/reset", now)
r4 = bot3.handle_text("/confirm 000000 khongdung1", now + 1)
chk("wrong code rejected", "Mã không đúng" in r4, r4)

# --- 5. /set voi ngoac
bot4 = new_bot()
v.set_password("hientai1")
r5 = bot4.handle_text("/set <hientai1> <moilam2>", now)
chk("bracketed /set works", "Đã đổi mật khẩu" in r5, r5.splitlines()[0])
chk("set password applied", v.check_password("moilam2") is True)

# --- 6. Cau tra loi "Cu phap" + CMD_HELP khong con in ngoac trong cum lenh
bot5 = new_bot()
s1 = bot5.handle_text("/set onlyone", now)
s2 = bot5.handle_text("/confirm onlyone", now)

chk("set syntax has no bracket placeholder",
    "<" not in placeholder_part(s1) and ">" not in placeholder_part(s1), s1)
chk("confirm syntax has no bracket placeholder",
    "<" not in placeholder_part(s2) and ">" not in placeholder_part(s2), s2)

cmd_lines = [ln for ln in t.CMD_HELP.splitlines() if ln.strip().startswith("/")]
bad = [ln for ln in cmd_lines if "<" in ln or ">" in ln]
chk("CMD_HELP command lines bracket-free", not bad,
    f"{len(cmd_lines)} dong lenh" + (f" | BAD={bad}" if bad else ""))
chk("help mentions no-<> rule", "KHÔNG gõ dấu" in t.CMD_HELP)
chk("help has a concrete example",
    "/confirm 123456 " in t.CMD_HELP or "Ví dụ đúng" in t.CMD_HELP)

# --- 7. Chan mat khau qua ngan van hoat dong
bot6 = new_bot()
bot6.handle_text("/reset", now)
c6 = bot6._reset_code
r6 = bot6.handle_text(f"/confirm <{c6}> <ab>", now + 1)
chk("short password blocked", "phải từ" in r6, r6)

# --- 8. Ngoac rong khong lam crash
bot7 = new_bot()
r7 = bot7.handle_text("/confirm <> <>", now)
chk("empty brackets safe", isinstance(r7, str) and r7 != "")

hr("KET QUA")
shutil.rmtree(TMP, ignore_errors=True)
print(f"PASS: {PASS}   FAIL: {FAIL}")
print("SMOKE v1.5.5: ALL PASS" if FAIL == 0 else "SMOKE v1.5.5: CO LOI - XEM [FAIL] O TREN")
sys.exit(0 if FAIL == 0 else 1)
