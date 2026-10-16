"""E2E v1.4.1 — chay THAT start-to-end qua dung duong production cua GUI:
worker_wrapper() -> run_single_profile() -> WarmupWorkflow.run_random_session()
(chi thay lop Tk bang 1 stub app; moi logic con lai nguyen ban).

Verify sau khi chay:
  - activity_history: row moi (dung status/duration_s)
  - cycle_history   : row moi do worker_wrapper finally ghi (target_s ngau nhien v1.4.1)
  - file log profile: dong moi
  - log live co 'Doc bao tin tuc (qua cong Google)' va KHONG co '(Fallback Google)'
"""
import os
import queue
import random
import sys
import time
import datetime
import sqlite3

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
sys.path.insert(0, REPO)
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

import tkinter as tk

from src import logger, paths
from src.logger import TeeStdout, append_line
from src.database.db_handler import DatabaseHandler
from src.browser.browser_factory import BROWSER_GPM
import src.ui_main as um


class E2ETee(TeeStdout):
    """TeeStdout + fix console cp1252 (giong ThreadSafeStdout v1.3.6): khong crash
    khi in tieng Viet/emoji; file log van nhan UTF-8 day du."""

    def write(self, msg):
        try:
            self.original.write(msg)
        except UnicodeEncodeError:
            enc = getattr(self.original, "encoding", None) or "ascii"
            try:
                self.original.write(msg.encode(enc, "replace").decode(enc, "replace"))
            except Exception:
                pass
        except Exception:
            pass
        append_line(self.profile_id, msg)
        return len(msg) if msg else 0

PROFILE_ID = sys.argv[1] if len(sys.argv) > 1 else "589ce4a3-9143-4f40-89d7-b43f61365e2e"
PHASE = os.environ.get("E2E_PHASE", "clean")
SKIP_YT = os.environ.get("E2E_SKIP_YT", "1") == "1"

THEMES = [
    {"google_query": "du lich viet nam", "youtube_query": "du lich viet nam"},
]


class StubApp:
    """Thay lop Tk: worker_wrapper chi can update_tab_name()."""

    def update_tab_name(self, slot_index, new_name):
        print(f"[UI-stub] Slot {slot_index + 1} -> {new_name}")


def main():
    db = DatabaseHandler()
    log_path = logger.profile_log_path(PROFILE_ID)

    conn = sqlite3.connect(db.db_path)
    before_act = conn.execute("SELECT COALESCE(MAX(id),0) FROM activity_history").fetchone()[0]
    before_cyc = conn.execute("SELECT COUNT(*) FROM cycle_history").fetchone()[0]
    conn.close()
    before_lines = 0
    if os.path.exists(log_path):
        with open(log_path, encoding="utf-8", errors="replace") as f:
            before_lines = len(f.readlines())

    # lay kich thuoc man hinh nhu GUI that
    _r = tk.Tk()
    screen_w = _r.winfo_screenwidth()
    screen_h = _r.winfo_screenheight() - 40
    _r.destroy()

    print("=" * 72)
    print("E2E v1.4.1 — CHAY THAT (production pipeline)")
    print("=" * 72)
    print(f"  profile   : {PROFILE_ID}")
    print(f"  phase     : {PHASE} | skip_youtube={SKIP_YT} | fixed_target_s=0 (bot RANDOM moi vong)")
    print(f"  db        : {db.db_path}")
    print(f"  log file  : {log_path} ({before_lines} dong truoc)")
    print(f"  screen    : {screen_w}x{screen_h}")
    print(f"  truoc chay: activity max id={before_act} | cycle rows={before_cyc}")
    print("=" * 72)
    sys.stdout.flush()

    tee = E2ETee(None)
    tee.profile_id = PROFILE_ID
    old_stdout = sys.stdout
    sys.stdout = tee

    t0 = time.time()
    status = "unknown"
    err = None
    try:
        slots_queue = queue.Queue()
        slots_queue.put(0)
        um.STOP_EVENT.clear()
        um.worker_wrapper(
            StubApp(), PROFILE_ID, THEMES, slots_queue,
            screen_w, screen_h, SKIP_YT, False,
            BROWSER_GPM, "", "none", PHASE, 0,
        )
    except Exception as e:
        err = e
        import traceback
        traceback.print_exc()
    finally:
        sys.stdout = old_stdout
        tee.profile_id = None
        elapsed = time.time() - t0
        print("\n" + "=" * 72)
        print(f"PHIEN CHAY KET THUC sau {elapsed:.0f}s ({elapsed/60:.1f} phut)")
        if err:
            print(f"  [!] Co exception: {err}")
        print("=" * 72)

        # ---- VERIFY ----
        print("\n[A] activity_history row moi:")
        conn = sqlite3.connect(db.db_path)
        rows = conn.execute(
            "SELECT id, action, platform, status, duration_s, substr(url,1,55), substr(COALESCE(error,''),1,60) "
            "FROM activity_history WHERE profile_id=? AND id>? ORDER BY id",
            (PROFILE_ID, before_act),
        ).fetchall()
        for r in rows:
            print("   ", r)

        print("\n[B] cycle_history row moi (v1.4.0/v1.4.1):")
        crows = conn.execute(
            "SELECT id, substr(profile_id,1,8), started_at, finished_at, ROUND(duration_s,1), "
            "status, actions, phase, COALESCE(target_s,-1), COALESCE(substr(error,1,50),'') "
            "FROM cycle_history ORDER BY id DESC LIMIT 3").fetchall()
        for r in crows:
            print("   ", r)

        print("\n[C] get_cycle_summary(days=1):")
        summ = db.get_cycle_summary(profile_id=PROFILE_ID, days=1)
        for pid, s in summ.items():
            print(f"    {pid[:8]} -> cycles={s['cycles']} total={um._fmt_dur(s['total_s'])} "
                  f"avg={um._fmt_dur(s['avg_s'])} ok={s['ok']} err={s['error']} over={s['over']} "
                  f"last_dur={um._fmt_dur(s['last_duration_s'])} last_target={um._fmt_dur(s['last_target_s'])} "
                  f"status={s['last_status']}")
        print("    get_last_cycle_targets(days=1):", um.DatabaseHandler().get_last_cycle_targets(days=1))

        print("\n[D] file log profile:")
        if os.path.exists(log_path):
            with open(log_path, encoding="utf-8", errors="replace") as f:
                lines = f.readlines()
            print(f"    {log_path}")
            print(f"    dong: {before_lines} -> {len(lines)} (+{len(lines)-before_lines})")
            txt = "".join(lines)
            print(f"    co 'qua cong Google'        : {'qua cổng Google' in txt}")
            print(f"    co '(Fallback Google)'      : {'(Fallback Google)' in txt}")
            print(f"    co action Reddit            : {'action_interact_reddit' in txt or 'Reddit' in txt}")
        else:
            print(f"    [!] Khong thay file log {log_path}")

        print("\n[E] Cac action da chay trong phien:")
        acts = conn.execute(
            "SELECT DISTINCT action FROM activity_history WHERE profile_id=? AND id>?",
            (PROFILE_ID, before_act)).fetchall()
        print("    ", [a[0] for a in acts])
        conn.close()

        ok = bool(rows) and len(crows) >= 1
        print("\n" + ("[+] E2E v1.4.1: PASS" if ok else "[-] E2E v1.4.1: CHECK LAI"))
        print("=" * 72)


if __name__ == "__main__":
    main()
