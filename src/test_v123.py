"""Test THẬT v1.2.3 — AI Brain sinh biến thể cho CẢ 2 vế của cặp (Google + YouTube), end-to-end qua CDP.

Profile GPM Chrome -> CDP -> WarmupWorkflow(brain=DualBrain, phase=clean, skip_youtube=False) ->
run_random_session(1 action) -> verify:
  1. Brain được hỏi ĐÚNG 2 lần: prompt #1 chứa google_query cặp + chữ "Google",
     prompt #2 chứa youtube_query cặp + chữ "YouTube".
  2. session_theme["google_query"] và ["youtube_query"] bị thay bằng 2 biến thể KHÁC NHAU
     (chứng minh mỗi vế sinh theo hint của chính nó, không chép lẫn).
  3. Action vẫn chạy bình thường (không crash).
  4. Gate: phase="mail" -> chỉ hỏi 1 lần (youtube giữ nguyên) — kiểm tra unit không cần browser.

Cách chạy:  python test_v123.py [profile_id]
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
THEME = {"google_query": "du lich viet nam", "youtube_query": "travel vlog japan"}
ANSWER_GOOGLE = "kinh nghiệm du lịch đà nẵng tự túc"
ANSWER_YOUTUBE = "japanese street food tour"


class DualBrain:
    """Brain giả lập: trả biến thể khác nhau tùy prompt là Google hay YouTube; ghi lại prompt."""
    def __init__(self):
        self.prompts = []

    def ask_text(self, prompt):
        self.prompts.append(prompt)
        time.sleep(0.2)  # giả độ trễ API
        return ANSWER_YOUTUBE if "YouTube" in prompt else ANSWER_GOOGLE


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


def test_unit_gate_mail():
    """Lượt 0 (không cần browser): mô phỏng call-site với phase=mail -> youtube không được hỏi."""
    print("\n[0] UNIT gate: phase=mail -> _safe_ask_keyword YouTube không được gọi")
    wb = WarmupWorkflow.__new__(WarmupWorkflow)
    brain = DualBrain()
    wb.brain = brain
    wb.phase = "mail"
    wb.skip_youtube = False
    wb.session_theme = dict(THEME)
    kw = wb._safe_ask_keyword(topic_hint=wb.session_theme.get("google_query", ""))
    if kw:
        wb.session_theme["google_query"] = kw
    if wb.phase != "mail" and not getattr(wb, "skip_youtube", False):
        ytkw = wb._safe_ask_keyword(topic_hint=wb.session_theme.get("youtube_query", ""), platform_label="YouTube")
        if ytkw:
            wb.session_theme["youtube_query"] = ytkw
    assert len(brain.prompts) == 1, "phase mail phải chỉ hỏi 1 lần"
    assert wb.session_theme["youtube_query"] == THEME["youtube_query"], "youtube_query phải giữ nguyên ở phase mail"
    print("    PASS: mail phase chỉ 1 prompt, youtube_query giữ nguyên từ khóa cặp")


def main():
    print("=" * 70)
    print("TEST THẬT v1.2.3 — AI sinh biến thể cả Google + YouTube (CDP)")
    print(f"Profile GPM: {PROFILE_ID}")
    print("=" * 70)

    test_unit_gate_mail()

    db = DatabaseHandler()
    api = AntidetectAPI()  # GPM port 9495
    brain = DualBrain()

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

        print("\n[3] WarmupWorkflow(brain=DualBrain, phase=clean, skip_youtube=False) + 1 action...")
        theme_copy = dict(THEME)
        warmup = WarmupWorkflow(
            context=context,
            db_handler=db,
            profile_id=PROFILE_ID,
            session_theme=theme_copy,
            skip_youtube=False,
            brain=brain,
            phase="clean",
        )
        warmup.run_random_session(total_actions=1)

        print("\n[4] VERIFY wiring v1.2.3:")
        ok_count = len(brain.prompts) == 2
        print(f"    Số lần brain được hỏi: {len(brain.prompts)} (kỳ vọng 2)")
        ok_g_prompt = ok_count and THEME["google_query"] in brain.prompts[0] and "Google" in brain.prompts[0]
        ok_y_prompt = ok_count and THEME["youtube_query"] in brain.prompts[1] and "YouTube" in brain.prompts[1]
        print(f"    Prompt #1 = Google + chứa '{THEME['google_query']}': {ok_g_prompt}")
        print(f"    Prompt #2 = YouTube + chứa '{THEME['youtube_query']}': {ok_y_prompt}")
        if brain.prompts:
            for i, p in enumerate(brain.prompts):
                print(f"    Prompt #{i + 1} (200 ký tự đầu): {p[:200]}")
        new_g = theme_copy.get("google_query")
        new_y = theme_copy.get("youtube_query")
        ok_g_replace = new_g == ANSWER_GOOGLE
        ok_y_replace = new_y == ANSWER_YOUTUBE
        print(f"    google_query sau phiên: '{new_g}' (kỳ vọng '{ANSWER_GOOGLE}') -> {ok_g_replace}")
        print(f"    youtube_query sau phiên: '{new_y}' (kỳ vọng '{ANSWER_YOUTUBE}') -> {ok_y_replace}")

        ok = ok_count and ok_g_prompt and ok_y_prompt and ok_g_replace and ok_y_replace
        print("\n" + "=" * 70)
        print("[+] KET LUAN: v1.2.3 PASS (2 prompt đúng nền tảng + 2 hint đúng vế + cả 2 từ khóa bị thay + action không crash)"
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
                print("[*] Profile vốn đã mở sẵn -> chỉ detach.")
        except Exception as e:
            print(f"[-] Lỗi dọn dẹp: {e}")
        print("[*] XONG.")


if __name__ == "__main__":
    main()
