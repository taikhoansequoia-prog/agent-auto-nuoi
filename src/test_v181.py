# -*- coding: utf-8 -*-
"""Smoke test v1.8.1 — KHÔNG CHO 2 PROFILE CHUNG PROXY CHẠY CÙNG LÚC + THỨ TỰ NGẪU NHIÊN.

User: tick hết các kênh cần ngâm rồi chạy, nhưng các lô mail dùng chung 1 proxy không được
chạy cùng phiên. GPM trả raw_proxy (ip:port:user:pass); đo 19/11/2026: 70 profile / 31 proxy.
v1.8.1: worker giữ khóa IP proxy TRƯỚC khi lấy luồng; run_thread_pool xáo + xen kẽ theo proxy.

Chạy OFFLINE: python src\\test_v181.py  (mô phỏng run_thread_pool thật, không mở trình duyệt)
"""
import os
import random
import sys
import tempfile
import threading
import time
import types

SRC = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(SRC)
for p in (ROOT, SRC):
    if p not in sys.path:
        sys.path.insert(0, p)
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass
os.environ["GPM_BOT_DATA_DIR"] = tempfile.mkdtemp(prefix="gpm_v181_")

import src.ui_main as ui  # noqa: E402

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


print("\n== 1. proxy_key")
for raw, exp in [("103.75.72.166:38193:axdk9650:TABwcj2941", "103.75.72.166"),
                 ("14.225.1.2:6666", "14.225.1.2"),
                 ("socks5://user:pa:ss@1.2.3.4:1080", "1.2.3.4"),
                 ("http://Proxy.Example.com:8080", "proxy.example.com"),
                 ("", ""), (None, ""), ("   ", "")]:
    check(f"{raw!r} -> {exp!r}", ui.proxy_key(raw) == exp, ui.proxy_key(raw))

print("\n== 2. order_profiles_by_proxy")
pm = {}
for i in range(6):
    pm[f"A{i}"] = "10.0.0.1:1:u:p"
for i in range(3):
    pm[f"B{i}"] = "10.0.0.2:2:u:p"
pm["C0"] = "10.0.0.3:3:u:p"
pm["D0"] = "10.0.0.4:4:u:p"
pm["N0"] = ""
pm["N1"] = ""
pids = list(pm)
o = ui.order_profiles_by_proxy(pids, pm, rng=random.Random(1))
check("giữ đủ mọi profile", sorted(o) == sorted(pids))
first = [ui.proxy_key(pm[p]) for p in o[:4]]
check("đợt đầu (4 cái) không trùng IP", len(set(x for x in first if x)) == len([x for x in first if x]), str(o[:6]))
orders = {tuple(ui.order_profiles_by_proxy(pids, pm, rng=random.Random(s))) for s in range(8)}
check("thứ tự ngẫu nhiên khác nhau giữa các lần", len(orders) > 1, str(len(orders)))

print("\n== 3. Mô phỏng run_thread_pool thật (12 profile chung proxy, 4 luồng)")
LOG = []
LOG_LOCK = threading.Lock()


class FakeAPI:
    def get_proxy_map(self):
        return dict(pm)

    def get_profile_name(self, pid):
        return pid


real = (ui.BrowserFactory.get_api, ui.run_single_profile, ui._stagger_startup)
ui.BrowserFactory.get_api = staticmethod(lambda *a, **k: FakeAPI())
ui._stagger_startup = lambda *a, **k: True


def fake_run(api, pid, *a, **k):
    t0 = time.time()
    time.sleep(random.uniform(0.15, 0.35))
    with LOG_LOCK:
        LOG.append((pid, ui.proxy_key(pm.get(pid, "")), t0, time.time()))


ui.run_single_profile = fake_run


class Btn:
    def config(self, **k):
        pass


stub = types.SimpleNamespace(
    _assignment_map={}, _running=True, _active_slots=[0, 1, 2, 3],
    root=types.SimpleNamespace(after=lambda *a, **k: None),
    btn_start=Btn(), btn_stop=Btn(), cbo_brain=Btn(), cbo_phase=Btn(), cbo_browser=Btn(),
    _set_utils_state=lambda *a: None, update_tab_name=lambda *a: None)

ui.STOP_EVENT.clear()
try:
    ui.AutomationApp.run_thread_pool(stub, list(pids), [], 4, 1200, 800, False, False,
                                     ui.BROWSER_GPM, "9495")
    check("chạy đủ cả 13 profile", sorted(x[0] for x in LOG) == sorted(pids), str(len(LOG)))
    overlap = []
    for i, a in enumerate(LOG):
        for b in LOG[i + 1:]:
            if a[1] and a[1] == b[1] and a[2] < b[3] and b[2] < a[3]:
                overlap.append((a[0], b[0]))
    check("KHÔNG có 2 profile cùng IP chạy chồng nhau", not overlap, str(overlap[:3]))
    maxpar = max(sum(1 for b in LOG if b[2] <= a[2] < b[3]) for a in LOG)
    check("vẫn chạy song song nhiều proxy khác nhau", maxpar >= 2, f"tối đa {maxpar} cùng lúc")
    check("không vượt số luồng (4)", maxpar <= 4, str(maxpar))
    check("nhả hết khóa proxy sau phiên", ui._PROXY_BUSY == {}, str(ui._PROXY_BUSY))

    print("\n== 4. Bấm DỪNG khi đang chờ proxy")
    ui._PROXY_MAP.update({"X": "9.9.9.9:1:u:p", "Y": "9.9.9.9:1:u:p"})
    ui.STOP_EVENT.clear()
    check("X giữ proxy", ui._acquire_proxy("X"))
    res = {}
    th = threading.Thread(target=lambda: res.setdefault("y", ui._acquire_proxy("Y")))
    th.start()
    time.sleep(0.8)
    check("Y đang phải chờ (cùng IP với X)", th.is_alive())
    ui.STOP_EVENT.set()
    th.join(3)
    check("DỪNG -> Y thoát khỏi chờ, trả False", not th.is_alive() and res.get("y") is False, str(res))
    ui.STOP_EVENT.clear()
    ui._release_proxy("X")
    check("nhả X -> Y lấy được", ui._acquire_proxy("Y"))
    ui._release_proxy("Y")
    check("profile không proxy không bị khóa", ui._acquire_proxy("N0") is True and "" not in ui._PROXY_BUSY)
finally:
    ui.BrowserFactory.get_api, ui.run_single_profile, ui._stagger_startup = real
    ui.STOP_EVENT.clear()

print("\n== 5. Tĩnh — không phá chuỗi test_v153 ghim")
src = open(os.path.join(SRC, "ui_main.py"), encoding="utf-8").read()
check("submit giữ nguyên đuôi tham số",
      "fixed_target_s, daily_seconds, pinned_theme, keyword_lang) for pid in profiles]" in src)
check("worker giữ proxy TRƯỚC khi lấy slot",
      src.index("if not _acquire_proxy(profile_id):") < src.index("slot = slots_queue.get()"))
check("antidetect có get_proxy_map + field proxy",
      "def get_proxy_map" in open(os.path.join(SRC, "browser", "antidetect.py"), encoding="utf-8").read())

print(f"\nPASS: {PASS}   FAIL: {FAIL}")
print("SMOKE v1.8.1: ALL PASS" if FAIL == 0 else "SMOKE v1.8.1: CO LOI")
sys.exit(0 if FAIL == 0 else 1)
