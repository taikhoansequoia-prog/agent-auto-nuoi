"""Test THẬT v1.2.2 — AI Brain topic_hint wiring, chạy end-to-end qua CDP.

Profile GPM Chrome -> CDP -> WarmupWorkflow(brain=RecordingBrain) ->
run_random_session(1 action) -> verify:
  1. Brain nhận prompt CHỨA chủ đề cặp (topic_hint được truyền từ session_theme).
  2. session_theme["google_query"] bị thay bằng từ khóa AI sinh (biến thể theo chủ đề).
  3. Action vẫn chạy bình thường với từ khóa mới (không crash).
  4. Fallback: brain=None -> giữ nguyên từ khóa cặp (kiểm tra ở lượt 2, không cần browser).

Cách chạy:  python test_v122.py [profile_id]
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
THEME = {"google_query": "du lich viet nam", "youtube_query": "du lich viet nam"}


class RecordingBrain:
    """Brain giả lập: ghi lại prompt, trả về biến thể theo chủ đề."""
    def __init__(self, answer="kinh nghiệm du lịch đà nẵng"):
        self.prompts = []
        self.answer = answer

    def ask_text(self, prompt):
        self.prompts.append(prompt)
        time.sleep(0.2)  # giả độ trễ API
        return self.answer


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


def test_unit_fallback():
    """Lượt 0 (không cần browser): brain=None -> session_theme không đổi."""
    print("\n[0] UNIT: brain=None -> fallback giữ nguyên từ khóa cặp")
    wb = WarmupWorkflow.__new__(WarmupWorkflow)
    wb.brain = None
    wb.session_theme = dict(THEME)
    kw = wb._safe_ask_keyword(topic_hint="du lich viet nam")
    assert kw is None, "brain=None phải trả None"
    print("    PASS: _safe_ask_keyword trả None, không crash")


def main():
    print("=" * 70)
    print("TEST THẬT v1.2.2 — AI Brain topic_hint end-to-end (CDP)")
    print(f"Profile GPM: {PROFILE_ID}")
    print("=" * 70)

    test_unit_fallback()

    db = DatabaseHandler()
    api = AntidetectAPI()  # GPM port 9495
    brain = RecordingBrain()

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

        print("\n[3] WarmupWorkflow(brain=RecordingBrain, phase=clean, skip_youtube) + 1 action...")
        theme_copy = dict(THEME)
        warmup = WarmupWorkflow(
            context=context,
            db_handler=db,
            profile_id=PROFILE_ID,
            session_theme=theme_copy,
            skip_youtube=True,
            brain=brain,
            phase="clean",
        )
        warmup.run_random_session(total_actions=1)

        print("\n[4] VERIFY wiring topic_hint:")
        ok_prompt = bool(brain.prompts) and THEME["google_query"] in brain.prompts[0]
        print(f"    Số lần brain được hỏi: {len(brain.prompts)} (kỳ vọng 1)")
        if brain.prompts:
            print(f"    Prompt chứa chủ đề cặp: {ok_prompt}")
            print(f"    Prompt (200 ký tự đầu): {brain.prompts[0][:200]}")
        new_kw = theme_copy.get("google_query")
        ok_replace = new_kw == brain.answer
        print(f"    session_theme sau phiên: '{new_kw}' (kỳ vọng biến thể AI: '{brain.answer}')")
        print(f"    Từ khóa được thay bằng AI: {ok_replace}")

        ok = ok_prompt and ok_replace and len(brain.prompts) == 1
        print("\n" + "=" * 70)
        print("[+] KET LUAN: v1.2.2 PASS (hint truyền đúng + AI thay từ khóa + action chạy không crash)"
              if ok else "[-] KET LUAN: CO VAN DE — xem chi tiết ở trên")
        print("=" * 70)

    except KeyboardInterrupt:
        print("\n[!] Bạn bấm Ctrl+C - dừng test.")
    except Exception as e:
        print(f"\n[-] Lỗi trong quá trình test: {e}")
        import traceback
        traceback.print_exc()
    finally:
        print("\n[5] Dọn dẹp: đóng Playwright + profile GPM...")
        try:
            if controller:
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
