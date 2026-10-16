"""Test THẬT v1.2.4 — action_search_youtube dùng human_type (gõ như người thật), end-to-end qua CDP.

Profile GPM Chrome -> CDP -> WarmupWorkflow -> action_search_youtube(page) trực tiếp ->
verify:
  1. human_type được gọi: log "Đang nhập từ khóa" + "Nhập từ khóa hoàn tất" xuất hiện
     (chứng minh KHÔNG còn page.type thô một nhịp).
  2. Sau Enter, page.url chứa "/results?search_query=" và keyword (URL-encoded) -> gõ ĐÚNG.
  3. Không crash.
Để test tập trung vào phần sửa (search), stub _watch_single_video_logic + human_click
(không thật sự xem video dài) — đây là test có chủ đích cho hành vi gõ, không phải full flow.

Cách chạy:  python test_v124.py [profile_id]
Mặc định:  589ce4a3... ("Profile ngâm 10", Chrome, locale vi).
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

PROFILE_ID = sys.argv[1] if len(sys.argv) > 1 else "589ce4a3-9143-4f40-89d7-b43f61365e2e"
KEYWORD = "japanese street food tour"
THEME = {"google_query": "du lich viet nam", "youtube_query": KEYWORD}


class LogCapture:
    """Capture stdout để kiểm tra log human_type."""
    def __init__(self):
        self.lines = []

    def write(self, s):
        self.lines.append(s)
        sys.__stdout__.write(s)

    def flush(self):
        pass


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


def main():
    print("=" * 70)
    print("TEST THẬT v1.2.4 — action_search_youtube human_type (CDP)")
    print(f"Profile GPM: {PROFILE_ID} | keyword: '{KEYWORD}'")
    print("=" * 70)

    db = DatabaseHandler()
    api = AntidetectAPI()  # GPM port 9495

    controller = None
    was_open = False
    cap = LogCapture()
    old_stdout = sys.stdout
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

        print("\n[3] WarmupWorkflow(phase=youtube) + action_search_youtube (stub xem video)...")
        warmup = WarmupWorkflow(
            context=context,
            db_handler=db,
            profile_id=PROFILE_ID,
            session_theme=dict(THEME),
            skip_youtube=False,
            brain=None,
            phase="youtube",
        )
        # Stub để test tập trung vào phần GÕ search, không xem video dài
        warmup._watch_single_video_logic = lambda *a, **k: print("      (stub) bỏ qua xem video")
        warmup.human_click = lambda *a, **k: print("      (stub) bỏ qua click video")

        page = context.new_page()
        sys.stdout = cap  # capture log human_type
        try:
            warmup.action_search_youtube(page)
        finally:
            sys.stdout = old_stdout
        time.sleep(1.5)
        final_url = page.url

        print("\n[4] VERIFY:")
        joined = "".join(cap.lines)
        ok_start = "Đang nhập từ khóa" in joined
        ok_done = "Nhập từ khóa hoàn tất" in joined
        ok_searched = f"Đã tìm kiếm: '{KEYWORD}'" in joined
        print(f"    human_type bắt đầu gõ (log): {ok_start}")
        print(f"    human_type hoàn tất (log):   {ok_done}")
        print(f"    Đã search đúng keyword:      {ok_searched}")
        ok_url = ("results" in final_url) and ("search_query" in final_url) and (KEYWORD.replace(" ", "+") in final_url or KEYWORD in final_url)
        print(f"    URL trang kết quả: {final_url[:120]}")
        print(f"    URL chứa /results?search_query=<keyword>: {ok_url}")

        ok = ok_start and ok_done and ok_searched and ok_url
        print("\n" + "=" * 70)
        print("[+] KET LUAN: v1.2.4 PASS (gõ human_type từng ký tự vào YouTube search + ra kết quả đúng, không crash)"
              if ok else "[-] KET LUAN: CO VAN DE — xem chi tiết ở trên")
        print("=" * 70)

    except KeyboardInterrupt:
        print("\n[!] Ctrl+C - dừng test.")
    except Exception as e:
        sys.stdout = old_stdout
        print(f"\n[-] Lỗi trong quá trình test: {e}")
        import traceback
        traceback.print_exc()
    finally:
        sys.stdout = old_stdout
        print("\n[5] Dọn dẹp...")
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
        print("[*] XONG.")


if __name__ == "__main__":
    main()
