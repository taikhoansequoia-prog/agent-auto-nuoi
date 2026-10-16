"""Test THẬT action_manage_google_alerts (Pha 2 - mail) qua profile GPM Chrome
đã login Google (Mail133). Chạy 2 lượt: lượt 1 tạo alert mới (Nhánh A),
lượt 2 chăm alert đã có (Nhánh B).

Cách chạy:  python test_alerts.py [profile_id]
Mặc định:  Mail133 (Chrome, nguyenluongpt88@gmail.com - tai khoan diag/test).
Xử lý cả trường hợp profile ĐÃ MỞ SẴN (resolve ws qua remote_debugging_port).
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
    print("TEST THẬT action_manage_google_alerts (Pha 2 - mail)")
    print(f"Profile GPM: {PROFILE_ID}")
    print("=" * 70)

    db = DatabaseHandler()
    api = AntidetectAPI()  # GPM mặc định port 9495

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

        print("\n[3] Khởi tạo WarmupWorkflow (phase=mail, brain=None)...")
        warmup = WarmupWorkflow(
            context=context,
            db_handler=db,
            profile_id=PROFILE_ID,
            session_theme={"google_query": "du lich viet nam", "youtube_query": "du lich viet nam"},
            brain=None,
            phase="mail",
        )

        page = context.new_page()
        warmup.enable_virtual_cursor(page)

        # --- LƯỢT 1: Nhánh A (tạo alert mới, nếu DB cho phép) ---
        print("\n" + "=" * 70)
        print("LƯỢT 1: action_manage_google_alerts (kỳ vọng Nhánh A - tạo mới)")
        print("=" * 70)
        warmup.action_manage_google_alerts(page)

        print("\n[Chờ 8s để bạn quan sát...]")
        time.sleep(8)

        # --- LƯỢT 2: Nhánh B (chăm alert đã có) ---
        print("\n" + "=" * 70)
        print("LƯỢT 2: action_manage_google_alerts (kỳ vọng Nhánh B - chăm)")
        print("=" * 70)
        warmup.action_manage_google_alerts(page)

        print("\n" + "=" * 70)
        print("[+] HOÀN TẤT TEST. Giữ browser 15s để bạn xem kết quả...")
        print("=" * 70)
        time.sleep(15)

    except KeyboardInterrupt:
        print("\n[!] Bạn bấm Ctrl+C - dừng test.")
    except Exception as e:
        print(f"\n[-] Lỗi trong quá trình test: {e}")
        import traceback
        traceback.print_exc()
    finally:
        print("\n[4] Dọn dẹp: đóng Playwright + profile GPM...")
        try:
            if page:
                page.close()
        except Exception:
            pass
        try:
            if controller:
                controller.close()
        except Exception:
            pass
        # CHỈ đóng profile nếu chính ta mở nó (không tắt profile user đang dùng dở)
        if not was_open:
            try:
                api.close_profile(PROFILE_ID)
            except Exception as e:
                print(f"[-] Lỗi đóng profile: {e}")
        else:
            print("[i] Profile đã mở sẵn từ trước -> chỉ detach, không đóng.")
        print("[x] Xong.")


if __name__ == "__main__":
    main()
