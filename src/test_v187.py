# -*- coding: utf-8 -*-
"""Smoke test v1.8.7 — ĐỌC BÁO NGẪU NHIÊN THEO PHIÊN (không phải phiên nào cũng đọc, không đọc dồn).

Mô phỏng THẬT run_random_session (thay hành động bằng hàm giả, nghỉ = 0) rồi đếm số lượt đọc báo mỗi phiên.
Chạy OFFLINE: python src\\test_v187.py
"""
import contextlib
import io
import os
import random
import sys
import tempfile
from collections import Counter

SRC = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(SRC)
for p in (ROOT, SRC):
    if p not in sys.path:
        sys.path.insert(0, p)
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass
os.environ["GPM_BOT_DATA_DIR"] = tempfile.mkdtemp(prefix="gpm_v187_")

import src.workflow.warmup as W  # noqa: E402

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


class FakePage:
    url = "about:blank"

    def close(self):
        pass


class Ctx:
    def on(self, *a, **k):
        return None

    def new_page(self):
        return FakePage()


ACTIONS = ["action_read_news", "action_read_world_news", "action_search_and_read_news", "action_search_weather",
           "action_google_finance", "action_watch_tiktok", "action_read_wikipedia", "action_search_maps",
           "action_watch_video", "action_search_youtube", "action_manage_google_alerts", "action_interact_reddit"]
NEWS = {"action_read_news", "action_read_world_news"}
W._sample_action_rest = lambda *a, **k: 0


def run_session(phase, seed, n_actions=8):
    random.seed(seed)
    wf = W.WarmupWorkflow(context=Ctx(), phase=phase, keyword_lang="en")
    wf.rng = random.Random(seed)
    wf.session_deadline_s = 3600
    wf.enable_virtual_cursor = lambda page: None
    ran = []
    for a in ACTIONS:
        setattr(wf, a, (lambda name: (lambda page: ran.append(name)))(a))
    with contextlib.redirect_stdout(io.StringIO()) as out:
        wf.run_random_session(total_actions=n_actions)
    return ran, out.getvalue()


print("\n== 1. Hạn mức đọc báo bốc ngẫu nhiên theo phiên")
wf = W.WarmupWorkflow(context=Ctx())
wf.rng = random.Random(1)
caps = Counter(wf._roll_news_cap() for _ in range(5000))
check("chỉ 0/1/2 lượt", set(caps) == {0, 1, 2}, str(dict(caps)))
check("~35% phiên không đọc báo", 0.31 <= caps[0] / 5000 <= 0.39, f"{caps[0] / 50:.1f}%")
check("~15% phiên đọc 2 lượt", 0.12 <= caps[2] / 5000 <= 0.18, f"{caps[2] / 50:.1f}%")

print("\n== 2. Mô phỏng 300 phiên x 8 hành động mỗi pha (đường chạy thật run_random_session)")
for phase in ("clean", "mail", "youtube"):
    per = Counter()
    worst_dup = 0
    logs_ok = True
    for sd in range(300):
        ran, log = run_session(phase, sd)
        n = sum(1 for a in ran if a in NEWS)
        per[n] += 1
        if n == 0 and "Phiên này KHÔNG đọc báo" not in log and "[Báo] Phiên này đọc báo tối đa" in log:
            pass
        if "[Báo] Phiên này" not in log:
            logs_ok = False
    check(f"{phase}: không phiên nào đọc báo quá 2 lượt", max(per) <= 2, str(dict(sorted(per.items()))))
    check(f"{phase}: có phiên KHÔNG đọc báo nào", per[0] >= 60, str(per[0]))
    check(f"{phase}: có phiên đọc 1 và 2 lượt", per[1] > 0 and per[2] > 0)
    check(f"{phase}: log báo hạn mức báo ở đầu phiên", logs_ok)

print("\n== 3. Báo quốc tế không lặp lại cùng báo trong 1 phiên")
wf = W.WarmupWorkflow(context=Ctx(), keyword_lang="en")
picked = []


class Stop(Exception):
    pass


def nav(page, kw, dom):
    picked.append(dom)
    raise Stop()


wf._navigate_via_google = nav
wf.DIRECT_VISIT_P = 0.0
ok = True
for trial in range(200):
    wf._world_news_seen = set()
    picked.clear()
    with contextlib.redirect_stdout(io.StringIO()):
        for _ in range(3):
            wf.action_read_world_news(object())
    if len(set(picked)) != 3:
        ok = False
check("3 lượt liền trong 1 phiên -> 3 báo khác nhau", ok)
src = open(os.path.join(SRC, "workflow", "warmup.py"), encoding="utf-8").read()
i = src.index("def run_random_session")
check("đầu phiên reset danh sách báo đã đọc", "self._world_news_seen = set()" in src[i:i + 9000])

print(f"\nPASS: {PASS}   FAIL: {FAIL}")
print("SMOKE v1.8.7: ALL PASS" if FAIL == 0 else "SMOKE v1.8.7: CO LOI")
sys.exit(0 if FAIL == 0 else 1)
