import sys
import os
import re
import csv
import time
import datetime
import random
import threading
import queue
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import tkinter.font as tkfont
from concurrent.futures import ThreadPoolExecutor

import requests

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../')))

from src.browser.browser_factory import BrowserFactory, BROWSER_GPM, BROWSER_BITBROWSER
from src.browser.playwright_core import BrowserController
from src.database.db_handler import DatabaseHandler
from src.workflow.warmup import WarmupWorkflow
from src.agent.brain_manager import BrainManager
from src.logger import append_line, LOG_DIR
from src.version import get_version_line
from src.app_config import load_config, save_config
from src import api_vault

# ==========================================
# SPRINT 1.5: nhãn phase "ngôn ngữ người vận hành" -> key nội bộ (warmup.py GIỮ NGUYÊN)
# ==========================================
PHASE_LABELS = [
    "1 - Acc mới — chưa có gì",
    "2 - Đã có mail — nuôi Google",
    "3 - Cày YouTube — được Sub",
]
PHASE_MAP = {PHASE_LABELS[0]: "clean", PHASE_LABELS[1]: "mail", PHASE_LABELS[2]: "youtube"}
PHASE_LABEL_BY_KEY = {v: k for k, v in PHASE_MAP.items()}

# ==========================================
# v1.3.8: TÀI LIỆU 3 CHẾ ĐỘ NGÂM cho dialog "CHI TIẾT" (thuần UI — số liệu
# đối chiếu tay từ action_map trong workflow/warmup.py::run_random_session,
# KHÔNG import warmup). Mỗi action = (tên hiển thị, trọng số, mô tả, nhóm):
#   nhóm "yt"   -> bị loại khi tick "Bỏ qua xem YouTube"
#   nhóm "rand" -> bị loại khi tick "Bỏ qua từ khóa ngẫu nhiên"
#   nhóm None   -> luôn có trong lịch trình pha đó
# ==========================================
PHASE_DETAILS = {
    "clean": {
        "goal": ("Giai đoạn 1 — tài khoản TRẮNG, chưa lắp mail. Bot chỉ tạo hành vi lướt web "
                 "tự nhiên để nuôi fingerprint. TUYỆT ĐỐI không đụng Google Alerts và không "
                 "đăng ký kênh (Sub) ở pha này."),
        "actions": [
            ("Tìm kiếm YouTube", 0.60, "Gõ từ khóa YouTube vào ô tìm kiếm (gõ như người thật), lướt kết quả 6-12s, bấm 1 trong 4 video đầu, xem chuỗi 2-3 video.", "yt"),
            ("Xem trang chủ YouTube", 0.40, "Vào youtube.com, lướt feed, hover thumbnail, chốt 1 video xem 55-90% thời lượng. Trang chủ trống (acc mới) -> tự chuyển sang tìm kiếm.", "yt"),
            ("Xem TikTok", 0.45, "Vào TikTok QUA CỔNG GOOGLE, xem thuần 3-7 video, mỗi cái ngồi 12-35s, không like/comment.", None),
            ("Đọc Wikipedia", 0.35, "Vào Wikipedia qua Google theo ngôn ngữ máy (vi/en...), cuộn đọc 60-120s, 40% bấm thêm 1 link nội bộ rồi đọc tiếp.", None),
            ("Đọc báo", 0.35, "Lên Google gõ 'chủ đề + tên báo' rồi bấm kết quả (1 trong 13 trang báo VN + quốc tế), lướt trang chủ 30-60s rồi bấm 1-2 bài đọc 60-180s.", None),
            ("Google: tìm + đọc tin", 0.25, "Tìm chủ đề tin tức trên Google, bấm tab 'Tin tức', đọc 1-3 bài (cuộn nghỉ 8-16s mỗi nhịp).", None),
            ("Thời tiết ngẫu nhiên", 0.10, "Hỏi Google thời tiết bằng từ khóa cố định ngoài chủ đề cặp, xem thẻ dự báo chi tiết.", "rand"),
            ("Google Finance", 0.10, "Xem google.com/finance, tra 1 mã ngẫu nhiên (BTC-USD, AAPL, TSLA...), ngắm biểu đồ + đọc 1 bài tài chính.", "rand"),
        ],
        "notes": ("Không có Google Alerts trong lịch trình. Không bao giờ Subscribe (kể cả xem video >70%). "
                  "KHÔNG có Reddit ở pha này (acc trắng chưa nên dạo nền tảng 'nặng') — Reddit chỉ xuất hiện từ Pha 2. "
                  "Đọc báo đi QUA CỔNG GOOGLE (gõ tìm kiếm rồi bấm kết quả), không goto thẳng. "
                  "AI Brain (nếu bật) sinh biến thể từ khóa cho CẢ Google lẫn YouTube — tối đa 2 lượt hỏi/phiên. "
                  "Tick 'Bỏ qua xem YouTube' -> còn 6 hành động thuần lướt web."),
    },
    "mail": {
        "goal": ("Giai đoạn 2 — tài khoản đã lắp Gmail. Trọng tâm là HỆ SINH THÁI GOOGLE: nuôi "
                 "Google Alerts (được phép TẠO MỚI) + thói quen tìm kiếm/đọc tin qua Google. "
                 "KHÔNG có YouTube trong lịch trình pha này."),
        "actions": [
            ("Đọc báo", 0.35, "Lên Google gõ 'chủ đề + tên báo' rồi bấm kết quả (1 trong 13 trang báo), lướt trang chủ rồi bấm 1-2 bài đọc 60-180s.", None),
            ("Google Alerts", 0.35, "Vào google.com/alerts: NHÁNH A tạo alert mới cho từ khóa phiên (gate DB: từ khóa chưa trùng + tối đa 1 alert mới/7 ngày/profile) hoặc NHÁNH B chăm alert cũ (hover, xem preview, mở edit rồi đóng — không sửa/xóa).", None),
            ("Đọc Wikipedia", 0.30, "Vào Wikipedia qua Google theo ngôn ngữ máy, cuộn đọc 60-120s.", None),
            ("Google: tìm + đọc tin", 0.25, "Tìm chủ đề tin tức trên Google, bấm tab 'Tin tức', đọc 1-3 bài.", None),
            ("Xem TikTok", 0.20, "Vào TikTok qua cổng Google, xem thuần 3-7 video.", None),
            ("Reddit", 0.20, "Lướt feed reddit.com, mở 2-4 bài, upvote bài + comment.", None),
            ("Thời tiết ngẫu nhiên", 0.10, "Hỏi Google thời tiết (từ khóa ngoài chủ đề cặp).", "rand"),
            ("Google Finance", 0.10, "Xem google.com/finance, tra 1 mã ngẫu nhiên.", "rand"),
        ],
        "notes": ("Chưa login Google trên trình duyệt -> action Alerts tự bỏ qua (log 'Chưa login Google'). "
                  "AI Brain chỉ hỏi 1 lượt từ khóa Google (không hỏi YouTube vì pha này không xem YouTube). "
                  "Không đăng ký kênh ở pha này. Menu tần suất alert chọn theo tỉ lệ 20% ngay lập tức / 50% mỗi ngày / 30% mỗi tuần."),
    },
    "youtube": {
        "goal": ("Giai đoạn 3 — CÀY YOUTUBE là trục chính, và là pha DUY NHẤT được đăng ký kênh "
                 "(Subscribe). Google Alerts chỉ được CHĂM SÓC, không tạo mới. Cảnh: tài khoản nên "
                 "đã nuôi qua Pha 1-2 trước khi chọn chế độ này."),
        "actions": [
            ("Tìm kiếm YouTube", 0.60, "Gõ từ khóa YouTube (gõ như người thật), lướt kết quả, bấm 1 trong 4 video đầu, xem chuỗi 2-3 video.", "yt"),
            ("Xem trang chủ YouTube", 0.40, "Lướt feed trang chủ, hover preview thumbnail, chốt video xem 55-90% thời lượng. Trang chủ trống -> tự chuyển sang tìm kiếm.", "yt"),
            ("Đọc báo", 0.20, "Điểm xuyết: lên Google gõ 'chủ đề + tên báo' rồi bấm kết quả, bấm 1-2 bài.", None),
            ("Đọc Wikipedia", 0.20, "Điểm xuyết đọc Wikipedia qua cổng Google.", None),
            ("Google Alerts (chăm thôi)", 0.15, "Mở google.com/alerts xem/hover/preview alert đã có — code CHẶN tạo mới khi phase = youtube.", None),
        ],
        "notes": ("Subscribe chỉ bật khi ĐỦ cả 3: xem >70% thời lượng video + chế độ này (needs_sub) + quota ngày còn "
                  "(DB gate 1 sub/ngày/profile, ghi log_sub_success). 40% Like khi xem video. Tick 'Bỏ qua xem YouTube' "
                  "ở pha này = mất trục chính, chỉ còn 3 hành động lướt web. AI Brain sinh biến thể từ khóa Google + YouTube."),
    },
}

# ==========================================
# v1.3.6: NHÓM PROFILE — gương phản chiếu nhóm trong GPM Login (chỉ đọc).
# API thật (dump 15/10/2026): profile có group_id UUID, tên nhóm lấy qua
# GET /api/v1/groups. Profile không nhóm / dán tay / BitBrowser -> "" -> "Chưa có nhóm".
# ==========================================
GROUP_ALL = "Tất cả nhóm"
UNGROUPED_LABEL = "Chưa có nhóm"

# ==========================================
# v1.3.5: MỐC NUÔI ACC 7 NGÀY (theo sheet "Auto ngm mail")
# Giai đoạn 0 = lắp proxy CHƯA lắp mail, bot tự ngâm 4 ngày (Ngày 1-4).
# Hết 4 ngày (từ Ngày 5) tới lúc NGƯỜI LÀM TAY: lắp mail + Móng bảo mật
# (đăng nhập Gmail sạch, 2SV, email/SĐT khôi phục, ESB — sheet dòng 3).
# App popup nhắc 1 lần/profile (dedup qua milestone_history), không spam mỗi lần mở.
# ==========================================
STAGE0_DAYS = 4
STAGE1_MILESTONE_CODE = "mail_manual_stage1"
STAGE1_TASKS_TEXT = (
    "Việc cần làm tay (sheet dòng 3 — Móng bảo mật):\n"
    "1. Đăng nhập Gmail trên trình duyệt sạch — KHÔNG xem YouTube ngay.\n"
    "2. Bật ngay Xác minh 2 bước (2SV).\n"
    "3. Khai báo Email khôi phục + Số điện thoại khôi phục.\n"
    "4. Bật Duyệt web an toàn tăng cường (Enhanced Safe Browsing).\n"
    "(Mục 2-3-4 chưa có thông tin thì bỏ qua.)"
)

# ==========================================
# MÁY CHỦ BẮT LOG ĐỘC LẬP TỪNG LUỒNG
# ==========================================
THREAD_SLOTS = {} 
# Map "Slot N" -> profile_id để ghi file log riêng theo profile (Task 5)
SLOT_PROFILE = {}
# Cờ dừng an toàn toàn cục: nút DỪNG set -> mỗi workflow nhận qua should_stop()
STOP_EVENT = threading.Event()
# Heartbeat (Sprint 0.2): mỗi slot ghi nhận lần in log cuối + tên + thread còn sống
SLOT_LAST_LOG = {}      # "Slot N" -> epoch float lần cuối có log
SLOT_LABEL = {}         # "Slot N" -> tên profile đang chạy ở slot
SLOT_THREAD_ALIVE = {}  # "Slot N" -> bool thread còn đang xử lý
# v1.4.0: epoch lúc BẮT ĐẦU chu trình ngâm của slot (đếm thời gian thực trên heartbeat/Bảng)
SLOT_CYCLE_START = {}
# v1.4.0: "Slot N" -> dict số liệu chu trình đang chạy (run_single_profile ghi, worker_wrapper đọc)
# {start_str, status('ok'|'error'|'stopped'|'pending'), duration_s, finish_str, actions, phase, error}
SLOT_CYCLE_INFO = {}


def _fmt_dur(v):
    """v1.4.0: giây -> '45s' / '12m30s' / '2h05m'; None -> '-'."""
    if v is None:
        return "-"
    try:
        v = float(v)
    except (TypeError, ValueError):
        return "-"
    if v < 60:
        return f"{v:.0f}s"
    if v < 3600:
        return f"{int(v // 60)}m{int(v % 60):02d}s"
    return f"{int(v // 3600)}h{int((v % 3600) // 60):02d}m"

# Sprint 2: nhận diện mức log theo tiền tố in sẵn trong code (KHÔNG đổi các dòng print)
# Thứ tự ưu tiên: lỗi > cảnh báo > thành công > thường.
_LEVEL_PREFIXES = (("[!]", "error"), ("⚠️", "error"), ("❌", "error"),
                   ("[*]", "warn"), ("[+]", "ok"))


def _tag_level(msg):
    """Gán tag mức vào đầu dòng log (kèm timestamp) — chỉ khi bật filter để UI mặc định y như cũ."""
    first = msg.lstrip()
    level = "info"
    for prefix, lv in _LEVEL_PREFIXES:
        if first.startswith(prefix):
            level = lv
            break
    return f"[{time.strftime('%H:%M:%S')}|{level}] {msg}"


class ThreadSafeStdout:
    def __init__(self, log_callback, level_filter=None):
        self.stdout = sys.stdout
        self.log_callback = log_callback
        # Sprint 2: None = hiện tất cả; set mức -> chỉ dòng thuộc mức đó (lỗi luôn kèm cảnh báo)
        self.level_filter = level_filter
        
    def write(self, msg):
        # v1.3.6: EXE chạy với stdout pipe/cp1252 -> print tiếng Việt có dấu raise
        # UnicodeEncodeError và làm CHẾT cả callback Tkinter (khuyến cáo: log mất dòng).
        # Bọc try: thay ký tự lỗi bằng '?' ở CONSOLE, GUI + file log vẫn nhận bản UTF-8 đầy đủ.
        try:
            self.stdout.write(msg)
        except UnicodeEncodeError:
            enc = getattr(self.stdout, "encoding", None) or "ascii"
            try:
                self.stdout.write(msg.encode(enc, "replace").decode(enc, "replace"))
            except Exception:
                pass
        if msg.strip('\n'):
            tid = threading.get_ident()
            slot = THREAD_SLOTS.get(tid, "MAIN")
            if slot != "MAIN":
                SLOT_LAST_LOG[slot] = time.time()  # heartbeat: slot vừa lên tiếng
            level = "info"
            if self.level_filter is not None:
                first = msg.lstrip()
                for prefix, lv in _LEVEL_PREFIXES:
                    if first.startswith(prefix):
                        level = lv
                        break
                if level not in self.level_filter:
                    return  # bị lọc: không vào GUI, không vào file
                msg = _tag_level(msg)
            self.log_callback(slot, msg)
            # Task 5: ghi song song vào file log của profile đang chạy ở slot này
            pid = SLOT_PROFILE.get(slot)
            if pid:
                append_line(pid, msg if msg.endswith("\n") else msg + "\n")
            
    def flush(self):
        self.stdout.flush()

# ==========================================
# 1. HÀM CHIA MÀN HÌNH CDP
# ==========================================
def adjust_window_bounds(context, slot_index, screen_w, screen_h):
    try:
        w = screen_w // 2
        h = screen_h // 2
        
        if slot_index % 4 == 0:   x, y = 0, 0
        elif slot_index % 4 == 1: x, y = w, 0
        elif slot_index % 4 == 2: x, y = 0, h
        elif slot_index % 4 == 3: x, y = w, h
        
        page = context.pages[0] if context.pages else context.new_page()
        client = context.new_cdp_session(page)
        win_info = client.send("Browser.getWindowForTarget")
        
        client.send("Browser.setWindowBounds", {
            "windowId": win_info["windowId"],
            "bounds": {"windowState": "normal"}
        })
        time.sleep(0.5) 
        
        client.send("Browser.setWindowBounds", {
            "windowId": win_info["windowId"],
            "bounds": {
                "left": int(x),
                "top": int(y),
                "width": int(w),
                "height": int(h)
            }
        })
    except Exception as e:
        print(f"[-] Không thể chỉnh vị trí cửa sổ (CDP Error): {e}")

# ==========================================
# 2. HÀM WORKER: XỬ LÝ ĐỘC LẬP CHO TỪNG PROFILE
# ==========================================
def run_single_profile(api, profile_id, profile_name, themes, slot_index, screen_w, screen_h, skip_youtube, skip_random_keywords, brain_type="none", phase="clean", fixed_target_s=0):
    print(f"\n[{profile_name}] 🚀 Đang yêu cầu API mở trình duyệt...")
    
    db = DatabaseHandler()

    # v1.4.0: đếm THỜI GIAN NGÂM của chu trình này (open -> dọn dẹp; lỗi/dừng vẫn ghi).
    # Số liệu ghi vào SLOT_CYCLE_INFO theo slot (mỗi luồng 1 khóa riêng — không race).
    _cyc_t0 = time.time()
    _cyc_key = f"Slot {slot_index + 1}"
    _cyc = SLOT_CYCLE_INFO.setdefault(_cyc_key, {})
    _cyc["start_str"] = datetime.datetime.fromtimestamp(_cyc_t0).isoformat(timespec="seconds")
    _cyc["status"] = "ok"
    _cyc["error"] = None
    _cyc["actions"] = 0
    _cyc["phase"] = phase
    _cyc.pop("duration_s", None)
    _cyc.pop("target_s", None)

    # Khởi tạo AI Brain nếu được chọn
    brain = None
    if brain_type and brain_type != "none":
        try:
            brain = BrainManager.get_brain(brain_type)
            print(f"[{profile_name}] 🧠 Đã kích hoạt AI Brain: {brain_type}")
        except Exception as e:
            print(f"[{profile_name}] ⚠️ Không thể khởi tạo AI Brain ({e}), dùng từ khóa thủ công.")
    
    try:
        # needs_sub (mua/nhuận YouTube) CHỈ bật ở Pha 3 - ngam YouTube
        needs_sub = (phase == "youtube") and db.can_subscribe_today(profile_id)
        ws_url = api.open_profile(profile_id)
        
        if not ws_url:
            _cyc["status"] = "error"  # v1.4.0: mở profile thất bại — vẫn ghi chu trình
            _cyc["error"] = "Khong lay duoc WebSocket URL"
            print(f"[{profile_name}] ❌ Lỗi: Không thể lấy WebSocket URL.")
            return

        controller = BrowserController(ws_url)
        if controller.connect():
            context = controller.browser.contexts[0]
            
            print(f"[{profile_name}] ✅ Đã kết nối Playwright thành công. Đang thiết lập màn hình...")
            time.sleep(2)
            adjust_window_bounds(context, slot_index, screen_w, screen_h)
            time.sleep(1)
            
            session_theme = random.choice(themes)
            print(f"[{profile_name}] ⚙️ Kích hoạt hệ thống với chủ đề: {session_theme['google_query']}")
            
            warmup = WarmupWorkflow(
                context=context, 
                db_handler=db, 
                profile_id=profile_id, 
                needs_sub=needs_sub,
                session_theme=session_theme,
                skip_youtube=skip_youtube,
                skip_random_keywords=skip_random_keywords,
                brain=brain,
                phase=phase,
                should_stop=STOP_EVENT.is_set
            )
            
            total_actions = random.randint(4, 8)
            _cyc["actions"] = total_actions  # v1.4.0: ghi vào row chu trình
            # v1.4.1: MỤC TIÊU NGẪU NHIÊN cho RIÊNG vòng này — bot tự quyết, không ngày nào
            # giống ngày nào, không profile nào giống profile nào (dùng random global,
            # khác hoàn toàn giữa các luồng). 0 = vòng này không đặt mục tiêu.
            if fixed_target_s and fixed_target_s > 0:
                target_s = int(fixed_target_s)  # người dùng ghim số phút cố định
                _cyc["target_s"] = target_s
                print(f"[{profile_name}] 🎯 Mục tiêu vòng (cố định): {_fmt_dur(target_s)}")
            else:
                _auto_min = max(1, total_actions - 1)
                target_s = random.randint(0, _auto_min) * 60
                _cyc["target_s"] = target_s if target_s else None
                if target_s:
                    print(f"[{profile_name}] 🎲 Mục tiêu vòng (ngẫu nhiên): {_fmt_dur(target_s)}")
                else:
                    print(f"[{profile_name}] 🎲 Vòng này không đặt mục tiêu (ngẫu nhiên = 0).")
            warmup.run_random_session(total_actions=total_actions)
            
    except Exception as e:
        _cyc["status"] = "error"  # v1.4.0
        _cyc["error"] = str(e)[:300]
        print(f"[{profile_name}] ❌ Lỗi quá trình chạy: {e}")
    finally:
        # v1.4.0: chốt số liệu chu trình — worker_wrapper (finally ngoài) đọc để ghi DB.
        # return sớm (ws_url lỗi) cũng đi qua đây -> duration vẫn được ghi.
        try:
            _cyc["duration_s"] = round(time.time() - _cyc_t0, 1)
            _cyc["finish_str"] = datetime.datetime.now().isoformat(timespec="seconds")
            if STOP_EVENT.is_set():
                _cyc["status"] = "stopped"
        except Exception:
            pass
        print(f"[{profile_name}] 🧹 Đang dọn dẹp và đóng Profile...")
        try: controller.close()
        except: pass
        try: api.close_profile(profile_id)
        except Exception as e: print(f"[{profile_name}] ❌ Lỗi khi đóng profile: {e}")
        # Khi Stop: bỏ giấc ngủ xếp hàng 2s để các luồng còn lại đóng nhanh
        if not STOP_EVENT.is_set():
            time.sleep(2)

def worker_wrapper(app_instance, profile_id, themes, slots_queue, screen_w, screen_h, skip_youtube, skip_random_keywords, browser_type=BROWSER_GPM, api_port="", brain_type="none", phase="clean", fixed_target_s=0):
    if STOP_EVENT.is_set():
        print(f"[Skip] Người dùng đã yêu cầu dừng - bỏ qua profile {profile_id[:8]}.")
        return
    slot = slots_queue.get() 
    if STOP_EVENT.is_set():
        print(f"[Skip] Người dùng đã yêu cầu dừng - bỏ qua profile {profile_id[:8]}.")
        slots_queue.put(slot)
        return
    slot_key = f"Slot {slot + 1}"
    THREAD_SLOTS[threading.get_ident()] = slot_key
    SLOT_PROFILE[slot_key] = profile_id  # Task 5: route log của slot này vào file profile
    SLOT_LAST_LOG[slot_key] = time.time()
    SLOT_CYCLE_START[slot_key] = time.time()  # v1.4.0: mốc bắt đầu chu trình (đếm giờ ngâm live)
    SLOT_THREAD_ALIVE[slot_key] = True
    try:
        # Truyền port tùy chỉnh vào factory nếu có
        kwargs = {}
        if api_port:
            try:
                port_int = int(api_port)
                if browser_type == BROWSER_GPM:
                    kwargs["base_url"] = f"http://localhost:{port_int}"
                elif browser_type == BROWSER_BITBROWSER:
                    kwargs["port"] = port_int
            except ValueError:
                pass

        # v1.2.9: phần khởi tạo API từng nằm NGOÀI try/finally -> exception ở đây
        # làm future ném lỗi lên run_thread_pool (UI kẹt vĩnh viễn) VÀ slot không
        # bao giờ được trả về slots_queue (các luồng còn lại đói slot).
        try:
            api = BrowserFactory.get_api(browser_type, **kwargs)
            profile_name = api.get_profile_name(profile_id) if hasattr(api, 'get_profile_name') else profile_id[:8]
        except Exception as e:
            print(f"[!] Không khởi tạo được API anti-detect cho {profile_id[:8]}: {e}")
            return  # finally bên dưới vẫn chạy -> trả slot + dọn SLOT_* maps
        SLOT_LABEL[slot_key] = profile_name

        app_instance.update_tab_name(slot, profile_name)

        run_single_profile(api, profile_id, profile_name, themes, slot, screen_w, screen_h, skip_youtube, skip_random_keywords, brain_type, phase, fixed_target_s)
    finally:
        SLOT_THREAD_ALIVE[slot_key] = False
        # v1.4.0: ghi chu trình vào DB (kể cả dừng/lỗi giữa chừng — số liệu trung thực).
        # Bỏ qua nếu run_single_profile chưa kịp chốt số liệu (API chết ngay -> không có gì để đếm).
        SLOT_CYCLE_START.pop(slot_key, None)
        cyc = SLOT_CYCLE_INFO.pop(slot_key, None)
        if cyc and cyc.get("duration_s") is not None:
            try:
                DatabaseHandler().log_cycle(
                    profile_id, cyc.get("start_str", ""), cyc.get("finish_str", ""),
                    cyc.get("duration_s"), cyc.get("status", "ok"),
                    cyc.get("actions", 0), cyc.get("phase", ""), cyc.get("error"),
                    cyc.get("target_s"))
                tgt = cyc.get("target_s")
                tgt_txt = f" · mục tiêu {_fmt_dur(tgt)}" if tgt else ""
                print(f"[{profile_id[:8]}] [*] Chu trình xong: {_fmt_dur(cyc.get('duration_s'))}"
                      f" — {cyc.get('status', 'ok')}, {cyc.get('actions', 0)} hành động{tgt_txt}")
            except Exception as e:
                print(f"[!] log_cycle lỗi (bỏ qua): {e}")
        SLOT_PROFILE.pop(slot_key, None)
        SLOT_LABEL.pop(slot_key, None)
        app_instance.update_tab_name(slot, f"Slot {slot + 1}")
        slots_queue.put(slot)

# ==========================================
# 3. GIAO DIỆN NGƯỜI DÙNG
# ==========================================
class AutomationApp:
    # ============ v1.3.7: DESIGN SYSTEM SÁNG/TỐI — đổi theme nóng, lưu vào config ============
    # Tên key = đúng tên attr self.C_* mà toàn app đang dùng. Các key cũ giữ nguyên tên
    # (tương thích ngược); nhóm key MỚI thêm cho layout mới: C_CARD2 (bề mặt nổi),
    # C_HEADER_BG/FG (dải tiêu đề), C_ACCENT_2/C_ACCENT_SOFT (nhánh phụ / nền nhóm),
    # C_ROW_HOVER (hover dòng), C_PILL_BG/FG (badge), C_OK_FG/C_WARN_FG (mức log).
    # QUY TẮC: mỗi key một mã màu ĐỘC NHẤT trong từng theme — _toggle_theme remap màu
    # theo hex cũ->mới, hai key trùng hex mà ánh xạ khác nhau sẽ làm lệch màu widget.
    THEMES = {
        "dark": {
            "C_BG": "#14171c", "C_CARD": "#1b1f26", "C_CARD2": "#21262e",
            "C_FIELD": "#262c36",
            "C_FG": "#e8ebf1", "C_MUTED": "#94a0b4", "C_ACCENT": "#57a8f5",
            "C_ACCENT_2": "#34d0b6", "C_ACCENT_SOFT": "#1d3648",
            "C_BORDER": "#2d333d",
            "C_HEADER_BG": "#0f1216", "C_HEADER_FG": "#dfe4ec",
            "C_BTN": "#2a303a", "C_BTN_ACTIVE": "#363d49", "C_BTN_FG": "#dce1ea",
            "C_DISABLED_BG": "#1f242b", "C_DISABLED_FG": "#5c6470",
            "C_SEL": "#0b4a86", "C_SEL_FG": "#ffffff",
            "C_TAB": "#171b21", "C_TAB_FG": "#98a2b3",
            "C_HEADING_BG": "#232932", "C_HEADING_FG": "#cfd6e0",
            "C_SCROLL": "#3a414c", "C_SCROLL_ACTIVE": "#4d5563",
            "C_STATUS_BG": "#101319", "C_STATUS_FG": "#9fd6f2",
            "C_LOG_FG": "#b9dfa0", "C_ERR_FG": "#f1866f", "C_PID_FG": "#7c8794",
            "C_HB_GREEN": "#57d38c", "C_HB_YELLOW": "#e0b455", "C_HB_RED": "#f1706c",
            "C_START_BG": "#238636", "C_START_ACTIVE": "#2ea043",
            "C_STOP_BG": "#a1261d", "C_STOP_ACTIVE": "#c9372c",
            "C_ROW_HOVER": "#252b34", "C_PILL_BG": "#232a33", "C_PILL_FG": "#a8d4ff",
            "C_OK_FG": "#63d18f", "C_WARN_FG": "#e6bf62",
        },
        "light": {
            "C_BG": "#e9edf2", "C_CARD": "#ffffff", "C_CARD2": "#f2f5f9",
            "C_FIELD": "#fbfcfe",
            "C_FG": "#1b2229", "C_MUTED": "#5f6b7a", "C_ACCENT": "#0a66c2",
            "C_ACCENT_2": "#0f8a70", "C_ACCENT_SOFT": "#dcebf9",
            "C_BORDER": "#d0d7e1",
            "C_HEADER_BG": "#f7f9fc", "C_HEADER_FG": "#16202b",
            "C_BTN": "#e6eaf0", "C_BTN_ACTIVE": "#d8dee8", "C_BTN_FG": "#22303f",
            "C_DISABLED_BG": "#eef1f5", "C_DISABLED_FG": "#a3abb6",
            "C_SEL": "#cfe4fa", "C_SEL_FG": "#0b3d61",
            "C_TAB": "#dfe4ea", "C_TAB_FG": "#5b6675",
            "C_HEADING_BG": "#eef2f7", "C_HEADING_FG": "#3b4654",
            "C_SCROLL": "#c2cad6", "C_SCROLL_ACTIVE": "#a2adbc",
            "C_STATUS_BG": "#dfe5ec", "C_STATUS_FG": "#0b4d8f",
            "C_LOG_FG": "#14603a", "C_ERR_FG": "#b42318", "C_PID_FG": "#8791a0",
            "C_HB_GREEN": "#0b7a3b", "C_HB_YELLOW": "#8a6d1f", "C_HB_RED": "#c0392b",
            "C_START_BG": "#1a7f37", "C_START_ACTIVE": "#21a04a",
            "C_STOP_BG": "#b3352f", "C_STOP_ACTIVE": "#cb4a44",
            "C_ROW_HOVER": "#eaf1fb", "C_PILL_BG": "#e8eff8", "C_PILL_FG": "#0b5394",
            "C_OK_FG": "#157f3d", "C_WARN_FG": "#9a7b12",
        },
    }

    def _apply_theme(self, name):
        """v1.3.3: nạp 1 bảng màu vào attr instance self.C_* (giữ đúng tên cũ, mọi chỗ khác không đổi)."""
        self.theme_name = name if name in self.THEMES else "dark"
        for k, v in self.THEMES[self.theme_name].items():
            setattr(self, k, v)

    def _theme_btn_text(self):
        """v1.3.4: nhãn nút theme = theme sẽ chuyển ĐẾN. v1.3.7: nút nằm ở header
        nên nhãn gọn lại còn 'NỀN SÁNG' / 'NỀN TỐI' (in hoa cho dễ thấy)."""
        return ("NỀN SÁNG" if self.theme_name == "dark"
                else "NỀN TỐI")

    def _toggle_theme(self):
        """Đổi sáng<->tối NGAY LẬP TỨC: dựng lại style ttk + quét remap màu widget tk thuần
        (status bar, log, canvas, dialog đang mở...). Chỉ đổi giao diện — không đụng hành vi."""
        old_pal = {k: getattr(self, k) for k in self.THEMES["dark"]}
        self._apply_theme("light" if self.theme_name == "dark" else "dark")
        remap = {old_pal[k]: getattr(self, k) for k in old_pal
                 if old_pal[k] != getattr(self, k)}
        # v1.3.7: #ffffff là màu chữ trên nút CTA/logo — KHÔNG được remap (trắng là trắng
        # ở cả 2 theme; nếu không chữ logo bị đổi thành màu select của theme mới).
        remap.pop("#ffffff", None)
        self._setup_style()  # ttk đổi màu tức thì toàn bộ (kể cả Treeview trong dialog đang mở)
        for w in [self.root] + [c for c in self.root.winfo_children()
                                if isinstance(c, tk.Toplevel)]:
            self._remap_colors(w, remap)
        # status bar set tường minh (màu idle của nó trùng giá trị với heartbeat xanh palette cũ)
        self.lbl_status.config(bg=self.C_STATUS_BG, fg=self.C_STATUS_FG)
        try:
            self.chk_theme.config(text=self._theme_btn_text())
        except Exception:
            pass
        # lưu ngay best-effort (không chờ đóng app)
        self.cfg = dict(self.cfg)
        self.cfg["theme"] = self.theme_name
        save_config(self.cfg)

    def _remap_colors(self, widget, remap):
        """Đệ quy đổi màu nền/chữ cho widget tk thuần theo bảng old->new. ttk tự skip
        (không có option 'bg'/'fg' rút gọn) — style ttk đã được dựng lại."""
        try:
            opts = widget.configure()
        except tk.TclError:
            return
        # v1.3.7: thêm active* — nút tk thuần trên header (theme) có hover color riêng
        for opt in ("bg", "fg", "insertbackground", "highlightbackground",
                    "activebackground", "activeforeground"):
            if opt not in opts:
                continue
            try:
                cur = str(widget.cget(opt))
            except tk.TclError:
                continue
            if cur in remap:
                try:
                    widget.configure(**{opt: remap[cur]})
                except tk.TclError:
                    pass
        for c in widget.winfo_children():
            self._remap_colors(c, remap)

    def _setup_style(self):
        """v1.3.7: design system — mọi màu dẫn xuất từ palette theme hiện hành (self.C_*).
        Nút phẳng padding rộng, entry focus viền accent, Treeview thoáng (28px), scrollbar
        mảnh, tab log chữ đậm, checkbutton dòng có style hover. ttk styles toàn cục nên
        _toggle_theme gọi lại hàm này là đổi màu tức thì cả app (kể cả dialog đang mở).
        Chỉ đổi giao diện — KHÔNG đổi tên widget, hành vi hay luồng dữ liệu."""
        style = ttk.Style()
        style.theme_use("clam")
        try:
            tkfont.nametofont("TkDefaultFont").configure(family="Segoe UI", size=10)
        except Exception:
            pass
        P = self.THEMES[self.theme_name]
        B, CD, F, T, M, A, A2, BD = (self.C_BG, self.C_CARD, self.C_FIELD,
                                     self.C_FG, self.C_MUTED, self.C_ACCENT,
                                     self.C_ACCENT_2, self.C_BORDER)
        BTN, BTNA, BTNFG = P["C_BTN"], P["C_BTN_ACTIVE"], P["C_BTN_FG"]
        DBG, DFG = P["C_DISABLED_BG"], P["C_DISABLED_FG"]
        SEL, SELFG = P["C_SEL"], P["C_SEL_FG"]
        TAB, TABFG = P["C_TAB"], P["C_TAB_FG"]
        HB, HF = P["C_HEADING_BG"], P["C_HEADING_FG"]
        SC, SCA = P["C_SCROLL"], P["C_SCROLL_ACTIVE"]
        HR = P["C_ROW_HOVER"]
        self.root.configure(bg=B)

        # ---- Khung & nhãn ----
        style.configure("TFrame", background=CD)
        style.configure("Outer.TFrame", background=B)
        style.configure("TLabel", background=CD, foreground=T)
        style.configure("Outer.TLabel", background=B, foreground=T)
        style.configure("Muted.TLabel", background=CD, foreground=M)
        style.configure("Accent.TLabel", background=CD, foreground=A2,
                        font=("Segoe UI", 9, "bold"))

        # ---- Thẻ khu vực ----
        style.configure("TLabelframe", background=CD, bordercolor=BD, relief="flat",
                        padding=(12, 10))
        style.configure("TLabelframe.Label", background=CD, foreground=A,
                        font=("Segoe UI", 10, "bold"))

        # ---- Checkbutton ----
        style.configure("TCheckbutton", background=CD, foreground=T,
                        activebackground=CD, activeforeground=T, padding=(2, 3))
        style.map("TCheckbutton", background=[("active", CD)],
                  foreground=[("disabled", DFG)])
        # 2 style tĩnh cho dòng checklist — _add_profile_row đổi tên style khi mouse vào/ra
        for nm, bgc in (("Row.TCheckbutton", CD), ("RowHover.TCheckbutton", HR)):
            style.configure(nm, background=bgc, foreground=T,
                            activebackground=bgc, activeforeground=T, padding=(4, 2))
            style.map(nm, background=[("active", bgc)], foreground=[("disabled", DFG)])

        # ---- Nút ----
        style.configure("TButton", background=BTN, foreground=BTNFG,
                        bordercolor=BD, lightcolor=BTN, darkcolor=BTN,
                        arrowcolor=BTNFG, focuscolor=A, padding=(12, 6),
                        font=("Segoe UI", 10))
        style.map("TButton",
                  background=[("pressed", BTNA), ("active", BTNA), ("disabled", DBG)],
                  foreground=[("disabled", DFG)])
        style.configure("Tool.TButton", padding=(9, 4), font=("Segoe UI", 9))
        style.configure("Start.TButton", background=P["C_START_BG"], foreground="#ffffff",
                        lightcolor=P["C_START_BG"], darkcolor=P["C_START_BG"],
                        bordercolor=P["C_START_BG"],
                        font=("Segoe UI", 12, "bold"), padding=(10, 12))
        style.map("Start.TButton",
                  background=[("active", P["C_START_ACTIVE"]), ("disabled", DBG)],
                  foreground=[("disabled", DFG)])
        style.configure("Stop.TButton", background=P["C_STOP_BG"], foreground="#ffffff",
                        lightcolor=P["C_STOP_BG"], darkcolor=P["C_STOP_BG"],
                        bordercolor=P["C_STOP_BG"],
                        font=("Segoe UI", 11, "bold"), padding=(10, 8))
        style.map("Stop.TButton",
                  background=[("active", P["C_STOP_ACTIVE"]), ("disabled", DBG)],
                  foreground=[("disabled", DFG)])

        # ---- Nhập liệu ----
        style.configure("TEntry", fieldbackground=F, foreground=T, insertcolor=A,
                        bordercolor=BD, lightcolor=F, darkcolor=F, padding=6)
        style.map("TEntry", bordercolor=[("focus", A)], lightcolor=[("focus", F)],
                  darkcolor=[("focus", F)], state=[("readonly", F)])
        style.configure("TCombobox", fieldbackground=F, background=BTN,
                        foreground=T, arrowcolor=T, bordercolor=BD,
                        lightcolor=F, darkcolor=F, padding=5, arrowsize=14)
        style.map("TCombobox", fieldbackground=[("readonly", F), ("disabled", DBG)],
                  foreground=[("readonly", T), ("disabled", DFG)],
                  arrowcolor=[("disabled", DFG)],
                  bordercolor=[("focus", A)])
        style.configure("TSpinbox", fieldbackground=F, foreground=T, insertcolor=A,
                        bordercolor=BD, lightcolor=F, darkcolor=F,
                        arrowcolor=T, padding=5, arrowsize=13)
        style.map("TSpinbox", arrowcolor=[("disabled", DFG)],
                  bordercolor=[("focus", A)])

        # ---- Notebook (tab log) ----
        style.configure("TNotebook", background=B, bordercolor=BD,
                        tabmargins=(10, 6, 10, 0))
        style.configure("TNotebook.Tab", background=TAB, foreground=TABFG,
                        padding=(16, 6), bordercolor=B,
                        font=("Segoe UI", 9, "bold"))
        style.map("TNotebook.Tab", background=[("selected", B)],
                  foreground=[("selected", A)])

        # ---- Bảng dữ liệu (Treeview) ----
        style.configure("Treeview", background=CD, fieldbackground=CD, foreground=T,
                        rowheight=28, bordercolor=BD, borderwidth=0,
                        font=("Segoe UI", 10))
        style.configure("Treeview.Heading", background=HB, foreground=HF,
                        font=("Segoe UI", 9, "bold"), relief="flat", padding=(8, 7))
        style.map("Treeview", background=[("selected", SEL)],
                  foreground=[("selected", SELFG)])

        # ---- Thanh cuộn mảnh ----
        for side in ("Vertical", "Horizontal"):
            style.configure(f"{side}.TScrollbar", background=SC, troughcolor=CD,
                            bordercolor=CD, arrowcolor=T, relief="flat",
                            arrowsize=10, width=11)
            style.map(f"{side}.TScrollbar", background=[("active", SCA)])
        style.configure("TSeparator", background=BD)
        style.configure("TSizegrip", background=B)

        # Listbox popup của Combobox (không phải TTK -> tô bằng option_add)
        self.root.option_add("*TCombobox*Listbox*Background", F)
        self.root.option_add("*TCombobox*Listbox*Foreground", T)
        self.root.option_add("*TCombobox*Listbox*selectBackground", SEL)
        self.root.option_add("*TCombobox*Listbox*selectForeground", SELFG)

    def __init__(self, root):
        self.root = root
        self.cfg = load_config()  # Sprint 1.1: cấu hình phiên trước (best-effort)
        self._version_line = get_version_line()
        self.root.title(f"GPM Automation Tool {self._version_line}")
        # v1.3.2: cửa sổ rộng hơn + co giãn được; cao tối đa theo vùng làm việc
        # (trừ taskbar ~50px) để status bar không bao giờ bị che, căn giữa màn hình.
        _sw = self.root.winfo_screenwidth()
        _sh = self.root.winfo_screenheight()
        _w = min(1180, _sw - 40)
        _h = min(840, _sh - 100)
        self.root.geometry(f"{_w}x{_h}+{max(0, (_sw - _w) // 2)}+{max(0, (_sh - 50 - _h) // 2)}")
        self.root.minsize(1040, 700)
        # v1.3.3: nạp bảng màu SÁNG/TỐI đã lưu (mặc định tối như cũ) TRƯỚC khi dựng style
        self._apply_theme(self.cfg.get("theme", "dark"))
        self._setup_style()

        # ============ v1.3.7: HEADER ĐỊNH DANH + LƯỚI THẺ 2 CỘT + TAB LOG ============
        # Chỉ đổi trình bày/tên gọi style — giữ 100% tên widget attr, command, bind,
        # biến điều khiển (start/stop/report/dashboard/... hoạt động y như cũ).
        # --- Dải tiêu đề: logo + tên app + version pill + nút đổi theme ---
        hdr = tk.Frame(root, bg=self.C_HEADER_BG, height=58)
        hdr.pack(fill="x", side="top")
        hdr.pack_propagate(False)
        tk.Label(hdr, text="GPM", bg=self.C_ACCENT, fg="#ffffff",
                 font=("Segoe UI", 14, "bold"), width=4, pady=2).pack(
            side="left", padx=(14, 10), pady=12)
        tk.Label(hdr, text="Auto Nuôi Tài khoản", bg=self.C_HEADER_BG,
                 fg=self.C_HEADER_FG,
                 font=("Segoe UI", 14, "bold")).pack(side="left")
        tk.Label(hdr, text="warmup · fingerprint · anti-detect",
                 bg=self.C_HEADER_BG, fg=self.C_MUTED,
                 font=("Segoe UI", 9, "italic")).pack(side="left", padx=(10, 0), pady=(5, 0))
        tk.Label(hdr, text=self._version_line, bg=self.C_PILL_BG, fg=self.C_PILL_FG,
                 font=("Consolas", 9), padx=8, pady=3).pack(side="right", padx=(8, 14))
        # v1.3.7: nút theme lên header (tk.Button phẳng, cùng họ màu dải tiêu đề)
        self.chk_theme = tk.Button(hdr, command=self._toggle_theme,
                                   text=self._theme_btn_text(),
                                   bg=self.C_BTN, fg=self.C_BTN_FG,
                                   activebackground=self.C_BTN_ACTIVE,
                                   activeforeground=self.C_BTN_FG,
                                   relief="flat", bd=0, cursor="hand2",
                                   font=("Segoe UI", 9, "bold"), padx=12, pady=5,
                                   highlightthickness=1,
                                   highlightbackground=self.C_BORDER)
        self.chk_theme.pack(side="right", padx=(0, 2))
        tk.Frame(root, bg=self.C_BORDER, height=1).pack(fill="x")

        # --- Lưới 2 cột: trái = checklist (trục chính), phải = cấu hình + điều khiển ---
        outer = ttk.Frame(root, style="Outer.TFrame")
        outer.pack(fill="x", side="top", padx=12, pady=(12, 0))
        outer.columnconfigure(0, weight=11)
        outer.columnconfigure(1, weight=9)

        # ---------- Thẻ trái: checklist tài khoản (giữ nguyên hành vi 1.3/1.6/1.3.6) ----------
        card_prof = ttk.Labelframe(outer, text="  TÀI KHOẢN SẼ NGÂM  ", padding=(12, 8))
        card_prof.grid(row=0, column=0, sticky="nsew", padx=(0, 10), pady=(0, 10))

        prof_head = ttk.Frame(card_prof)
        prof_head.pack(fill="x")
        self.lbl_prof_count = ttk.Label(prof_head, text="0 chọn", style="Accent.TLabel")
        self.lbl_prof_count.pack(side="left", pady=(2, 0))
        self.btn_refresh_profiles = ttk.Button(prof_head, text="Tải từ GPM", command=self.load_profiles_from_api, style="Tool.TButton", width=12)
        self.btn_refresh_profiles.pack(side="right", padx=(6, 0))
        self.btn_add_manual = ttk.Button(prof_head, text="Dán ID thủ công", command=self.open_manual_add_dialog, style="Tool.TButton", width=15)
        self.btn_add_manual.pack(side="right", padx=(6, 0))
        ttk.Button(prof_head, text="Bỏ hết", command=lambda: self._set_all_profiles(False), style="Tool.TButton", width=8).pack(side="right", padx=(6, 0))
        ttk.Button(prof_head, text="Chọn tất cả", command=lambda: self._set_all_profiles(True), style="Tool.TButton", width=11).pack(side="right", padx=(6, 0))

        # Lọc nhanh khi danh sách dài (tìm theo tên hoặc ID) + lọc theo nhóm (v1.3.6)
        prof_filter_row = ttk.Frame(card_prof)
        prof_filter_row.pack(fill="x", pady=(8, 2))
        self._lbl_group_filter = ttk.Label(prof_filter_row, text="Nhóm:", style="Muted.TLabel")
        self.var_prof_group = tk.StringVar(value=GROUP_ALL)
        self.cbo_prof_group = ttk.Combobox(prof_filter_row, textvariable=self.var_prof_group,
                                           values=[GROUP_ALL], state="readonly", width=18)
        self.cbo_prof_group.bind("<<ComboboxSelected>>", self._filter_profiles)
        # chưa hiển thị ở đây — _populate_group_filter quyết định sau khi có dòng
        self._lbl_filter_text = ttk.Label(prof_filter_row, text="Lọc:", style="Muted.TLabel")
        self._lbl_filter_text.pack(side="left")
        self.var_prof_filter = tk.StringVar()
        ent_filter = ttk.Entry(prof_filter_row, textvariable=self.var_prof_filter, width=30)
        ent_filter.pack(side="left", padx=(6, 0), fill="x", expand=True)
        ent_filter.bind("<KeyRelease>", self._filter_profiles)

        prof_box = ttk.Frame(card_prof)
        prof_box.pack(fill="both", expand=True, pady=(4, 2))
        self.prof_canvas, self.prof_inner = self._make_scrollable(prof_box, 300)
        # v1.3.6: mỗi dòng thêm "group" (tên nhóm GPM, "" = chưa có) + "hidden" (lọc đang ẩn)
        self.profile_rows = []  # [{"id", "name", "firefox", "var", "frame", "group", "hidden"}]
        self._group_headers = {}  # tên nhóm -> {"group", "frame", "count"} (label header)
        self._rebuild_profile_rows(self.cfg.get("profiles") or [])

        # ---------- Cột phải: 2 thẻ chồng nhau (cấu hình + điều khiển) ----------
        right = ttk.Frame(outer, style="Outer.TFrame")
        right.grid(row=0, column=1, sticky="nsew", pady=(0, 10))

        card_cfg = ttk.Labelframe(right, text="  CẤU HÌNH CHẠY  ", padding=(12, 8))
        card_cfg.pack(fill="x", pady=(0, 10))
        card_cfg.columnconfigure(1, weight=1)

        ttk.Label(card_cfg, text="Browser:").grid(row=0, column=0, sticky="w", pady=(2, 0))
        cfg_line1 = ttk.Frame(card_cfg)
        cfg_line1.grid(row=0, column=1, sticky="w", padx=(10, 0))
        self.var_browser_type = tk.StringVar(value=BROWSER_GPM)
        self.cbo_browser = ttk.Combobox(cfg_line1, textvariable=self.var_browser_type,
                                        values=[BROWSER_GPM, BROWSER_BITBROWSER],
                                        state="readonly", width=12)
        self.cbo_browser.pack(side="left")
        self.cbo_browser.bind("<<ComboboxSelected>>", self._on_browser_type_changed)
        ttk.Label(cfg_line1, text="Port:").pack(side="left", padx=(12, 4))
        self.var_api_port = tk.StringVar(value="9495")
        self.txt_api_port = ttk.Entry(cfg_line1, textvariable=self.var_api_port, width=7)
        self.txt_api_port.pack(side="left")
        self.lbl_browser_hint = ttk.Label(card_cfg, text="(GPM Login - Port 9495)", style="Muted.TLabel")
        self.lbl_browser_hint.grid(row=1, column=1, sticky="w", padx=(10, 0))

        ttk.Label(card_cfg, text="AI Brain:").grid(row=2, column=0, sticky="w", pady=(8, 0))
        self.var_brain_type = tk.StringVar(value="none")
        self.cbo_brain = ttk.Combobox(card_cfg, textvariable=self.var_brain_type,
                                      values=["none", "gemini", "openai", "qwen-max", "qwen-flash", "local"],
                                      state="readonly", width=13)
        self.cbo_brain.grid(row=2, column=1, sticky="w", padx=(10, 0), pady=(8, 0))
        self.lbl_brain_hint = ttk.Label(card_cfg, text="(Tắt AI - dùng từ khóa thủ công)", style="Muted.TLabel")
        self.lbl_brain_hint.grid(row=3, column=1, sticky="w", padx=(10, 0))
        self.cbo_brain.bind("<<ComboboxSelected>>", self._on_brain_type_changed)

        ttk.Label(card_cfg, text="Chế độ ngâm:").grid(row=4, column=0, sticky="w", pady=(8, 0))
        self.var_phase_label = tk.StringVar(value=PHASE_LABELS[0])
        # v1.3.8: combobox + nút "CHI TIẾT" mở tài liệu 3 chế độ ngâm (thuần UI)
        phase_line = ttk.Frame(card_cfg)
        phase_line.grid(row=4, column=1, sticky="w", padx=(10, 0), pady=(8, 0))
        self.cbo_phase = ttk.Combobox(phase_line, textvariable=self.var_phase_label,
                                      values=PHASE_LABELS, state="readonly", width=26)
        self.cbo_phase.pack(side="left")
        self.btn_phase_info = ttk.Button(phase_line, text="CHI TIẾT",
                                         command=self.show_phase_details,
                                         style="Tool.TButton", width=8)
        self.btn_phase_info.pack(side="left", padx=(6, 0))
        self.cbo_phase.bind("<<ComboboxSelected>>", self._on_phase_changed)
        self.lbl_phase_hint = ttk.Label(card_cfg, text="", style="Muted.TLabel",
                                        wraplength=360, justify="left")
        self.lbl_phase_hint.grid(row=5, column=1, sticky="w", padx=(10, 0))
        self._on_phase_changed()  # set hint ban đầu theo pha mặc định

        ttk.Label(card_cfg, text="Số luồng:").grid(row=6, column=0, sticky="w", pady=(10, 0))
        self.spin_threads = ttk.Spinbox(card_cfg, from_=1, to=20, width=5)
        self.spin_threads.grid(row=6, column=1, sticky="w", padx=(10, 0), pady=(10, 0))
        self.spin_threads.set(4)

        # v1.4.0: mục tiêu thời lượng 1 chu trình (phút).
        # v1.4.1: 0 = BOT TỰ RANDOM mỗi vòng (mỗi profile/vòng một số khác nhau — mặc định);
        #         >0 = ghim số phút cố định cho mọi vòng (dùng khi muốn soi 1 mốc).
        # Dùng cho: ⏰ trên heartbeat/Bảng + cột 'Qua mục tiêu' trong dialog Thời gian ngâm.
        ttk.Label(card_cfg, text="Mục tiêu vòng:").grid(row=9, column=0, sticky="w", pady=(10, 0))
        tgt_line = ttk.Frame(card_cfg)
        tgt_line.grid(row=9, column=1, sticky="w", padx=(10, 0), pady=(10, 0))
        self.spin_target_min = ttk.Spinbox(tgt_line, from_=0, to=600, width=5)
        self.spin_target_min.pack(side="left")
        ttk.Label(tgt_line, text="phút/vòng (0 = bot tự random)", style="Muted.TLabel").pack(side="left", padx=(6, 0))

        self.var_skip_youtube = tk.BooleanVar(value=False)
        self.chk_skip_youtube = ttk.Checkbutton(card_cfg, text="Bỏ qua xem YouTube",
                                                variable=self.var_skip_youtube,
                                                command=self._on_phase_changed)
        self.chk_skip_youtube.grid(row=7, column=0, columnspan=2, sticky="w", pady=(10, 0))
        self.var_skip_random_keywords = tk.BooleanVar(value=False)
        self.chk_skip_random_keywords = ttk.Checkbutton(card_cfg, text="Bỏ qua từ khóa ngẫu nhiên",
                                                        variable=self.var_skip_random_keywords)
        self.chk_skip_random_keywords.grid(row=8, column=0, columnspan=2, sticky="w", pady=(3, 0))

        # ---------- Thẻ điều khiển: CTA chạy/dừng + lưới tiện ích ----------
        card_ctl = ttk.Labelframe(right, text="  ĐIỀU KHIỂN  ", padding=(12, 8))
        card_ctl.pack(fill="x")
        for c in range(3):
            card_ctl.columnconfigure(c, weight=1)

        self.btn_start = ttk.Button(card_ctl, text="BẮT ĐẦU CHẠY", command=self.start_automation,
                                    style="Start.TButton")
        self.btn_start.grid(row=0, column=0, columnspan=3, sticky="we", pady=(2, 6))
        self.btn_stop = ttk.Button(card_ctl, text="DỪNG AN TOÀN", command=self.request_stop_all,
                                   state="disabled", style="Stop.TButton")
        self.btn_stop.grid(row=1, column=0, columnspan=3, sticky="we", pady=(0, 8))
        ttk.Separator(card_ctl).grid(row=2, column=0, columnspan=3, sticky="we", pady=(0, 8))

        self.btn_report = ttk.Button(card_ctl, text="Báo cáo", command=self.show_activity_report,
                                     style="Tool.TButton")
        self.btn_report.grid(row=3, column=0, sticky="we", padx=(0, 5), pady=2)
        self.btn_dashboard = ttk.Button(card_ctl, text="Bảng tài khoản", command=self.show_account_dashboard,
                                        style="Tool.TButton")
        self.btn_dashboard.grid(row=3, column=1, sticky="we", padx=5, pady=2)
        self.btn_export_csv = ttk.Button(card_ctl, text="Xuất CSV", command=self.export_activity_csv,
                                         style="Tool.TButton")
        self.btn_export_csv.grid(row=3, column=2, sticky="we", padx=(5, 0), pady=2)
        self.btn_open_logs = ttk.Button(card_ctl, text="Mở thư mục Log", command=self.open_logs_folder,
                                        style="Tool.TButton")
        self.btn_open_logs.grid(row=4, column=0, columnspan=2, sticky="we", padx=(0, 5), pady=2)
        self.btn_load_keywords = ttk.Button(card_ctl, text="Nạp keywords.txt", command=self.load_keywords_file,
                                            style="Tool.TButton")
        self.btn_load_keywords.grid(row=4, column=2, sticky="we", padx=(5, 0), pady=2)
        self.var_log_errors = tk.BooleanVar(value=False)
        self.chk_log_errors = ttk.Checkbutton(card_ctl, text="Chỉ hiện lỗi + cảnh báo trong log",
                                              variable=self.var_log_errors,
                                              command=self._apply_log_filter)
        self.chk_log_errors.grid(row=5, column=0, columnspan=3, sticky="w", pady=(8, 0))
        # v1.3.5: mốc nuôi acc 7 ngày — đặt ngày bắt đầu + nhắc tới giai đoạn LÀM TAY (lắp mail)
        # v1.3.7: nút theme đã lên header; timeline vẫn là nút hành động full-width cuối thẻ.
        self.btn_timeline = ttk.Button(card_ctl, text="MỐC NUÔI ACC (7 NGÀY)",
                                       command=self.show_stage_timeline, style="Tool.TButton")
        self.btn_timeline.grid(row=6, column=0, columnspan=3, sticky="we", pady=(8, 0))
        # v1.4.0: thời gian ngâm theo chu trình — tổng/TB/số vòng + chi tiết từng vòng
        self.btn_cycle_time = ttk.Button(card_ctl, text="THỜI GIAN NGÂM (CHU TRÌNH)",
                                         command=self.show_cycle_time_dialog, style="Tool.TButton")
        self.btn_cycle_time.grid(row=7, column=0, columnspan=3, sticky="we", pady=(6, 0))
        # v1.4.8: tiện ích API key có cổng mật khẩu — khỏi phải sửa .env tay
        self.btn_api_keys = ttk.Button(card_ctl, text="QUẢN LÝ API KEY (CẦN MẬT KHẨU)",
                                       command=self.open_api_key_manager, style="Tool.TButton")
        self.btn_api_keys.grid(row=8, column=0, columnspan=3, sticky="we", pady=(6, 0))

        # ---------- Thẻ ngang dưới: cặp từ khóa Google ↔ YouTube (hành vi 1.4 giữ nguyên) ----------
        card_kw = ttk.Labelframe(outer, text="  CẶP TỪ KHÓA — GOOGLE ↔ YOUTUBE  ", padding=(12, 8))
        card_kw.grid(row=1, column=0, columnspan=2, sticky="nsew", pady=(0, 6))
        kw_head = ttk.Frame(card_kw)
        kw_head.pack(fill="x")
        ttk.Label(kw_head, text="Mỗi dòng 1 chủ đề · YouTube trống sẽ dùng lại Google",
                  style="Muted.TLabel").pack(side="left")
        ttk.Button(kw_head, text="+ Thêm cặp", command=lambda: self._add_kw_row("", "", focus=True),
                   style="Tool.TButton", width=11).pack(side="right")
        # Header cột canh gần đúng 2 Entry (mỗi Entry expand đều, chừa chỗ nút X ~26px)
        kw_cols = ttk.Frame(card_kw)
        kw_cols.pack(fill="x", pady=(6, 1))
        ttk.Label(kw_cols, text="GOOGLE", foreground=self.C_ACCENT,
                  font=("Segoe UI", 8, "bold")).pack(side="left", fill="x", expand=True, padx=(1, 3))
        ttk.Label(kw_cols, text="YOUTUBE", foreground=self.C_ACCENT_2,
                  font=("Segoe UI", 8, "bold")).pack(side="left", fill="x", expand=True, padx=(3, 30))
        kw_box = ttk.Frame(card_kw)
        kw_box.pack(fill="both", expand=True, pady=(2, 2))
        self.kw_canvas, self.kw_inner = self._make_scrollable(kw_box, 96)
        self.kw_rows = []  # [{"g": Entry, "y": Entry, "frame": Frame}]
        _g_saved = self.cfg.get("kw_google") or []
        _y_saved = self.cfg.get("kw_youtube") or []
        if _g_saved or _y_saved:
            self._rebuild_kw_rows(_g_saved, _y_saved)
        else:
            self._add_kw_row("tin tức kinh tế vĩ mô", "global macro economics")
            self._add_kw_row("chứng khoán mỹ", "us stock market analysis")

        # ============ LOG + STATUS ============
        # --- STATUS BAR (Sprint 0.2): heartbeat các slot, màu theo trạng thái ---
        self._running = False
        self._active_slots = []
        self.var_status = tk.StringVar(value=f"Sẵn sàng · {self._version_line}")
        self.lbl_status = tk.Label(root, textvariable=self.var_status, anchor="w",
                                   bg=self.C_STATUS_BG, fg=self.C_STATUS_FG,
                                   font=("Segoe UI", 9),
                                   padx=10, pady=4)
        self.lbl_status.pack(side="bottom", fill="x")

        self.notebook = ttk.Notebook(root)
        self.notebook.pack(fill="both", expand=True, padx=10, pady=(4, 10))

        self.log_boxes = {}
        self._create_tab("MAIN")
        # v1.4.9: tab "THỜI LƯỢNG CHẠY" — LUÔN tạo SAU MAIN và được nối lại vào CUỐI
        # notebook mỗi lần Start, nên tabs()[slot_index + 1] của update_tab_name không lệch.
        self.board_frame = None
        self.var_board_days = None
        self._create_board_tab()

        sys.stdout = ThreadSafeStdout(self.append_log)

        # Sprint 1.1: khôi phục lựa chọn của phiên trước + tự lưu khi đóng app
        self._apply_loaded_config()
        # v1.4.8: nạp mọi key trong .env vào os.environ ngay khi mở app — brain
        # (dotenv + os.getenv) đọc được cả khi EXE chạy với cwd khác.
        try:
            _n_keys = api_vault.sync_env_into_process()
            print(f"[+] Đã nạp {_n_keys} API key từ .env vào phiên chạy.")
        except Exception as _e:
            print(f"[!] Nạp .env vào process lỗi (bỏ qua): {_e}")
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self._tick_status()
        # Sprint 1.6: mở app là tự kéo danh sách profile từ GPM (im lặng, nền) — khỏi để ô trống
        self.root.after(600, self._auto_load_profiles)
        # v1.3.5: mở app xong ~2s thì kiểm tra mốc nuôi acc — profile quá Ngày 4 mà chưa từng
        # nhắc -> popup 1 lần + ghi milestone_history (dedup, không spam mỗi phiên)
        self.root.after(2000, self.check_stage1_milestones)

    def _tick_status(self):
        """Sprint 0.2: 5s/lần dựng dòng heartbeat slot. 🟢<3 phút, 🟡 3-10 phút, 🔴 >10 phút im lặng, ⚪ xong.
        v1.4.0: kèm giờ ngâm live của chu trình (m=phút); vượt mục tiêu -> ⏰ (đếm đỏ).
        v1.4.1: mục tiêu dùng số RANDOM của chính vòng đang chạy (SLOT_CYCLE_INFO['target_s']),
        chỉ rơi về mục tiêu cố định khi vòng chưa kịp random (hoặc bản cũ không ghi)."""
        if self._running and self._active_slots:
            parts = []
            now = time.time()
            worst = "green"
            tgt_fixed = self._target_secs()  # 0 = bot tự random mỗi vòng
            for i in self._active_slots:
                key = f"Slot {i + 1}"
                name = (SLOT_LABEL.get(key) or SLOT_PROFILE.get(key, ""))[:8] or "?"
                # v1.4.0: thời lượng chu trình đang chạy (tính từ lúc slot nhận việc)
                t0 = SLOT_CYCLE_START.get(key)
                cyc_txt = ""
                over = False
                if t0:
                    el = int(now - t0)
                    cyc_txt = f" {_fmt_dur(el)}"
                    t_eff = SLOT_CYCLE_INFO.get(key, {}).get("target_s") or tgt_fixed
                    over = bool(t_eff) and el >= t_eff
                if not SLOT_THREAD_ALIVE.get(key, False):
                    parts.append(f"{key}:{name} ⚪xong")
                    continue
                age = int(now - SLOT_LAST_LOG.get(key, now))
                mark = "⏰" if over else ""
                if age < 180:
                    parts.append(f"{key}:{name} 🟢{age}s{cyc_txt}{mark}")
                    if over:
                        worst = "yellow" if worst == "green" else worst
                elif age < 600:
                    parts.append(f"{key}:{name} 🟡{age}s{cyc_txt}{mark}")
                    worst = "yellow" if worst == "green" else worst
                else:
                    parts.append(f"{key}:{name} 🔴{age}s{cyc_txt}{mark}")
                    worst = "red"
            text = " · ".join(parts) if parts else "Đang khởi động luồng..."
            # v1.3.7: trạng thái chạy bình thường = accent 2 (xá cù non), không trùng màu idle
            fg = {"green": self.C_ACCENT_2, "yellow": self.C_HB_YELLOW,
                  "red": self.C_HB_RED}[worst]
            self.root.after(0, lambda t=text, f=fg: (
                self.var_status.set(t), self.lbl_status.config(fg=f)))
        else:
            self.root.after(0, lambda: (
                self.var_status.set(f"Sẵn sàng · {self._version_line}"),
                self.lbl_status.config(fg=self.C_STATUS_FG)))
        self.root.after(5000, self._tick_status)

    def _create_tab(self, tab_name):
        frame = ttk.Frame(self.notebook)
        self.notebook.add(frame, text=f" {tab_name} ")

        # v1.3.7: log trên nền field (sáng hơn trang), chữ Consolas 10, border mềm.
        txt_log = tk.Text(frame, bg=self.C_FIELD, fg=self.C_LOG_FG, font=("Consolas", 10),
                          state="disabled", relief="flat", padx=10, pady=8,
                          insertbackground=self.C_FG, highlightthickness=1,
                          highlightbackground=self.C_BORDER)
        txt_log.pack(fill="both", expand=True)

        scrollbar = ttk.Scrollbar(txt_log, command=txt_log.yview)
        scrollbar.pack(side="right", fill="y")
        txt_log.config(yscrollcommand=scrollbar.set)
        # Line spacing thoáng + không bẻ dòng (log dài cuộn ngang)
        txt_log.config(spacing1=2, wrap="none")

        self.log_boxes[tab_name] = txt_log

    def append_log(self, slot_name, text):
        def _update():
            if slot_name in self.log_boxes:
                box = self.log_boxes[slot_name]
                box.config(state="normal")
                box.insert(tk.END, text + ("\n" if not text.endswith("\n") else ""))
                box.see(tk.END) 
                box.config(state="disabled")
        self.root.after(0, _update)
        
    def update_tab_name(self, slot_index, new_name):
        def _update():
            try:
                tab_id = self.notebook.tabs()[slot_index + 1]
                self.notebook.tab(tab_id, text=f" {new_name} ")
            except Exception:
                pass
        self.root.after(0, _update)

    # ==========================================================
    # v1.4.9: BOARD THỜI LƯỢNG CHẠY — tab riêng, luôn nhìn thấy
    # ==========================================================
    BOARD_COLUMNS = ("name", "group", "id", "running", "cycles", "today", "total_all",
                     "avg", "actions", "first", "days", "last_dur", "result", "last_at")
    BOARD_HEADERS = {"name": "Tài khoản", "group": "Nhóm", "id": "ID", "running": "Đang chạy",
                     "cycles": "Số vòng", "today": "Hôm nay", "total_all": "Tổng mọi thời",
                     "avg": "TB/vòng", "actions": "Hành động", "first": "Ngày đầu",
                     "days": "Ngày ngâm", "last_dur": "Vòng cuối", "result": "Kết quả",
                     "last_at": "Xong lúc"}
    BOARD_WIDTHS = {"name": 152, "group": 92, "id": 74, "running": 88, "cycles": 58,
                    "today": 74, "total_all": 94, "avg": 70, "actions": 74, "first": 90,
                    "days": 68, "last_dur": 70, "result": 100, "last_at": 112}
    # Cột sort theo SỐ (raw trong self._board_raw); các cột còn lại sort theo chuỗi.
    BOARD_NUM_COLS = ("running", "cycles", "today", "total_all", "avg", "actions",
                      "days", "last_dur")

    def _create_board_tab(self):
        """Tạo (hoặc tạo lại) tab "THỜI LƯỢNG CHẠY". Tab LUÔN nằm CUỐI notebook, nên
        công thức tabs()[slot_index + 1] của update_tab_name không bị lệch khi chạy.
        Không đăng ký vào log_boxes (tab này là bảng, không phải khung log)."""
        old = getattr(self, "board_frame", None)
        if old is not None:
            try:
                old.destroy()
            except Exception:
                pass
        # Giữ cửa sổ ngày đã chọn giữa các lần tạo lại (Start tạo lại tab này)
        _prev_days = "30"
        try:
            if self.var_board_days is not None:
                _prev_days = self.var_board_days.get()
        except Exception:
            pass

        frame = ttk.Frame(self.notebook)
        self.notebook.add(frame, text=" THỜI LƯỢNG CHẠY ")
        self.board_frame = frame

        bar = ttk.Frame(frame, padding=(10, 8, 10, 2))
        bar.pack(fill="x")
        ttk.Label(bar, text="Mỗi lần BẮT ĐẦU CHẠY 1 profile = 1 chu trình (lỗi/dừng giữa vòng vẫn ghi).",
                  style="Muted.TLabel").pack(side="left")
        ttk.Button(bar, text="Làm mới", width=9, command=lambda: refresh()).pack(side="right")
        self.var_board_days = tk.StringVar(value=_prev_days)
        ttk.Label(bar, text="Cửa sổ:").pack(side="right", padx=(4, 0))
        self.cbo_board_days = ttk.Combobox(bar, textvariable=self.var_board_days,
                                           values=["7", "30", "90", "Tất cả"],
                                           state="readonly", width=7)
        self.cbo_board_days.pack(side="right", padx=(4, 10))
        self.cbo_board_days.bind("<<ComboboxSelected>>", lambda e: refresh())

        body = ttk.Frame(frame)
        body.pack(fill="both", expand=True, padx=10, pady=(4, 0))
        tree = ttk.Treeview(body, columns=self.BOARD_COLUMNS, show="headings")
        self.board_tree = tree
        for col in self.BOARD_COLUMNS:
            tree.heading(col, text=self.BOARD_HEADERS[col], command=lambda c=col: sort_by(c))
            tree.column(col, width=self.BOARD_WIDTHS[col],
                        anchor="w" if col in ("name", "group", "first", "result", "last_at") else "center")
        scroll = ttk.Scrollbar(body, command=tree.yview)
        tree.configure(yscrollcommand=scroll.set)
        scroll.pack(side="right", fill="y")
        tree.pack(side="left", fill="both", expand=True)

        self._board_status = ttk.Label(frame, text="", style="Muted.TLabel")
        self._board_status.pack(anchor="w", padx=12, pady=(4, 0))
        ttk.Label(frame,
                  text="Double-click một dòng để xem phân tích hành động/nền tảng của profile đó. "
                       "Bảng tự tươi mỗi 15 giây khi app đang chạy. ⏰ = vòng này đã vượt mục tiêu của nó.",
                  style="Muted.TLabel").pack(anchor="w", padx=12, pady=(0, 8))

        # Bind cả virtual event để test mở được dialog (Tk build này cấm event_generate("<Double-1>")).
        tree.bind("<Double-1>", lambda e: show_breakdown())
        tree.bind("<<ShowBoardBreakdown>>", lambda e: show_breakdown())

        self._board_raw = {}
        _sort = {"col": None, "rev": False}

        def days_window():
            """-> (số ngày, nhãn hiển thị). 'Tất cả' = 3650 ngày (quy ước sẵn có của codebase)."""
            try:
                if self.var_board_days.get().strip().lower() in ("tất cả", "tat ca", "all"):
                    return 3650, "mọi thời"
                return int(self.var_board_days.get()), None
            except (ValueError, tk.TclError):
                return 30, None

        def refresh():
            for item in tree.get_children():
                tree.delete(item)
            self._board_raw = {}
            days, _lbl = days_window()
            tgt = self._target_secs()
            try:
                db = DatabaseHandler()
                cyc = db.get_cycle_summary(days=days, target_s=tgt)
                life = db.get_cycle_lifetime_stats()
            except Exception as e:
                self._board_status.config(text=f"Lỗi đọc DB: {e}")
                return
            # Union: profile trong checklist + mọi profile có dữ liệu DB (kể cả đã bỏ khỏi checklist)
            known = {r["id"]: r for r in (self.profile_rows or [])}
            pids, seen = [], set()
            for pid in list(known.keys()) + list(cyc.keys()) + list(life.keys()):
                if pid and pid not in seen:
                    seen.add(pid)
                    pids.append(pid)
            running_pid = {pid: key for key, pid in SLOT_PROFILE.items()}
            now = time.time()
            n_cyc = tot_win = tot_all = acts_all = 0
            today_all = 0.0
            for pid in pids:
                r = known.get(pid, {})
                d = cyc.get(pid, {})
                lf = life.get(pid, {})
                cycles = d.get("cycles", 0)
                cycles_all = lf.get("cycles_all", 0)
                # Cột "Đang chạy" — realtime từ SLOT_* của worker (mốc so = của CHÍNH vòng này)
                key = running_pid.get(pid)
                ci = SLOT_CYCLE_INFO.get(key, {}) if key else {}
                t_run = ci.get("target_s") or tgt
                run_txt, run_s = "", None
                if key:
                    t0 = SLOT_CYCLE_START.get(key)
                    if t0 and SLOT_THREAD_ALIVE.get(key, False):
                        run_s = now - t0
                        run_txt = _fmt_dur(run_s) + (" ⏰" if t_run and run_s >= t_run else "")
                st = d.get("last_status") or lf.get("last_status") or ""
                err = (d.get("last_error") or lf.get("last_error") or "").strip()
                if st == "ok":
                    res = "OK"
                elif st == "error":
                    res = "LOI" + ((" " + err[:34]) if err else "")
                elif st == "stopped":
                    res = "Dung giua vong"
                else:
                    res = "-" if cycles_all else ""
                today_s = lf.get("today_s", 0.0)
                iid = tree.insert("", tk.END, values=(
                    (r.get("name") or pid)[:42],
                    (r.get("group") or UNGROUPED_LABEL)[:16] if cycles_all else "",
                    pid[:8],
                    run_txt,
                    cycles or "",
                    _fmt_dur(today_s) if today_s else "",
                    _fmt_dur(lf.get("total_all_s")) if cycles_all else "",
                    _fmt_dur(d.get("avg_s")) if cycles else "",
                    lf.get("actions_all") or "",
                    (lf.get("first_at") or "")[:10],
                    lf.get("days_active") or "",
                    _fmt_dur(d.get("last_duration_s") if d.get("last_duration_s") is not None
                             else lf.get("last_duration_s"))
                    if (d.get("last_duration_s") is not None or lf.get("last_duration_s") is not None)
                    else "",
                    res,
                    ((d.get("last_at") or lf.get("last_at") or "")[:19]).replace("T", " "),
                ))
                # Cột trống -> None (chứ không phải 0) de profile chua chay luon roi xuong
                # day khi sort, khong bi "ho" voi vong 0 giay that.
                self._board_raw[iid] = {
                    "pid": pid, "running": run_s,
                    "cycles": cycles if cycles else None,
                    "today": today_s if today_s else None,
                    "total_all": lf.get("total_all_s") if cycles_all else None,
                    "avg": d.get("avg_s") if cycles else None,
                    "actions": lf.get("actions_all") if cycles_all else None,
                    "days": lf.get("days_active") if cycles_all else None,
                    "last_dur": (d.get("last_duration_s")
                                 if d.get("last_duration_s") is not None
                                 else (lf.get("last_duration_s") if cycles_all else None)),
                }
                n_cyc += cycles
                tot_win += d.get("total_s", 0) or 0
                tot_all += lf.get("total_all_s", 0.0)
                acts_all += lf.get("actions_all", 0)
                today_all += today_s
            txt = f"{len(pids)} profile · {n_cyc} vòng trong cửa sổ đang chọn · tổng {_fmt_dur(tot_win)}"
            txt += f" · hôm nay {_fmt_dur(today_all)} · mọi thời {_fmt_dur(tot_all)} · {acts_all} hành động"
            self._board_status.config(text=txt)

        def sort_by(col):
            """Sort theo cột; click lại cột đang sort = đảo chiều (header hiện ▲/▼).
            Click ĐẦU TIÊN: cột số -> giảm dần (profile ngâm nhiều nhất trên đầu),
            cột chữ -> tăng dần. Ô thiếu dữ liệu (None) luôn nằm CUỐI dù sort chiều nào."""
            reverse = (not _sort["rev"]) if _sort["col"] == col else (col in self.BOARD_NUM_COLS)
            allitems = list(tree.get_children())
            if col in self.BOARD_NUM_COLS:
                have = [i for i in allitems
                        if self._board_raw.get(i, {}).get(col) is not None]
                miss = [i for i in allitems
                        if self._board_raw.get(i, {}).get(col) is None]
                have.sort(key=lambda i: self._board_raw[i][col], reverse=reverse)
                items = have + miss
            else:
                items = sorted(allitems,
                               key=lambda i: str(tree.set(i, col)).lower(),
                               reverse=reverse)
            for idx, iid in enumerate(items):
                tree.move(iid, "", idx)
            _sort["rev"] = reverse
            _sort["col"] = col
            for c in self.BOARD_COLUMNS:
                mark = ""
                if c == col:
                    mark = " ▼" if reverse else " ▲"
                tree.heading(c, text=self.BOARD_HEADERS[c] + mark)

        def show_breakdown(_event=None):
            sel = tree.selection()
            if not sel:
                return
            pid = self._board_raw.get(sel[0], {}).get("pid")
            if not pid:
                return
            days, _lbl = days_window()
            name = (tree.set(sel[0], "name") or pid[:8])
            try:
                rows = DatabaseHandler().get_activity_summary(pid, days=days)
            except Exception as e:
                messagebox.showerror("Lỗi", f"Không đọc được activity: {e}", parent=self.root)
                return
            dlg = tk.Toplevel(frame.winfo_toplevel())
            dlg.title(f"Hành động — {name}")
            dlg.configure(bg=self.C_CARD)
            dlg.geometry("880x430")
            ttk.Label(dlg, text=f"Phân tích hành động/nền tảng của {pid} trong {days} ngày "
                                f"(nguồn: activity_history).",
                      style="Muted.TLabel").pack(anchor="w", padx=12, pady=(10, 4))
            t2 = ttk.Treeview(dlg, columns=("action", "platform", "count", "errors",
                                            "avg", "total", "last"),
                              show="headings")
            for col, txt in (("action", "Hành động"), ("platform", "Nền tảng"), ("count", "Số lần"),
                             ("errors", "Lỗi"), ("avg", "TB/lần"), ("total", "Tổng"),
                             ("last", "Lần cuối")):
                t2.heading(col, text=txt)
                t2.column(col, width={"action": 190, "platform": 110, "count": 62, "errors": 52,
                                      "avg": 76, "total": 84, "last": 122}[col],
                          anchor="w" if col in ("action", "platform", "last") else "center")
            s2 = ttk.Scrollbar(dlg, command=t2.yview)
            t2.configure(yscrollcommand=s2.set)
            s2.pack(side="right", fill="y")
            t2.pack(fill="both", expand=True, padx=(12, 0), pady=(0, 4))
            tot_min = 0.0
            for row in rows:
                t2.insert("", tk.END, values=(
                    row.get("action") or "", row.get("platform") or "",
                    row.get("count") or 0, row.get("errors") or 0,
                    _fmt_dur(row.get("avg_duration_s")),
                    _fmt_dur(row.get("total_duration_s")),
                    (row.get("last_at") or "")[:19].replace("T", " "),
                ))
                tot_min += row.get("total_duration_s") or 0
            ttk.Label(dlg, text=f"{len(rows)} loại hành động · tổng thời gian hoạt động {_fmt_dur(tot_min)}",
                      style="Muted.TLabel").pack(anchor="w", padx=12, pady=(0, 6))
            ttk.Button(dlg, text="Đóng", command=dlg.destroy).pack(anchor="e", padx=12, pady=(0, 10))

        refresh()

        # Tự tươi 15s (chỉ khi tab còn tồn tại — vòng cũ tự chết khi frame bị destroy lúc Start)
        def _auto():
            try:
                if frame.winfo_exists():
                    refresh()
                    self.root.after(15000, _auto)
            except Exception:
                pass
        self.root.after(15000, _auto)

    # ==========================================================
    # SPRINT 1: khung cuộn được (checklist profile + cặp từ khóa)
    # ==========================================================
    def _make_scrollable(self, parent, pixel_height):
        """Canvas + scrollbar + frame trong; trả về (canvas, inner). Con đặt pack(fill=x) vào inner.
        v1.3.7: nền field sáng hơn thẻ một bậc + border mềm — khung danh sách 'lõm' tự nhiên."""
        canvas = tk.Canvas(parent, height=pixel_height, highlightthickness=1, relief="flat",
                           bg=self.C_FIELD, highlightbackground=self.C_BORDER)
        scrollbar = ttk.Scrollbar(parent, orient="vertical", command=canvas.yview)
        inner = ttk.Frame(canvas)
        inner_win = canvas.create_window((0, 0), window=inner, anchor="nw")
        inner.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>", lambda e: canvas.itemconfigure(inner_win, width=e.width))
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        def _wheel(event):
            canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
        canvas.bind("<Enter>", lambda e: canvas.bind_all("<MouseWheel>", _wheel))
        canvas.bind("<Leave>", lambda e: canvas.unbind_all("<MouseWheel>"))
        return canvas, inner

    # ---------------- Checklist tài khoản (1.3) + nhóm kiểu GPM (v1.3.6) ----------------
    def _rebuild_profile_rows(self, entries):
        """Dựng lại checklist: gom theo nhóm (header + các dòng), nhóm có sort-order
        thấp hơn đứng trước; 'Chưa có nhóm' chót. Header chỉ để nhìn, tick vẫn từng dòng."""
        for w in self.prof_inner.winfo_children():
            w.destroy()
        self.profile_rows = []
        self._group_headers = {}
        for e in entries:
            self._add_profile_row(e.get("id", ""), e.get("name", ""),
                                  bool(e.get("firefox")), bool(e.get("selected", True)),
                                  e.get("group", "") or "")
        self._layout_groups()
        self._populate_group_filter()
        self._update_prof_count()
        self._filter_profiles()

    def _layout_groups(self):
        """v1.3.6: tạo frame header cho mọi nhóm có trong profile_rows (pack sau này
        theo thứ tự trong _filter_profiles — header + dòng cùng nhóm xen kẽ).
        v1.3.7: header là dải nền nổi (C_CARD2) — tên nhóm accent + badge đếm,
clearly tách nhóm hơn kiểu label trần + separator."""
        for r in self.profile_rows:
            g = r["group"] or UNGROUPED_LABEL
            if g in self._group_headers:
                continue
            hdr = tk.Frame(self.prof_inner, bg=self.C_CARD2)
            tk.Label(hdr, text=g.upper(), fg=self.C_ACCENT, bg=self.C_CARD2,
                     font=("Segoe UI", 9, "bold")).pack(side="left", padx=(8, 0), pady=4)
            cnt = tk.Label(hdr, text="", fg=self.C_PILL_FG, bg=self.C_PILL_BG,
                           font=("Consolas", 9, "bold"), padx=6, pady=1)
            cnt.pack(side="left", padx=(8, 8))
            self._group_headers[g] = {"group": g, "frame": hdr, "count": cnt}

    def _groups_multi(self):
        """v1.3.6: True khi có >=2 nhóm và có ít nhất 1 nhóm thật (ngoài 'Chưa có nhóm').
        Nguồn quyết định hiện combobox lọc + header nhóm — danh sách chưa phân nhóm
        thì UI y hệt v1.2.x (bài học: không thêm chi tiết thừa khi chưa có dữ liệu)."""
        groups = []
        for r in self.profile_rows:
            g = r["group"] or UNGROUPED_LABEL
            if g not in groups:
                groups.append(g)
        return len([g for g in groups if g != UNGROUPED_LABEL]) >= 1 and len(groups) >= 2

    def _populate_group_filter(self):
        """Combobox lọc nhóm: hiện khi có >=2 nhóm thật (ngoài 'Chưa có nhóm'),
        ẩn khi danh sách chưa phân nhóm — UI mặc định y như trước (bài học v1.2.x)."""
        groups = []
        for r in self.profile_rows:
            g = r["group"] or UNGROUPED_LABEL
            if g not in groups:
                groups.append(g)
        multi = self._groups_multi()
        vals = [GROUP_ALL] + groups
        self.cbo_prof_group.config(values=vals)
        if self.var_prof_group.get() not in vals:
            self.var_prof_group.set(GROUP_ALL)
        if multi:
            self._lbl_group_filter.pack(side="left", before=self._lbl_filter_text)
            self.cbo_prof_group.pack(side="left", before=self._lbl_filter_text, padx=(4, 6))
        else:
            self.cbo_prof_group.pack_forget()
            self._lbl_group_filter.pack_forget()
            self.var_prof_group.set(GROUP_ALL)

    def _group_order(self):
        """Thứ tự hiển thị nhóm: theo lần xuất hiện đầu trong profile_rows,
        'Chưa có nhóm' luôn chót (API GPM trả profile đã gom theo nhóm)."""
        seen = []
        for r in self.profile_rows:
            g = r["group"] or UNGROUPED_LABEL
            if g not in seen:
                seen.append(g)
        if UNGROUPED_LABEL in seen:
            seen.remove(UNGROUPED_LABEL)
            seen.append(UNGROUPED_LABEL)
        return seen

    def _filter_profiles(self, event=None):
        """Ẩn/hiện dòng theo (1) nhóm đã chọn và (2) từ khóa lọc (tên/ID, không phân biệt
        hoa thường). Pack THEO THỨ TỰ NHÓM: header rồi các dòng của nhóm đó (xen kẽ đúng).
        Header chỉ hiện khi nhóm còn dòng hiển thị. Placeholder khi trống."""
        q = self.var_prof_filter.get().strip().lower()
        sel_group = self.var_prof_group.get() if self.cbo_prof_group.winfo_ismapped() else GROUP_ALL
        visible = 0
        multi = self._groups_multi()
        # 1) tính ẩn/hiện từng dòng
        for r in self.profile_rows:
            hay = (r["name"] + " " + r["id"]).lower()
            g = r["group"] or UNGROUPED_LABEL
            ok_group = (sel_group == GROUP_ALL) or (sel_group == g)
            r["hidden"] = bool((q and q not in hay) or (not ok_group))
        # 2) QUÊN hết pack cũ rồi pack lại theo nhóm. BÀI HỌC v1.3.6: gọi pack() lại trên
        # widget ĐÃ pack KHÔNG đổi thứ tự (Tk giữ vị trí cũ) -> header rớt xuống đáy canvas,
        # ngoài vùng nhìn. Phải pack_forget trước rồi mới pack theo thứ tự mong muốn.
        for h in self._group_headers.values():
            h["frame"].pack_forget()
        for r in self.profile_rows:
            r["frame"].pack_forget()
        # 3) pack theo nhóm: header rồi các dòng chưa ẩn của nhóm đó (xen kẽ đúng)
        for g in self._group_order():
            rows_g = [r for r in self.profile_rows if (r["group"] or UNGROUPED_LABEL) == g]
            shown = [r for r in rows_g if not r["hidden"]]
            h = self._group_headers.get(g)
            nsel = sum(1 for r in rows_g if r["var"].get())
            if h:
                h["count"].config(text=f"{nsel}/{len(rows_g)}")
                if shown and multi:
                    h["frame"].pack(fill="x", anchor="w", padx=2, pady=(5, 2))
            for r in shown:
                r["frame"].pack(fill="x", anchor="w", padx=2, pady=1)
            visible += len(shown)
        # Placeholder hướng dẫn khi chưa có dòng nào hiển thị (danh sách trống / lọc không khớp)
        if hasattr(self, "_lbl_prof_empty") and self._lbl_prof_empty.winfo_exists():
            self._lbl_prof_empty.destroy()
        if visible == 0:
            filtering = (q and self.profile_rows) or (sel_group != GROUP_ALL and self.profile_rows)
            hint = ("Chưa có tài khoản nào khớp bộ lọc (nhóm / từ khóa). Xóa lọc để thấy lại tất cả."
                    if filtering else
                    "Chưa có tài khoản — bấm 'Tải từ GPM' (GPM Login phải bật) hoặc 'Dán ID thủ công'.")
            self._lbl_prof_empty = tk.Label(
                self.prof_inner, text=hint, fg=self.C_MUTED, bg=self.C_CARD,
                font=("Segoe UI", 10, "italic"), anchor="w", justify="left")
            self._lbl_prof_empty.pack(fill="x", padx=6, pady=8)

    def _add_profile_row(self, pid, name, firefox, selected, group=""):
        var = tk.BooleanVar(value=(False if firefox else selected))
        row = ttk.Frame(self.prof_inner)
        row.pack(fill="x", anchor="w", padx=2, pady=1)
        # Tên dài (vd kèm email) cắt ngắn cho dễ đọc; ID 8 ký tự đặt riêng bên phải
        display = (name or pid[:8]).strip()
        if len(display) > 42:
            display = display[:41] + "…"
        if firefox:
            display += "   (Firefox - khong chay duoc CDP)"
        cb = ttk.Checkbutton(row, text=display, variable=var,
                             command=self._update_prof_count,
                             style="Row.TCheckbutton")
        if firefox:
            cb.config(state="disabled")
        cb.pack(side="left", fill="x", expand=True, anchor="w")
        # v1.3.7: hover sáng nền cả dòng (2 style tĩnh đổi tên — không tạo style động)
        if not firefox:
            row.bind("<Enter>", lambda e: cb.config(style="RowHover.TCheckbutton"), add="+")
            row.bind("<Leave>", lambda e: cb.config(style="Row.TCheckbutton"), add="+")
        # v1.3.7: ID dạng pill Consolas gọn mắt, dễ phân biệt 2 acc trùng tên
        tk.Label(row, text=pid[:8], fg=self.C_PILL_FG, bg=self.C_PILL_BG,
                 font=("Consolas", 8), padx=5, pady=1).pack(side="right", padx=6)
        self.profile_rows.append({"id": pid, "name": name, "firefox": firefox,
                                  "var": var, "frame": row, "group": group,
                                  "hidden": False})

    def _update_prof_count(self):
        """Tổng số chọn + cập nhật header từng nhóm + giữ nguyên placeholder/lọc."""
        n_sel = sum(1 for r in self.profile_rows if r["var"].get())
        self.lbl_prof_count.config(text=f"{n_sel}/{len(self.profile_rows)} chọn")
        for gname, h in self._group_headers.items():
            total = sum(1 for r in self.profile_rows if (r["group"] or UNGROUPED_LABEL) == gname)
            nsel = sum(1 for r in self.profile_rows
                       if (r["group"] or UNGROUPED_LABEL) == gname and r["var"].get())
            h["count"].config(text=f"{nsel}/{total}")

    def _set_all_profiles(self, value):
        """Chọn/bỏ CHỈ các dòng đang hiển thị (theo nhóm + từ khóa lọc hiện tại)."""
        for r in self.profile_rows:
            if not r["firefox"] and not r.get("hidden", False):
                r["var"].set(value)
        self._update_prof_count()

    def _auto_load_profiles(self):
        """Sprint 1.6: lúc mở app, nếu checklist đang trống thì tự tải từ GPM (background, im lặng khi lỗi)."""
        if self.profile_rows or self.var_browser_type.get() != BROWSER_GPM:
            return

        def _work():
            try:
                port_int = int(self.var_api_port.get() or 9495)
            except ValueError:
                port_int = 9495
            try:
                api = BrowserFactory.get_api(BROWSER_GPM, base_url=f"http://localhost:{port_int}")
                lst = api.list_profiles()
            except Exception:
                lst = None
            if lst:
                self.root.after(0, lambda: self._apply_api_profiles(lst, silent=True))

        threading.Thread(target=_work, daemon=True).start()

    def load_profiles_from_api(self):
        """Kéo danh sách profile từ GPM Login thành checklist (Firefox bị xám, không tick được)."""
        if self.var_browser_type.get() != BROWSER_GPM:
            messagebox.showinfo(
                "BitBrowser",
                "Tải danh sách tự động hiện chỉ hỗ trợ GPM Login.\n"
                "Với BitBrowser, hãy dùng nút 'Dán ID thủ công'.",
            )
            return
        try:
            port_int = int(self.var_api_port.get() or 9495)
        except ValueError:
            port_int = 9495
        try:
            api = BrowserFactory.get_api(BROWSER_GPM, base_url=f"http://localhost:{port_int}")
            lst = api.list_profiles()
        except Exception as e:
            lst = None
            err = e
        else:
            err = None
        if not lst:
            messagebox.showerror(
                "Không tải được danh sách",
                f"Không gọi được API GPM ở port {port_int}.\n\n"
                "Kiểm tra GPM Login đã bật chưa.\n"
                + (f"Lỗi: {err}" if err else ""),
            )
            return
        self._apply_api_profiles(lst)

    def _apply_api_profiles(self, lst, silent=False):
        """Nạp danh sách từ API vào checklist, giữ selection cũ nếu có. Auto-load (silent) chỉ khi checklist trống."""
        if silent and self.profile_rows:
            return
        had_selection = any(r["var"].get() for r in self.profile_rows)
        keep_sel = {r["id"] for r in self.profile_rows if r["var"].get()}
        entries = []
        for p in lst:
            sel = (p["id"] in keep_sel) if had_selection else (not p["firefox"])
            entries.append({"id": p["id"], "name": p["name"], "firefox": p["firefox"],
                            "selected": sel, "group": p.get("group", "") or ""})
        self._rebuild_profile_rows(entries)
        n_ok = sum(1 for p in lst if not p["firefox"])
        print(f"[+] Đã tải {len(lst)} profile từ GPM Login ({n_ok} Chrome dùng được, {len(lst) - n_ok} Firefox đã xám).")

    def open_manual_add_dialog(self):
        """Cho BitBrowser / trường hợp dán UUID tay: thêm vào checklist, vẫn lưu config."""
        win = tk.Toplevel(self.root)
        win.title("Dán Profile ID thủ công")
        win.configure(bg=self.C_CARD)
        win.geometry("500x280")
        ttk.Label(win, text="Mỗi dòng 1 UUID (lấy từ GPM Login / BitBrowser):").pack(anchor="w", padx=8, pady=(8, 2))
        txt = tk.Text(win, height=8, bg=self.C_FIELD, fg=self.C_FG, insertbackground=self.C_FG,
                      relief="flat", padx=6, pady=4, font=("Consolas", 10))
        txt.pack(fill="both", expand=True, padx=8)

        def ok():
            raw = [ln.strip() for ln in txt.get("1.0", tk.END).splitlines() if ln.strip()]
            if not raw:
                win.destroy()
                return
            uuid_re = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")
            bad = [x for x in raw if not uuid_re.match(x)]
            if bad:
                messagebox.showerror(
                    "UUID không hợp lệ",
                    "Những dòng sau sai định dạng:\n\n" + "\n".join(bad[:10]),
                    parent=win,
                )
                return
            existing = {r["id"] for r in self.profile_rows}
            added = 0
            for x in raw:
                if x not in existing:
                    # v1.3.6: ID dán tay không có thông tin nhóm -> gom 'Chưa có nhóm'
                    self._add_profile_row(x, x[:8], False, True, "")
                    added += 1
            self._layout_groups()
            self._populate_group_filter()
            self._filter_profiles()
            self._update_prof_count()
            print(f"[+] Thêm thủ công {added} profile vào checklist.")
            win.destroy()

        ttk.Button(win, text="Thêm vào danh sách", command=ok).pack(pady=8)

    # ---------------- Cặp từ khóa (1.4) ----------------
    def _add_kw_row(self, g="", y="", focus=False):
        row = ttk.Frame(self.kw_inner)
        row.pack(fill="x", pady=1)
        ent_g = ttk.Entry(row)
        ent_g.insert(0, g)
        ent_y = ttk.Entry(row)
        ent_y.insert(0, y)
        ent_g.pack(side="left", fill="x", expand=True, padx=(0, 3))
        ent_y.pack(side="left", fill="x", expand=True, padx=(3, 3))
        data = {"g": ent_g, "y": ent_y, "frame": row}
        ttk.Button(row, text="X", width=3, style="Tool.TButton",
                   command=lambda d=data: self._remove_kw_row(d)).pack(side="left", padx=(2, 0))
        self.kw_rows.append(data)
        if focus:
            ent_g.focus_set()
        return data

    def _remove_kw_row(self, data):
        if data in self.kw_rows:
            self.kw_rows.remove(data)
        data["frame"].destroy()
        if not self.kw_rows:
            self._add_kw_row("", "")

    def _rebuild_kw_rows(self, g_list, y_list):
        for r in self.kw_rows:
            r["frame"].destroy()
        self.kw_rows = []
        n = max(len(g_list), len(y_list))
        for i in range(n):
            self._add_kw_row(g_list[i] if i < len(g_list) else "",
                             y_list[i] if i < len(y_list) else "")

    def _collect_kw_pairs(self):
        """Danh sách chủ đề từ các cặp; YouTube trống -> dùng lại Google (như quy tắc cũ)."""
        pairs = []
        for r in self.kw_rows:
            g = r["g"].get().strip()
            y = r["y"].get().strip()
            if not g and not y:
                continue
            pairs.append({"google_query": g or y, "youtube_query": y or g})
        return pairs

    # ---------------- Persist config (1.1) ----------------
    def _apply_loaded_config(self):
        cfg = self.cfg
        if cfg.get("browser_type") in (BROWSER_GPM, BROWSER_BITBROWSER):
            self.var_browser_type.set(cfg["browser_type"])
        if cfg.get("api_port"):
            self.var_api_port.set(str(cfg["api_port"]))
        if cfg.get("brain_type"):
            self.var_brain_type.set(cfg["brain_type"])
            self._on_brain_type_changed()
        self.var_phase_label.set(PHASE_LABEL_BY_KEY.get(cfg.get("phase", "clean"), PHASE_LABELS[0]))
        self._on_phase_changed()
        try:
            self.spin_threads.set(int(cfg.get("threads", 4)))
        except (ValueError, TypeError):
            self.spin_threads.set(4)
        self.var_skip_youtube.set(bool(cfg.get("skip_youtube", False)))
        self.var_skip_random_keywords.set(bool(cfg.get("skip_random_keywords", False)))
        # v1.4.0: mục tiêu phút/vòng (0 = tắt)
        try:
            self.spin_target_min.set(max(0, int(cfg.get("target_cycle_minutes", 0))))
        except (ValueError, TypeError):
            self.spin_target_min.set(0)

    def _target_secs(self):
        """Mục tiêu 1 chu trình (giây). v1.4.1: 0 = KHÔNG ghim — bot tự random mỗi vòng
        (mỗi profile một số khác nhau, không ngày nào giống ngày nào). >0 = số phút cố định
        (mọi vòng dùng chung, để soi một mốc cụ thể)."""
        try:
            return max(0, int(float(self.spin_target_min.get()))) * 60
        except (ValueError, TypeError):
            return 0

    def save_current_config(self):
        cfg = dict(self.cfg)
        cfg["profiles"] = [
            {"id": r["id"], "name": r["name"], "firefox": r["firefox"],
             "selected": bool(r["var"].get()), "group": r.get("group", "")}
            for r in self.profile_rows
        ]
        g_list, y_list = [], []
        for r in self.kw_rows:
            g = r["g"].get().strip()
            y = r["y"].get().strip()
            if not g and not y:
                continue
            g_list.append(g)
            y_list.append(y)
        cfg["kw_google"] = g_list
        cfg["kw_youtube"] = y_list
        cfg["browser_type"] = self.var_browser_type.get()
        cfg["api_port"] = self.var_api_port.get()
        cfg["brain_type"] = self.var_brain_type.get()
        cfg["phase"] = PHASE_MAP.get(self.var_phase_label.get(), "clean")
        try:
            cfg["threads"] = int(self.spin_threads.get())
        except (ValueError, TypeError):
            cfg["threads"] = 4
        cfg["skip_youtube"] = bool(self.var_skip_youtube.get())
        cfg["skip_random_keywords"] = bool(self.var_skip_random_keywords.get())
        cfg["theme"] = self.theme_name  # v1.3.3: nhớ sáng/tối giữa các phiên
        try:  # v1.4.0: nhớ mục tiêu thời lượng 1 chu trình
            cfg["target_cycle_minutes"] = max(0, int(float(self.spin_target_min.get())))
        except (ValueError, TypeError):
            cfg["target_cycle_minutes"] = 0
        self.cfg = cfg
        save_config(cfg)

    def _on_close(self):
        try:
            self.save_current_config()
        except Exception:
            pass
        self.root.destroy()

    def _on_browser_type_changed(self, event=None):
        """Cập nhật port mặc định và hint khi đổi loại browser."""
        browser_type = self.var_browser_type.get()
        if browser_type == BROWSER_GPM:
            self.var_api_port.set("9495")
            self.lbl_browser_hint.config(text="(GPM Login - Port 9495)")
        elif browser_type == BROWSER_BITBROWSER:
            self.var_api_port.set("54345")
            self.lbl_browser_hint.config(text="(BitBrowser - Port 54345)")

    def _on_brain_type_changed(self, event=None):
        """Cập nhật hint khi đổi loại AI Brain."""
        brain_type = self.var_brain_type.get()
        hints = {
            "none": "(Tắt AI - dùng từ khóa thủ công)",
            "gemini": "(Cần GEMINI_API_KEY - bấm nút QUẢN LÝ API KEY)",
            "openai": "(Cần OPENAI_API_KEY - bấm nút QUẢN LÝ API KEY)",
            "qwen-max": "(Cần QWEN_API_KEY - bấm nút QUẢN LÝ API KEY)",
            "qwen-flash": "(Cần QWEN_API_KEY - bấm nút QUẢN LÝ API KEY)",
            "local": "(Cần Ollama chạy ở localhost:11434)",
        }
        self.lbl_brain_hint.config(text=hints.get(brain_type, ""))

    def _on_phase_changed(self, event=None):
        """Cập nhật hint: pha này có xem YouTube không, vì sao."""
        label = self.var_phase_label.get()
        skip_yt = self.var_skip_youtube.get() if hasattr(self, "var_skip_youtube") else False
        if label.startswith("1"):
            hint = ("YouTube: " + ("CÓ — nhưng bạn đang tick 'Bỏ qua xem YouTube'." if skip_yt
                                   else "CÓ xem (trang chủ + tìm kiếm)."))
        elif label.startswith("2"):
            hint = "YouTube: KHÔNG. Pha 2 ở hệ Google (Alerts/News/Wikipedia/TikTok/Reddit) - tập dượt Alerts."
        else:
            hint = "YouTube: CÓ - trục chính, được Sub (quota 1/ngày/profile). Cảnh: tài khoản phải đã nuôi Pha 1-2."
        self.lbl_phase_hint.config(text=hint)

    def show_phase_details(self):
        """v1.3.8: tài liệu 3 chế độ ngâm — tab clean/mail/youtube, mỗi tab liệt kê
        hành động + trọng số + mô tả + ghi chú gate. Thuần UI (dữ liệu đối chiếu từ
        action_map warmup.py, không import runtime). Tab mở sẵn ở pha đang chọn."""
        phase = PHASE_MAP.get(self.var_phase_label.get(), "clean")
        win = tk.Toplevel(self.root)
        win.title("Chi tiết 3 chế độ ngâm")
        win.configure(bg=self.C_BG)
        win.geometry("880x620")

        nb = ttk.Notebook(win)
        nb.pack(fill="both", expand=True, padx=10, pady=(10, 4))
        for key in ("clean", "mail", "youtube"):
            info = PHASE_DETAILS[key]
            frame = tk.Frame(nb, bg=self.C_CARD)
            nb.add(frame, text=PHASE_LABEL_BY_KEY[key])
            inner = tk.Frame(frame, bg=self.C_CARD)
            inner.pack(fill="both", expand=True, padx=12, pady=10)
            tk.Label(inner, text=PHASE_LABEL_BY_KEY[key], bg=self.C_CARD,
                     fg=self.C_ACCENT, font=("Segoe UI", 12, "bold"),
                     anchor="w", justify="left").pack(fill="x")
            tk.Label(inner, text=info["goal"], bg=self.C_CARD, fg=self.C_FG,
                     font=("Segoe UI", 10), anchor="w", justify="left",
                     wraplength=810).pack(fill="x", pady=(4, 8))

            cols = ("action", "w", "desc")
            tree = ttk.Treeview(inner, columns=cols, show="headings", height=9)
            tree.heading("action", text="Hành động")
            tree.heading("w", text="Trọng số")
            tree.heading("desc", text="Nội dung chi tiết")
            tree.column("action", width=175, anchor="w")
            tree.column("w", width=62, anchor="center")
            tree.column("desc", width=600, anchor="w")
            vsb = ttk.Scrollbar(inner, command=tree.yview)
            tree.configure(yscrollcommand=vsb.set)
            vsb.pack(side="right", fill="y")
            tree.pack(fill="both", expand=True)
            for name, weight, desc, group in info["actions"]:
                label = name
                if group == "yt":
                    label += "  [bỏ khi tick 'Bỏ qua YouTube']"
                elif group == "rand":
                    label += "  [bỏ khi tick 'Bỏ qua từ khóa ngẫu nhiên']"
                tree.insert("", tk.END, values=(label, f"{weight:.2f}", desc))

            tk.Label(inner, text="Ghi chú: " + info["notes"], bg=self.C_CARD,
                     fg=self.C_MUTED, font=("Segoe UI", 9, "italic"),
                     anchor="w", justify="left", wraplength=810).pack(fill="x", pady=(8, 0))
        # nb.add() trả None trên Tk build này -> select theo index (thứ tự loop cố định)
        nb.select({"clean": 0, "mail": 1, "youtube": 2}.get(phase, 0))
        ttk.Button(win, text="Đóng", command=win.destroy).pack(pady=(0, 10))

    def request_stop_all(self):
        """Nút DỪNG: xác nhận -> set cờ -> mọi workflow kết thúc sau hành động hiện tại (không cắt giữa trang)."""
        if not messagebox.askyesno(
            "Xác nhận dừng",
            "Dừng an toàn: mỗi luồng sẽ hoàn tất hành động/tab hiện tại rồi thoát.\n"
            "Các profile chưa tới lượt sẽ bị bỏ qua.\n\nBạn chắc chắn muốn dừng?",
        ):
            return
        STOP_EVENT.set()
        self.btn_stop.config(state="disabled")
        print("\n[!] ================================ DỪNG AN TOÀN ĐƯỢC YÊU CẦU ================================")
        print("[!] Các luồng sẽ hoàn tất hành động/tab hiện tại rồi thoát. Vui lòng chờ vài giây...")

    def open_logs_folder(self):
        """Mở thư mục data/logs trong Explorer."""
        try:
            os.makedirs(LOG_DIR, exist_ok=True)
            os.startfile(LOG_DIR)
        except Exception as e:
            messagebox.showerror("Lỗi", f"Không mở được thư mục log:\n{e}\n\nĐường dẫn: {LOG_DIR}")

    def load_keywords_file(self):
        """Nạp keywords.txt (cú pháp 'Google | YouTube') vào ô Keywords trên GUI."""
        default_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "keywords.txt")
        path = filedialog.askopenfilename(
            title="Chọn file keywords",
            initialdir=os.path.dirname(default_path),
            initialfile=os.path.basename(default_path),
            filetypes=[("Text files", "*.txt"), ("All files", "*.*")],
        )
        if not path:
            return
        try:
            with open(path, "r", encoding="utf-8-sig") as f:
                content = f.read()
        except Exception as e:
            messagebox.showerror("Lỗi", f"Không đọc được file:\n{e}")
            return
        lines = [ln.strip() for ln in content.splitlines() if ln.strip()]
        if not lines:
            messagebox.showwarning("Cảnh báo", "File trống - giữ nguyên danh sách hiện tại.")
            return
        g_lines, y_lines = [], []
        for ln in lines:
            if "|" in ln:
                g, y = ln.split("|", 1)
                g_lines.append(g.strip())
                y_lines.append(y.strip())
            else:
                g_lines.append(ln.strip())
                y_lines.append(ln.strip())
        self._rebuild_kw_rows(g_lines, y_lines)
        print(f"[+] Đã nạp {len(lines)} cặp từ khóa từ {os.path.basename(path)}.")

    def show_activity_report(self):
        """Cửa sổ Báo cáo hoạt động (đọc bảng activity_history, 7/30/90 ngày)."""
        win = tk.Toplevel(self.root)
        win.title("Báo cáo hoạt động ngâm tài khoản")
        win.configure(bg=self.C_CARD)
        win.geometry("920x480")

        bar = ttk.Frame(win, padding=8)
        bar.pack(fill="x")
        ttk.Label(bar, text="Số ngày:").pack(side="left")
        var_days = tk.StringVar(value="7")
        cbo_days = ttk.Combobox(bar, textvariable=var_days, values=["7", "30", "90"], state="readonly", width=5)
        cbo_days.pack(side="left", padx=5)

        columns = ("profile", "action", "platform", "count", "errors", "avg", "last_at")
        tree = ttk.Treeview(win, columns=columns, show="headings")
        headers = {"profile": "Profile", "action": "Hành động", "platform": "Nền tảng",
                   "count": "Lượt", "errors": "Lỗi", "avg": "TB thời lượng",
                   "last_at": "Lần cuối"}
        widths = {"profile": 200, "action": 190, "platform": 95, "count": 55, "errors": 45,
                  "avg": 95, "last_at": 145}
        for col in columns:
            tree.heading(col, text=headers[col])
            tree.column(col, width=widths[col],
                        anchor="center" if col in ("count", "errors", "avg") else "w")

        scroll = ttk.Scrollbar(win, command=tree.yview)
        tree.configure(yscrollcommand=scroll.set)
        scroll.pack(side="right", fill="y")
        tree.pack(fill="both", expand=True, padx=(10, 0), pady=(0, 10))

        status = ttk.Label(bar, text="", style="Muted.TLabel")
        status.pack(side="left", padx=10)

        def _fmt_dur(v):
            """v1.2.7: giây -> '12s' / '2m30s'; None (row trước wiring) -> '-'."""
            if v is None:
                return "-"
            v = float(v)
            if v < 60:
                return f"{v:.0f}s"
            return f"{int(v // 60)}m{int(v % 60):02d}s"

        def refresh():
            for item in tree.get_children():
                tree.delete(item)
            try:
                rows = DatabaseHandler().get_activity_summary(profile_id=None, days=int(var_days.get()))
            except Exception as e:
                status.config(text=f"Lỗi đọc DB: {e}")
                return
            for r in rows:
                errs = r.get("errors", 0) or 0
                tree.insert("", tk.END, values=(
                    r.get("profile_id") or "?", r.get("action") or "",
                    r.get("platform") or "", r.get("count"),
                    errs if errs else "-",
                    _fmt_dur(r.get("avg_duration_s")),
                    r.get("last_at") or "",
                ))
            total = sum(r.get("count", 0) for r in rows)
            total_err = sum(r.get("errors", 0) or 0 for r in rows)
            txt = f"{len(rows)} nhóm hành động · {total} lượt trong {var_days.get()} ngày"
            if total_err:
                txt += f" · {total_err} lỗi"
            status.config(text=txt)

        ttk.Button(bar, text="Làm mới", command=refresh).pack(side="left", padx=5)
        refresh()

    # ==========================================================
    # SPRINT 2: Bảng tài khoản (dashboard read-only) + Export CSV
    # ==========================================================
    def show_account_dashboard(self):
        """Cửa sổ 'Bảng tài khoản': mỗi profile 1 dòng — trạng thái heartbeat + hành động/alert/sub cuối."""
        win = tk.Toplevel(self.root)
        win.title("Bảng tài khoản")
        win.configure(bg=self.C_CARD)
        win.geometry("1240x520")

        bar = ttk.Frame(win, padding=8)
        bar.pack(fill="x")
        ttk.Label(bar, text="Nguồn: checklist + heartbeat đang chạy + data thật từ DB (chỉ hiện cột có dữ liệu).",
                  style="Muted.TLabel").pack(side="left")

        # v1.3.6: +cột 'group' (nhóm GPM, kế tên) — nguồn profile_rows
        # v1.4.0: +cột 'cycle_now' (giờ ngâm vòng này, live khi đang chạy) + 'cycles'/'total_time'
        # (số vòng + tổng giờ ngâm 30 ngày gần nhất, từ cycle_history)
        columns = ("name", "group", "id", "status", "slot", "cycle_now", "last_action",
                   "last_result", "last_error", "last_at", "cycles", "total_time",
                   "last_alert", "last_sub")
        tree = ttk.Treeview(win, columns=columns, show="headings")
        headers = {"name": "Tài khoản", "group": "Nhóm", "id": "ID", "status": "Trạng thái", "slot": "Slot",
                   "cycle_now": "Vòng này", "action": "", "last_action": "Hành động cuối", "last_result": "Kết quả",
                   "last_error": "Lỗi gần nhất", "last_at": "Cách đây", "cycles": "Vòng 30 ngày",
                   "total_time": "Tổng ngâm", "last_alert": "Alert gần nhất", "last_sub": "Sub gần nhất"}
        widths = {"name": 140, "group": 100, "id": 85, "status": 85, "slot": 55, "cycle_now": 95,
                  "last_action": 140,
                  "last_result": 62, "last_error": 150, "last_at": 85, "cycles": 70, "total_time": 80,
                  "last_alert": 130, "last_sub": 100}
        for col in columns:
            tree.heading(col, text=headers[col])
            tree.column(col, width=widths[col],
                        anchor="center" if col in ("last_result", "cycles", "total_time") else "w")
        # v1.2.8: item-id -> (tên, hành động, lỗi đầy đủ) cho double-click xem chi tiết
        error_map = {}

        scroll = ttk.Scrollbar(win, command=tree.yview)
        tree.configure(yscrollcommand=scroll.set)
        scroll.pack(side="right", fill="y")
        tree.pack(fill="both", expand=True, padx=(10, 0), pady=(0, 4))
        ttk.Label(win, text="Alert: 'hết khóa' = mới tạo trong 7 ngày (cap 1/tuần). Sub: hôm nay đã Sub = hết lượt ngày. Double-click dòng có lỗi để xem chi tiết.",
                  style="Muted.TLabel").pack(anchor="w", padx=12, pady=(0, 8))

        def _ago(at_str):
            """'2026-10-13T16:58:02' -> '3h trước' / '5 ngày trước' / '?'"""
            try:
                dt = datetime.datetime.fromisoformat(at_str)
                secs = (datetime.datetime.now() - dt).total_seconds()
                if secs < 0:
                    return "vừa xong"
                if secs < 3600:
                    return f"{int(secs // 60)} phút trước"
                if secs < 86400:
                    return f"{int(secs // 3600)}h trước"
                return f"{int(secs // 86400)} ngày trước"
            except Exception:
                return "?"

        def refresh():
            for item in tree.get_children():
                tree.delete(item)
            error_map.clear()
            try:
                db_info = DatabaseHandler().get_profile_dashboard_info()
            except Exception as e:
                db_info = {}
                print(f"[!] Bảng tài khoản: đọc DB lỗi ({e}) — chỉ hiện trạng thái chạy.")
            # v1.4.0: tổng hợp thời gian ngâm 30 ngày gần nhất (best-effort)
            try:
                cyc_info = DatabaseHandler().get_cycle_summary(days=30)
            except Exception:
                cyc_info = {}
            tgt = self._target_secs()  # v1.4.0: 0 = tắt giám sát mục tiêu
            # Map slot đang chạy -> profile_id (kể cả MAIN=None)
            running_pid = {}
            for key, pid in SLOT_PROFILE.items():
                running_pid[pid] = key
            now = time.time()
            rows = self.profile_rows if self.profile_rows else []
            for r in rows:
                pid = r["id"]
                key = running_pid.get(pid)
                if key and SLOT_THREAD_ALIVE.get(key, False):
                    age = int(now - SLOT_LAST_LOG.get(key, now))
                    if age < 180:
                        status, slot_txt = "🟢 đang chạy", key
                    elif age < 600:
                        status, slot_txt = "🟡 chậm", key
                    else:
                        status, slot_txt = "🔴 kẹt", key
                elif key:
                    status, slot_txt = "⚪ vừa xong", key
                else:
                    status, slot_txt = "⚪ nghỉ", ""
                # v1.4.0: cột 'Vòng này' — live khi đang chạy (đỏ ⏰ nếu quá mục tiêu),
                # hoặc thời lượng vòng vừa xong (chưa quá 15 phút); rỗng khi nghỉ lâu.
                d_c = cyc_info.get(pid, {})
                # v1.4.1: mục tiêu của CHÍNH vòng đang chạy là số bot đã random lúc bắt đầu
                # (SLOT_CYCLE_INFO); nếu chưa có (chạy bản cũ) -> dùng mục tiêu cố định.
                t_eff = tgt
                ci = SLOT_CYCLE_INFO.get(key, {}) if key else {}
                if ci.get("target_s"):
                    t_eff = ci["target_s"]
                cycle_now = ""
                if key and SLOT_THREAD_ALIVE.get(key, False):
                    t0 = SLOT_CYCLE_START.get(key)
                    if t0:
                        el = now - t0
                        cycle_now = _fmt_dur(el) + (" ⏰" if t_eff and el >= t_eff else "")
                elif key:
                    ld = d_c.get("last_duration_s")
                    if ld is not None and d_c.get("last_at"):
                        try:
                            fresh = (now - datetime.datetime.fromisoformat(d_c["last_at"]).timestamp()) < 900
                        except Exception:
                            fresh = False
                        if fresh:
                            t_last = d_c.get("last_target_s") or tgt
                            cycle_now = _fmt_dur(ld) + (" ⏰" if t_last and ld >= t_last else "")
                d = db_info.get(pid, {})
                la = d.get("last_action", "")
                # v1.2.7: kết quả hành động cuối — 'ok'/'error'/None (row trước wiring)
                st = d.get("last_status")
                if st == "error":
                    lr = "❌ lỗi"
                elif st == "ok":
                    lr = "✅ ok"
                else:
                    lr = "·"
                # v1.2.8: lỗi gần nhất — cắt ngắn trong bảng, full text xem qua double-click
                err_full = d.get("last_error") or ""
                err_short = (err_full[:38] + "…") if len(err_full) > 39 else err_full
                lat = _ago(d["last_at"]) if d.get("last_at") else ""
                al = d.get("last_alert", "")
                if al:
                    try:
                        dt = datetime.datetime.fromisoformat(al)
                        days_left = 7 - (datetime.datetime.now() - dt).days
                        al = f"{al[:10]} " + ("(hết khóa)" if days_left > 0 else "(tạo mới được)")
                    except Exception:
                        pass
                sub = d.get("last_sub", "")
                today = datetime.date.today().isoformat()
                if sub:
                    sub = sub + (" (hết lượt)" if sub == today else "")
                iid = tree.insert("", tk.END, values=(
                    r["name"][:42], (r.get("group") or UNGROUPED_LABEL)[:16],
                    pid[:8], status, slot_txt, cycle_now, la, lr, err_short, lat,
                    d_c.get("cycles", 0) or "", _fmt_dur(d_c.get("total_s")) if d_c.get("cycles") else "",
                    al, sub))
                if err_full:
                    error_map[iid] = (r["name"], la, err_full)
            if not rows:
                print("[*] Bảng tài khoản: checklist trống — bấm 'Tải từ GPM' trước.")

        def _show_error_detail(_event=None):
            """v1.2.8: double-click dòng có lỗi -> cửa sổ phụ hiển thị lỗi đầy đủ."""
            sel = tree.selection()
            if not sel:
                return
            info = error_map.get(sel[0])
            if not info:
                return
            name, action, err = info
            dlg = tk.Toplevel(win)
            dlg.title(f"Lỗi gần nhất — {name}")
            dlg.configure(bg=self.C_CARD)
            dlg.geometry("560x320")
            ttk.Label(dlg, text=f"Hành động: {action or '?'}", padding=(10, 8, 10, 2)).pack(anchor="w")
            txt = tk.Text(dlg, wrap="word", height=12, font=("Consolas", 9),
                          bg=self.C_BG, fg=self.C_ERR_FG, relief="flat", padx=6, pady=4)
            txt.pack(fill="both", expand=True, padx=10, pady=(2, 8))
            txt.insert("1.0", err)
            txt.configure(state="disabled")
            ttk.Button(dlg, text="Đóng", command=dlg.destroy).pack(pady=(0, 8))

        tree.bind("<Double-1>", _show_error_detail)

        ttk.Button(bar, text="Làm mới", command=refresh).pack(side="left", padx=(0, 8))
        refresh()

    # ============ v1.4.0: THỜI GIAN NGÂM THEO CHU TRÌNH ============
    def show_cycle_time_dialog(self):
        """Cửa sổ 'Thời gian ngâm': mỗi profile 1 dòng — số vòng / tổng / TB / quá mục tiêu.
        Double-click dòng -> chi tiết từng chu trình (cycle_history). Tự tươi 15s khi app đang chạy."""
        win = tk.Toplevel(self.root)
        win.title("Thời gian ngâm — chu trình")
        win.configure(bg=self.C_CARD)
        win.geometry("1150x540")

        bar = ttk.Frame(win, padding=8)
        bar.pack(fill="x")
        ttk.Label(bar, text="Nguồn: cycle_history (mỗi lần BẮT ĐẦU CHẠY 1 profile = 1 chu trình; lỗi/dừng giữa vòng vẫn ghi).",
                  style="Muted.TLabel").pack(side="left")

        var_days = tk.StringVar(value="30")
        ttk.Label(bar, text="Ngày:").pack(side="right", padx=(4, 0))
        cbo_days = ttk.Combobox(bar, textvariable=var_days, values=["7", "30", "90"],
                                state="readonly", width=4)
        cbo_days.pack(side="right", padx=(4, 8))

        # v1.4.1: +cột 'last_target' (mục tiêu bot random cho vòng cuối) — thấy rõ vòng nào
        # bị bot đặt mốc nào; cột 'over' đếm vòng vượt CHÍNH mốc của nó.
        columns = ("name", "group", "id", "cycles", "total", "avg", "okerr", "over",
                   "last_target", "last_dur", "last_at", "running")
        tree = ttk.Treeview(win, columns=columns, show="headings")
        headers = {"name": "Tài khoản", "group": "Nhóm", "id": "ID", "cycles": "Số vòng",
                   "total": "Tổng ngâm", "avg": "TB/vòng", "okerr": "Ok / Lỗi / Dừng",
                   "over": "Qua mục tiêu", "last_target": "M.tiêu cuối", "last_dur": "Vòng cuối",
                   "last_at": "Xong lúc", "running": "Đang chạy"}
        widths = {"name": 140, "group": 92, "id": 78, "cycles": 58, "total": 78, "avg": 66,
                  "okerr": 100, "over": 76, "last_target": 72, "last_dur": 70, "last_at": 116,
                  "running": 95}
        for col in columns:
            tree.heading(col, text=headers[col])
            tree.column(col, width=widths[col],
                        anchor="center" if col in ("cycles", "total", "avg", "okerr", "over",
                                                   "last_target", "last_dur", "running") else "w")
        scroll = ttk.Scrollbar(win, command=tree.yview)
        tree.configure(yscrollcommand=scroll.set)
        scroll.pack(side="right", fill="y")
        tree.pack(fill="both", expand=True, padx=(10, 0), pady=(0, 4))

        status = ttk.Label(win, text="", style="Muted.TLabel")
        status.pack(anchor="w", padx=12, pady=(0, 2))
        ttk.Label(win, text="Mục tiêu mặc định = 0: BOT TỰ RANDOM mỗi vòng (mỗi profile một số khác nhau). Cột 'M.tiêu cuối' = mốc bot đặt cho vòng cuối. Double-click dòng để xem chi tiết từng vòng.",
                  style="Muted.TLabel").pack(anchor="w", padx=12, pady=(0, 8))

        def refresh():
            for item in tree.get_children():
                tree.delete(item)
            try:
                days = int(var_days.get())
            except ValueError:
                days = 30
            tgt = self._target_secs()
            try:
                cyc = DatabaseHandler().get_cycle_summary(days=days, target_s=tgt)
            except Exception as e:
                status.config(text=f"Lỗi đọc DB: {e}")
                return
            # union: profile trong checklist + profile có dữ liệu DB (dù đã xóa khỏi checklist)
            known = {r["id"]: r for r in (self.profile_rows or [])}
            pids = list(known.keys()) + [p for p in cyc if p not in known]
            now = time.time()
            running_pid = {pid: key for key, pid in SLOT_PROFILE.items()}
            n_cyc = sum(d.get("cycles", 0) for d in cyc.values())
            tot_s = sum(d.get("total_s", 0) for d in cyc.values())
            for pid in pids:
                r = known.get(pid, {})
                d = cyc.get(pid, {})
                cycles = d.get("cycles", 0)
                key = running_pid.get(pid)
                # v1.4.1: mốc của vòng đang chạy = số bot random (SLOT_CYCLE_INFO); nếu chưa có
                # -> mốc cố định. Nhờ vậy ⏰ phản ánh đúng mốc của chính vòng này.
                t_run = tgt
                ci = SLOT_CYCLE_INFO.get(key, {}) if key else {}
                if ci.get("target_s"):
                    t_run = ci["target_s"]
                run_txt = ""
                if key and SLOT_THREAD_ALIVE.get(key, False):
                    t0 = SLOT_CYCLE_START.get(key)
                    if t0:
                        el = now - t0
                        run_txt = _fmt_dur(el) + (" ⏰" if t_run and el >= t_run else "")
                okerr = f"{d.get('ok', 0)} / {d.get('error', 0)} / {d.get('stopped', 0)}" if cycles else ""
                # v1.4.1: tổng 'over' nay LUÔN có nghĩa (đếm theo mốc riêng từng vòng trong DB);
                # vòng cũ không ghi mốc thì không đếm -> '-' khi chưa từng có mốc nào.
                over_val = d.get("over", 0) if cycles else None
                if not cycles:
                    over_cell = ""
                elif tgt:
                    over_cell = over_val
                else:
                    over_cell = over_val if over_val else "-"
                lt = d.get("last_target_s")
                iid = tree.insert("", tk.END, values=(
                    (r.get("name") or pid)[:42],
                    (r.get("group") or UNGROUPED_LABEL)[:16] if cycles or run_txt else "",
                    pid[:8], cycles or "", _fmt_dur(d.get("total_s")) if cycles else "",
                    _fmt_dur(d.get("avg_s")) if cycles else "", okerr, over_cell,
                    _fmt_dur(lt) if lt else ("-" if cycles else ""),
                    _fmt_dur(d.get("last_duration_s")) if d.get("last_duration_s") is not None else "",
                    (d.get("last_at") or "")[:19].replace("T", " "),
                    run_txt,
                ))
            txt = f"{n_cyc} chu trình trong {days} ngày"
            if n_cyc:
                txt += f" · tổng {_fmt_dur(tot_s)} · TB/vòng {_fmt_dur(tot_s / n_cyc)}"
            txt += (" · mục tiêu NGẪU NHIÊN mỗi vòng (bot tự chọn)" if not tgt
                    else f" · mục tiêu cố định {_fmt_dur(tgt)}/vòng")
            status.config(text=txt)

        def _show_detail(_event=None):
            sel = tree.selection()
            if not sel:
                return
            vals = tree.item(sel[0], "values")
            pid8 = vals[2]
            name = vals[0]
            pid = next((p for p in [r["id"] for r in (self.profile_rows or [])] + list(cyc_keys)
                        if p[:8] == pid8), None)
            if not pid:
                return
            try:
                days = int(var_days.get())
            except ValueError:
                days = 30
            rows = DatabaseHandler().get_cycle_rows(pid, days=days)
            dlg = tk.Toplevel(win)
            dlg.title(f"Chu trình — {name}")
            dlg.configure(bg=self.C_CARD)
            dlg.geometry("980x470")
            t2 = ttk.Treeview(dlg, columns=("st", "fi", "du", "tg", "stat", "act", "ph", "err"),
                              show="headings")
            for col, txt in (("st", "Bắt đầu"), ("fi", "Kết thúc"), ("du", "Thời lượng"),
                             ("tg", "Mục tiêu"), ("stat", "Kết quả"), ("act", "Hành động"),
                             ("ph", "Chế độ"), ("err", "Lỗi")):
                t2.heading(col, text=txt)
                t2.column(col, width={"st": 130, "fi": 130, "du": 78, "tg": 74, "stat": 68,
                                      "act": 68, "ph": 68, "err": 270}[col],
                          anchor="center" if col in ("du", "tg", "stat", "act", "ph") else "w")
            s2 = ttk.Scrollbar(dlg, command=t2.yview)
            t2.configure(yscrollcommand=s2.set)
            s2.pack(side="right", fill="y")
            t2.pack(fill="both", expand=True, padx=(10, 0), pady=8)
            lab = {"ok": "✅ ok", "error": "❌ lỗi", "stopped": "⏹ dừng"}
            for r_ in rows:
                tgt_r = r_.get("target_s")
                # v1.4.1: ⏰ đánh dấu vòng vượt mốc riêng của nó (hay đúng mốc vẫn tính là 'over')
                dur_r = r_.get("duration_s")
                over_r = (tgt_r and dur_r is not None and dur_r >= tgt_r)
                t2.insert("", tk.END, values=(
                    (r_["started_at"] or "")[:19].replace("T", " "),
                    (r_["finished_at"] or "")[:19].replace("T", " "),
                    _fmt_dur(dur_r) + (" ⏰" if over_r else ""),
                    _fmt_dur(tgt_r) if tgt_r else "-",
                    lab.get(r_["status"], r_["status"] or ""),
                    r_["actions"] or "", r_["phase"] or "", (r_["error"] or "")[:160]))
            ttk.Label(dlg, text=f"{len(rows)} chu trình gần nhất trong {days} ngày.",
                      style="Muted.TLabel").pack(anchor="w", padx=12)
            ttk.Button(dlg, text="Đóng", command=dlg.destroy).pack(pady=(4, 10))

        tree.bind("<Double-1>", _show_detail)
        # virtual event: cùng handler, để test tự động kích được (Tk không simulate được <Double-1>)
        win.bind("<<ShowCycleDetail>>", _show_detail)

        # Cho _show_detail tra profile_id đầy đủ theo 8 ký tự đầu
        try:
            cyc_keys = list(DatabaseHandler().get_cycle_summary(days=3650).keys())
        except Exception:
            cyc_keys = []

        ttk.Button(bar, text="Làm mới", command=refresh).pack(side="right", padx=(0, 8))
        refresh()

        def _auto():
            # tự tươi 15s khi dialog còn mở (đặc biệt hữu ích lúc đang chạy)
            try:
                if win.winfo_exists():
                    refresh()
                    win.after(15000, _auto)
            except Exception:
                pass
        win.after(15000, _auto)

    # ================= MỐC NUÔI ACC 7 NGÀY (v1.3.5) =================
    def _parse_date_input(self, raw):
        """'2026-10-15' / '15/10/2026' / '15-10-2026' -> 'YYYY-MM-DD'. Sai/empty -> None."""
        raw = (raw or "").strip()
        if not raw:
            return None
        for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y"):
            try:
                return datetime.datetime.strptime(raw, fmt).date().isoformat()
            except ValueError:
                pass
        return None

    def _day_number(self, start_str):
        """Ngày thứ N theo dương lịch (ngày bắt đầu = Ngày 1). Future -> 0. Format lỗi -> None."""
        try:
            d0 = datetime.date.fromisoformat(start_str)
        except Exception:
            return None
        delta = (datetime.date.today() - d0).days
        return delta + 1 if delta >= 0 else 0

    def _stage_note(self, day):
        """Nhãn trạng thái theo Ngày thứ N (dialog mốc). Hợp mốc sheet: Stage 0 = Ngày 1-4."""
        if day is None:
            return "ngày đặt không hợp lệ"
        if day == 0:
            return "chưa tới ngày bắt đầu"
        if day <= STAGE0_DAYS:
            left = STAGE0_DAYS - day + 1
            return f"Giai đoạn 0 (ngâm proxy, chưa mail) — còn {left} ngày tới mốc làm tay"
        return (f"NGÀY {day}: ĐẾN LÚC LÀM TAY — lắp mail + Móng bảo mật "
                "(2SV, email/SĐT khôi phục, ESB). Sau đó chuyển app sang pha 2.")

    def show_stage_timeline(self):
        """Dialog 'Mốc nuôi acc 7 ngày': đặt NGÀY BẮT ĐẦU cho từng tài khoản (Ngày 1 = Giai đoạn 0,
        lắp proxy chưa mail) — app đếm Ngày thứ N và chỉ khi nào tới mốc làm tay (lắp mail)."""
        win = tk.Toplevel(self.root)
        win.title("Mốc nuôi acc 7 ngày")
        win.configure(bg=self.C_CARD)
        win.geometry("980x480")
        ttk.Label(
            win,
            text=(f"Ngày 1 = bắt đầu Giai đoạn 0 (lắp proxy, CHƯA lắp mail) — bot tự ngâm {STAGE0_DAYS} ngày. "
                  f"Hết {STAGE0_DAYS} ngày (từ Ngày {STAGE0_DAYS + 1}) tới lượt BẠN LÀM TAY: lắp mail + "
                  "Móng bảo mật (sheet dòng 3). App popup nhắc đúng 1 lần cho mỗi tài khoản."),
            style="Muted.TLabel", wraplength=820, justify="left").pack(anchor="w", padx=12, pady=(10, 4))

        columns = ("name", "group", "id", "start", "day", "note")
        tree = ttk.Treeview(win, columns=columns, show="headings")
        for col, head, w, anchor in (("name", "Tài khoản", 200, "w"), ("group", "Nhóm", 110, "w"),
                                     ("id", "ID", 90, "w"),
                                     ("start", "Ngày bắt đầu", 110, "center"),
                                     ("day", "Ngày thứ", 75, "center"),
                                     ("note", "Trạng thái / việc cần làm", 350, "w")):
            tree.heading(col, text=head)
            tree.column(col, width=w, anchor=anchor)
        scroll = ttk.Scrollbar(win, command=tree.yview)
        tree.configure(yscrollcommand=scroll.set)
        scroll.pack(side="right", fill="y")
        tree.pack(fill="both", expand=True, padx=(10, 0), pady=(4, 4))

        def refresh():
            for item in tree.get_children():
                tree.delete(item)
            try:
                starts = DatabaseHandler().get_profile_start_dates()
            except Exception as e:
                starts = {}
                print(f"[!] Mốc nuôi acc: đọc DB lỗi ({e}).")
            # Nguồn dòng: checklist hiện tại + config phiên trước + mọi pid từng đặt ngày (DB)
            seen = {}
            groups = {}
            for r in self.profile_rows:
                seen[r["id"]] = r["name"] or r["id"][:8]
                groups[r["id"]] = r.get("group") or ""
            for p in (self.cfg.get("profiles") or []):
                if isinstance(p, dict) and p.get("id"):
                    seen.setdefault(p["id"], p.get("name") or p["id"][:8])
                    groups.setdefault(p["id"], p.get("group") or "")
            for pid in starts:
                seen.setdefault(pid, pid[:8])
            for pid, name in seen.items():
                s = starts.get(pid) or ""
                day = self._day_number(s) if s else None
                # iid = pid ĐẦY ĐỦ (cột ID chỉ hiển thị 8 ký tự) — set/clear cần full UUID
                tree.insert("", tk.END, iid=pid, values=(
                    (name or pid[:8])[:42], (groups.get(pid) or UNGROUPED_LABEL)[:16], pid[:8],
                    s or "— chưa đặt —",
                    day if day is not None else "—",
                    self._stage_note(day) if s else "Bấm 'Đặt hôm nay' để bắt đầu đếm"))

        def _sel_pid():
            sel = tree.selection()
            if not sel:
                messagebox.showwarning("Mốc nuôi acc", "Chọn 1 dòng tài khoản trước.", parent=win)
                return None
            return sel[0]

        def set_today():
            pid = _sel_pid()
            if not pid:
                return
            DatabaseHandler().set_profile_start_date(pid, datetime.date.today().isoformat())
            refresh()

        def set_other():
            from tkinter import simpledialog
            pid = _sel_pid()
            if not pid:
                return
            raw = simpledialog.askstring(
                "Đặt ngày bắt đầu",
                "Ngày bắt đầu ngâm (vd 2026-10-15 hoặc 15/10/2026):",
                initialvalue=datetime.date.today().isoformat(), parent=win)
            d = self._parse_date_input(raw)
            if raw and d is None:
                messagebox.showerror("Mốc nuôi acc",
                                     f"Ngày không hợp lệ: '{raw}'\nĐịnh dạng: YYYY-MM-DD hoặc DD/MM/YYYY",
                                     parent=win)
                return
            if not raw:
                return
            DatabaseHandler().set_profile_start_date(pid, d)
            refresh()

        def clear_date():
            pid = _sel_pid()
            if not pid:
                return
            # Xóa = lưu chuỗi rỗng (check_stage1/dialog đều coi rỗng là chưa đặt)
            DatabaseHandler().set_profile_start_date(pid, "")
            refresh()

        bar_btns = ttk.Frame(win, padding=(12, 6))
        bar_btns.pack(fill="x")
        ttk.Button(bar_btns, text="Đặt hôm nay", command=set_today, style="Tool.TButton").pack(side="left")
        ttk.Button(bar_btns, text="Đặt ngày khác…", command=set_other, style="Tool.TButton").pack(side="left", padx=(6, 0))
        ttk.Button(bar_btns, text="Xóa ngày", command=clear_date, style="Tool.TButton").pack(side="left", padx=(6, 0))
        ttk.Button(bar_btns, text="Đóng", command=win.destroy, style="Tool.TButton").pack(side="right")
        refresh()

    def check_stage1_milestones(self):
        """v1.3.5: lúc mở app — profile đã qua Ngày {STAGE0_DAYS} mà CHƯA từng nhắc -> popup 1 lần
        (liệt kê tất cả) + ghi milestone_history. Chỉ đọc DB, không chặn khởi động (best-effort)."""
        try:
            db = DatabaseHandler()
            starts = db.get_profile_start_dates()
        except Exception as e:
            print(f"[!] Mốc nuôi acc: đọc DB lỗi ({e}) — bỏ qua kiểm tra mốc.")
            return
        due = []
        for pid, s in starts.items():
            if not s:
                continue
            day = self._day_number(s)
            if day is None or day <= STAGE0_DAYS:
                continue
            try:
                if db.milestone_notified(pid, STAGE1_MILESTONE_CODE):
                    continue
            except Exception:
                continue
            due.append((pid, day, s))
        if not due:
            return
        name_map = {}
        for p in (self.cfg.get("profiles") or []):
            if isinstance(p, dict) and p.get("id"):
                name_map[p["id"]] = p.get("name") or p["id"][:8]
        lines = []
        for pid, day, s in due:
            nm = (name_map.get(pid) or pid[:8]).strip()[:42]
            lines.append(f"• {nm} ({pid[:8]}) — bắt đầu {s}, Ngày thứ {day}")
            try:
                db.log_milestone(pid, STAGE1_MILESTONE_CODE)
            except Exception:
                pass
        messagebox.showwarning(
            "Đến mốc làm tay — lắp mail + Móng bảo mật",
            (f"Tài khoản dưới đây đã qua {STAGE0_DAYS} ngày ngâm proxy (Giai đoạn 0 "
             "— Giai đoạn 3 theo quy trình của bạn). ĐẾN LÚC LÀM TAY:\n\n"
             + "\n".join(lines)
             + "\n\n" + STAGE1_TASKS_TEXT
             + "\n\nPopup này chỉ nhắc 1 lần/tài khoản. Xem lại mọi lúc bằng nút "
             "'MỐC NUÔI ACC (7 NGÀY)'."),
        )

    def export_activity_csv(self):
        """Sprint 2: xuất dòng activity_history (7/30/90 ngày, chọn trước) ra file CSV UTF-8-BOM."""
        from tkinter import simpledialog
        days = simpledialog.askstring("Xuất CSV", "Số ngày gần nhất (7 / 30 / 90)?",
                                      initialvalue="30", parent=self.root)
        try:
            days_i = int(days)
        except (TypeError, ValueError):
            return
        path = filedialog.asksaveasfilename(
            title="Lưu file CSV", defaultextension=".csv",
            initialfile=f"activity_{datetime.datetime.now().strftime('%Y%m%d_%H%M')}.csv",
            filetypes=[("CSV files", "*.csv")],
        )
        if not path:
            return
        try:
            rows = DatabaseHandler().get_activity_rows(days=days_i)
            with open(path, "w", newline="", encoding="utf-8-sig") as f:
                w = csv.writer(f)
                w.writerow(["profile_id", "action", "platform", "url", "title",
                            "created_at", "status", "duration_s", "error"])
                for r in rows:
                    w.writerow([r.get(k, "") for k in ("profile_id", "action", "platform", "url",
                                                       "title", "created_at", "status", "duration_s", "error")])
            print(f"[+] Đã xuất {len(rows)} dòng activity ({days_i} ngày) -> {path}")
            messagebox.showinfo("Xuất CSV", f"Đã xuất {len(rows)} dòng.\n\n{path}")
        except Exception as e:
            messagebox.showerror("Lỗi xuất CSV", str(e))

    def start_automation(self):
        # Sprint 1.3: tài khoản lấy từ checklist đã tick (Firefox đã bị chặn tick từ UI)
        # v1.4.4: dòng đang bị ẨN bởi bộ lọc Nhóm/Từ khóa KHÔNG được đưa vào danh sách chạy
        # (bộ lọc giờ GIỚI HẠN phạm vi chạy, không chỉ ẩn hiển thị).
        profiles = [r["id"] for r in self.profile_rows
                    if r["var"].get() and not r["firefox"] and not r.get("hidden", False)]
        n_ticked = sum(1 for r in self.profile_rows if r["var"].get() and not r["firefox"])
        n_hidden = n_ticked - len(profiles)

        if not profiles:
            if n_ticked:
                messagebox.showwarning(
                    "Cảnh báo",
                    f"Đã tick {n_ticked} tài khoản nhưng tất cả đang bị ẨN bởi bộ lọc Nhóm/Từ khóa.\n\n"
                    "Chọn 'Tất cả nhóm' / xóa ô Lọc để hiện lại, hoặc tick lại trong danh sách đang hiện.",
                )
            else:
                messagebox.showwarning(
                    "Cảnh báo",
                    "Chưa tick chọn tài khoản nào để ngâm!\n\n"
                    "Bấm 'Tải từ GPM' để kéo danh sách, hoặc 'Dán ID thủ công'.",
                )
            return

        # Sprint 0.3: chặn UUID sai format (ID tải từ API luôn hợp lệ; chặn cho ID dán tay)
        uuid_re = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")
        bad = [p for p in profiles if not uuid_re.match(p)]
        if bad:
            messagebox.showerror(
                "Profile ID không hợp lệ",
                "Những dòng sau không đúng định dạng UUID "
                "(vd 589ce4a3-9143-4f40-89d7-b43f61365e2e):\n\n"
                + "\n".join(bad[:10])
                + ("\n..." if len(bad) > 10 else ""),
            )
            return

        # Sprint 1.4: chủ đề = các CẶP từ khóa (Google ↔ YouTube); YouTube trống -> dùng Google
        themes = self._collect_kw_pairs()

        if not themes:
            themes = [{"google_query": "tin tức mới nhất", "youtube_query": "video giải trí"}]
            
        try: max_workers = int(self.spin_threads.get())
        except ValueError: max_workers = 4

        browser_type = self.var_browser_type.get()
        api_port = self.var_api_port.get()

        # --- KIỂM TRA API ANTI-DETECT TRƯỚC KHI CHẠY ---
        if not self.ping_api(browser_type, api_port):
            messagebox.showerror(
                "Không thấy API",
                f"Không kết nối được {browser_type} ở port {api_port or '(mặc định)'}.\n\n"
                "Hãy mở phần mềm GPM Login / BitBrowser rồi thử lại.",
            )
            return

        STOP_EVENT.clear()  # phiên mới: xóa cờ dừng của lần trước

        self.btn_start.config(state="disabled", text="ĐANG CHẠY...")
        self.btn_stop.config(state="normal")
        self.cbo_brain.config(state="disabled")
        self.cbo_phase.config(state="disabled")
        self.cbo_browser.config(state="disabled")
        for btn in (self.btn_report, self.btn_open_logs, self.btn_load_keywords,
                    self.btn_refresh_profiles, self.btn_add_manual,
                    self.btn_dashboard, self.btn_export_csv, self.btn_timeline,
                    self.btn_phase_info, self.btn_cycle_time, self.btn_api_keys):
            btn.config(state="disabled")
        
        for tab_name in list(self.log_boxes.keys()):
            if tab_name != "MAIN":
                del self.log_boxes[tab_name]
                
        for tab in self.notebook.tabs()[1:]:
            self.notebook.forget(tab)
            
        # v1.4.4: số tab/slot = số profile sẽ chạy (không tạo slot thừa khi profile < luồng)
        n_slots = min(max_workers, len(profiles))
        for i in range(n_slots):
            self._create_tab(f"Slot {i + 1}")
        # v1.4.9: vòng forget ở trên đã gỡ tab thời lượng -> nối lại vào CUỐI cùng,
        # để slot vẫn nằm ở index 1..n_slots (công thức tabs()[slot+1] giữ nguyên).
        self._create_board_tab()

        self._running = True
        self._active_slots = list(range(n_slots))

        if n_hidden:
            print(f"[!] {n_hidden} profile đã tick nhưng đang ẩn bởi bộ lọc Nhóm/Từ khóa - sẽ KHÔNG chạy.")
        print(f"Bắt đầu khởi chạy {len(profiles)} profiles trên {n_slots} luồng...")
        
        screen_w = self.root.winfo_screenwidth()
        screen_h = self.root.winfo_screenheight() - 40
        
        skip_youtube = self.var_skip_youtube.get()
        skip_random_keywords = self.var_skip_random_keywords.get()
        brain_type = self.var_brain_type.get()
        # Map nhãn combobox -> phase string (warmup.py vẫn nhận key clean/mail/youtube như cũ)
        phase = PHASE_MAP.get(self.var_phase_label.get(), "clean")
        fixed_target_s = self._target_secs()  # v1.4.1: >0 = mục tiêu cố định; 0 = bot random mỗi vòng
        self.save_current_config()  # Sprint 1.1: nhớ mọi lựa chọn của phiên này
        threading.Thread(target=self.run_thread_pool, args=(profiles, themes, max_workers, screen_w, screen_h, skip_youtube, skip_random_keywords, browser_type, api_port, brain_type, phase, fixed_target_s), daemon=True).start()

    def run_thread_pool(self, profiles, themes, max_workers, screen_w, screen_h, skip_youtube, skip_random_keywords, browser_type=BROWSER_GPM, api_port="", brain_type="none", phase="clean", fixed_target_s=0):
        # v1.4.4: số slot = min(luồng, số profile) - khớp số tab đã tạo trong start_automation
        n_slots = min(max_workers, len(profiles))
        slots_queue = queue.Queue()
        for i in range(n_slots):
            slots_queue.put(i)
        
        print(f"[System] Đang chạy với Browser: {browser_type.upper()} | Port API: {api_port or 'default'} | AI Brain: {brain_type} | Chế độ ngâm: {phase}")
        print("[System] Mục tiêu vòng: " + (f"CỐ ĐỊNH {_fmt_dur(fixed_target_s)}/vòng (bạn tự đặt)"
                                            if fixed_target_s else "NGẪU NHIÊN mỗi vòng (bot tự chọn, mỗi profile khác nhau)"))
        
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = [executor.submit(worker_wrapper, self, pid, themes, slots_queue, screen_w, screen_h, skip_youtube, skip_random_keywords, browser_type, api_port, brain_type, phase, fixed_target_s) for pid in profiles]
            # v1.2.9: lỗi thoát khỏi worker từng làm f.result() ném lên đây -> toàn bộ
            # đoạn khôi phục UI bên dưới bị nhảy qua -> GUI kẹt "ĐANG CHẠY" vĩnh viễn.
            # Nay mọi exception của future chỉ in log, UI luôn được khôi phục (finally).
            try:
                for f in futures:
                    try:
                        f.result()
                    except Exception as e:
                        print(f"[!] Lỗi luồng nền (đã bỏ qua, UI vẫn khôi phục): {e}")
            finally:
                self._running = False
                self._active_slots = []
                stopped = STOP_EVENT.is_set()
                print("TẤT CẢ PROFILE ĐÃ HOÀN THÀNH." if not stopped
                      else "[!] ĐÃ DỪNG AN TOÀN - các profile còn lại chưa chạy đã được bỏ qua.")
                self.root.after(0, lambda: self.btn_start.config(state="normal", text="BẮT ĐẦU CHẠY"))
                self.root.after(0, lambda: self.btn_stop.config(state="disabled"))
                self.root.after(0, lambda: self.cbo_brain.config(state="readonly"))
                self.root.after(0, lambda: self.cbo_phase.config(state="readonly"))
                self.root.after(0, lambda: self.cbo_browser.config(state="readonly"))
                self.root.after(0, lambda: self._set_utils_state("normal"))
                msg = ("Đã dừng theo yêu cầu." if stopped else "Chạy xong") + f" {len(profiles)} profiles."
                self.root.after(0, lambda: messagebox.showinfo("Hoàn thành", msg))

    # ------------------------------------------------------------------ v1.4.8: API VAULT
    def open_api_key_manager(self):
        """Cổng mật khẩu -> dialog quản lý API key trong .env (khỏi sửa file tay)."""
        if getattr(self, "_api_dialog", None) is not None:
            try:
                if self._api_dialog.winfo_exists():
                    self._api_dialog.lift()
                    return
            except Exception:
                pass
            self._api_dialog = None
        self._ask_api_password(self._open_api_key_dialog)

    def _ask_api_password(self, on_ok, change_mode=False):
        """Dialog mật khẩu phi modal (modal thật sẽ khóa remap theme).

        change_mode=True: ô "Mật khẩu hiện tại" chỉ bắt buộc khi ĐÃ đặt mật khẩu
        riêng (hash trong config); lần đầu đổi từ mật khẩu khởi điểm thì bỏ trống được.
        """
        win = tk.Toplevel(self.root)
        win.title("Đổi mật khẩu tiện ích API" if change_mode else "Mật khẩu tiện ích API")
        win.configure(bg=self.C_CARD)
        win.resizable(False, False)
        win.transient(self.root)
        # PHI GRAB: grab sẽ chặn nút "ĐỔI NỀN" ở cửa sổ chính trong lúc dialog mở,
        # và người dùng có thể cần đổi nền khi đang nhập mật khẩu.
        box = tk.Frame(win, bg=self.C_CARD, padx=16, pady=14)
        box.pack(fill="both", expand=True)

        if change_mode:
            msg = ("Đặt mật khẩu MỚI cho tiện ích API (tối thiểu 4 ký tự).")
            if not api_vault.has_custom_password():
                msg += ("\nTiện ích đang dùng mật khẩu khởi điểm — ô \"Mật khẩu hiện tại\" "
                        "có thể BỎ TRỐNG, hoặc điền mật khẩu khởi điểm.")
            lbl_head = "Đổi mật khẩu"
        else:
            msg = "Nhập mật khẩu để mở tiện ích quản lý API key."
            lbl_head = "Tiện ích API KEY"
        tk.Label(box, text=lbl_head, bg=self.C_CARD, fg=self.C_FG,
                 font=("Segoe UI", 11, "bold")).pack(anchor="w")
        tk.Label(box, text=msg, bg=self.C_CARD, fg=self.C_MUTED, wraplength=330,
                 justify="left").pack(anchor="w", pady=(2, 10))

        rows = []

        def _add_row(label):
            fr = tk.Frame(box, bg=self.C_CARD)
            fr.pack(fill="x", pady=2)
            tk.Label(fr, text=label, width=16, anchor="w", bg=self.C_CARD,
                     fg=self.C_MUTED).pack(side="left")
            var = tk.StringVar()
            en = tk.Entry(fr, textvariable=var, show="•", width=26, bg=self.C_FIELD,
                          fg=self.C_FG, insertbackground=self.C_FG,
                          highlightbackground=self.C_BORDER)
            en.pack(side="left")
            state = {"show": False}

            def _toggle():
                state["show"] = not state["show"]
                en.config(show="" if state["show"] else "•")
                btn.config(text="Ẩn" if state["show"] else "Hiện")
                en.focus_set()

            btn = tk.Button(fr, text="Hiện", width=5, command=_toggle,
                            bg=self.C_CARD2, fg=self.C_FG, relief="flat",
                            activebackground=self.C_CARD, activeforeground=self.C_FG)
            btn.pack(side="left", padx=(6, 0))
            rows.append((var, en))
            return en

        cur_en = _add_row("Mật khẩu hiện tại" if change_mode else "Mật khẩu")
        new_en = None
        confirm_en = None
        if change_mode:
            new_en = _add_row("Mật khẩu mới")
            confirm_en = _add_row("Nhập lại")

        err = tk.Label(box, text="", bg=self.C_CARD, fg=self.C_ERR_FG, anchor="w")
        err.pack(fill="x", pady=(6, 0))

        def _close():
            win.destroy()

        def _submit(_e=None):
            cur = cur_en.get()
            if change_mode:
                if api_vault.has_custom_password():
                    if not api_vault.check_password(cur):
                        err.config(text="Mật khẩu hiện tại không đúng.")
                        return
                new = new_en.get()
                if len(new) < 4:
                    err.config(text="Mật khẩu mới cần tối thiểu 4 ký tự.")
                    return
                if new != confirm_en.get():
                    err.config(text="Mật khẩu nhập lại không khớp.")
                    return
                if api_vault.set_password(new):
                    print("[+] Đã đổi mật khẩu tiện ích API.")
                    messagebox.showinfo("Đổi mật khẩu",
                                        "Mật khẩu mới đã được lưu. Lần mở tiện ích sau dùng mật khẩu này.",
                                        parent=win)
                    _close()
                else:
                    err.config(text="Không lưu được mật khẩu (lỗi ghi app_config).")
                return
            if api_vault.check_password(cur):
                err.config(text="")
                _close()
                on_ok()
            else:
                err.config(text="Sai mật khẩu.")
                cur_en.select_range(0, "end")
                cur_en.focus_set()

        btns = tk.Frame(box, bg=self.C_CARD)
        btns.pack(fill="x", pady=(12, 0))
        ttk.Button(btns, text="Xác nhận", command=_submit).pack(side="right")
        ttk.Button(btns, text="Hủy", command=_close).pack(side="right", padx=(0, 8))

        win.bind("<Return>", _submit)
        win.bind("<Escape>", lambda _e: _close())
        (new_en if change_mode else cur_en).focus_set()

    def _open_api_key_dialog(self):
        """Dialog chính: liệt kê + sửa/xóa/add key trong .env (best-effort, không ném)."""
        win = tk.Toplevel(self.root)
        win.title("Quản lý API KEY")
        win.configure(bg=self.C_CARD)
        win.geometry("780x540")
        win.transient(self.root)
        self._api_dialog = win
        win.protocol("WM_DELETE_WINDOW", lambda: (setattr(self, "_api_dialog", None), win.destroy()))

        body = tk.Frame(win, bg=self.C_CARD, padx=12, pady=10)
        body.pack(fill="both", expand=True)

        tk.Label(body, text=f"File: {api_vault.env_path()}", bg=self.C_CARD,
                 fg=self.C_MUTED, anchor="w").pack(fill="x")
        tk.Label(body, text="Key lưu trong .env và nạp thẳng vào os.environ — AI brain dùng được ngay, không cần mở lại app.",
                 bg=self.C_CARD, fg=self.C_MUTED, anchor="w", wraplength=700,
                 justify="left").pack(fill="x", pady=(0, 8))

        canvas, inner = self._make_scrollable(body, 330)  # helper đã pack canvas+scrollbar vào body

        rows_fr = tk.Frame(inner, bg=self.C_CARD)
        rows_fr.pack(fill="x")
        revealed = {}  # key -> bool (mắt Hiện/ẩn từng dòng, chỉ trong phiên này)

        def _render_rows():
            for w in rows_fr.winfo_children():
                w.destroy()
            try:
                env_pairs = api_vault.list_keys()
            except Exception as e:
                tk.Label(rows_fr, text=f"[!] Không đọc được .env: {e}", bg=self.C_CARD,
                         fg=self.C_ERR_FG).pack(anchor="w")
                return
            env_map = dict(env_pairs)
            known_names = {k for k, _d in api_vault.KNOWN_KEYS}
            ordered = list(api_vault.KNOWN_KEYS)
            ordered += [(k, "") for k, _v in env_pairs if k not in known_names]
            for name, desc in ordered:
                val = env_map.get(name, "")
                fr = tk.Frame(rows_fr, bg=self.C_CARD if name in known_names else self.C_CARD2)
                fr.pack(fill="x", pady=2, padx=2)
                lbl_fr = tk.Frame(fr, bg=fr["bg"])
                lbl_fr.pack(side="left", fill="x", expand=True, padx=(8, 4), pady=5)
                tk.Label(lbl_fr, text=name, bg=fr["bg"], fg=self.C_ACCENT,
                         font=("Consolas", 10, "bold")).pack(anchor="w")
                if desc:
                    tk.Label(lbl_fr, text=desc, bg=fr["bg"], fg=self.C_MUTED,
                             font=("Segoe UI", 8, "italic")).pack(anchor="w")
                shown = val if revealed.get(name) else (api_vault.mask(val) if val else "(trống)")
                val_lbl = tk.Label(fr, text=shown, bg=fr["bg"], fg=self.C_FG,
                                   font=("Consolas", 9), width=26, anchor="e")
                val_lbl.pack(side="left", padx=4)

                eye_btn = tk.Button(fr, text=("Ẩn" if revealed.get(name) else "Hiện"), width=5,
                                    bg=fr["bg"], fg=self.C_FG, relief="flat",
                                    activebackground=self.C_CARD,
                                    activeforeground=self.C_FG)

                def _toggle(name=name, val_lbl=val_lbl, btn=eye_btn):
                    revealed[name] = not revealed.get(name)
                    cur = api_vault.get_key(name) or ""
                    val_lbl.config(text=cur if revealed[name] else (api_vault.mask(cur) if cur else "(trống)"))
                    btn.config(text="Ẩn" if revealed[name] else "Hiện")

                eye_btn.config(command=_toggle)
                eye_btn.pack(side="left", padx=2)

                def _edit(name=name, desc=desc):
                    self._api_key_edit_dialog(name, desc, _refresh)

                def _delete(name=name):
                    if not messagebox.askyesno("Xóa API key",
                                               f"Xóa {name} khỏi .env?\n(AI brain đang dùng key này sẽ mất.)",
                                               parent=win):
                        return
                    if api_vault.delete_key(name):
                        print(f"[+] Đã xóa {name} khỏi .env.")
                        _refresh()
                    else:
                        messagebox.showerror("Lỗi", "Không xóa được — xem log để biết lý do.", parent=win)

                tk.Button(fr, text="Sửa", width=6, command=_edit, bg=fr["bg"], fg=self.C_FG,
                          relief="flat", activebackground=self.C_CARD,
                          activeforeground=self.C_FG).pack(side="left", padx=2)
                tk.Button(fr, text="Xóa", width=6, command=_delete, bg=fr["bg"], fg=self.C_ERR_FG,
                          relief="flat", activebackground=self.C_CARD,
                          activeforeground=self.C_FG).pack(side="left", padx=2)
            if not ordered:
                tk.Label(rows_fr, text="Chưa có key nào trong .env — bấm \"Thêm key\".",
                         bg=self.C_CARD, fg=self.C_MUTED).pack(anchor="w", pady=8)

        def _refresh():
            try:
                _render_rows()
            except Exception as e:
                print(f"[!] Vẽ danh sách API key lỗi: {e}")

        _refresh()

        bar = tk.Frame(win, bg=self.C_CARD, padx=12, pady=10)
        bar.pack(fill="x")
        ttk.Button(bar, text="+ Thêm key", style="Tool.TButton",
                   command=lambda: self._api_key_edit_dialog("", "", _refresh, win)).pack(side="left")
        ttk.Button(bar, text="Đổi mật khẩu", style="Tool.TButton",
                   command=lambda: self._ask_api_password(lambda: None, change_mode=True)).pack(side="left", padx=8)
        ttk.Button(bar, text="Đóng", style="Tool.TButton",
                   command=win.destroy).pack(side="right")

    def _api_key_edit_dialog(self, name, desc, on_saved, parent=None):
        """Dialog thêm/sửa 1 key: tên + value (dán được) + Hiện/ẩn + kiểm tra tên trùng."""
        parent = parent or self._api_dialog
        is_new = not name
        win = tk.Toplevel(self.root)
        win.title("Thêm API key" if is_new else f"Sửa {name}")
        win.configure(bg=self.C_CARD)
        win.resizable(False, False)
        win.transient(parent if parent is not None else self.root)
        # Phi grab (giống dialog mật khẩu): grab thật sẽ khóa nút đổi nền + bảng liệt kê.
        win.lift()

        box = tk.Frame(win, bg=self.C_CARD, padx=16, pady=14)
        box.pack(fill="both", expand=True)
        if desc:
            tk.Label(box, text=desc, bg=self.C_CARD, fg=self.C_MUTED, wraplength=340,
                     justify="left").pack(anchor="w", pady=(0, 8))

        tk.Label(box, text="Tên key (VD: GEMINI_API_KEY)", bg=self.C_CARD, fg=self.C_FG,
                 anchor="w").pack(fill="x")
        name_var = tk.StringVar(value=name)
        name_en = ttk.Entry(box, textvariable=name_var, width=46, font=("Consolas", 10))
        name_en.pack(fill="x", pady=(2, 8))

        tk.Label(box, text="Giá trị (key) — dán trực tiếp được", bg=self.C_CARD, fg=self.C_FG,
                 anchor="w").pack(fill="x")
        val_var = tk.StringVar(value=api_vault.get_key(name) if name else "")
        val_en = ttk.Entry(box, textvariable=val_var, width=46, font=("Consolas", 10), show="•")
        val_en.pack(fill="x", pady=(2, 4))
        if is_new:
            val_en.config(show="")

        def _toggle_show():
            val_en.config(show="" if val_en.cget("show") else "•")

        state_fr = tk.Frame(box, bg=self.C_CARD)
        state_fr.pack(fill="x")
        tk.Checkbutton(state_fr, text="Hiện giá trị", variable=tk.BooleanVar(value=is_new),
                       command=_toggle_show, bg=self.C_CARD, fg=self.C_FG,
                       selectcolor=self.C_FIELD, activebackground=self.C_CARD,
                       activeforeground=self.C_FG).pack(side="left")
        if not is_new:
            tk.Label(box, text="(Đang che — tick \"Hiện giá trị\" để sửa trực tiếp)",
                     bg=self.C_CARD, fg=self.C_MUTED, font=("Segoe UI", 8, "italic")).pack(anchor="w")

        err = tk.Label(box, text="", bg=self.C_CARD, fg=self.C_ERR_FG, anchor="w",
                       wraplength=340, justify="left")
        err.pack(fill="x", pady=(6, 0))

        def _save(_e=None):
            key_name = name_var.get().strip().upper().replace(" ", "_").replace("-", "_")
            value = val_var.get().strip()
            if not key_name or not api_vault._KEY_RE.match(f"{key_name}="):
                err.config(text="Tên key không hợp lệ (chữ/số/gạch dưới, không bắt đầu bằng số).")
                return
            if not value:
                err.config(text="Giá trị rỗng — muốn gỡ key thì bấm Xóa ở danh sách.")
                return
            if is_new and key_name in dict(api_vault.list_keys()):
                if not messagebox.askyesno("Key đã tồn tại",
                                           f"{key_name} đã có trong .env. Ghi đè key mới?", parent=win):
                    return
            if api_vault.set_key(key_name, value):
                print(f"[+] Đã lưu {key_name} vào .env + os.environ.")
                win.destroy()
                on_saved()
            else:
                err.config(text="Không ghi được .env — xem log để biết lý do.")

        btns = tk.Frame(box, bg=self.C_CARD)
        btns.pack(fill="x", pady=(12, 0))
        ttk.Button(btns, text="Lưu", command=_save).pack(side="right")
        ttk.Button(btns, text="Hủy", command=win.destroy).pack(side="right", padx=(0, 8))
        win.bind("<Return>", _save)
        win.bind("<Escape>", lambda _e: win.destroy())
        (name_en if is_new else val_en).focus_set()

    def _set_utils_state(self, state):
        for btn in (self.btn_report, self.btn_open_logs, self.btn_load_keywords,
                    self.btn_refresh_profiles, self.btn_add_manual,
                    self.btn_dashboard, self.btn_export_csv, self.btn_timeline,
                    self.btn_phase_info, self.btn_cycle_time, self.btn_api_keys):
            btn.config(state=state)

    def _apply_log_filter(self):
        """Sprint 2: bật/tắt chế độ 'chỉ hiện lỗi+cảnh báo' cho máy chủ log (GUI + file)."""
        stdout = sys.stdout
        if isinstance(stdout, ThreadSafeStdout):
            stdout.level_filter = {"error", "warn"} if self.var_log_errors.get() else None

    def ping_api(self, browser_type, api_port):
        """Kiểm tra API anti-detect có sống không trước khi khởi chạy threads."""
        try:
            port_int = int(api_port) if api_port else None
        except ValueError:
            port_int = None
        try:
            if browser_type == BROWSER_BITBROWSER:
                port = port_int or 54345
                # BitBrowser: mọi HTTP response (kể cả lỗi) nghĩa là API đang sống
                requests.post(f"http://127.0.0.1:{port}/health", json={}, timeout=3)
                return True
            port = port_int or 9495
            r = requests.get(
                f"http://localhost:{port}/api/v1/profiles?page_index=1&page_size=1",
                timeout=3,
            )
            return r.status_code == 200
        except requests.exceptions.RequestException:
            return False

if __name__ == "__main__":
    root = tk.Tk()
    app = AutomationApp(root)
    root.mainloop()