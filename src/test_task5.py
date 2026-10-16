"""Test THẬT Task 5 — reporting + file log, chạy end-to-end như CLI.

Profile GPM Chrome (Mail133) -> CDP -> wrap sys.stdout bằng TeeStdout (giống
main_gpm.py) -> run_random_session(phase=mail, 2 action) -> verify:
  1. Bảng activity_history có row mới (action, platform, url, title).
  2. File data/logs/{profile_id}.log tồn tại và chứa các dòng print.

Cách chạy:  python test_task5.py [profile_id]
Mặc định:  Mail133 (Chrome, logged-in Google, locale vi).
Xử lý profile ĐÃ MỞ SẴN (resolve ws qua remote_debugging_port, chỉ detach).
"""
import sys
import os
import time

import requests

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../')))

from src.browser.antidetect import AntidetectAPI
from src.browser.playwright_core import BrowserController
from src.database.db_handler import DatabaseHandler
from src.workflow.warmup import WarmupWorkflow
from src import logger
from src.logger import TeeStdout

PROFILE_ID = sys.argv[1] if len(sys.argv) > 1 else "79643241-9845-4ed1-b12f-3f418a293c57"


def resolve_ws(api, profile_id):
    """Trả về (ws_url, was_open). Nếu profile đã mở sẵn -> only detach, don't close."""
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


def main():
    print("=" * 70)
    print("TEST THẬT Task 5 — activity_history + file log (end-to-end)")
    print(f"Profile GPM: {PROFILE_ID}")
    print("=" * 70)

    db = DatabaseHandler()
    api = AntidetectAPI()  # GPM mặc định port 9495

    # Đếm row trước để biết có row mới thật không
    before = len(db.get_activity_summary(PROFILE_ID, days=1))

    # --- Giống CLI main_gpm.py: wrap sys.stdout 1 lần, set profile_id ---
    tee = TeeStdout(None)
    old_stdout = sys.stdout
    sys.stdout = tee
    tee.profile_id = PROFILE_ID

    controller = None
    was_open = False
    try:
        print("\n[1] Đang yêu cầu GPM mở trình duyệt (headed)...")
        ws_url, was_open = resolve_ws(api, PROFILE_ID)
        if not ws_url:
            print("[-] Không mở được profile. Kiểm tra GPM Login đang chạy + Profile ID đúng.")
            return

        print("\n[2] Kết nối Playwright qua CDP...")
        controller = BrowserController(ws_url)
        if not controller.connect():
            print("[-] Kết nối Playwright thất bại.")
            return

        context = controller.browser.contexts[0]

        print("\n[3] Khởi tạo WarmupWorkflow (phase=mail) + run_random_session(2 action)...")
        warmup = WarmupWorkflow(
            context=context,
            db_handler=db,
            profile_id=PROFILE_ID,
            session_theme={"google_query": "du lich viet nam", "youtube_query": "du lich viet nam"},
            brain=None,
            phase="mail",
        )
        warmup.run_random_session(total_actions=2)

        print("\n[4] VERIFY DB — activity_history:")
        rows = db.get_activity_summary(PROFILE_ID, days=1)
        print(f"    summary group hom nay: {len(rows)} (truoc do: {before})")
        for r in rows:
            print(f"    - {r['action']} | {r['platform']} | x{r['count']} | {r['last_at']}")
        # row thô 5 bản ghi mới nhất
        import sqlite3
        conn = sqlite3.connect(db.db_path)
        cur = conn.execute(
            "SELECT action, platform, substr(url,1,60), substr(title,1,50), created_at "
            "FROM activity_history WHERE profile_id=? ORDER BY id DESC LIMIT 5",
            (PROFILE_ID,),
        )
        print("    5 row moi nhat (tho):")
        for row in cur.fetchall():
            print("      ", row)
        conn.close()

        print("\n[5] VERIFY file log:")
        p = logger.profile_log_path(PROFILE_ID)
        exists = os.path.exists(p)
        print(f"    path: {p}")
        print(f"    exists: {exists}")
        if exists:
            with open(p, encoding="utf-8") as f:
                lines = f.readlines()
            print(f"    so dong: {len(lines)}")
            print("    10 dong dau:")
            for ln in lines[:10]:
                print("      |", ln.rstrip())
            print("    5 dong cuoi:")
            for ln in lines[-5:]:
                print("      |", ln.rstrip())

        ok = exists and len(rows) > before
        print("\n" + "=" * 70)
        print(("[+] KET LUAN: Task 5 PASS (DB co row moi + file log ton tai)"
               if ok else "[-] KET LUAN: CO VAN DE — kiem tra phan verify o tren"))
        print("=" * 70)

    except KeyboardInterrupt:
        print("\n[!] Bạn bấm Ctrl+C - dừng test.")
    except Exception as e:
        print(f"\n[-] Lỗi trong quá trình test: {e}")
        import traceback
        traceback.print_exc()
    finally:
        print("\n[6] Dọn dẹp: đóng Playwright + profile GPM...")
        # restore stdout TRƯỚC khi dọn dẹp để in bình thường
        tee.profile_id = None
        sys.stdout = old_stdout
        try:
            if controller:
                # chỉ detach browser của ta, đóng các page bot mở thì ko cần — close() của controller
                controller.close()
            if not was_open:
                api.close_profile(PROFILE_ID)
                print("[*] Đã đóng profile GPM.")
            else:
                print("[*] Profile vốn đã mở sẵn -> chỉ detach (giữ nguyên cho bạn).")
        except Exception as e:
            print(f"[-] Lỗi dọn dẹp: {e}")
        print("[*] XONG.")


if __name__ == "__main__":
    main()
