"""Test THẬT v1.2.6 — wiring status/duration_s/error vào activity_history, end-to-end qua CDP.

4 scenario verify bằng cách đọc thẳng DB (data/agent_logs.db):
  A. Action thành công (run_random_session, action stub ok)  -> row status='ok', duration_s>=0, error NULL.
  B. Action thất bại (action stub raise)                    -> exception LAN lên caller (hành vi cũ),
                                                               row status='error', error chứa message.
  C. _watch_single_video_logic thành công (page stub)       -> row watch_video status='ok', duration_s ghi, title đúng.
  D. _watch_single_video_logic lỗi giữa chừng (page stub)   -> row watch_video status='error', error ghi, KHÔNG double-row.

Dùng page THẬT (context.new_page) cho A/B để page.url là URL thật -> _derive_platform chạy đúng.
C/D dùng stub page (không xem video thật 3 phút — test có chủ đích cho phần GHI LOG).

Cách chạy:  python test_v126.py [profile_id]
Mặc định:  589ce4a3... ("Profile ngâm 10", Chrome, locale vi).
Xử lý profile ĐÃ MỞ SẴN (resolve ws qua remote_debugging_port, chỉ detach).
"""
import sys
import os
import time
import sqlite3

import requests

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../')))

from src.browser.antidetect import AntidetectAPI
from src.browser.playwright_core import BrowserController
from src.database.db_handler import DatabaseHandler
from src.workflow.warmup import WarmupWorkflow

PROFILE_ID = sys.argv[1] if len(sys.argv) > 1 else "589ce4a3-9143-4f40-89d7-b43f61365e2e"
# v1.3.0: DB đường dẫn thống nhất qua src.paths (repo-root data/, không phụ thuộc cwd)
from src.paths import db_path as _db_path
DB_PATH = _db_path()
THEME = {"google_query": "du lich viet nam", "youtube_query": "travel vlog japan"}


def resolve_ws(api, profile_id):
    url = f"{api.base_url}/api/v1/profiles/start/{profile_id}"
    try:
        r = requests.get(url, timeout=10).json()
    except Exception as e:
        print(f"[-] API start loi: {e}")
        return None, False
    d = (r.get("data") or {})
    ws = d.get("websocket_debugging_url") or ""
    if ws:
        return ws, False
    port = d.get("remote_debugging_port")
    if port:
        try:
            v = requests.get(f"http://localhost:{port}/json/version", timeout=5).json()
            ws = v.get("webSocketDebuggerUrl")
            if ws:
                print(f"[+] Profile da mo san -> ws tu port {port}")
                return ws, True
        except Exception:
            pass
    print("[-] Khong lay duoc ws:", str(r)[:200])
    return None, False


def last_row(action):
    """Row mới nhất của action (bất kỳ profile) — đọc thẳng DB để không phụ thuộc API."""
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    try:
        r = con.execute(
            "SELECT * FROM activity_history WHERE action=? ORDER BY id DESC LIMIT 1",
            (action,)).fetchone()
        return dict(r) if r else None
    finally:
        con.close()


class StubLocator:
    def __init__(self, text=None, fail=False):
        self._text = text
        self._fail = fail
    def count(self):
        return 0
    def inner_text(self, **k):
        if self._fail:
            raise RuntimeError("no player element")
        return self._text
    def is_visible(self, **k):
        return False
    def first(self):
        return self
    def all(self):
        return []


class StubPageVideoOK:
    url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
    def wait_for_load_state(self, *a, **k): pass
    def locator(self, sel, **k): return StubLocator(text="0:12")
    def title(self): return "Test Video Title - YouTube"
    def evaluate(self, *a, **k): return None


class StubPageVideoErr:
    url = "https://www.youtube.com/watch?v=broken"
    def wait_for_load_state(self, *a, **k): pass
    def locator(self, sel, **k): return StubLocator(fail=True)
    def title(self): return ""


def make_warmup(context, db):
    w = WarmupWorkflow(
        context=context, db_handler=db, profile_id=PROFILE_ID,
        session_theme=dict(THEME), skip_youtube=False, brain=None, phase="youtube",
    )
    w.random_sleep = lambda *a, **k: None
    w._random_youtube_actions = lambda *a, **k: None
    w._check_and_skip_ad = lambda *a, **k: None
    return w


def main():
    print("=" * 70)
    print("TEST THẬT v1.2.6 — status/duration_s/error landing DB (CDP)")
    print(f"Profile GPM: {PROFILE_ID}")
    print("=" * 70)

    db = DatabaseHandler()
    api = AntidetectAPI()
    controller = None
    was_open = False
    results = {}
    try:
        print("\n[1] GPM mở trình duyệt...")
        ws_url, was_open = resolve_ws(api, PROFILE_ID)
        if not ws_url:
            print("[-] Không mở được profile. Kiểm tra GPM đang chạy + Profile ID đúng.")
            return
        print("\n[2] Kết nối Playwright qua CDP...")
        controller = BrowserController(ws_url)
        if not controller.connect():
            print("[-] Kết nối Playwright thất bại.")
            return
        context = controller.browser.contexts[0]

        # ---------- A: action OK qua run_random_session (page thật) ----------
        print("\n[3] A) run_random_session với action thành công (stub nhanh)...")
        w = make_warmup(context, db)
        import random as _r
        orig_choices, orig_uniform = _r.choices, _r.uniform
        _r.choices = lambda names, weights, k: ["action_read_news"]
        _r.uniform = lambda a, b: 0.0  # nghỉ giữa action = 0s cho nhanh
        page_holder = {}
        orig_new_page = context.new_page
        def spy_new_page(*a, **k):
            p = orig_new_page(*a, **k)
            page_holder["p"] = p
            return p
        context.new_page = spy_new_page
        w.action_read_news = lambda p: (p.goto("https://vnexpress.net", timeout=30000, wait_until="domcontentloaded"),
                                        print("      (stub) action ok"))
        try:
            w.run_random_session(total_actions=1)
        finally:
            context.new_page = orig_new_page
            _r.choices, _r.uniform = orig_choices, orig_uniform
        row = last_row("action_read_news")
        okA = bool(row) and row["status"] == "ok" and row["duration_s"] is not None and row["duration_s"] >= 0 \
              and row["error"] is None and row["profile_id"] == PROFILE_ID
        print(f"    row: {row}")
        print(f"    A status=ok + duration_s + error NULL + đúng pid: {okA}")
        results["A"] = okA

        # ---------- B: action FAIL qua run_random_session ----------
        print("\n[4] B) run_random_session với action raise exception...")
        w = make_warmup(context, db)
        _r.choices = lambda names, weights, k: ["action_read_news"]
        _r.uniform = lambda a, b: 0.0
        def bad_act(p):
            raise RuntimeError("E2E forced failure v126")
        w.action_read_news = bad_act
        raised = False
        try:
            w.run_random_session(total_actions=1)
        except RuntimeError as e:
            raised = "E2E forced failure v126" in str(e)
        finally:
            _r.choices, _r.uniform = orig_choices, orig_uniform
        row = last_row("action_read_news")
        okB = raised and bool(row) and row["status"] == "error" and row["error"] == "E2E forced failure v126" \
              and row["duration_s"] is not None
        print(f"    exception lan len caller (hành vi cũ giữ nguyên): {raised}")
        print(f"    row: {row}")
        results["B"] = okB

        # ---------- C: video OK (stub page) ----------
        print("\n[5] C) _watch_single_video_logic thành công (page stub, duration 12s)...")
        w = make_warmup(context, db)
        w._watch_single_video_logic(StubPageVideoOK(), videos_remaining_to_watch=1)
        row = last_row("watch_video")
        okC = bool(row) and row["status"] == "ok" and row["duration_s"] is not None \
              and row["error"] is None and row["platform"] == "YouTube" \
              and row["title"] == "Test Video Title"
        print(f"    row: {row}")
        results["C"] = okC

        # ---------- D: video FAIL giữa chừng (stub page) ----------
        print("\n[6] D) _watch_single_video_logic lỗi locator -> row error, không double...")
        w = make_warmup(context, db)
        import src.workflow.warmup as wm
        orig_randint = _r.randint
        _r.randint = lambda a, b: 1  # sleep 1s ở except-block
        try:
            w._watch_single_video_logic(StubPageVideoErr(), videos_remaining_to_watch=1)
        finally:
            _r.randint = orig_randint
        rows = sqlite3.connect(DB_PATH).execute(
            "SELECT id,status,error,duration_s,title FROM activity_history WHERE action='watch_video' ORDER BY id DESC LIMIT 2"
        ).fetchall()
        row = last_row("watch_video")
        okD = bool(row) and row["status"] == "error" and row["error"] == "no player element" \
              and row["duration_s"] is not None and row["title"] == ""
        print(f"    2 row watch_video gần nhất: {rows}")
        print(f"    D status=error + error text + duration + title trống: {okD}")
        results["D"] = okD

        print("\n" + "=" * 70)
        allok = all(results.values())
        print("[+] KET LUAN: v1.2.6 PASS — 4/4 scenario (ok/error action, ok/error video) ghi đúng cột mới"
              if allok else f"[-] KET LUAN: CO VAN DE — {results}")
        print("=" * 70)
    except KeyboardInterrupt:
        print("\n[!] Ctrl+C - dừng test.")
    except Exception as e:
        print(f"\n[-] Lỗi trong quá trình test: {e}")
        import traceback
        traceback.print_exc()
    finally:
        print("\n[7] Dọn dẹp...")
        try:
            if controller:
                controller.close()
            if not was_open:
                api.close_profile(PROFILE_ID)
                print("[*] Đã đóng profile GPM.")
            else:
                print("[*] Profile vốn đã mở sẵn -> chỉ detach.")
        except Exception as e:
            print(f"[-] Lỗi dọn dẹp: {e}")


if __name__ == "__main__":
    main()
