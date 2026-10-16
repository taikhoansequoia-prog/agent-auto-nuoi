"""Test THẬT Task 4: chạy action_watch_tiktok + action_read_wikipedia
qua profile GPM thật (headed - bạn sẽ thấy cửa sổ browser thao tác).

Cách chạy:  python test_task4.py
Tắt AI brain -> chỉ test 2 action mới, không cần openai SDK.
"""
import sys
import os
import time
import random

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../')))

from src.browser.antidetect import AntidetectAPI
from src.browser.playwright_core import BrowserController
from src.database.db_handler import DatabaseHandler
from src.workflow.warmup import WarmupWorkflow

PROFILE_ID = "589ce4a3-9143-4f40-89d7-b43f61365e2e"  # "Profile ngâm 10" - lấy từ GET /api/v1/profiles


def main():
    print("=" * 70)
    print("TEST THẬT TASK 4 - TIKTOK (xem) + WIKIPEDIA (theo locale)")
    print(f"Profile GPM: {PROFILE_ID}")
    print("=" * 70)

    db = DatabaseHandler()
    api = AntidetectAPI()  # GPM mặc định port 9495

    controller = None
    try:
        print("\n[1] Đang yêu cầu GPM mở trình duyệt (headed)...")
        ws_url = api.open_profile(PROFILE_ID)
        if not ws_url:
            print("[-] Không mở được profile. Kiểm tra GPM Login đang chạy + Profile ID đúng.")
            return

        print("\n[2] Kết nối Playwright qua CDP...")
        controller = BrowserController(ws_url)
        if not controller.connect():
            print("[-] Kết nối Playwright thất bại.")
            return

        context = controller.browser.contexts[0]

        print("\n[3] Khởi tạo WarmupWorkflow (brain=None)...")
        warmup = WarmupWorkflow(
            context=context,
            db_handler=db,
            profile_id=PROFILE_ID,
            session_theme={"google_query": "du lich viet nam", "youtube_query": "du lich viet nam"},
            brain=None,
        )

        page = context.new_page()
        warmup.enable_virtual_cursor(page)

        # --- TEST 1: Wikipedia (nhanh, an toàn, xem locale detection) ---
        print("\n" + "=" * 70)
        print("TEST 1: action_read_wikipedia")
        print("=" * 70)
        warmup.action_read_wikipedia(page)

        print("\n[Chờ 5s để bạn quan sát...]")
        time.sleep(5)

        # --- TEST 2: TikTok feed (xem thuần) ---
        print("\n" + "=" * 70)
        print("TEST 2: action_watch_tiktok")
        print("=" * 70)
        warmup.action_watch_tiktok(page)

        print("\n" + "=" * 70)
        print("[+] HOÀN TẤT TEST. Giữ browser 10s để bạn xem kết quả...")
        print("=" * 70)
        time.sleep(10)

    except KeyboardInterrupt:
        print("\n[!] Bạn bấm Ctrl+C - dừng test.")
    except Exception as e:
        print(f"\n[-] Lỗi trong quá trình test: {e}")
        import traceback
        traceback.print_exc()
    finally:
        print("\n[4] Dọn dẹp: đóng Playwright + profile GPM...")
        try:
            if controller:
                controller.close()
        except Exception:
            pass
        try:
            api.close_profile(PROFILE_ID)
        except Exception as e:
            print(f"[-] Lỗi đóng profile: {e}")
        print("[x] Xong.")


if __name__ == "__main__":
    main()
