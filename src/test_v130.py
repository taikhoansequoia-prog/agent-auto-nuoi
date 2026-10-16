"""Test THẬT v1.3.0 — phiên warmup end-to-end qua production modules, xác nhận
DB + file log rơi vào data/ THỐNG NHẤT (src.paths), không stray trong dist/.

Khác biệt vs test_task5.py: phase="clean" + skip_youtube=True -> action map chỉ
gồm hành động đọc/lướt AN TOÀN (news, wikipedia, reddit, weather, finance,
tiktok): KHÔNG tạo Google Alert, KHÔNG Sub, không cày YouTube.

Chạy bằng interpreter thật + cwd thật:  python test_v130.py [profile_id]
Mặc định: 589ce4a3 (Profile ngâm 10, Chrome, locale vi — đã chứng minh CDP OK).
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
from src import paths
from src import logger
from src.logger import TeeStdout

PROFILE_ID = sys.argv[1] if len(sys.argv) > 1 else "589ce4a3-9143-4f40-89d7-b43f61365e2e"


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
    print("TEST THẬT v1.3.0 — session warmup an toàn (clean + skip_youtube)")
    print(f"Profile GPM: {PROFILE_ID}")
    print("=" * 70)

    # [0] Đường dẫn thống nhất phải trỏ repo-root data/
    print("\n[0] Duong dan src.paths (phai la repo-root data/):")
    print(f"    data_dir : {paths.data_dir()}")
    print(f"    db_path  : {paths.db_path()}")
    print(f"    logs_dir : {paths.logs_dir()}")

    db = DatabaseHandler()
    print(f"    DatabaseHandler.db_path = {db.db_path}")
    api = AntidetectAPI()

    import sqlite3
    conn = sqlite3.connect(db.db_path)
    before_max_id = conn.execute("SELECT COALESCE(MAX(id),0) FROM activity_history").fetchone()[0]
    conn.close()
    print(f"    activity_history MAX(id) truoc test: {before_max_id}")

    # --- Giống CLI main_gpm.py: wrap sys.stdout 1 lần, set profile_id ---
    tee = TeeStdout(None)
    old_stdout = sys.stdout
    sys.stdout = tee
    tee.profile_id = PROFILE_ID

    log_path = logger.profile_log_path(PROFILE_ID)
    log_lines_before = 0
    if os.path.exists(log_path):
        with open(log_path, encoding="utf-8") as f:
            log_lines_before = sum(1 for _ in f)

    controller = None
    was_open = False
    try:
        print("\n[1] Dang yeu cau GPM mo trinh duyet (headed)...")
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

        print("\n[3] WarmupWorkflow(phase=clean, skip_youtube=True) + 2 action...")
        warmup = WarmupWorkflow(
            context=context,
            db_handler=db,
            profile_id=PROFILE_ID,
            session_theme={"google_query": "du lich viet nam", "youtube_query": "du lich viet nam"},
            brain=None,
            phase="clean",
            skip_youtube=True,
        )
        t_start = time.time()
        warmup.run_random_session(total_actions=2)
        print(f"\n[*] Phiên chạy hết {time.time() - t_start:.0f}s.")

        print("\n[4] VERIFY DB — row activity_history MOI (id > %d):" % before_max_id)
        conn = sqlite3.connect(db.db_path)
        cur = conn.execute(
            "SELECT id, action, platform, substr(url,1,60), substr(title,1,40), "
            "status, duration_s, error, created_at "
            "FROM activity_history WHERE profile_id=? AND id>? ORDER BY id",
            (PROFILE_ID, before_max_id),
        )
        new_rows = cur.fetchall()
        conn.close()
        print(f"    so row moi: {len(new_rows)}")
        for row in new_rows:
            print("      ", row)

        print("\n[5] VERIFY file log (phai o repo-root data\\logs):")
        print(f"    path: {log_path}")
        exists = os.path.exists(log_path)
        print(f"    exists: {exists}")
        if exists:
            with open(log_path, encoding="utf-8") as f:
                lines = f.readlines()
            print(f"    so dong: {len(lines)} (truoc do: {log_lines_before})")
            print("    5 dong cuoi:")
            for ln in lines[-5:]:
                print("      |", ln.rstrip())

        # [6] Khong duoc co stray data/ trong dist (cwd cua EXE la dist)
        stray = os.path.join(os.path.dirname(os.path.abspath(__file__)), "dist", "GPM_Auto_Bot", "data")
        print("\n[6] Stray data/ trong dist:", stray, "->", os.path.isdir(stray))

        ok = exists and len(new_rows) >= 1 and not os.path.isdir(stray)
        print("\n" + "=" * 70)
        print(("[+] KET LUAN: v1.3.0 E2E PASS (row moi trong data\\agent_logs.db + log trong data\\logs + khong stray dist)"
               if ok else "[-] KET LUAN: CO VAN DE — kiem tra phan verify o tren"))
        print("=" * 70)

    except KeyboardInterrupt:
        print("\n[!] Bạn bấm Ctrl+C - dừng test.")
    except Exception as e:
        print(f"\n[-] Lỗi trong quá trình test: {e}")
        import traceback
        traceback.print_exc()
    finally:
        print("\n[7] Dọn dẹp: đóng Playwright + profile GPM...")
        tee.profile_id = None
        sys.stdout = old_stdout
        try:
            if controller:
                controller.close()
            if not was_open:
                api.close_profile(PROFILE_ID)
                print("[*] Đã đóng profile GPM.")
            else:
                print("[*] Profile đã mở sẵn từ trước -> chỉ detach, KHÔNG đóng.")
        except Exception as e:
            print(f"[!] Lỗi dọn dẹp (bỏ qua): {e}")


if __name__ == "__main__":
    main()
