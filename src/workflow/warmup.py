import hashlib
import random
import time

class WarmupWorkflow:
    def __init__(self, context, db_handler=None, profile_id=None, needs_sub=False, session_theme=None, skip_youtube=False, skip_random_keywords=False, brain=None, phase="clean", should_stop=None):
        self.context = context
        self.db = db_handler
        self.profile_id = profile_id
        self.needs_sub = needs_sub
        self.brain = brain
        self.skip_youtube = skip_youtube # LƯU TRẠNG THÁI TICK BỎ QUA YOUTUBE
        self.skip_random_keywords = skip_random_keywords # LƯU TRẠNG THÁI TICK BỎ QUA TỪ KHÓA NGẪU NHIÊN
        # Giai đoạn ngâm: "clean" (trắng, chưa mail) | "mail" (đã login mail) | "youtube" (cày YouTube)
        self.phase = phase if phase in ("clean", "mail", "youtube") else "clean"
        # Callback dừng an toàn: GUI truyền (vd STOP_EVENT.is_set) -> phiên dừng sau hành động hiện tại
        self._should_stop_cb = should_stop
        self.context.on("dialog", lambda dialog: dialog.accept())

        # --- Per-profile deterministic RNG cho human typing ---
        seed_str = str(self.profile_id) if self.profile_id else str(time.time())
        seed_hash = hashlib.md5(seed_str.encode()).hexdigest()
        self.rng = random.Random(seed_hash)
        # Base WPM cố định per profile: phân bố 45-75, đỉnh ~58
        self.base_wpm = max(45, min(75, 55 + int(seed_hash[:4], 16) % 26 - 10))

        self.session_theme = session_theme or {
            "google_query": "tin tức mới nhất",
            "youtube_query": "video giải trí"
        }
        # v1.4.5: nhớ selector popup đã báo lần cuối -> chống log lặp (xem _close_popups)
        self._popup_sel_memo = None

    @property
    def stop_requested(self):
        """Đọc cờ dừng từ callback GUI truyền vào (should_stop)."""
        try:
            return bool(self._should_stop_cb and self._should_stop_cb())
        except Exception:
            return False

    # v1.4.3: bounding_box() của Playwright CHỜ tối đa 30s rồi mới raise TimeoutError.
    # Element đã bị DOM render lại (detached) hoặc locator 0 khớp đều bị coi là "chưa
    # sẵn sàng" -> mỗi lần gọi là 30s ĐỨNG IM không log gì. Đo thật: detached ->
    # "Timeout 30000ms exceeded", is_visible() thì trả False tức thời.
    # => Mọi chỗ cần toạ độ PHẢI đi qua helper này (tối đa 1.5s) thay vì gọi trực tiếp.
    def _safe_bbox(self, element, timeout=1500):
        try:
            if not element.is_visible():
                return None
        except Exception:
            return None
        try:
            return element.bounding_box(timeout=timeout)
        except Exception:
            return None

    def random_sleep(self, min_s=2, max_s=5):
        time.sleep(random.uniform(min_s, max_s))

    def _safe_ask_keyword(self, topic_hint="", platform_label="Google"):
        """Hỏi AI sinh từ khóa tìm kiếm tự nhiên. Trả về string hoặc None nếu lỗi.
        Có topic_hint: sinh BIẾN THỂ xoay quanh chủ đề đó (nhất quán persona trong phiên).
        Không hint: sinh ngẫu nhiên đa chủ đề như cũ.
        platform_label: "Google" (mặc định) hoặc "YouTube" — chỉ ảnh hưởng cách diễn đạt prompt."""
        if not self.brain:
            return None
        try:
            if topic_hint:
                prompt = (
                    f"Bạn là người dùng Việt Nam đang lướt web. Hãy tạo 1 từ khóa tìm kiếm {platform_label} "
                    "ngắn gọn (3-8 từ), là biến thể hoặc cách diễn đạt khác xoay quanh chủ đề cho trước "
                    "(không cần giống nguyên văn; có thể cụ thể hơn hoặc rộng hơn một chút nhưng phải liên quan). "
                    f"Chủ đề: {topic_hint}. "
                    "Giữ đúng ngôn ngữ tự nhiên như người dùng thật (chủ đề tiếng Việt thì trả về tiếng Việt). "
                    "Chỉ trả về đúng từ khóa, không giải thích, không dấu ngoặc."
                )
            else:
                prompt = (
                    "Bạn là người dùng Việt Nam đang lướt web. Hãy tạo 1 từ khóa tìm kiếm Google "
                    "ngắn gọn (3-8 từ), tự nhiên, đa dạng chủ đề (tin tức, giải trí, mua sắm, học tập...). "
                    "Chỉ trả về đúng từ khóa, không giải thích, không dấu ngoặc."
                )
            result = self.brain.ask_text(prompt)
            # Làm sạch kết quả
            cleaned = result.strip().strip('"').strip("'").strip()
            if cleaned and len(cleaned) < 100:
                print(f"  [AI] Từ khóa {platform_label} được sinh: '{cleaned}'")
                return cleaned
        except Exception as e:
            print(f"  [!] Lỗi khi hỏi AI keyword: {e}")
        return None

    # ==========================================
    # CÁC HÀNH ĐỘNG NGUYÊN TỬ (ATOMIC ACTIONS)
    # ==========================================

    def action_search_google(self, page):
        """Hành động 1: Lên Google tìm kiếm theo chủ đề AI chọn"""
        # v1.4.5: action này KHÔNG nằm trong action_map của phase nào (xem run_random_session)
        # -> hiện là code chết. Nếu định bật lại: bấm kết quả Google phải dùng
        # Locator.click() + poll page.url (SERP đổi href thành /goto?url=, và
        # human_click ở đây KHÔNG kích hoạt điều hướng — xem _navigate_via_google).
        print("  -> [Action] Tìm kiếm Google...")
        
        # [CẬP NHẬT LẤY TỪ KHÓA TỪ AI THEME]
        keyword = self.session_theme.get("google_query", "tin tức thời sự")
        
        try:
            page.goto("https://www.google.com", wait_until="domcontentloaded", timeout=45000)
            self.human_type(page.locator("textarea[name='q'], input[name='q']").first, keyword)
            page.keyboard.press("Enter")
            page.wait_for_load_state("domcontentloaded", timeout=50000)
            
            # --- THÊM MỚI: Giả lập thời gian lướt đọc các kết quả tìm kiếm ---
            print("      + Đang lướt xem và cân nhắc các kết quả...")
            scroll_time = random.randint(8, 15) # Dành ra 8-15s để lướt trang Google
            end_time = time.time() + scroll_time
            while time.time() < end_time:
                # Cuộn xuống từ từ để đọc snippet
                self.smooth_scroll(page, random.randint(300, 700))
                self.random_sleep(3, 4)
            
            # Đôi khi người dùng cuộn ngược lên trên một chút để chọn bài top đầu
            if random.random() < 0.5:
                self.smooth_scroll(page, -random.randint(300, 800))
                self.random_sleep(1, 3)
            # -----------------------------------------------------------------
            
            # 2. Đếm số lượng thẻ h3
            total = page.locator("h3").count()
            
            if total > 0:
                choice_index = random.randint(0, min(total - 1, 10))  # Chọn trong top 10 kết quả
                
                print(f"      + Quyết định click vào kết quả thứ {choice_index + 1}.")
                # 3. Dùng .nth() để click vào vị trí index
                target_result = page.locator("h3").nth(choice_index)
                self.human_click(page, target_result)
                page.wait_for_load_state("domcontentloaded", timeout=30000)
                
                # Vào bài viết và bắt đầu đọc
                self._simulate_scroll_and_read(page, random.randint(120, 300))  # Đọc bài từ 2-5 phút
            else:
                print("      + Không có kết quả tìm kiếm nào.")
                
        except Exception as e:
            print(f"      + Bỏ qua click kết quả tìm kiếm do lỗi: {e}")

    def action_read_news(self, page):
        """Hành động 2: LÊN GOOGLE tìm chủ đề -> bấm vào 1 trang báo -> đọc (không goto thẳng).
        v1.4.1: trước đây goto thẳng trang báo; nay đi qua cổng Google như TikTok/Wikipedia —
        người thật tìm qua Google rồi mới bấm kết quả. Fallback goto thẳng CHỈ khi cổng lỗi."""
        print("  -> [Action] Đọc báo tin tức (qua cổng Google)...")
        # (url đích để fallback, domain dùng cho cổng Google + khớp kết quả tìm kiếm)
        sites = [
            ("https://vietnamnet.vn", "vietnamnet.vn"),
            ("https://tienphong.vn", "tienphong.vn"),
            ("https://vnexpress.net", "vnexpress.net"),
            ("https://dantri.com.vn", "dantri.com.vn"),
            ("https://thanhnien.vn", "thanhnien.vn"),
            ("https://tuoitre.vn", "tuoitre.vn"),
            ("https://zingnews.vn", "zingnews.vn"),
            ("https://cafef.vn", "cafef.vn"),
            ("https://edition.cnn.com/", "cnn.com"),
            ("https://www.bbc.com/news", "bbc.com"),
            ("https://www.nytimes.com/", "nytimes.com"),
            ("https://www.theguardian.com/international", "theguardian.com"),
            ("https://www.reuters.com/", "reuters.com"),
        ]
        target_site, target_domain = random.choice(sites)
        
        try:
            # Cổng vào tự nhiên: gõ "chủ đề + tên báo" trên Google rồi bấm kết quả
            landed = self._navigate_via_google(page, self.session_theme["google_query"], target_domain)
            if not landed:
                print("      + [Google] Không đáp đúng trang báo qua cổng Google — (Fallback Google) vào thẳng.")
                page.goto(target_site, wait_until="domcontentloaded", timeout=45000)
            self.restore_mouse_position(page)
            
            # Lướt nhẹ trang chủ 30-60 giây để ngắm các tin nổi bật
            self._simulate_scroll_and_read(page, 30, 60)
            
            num_clicks = random.randint(1, 2)
            for i in range(num_clicks):
                print(f"      + Đang tìm và click bài báo thứ {i+1}...")
                try:
                    # Bắt tất cả các thẻ a có chứa liên kết
                    all_links = page.locator("a[href]").all()
                    valid_links = []
                    
                    viewport = page.viewport_size
                    vh = viewport['height'] if viewport else 800
                    
                    for link in all_links:
                        try:
                            # 1. Đảm bảo link đang hiển thị
                            if link.is_visible(timeout=500):
                                href = link.get_attribute("href")
                                
                                # 2. Đặc điểm nhận diện bài báo: Link dài > 25 ký tự và chứa dấu gạch ngang "-"
                                if href and "-" in href and len(href) > 25 and "javascript" not in href:
                                    box = self._safe_bbox(link)
                                    
                                    # 3. Lọc bỏ các link rác 1 pixel và lấy các bài nằm gần khung nhìn hiện tại
                                    if box and box['width'] > 10 and box['height'] > 10 and -200 <= box['y'] <= vh + 200:
                                        valid_links.append(link)
                        except:
                            continue

                    if valid_links:
                        # Bốc ngẫu nhiên một bài báo đang có trên màn hình
                        target_link = random.choice(valid_links)
                        
                        print("      + Đã quét thấy bài báo hợp lệ. Đang lăn chuột tới mục tiêu...")
                        self._smooth_scroll_to_element(page, target_link)
                        self.random_sleep(1, 2)
                        
                        # KIỂM TRA: Link này mở trong tab hiện tại hay tab mới?
                        target_attr = target_link.get_attribute("target")
                        
                        if target_attr == "_blank":
                            print("      + Bài báo sẽ mở sang TAB MỚI. Đang bắt tab...")
                            
                            with self.context.expect_page(timeout=10000) as new_page_info:
                                self.human_click(page, target_link) 
                            
                            active_page = new_page_info.value
                            active_page.wait_for_load_state("domcontentloaded", timeout=30000)
                            active_page.bring_to_front() 
                            
                            # Đồng bộ chuột sang tab mới
                            self.enable_virtual_cursor(active_page)
                            self.restore_mouse_position(active_page)
                            
                            print("      + Bắt đầu lướt đọc bài báo...")
                            self._simulate_scroll_and_read(active_page, 60, 180)
                            
                            print("      + Đọc xong, đóng tab phụ và quay về trang chủ.")
                            active_page.close()
                            page.bring_to_front()
                            self.restore_mouse_position(page)
                            
                        else:
                            print("      + Bài báo mở trong TAB HIỆN TẠI.")
                            self.human_click(page, target_link)
                            
                            try:
                                page.wait_for_load_state("domcontentloaded", timeout=30000)
                            except:
                                pass # Bỏ qua nếu trang load chậm
                                
                            self.restore_mouse_position(page)
                            
                            print("      + Bắt đầu lướt đọc bài báo...")
                            self._simulate_scroll_and_read(page, 60, 180)
                            
                            if i < num_clicks - 1:
                                print("      + Back lại trang chủ để tìm bài tiếp theo...")
                                page.go_back(wait_until="commit", timeout=15000)
                                self.restore_mouse_position(page)
                                self.random_sleep(3, 5)
                                
                    else:
                        print("      [-] Khung nhìn hiện tại không bắt được bài báo nào. Bot sẽ lướt thêm để tìm sau.")
                        
                except Exception as e:
                    print(f"      + Không thể click bài báo. Lỗi: {e}")
                    
        except Exception as e:
            print(f"      + Lỗi mạng khi vào trang báo, bỏ qua hành động này. Lỗi: {e}")

    def action_watch_video(self, page):
        """Hành động 3: Xem video từ trang chủ. Nếu trang chủ trống/mới, tự động chuyển sang tìm kiếm theo từ khóa."""
        print("  -> [Action] Kiểm tra trang chủ YouTube...")
        
        try:
            if "youtube.com" not in page.url or page.url == "https://www.youtube.com/":
                # v1.4.6: YouTube là site đích — vào thẳng là CỐ Ý (không phải
                # lỗi bỏ cổng Google; cổng Google chỉ bắt buộc cho TikTok/Wiki/báo).
                print("      + [YouTube] Đích là youtube.com — vào thẳng (site đích, cố ý).")
                # --- FIX LỖI INTERRUPTED NAVIGATION ---
                try:
                    page.goto("https://www.youtube.com", wait_until="domcontentloaded", timeout=45000)
                except Exception as goto_err:
                    if "interrupted" in str(goto_err).lower():
                        print("      [!] Quá trình tải trang bị ngắt do web cũ nhảy redirect. Đang ép tải lại...")
                        try: 
                            page.evaluate("window.stop()") 
                        except: 
                            pass
                        self.random_sleep(2, 4)
                        page.goto("https://www.youtube.com", wait_until="domcontentloaded", timeout=45000)
                    else:
                        raise goto_err
                
                self.random_sleep(3, 5)

            # Lướt nhẹ trang chủ 2-4 nhịp để YouTube tải thêm video
            print("      + Đang lướt để tải danh sách video trang chủ...")
            for _ in range(random.randint(2, 5)):
                self.smooth_scroll(page, random.randint(400, 700))
                self.random_sleep(1, 3)

            # Lấy TOÀN BỘ thẻ <a> chứa link video đang hiển thị trên trang chủ
            videos = page.locator("a[href^='/watch?v=']:visible").all()
            
            # =========================================================================
            # TÍNH NĂNG MỚI: NẾU TRANG CHỦ TRỐNG HOẶC TÀI KHOẢN MỚI KHÔNG CÓ ĐỀ XUẤT
            # =========================================================================
            if not videos:
                print("      [!] Phát hiện trang chủ YouTube chưa có video đề xuất (Tài khoản mới hoặc trống dữ liệu).")
                print("      [+] Đang chuyển hướng sang cơ chế TÌM KIẾM THEO TỪ KHÓA...")
                
                # Gọi thẳng sang hàm tìm kiếm YouTube sẵn có của anh
                self.action_search_youtube(page)
                return
            # =========================================================================
                
            total_videos = len(videos)
            print(f"      + Đã quét thấy {total_videos} video trên trang chủ. Tiến hành xem...")

            # ---------------------------------------------------------
            # v1.4.2: LƯỚT XEM TRƯỚC NHIỀU LƯỢT TRƯỚC KHI CHỐT VIDEO
            # Ở màn hình trang chủ: dừng lại trỏ chuột vào thumbnail xem lướt
            # (hover chờ autoplay preview), rồi quẹt quẹt thêm lượt mới — lặp
            # 1-3 lượt (random tỷ lệ) rồi mới pick 1 video thật sự để xem.
            # ---------------------------------------------------------
            num_sweeps = random.randint(1, 3)
            if num_sweeps > 1:
                print(f"      + Sẽ lướt xem trước {num_sweeps} lượt rồi mới chốt video...")
            else:
                print("      + Sẽ lướt xem trước 1 lượt rồi chốt video...")
            for sweep_idx in range(num_sweeps):
                if not videos:
                    break
                print(f"      + [Lượt lướt {sweep_idx + 1}/{num_sweeps}] Dừng lại trỏ chuột vào thumbnail...")
                self._preview_sweep_browse(page, videos)
                # Quẹt xong -> quét lại danh sách thumb mới tải thêm cho lượt kế
                try:
                    refreshed = page.locator("a[href^='/watch?v=']:visible").all()
                    if refreshed:
                        videos = refreshed
                        total_videos = len(videos)
                except Exception:
                    pass

            # ---------------------------------------------------------
            # CHỌN VIDEO MỤC TIÊU VÀ CLICK 
            # ---------------------------------------------------------
            # v1.4.3: element có thể đã bị YouTube render lại sau các lượt lướt -> lọc lại
            # element còn sống, tránh hover()/click() treo 30s trên node đã detach.
            # (is_visible() trên node detached trả False TỨC THỜI, còn count() thì không
            #  phát hiện được vì element vẫn "khớp" selector.)
            live_videos = []
            for el in videos:
                try:
                    if el.is_visible():
                        live_videos.append(el)
                except Exception:
                    continue
            if not live_videos:
                print("      [!] Thumbnail không còn khả dụng sau khi lướt - chuyển sang TÌM KIẾM theo từ khóa...")
                self.action_search_youtube(page)
                return
            videos = live_videos

            target_video = random.choice(videos)
            print("      + Đã chốt video mục tiêu trên trang chủ. Đang lăn chuột tới vị trí click...")
            
            self._smooth_scroll_to_element(page, target_video)
            self.random_sleep(1, 2)
            
            try:
                target_video.hover(timeout=3000)
            except Exception:
                print("      [!] Không hover được thumbnail (đã bị đổi) - bỏ qua bước ngắm tiêu đề.")
            
            if random.random() > 0.4:
                preview_time = random.randint(2, 5)
                print(f"      + Ngắm nghía tiêu đề thêm {preview_time}s trước khi click...")
                time.sleep(preview_time)
            
            self.human_click(page, target_video)

            self.restore_mouse_position(page)
            self.random_sleep(0.5, 1)
            
            # GỌI HÀM LOGIC XỬ LÝ VIDEO
            total_videos_to_watch = random.randint(2, 3)
            print(f"      + Bắt đầu chuỗi xem YouTube liên hoàn: {total_videos_to_watch} video.")
            self._watch_single_video_logic(page, videos_remaining_to_watch=total_videos_to_watch)
            
        except Exception as e:
            print(f"      + Lỗi trong quá trình xem video trang chủ. Lỗi: {e}")
            time.sleep(random.randint(20, 40))

    def action_go_back(self, page):
        """Hành động 4: Back lại trang trước"""
        print("  -> [Action] Back lại trang trước...")
        try:
            page.go_back(timeout=5000)
            page.wait_for_load_state("load")
            self.random_sleep(3, 6)
            self._simulate_scroll_and_read(page, random.randint(30, 60)) # Về trang cũ đọc lướt tí
        except:
            print("      + Không có lịch sử để back.")

    def action_go_forward(self, page):
        """Hành động 5: Forward sang trang sau"""
        print("  -> [Action] Forward sang trang sau...")
        try:
            page.go_forward(timeout=5000)
            page.wait_for_load_state("load")
            self.random_sleep(3, 6)
        except:
            print("      + Không có lịch sử để forward.")

    def action_search_and_read_news(self, page):
        """Tìm kiếm Google, chuyển sang tab Tin tức và đọc nhiều bài báo liên tiếp"""
        print("  -> [Action] Tìm kiếm Google và chuyển sang tab Tin Tức (News) để đọc...")
        
        # [QUAN TRỌNG] Gán mặc định active_page là tab hiện tại để chống lỗi UnboundLocalError
        active_page = page 
        
        try:
            active_page.goto("https://www.google.com", wait_until="domcontentloaded", timeout=45000)
            self.random_sleep(2, 4)
            self.move_mouse_viewport_center(active_page)
            
            search_box = active_page.locator("textarea[name='q'], input[name='q']").first
            
            # Lấy query từ AI theme, nếu không có thì dùng từ khóa fallback
            query = self.session_theme.get("google_query", "thời sự hôm nay") if hasattr(self, 'session_theme') and self.session_theme else "feeling burned out"
            
            print(f"      + Đang nhập từ khóa: '{query}'...")
            self.human_type(search_box, query)
            print("      + Nhập từ khóa hoàn tất. Đang Enter...")
            
            active_page.keyboard.press("Enter")
            active_page.wait_for_load_state("domcontentloaded", timeout=30000)
            self.random_sleep(3, 5)
            
            # 1. Bấm sang tab Tin tức (News) của Google
            print("      + Đang tìm và bấm sang tab Tin tức (News)...")
            news_tab = active_page.locator("a:has-text('Tin tức'), a:has-text('News'), div[role='tab']:has-text('Tin tức'), div[role='tab']:has-text('News')").first
            if news_tab.is_visible():
                self.human_click(active_page, news_tab)
                active_page.wait_for_load_state("domcontentloaded")
                self.random_sleep(3, 6)
            
            # --- VÒNG LẶP ĐỌC BÁO (1 ĐẾN 3 BÀI) ---
            num_articles_to_read = random.randint(1, 3)
            print(f"      + Kế hoạch: Sẽ lướt và đọc {num_articles_to_read} bài báo trong phiên này.")
            
            read_urls = set() # Bộ nhớ lưu các link đã đọc để không bấm trùng
            
            for article_index in range(num_articles_to_read):
                print(f"\n      + [Google News] Đang tìm và xử lý bài báo thứ {article_index + 1}/{num_articles_to_read}...")
                
                # 2. Cuộn nhẹ để tìm bài báo (hoặc tải thêm bài mới nếu đã đọc các bài trên cùng)
                for _ in range(random.randint(1, 4)):
                    self.smooth_scroll(active_page, random.randint(400, 700))
                    self.random_sleep(2, 4)
                    
                # Quét các liên kết bài báo
                all_article_links = active_page.locator("a[jsname='YKoRaf'], a.WlydOe, a h3").all()
                valid_links = []
                
                for link in all_article_links:
                    try:
                        if link.is_visible(timeout=500):
                            href = link.get_attribute("href")
                            if href and href not in read_urls:
                                valid_links.append((link, href))
                    except:
                        continue
                
                if valid_links:
                    # Bốc ngẫu nhiên một bài chưa đọc
                    target_data = random.choice(valid_links[:8]) # Chọn trong 8 bài hợp lệ đầu tiên
                    target_article = target_data[0]
                    target_href = target_data[1]
                    read_urls.add(target_href)
                    
                    self._smooth_scroll_to_element(active_page, target_article)
                    self.random_sleep(1, 2)
                    
                    print("      + Đã chốt mục tiêu bài báo. Đang click...")
                    
                    # 3. Xử lý logic Click mở báo (Cùng tab hoặc Tab mới)
                    try:
                        with active_page.context.expect_page(timeout=5000) as new_page_info:
                            self.human_click(active_page, target_article)
                        
                        # Nếu code chạy đến đây nghĩa là bài báo mở ra TAB MỚI
                        active_page = new_page_info.value 
                        print("      + Bài báo được mở ở Tab mới.")
                        active_page.wait_for_load_state("domcontentloaded")
                        
                        # Tiêm chuột ảo vào tab mới
                        self.enable_virtual_cursor(active_page)
                        
                    except Exception:
                        # Nếu Timeout xảy ra, nghĩa là bài báo mở TRONG CÙNG TAB.
                        print("      + Bài báo load thẳng trên cùng Tab hiện tại.")
                        active_page.wait_for_load_state("domcontentloaded")
                    
                    self.random_sleep(3, 6)
                    self.restore_mouse_position(active_page)
                    
                    # 4. Hành vi đọc báo
                    scroll_steps = random.randint(5, 9)
                    print(f"      + Đang lướt đọc nội dung bài báo {scroll_steps} nhịp...")
                    
                    for _ in range(scroll_steps):
                        if random.random() < 0.3:
                            self.move_mouse_viewport_center(active_page)
                        
                        # 80% cuộn xuống, 20% cuộn lên xem lại
                        if random.random() < 0.8:
                            self.smooth_scroll(active_page, random.randint(400, 800))
                        else:
                            self.smooth_scroll(active_page, -random.randint(200, 400))
                        self.random_sleep(8, 16)
                        
                    print(f"      + Đã đọc xong bài {article_index + 1}.")
                    
                    # 5. Dọn dẹp để chuẩn bị cho vòng lặp tiếp theo
                    if active_page != page:
                        print("      + Đang đóng tab báo vừa đọc, quay lại trang Google News...")
                        active_page.close()
                        active_page = page # Trả quyền điều khiển về tab Google gốc
                        active_page.bring_to_front()
                    else:
                        print("      + Đang Back lại trang kết quả Google News...")
                        try:
                            # Dùng "commit" thay vì "domcontentloaded" để tránh kẹt loading
                            active_page.go_back(wait_until="commit", timeout=15000)
                            # Đợi thêm một chút để trang định hình, nếu lỗi thì bỏ qua
                            active_page.wait_for_load_state("domcontentloaded", timeout=10000)
                        except Exception as back_err:
                            print(f"      [!] Trang Google kẹt khi Back, đang ép tải lại (Reload)...")
                            try:
                                active_page.reload(timeout=15000)
                            except:
                                pass
                    
                    self.random_sleep(3, 5)
                    self.restore_mouse_position(active_page)
                        
                else:
                    print("      [-] Không tìm thấy bài báo nào mới trên màn hình, sẽ cuộn tiếp ở nhịp sau.")
                    
            print(f"  -> [Action] HOÀN TẤT ĐỌC BÁO! (Đã xử lý {num_articles_to_read} bài).")
                
        except Exception as e:
            print(f"      + Lỗi trong quá trình tìm và đọc báo: {e}")

    def move_mouse_bezier(self, page, target_element):
        """Di chuyển chuột đến phần tử theo quỹ đạo cong Bezier, xuất phát từ vị trí chuột cũ (nếu có)"""
        # v1.4.3: bounding_box() trên element detached/0 khớp sẽ TREO 30s rồi raise
        # TimeoutError. Dùng _safe_bbox() (is_visible() tức thời + timeout 1.5s).
        box = self._safe_bbox(target_element, timeout=2000)
        if not box:
            return False
            
        # Chọn 1 điểm ngẫu nhiên BÊN TRONG phần tử đích
        end_x = box['x'] + random.uniform(2, box['width'] - 2)
        end_y = box['y'] + random.uniform(2, box['height'] - 2)
        
        # 1. LẤY TỌA ĐỘ CUỐI CÙNG HOẶC FALLBACK VỀ MẶC ĐỊNH
        if hasattr(page.mouse, '_last_x') and hasattr(page.mouse, '_last_y'):
            start_x = page.mouse._last_x
            start_y = page.mouse._last_y
        else:
            viewport = page.viewport_size
            if viewport:
                start_x = random.uniform(0, viewport['width'])
                start_y = random.uniform(0, viewport['height'])
            else:
                start_x, start_y = (400, 300)
            
        # Sinh quỹ đạo gồm 20-40 bước
        steps = random.randint(20, 40)
        path = self._generate_bezier_path((start_x, start_y), (end_x, end_y), steps)
        
        # Bắt đầu di chuyển chuột theo từng điểm trên quỹ đạo
        for point in path:
            page.mouse.move(point[0], point[1])
            time.sleep(random.uniform(0.005, 0.02))
            
        # 2. CẬP NHẬT LẠI TỌA ĐỘ MỚI SAU KHI DI CHUYỂN XONG
        page.mouse._last_x = end_x
        page.mouse._last_y = end_y
            
        return True               

    def move_mouse_viewport_center(self, page):
        """Di chuyển chuột mượt mà (Bezier) từ vị trí cũ đến một điểm ngẫu nhiên an toàn trên màn hình"""
        try:
            viewport = page.viewport_size
            if viewport:
                end_x = random.uniform(viewport['width'] * 0.3, viewport['width'] * 0.7)
                end_y = random.uniform(viewport['height'] * 0.3, viewport['height'] * 0.7)
                
                # Nếu đã có tọa độ cũ, dùng đường cong Bezier để nối mượt mà như người thật
                if hasattr(page.mouse, '_last_x') and hasattr(page.mouse, '_last_y'):
                    start_x = page.mouse._last_x
                    start_y = page.mouse._last_y
                    
                    steps = random.randint(15, 30)
                    path = self._generate_bezier_path((start_x, start_y), (end_x, end_y), steps)
                    
                    for point in path:
                        page.mouse.move(point[0], point[1])
                        time.sleep(random.uniform(0.005, 0.02))
                else:
                    # Nếu là lần đầu tiên chuột xuất hiện trên trang, bay thẳng vào rồi ghi nhận
                    page.mouse.move(end_x, end_y)
                
                # Lưu lại vị trí cuối cùng cho hành động tiếp theo
                page.mouse._last_x = end_x
                page.mouse._last_y = end_y
                
                time.sleep(random.uniform(0.2, 0.4))
        except Exception as e:
            print(f"      [-] Không thể di chuyển chuột vào viewport: {e}")

    def human_hover(self, page, element):
        """Đưa chuột vào phần tử bằng quỹ đạo Bezier và tạo độ rung tay tự nhiên, lưu lại tọa độ để không nhảy cóc"""
        # v1.4.3: phần tử detached/không tồn tại -> thoát ngay, tránh bounding_box() treo 30s
        if not self._safe_bbox(element, timeout=2000):
            return False

        # 1. Di chuyển chuột lượn vòng tới mục tiêu bằng Bezier
        self.move_mouse_bezier(page, element)
        
        # 2. Xê dịch chuột nhè nhẹ (jitter) tại chỗ để giả lập tay người đang giữ chuột
        box = self._safe_bbox(element, timeout=2000)
        if box:
            current_x = box['x'] + box['width'] / 2
            current_y = box['y'] + box['height'] / 2
            
            # Rung nhẹ 2-4 nhịp, mỗi nhịp xê dịch vài pixel.
            # v1.5.1: biên độ 10px -> 3px và rê DẦN từng bước nhỏ (không nhảy cóc).
            # Trước đây mỗi nhịp là MỘT page.mouse.move() tức thì nhảy tới 14px chéo,
            # trên thẻ <video> chiếm cả màn hình -> nhìn như con trỏ "giật cục cục".
            for _ in range(random.randint(2, 4)):
                target_x = current_x + random.uniform(-3, 3)
                target_y = current_y + random.uniform(-3, 3)
                last_x = getattr(page.mouse, "_last_x", current_x) or current_x
                last_y = getattr(page.mouse, "_last_y", current_y) or current_y

                # Đi 3-5 bước nội suy giữa 2 điểm rung, mỗi bước 12-40ms
                sub = random.randint(3, 5)
                for s in range(1, sub + 1):
                    ratio = s / sub
                    page.mouse.move(last_x + (target_x - last_x) * ratio,
                                    last_y + (target_y - last_y) * ratio)
                    time.sleep(random.uniform(0.012, 0.04))

                # CẬP NHẬT TỌA ĐỘ VÀO BỘ NHỚ LƯU TRỮ CHUỘT ẢO
                page.mouse._last_x = target_x
                page.mouse._last_y = target_y

                time.sleep(random.uniform(0.25, 0.7))
    
    def human_click(self, page, element):
        """Click chuẩn người thật: Tự động dùng Bezier xuất phát từ vị trí cũ -> Bấm -> Nhả"""
        # 1. Di chuyển chuột lượn vòng tới mục tiêu (tự động nối tiếp từ tọa độ cũ)
        self.move_mouse_bezier(page, element)
        
        # 2. Ngập ngừng 1 nhịp ngắn trước khi bấm
        self.random_sleep(0.1, 0.3)
        
        # 3. Giả lập bấm chuột vật lý tại vị trí hiện tại của con trỏ
        page.mouse.down()
        time.sleep(random.uniform(0.05, 0.15))
        page.mouse.up()

    def smooth_scroll(self, page, distance):
            """
            Chia nhỏ quãng đường cuộn để giả lập từng khấc lăn chuột của người thật.
            """
            # Chia quãng đường thành 8 đến 15 bước nhỏ (tương đương 8-15 khấc lăn chuột)
            steps = random.randint(8, 15)
            step_distance = distance / steps
            
            for _ in range(steps):
                page.mouse.wheel(0, step_distance)
                # Nghỉ vài chục mili-giây giữa mỗi khấc lăn, giống hệt ngón tay người
                time.sleep(random.uniform(0.02, 0.08))

    def _human_scroll(self, page, distance, settle=True):
        """v1.5.1: cuộn KIỂU CỔ TAY người cho feed có scroll-snap (TikTok).

        Vì sao không dùng smooth_scroll ở đây: smooth_scroll đi 8-15 khấc với nhịp
        nghỉ 0.02-0.08s -> cả 1 viewport (~950-1100px) lướt xong trong 0.2-1.2s.
        TikTok scroll-snap chưa kịp bám theo đã bị kéo tiếp, rồi "cập" vào ô video
        -> mắt người thấy thành một cú GIẬT. Helper này vê CHẬM hơn hẳn và nhịp nghỉ
        hình sin (dài ở đầu/cuối, ngắn ở giữa) giống hệt cú đẩy cổ tay thật, rồi
        dừng 1 nhịp cho snap ổn định trước khi trả quyền điều khiển.
        """
        steps = random.randint(18, 30)
        step_distance = distance / steps

        for i in range(steps):
            page.mouse.wheel(0, step_distance)
            # 0.0 = vừa bắt đầu đẩy (chậm), 0.5 = giữa cú vuốt (nhanh nhất),
            # 1.0 = sắp tới đích (khựng lại) -> không còn "vút một cái"
            t = i / max(1, steps - 1)
            ease = 0.35 + 0.65 * (abs(t - 0.5) * 2) ** 1.5
            time.sleep(random.uniform(0.08, 0.18) * ease + 0.03)

        if settle:
            # Cho scroll-snap chạy xong + mắt người "đọc" xong khung hình mới
            time.sleep(random.uniform(0.5, 1.1))

    def action_google_finance(self, page):
        """Hành động: Truy cập trực tiếp Google Finance tìm kiếm mã cổ phiếu, tiền ảo, vàng"""
        print("  -> [Action] Truy cập Google Finance tra cứu thị trường...")
        try:
            # 1. Truy cập trang chủ Google Finance
            # v1.4.6: đích là CHÍNH Google — goto thẳng là hợp lệ (không phải
            # bỏ cổng Google; cổng Google chỉ cho site thứ ba như TikTok/Wiki/báo).
            print("      + [Cổng Google] Đích là chính Google (Finance) — vào thẳng, không cần gõ Search.")
            page.goto("https://www.google.com/finance/", wait_until="domcontentloaded", timeout=45000)
            self.random_sleep(3, 5)
            self.restore_mouse_position(page)
            
            # Lướt nhẹ trang chủ xem tổng quan thị trường (chỉ số Dow Jones, S&P 500...)
            print("      + Đang lướt xem bảng tổng quan thị trường...")
            for _ in range(random.randint(4, 7)):
                self.move_mouse_viewport_center(page)
                self.human_hover(page, page.locator("div[data-earnings-banner-count='0']"))
                self.smooth_scroll(page, random.randint(300, 500))
                self.random_sleep(2, 4)

            # 2. Tìm ô tìm kiếm giả (div) và click để mở Overlay
            print("      + Đang tìm ô Search trên giao diện Google Finance...")
            try:
                search_box_dummy = page.locator("div[role='button'][aria-label*='Search for stocks'] div div div, div[role='button'][aria-label*='Tìm'] div div div").first
                if not search_box_dummy.is_visible(timeout=3000):
                    search_box_dummy = page.locator("div[aria-label*='Tìm'], div[aria-label*='Search']").first
            except:
                search_box_dummy = page.locator("input[type='text']").first
            
            symbols = ["BTC-USD", "ETH-USD", "AAPL", "TSLA", "NVDA", "GCW00", "VNINDEX"]
            query = random.choice(symbols)
            
            print("      + Đang click vào ô search để mở bảng nhập mã...")
            self.human_click(page, search_box_dummy)
            
            # [QUAN TRỌNG] Chờ 1.5 - 2.5 giây để bảng Overlay mở ra và TỰ ĐỘNG FOCUS con trỏ nhấp nháy
            self.random_sleep(1.5, 2.5)
            
            print(f"      + Bảng gõ chữ đã mở. Đang gõ phím trực tiếp từ bàn phím: '{query}'...")
            
            # GÕ PHÍM TOÀN CỤC (Không cần truyền locator)
            for char in query:
                if char == " ":
                    page.keyboard.press("Space")
                else:
                    page.keyboard.type(char)
                
                # Độ trễ ngẫu nhiên giống người thật đang gõ
                time.sleep(random.uniform(0.08, 0.25))
            
            self.random_sleep(1, 2)
            
            # Nhấn Enter để xem biểu đồ chi tiết
            page.keyboard.press("Enter")
            self.random_sleep(3, 5)
            self.restore_mouse_position(page)

            # 3. Hành vi lăn chuột ngắm biểu đồ và các chỉ số P/E, Market Cap...
            self.human_hover(page, page.locator("div[data-earnings-banner-count='0']"))
            scroll_steps = random.randint(4, 7)
            for _ in range(scroll_steps):
                if random.random() < 0.4:
                    self.move_mouse_viewport_center(page)
                
                # 80% cuộn xuống, 20% cuộn lên xem lại đỉnh/đáy biểu đồ
                if random.random() < 0.8:
                    self.smooth_scroll(page, random.randint(300, 600))
                else:
                    self.smooth_scroll(page, -random.randint(200, 400))
                    
                self.random_sleep(3, 6)

            # 4. (Tùy chọn) Mở một bài báo tài chính liên quan đến mã vừa tìm
            if random.random() < 0.6:
                try:
                    # Bắt thẻ chứa bài viết báo chí trên Google Finance
                    news_links = page.locator("a[href*='/articles/'], a:has(div[role='heading'])").all()
                    if news_links:
                        # Chỉ lọc các bài tin tức đang nằm trong tầm nhìn
                        viewport = page.viewport_size
                        vh = viewport['height'] if viewport else 800
                        visible_news = []
                        for n in news_links:
                            nb = self._safe_bbox(n)
                            if nb and 0 < nb['y'] < vh:
                                visible_news.append(n)
                        
                        if visible_news:
                            target_news = random.choice(visible_news[:3])
                            print("      + Đang click mở một bài báo tài chính liên quan...")
                            self.human_click(page, target_news)
                            
                            page.wait_for_load_state("domcontentloaded", timeout=30000)
                            self.random_sleep(3, 5)
                            self.restore_mouse_position(page)
                            
                            print("      + Đang lướt đọc bài báo...")
                            for _ in range(random.randint(3, 6)):
                                self.smooth_scroll(page, random.randint(300, 600))
                                self.random_sleep(3, 5)
                                
                            print("      + Đọc xong, back lại Google Finance...")
                            page.go_back(wait_until="domcontentloaded")
                            self.restore_mouse_position(page)
                except Exception as e:
                    print(f"      + Bỏ qua đọc tin tức tài chính: {e}")

            print("      + Hoàn tất phiên lướt Google Finance.")

        except Exception as e:
            print(f"      + Lỗi khi tra cứu Google Finance: {e}")

    def action_search_youtube(self, page):
            """Hành động mới: Tìm kiếm YouTube theo chủ đề AI chọn"""
            print("  -> [Action] Tìm kiếm và xem trên YouTube...")
            
            # [CẬP NHẬT LẤY TỪ KHÓA TỪ AI THEME]
            keyword = self.session_theme.get("youtube_query", "tin tức mới nhất")
            
            try:
                page.goto("https://www.youtube.com", wait_until="domcontentloaded", timeout=45000)
                self.random_sleep(2, 4)
    
                # Gõ từ khóa vào ô tìm kiếm NHƯ NGƯỜI THẬT (human_type: WPM Gauss, typo/backspace) rồi Enter
                search_box = page.locator("input[name='search_query']")
                search_box.wait_for(state="visible", timeout=15000)
                self.human_type(search_box, keyword)
                self.random_sleep(1, 2)
                page.keyboard.press("Enter")
                page.wait_for_load_state("domcontentloaded", timeout=30000)
                
                print(f"      + Đã tìm kiếm: '{keyword}'. Đang lướt đọc các kết quả...")
                self.random_sleep(3, 5)
    
                # Cuộn xuống lướt qua kết quả vài giây giống người thật đang tìm video ưng ý
                scroll_time = random.randint(6, 12)
                end_time = time.time() + scroll_time
                while time.time() < end_time:
                    self.smooth_scroll(page, random.randint(300, 700))
                    self.random_sleep(2, 4)
                    
                # Cuộn ngược lên một chút (hành vi rất phổ biến khi chọn video)
                if random.random() < 0.5:
                    self.smooth_scroll(page, -random.randint(400, 800))
                    self.random_sleep(2, 4)
                    
                # Đếm và lấy các video từ danh sách kết quả tìm kiếm
                videos = page.locator("ytd-video-renderer a#video-title").all()
                if videos:
                    # Chọn ngẫu nhiên trong 4 video đầu tiên
                    choice_index = random.randint(0, min(len(videos) - 1, 3)) 
                    target_video = videos[choice_index]
                    print(f"      + Quyết định chọn video thứ {choice_index + 1} trong danh sách.")
                    
                    # --- GIẢ LẬP LƯỚT CHẬM TỚI VIDEO MỤC TIÊU ---
                    target_video.scroll_into_view_if_needed(timeout=3000)
                    print("      + Đang dừng lại đọc kỹ tiêu đề trước khi click...")
                    self.random_sleep(2, 5) # Chờ ngắm nghía
                    # ---------------------------------------------
                    
                    self.human_click(page, target_video)
                    
                    # GỌI HÀM LOGIC XỬ LÝ VIDEO (Bao gồm % xem, Like, Sub, Suggested)
                    total_videos_to_watch = random.randint(2, 3)
                    print(f"  -> [Action] Bắt đầu chuỗi xem YouTube tìm kiếm: {total_videos_to_watch} video.")
                    self._watch_single_video_logic(page, videos_remaining_to_watch=total_videos_to_watch)
                    
                else:
                    print("      + Không tìm thấy video nào trong trang kết quả tìm kiếm.")
                    
            except Exception as e:
                print(f"      + Lỗi quá trình tìm kiếm YouTube. Lỗi: {e}")

    def human_type(self, locator, text):
        """Gõ phím mô phỏng người thật.
        - WPM phân phối chuẩn quanh base_wpm per-profile (gauss, sigma=8, clamp 40-85)
        - Typo rate tuyến tính theo WPM (nhanh = nhiều lỗi hơn)
        - Cognitive hesitation trước khi gõ, tỷ lệ nghịch với độ dài text
        - Backspace 1-2-3 ký tự theo trọng số thực tế (70/25/5)
        - End-of-word slowdown (cognitive boundary effect)
        - Burst/slow xen kẽ theo phân phối 20/8/72
        - Thread-safe: dùng self.rng thay vì random global
        """
        try:
            page = locator.page
            rng = self.rng
            locator.click()

            # --- Cognitive Preparation Time ---
            # Text ngắn → hesitate lâu hơn (đang nghĩ), text dài → gõ gần như ngay
            hesitation_base = max(0.5, min(2.0, 2.5 - len(text) * 0.06))
            self.random_sleep(hesitation_base * 0.8, hesitation_base * 1.3)

            print(f"      + Đang nhập từ khóa: '{text}'...")

            # --- Sinh WPM cho lần gõ này ---
            # Gauss quanh base_wpm, sigma=8, clamp [40, 85]
            wpm = max(40, min(85, rng.gauss(mu=self.base_wpm, sigma=8)))
            chars_per_sec = (wpm * 5) / 60.0
            base_delay = 1.0 / chars_per_sec if chars_per_sec > 0 else 0.15

            # --- Typo chance tuyến tính theo WPM ---
            # 40 WPM → ~0.5%, 85 WPM → ~3.2%
            typo_chance = 0.005 + (wpm - 40) * 0.0006

            i = 0
            while i < len(text):
                char = text[i]

                # ==========================================
                # XỬ LÝ TYPO + BACKSPACE CỤM
                # ==========================================
                if rng.random() < typo_chance and char.isalpha():
                    neighbors = self._get_keyboard_neighbors(char)
                    if neighbors:
                        wrong_char = rng.choice(neighbors)
                        if char.isupper():
                            wrong_char = wrong_char.upper()

                        # Gõ nhầm
                        page.keyboard.type(wrong_char)
                        time.sleep(base_delay * rng.uniform(0.5, 1.0))

                        # Quyết định backspace bao nhiêu ký tự
                        bs_count = rng.choices([1, 2, 3], weights=[0.70, 0.25, 0.05])[0]
                        # Không xóa quá số ký tự đã gõ
                        bs_count = min(bs_count, i + 1)

                        for _ in range(bs_count):
                            page.keyboard.press("Backspace")
                            time.sleep(rng.uniform(0.06, 0.15))

                        # Dừng suy nghĩ lại sau khi xóa
                        self.random_sleep(0.15, 0.45)

                        # Nếu xóa > 1, gõ lại các ký tự đúng bị xóa mất + ký tự hiện tại
                        if bs_count > 1:
                            retype_start = max(0, i - bs_count + 1)
                            for ri in range(retype_start, i + 1):
                                rc = text[ri]
                                page.keyboard.type(rc)
                                time.sleep(base_delay * rng.uniform(0.6, 1.2))
                        else:
                            # Xóa 1 → gõ lại đúng ký tự hiện tại
                            page.keyboard.type(char)
                            time.sleep(base_delay * rng.uniform(0.7, 1.3))

                        i += 1
                        continue

                # ==========================================
                # GÕ KÝ TỰ BÌNH THƯỜNG (KHÔNG TYPO)
                # ==========================================
                if char == " ":
                    page.keyboard.press("Space")
                    delay = base_delay * rng.uniform(1.0, 1.8)
                elif char in ".,;:!?":
                    page.keyboard.type(char)
                    delay = base_delay * rng.uniform(2.5, 5.0)
                else:
                    page.keyboard.type(char)

                    # Burst / Slow / Normal pattern
                    roll = rng.random()
                    if roll < 0.20:
                        delay = base_delay * rng.uniform(0.3, 0.6)     # burst nhanh
                    elif roll < 0.28:
                        delay = base_delay * rng.uniform(2.5, 5.0)     # khựng suy nghĩ
                    else:
                        delay = base_delay * rng.uniform(0.7, 1.4)     # bình thường

                # --- End-of-word slowdown ---
                # Ký tự trước space chậm lại 20-60% (cognitive boundary)
                if i + 1 < len(text) and text[i + 1] == ' ':
                    delay *= rng.uniform(1.2, 1.6)

                time.sleep(delay)
                i += 1

            print("      + Nhập từ khóa hoàn tất.")
            self.random_sleep(0.6, 1.2)

        except Exception as e:
            print(f"      [-] Lỗi khi gõ phím mô phỏng: {e}")
            try:
                locator.press_sequentially(text, delay=int(self.rng.uniform(80, 160)))
            except Exception:
                pass

    def _get_keyboard_neighbors(self, char):
        """Trả về danh sách ký tự nằm cạnh trên bàn phím QWERTY để giả lập typo."""
        keyboard_map = {
            'q': ['w', 'a'], 'w': ['q', 'e', 'a', 's'], 'e': ['w', 'r', 's', 'd'],
            'r': ['e', 't', 'd', 'f'], 't': ['r', 'y', 'f', 'g'], 'y': ['t', 'u', 'g', 'h'],
            'u': ['y', 'i', 'h', 'j'], 'i': ['u', 'o', 'j', 'k'], 'o': ['i', 'p', 'k', 'l'],
            'p': ['o', 'l'], 'a': ['q', 'w', 's', 'z'], 's': ['a', 'w', 'e', 'd', 'z', 'x'],
            'd': ['s', 'e', 'r', 'f', 'x', 'c'], 'f': ['d', 'r', 't', 'g', 'c', 'v'],
            'g': ['f', 't', 'y', 'h', 'v', 'b'], 'h': ['g', 'y', 'u', 'j', 'b', 'n'],
            'j': ['h', 'u', 'i', 'k', 'n', 'm'], 'k': ['j', 'i', 'o', 'l', 'm'],
            'l': ['k', 'o', 'p'], 'z': ['a', 's', 'x'], 'x': ['z', 's', 'd', 'c'],
            'c': ['x', 'd', 'f', 'v'], 'v': ['c', 'f', 'g', 'b'], 'b': ['v', 'g', 'h', 'n'],
            'n': ['b', 'h', 'j', 'm'], 'm': ['n', 'j', 'k'],
        }
        lower = char.lower()
        neighbors = keyboard_map.get(lower, [])
        # Giữ nguyên case của ký tự gốc
        if char.isupper():
            return [n.upper() for n in neighbors]
        return neighbors

    def action_interact_reddit(self, page):
        """Kịch bản Reddit (Bản Hoàn Thiện): Xử lý nhiều bài, cuộn Lên/Xuống tự nhiên, Fix lỗi Locator"""
        print("  -> [Action] Bắt đầu phiên Reddit: Lướt Feed và tương tác nhiều bài viết...")
        try:
            # --- FIX LỖI INTERRUPTED NAVIGATION BỊ KẸT Ở TRANG TRƯỚC ---
            try:
                page.goto("https://www.reddit.com/", wait_until="domcontentloaded", timeout=60000)
            except Exception as goto_err:
                if "interrupted" in str(goto_err).lower():
                    print("      [!] Quá trình chuyển hướng bị kẹt từ trang trước. Đang ép dừng và tải lại Reddit...")
                    try:
                        page.evaluate("window.stop()")
                    except:
                        pass
                    self.random_sleep(2, 4)
                    page.goto("https://www.reddit.com/", wait_until="domcontentloaded", timeout=60000)
                else:
                    raise goto_err
            # -----------------------------------------------------------

            self.random_sleep(3, 6)

            self.move_mouse_viewport_center(page)
            self.random_sleep(0.5, 1)

            num_posts_to_interact = random.randint(2, 4)
            print(f"      + Kế hoạch phiên này: Tương tác lần lượt với {num_posts_to_interact} bài viết.")
            
            read_urls = set()

            for post_index in range(num_posts_to_interact):
                print(f"\n      + [Reddit] Đang tìm và xử lý bài viết thứ {post_index + 1}/{num_posts_to_interact}...")
                
                # 1. Lướt Feed (Kết hợp Cuộn Xuống và Cuộn Lên)
                scroll_steps = random.randint(5, 8) 
                print(f"      + Đang lướt Feed ngẫu nhiên {scroll_steps} nhịp...")
                for _ in range(scroll_steps):
                    if random.random() < 0.3:
                        self.move_mouse_viewport_center(page)
                    
                    # 80% cuộn xuống, 20% cuộn lên
                    if random.random() < 0.8:
                        self.smooth_scroll(page, random.randint(600, 1000))
                    else:
                        self.smooth_scroll(page, -random.randint(300, 600))
                    self.random_sleep(2, 4)
                    
                # 2. Bắt và lọc bài viết
                all_posts = page.locator('a[slot="title"]').all()
                on_screen_posts = []
                viewport = page.viewport_size
                vh = viewport['height'] if viewport else 800
                
                for post in all_posts:
                    try:
                        if post.is_visible(timeout=500):
                            href = post.get_attribute("href")
                            if href and href in read_urls:
                                continue
                                
                            box = self._safe_bbox(post)
                            if box and -150 <= box['y'] <= vh:
                                on_screen_posts.append((post, href))
                    except:
                        continue
                
                if on_screen_posts:
                    target_post_data = random.choice(on_screen_posts)
                    target_post = target_post_data[0]
                    target_href = target_post_data[1]
                    
                    if target_href:
                        read_urls.add(target_href)
                    
                    # 3. FIX LỖI LOCATOR: Tự tính toán khoảng cách để cuộn bài viết ra giữa màn hình
                    box = self._safe_bbox(target_post)
                    if box and viewport:
                        scroll_amount = int(box['y'] - (viewport['height'] / 3))
                        if scroll_amount != 0:
                            self.smooth_scroll(page, scroll_amount)
                            self.random_sleep(1, 2)
                    
                    # 4. Quyết định Upvote ngoài Feed
                    if random.random() < 0.6: 
                        print("      + Quyết định: Thả Upvote bài viết ngay ngoài Feed trước khi xem.")
                        try:
                            post_container = target_post.locator("xpath=ancestor::shreddit-post").first
                            if post_container.is_visible():
                                feed_upvote = post_container.locator("button[data-action-bar-action='upvote'], button[aria-label^='Upvote'], shreddit-vote-animations button[upvote]").first
                                
                                if feed_upvote.is_visible():
                                    btn_box = self._safe_bbox(feed_upvote)
                                    if btn_box and viewport:
                                        if btn_box['y'] > (viewport['height'] - 80):
                                            print("      + Nút Upvote đang bị khuất dưới hình, đang cuộn nhẹ xuống...")
                                            scroll_down = int(btn_box['y'] - (viewport['height'] / 1.5))
                                            self.smooth_scroll(page, scroll_down)
                                            self.random_sleep(1, 2)
                                            
                                    self.human_click(page, feed_upvote)
                                    self.random_sleep(1.5, 3)
                        except Exception as e:
                            print(f"      + Bỏ qua upvote trên feed do lỗi cấu trúc DOM: {e}")

                    print("      + Đã khóa mục tiêu. Đang rê chuột click mở bài viết...")
                    
                    title_box = self._safe_bbox(target_post)
                    if title_box and viewport:
                        if title_box['y'] < 50 or title_box['y'] > (viewport['height'] - 50):
                            scroll_back = int(title_box['y'] - (viewport['height'] / 3))
                            self.smooth_scroll(page, scroll_back)
                            self.random_sleep(1, 2)
                            
                    self.human_click(page, target_post)
                    
                    # 5. Đọc nội dung bài
                    for _ in range(random.randint(2, 4)):
                        if random.random() < 0.8:
                            self.smooth_scroll(page, random.randint(300, 600))
                        else:
                            self.smooth_scroll(page, -random.randint(200, 400))
                        self.random_sleep(3, 5)
                    
                    # 6. Cuộn đọc bình luận
                    print("      + Đang cuộn sâu xuống phần Thread bình luận...")
                    for _ in range(random.randint(3, 6)):
                        if random.random() < 0.8:
                            self.smooth_scroll(page, random.randint(400, 800))
                        else:
                            self.smooth_scroll(page, -random.randint(300, 500))
                        self.random_sleep(3, 5)
                    
                    # 7. Upvote bình luận
                    all_upvotes = page.locator("button[upvote], shreddit-vote-animations button[upvote], button[aria-label^='Upvote']").all()
                    on_screen_upvotes = []
                    
                    for btn in all_upvotes:
                        try:
                            if btn.is_visible(timeout=500):
                                box = self._safe_bbox(btn)
                                if box and 50 < box['y'] < vh - 50:
                                    on_screen_upvotes.append(btn)
                        except:
                            continue
                    
                    if on_screen_upvotes:
                        num_to_upvote = random.randint(1, min(2, len(on_screen_upvotes)))
                        print(f"      + Có {len(on_screen_upvotes)} bình luận trong tầm nhìn. Quyết định Upvote {num_to_upvote} cái.")
                        
                        chosen_comments = random.sample(on_screen_upvotes, num_to_upvote)
                        for idx, comment_upvote in enumerate(chosen_comments):
                            print(f"      + Đang rê chuột thả Upvote cho bình luận thứ {idx + 1}...")
                            self.human_click(page, comment_upvote)
                            self.random_sleep(2, 4)
                    else:
                        print("      + [Bỏ qua] Không có bình luận nào hiển thị rõ trên màn hình.")
                    
                    # 8. Thoát ra Feed
                    print(f"      + Xong bài thứ {post_index + 1}. Đang Back lại Feed...")
                    page.go_back(wait_until="domcontentloaded")
                    self.random_sleep(5, 8)
                    
                    self.restore_mouse_position(page)
                    self.random_sleep(1, 2)
                    
                else:
                    print("      [-] Màn hình hiện tại không bắt được bài nào mới. Sẽ thử lướt thêm ở vòng lặp tiếp.")

            print(f"  -> [Action] HOÀN TẤT PHIÊN REDDIT! (Đã xử lý xong {num_posts_to_interact} bài).")

        except Exception as e:
            print(f"      + Lỗi khi tương tác Reddit: {e}")

    def action_search_weather(self, page):
        """Hành động: Tìm kiếm thời tiết Google (Random 50% gõ trên URL, 50% gõ ở ô Search)"""
        print("  -> [Action] Tra cứu thời tiết Google theo khu vực IP...")
        try:
            import urllib.parse
            
            # Chọn từ khóa tự nhiên giống người dùng đang hỏi
            query = random.choice(["thời tiết hôm nay thế nào", "dự báo thời tiết", "weather today", "nhiệt độ ngoài trời"])
            
            # Quay xổ số quyết định hành vi tìm kiếm (50/50)
            if random.random() < 0.5:
                # CÁCH 1: Giả lập gõ thẳng từ khóa lên thanh URL (Omnibox)
                print(f"      + Quyết định: Gõ trực tiếp lên thanh địa chỉ URL từ khóa '{query}' (đích là chính Google — hợp lệ, không cần cổng).")
                # Xử lý khoảng trắng và dấu tiếng Việt thành định dạng URL chuẩn (vd: thời+tiết)
                encoded_query = urllib.parse.quote_plus(query)
                page.goto(f"https://www.google.com/search?q={encoded_query}", wait_until="domcontentloaded", timeout=45000)
                self.random_sleep(2, 4)
                
            else:
                # CÁCH 2: Vào trang chủ Google.com rồi click tìm kiếm thủ công
                print("      + Quyết định: Vào trang chủ Google rồi rê chuột gõ phím.")
                page.goto("https://www.google.com", wait_until="domcontentloaded", timeout=45000)
                self.random_sleep(2, 4)

                # Đưa chuột vào vùng an toàn trước khi gõ
                self.move_mouse_viewport_center(page)
                self.random_sleep(0.5, 1)
                self.human_click(page, page.locator("textarea[name='q'], input[name='q']").first)
                search_box = page.locator("textarea[name='q'], input[name='q']").first
                print(f"      + Đang nhập từ khóa: '{query}'...")
                
                # Gọi hàm gõ chậm từng chữ kết hợp Bezier
                self.human_type(search_box, query)
                self.random_sleep(0.5, 1)
                page.keyboard.press("Enter")
                page.wait_for_load_state("domcontentloaded", timeout=30000)
            
            print("      + Đã tải xong kết quả thời tiết. Đang dừng lại xem thông tin...")
            self.random_sleep(3, 5)

            # Đưa chuột vào màn hình (nếu dùng cách 1 thì nãy giờ chuột chưa xuất hiện)
            self.move_mouse_viewport_center(page)
            
            # Cuộn lướt nhẹ qua lại các thẻ dự báo thời tiết Google
            scroll_steps = random.randint(4, 10)
            print(f"      + Đang lướt đọc kết quả thời tiết và tin tức xung quanh {scroll_steps} nhịp...")
            
            for _ in range(scroll_steps):
                if random.random() < 0.4:
                    self.move_mouse_viewport_center(page)
                
                # 80% cuộn xuống, 20% cuộn ngược lên một chút để tránh bị trôi tuột xuống đáy quá nhanh
                if random.random() < 0.8:
                    self.smooth_scroll(page, random.randint(200, 500))
                else:
                    self.smooth_scroll(page, -random.randint(150, 400))
                    
                self.random_sleep(5, 6)

            # Random click vào một ngày trong tuần để xem chi tiết
            if random.random() < 0.8:
                try:
                    weather_cards = page.locator("div[jsname='w75vcd'] div, div.wob_df").all()
                    if weather_cards:
                        target_card = random.choice(weather_cards[:5])
                        if target_card.is_visible():
                            print("      + Đang rê chuột click xem chi tiết dự báo của một ngày...")
                            self.human_click(page, target_card) # Đã bao gồm move_mouse_bezier bên trong
                            self.random_sleep(3, 5)
                except Exception as e:
                    print(f"      + Bỏ qua xem chi tiết ngày: {e}")

            print("      + Hoàn tất tra cứu thời tiết.")

        except Exception as e:
            print(f"      + Lỗi khi tra cứu thời tiết Google: {e}")

    def enable_virtual_cursor(self, page):
        """Tiêm script tạo chấm tròn đỏ theo dõi tọa độ chuột (Hoạt động xuyên suốt các trang)"""
        cursor_script = """
            // Đảm bảo chỉ tạo 1 cursor duy nhất trên trang
            if (!document.getElementById('playwright-virtual-cursor')) {
                const cursor = document.createElement('div');
                cursor.id = 'playwright-virtual-cursor';
                cursor.style.width = '20px';
                cursor.style.height = '20px';
                cursor.style.borderRadius = '50%';
                cursor.style.backgroundColor = 'rgba(220, 20, 60, 0.7)'; // Đỏ mờ
                cursor.style.boxShadow = '0 0 5px rgba(0,0,0,0.3)';
                cursor.style.position = 'fixed';
                cursor.style.pointerEvents = 'none'; // Xuyên thấu, không cản trở click
                cursor.style.zIndex = '2147483647'; // Nổi lên trên cùng mọi lớp CSS
                cursor.style.transform = 'translate(-50%, -50%)';
                cursor.style.transition = 'transform 0.1s ease-out, background-color 0.1s';
                
                // Hàm chèn cursor vào body khi body đã xuất hiện
                const initCursor = () => {
                    if (document.body) {
                        document.body.appendChild(cursor);
                    } else {
                        requestAnimationFrame(initCursor);
                    }
                };
                initCursor();

                // Cập nhật tọa độ khi chuột di chuyển
                document.addEventListener('mousemove', (e) => {
                    cursor.style.left = e.clientX + 'px';
                    cursor.style.top = e.clientY + 'px';
                });

                // Hiệu ứng nhấp nháy khi Click
                document.addEventListener('mousedown', () => {
                    cursor.style.backgroundColor = 'rgba(46, 204, 113, 0.9)'; // Chuyển xanh lá
                    cursor.style.transform = 'translate(-50%, -50%) scale(0.6)'; // Thu nhỏ móp lại
                });

                document.addEventListener('mouseup', () => {
                    cursor.style.backgroundColor = 'rgba(220, 20, 60, 0.7)';
                    cursor.style.transform = 'translate(-50%, -50%) scale(1)';
                });
            }
        """
        try:
            # Dùng add_init_script để chuột ảo tự động tiêm lại mỗi khi load sang trang mới hoặc back trang
            page.context.add_init_script(cursor_script)
            
            # Tiêm ngay lập tức vào trang hiện tại (nếu trang đã load xong)
            page.evaluate(cursor_script)
        except Exception as e:
            print(f"      [-] Không thể khởi tạo chuột ảo: {e}")

    

    def action_interact_quora(self, page):
        """Kịch bản Quora: Lướt Feed hỏi đáp, chọn câu hỏi, đọc câu trả lời và Upvote"""
        print("  -> [Action] Bắt đầu phiên Quora: Lướt Feed và đọc các câu trả lời chuyên sâu...")
        try:
            # 1. Truy cập trang chủ Quora
            page.goto("https://www.quora.com/", wait_until="domcontentloaded", timeout=60000)
            self.random_sleep(3, 6)
            self.restore_mouse_position(page)
            self.random_sleep(0.5, 1)

            num_posts_to_interact = random.randint(2, 4)
            print(f"      + Kế hoạch phiên này: Khám phá {num_posts_to_interact} chủ đề trên Quora.")
            
            read_urls = set()

            for post_index in range(num_posts_to_interact):
                print(f"\n      + [Quora] Đang tìm và xử lý bài viết thứ {post_index + 1}/{num_posts_to_interact}...")
                
                # 2. Lướt Feed (Kết hợp Cuộn Xuống 80% và Cuộn Lên 20%)
                scroll_steps = random.randint(5, 8) 
                print(f"      + Đang lướt Feed ngẫu nhiên {scroll_steps} nhịp...")
                for _ in range(scroll_steps):
                    if random.random() < 0.3:
                        self.move_mouse_viewport_center(page)
                    
                    if random.random() < 0.8:
                        self.smooth_scroll(page, random.randint(500, 900))
                    else:
                        self.smooth_scroll(page, -random.randint(300, 500))
                    self.random_sleep(2, 4)
                    
                # 3. Bắt và lọc bài viết trên Feed
                # Quora thường dùng thẻ a chứa thẻ span.q-text cho các tiêu đề câu hỏi/câu trả lời
                all_posts = page.locator("div[class*=puppeteer_test_tribe_post_item_feed_story]").all()
                on_screen_posts = []
                viewport = page.viewport_size
                vh = viewport['height'] if viewport else 800
                
                for post in all_posts:
                    try:
                        if post.is_visible(timeout=500):
                            href = post.get_attribute("href")
                            text = post.inner_text().strip()
                            
                            # Lọc các link hợp lệ (có chữ đủ dài, không phải link profile/topic)
                            if href and len(text) > 20 and "/profile/" not in href and "/topic/" not in href and href not in read_urls:
                                box = self._safe_bbox(post)
                                if box and 0 <= box['y'] <= vh:
                                    on_screen_posts.append((post, href))
                    except:
                        continue
                
                if on_screen_posts:
                    # Bốc ngẫu nhiên một bài trong tầm nhìn
                    target_post_data = random.choice(on_screen_posts)
                    target_post = target_post_data[0]
                    target_href = target_post_data[1]
                    read_urls.add(target_href)
                    
                    # 4. Tính toán đưa tiêu đề câu hỏi ra giữa màn hình
                    box = self._safe_bbox(target_post)
                    if box and viewport:
                        scroll_amount = int(box['y'] - (viewport['height'] / 3))
                        if scroll_amount != 0:
                            self.smooth_scroll(page, scroll_amount)
                            self.random_sleep(1, 2)
                    
                    print("      + Đã khóa mục tiêu chủ đề. Đang click mở bài...")
                    self.human_click(page, target_post)
                    
                    # Chờ trang câu hỏi/câu trả lời tải xong
                    page.wait_for_load_state("domcontentloaded", timeout=30000)
                    self.random_sleep(4, 7)
                    self.restore_mouse_position(page)
                    
                    print(f"      + Đã vào bài {post_index + 1}. Đang cuộn đọc các câu trả lời (Answers)...")
                    
                    # 5. Lướt đọc nội dung các câu trả lời
                    for _ in range(random.randint(5, 9)):
                        if random.random() < 0.3:
                            self.move_mouse_viewport_center(page)
                            
                        if random.random() < 0.8:
                            self.smooth_scroll(page, random.randint(400, 700))
                        else:
                            self.smooth_scroll(page, -random.randint(200, 400))
                        self.random_sleep(3, 6)
                    
                    # 6. Tìm và Upvote cho một câu trả lời hay
                    # Nút Upvote của Quora rất đa dạng, bao phủ bằng aria-label là chuẩn nhất
                    all_upvotes = page.locator("div[role='button'][aria-label^='Upvote'], button[aria-label^='Upvote']").all()
                    on_screen_upvotes = []
                    
                    for btn in all_upvotes:
                        try:
                            if btn.is_visible(timeout=500):
                                box = self._safe_bbox(btn)
                                if box and 50 < box['y'] < vh - 50:
                                    on_screen_upvotes.append(btn)
                        except:
                            continue
                    
                    if on_screen_upvotes:
                        # Chọn Upvote 1 hoặc tối đa 2 câu trả lời
                        num_to_upvote = random.randint(1, min(2, len(on_screen_upvotes)))
                        print(f"      + Tìm thấy {len(on_screen_upvotes)} nút Upvote. Quyết định Upvote {num_to_upvote} câu trả lời.")
                        
                        chosen_comments = random.sample(on_screen_upvotes, num_to_upvote)
                        for idx, comment_upvote in enumerate(chosen_comments):
                            print(f"      + Đang rê chuột bấm Upvote thứ {idx + 1}...")
                            self.human_click(page, comment_upvote)
                            self.random_sleep(2, 4)
                    else:
                        print("      + [Bỏ qua] Không có nút Upvote nào hiển thị rõ trong tầm nhìn.")
                    
                    # 7. Thoát ra Feed để tiếp tục vòng lặp
                    print(f"      + Xong chủ đề {post_index + 1}. Đang Back lại trang chủ Quora...")
                    page.go_back(wait_until="domcontentloaded")
                    self.random_sleep(5, 8)
                    
                    self.restore_mouse_position(page)
                    self.random_sleep(1, 2)
                    
                else:
                    print("      [-] Màn hình hiện tại chưa bắt được chủ đề mới. Sẽ lướt thêm ở lượt sau.")

            print(f"  -> [Action] HOÀN TẤT PHIÊN QUORA! (Đã khám phá {num_posts_to_interact} chủ đề).")

        except Exception as e:
            print(f"      + Lỗi khi tương tác Quora: {e}")

    # ==========================================
    # HÀNH ĐỘNG MỚI: TIKTOK & WIKIPEDIA (Task 4)
    # ==========================================

    def _detect_locale_lang(self, page):
        """Đọc ngôn ngữ trình duyệt (navigator.language) để chọn subdomain Wikipedia theo IP/locale.
        Trả về mã 2 ký tự như 'vi', 'en', 'ja'... Mặc định 'en' nếu lỗi."""
        try:
            lang = page.evaluate("navigator.language || 'en'")
            code = str(lang).split("-")[0].lower()
            return code if code else "en"
        except Exception:
            return "en"

    def _navigate_via_google(self, page, keyword, target_domain):
        """Cổng vào TỰ NHIÊN cho mọi site đích: lên Google -> human_type từ khóa ->
        cuộn lướt đọc kết quả (hành vi người thật) -> bấm kết quả thuộc target_domain.
        KHÔNG bao giờ goto thẳng link đích. Trả về True nếu cuối cùng đáp đúng site."""
        try:
            print(f"      + [Google] Mở Google để tìm '{keyword} {target_domain}' (không vào thẳng)...")
            # v1.4.6: nếu tab ĐANG ở Google sẵn (rất hay xảy ra — ví dụ vừa chết
            # trên trang kết quả), goto google.com không đổi gì trên màn hình ->
            # đọc log cũ dễ hiểu nhầm là "bỏ qua bước gõ". Nói rõ để khỏi nghi.
            try:
                if "google.com" in (page.url or "").lower():
                    print("      + [Google] Tab đang ở Google sẵn — mở lại trang chủ Google rồi gõ lại từ khóa (KHÔNG phải bỏ cổng Google).")
            except Exception:
                pass
            try:
                page.goto("https://www.google.com", wait_until="domcontentloaded", timeout=45000)
            except Exception as goto_err:
                if "interrupted" in str(goto_err).lower():
                    try:
                        page.evaluate("window.stop()")
                    except Exception:
                        pass
                    self.random_sleep(2, 3)
                    page.goto("https://www.google.com", wait_until="domcontentloaded", timeout=45000)
                else:
                    raise goto_err

            self.random_sleep(1, 2)
            search_box = page.locator("textarea[name='q'], input[name='q']").first
            search_box.wait_for(state="visible", timeout=8000)
            search_box.click(timeout=4000)
            self.random_sleep(0.3, 0.9)
            self.human_type(search_box, f"{keyword} {target_domain.split('.')[0]}")
            page.keyboard.press("Enter")
            page.wait_for_load_state("domcontentloaded", timeout=50000)
            self.random_sleep(2, 4)

            # --- Hành vi cuộn lướt kết quả như người thật (6-13s) ---
            print("      + [Google] Đang lướt cân nhắc các kết quả tìm kiếm...")
            end_time = time.time() + random.randint(6, 13)
            while time.time() < end_time:
                self.smooth_scroll(page, random.randint(250, 650))
                self.random_sleep(2, 4)
            if random.random() < 0.5:  # cuộn ngược lên chọn kết quả top
                self.smooth_scroll(page, -random.randint(300, 800))
                self.random_sleep(1, 3)

            # --- Tìm và bấm kết quả thuộc đúng domain đích ---
            # BÀI HỌC DOM THẬT (diag 2026-10-12): Google rewrite href về "/goto?url=<base64>"
            # -> target_domain KHÔNG BAO GIỜ nằm trong href. Domain thật chỉ xuất hiện
            # trong text breadcrumb dưới tiêu đề (vd "Wikipedia | https://en.wikipedia.org › ...").
            # Vì vậy phải kiểm tra CẢ href lẫn innerText, và lọc các anchor trùng 0x0 (ẩn).
            anchors = page.locator("a:has(h3)").all()
            candidates = []
            for a in anchors:
                try:
                    box = self._safe_bbox(a)
                    if not box or box['width'] < 10 or box['height'] < 10:
                        continue  # bản sao anchor ẩn (0x0) của cùng kết quả
                    href = a.get_attribute("href") or ""
                    try:
                        text = a.inner_text(timeout=1000)
                    except Exception:
                        text = ""
                    if target_domain in href or target_domain in text:
                        candidates.append(a)
                except Exception:
                    continue
            if not candidates:
                print(f"      + [Google] Trang 1 không có kết quả {target_domain}.")
                return False

            target = random.choice(candidates[:min(len(candidates), 5)])
            print(f"      + [Google] Bấm 1 kết quả {target_domain} trong top {min(len(candidates), 5)}.")

            # BÀI HỌC (diag_click 2026-10-12, DOM thật): mouse.down/up thô (human_click)
            # KHÔNG kích hoạt điều hướng link kết quả Google (URL đứng yên, không mở tab),
            # trong khi Locator.click() chuẩn thì điều hướng OK. Vì vậy vẫn rê chuột Bezier +
            # hover như người thật để tạo tín hiệu di chuột, nhưng PHÁT ĐỘNG bằng
            # Locator.click(). click() chờ trang đích load xong nên hay báo timeout — bỏ qua
            # exception, vòng poll URL bên dưới mới là quyết định.
            try:
                target.scroll_into_view_if_needed(timeout=5000)
            except Exception:
                pass
            # Rê chuột tới kết quả + ngập ngừng (hành vi người thật trước khi bấm)
            try:
                self.move_mouse_bezier(page, target)
                self.random_sleep(0.4, 1.5)
            except Exception:
                pass
            try:
                target.click(timeout=10000)
            except Exception as click_err:
                # click() chờ trang đích load xong nên hay báo timeout (Wikipedia/TikTok
                # chậm) -> navigation THỰC TẾ đã xảy ra. Bỏ qua, vòng poll URL dưới quyết định.
                print(f"      + [Google] click() trả lời: {str(click_err)[:80]} (bỏ qua, poll URL)")

            # --- Chờ redirect /goto -> site đích hoàn tất (poll URL tới ~12s) ---
            # BÀI HỌC: href là /goto?url=<base64>, trình duyệt phải nhảy qua nhiều hop
            # (google interstitial -> site thật). wait_for_load_state 1 lần dễ bắt trúng
            # trang trung gian, nên PHẢI poll page.url cho tới khi thấy target_domain.
            landed = False
            deadline = time.time() + 12
            while time.time() < deadline:
                try:
                    if target_domain in page.url:
                        landed = True
                        break
                    # Google đôi khi mở kết quả ở tab mới -> lấy URL rồi đưa tab hiện tại tới đó
                    for p in page.context.pages:
                        if p is not page and target_domain in p.url:
                            new_url = p.url
                            try:
                                p.close()  # dọn tab mồ côi, giữ 1 tab nhất quán cho caller
                            except Exception:
                                pass
                            try:
                                page.goto(new_url, wait_until="domcontentloaded", timeout=20000)
                                landed = True
                            except Exception:
                                pass
                            break
                except Exception:
                    pass
                if landed:
                    break
                self.random_sleep(0.4, 0.9)

            if landed:
                self.random_sleep(1, 2)
                print(f"      + [Google] Đã đáp vào {target_domain} một cách tự nhiên.")
                return True
            print(f"      + [Google] Bấm xong nhưng chưa đáp {target_domain} (URL: {page.url}) -> fallback.")
            return False
        except Exception as e:
            print(f"      + [Google] Điều hướng qua Google thất bại: {e}")
            return False

    def _preview_sweep_browse(self, page, elements):
        """Xem lướt bằng chuột: quẹt qua vài thumb, dừng trỏ chuột 'ngắm' ngẫu nhiên.
        v1.4.5: CHỈ dùng cho trang chủ YouTube (list locator thumbnail). TikTok dùng feed
        scroll-snap toàn màn hình nên tự có nhánh xử lý riêng trong action_watch_tiktok.
        Số thumb được trỏ xem + thời lượng dừng ở từng thumb = ngẫu nhiên
        (random tỷ lệ), không click."""
        try:
            if not elements:
                return
            sweep_count = random.randint(2, 5)
            picked = random.sample(elements, min(sweep_count, len(elements)))
            print(f"      + Lướt qua {len(picked)} thumb, dừng trỏ xem ngẫu nhiên...")
            for el in picked:
                try:
                    # Random tỷ lệ hành vi từng thumb: lướt vội / liếc nhanh / ngắm kỹ
                    mode_roll = random.random()
                    if mode_roll < 0.25:
                        # Lướt vội qua: vẫn PHẢI trỏ chuột vào thumb (v1.4.5 — trước đây
                        # nhánh này bỏ qua human_hover nên ~25% thumb không hề được trỏ)
                        self._smooth_scroll_to_element(page, el)
                        self.human_hover(page, el)
                        self.random_sleep(0.3, 0.8)
                    elif mode_roll < 0.55:
                        # Nhìn lướt: dừng ngắn
                        self._smooth_scroll_to_element(page, el)
                        self.random_sleep(0.5, 1.2)
                        self.human_hover(page, el)
                        self.random_sleep(1.5, 3.5)
                    else:
                        # Ngắm kỹ: dừng dài hơn
                        # v1.4.3: hạ trần 7s -> 6s để không tạo cảm giác "đứng im"
                        self._smooth_scroll_to_element(page, el)
                        self.random_sleep(0.5, 1.5)
                        self.human_hover(page, el)
                        self.random_sleep(2.5, 6)
                        if random.random() < 0.35:
                            # Rê chuột rời ra rồi quay lại (kiểu mắt lười, đọc tên video)
                            self.move_mouse_viewport_center(page)
                            self.random_sleep(1, 2)
                except Exception:
                    continue
            # Người thật đôi khi quẹt lố rồi kéo ngược lên xem lại thumb vừa lướt
            if random.random() < 0.3:
                print("      + Quẹt lố, kéo nhẹ ngược lên nhìn lại...")
                self.smooth_scroll(page, -random.randint(150, 400))
                self.random_sleep(1, 2.5)
        except Exception:
            pass

    def action_watch_tiktok(self, page):
        """Kịch bản TikTok (Bản Thuần Xem): Lướt feed video KHÔNG cần login, KHÔNG like/comment.
        Chỉ mô phỏng hành vi xem và cuộn để tạo tín hiệu fingerprint."""
        print("  -> [Action] Bắt đầu phiên TikTok: Tìm qua Google + lướt video (chế độ xem, không tương tác)...")
        try:
            keyword = self.session_theme.get("google_query", "giai tri").strip()

            # --- CỔNG VÀO TỰ NHIÊN: Google -> gõ từ khóa -> cuộn -> bấm kết quả TikTok ---
            landed = self._navigate_via_google(page, keyword, "tiktok.com")
            if not landed:
                # Fallback: chỉ khi Google lỗi/không có kết quả mới vào thẳng feed
                print("      + (Fallback Google) Vào feed For You trực tiếp...")
                try:
                    page.goto("https://www.tiktok.com/foryou", wait_until="domcontentloaded", timeout=60000)
                except Exception as goto_err:
                    if "interrupted" in str(goto_err).lower():
                        print("      [!] Chuyển hướng bị kẹt. Đang ép dừng và tải lại TikTok...")
                        try:
                            page.evaluate("window.stop()")
                        except:
                            pass
                        self.random_sleep(2, 4)
                        page.goto("https://www.tiktok.com/foryou", wait_until="domcontentloaded", timeout=60000)
                    else:
                        raise goto_err

            self.random_sleep(3, 6)
            self.move_mouse_viewport_center(page)
            self.random_sleep(0.5, 1)

            # --- Đóng an toàn popup cookie / login (logged-out hay bị chặn bởi overlay) ---
            # v1.4.3: TikTok hiện dùng modal "Đăng nhập" che gần hết màn hình -> phải đóng
            # được nó mới thấy video. Lưu ý: KHÔNG bấm vào nút "Đăng nhập"/"Log in" (bấm là
            # mở luôn luồng đăng nhập), chỉ bấm nút ĐÓNG của modal.
            # Bản cũ đặt selector nút "Đăng nhập" trước nút đóng và `break` ngay sau lần
            # click đầu -> có thể bấm nhầm nút đăng nhập rồi bỏ luôn bước đóng modal.
            dismissed = 0
            for sel in [
                'button:has-text("Accept all")',
                'button:has-text("Consent")',
                '[data-e2e="cookie2-popup-accept-all-button"]',
                'div[role="dialog"] [aria-label="Close"]',
                'div[role="dialog"] [data-e2e="modal-close-inner-button"]',
                '[data-e2e="modal-close-inner-button"]',
                'button[aria-label="Close"]',
                'x-icon[role="button"]',
                'div[role="dialog"] button:has-text("Not now")',
                'div[role="dialog"] button:has-text("Để sau")',
            ]:
                if dismissed >= 3:
                    break
                try:
                    btn = page.locator(sel).first
                    if btn.is_visible(timeout=600):
                        btn.click(timeout=1500)
                        dismissed += 1
                        self.random_sleep(1, 2)
                except Exception:
                    continue
            if dismissed:
                print(f"      + Đã đóng {dismissed} lớp popup/overlay (cookie hoặc modal đăng nhập).")
                self.random_sleep(0.5, 1.5)

            # --- v1.4.3: CỔNG CHẶN "TRANG KHÔNG CÓ VIDEO" ---
            # Cổng Google đôi khi trả về trang dạng lưới (tiktok.com/discover/...) hoặc
            # trang trắng/overlay đăng nhập -> KHÔNG có video nào phát. Trước đây bot vẫn
            # "xem" vô ích (mỗi vòng 12-35s, lại còn treo 30s ở bounding_box) nên nhìn như
            # ĐỨNG IM. Giờ phát hiện sớm và đưa về feed For You.
            # Lưu ý: TikTok render feed theo layout animation nên 1-2s đầu có thể chưa có
            # thẻ <video> -> phải chờ ngắn (bounded) trước khi kết luận là trang rỗng.
            feed_ok = False
            vcount = -1
            for attempt in range(2):
                try:
                    vcount = page.locator("video:visible").count()
                except Exception:
                    vcount = 0
                if vcount > 0:
                    feed_ok = True
                    break
                print(f"      [!] Trang hiện tại không có video nào phát (lần {attempt + 1}/2) - chuyển về feed For You... (đích vẫn là TikTok — không phải bỏ cổng Google)")
                try:
                    page.goto("https://www.tiktok.com/foryou", wait_until="domcontentloaded", timeout=60000)
                except Exception as goto_err:
                    if "interrupted" in str(goto_err).lower():
                        print("      [!] Chuyển hướng bị kẹt. Đang ép dừng và tải lại TikTok...")
                        try:
                            page.evaluate("window.stop()")
                        except Exception:
                            pass
                    self.random_sleep(1, 2)
                self.random_sleep(1.5, 3)
                try:
                    page.locator("video").first.wait_for(state="attached", timeout=7000)
                except Exception:
                    pass
            if not feed_ok:
                # Lần kiểm tra cuối (không goto thêm) - tránh cộng dồn chờ vô ích
                try:
                    feed_ok = page.locator("video:visible").count() > 0
                except Exception:
                    feed_ok = False
            if not feed_ok:
                print("      [!] Không lấy được feed video TikTok - BỎ QUA action này (tránh đứng im).")
                return

            num_videos = random.randint(3, 7)
            print(f"      + Kế hoạch phiên này: Xem lần lượt {num_videos} video.")

            viewport = page.viewport_size
            vh = viewport['height'] if viewport else 900

            for v_index in range(num_videos):
                print(f"\n      + [TikTok] Đang xem video thứ {v_index + 1}/{num_videos}...")

                # 1. Ngồi xem video một khoảng thời lượng NGẪU NHIÊN kiểu người.
                #    v1.5.1: bản cũ `uniform(12, 35)` là phân phối ĐỀU nên mọi video
                #    đều rơi vào giữa dải — E2E 20/10 đo được 27/27/32/24/20/21s:
                #    không video nào "liếc rồi quẹt", cũng không video nào "xem lâu"
                #    -> trông như đồng hồ hẹn giờ chứ không phải người thật.
                #    Giờ pha 3 hành vi theo xác suất cộng dồn 1.0:
                #      ~45% liếc nhanh 4-12s, ~38% xem vừa 15-35s, ~17% xem lâu 45-90s.
                roll = random.random()
                if roll < 0.45:
                    watch_time = int(random.uniform(4, 12))
                    mood = "liếc nhanh"
                elif roll < 0.83:
                    watch_time = int(random.uniform(15, 35))
                    mood = "xem vừa"
                else:
                    watch_time = int(random.uniform(45, 90))
                    mood = "xem lâu (hứng thú)"
                print(f"      + Đang xem trong {watch_time}s ({mood})...")
                watched = 0
                while watched < watch_time:
                    # v1.4.6: chunk bị chặn bởi thời gian còn lại — log không còn
                    # in "(30/27s)" (xem vượt 100% do độ hạt của chunk)
                    chunk = min(random.uniform(3, 6), watch_time - watched)
                    time.sleep(chunk)
                    watched += chunk
                    # v1.4.3: in nhịp tim để người xem không thấy log "đứng im" im lặng
                    # v1.5.1: min() để dòng cuối không in "(13/12s)" khi chunk cán đích
                    print(f"         ...đang xem video {v_index + 1}/{num_videos} ({min(watched, watch_time):.0f}/{watch_time:.0f}s)")
                    # Thỉnh thoảng di chuột nhẹ để trông tự nhiên (không click gì)
                    if random.random() < 0.3:
                        self.move_mouse_viewport_center(page)

                # 2. Cuộn sang video kế tiếp (feed dùng scroll-snap ~ 1 viewport)
                #    v1.4.2: trước khi quẹt, đôi khi dừng trỏ chuột "ngắm" video như
                #    xem lướt, thậm chí quẹt nhẹ "thăm dò" rồi kéo về (random tỷ lệ)
                #    v1.4.5: nâng tỷ lệ 0.5 -> 0.75 và trỏ thêm thumb video KẾ TIẾP
                #    (E2E 16/10 tiktok 4 lượt chuyển mà 0 lần dừng trỏ -> quá hiếm)
                if v_index < num_videos - 1:
                    if random.random() < 0.75:
                        try:
                            print("      + Dừng chút, trỏ chuột ngắm video đang xem (kiểu xem lướt)...")
                            self.human_hover(page, page.locator("video:visible").first)
                            # Random tỷ lệ: thỉnh thoảng chỉ liếc qua, đôi khi ngắm lâu
                            # v1.4.3: hạ trần ngắm 9s -> 6s cho đỡ "đứng im" mà vẫn tự nhiên
                            if random.random() < 0.4:
                                self.random_sleep(1, 3)
                            else:
                                self.random_sleep(3, 6)
                            # Liếc sang video kế tiếp cạnh dưới (kiểu mắt đọc trước)
                            if random.random() < 0.5:
                                try:
                                    next_vid = page.locator("video:visible").nth(1)
                                    if next_vid.count() > 0:
                                        print("      + Liếc mắt xuống thumb video kế tiếp...")
                                        self.human_hover(page, next_vid)
                                        self.random_sleep(0.6, 1.6)
                                except Exception:
                                    pass
                        except Exception:
                            self.move_mouse_viewport_center(page)
                    if random.random() < 0.4:
                        print("      + Quẹt nhẹ xem trước video kế rồi kéo về...")
                        # v1.5.1: đổi sang _human_scroll (cùng nhịpEase với cú chuyển
                        # video). Chiều giữ nguyên như cũ: xuống 0.4-0.7 viewport rồi
                        # kéo NGƯỢC lại 100-300px = đúng nghĩa "xem trước rồi kéo về".
                        self._human_scroll(page, int(vh * random.uniform(0.4, 0.7)))
                        self.random_sleep(1, 2)
                        self._human_scroll(page, -random.randint(100, 300))
                        self.random_sleep(0.8, 1.5)
                    print("      + Cuộn sang video tiếp theo...")
                    # v1.5.1: CẢ viewport mà smooth_scroll vê xong trong 0.2-1.2s là
                    # nguyên nhân chính TikTok snap "cập" cái GIẬT -> _human_scroll
                    self._human_scroll(page, vh + random.randint(50, 200))
                    self.random_sleep(2, 4)

            print(f"  -> [Action] HOÀN TẤT PHIÊN TIKTOK! (Đã xem xong {num_videos} video).")
            self.restore_mouse_position(page)

        except Exception as e:
            print(f"      + Lỗi khi lướt TikTok: {e}")

    def action_read_wikipedia(self, page):
        """Kịch bản Wikipedia: Vào bài ngẫu nhiên theo NGÔN NGỮ của trình duyệt (theo IP/locale),
        cuộn đọc và thỉnh thoảng nhảy sang bài liên quan. Tín hiệu sạch, an toàn nhất."""
        print("  -> [Action] Bắt đầu phiên Wikipedia: Tìm qua Google rồi đọc bài theo locale...")
        try:
            lang = self._detect_locale_lang(page)
            base_url = f"https://{lang}.wikipedia.org"
            keyword = self.session_theme.get("google_query", "kien thuc").strip()
            print(f"      + Ngôn ngữ trình duyệt: '{lang}' -> đích {base_url}")

            # --- CỔNG VÀO TỰ NHIÊN: Google -> gõ từ khóa -> cuộn -> bấm kết quả Wikipedia ---
            landed = self._navigate_via_google(page, keyword, "wikipedia.org")

            self.random_sleep(2, 4)
            self.move_mouse_viewport_center(page)

            if not landed:
                # Fallback: CHỈ khi Google lỗi/không có kết quả mới vào thẳng (hiếm gặp)
                print("      + (Fallback Google) Vào Special:Random trực tiếp...")
                try:
                    page.goto(f"{base_url}/wiki/Special:Random", wait_until="domcontentloaded", timeout=60000)
                    self.random_sleep(2, 4)
                except Exception:
                    pass

            # Đọc bài hiện tại (tái dùng helper có sẵn)
            self._simulate_scroll_and_read(page, random.randint(60, 120), random.randint(150, 240))

            # 40% nhảy sang 1 bài nội bộ rồi đọc tiếp
            if random.random() < 0.4:
                print("      + Quyết định nhấp vào 1 liên kết nội bộ trong bài...")
                try:
                    links = page.locator("#bodyContent a[href^='/wiki/']").all()
                    on_screen_links = []
                    for a in links:
                        try:
                            if a.is_visible(timeout=400):
                                href = a.get_attribute("href")
                                if href and "Special:Random" not in href and "#(" not in href:
                                    on_screen_links.append(a)
                        except Exception:
                            continue

                    if on_screen_links:
                        target_link = random.choice(on_screen_links)
                        self.human_click(page, target_link)
                        page.wait_for_load_state("domcontentloaded", timeout=30000)
                        self.random_sleep(2, 4)
                        self._simulate_scroll_and_read(page, random.randint(50, 90), random.randint(120, 200))
                    else:
                        print("      + [Bỏ qua] Không tìm thấy liên kết nội bộ phù hợp.")
                except Exception as link_err:
                    print(f"      + Bỏ qua nhảy liên kết do lỗi: {link_err}")

            print("  -> [Action] HOÀN TẤT PHIÊN WIKIPEDIA!")

        except Exception as e:
            print(f"      + Lỗi khi đọc Wikipedia: {e}")

    # ==========================================
    # PHA 2/3 - QUẢN LÝ GOOGLE ALERTS (google.com/alerts)
    # Selector đã chốt từ DOM thật (diag 2026-10, account logged-in, locale vi).
    # Mọi bước phụ best-effort: thiếu selector nào bỏ qua bước đó, không fail cả action.
    # ==========================================

    def _alerts_logged_in(self, page):
        """Kiểm tra đã đăng nhập Google chưa (qua trang alerts)."""
        try:
            if page.locator('a.gb_C[aria-label*="@"]').count() > 0:
                return True
        except Exception:
            pass
        try:
            if page.locator('li.alert_instance').count() > 0:
                return True
        except Exception:
            pass
        try:
            if page.locator('a[href*="ServiceLogin"], a[href*="accounts.google.com/signin"]').count() > 0:
                return False
        except Exception:
            pass
        return False

    def _find_alerts_query_input(self, page):
        """Tìm ô nhập từ khóa tạo thông báo (nhiều biến thể aria-label/locale)."""
        for sel in (
            'input[aria-label*="thông báo về"]',
            'input[aria-label*="Create an alert" i]',
            'input[aria-label*="an alert" i]',
            'input[aria-label*="通知"]',
        ):
            try:
                loc = page.locator(sel).first
                if loc.is_visible(timeout=1500):
                    return loc
            except Exception:
                continue
        return None

    def _read_alert_rows(self, page):
        """Trả về list (row_locator, query_text) cho các li.alert_instance ĐÃ LƯU.
        CHÚ Ý: li.result là kết quả preview (không phải alert đã lưu) -> bỏ qua."""
        rows = []
        try:
            locs = page.locator('li.alert_instance[data-id]').all()
        except Exception:
            return rows
        for r in locs:
            txt = ""
            try:
                txt = r.locator('.query_div span[tabindex="0"]').first.inner_text(timeout=1000).strip()
            except Exception:
                pass
            rows.append((r, txt))
        return rows

    def _count_alert_rows(self, page):
        return len(self._read_alert_rows(page))

    def _pick_alerts_menu_option(self, page, button_selector, desired_text):
        """Mở 1 nút menu kiểu goog-flat-menu-button (KHÔNG phải <select>) và chọn
        item theo text. Best-effort: không match thì Escape giữ default."""
        try:
            btn = page.locator(button_selector).first
            if not btn.is_visible(timeout=1500):
                return False
            btn.click(timeout=3000)
            self.random_sleep(0.6, 1.2)
            items = page.locator('.goog-menuitem:visible').all()
            target = None
            for it in items:
                try:
                    txt = it.inner_text(timeout=800).strip()
                except Exception:
                    continue
                if txt == desired_text or desired_text.lower() in txt.lower():
                    target = it
                    break
            if target is not None:
                try:
                    target.click(timeout=3000)
                    self.random_sleep(0.5, 1.0)
                    return True
                except Exception:
                    pass
            try:
                page.keyboard.press("Escape")
            except Exception:
                pass
            return False
        except Exception:
            try:
                page.keyboard.press("Escape")
            except Exception:
                pass
            return False

    def _create_google_alert(self, page, query):
        """Nhánh A: tạo 1 thông báo mới cho `query` (đã được gate dedup + cap tuần)."""
        loc = self._find_alerts_query_input(page)
        if loc is None:
            print("      + [Alerts] Không thấy ô nhập từ khóa. Bỏ qua tạo.")
            return False
        try:
            self.human_type(loc, query)
        except Exception as e:
            print(f"      + [Alerts] Gõ từ khóa lỗi: {e}")
            return False
        self.random_sleep(3, 4)

        # Mở panel "Hiển thị tùy chọn" (best-effort)
        try:
            so = page.locator('span.show_options').first
            so.wait_for(state="visible", timeout=6000)
            so.click(timeout=3000)
            self.random_sleep(1, 2)
        except Exception:
            print("      + [Alerts] Không mở được 'Hiển thị tùy chọn' — tạo với default.")

        # Chọn tần suất (best-effort, giữ default nếu menu lỗi)
        freq_texts = ["Ngay lập tức", "Tối đa một lần mỗi ngày", "Tối đa một lần mỗi tuần"]
        chosen_freq = random.choices(freq_texts, weights=[0.20, 0.50, 0.30], k=1)[0]
        self._pick_alerts_menu_option(
            page, 'div.goog-flat-menu-button.jfk-select.frequency_select', chosen_freq
        )

        # Bấm "Tạo Thông báo"
        try:
            ca = page.locator('span#create_alert').first
            ca.wait_for(state="visible", timeout=6000)
            try:
                ca.click(timeout=5000)
            except Exception:
                # click thường báo timeout vì chờ trang đích; poll DOM bên dưới quyết định
                pass
        except Exception as e:
            print(f"      + [Alerts] Không bấm được nút Tạo: {e}")
            return False

        # Poll xác nhận row mới xuất hiện (khớp query, không phân biệt hoa/thường)
        q_norm = query.strip().lower()
        deadline = time.time() + 12
        created = False
        while time.time() < deadline:
            for _, txt in self._read_alert_rows(page):
                if txt.strip().lower() == q_norm:
                    created = True
                    break
            if created:
                break
            self.random_sleep(0.5, 1.0)

        if created:
            print(f"      + [Alerts] Đã tạo thông báo '{query}' (tan suat: {chosen_freq}).")
            if self.db and self.profile_id:
                try:
                    self.db.log_alert_created(self.profile_id, query)
                except Exception as e:
                    print(f"      + [Alerts] Ghi DB lỗi: {e}")
            return True
        print("      + [Alerts] Không xác nhận được row mới sau 12s (Google cham?).")
        return False

    def _care_existing_alerts(self, page):
        """Nhánh B: ngắm/hover/chạm nhẹ các thông báo đã có, KHÔNG sửa/xóa."""
        rows = self._read_alert_rows(page)
        if not rows:
            print("      + [Alerts] Chưa có thông báo nào. Lướt trang rồi kết thúc.")
            self.move_mouse_viewport_center(page)
            self.smooth_scroll(page, random.randint(150, 400))
            self.random_sleep(4, 9)
            return False

        print(f"      + [Alerts] Co {len(rows)} thong bao da luu. Cham soc (khong sua/xoa)...")
        self.move_mouse_viewport_center(page)
        self.smooth_scroll(page, random.randint(150, 400))
        self.random_sleep(1, 3)

        # Hover 1-3 row ngẫu nhiên (tín hiệu chuột người thật)
        sample = random.sample(rows, k=random.randint(1, min(3, len(rows))))
        for r, txt in sample:
            try:
                self.move_mouse_bezier(page, r.locator('.query_div span[tabindex="0"]').first)
                self.random_sleep(1.5, 4)
            except Exception:
                continue

        # 50%: bấm 1 query để xem preview kết quả, rồi đóng bang close_icon
        if random.random() < 0.5:
            try:
                r, txt = random.choice(rows)
                r.locator('.query_div span[tabindex="0"]').first.click(timeout=4000)
                self.random_sleep(2, 5)
                try:
                    ci = page.locator('div.close_icon').first
                    if ci.is_visible(timeout=1500):
                        ci.click(timeout=2000)
                except Exception:
                    page.keyboard.press("Escape")
            except Exception:
                pass

        # 30%: mở panel chỉnh sửa (edit_button) roi DONG bang close_icon, KHONG luu
        if random.random() < 0.3:
            try:
                r, txt = random.choice(rows)
                edit = r.locator('span.edit_button.alert_button').first
                if edit.is_visible(timeout=1500):
                    edit.click(timeout=3000)
                    self.random_sleep(2, 4)
                    ci = page.locator('div.close_icon').first
                    if ci.is_visible(timeout=1500):
                        ci.click(timeout=2000)
                    else:
                        page.keyboard.press("Escape")
            except Exception:
                pass

        # Ngam danh sach them 5-15s
        dwell = random.randint(5, 15)
        print(f"      + [Alerts] Ngam danh sach thong bao ~{dwell}s...")
        end = time.time() + dwell
        while time.time() < end:
            if random.random() < 0.4:
                self.smooth_scroll(page, random.randint(-200, 300))
            self.random_sleep(1.5, 3.5)
        return True

    def action_manage_google_alerts(self, page):
        """Vao Google Alerts: tao thong bao moi (nhanh A) hoac cham thong bao da co
        (nhanh B). Pha 'youtube' chi cham, khong tao moi."""
        print("  -> [Action] Quan ly Google Alerts...")
        try:
            # 1. Vao thang trang alerts (Pha 2 user da quen he sinh thai Google)
            try:
                page.goto("https://www.google.com/alerts", wait_until="domcontentloaded", timeout=60000)
            except Exception as nav_err:
                if "interrupted" in str(nav_err).lower():
                    try:
                        page.evaluate("window.stop();")
                        page.goto("https://www.google.com/alerts", wait_until="domcontentloaded", timeout=60000)
                    except Exception:
                        pass
                else:
                    raise
            self.random_sleep(2, 4)
            self._close_popups(page)

            # 2. Cong login: chua dang nhap thi bo qua
            if not self._alerts_logged_in(page):
                print("      + (Chua login Google - bo qua alerts)")
                return False

            # 3. Chon nhanh
            query = (self.session_theme.get("google_query") or "tin tức mới nhất").strip()
            branch_a_possible = True
            if self.phase == "youtube":
                branch_a_possible = False  # Pha 3 chi cham, khong tao moi
            if not (self.db and self.profile_id):
                branch_a_possible = False  # khong co DB thi khong tao (tranh spam)
            else:
                try:
                    if self.db.alert_exists(self.profile_id, query):
                        branch_a_possible = False
                    elif not self.db.can_create_alert_week(self.profile_id):
                        branch_a_possible = False
                except Exception as db_err:
                    print(f"      + [Alerts] Loi kiem tra DB ({db_err}) - thien ve cham cu.")
                    branch_a_possible = False

            existing = self._count_alert_rows(page)
            # Profile moi (0 alert) duoc phep thi tao ngay; nguon da co -> 35% tao moi
            use_create = branch_a_possible and (existing == 0 or random.random() < 0.35)

            if use_create:
                print(f"      + Nhanh A: tao thong bao moi cho '{query}'.")
                ok = self._create_google_alert(page, query)
                self.random_sleep(3, 8)  # ngam sau khi tao, giong nguoi that
                return ok
            else:
                print("      + Nhanh B: cham soc thong bao da co.")
                return self._care_existing_alerts(page)
        except Exception as e:
            print(f"      + Loi khi quan ly Google Alerts: {e}")
            return False

    # ==========================================
    # CỖ MÁY ĐIỀU PHỐI (ORCHESTRATOR)
    # ==========================================

    def run_random_session(self, total_actions=5):
        """
        Khởi chạy một phiên lướt web hoàn toàn ngẫu nhiên.
        Tích hợp bộ nhớ chống lặp hành động liên tiếp.
        """
        page = self.context.new_page()
        self.enable_virtual_cursor(page)
        
        print(f"[*] Bắt đầu phiên làm việc ngẫu nhiên với {total_actions} hành động.")

        # --- AI Brain: Sinh biến thể từ khóa xoay quanh chủ đề của cặp được chọn ---
        if self.brain:
            theme = self.session_theme or {}
            # Google: mọi phase đều dùng google_query (search/tin tức/alerts/cổng Google)
            ai_keyword = self._safe_ask_keyword(topic_hint=theme.get("google_query", ""))
            if ai_keyword:
                self.session_theme["google_query"] = ai_keyword
            # YouTube: chỉ sinh khi phiên này THỰC SỰ xem YouTube (phase clean/youtube + không tick bỏ qua)
            # -> tránh tốn 1 lượt gọi AI vô ích ở phase mail hoặc khi bỏ qua YouTube
            if self.phase != "mail" and not getattr(self, "skip_youtube", False):
                ai_youtube = self._safe_ask_keyword(
                    topic_hint=theme.get("youtube_query", ""), platform_label="YouTube"
                )
                if ai_youtube:
                    self.session_theme["youtube_query"] = ai_youtube

        # === Bản đồ hành động theo GIAI ĐOẠN NGÂM (phase) ===
        if self.phase == "youtube":
            # Pha 3: cày YouTube là chính, điểm xuyết Google Alerts (chỉ chăm, không tạo mới)
            action_map = {
                "watch_video": (self.action_watch_video, 0.40),
                "action_search_youtube": (self.action_search_youtube, 0.60),
                "action_read_news": (self.action_read_news, 0.20),
                "action_read_wikipedia": (self.action_read_wikipedia, 0.20),
                "action_manage_google_alerts": (self.action_manage_google_alerts, 0.15),
            }
            if getattr(self, 'skip_youtube', False):
                action_map.pop("watch_video", None)
                action_map.pop("action_search_youtube", None)
                print("      [!] Chế độ BỎ QUA YOUTUBE đang bật (Pha 3 mất trục chính). Sẽ chỉ lướt web.")
        elif self.phase == "mail":
            # Pha 2: đã login mail — Google hệ sinh thái là trung tâm (Alerts, News, Wikipedia)
            action_map = {
                "read_news": (self.action_read_news, 0.35),
                "search_google": (self.action_search_and_read_news, 0.25),
                "action_read_wikipedia": (self.action_read_wikipedia, 0.30),
                "action_manage_google_alerts": (self.action_manage_google_alerts, 0.35),
                "action_watch_tiktok": (self.action_watch_tiktok, 0.20),
                "action_interact_reddit": (self.action_interact_reddit, 0.20),
                "action_search_weather": (self.action_search_weather, 0.1),
                "action_google_finance": (self.action_google_finance, 0.1),
            }
        else:
            # Pha 1 "clean": trắng, chưa mail — không đụng Google Alerts.
            # v1.4.1: acc MỚI chưa nên dạo Reddit (nền tảng "nặng" cho acc trắng) -> bỏ khỏi pha 1.
            # Chỉ lướt web thông tin (báo, Wikipedia, TikTok, Google tin tức) là đủ.
            action_map = {
                "read_news": (self.action_read_news, 0.35),
                "search_google": (self.action_search_and_read_news, 0.25),
                "action_search_weather": (self.action_search_weather, 0.1),
                "action_google_finance": (self.action_google_finance, 0.1),
                "action_watch_tiktok": (self.action_watch_tiktok, 0.45),
                "action_read_wikipedia": (self.action_read_wikipedia, 0.35),
            }
            # Chỉ bổ sung kịch bản YouTube nếu người dùng KHÔNG tick ô "Bỏ qua"
            if getattr(self, 'skip_youtube', False) == False:
                action_map["watch_video"] = (self.action_watch_video, 0.40)
                action_map["action_search_youtube"] = (self.action_search_youtube, 0.60)
            else:
                print("      [!] Chế độ BỎ QUA YOUTUBE đang bật. Sẽ chỉ lướt web và đọc báo.")

        print(f"      [Phase] Chế độ ngâm: {self.phase.upper()} ({len(action_map)} hành động trong lịch trình).")

        # Loại bỏ 2 hành động "từ khóa ngẫu nhiên" (không liên quan chủ đề) nếu người dùng tick ô "Bỏ qua"
        if getattr(self, 'skip_random_keywords', False):
            action_map.pop("action_search_weather", None)
            action_map.pop("action_google_finance", None)
            print("      [!] Chế độ BỎ QUA TỪ KHÓA NGẪU NHIÊN đang bật. Sẽ không tra thời tiết/tài chính ngẫu nhiên.")
        
        last_action_name = None 

        for i in range(total_actions):
            if self.stop_requested:
                print(f"\n[!] [Stop] Người dùng yêu cầu dừng - kết thúc phiên sau {i} hành động.")
                break
            print(f"\n[*] Hành động thứ {i+1}/{total_actions}:")
            
            # 1. Lọc bỏ hành động vừa chạy ở lượt trước
            valid_actions = {name: data for name, data in action_map.items() if name != last_action_name}
            
            # (Fallback an toàn: Nếu anh chỉ bật đúng 1 hành động duy nhất trong action_map thì bỏ qua bộ lọc)
            if not valid_actions:
                valid_actions = action_map
                
            # 2. Bốc thăm hành động mới dựa trên danh sách đã lọc
            action_names = list(valid_actions.keys())
            weights = [data[1] for data in valid_actions.values()]
            
            chosen_action_name = random.choices(action_names, weights=weights, k=1)[0]
            action_function = valid_actions[chosen_action_name][0]
            
            # 3. Ghi nhớ hành động này để chặn ở vòng lặp sau
            last_action_name = chosen_action_name
            
            # 4. Thực thi (v1.2.6: bấm giờ + ghi lỗi để đổ vào cột status/duration_s/error)
            _t0 = time.time()
            _status, _err = "ok", None
            try:
                action_function(page)
            except Exception as e:
                _status, _err = "error", str(e)
                raise  # giữ nguyên hành vi cũ: lỗi action vẫn lan lên caller
            finally:
                # 4.5 TASK 5 — Ghi activity-level cho action đọc/lướt.
                # (2 action YouTube đã tự ghi video-level trong _watch_single_video_logic -> bỏ qua để khỏi double)
                if chosen_action_name not in ("watch_video", "action_search_youtube"):
                    self._log_activity(page, chosen_action_name, status=_status,
                                       duration_s=round(time.time() - _t0, 1), error=_err)
            
            # Nghỉ giữa 2 hành động, nhưng responsive với Stop
            sleep_end = time.time() + random.uniform(5, 10)
            while time.time() < sleep_end and not self.stop_requested:
                time.sleep(0.5)

        print("[+] Kết thúc phiên làm việc ngẫu nhiên.")
        page.close()

    def restore_mouse_position(self, page):
        """Khôi phục vị trí chấm đỏ trên giao diện mới dựa trên tọa độ cuối cùng đã lưu"""
        try:
            if hasattr(page.mouse, '_last_x') and hasattr(page.mouse, '_last_y'):
                # Gọi lệnh move ngay tại chỗ cũ để kích hoạt lại sự kiện mousemove trên DOM mới
                page.mouse.move(page.mouse._last_x, page.mouse._last_y)
                time.sleep(random.uniform(0.1, 0.3))
            else:
                # Nếu mới mở trình duyệt chưa có tọa độ cũ thì bay vào giữa màn hình
                self.move_mouse_viewport_center(page)
        except Exception as e:
            pass
    # ==========================================
    # CÁC HÀM TIỆN ÍCH CỐT LÕI (GIỮ NGUYÊN HOẶC CẬP NHẬT)
    # ==========================================

    def _simulate_scroll_and_read(self, page, min_seconds=120, max_seconds=500):
        """Cuộn trang liên tục và tự động diệt quảng cáo"""
        read_time_seconds = random.randint(min_seconds, max_seconds)
        print(f"      + Đang tập trung đọc nội dung bài viết trong ~{read_time_seconds}s...")
        
        end_time = time.time() + read_time_seconds
        while time.time() < end_time:
            # LIÊN TỤC QUÉT VÀ TẮT QUẢNG CÁO
            self._close_popups(page)
            
            scroll_down_distance = random.randint(300, 800)
            self.smooth_scroll(page, scroll_down_distance)
            
            self.random_sleep(2, 10) 
            
            if random.random() < 0.2:
                scroll_up_distance = -random.randint(200, 500)
                self.smooth_scroll(page, scroll_up_distance)
                self.random_sleep(1, 3)
                
        print("      + Đã đọc xong bài. Đang nghỉ ngơi trước khi chuyển hành động...")
        self.random_sleep(3, 6)

    def _random_youtube_actions(self, page):
        action = random.random()
        if action < 0.1:
            page.keyboard.press("Space")
            time.sleep(random.uniform(2, 5))
            page.keyboard.press("Space")
        elif action < 0.2:
            page.keyboard.press("l")
        elif action < 0.25:
            page.keyboard.press("j")
        elif action < 0.3:
            page.keyboard.press("f")
            time.sleep(random.uniform(3, 10))
            page.keyboard.press("f")
        elif action < 0.35:
            page.keyboard.press("ArrowUp") if random.choice([True, False]) else page.keyboard.press("ArrowDown")

    def _check_and_skip_ad(self, page):
        ad_selectors = [".ytp-ad-skip-button-modern", ".ytp-ad-skip-button", ".ytp-skip-ad-button"]
        for selector in ad_selectors:
            try:
                skip_btn = page.locator(selector)
                if skip_btn.count() > 0 and skip_btn.first.is_visible():
                    print("      [!] Đã bấm Skip Ad.")
                    self.human_click(page, skip_btn.first)
                    time.sleep(1)
                    return True
            except:
                pass
        return False

    def _parse_time(self, time_str):
        # v1.4.6: rỗng/không parse được -> trả 0 (trước đây trả 120, làm chết
        # fallback `random.randint(180, 300)` của _watch_single_video_logic —
        # video thiếu badge .ytp-time-duration bị chốt cứng xem 66-108s).
        parts = (time_str or "").strip().split(":")
        try:
            if len(parts) == 2:
                return int(parts[0]) * 60 + int(parts[1])
            elif len(parts) == 3:
                return int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
        except ValueError:
            pass
        return 0

    # ==========================================
    # TASK 5 — LOG ACTIVITY (reporting thuần, không ảnh hưởng hành vi bot)
    # ==========================================

    # (v1.3.1) Ánh xạ tên action -> nền tảng. Bền hơn suy từ URL vì vài action
    # kết thúc ở about:blank (Reddit go_back khỏi bài) hoặc host phụ (bài báo
    # mở sau khi vào Google Finance). Action ĐA-SITE (đọc báo, search+rồi đọc
    # bài) KHÔNG có ở đây -> vẫn suy từ URL để giữ đúng host thật.
    _ACTION_PLATFORM = {
        "action_interact_reddit": "Reddit",
        "action_watch_tiktok": "TikTok",
        "action_read_wikipedia": "Wikipedia",
        "action_manage_google_alerts": "GoogleAlerts",
        "action_search_weather": "Google",
        "action_google_finance": "Google",
    }

    def _derive_platform(self, url):
        """Suy ra tên nền tảng từ URL hiện tại (best-effort)."""
        u = (url or "").lower()
        if "youtube.com" in u:
            return "YouTube"
        if "tiktok.com" in u:
            return "TikTok"
        if "reddit.com" in u:
            return "Reddit"
        if "wikipedia.org" in u:
            return "Wikipedia"
        if "google.com/alerts" in u:
            return "GoogleAlerts"
        if "quora.com" in u:
            return "Quora"
        if "google.com" in u:
            return "Google"
        try:
            if u.startswith("http"):
                host = u.split("/")[2]
                return host[4:] if host.startswith("www.") else host
        except Exception:
            pass
        return ""

    def _log_activity(self, page, action, platform=None, url=None, title=None,
                      status="ok", duration_s=None, error=None):
        """Ghi 1 dòng activity_history. Best-effort: không DB / lỗi DB -> im lặng bỏ qua.
        (v1.2.6: status/duration_s/error truyền xuống db.log_activity — cột Sprint 2.)"""
        if not (self.db and self.profile_id):
            return
        try:
            if url is None:
                url = page.url
            if platform is None:
                # (v1.3.1) ưu tiên suy theo TÊN action (ổn định), chỉ suy từ
                # URL khi action không có trong map (đa-site: đọc báo/search).
                platform = self._ACTION_PLATFORM.get(action) or self._derive_platform(url)
            if title is None:
                title = ""
            self.db.log_activity(self.profile_id, action, platform, url, title,
                                 status=status, duration_s=duration_s, error=error)
        except Exception as e:
            print(f"      + [Log] Bỏ qua ghi activity (loi: {e})")

    def _watch_single_video_logic(self, page, videos_remaining_to_watch=1):
        """
        Hàm xử lý logic xem video liên hoàn:
        - Xem đủ % thời lượng.
        - Random Like.
        - Sub nếu > 70% (và được phép).
        - Nếu vẫn còn số lượng video trong chuỗi (videos_remaining_to_watch > 1), 
          sẽ tự động chọn video tiếp theo ở cột phải để xem tiếp.
        """
        _t0 = time.time()  # v1.2.6: bấm giờ từng video cho cột duration_s
        _logged = False    # v1.2.6: tránh double-log (row error chỉ ghi nếu chưa ghi row ok)
        try:
            page.wait_for_load_state("domcontentloaded", timeout=30000)
            self.random_sleep(3, 6)
            
            # 1. Chờ & xử lý hết quảng cáo đầu video
            print("      + Đang kiểm tra quảng cáo đầu video...")
            for _ in range(30):
                if page.locator(".ad-showing").count() == 0:
                    break
                self._check_and_skip_ad(page)
                time.sleep(2)
                
            self.random_sleep(1, 3)
            
            # 2. Lấy thời lượng thực của video
            duration_text = page.locator(".ytp-time-duration").inner_text()
            total_seconds = self._parse_time(duration_text)
            if total_seconds == 0:
                total_seconds = random.randint(180, 300)
            
            watch_percent = random.uniform(0.55, 0.9)
            watch_seconds = int(total_seconds * watch_percent)

            # v1.4.7: CAP thời lượng xem/video — người thật BỎ DỞ video dài,
            # không ngồi 20+ phút cho MỘT video (E2E 17/10: video 45 phút ->
            # bot định xem 1568s = 26 phút, log im lặng = "đứng im"). Video
            # ngắn (watch_seconds <= cap) giữ nguyên hành vi % thời lượng thật.
            cap_seconds = random.randint(240, 420)
            capped = watch_seconds > cap_seconds
            if capped:
                watch_seconds = cap_seconds
            if capped:
                print(f"      + Thời lượng thực: {total_seconds}s. Sẽ xem: ~{watch_seconds}s (bỏ dở — cap {cap_seconds}s, kiểu người thật không cày hết video dài).")
            else:
                print(f"      + Thời lượng thực: {total_seconds}s. Sẽ xem: {watch_percent*100:.1f}% (~{watch_seconds}s).")

            # 3. Tiến hành xem và lướt qua ad giữa video
            # v1.4.6: clamp — giấc nghỉ giữa video bị chặn bởi thời gian CÒN LẠI,
            # để tổng thời gian xem không vượt watch_seconds (log từng ghi
            # "30/27s" = xem 30s cho video 27s).
            # v1.4.7: thêm nhịp tim log (như vòng TikTok) — chống "đứng im".
            end_time = time.time() + watch_seconds
            watched = 0.0
            next_beat = 0.0
            while time.time() < end_time:
                if self.stop_requested:
                    print("      + [Stop] Nhận yêu cầu dừng - kết thúc sớm video đang xem.")
                    break
                self._check_and_skip_ad(page)
                remaining = end_time - time.time()
                if remaining <= 0:
                    break
                nap = min(random.uniform(4, 8), remaining)
                if self.stop_requested:
                    break
                time.sleep(nap)
                watched += nap
                # v1.4.7: nhịp tim mỗi ~20-30s trong lúc xem video YouTube
                if watched >= next_beat:
                    print(f"         ...đang xem video YouTube ({watched:.0f}/{watch_seconds}s)")
                    next_beat = watched + random.uniform(20, 30)
                if random.random() < 0.15:
                    self._random_youtube_actions(page)
            
            # 4. Random Like (40% tỷ lệ)
            if random.random() < 0.4:
                try:
                    like_btn = page.locator('button[aria-label*="thích video này" i], button[aria-label*="like this video" i]').first
                    if like_btn.is_visible(timeout=2000):
                        print("      + Thực hiện: Bấm Like video.")
                        self.human_click(page, like_btn)
                        self.random_sleep(1, 3)
                except:
                    pass

            # 5. Kịch bản Đăng ký (Subscribe) nếu xem > 70% và còn quota
            if watch_percent > 0.70 and getattr(self, 'needs_sub', False):
                try:
                    sub_btn = page.locator('ytd-subscribe-button-renderer button').first
                    if sub_btn.is_visible(timeout=2000):
                        print("      + Đạt điều kiện xem >70% và còn quota. Thực hiện: Bấm Đăng ký kênh.")
                        self.human_click(page, sub_btn)
                        self.random_sleep(2, 4)
                        
                        if self.db and self.profile_id:
                            self.db.log_sub_success(self.profile_id)
                        self.needs_sub = False 
                except Exception as e:
                    print(f"      + Lỗi khi bấm nút Subscribe: {e}")

            # 5.5 TASK 5 — Ghi video vừa xem (URL + tiêu đề) vào activity_history
            try:
                vid_title = (page.title() or "").replace(" - YouTube", "").strip()
                self._log_activity(page, "watch_video", platform="YouTube",
                                   url=page.url, title=vid_title,
                                   status="ok", duration_s=round(time.time() - _t0, 1))
                _logged = True
            except Exception:
                pass

            # 6. KIỂM TRA CHUỖI XEM LIÊN HOÀN (2-3 VIDEO)
            if self.stop_requested:
                print("      + [Stop] Không xem tiếp chuỗi video (người dùng yêu cầu dừng).")
                return
            if videos_remaining_to_watch > 1:
                print(f"      + Đã xem xong 1 video. Vẫn còn {videos_remaining_to_watch - 1} video trong chuỗi. Đang tìm video tiếp theo ở cột phải...")
                
                # Lấy các video đề xuất ở cột bên phải
                selector = "ytd-watch-next-secondary-results-renderer a[href^='/watch?v=']:visible"
                suggested_videos = page.locator(selector).all()
                if suggested_videos:
                    target_suggested = random.choice(suggested_videos[:8])
                    
                    # Cuộn mượt và ngắm nghía trước khi click video tiếp theo
                    target_suggested.scroll_into_view_if_needed(timeout=3000)
                    self.random_sleep(2, 4)
                    print("      + Đang chọn video đề xuất tiếp theo...")
                    
                    self.human_click(page, target_suggested)
                    
                    # Đệ quy gọi lại chính hàm này, giảm số lượng video còn lại đi 1
                    self._watch_single_video_logic(page, videos_remaining_to_watch=videos_remaining_to_watch - 1)
                else:
                    print("      + Không tìm thấy video đề xuất nào bên phải để xem tiếp chuỗi.")
            else:
                print("      + Đã hoàn thành chuỗi xem YouTube trong session này.")

        except Exception as e:
            print(f"      + Lỗi trong quá trình xử lý chuỗi video: {e}")
            # v1.2.6: video fail trước khi ghi row ok -> ghi 1 row error (không double nếu đã log)
            if not _logged:
                try:
                    self._log_activity(page, "watch_video", platform="YouTube",
                                       url=page.url, title="",
                                       status="error",
                                       duration_s=round(time.time() - _t0, 1), error=str(e))
                except Exception:
                    pass
            time.sleep(random.randint(20, 40))

    def _smooth_scroll_to_element(self, page, element):
        """Tính toán khoảng cách vật lý và cuộn chuột mượt mà đến đúng vị trí phần tử"""
        try:
            # Lấy kích thước khung nhìn hiện tại
            viewport = page.viewport_size
            if not viewport:
                viewport = {'height': 720} # Fallback an toàn
                
            screen_height = viewport['height']
            
            # Lấy tọa độ của phần tử (relative so với màn hình hiện tại)
            # v1.4.3: dùng _safe_bbox() để element detached không treo 30s
            box = self._safe_bbox(element, timeout=2000)
            if not box:
                return

            # Vị trí Y của phần tử. Nếu Y > screen_height tức là nó nằm bên dưới chưa nhìn thấy.
            element_y = box['y']
            
            # Mục tiêu là đưa video vào tầm mắt người xem (khoảng 1/3 từ trên xuống)
            target_y_on_screen = screen_height / 3 
            
            # Khoảng cách thực tế cần cuộn (Dương = cuộn xuống, Âm = cuộn lên)
            distance_to_scroll = element_y - target_y_on_screen
            
            # Chỉ cuộn nếu khoảng cách lớn hơn 50px (tránh cuộn lắt nhắt)
            if abs(distance_to_scroll) > 50:
                print(f"        -> [Radar] Cách mục tiêu {int(distance_to_scroll)}px. Đang lăn chuột...")
                self.smooth_scroll(page, distance_to_scroll)
                
            # Cuối cùng, gọi nhẹ hàm dự phòng để đảm bảo Playwright khóa mục tiêu mà không bị giật
            element.scroll_into_view_if_needed(timeout=1000)
            
        except Exception as e:
            print(f"      [!] Lỗi khi đo tọa độ cuộn: {e}")
            
    def _close_popups(self, page):
        """Tìm và tắt các popup/quảng cáo HTML hiển thị đè lên trang"""
        # Danh sách bộ nhận diện các nút tắt quảng cáo phổ biến
        close_selectors = [
            "#dismiss-button",           # Nút tắt Google Ads
            "[aria-label='Close']",      # Chuẩn tiếng Anh
            "[aria-label='Close ad']",   # Nút đóng quảng cáo
            "[aria-label='Đóng']",       # Chuẩn tiếng Việt
            ".close-button", ".close-btn", ".close", 
            "svg[class*='close']",       # Nút tắt dùng icon SVG
            "button:has-text('Đóng')",   # Nút chứa chữ Đóng
            "button:has-text('Bỏ qua')"  # Nút chứa chữ Bỏ qua
        ]
        
        # v1.4.5: hàm này được gọi MỖI VÒNG của _simulate_scroll_and_read, mà popup thì
        # hiện liên tục -> trước đây in 1 dòng [+] cho MỖI element khớp selector (thấy tận
        # 19 dòng trùng nhau liên tiếp trong 1 lần đọc bài). Nay: chỉ in khi selector khớp
        # ĐỔI so với lần báo trước, và in 1 dòng tổng kết số nút đã bấm trong lần gọi này.
        clicked = 0
        sels_hit = []
        matched = []
        for selector in close_selectors:
            try:
                # Tìm xem có nút nào đang hiển thị trên màn hình không
                elements = page.locator(f"{selector}:visible").all()
            except Exception:
                continue # Bỏ qua nếu selector không đọc được
            if not elements:
                continue
            matched.append(selector)
            for el in elements:
                # Click tắt với timeout cực ngắn để không làm chậm bot
                try:
                    el.click(timeout=2000)
                    clicked += 1
                    self.random_sleep(1, 2)
                except Exception:
                    continue
            sels_hit.append(selector)

        # Chỉ báo khi "bộ selector khớp" ĐỔI so với lần báo trước: popup cũ còn hiện
        # trong lúc cuộn bài chỉ tốn đúng 1 dòng cho cả phiên đọc (trước fix: 1 dòng
        # cho MỖI element khớp -> thấy 19 dòng trùng nhau liên tiếp trong 1 lần đọc).
        hit_set = tuple(matched)
        if hit_set and hit_set != self._popup_sel_memo:
            print(f"      [+] Phát hiện popup quảng cáo chặn màn hình. Đang đóng...")
            self._popup_sel_memo = hit_set
        if clicked:
            print(f"      [+] Đã đóng {clicked} nút popup (selector: {', '.join(sels_hit)}).")

    def _generate_bezier_path(self, start_point, end_point, steps=30):
        """Hàm toán học sinh tọa độ các điểm trên đường cong Bezier"""
        x0, y0 = start_point
        x3, y3 = end_point
        
        # Tạo 2 điểm uốn (Control points) ngẫu nhiên để đường đi bị lệch cong như người cầm chuột
        x1 = x0 + (x3 - x0) * random.uniform(0.1, 0.4) + random.randint(-80, 80)
        y1 = y0 + (y3 - y0) * random.uniform(0.1, 0.4) + random.randint(-80, 80)
        
        x2 = x0 + (x3 - x0) * random.uniform(0.6, 0.9) + random.randint(-80, 80)
        y2 = y0 + (y3 - y0) * random.uniform(0.6, 0.9) + random.randint(-80, 80)
        
        path = []
        for i in range(steps + 1):
            t = i / steps
            # Áp dụng phương trình Bezier bậc 3
            x = (1 - t)**3 * x0 + 3 * (1 - t)**2 * t * x1 + 3 * (1 - t) * t**2 * x2 + t**3 * x3
            y = (1 - t)**3 * y0 + 3 * (1 - t)**2 * t * y1 + 3 * (1 - t) * t**2 * y2 + t**3 * y3
            path.append((x, y))
            
        return path

        """Kịch bản X (Twitter): Thả tim (Like) một dòng Tweet ngẫu nhiên"""
        print("      + [X] Đang tìm kiếm Tweet để thả tim...")
        try:
            # X thường dùng thuộc tính data-testid='like' cho nút tim chưa bấm
            like_buttons = page.locator("button[data-testid='like']").all()
            
            if like_buttons:
                visible_likes = [btn for btn in like_buttons if btn.is_visible()]
                
                if visible_likes:
                    # Chọn 1 nút ngẫu nhiên
                    target_btn = random.choice(visible_likes)
                    
                    self._smooth_scroll_to_element(page, target_btn)
                    self.random_sleep(1, 2)
                    
                    # Dừng lại đọc tweet vài giây
                    print("      + [X] Đang đọc nội dung Tweet...")
                    self.random_sleep(3, 6)
                    
                    print("      + [X] Đang rê chuột tới nút Like...")
                    self.human_hover(page, target_btn)
                    self.random_sleep(0.5, 1.5)
                    
                    if random.random() < 0.8: # 80% sẽ like
                        print("      + [X] Đã thả tim thành công!")
                        self.human_click(page, target_btn)
                        
            self.smooth_scroll(page, 400)
            self.random_sleep(3, 5)
        except Exception as e:
            print(f"      + [X] Lỗi tương tác: {e}")

