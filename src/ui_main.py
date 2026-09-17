import sys
import os
import time
import random
import threading
import queue
import tkinter as tk
from tkinter import ttk, messagebox
from concurrent.futures import ThreadPoolExecutor

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../')))

from src.browser.antidetect import AntidetectAPI
from src.browser.playwright_core import BrowserController
from src.database.db_handler import DatabaseHandler
from src.workflow.warmup import WarmupWorkflow

# ==========================================
# MÁY CHỦ BẮT LOG ĐỘC LẬP TỪNG LUỒNG
# ==========================================
THREAD_SLOTS = {} 

class ThreadSafeStdout:
    def __init__(self, log_callback):
        self.stdout = sys.stdout
        self.log_callback = log_callback
        
    def write(self, msg):
        self.stdout.write(msg)
        if msg.strip('\n'):
            tid = threading.get_ident()
            slot = THREAD_SLOTS.get(tid, "MAIN")
            self.log_callback(slot, msg)
            
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
def run_single_profile(api, profile_id, profile_name, themes, slot_index, screen_w, screen_h, skip_youtube, skip_random_keywords):
    print(f"\n[{profile_name}] 🚀 Đang yêu cầu API mở trình duyệt...")
    
    db = DatabaseHandler()
    
    try:
        needs_sub = db.can_subscribe_today(profile_id)
        ws_url = api.open_profile(profile_id)
        
        if not ws_url:
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
            
            # TRUYỀN THAM SỐ SKIP YOUTUBE VÀO WARMUP
            warmup = WarmupWorkflow(
                context=context, 
                db_handler=db, 
                profile_id=profile_id, 
                needs_sub=needs_sub,
                session_theme=session_theme,
                skip_youtube=skip_youtube,
                skip_random_keywords=skip_random_keywords
            )
            
            total_actions = random.randint(4, 8)
            warmup.run_random_session(total_actions=total_actions)
            
    except Exception as e:
        print(f"[{profile_name}] ❌ Lỗi quá trình chạy: {e}")
    finally:
        print(f"[{profile_name}] 🧹 Đang dọn dẹp và đóng Profile...")
        try: controller.close()
        except: pass
        try: api.close_profile(profile_id)
        except Exception as e: print(f"[{profile_name}] ❌ Lỗi khi đóng profile: {e}")
        time.sleep(2)

def worker_wrapper(app_instance, profile_id, themes, slots_queue, screen_w, screen_h, skip_youtube, skip_random_keywords):
    slot = slots_queue.get() 
    THREAD_SLOTS[threading.get_ident()] = f"Slot {slot + 1}"
    
    api = AntidetectAPI()
    profile_name = api.get_profile_name(profile_id)
    
    app_instance.update_tab_name(slot, profile_name)
    
    try:
        run_single_profile(api, profile_id, profile_name, themes, slot, screen_w, screen_h, skip_youtube, skip_random_keywords)
    finally:
        app_instance.update_tab_name(slot, f"Slot {slot + 1}")
        slots_queue.put(slot)

# ==========================================
# 3. GIAO DIỆN NGƯỜI DÙNG
# ==========================================
class AutomationApp:
    def __init__(self, root):
        self.root = root
        self.root.title("GPM Automation Tool - Multi-Threads with Live Logs")
        self.root.geometry("1000x850") 
        
        style = ttk.Style()
        style.theme_use('clam')
        
        frame_ctrl = ttk.Frame(root, padding=10)
        frame_ctrl.pack(fill="x", side="top")
        
        ttk.Label(frame_ctrl, text="Danh sách Profile ID (Mỗi ID một dòng):").pack(anchor="w")
        self.txt_profiles = tk.Text(frame_ctrl, height=5, width=50)
        self.txt_profiles.pack(fill="both", expand=True, pady=(0, 10))
        self.txt_profiles.insert(tk.END, "c1a14c8d-24a7-49d1-8812-a7f9eda17cea\n")

        ttk.Label(frame_ctrl, text="Danh sách Keywords (Cú pháp: Google Keyword | YouTube Keyword):").pack(anchor="w")
        self.txt_keywords = tk.Text(frame_ctrl, height=5, width=50)
        self.txt_keywords.pack(fill="both", expand=True, pady=(0, 10))
        self.txt_keywords.insert(tk.END, "tin tức kinh tế vĩ mô | global macro economics\nchứng khoán mỹ | us stock market analysis")
        
        tools_frame = ttk.Frame(frame_ctrl)
        tools_frame.pack(fill="x", pady=5)
        
        ttk.Label(tools_frame, text="Số Threads (Luồng):").pack(side="left")
        self.spin_threads = ttk.Spinbox(tools_frame, from_=1, to=20, width=5)
        self.spin_threads.pack(side="left", padx=5)
        self.spin_threads.set(4) 
        
        # --- BỔ SUNG CHECKBOX YOUTUBE ---
        self.var_skip_youtube = tk.BooleanVar(value=False)
        self.chk_skip_youtube = ttk.Checkbutton(tools_frame, text="Bỏ qua xem YouTube", variable=self.var_skip_youtube)
        self.chk_skip_youtube.pack(side="left", padx=20)

        # --- BỔ SUNG CHECKBOX BỎ QUA TỪ KHÓA NGẪU NHIÊN ---
        self.var_skip_random_keywords = tk.BooleanVar(value=False)
        self.chk_skip_random_keywords = ttk.Checkbutton(tools_frame, text="Bỏ qua từ khóa ngẫu nhiên", variable=self.var_skip_random_keywords)
        self.chk_skip_random_keywords.pack(side="left", padx=20)
        
        self.btn_start = ttk.Button(tools_frame, text="🚀 BẮT ĐẦU CHẠY", command=self.start_automation)
        self.btn_start.pack(side="right", padx=10, ipadx=20, ipady=5)
        
        self.notebook = ttk.Notebook(root)
        self.notebook.pack(fill="both", expand=True, padx=10, pady=10)
        
        self.log_boxes = {} 
        self._create_tab("MAIN") 
        
        sys.stdout = ThreadSafeStdout(self.append_log)

    def _create_tab(self, tab_name):
        frame = ttk.Frame(self.notebook)
        self.notebook.add(frame, text=f" {tab_name} ")
        
        txt_log = tk.Text(frame, bg="#1e1e1e", fg="#00ff00", font=("Consolas", 10), state="disabled")
        txt_log.pack(fill="both", expand=True)
        
        scrollbar = ttk.Scrollbar(txt_log, command=txt_log.yview)
        scrollbar.pack(side="right", fill="y")
        txt_log.config(yscrollcommand=scrollbar.set)
        
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

    def start_automation(self):
        raw_profiles = self.txt_profiles.get("1.0", tk.END)
        profiles = [p.strip() for p in raw_profiles.split("\n") if p.strip()]
        
        if not profiles:
            messagebox.showwarning("Cảnh báo", "Vui lòng nhập ít nhất 1 Profile ID!")
            return

        raw_kw = self.txt_keywords.get("1.0", tk.END)
        kw_lines = [k.strip() for k in raw_kw.split("\n") if k.strip()]
        
        themes = []
        for line in kw_lines:
            if "|" in line:
                g, y = line.split("|", 1)
                themes.append({"google_query": g.strip(), "youtube_query": y.strip()})
            else:
                themes.append({"google_query": line.strip(), "youtube_query": line.strip()})
                
        if not themes:
            themes = [{"google_query": "tin tức mới nhất", "youtube_query": "video giải trí"}]
            
        try: max_workers = int(self.spin_threads.get())
        except ValueError: max_workers = 4
            
        self.btn_start.config(state="disabled", text="⏳ ĐANG CHẠY...")
        
        for tab_name in list(self.log_boxes.keys()):
            if tab_name != "MAIN":
                del self.log_boxes[tab_name]
                
        for tab in self.notebook.tabs()[1:]:
            self.notebook.forget(tab)
            
        for i in range(max_workers):
            self._create_tab(f"Slot {i + 1}")
            
        print(f"Bắt đầu khởi chạy {len(profiles)} profiles trên {max_workers} luồng...")
        
        screen_w = self.root.winfo_screenwidth()
        screen_h = self.root.winfo_screenheight() - 40
        
        # TRUYỀN BIẾN SKIP_YOUTUBE VÀO THREAD POOL
        skip_youtube = self.var_skip_youtube.get()
        skip_random_keywords = self.var_skip_random_keywords.get()
        threading.Thread(target=self.run_thread_pool, args=(profiles, themes, max_workers, screen_w, screen_h, skip_youtube, skip_random_keywords), daemon=True).start()

    def run_thread_pool(self, profiles, themes, max_workers, screen_w, screen_h, skip_youtube, skip_random_keywords):
        slots_queue = queue.Queue()
        for i in range(max_workers):
            slots_queue.put(i)
        
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = [executor.submit(worker_wrapper, self, pid, themes, slots_queue, screen_w, screen_h, skip_youtube, skip_random_keywords) for pid in profiles]
            for f in futures:
                f.result()
            
        print("TẤT CẢ PROFILE ĐÃ HOÀN THÀNH.")
        self.root.after(0, lambda: self.btn_start.config(state="normal", text="🚀 BẮT ĐẦU CHẠY"))
        self.root.after(0, lambda: messagebox.showinfo("Hoàn thành", f"Đã chạy xong {len(profiles)} profiles!"))

if __name__ == "__main__":
    root = tk.Tk()
    app = AutomationApp(root)
    root.mainloop()