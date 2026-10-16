"""Test v1.3.1 — xác nhận cột `platform` cho action Reddit.

Bug cũ: _log_activity đọc page.url LÚC GHI LOG. Sau action_interact_reddit
(page kết thúc ở about:blank vì go_back khỏi bài), platform bị rỗng ''.
Fix v1.3.1: _log_activity ưu tiên suy platform theo TÊN action
(_ACTION_PLATFORM), chỉ suy-từ-URL cho action đa-site.

Cách test (nhanh, THẬT, không chờ 5-10 phút cày Reddit):
- Kết nối CDP tới profile GPM (đúng production modules EXE bundle).
- Đặt page ở about:blank = CHÍNH xác điều kiện gây bug.
- Gọi production warmup._log_activity(page, "action_interact_reddit", ...).
- Đọc lại row vừa ghi -> platform PHAI la 'Reddit' (truoc day la '').
- (Thu thêm 1 action da-site "read_news" o bbc.com -> van giu host that.)

Chay:  python test_v131.py [profile_id]
Mac dinh: 589ce4a3 (Profile ngam 10, Chrome, locale vi - da chung minh CDP OK).
Xu ly profile DA MO SAN (chi detach, khong close cua user).
"""
import sys
import os
import sqlite3

import requests

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../')))

from src.browser.antidetect import AntidetectAPI
from src.browser.playwright_core import BrowserController
from src.database.db_handler import DatabaseHandler
from src.workflow.warmup import WarmupWorkflow
from src import paths

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
    print("TEST v1.3.1 — cot platform cho action Reddit (page o about:blank)")
    print(f"Profile GPM: {PROFILE_ID}")
    print("=" * 70)

    print("\n[0] Duong dan src.paths (phai la repo-root data/):")
    print(f"    db_path  : {paths.db_path()}")

    db = DatabaseHandler()
    conn = sqlite3.connect(db.db_path)
    before_max_id = conn.execute("SELECT COALESCE(MAX(id),0) FROM activity_history").fetchone()[0]
    conn.close()
    print(f"    activity_history MAX(id) truoc test: {before_max_id}")

    api = AntidetectAPI()
    controller = None
    was_open = False
    page = None
    try:
        print("\n[1] Mo / ket noi profile GPM qua CDP...")
        ws_url, was_open = resolve_ws(api, PROFILE_ID)
        if not ws_url:
            print("[-] Khong mo duoc profile. Kiem tra GPM Login dang chay + Profile ID dung.")
            return

        controller = BrowserController(ws_url)
        if not controller.connect():
            print("[-] Ket noi Playwright that bai.")
            return

        context = controller.browser.contexts[0]
        warmup = WarmupWorkflow(
            context=context,
            db_handler=db,
            profile_id=PROFILE_ID,
            session_theme={"google_query": "du lich viet nam", "youtube_query": "du lich viet nam"},
            brain=None,
            phase="clean",
            skip_youtube=True,
        )

        page = context.new_page()

        # === CASE 1: Dieu kien gay bug cu — page o about:blank, action Reddit ===
        print("\n[2] CASE 1: page.goto('about:blank') -> _log_activity('action_interact_reddit')")
        page.goto("about:blank")
        print(f"    page.url luc ghi log = {page.url!r}  (day la dieu kien sinh bug '')")
        warmup._log_activity(page, "action_interact_reddit", status="ok", duration_s=1.0)

        # === CASE 2 (doi chung): action da-site read_news o bbc.com -> giu host that ===
        print("\n[3] CASE 2 (doi chung): page.goto('https://www.bbc.com/news') -> _log_activity('read_news')")
        try:
            page.goto("https://www.bbc.com/news", wait_until="domcontentloaded", timeout=30000)
            print(f"    page.url luc ghi log = {page.url[:50]!r}")
            warmup._log_activity(page, "read_news", status="ok", duration_s=1.0)
        except Exception as e:
            print(f"    (!) Bo qua CASE 2 (loi mang): {e}")

        # === DOC LAI DB ===
        print("\n[4] VERIFY DB — row moi (id > %d):" % before_max_id)
        conn = sqlite3.connect(db.db_path)
        cur = conn.execute(
            "SELECT id, action, platform, substr(url,1,50), status, duration_s "
            "FROM activity_history WHERE profile_id=? AND id>? ORDER BY id",
            (PROFILE_ID, before_max_id),
        )
        new_rows = cur.fetchall()
        conn.close()
        for row in new_rows:
            print("      ", row)

        reddit_rows = [r for r in new_rows if r[1] == "action_interact_reddit"]
        news_rows = [r for r in new_rows if r[1] == "read_news"]

        print("\n" + "=" * 70)
        if not reddit_rows:
            print("[-] KET LUAN: khong co row Reddit -> kiem tra lai")
        else:
            plat = reddit_rows[0][2]
            if plat == "Reddit":
                print("[+] KET LUAN: v1.3.1 PASS — row Reddit o about:blank -> platform='Reddit' (fix hoat dong)")
            else:
                print(f"[-] KET LUAN: VAN CON BUG — row Reddit -> platform={plat!r} (dang la '' hoac giu khac)")
        if news_rows:
            nplat = news_rows[0][2]
            good = ("bbc" in (nplat or "").lower()) or (nplat not in ("", None))
            print(f"[{'+' if good else '!'}] CASE 2 (doi chung): read_news -> platform={nplat!r} "
                  f"(kỳ vọng host thật, KHÔNG bị ép thành giá trị cố định)")
        print("=" * 70)

    except KeyboardInterrupt:
        print("\n[!] Ban bam Ctrl+C - dung test.")
    except Exception as e:
        print(f"\n[-] Lỗi trong quá trình test: {e}")
        import traceback
        traceback.print_exc()
    finally:
        print("\n[5] Don dep: dong page + Playwright + profile GPM...")
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
        try:
            if not was_open:
                api.close_profile(PROFILE_ID)
                print("[*] Da dong profile GPM.")
            else:
                print("[*] Profile da mo san tu truoc -> chi detach, KHONG dong.")
        except Exception as e:
            print(f"[!] Lloi don dep (bo qua): {e}")


if __name__ == "__main__":
    main()
