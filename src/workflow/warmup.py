import random
import time

class WarmupWorkflow:
    def __init__(self, context, db_handler=None, profile_id=None, needs_sub=False, session_theme=None, skip_youtube=False, skip_random_keywords=False):
        self.context = context
        self.db = db_handler
        self.profile_id = profile_id
        self.needs_sub = needs_sub
        self.skip_youtube = skip_youtube # LƯU TRẠNG THÁI TICK BỎ QUA YOUTUBE
        self.skip_random_keywords = skip_random_keywords # LƯU TRẠNG THÁI TICK BỎ QUA TỪ KHÓA NGẪU NHIÊN
        self.context.on("dialog", lambda dialog: dialog.accept())
        
        self.session_theme = session_theme or {
            "google_query": "tin tức mới nhất",
            "youtube_query": "video giải trí"
        }

    def random_sleep(self, min_s=2, max_s=5):
        time.sleep(random.uniform(min_s, max_s))

    # ==========================================
    # CÁC HÀNH ĐỘNG NGUYÊN TỬ (ATOMIC ACTIONS)
    # ==========================================

    def action_search_google(self, page):
        """Hành động 1: Lên Google tìm kiếm theo chủ đề AI chọn"""
        print("  -> [Action] Tìm kiếm Google...")
        
        # [CẬP NHẬT LẤY TỪ KHÓA TỪ AI THEME]
        keyword = self.session_theme.get("google_query", "tin tức thời sự")
        
        try:
            page.goto("https://www.google.com", wait_until="domcontentloaded", timeout=45000)
            self.humantype(page.locator("textarea[name='q'], input[name='q']").first, keyword)
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
        """Hành động 2: Vào thẳng trang báo, đọc và xử lý nhảy Tab thông minh"""
        print("  -> [Action] Đọc báo tin tức...")
        sites = ["https://vietnamnet.vn", "https://tienphong.vn", "https://vnexpress.net", "https://dantri.com.vn", "https://thanhnien.vn", "https://tuoitre.vn", "https://zingnews.vn", "https://cafef.vn","https://edition.cnn.com/","https://www.bbc.com/news","https://www.nytimes.com/","https://www.theguardian.com/international","https://www.reuters.com/"]
        target_site = random.choice(sites)
        
        try:
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
                                    box = link.bounding_box()
                                    
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
            # KỸ NĂNG HOVER PREVIEW THUMBNAIL (LƯỚT XEM TRƯỚC)
            # ---------------------------------------------------------
            num_previews = random.randint(2, 3)
            print(f"      + Sẽ dừng lại xem trước {num_previews} video ngẫu nhiên...")
            
            preview_candidates = random.sample(videos, min(num_previews, total_videos))
            
            for idx, p_vid in enumerate(preview_candidates):
                print(f"      + Đang rà chuột tới video preview thứ {idx+1}...")
                self._smooth_scroll_to_element(page, p_vid)
                self.random_sleep(1, 2)
                
                print(f"        -> Đang đưa chuột vào thumbnail chờ Auto-play (5-10s)...")
                self.human_hover(page, p_vid)
                self.random_sleep(5, 10)

            # ---------------------------------------------------------
            # CHỌN VIDEO MỤC TIÊU VÀ CLICK 
            # ---------------------------------------------------------
            target_video = random.choice(videos)
            print("      + Đã chốt video mục tiêu trên trang chủ. Đang lăn chuột tới vị trí click...")
            
            self._smooth_scroll_to_element(page, target_video)
            self.random_sleep(1, 2)
            
            target_video.hover()
            
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
        box = target_element.bounding_box()
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
        # 1. Di chuyển chuột lượn vòng tới mục tiêu bằng Bezier
        self.move_mouse_bezier(page, element)
        
        # 2. Xê dịch chuột nhè nhẹ (jitter) tại chỗ để giả lập tay người đang giữ chuột
        box = element.bounding_box()
        if box:
            current_x = box['x'] + box['width'] / 2
            current_y = box['y'] + box['height'] / 2
            
            # Rung nhẹ 2-4 nhịp, mỗi nhịp xê dịch vài pixel
            for _ in range(random.randint(2, 4)):
                jitter_x = current_x + random.uniform(-10, 10)
                jitter_y = current_y + random.uniform(-10, 10)
                page.mouse.move(jitter_x, jitter_y)
                
                # CẬP NHẬT TỌA ĐỘ VÀO BỘ NHỚ LƯU TRỮ CHUỘT ẢO
                page.mouse._last_x = jitter_x
                page.mouse._last_y = jitter_y
                
                time.sleep(random.uniform(0.1, 0.4))
    
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

    def action_google_finance(self, page):
        """Hành động: Truy cập trực tiếp Google Finance tìm kiếm mã cổ phiếu, tiền ảo, vàng"""
        print("  -> [Action] Truy cập Google Finance tra cứu thị trường...")
        try:
            # 1. Truy cập trang chủ Google Finance
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
                        visible_news = [n for n in news_links if n.is_visible() and n.bounding_box() and n.bounding_box()['y'] > 0 and n.bounding_box()['y'] < vh]
                        
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
    
                # Gõ từ khóa vào ô tìm kiếm và Enter
                page.type("input[name='search_query']", keyword)
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
        """Gõ phím mô phỏng người thật, tương thích 100% với mọi phiên bản Playwright Python"""
        try:
            # 1. Click vào ô input để focus
            locator.click()
            self.random_sleep(0.3, 0.6)
            
            print(f"      + Đang nhập từ khóa: '{text}'...")
            
            # 2. Duyệt qua từng ký tự và dùng page.keyboard để gõ
            for char in text:
                if char == " ":
                    # Nếu là khoảng trắng, dùng lệnh space hoặc gõ trực tiếp
                    page = locator.page
                    page.keyboard.press("Space")
                    delay = random.uniform(0.15, 0.35)
                else:
                    # Gõ ký tự thường
                    page = locator.page
                    page.keyboard.type(char)
                    
                    if random.random() < 0.12: 
                        delay = random.uniform(0.4, 0.7) # Khựng lại suy nghĩ
                    else:
                        delay = random.uniform(0.07, 0.18) # Tốc độ bình thường
                        
                time.sleep(delay)
                
            # 3. Dừng lại đọc kiểm tra từ khóa sau khi gõ xong
            print("      + Nhập từ khóa hoàn tất.")
            self.random_sleep(0.6, 1.2)
            
        except Exception as e:
            print(f"      [-] Lỗi khi gõ phím mô phỏng: {e}")
            # Fallback an toàn nếu có lỗi
            try:
                locator.fill(text)
            except:
                pass

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
                                
                            box = post.bounding_box()
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
                    box = target_post.bounding_box()
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
                                    btn_box = feed_upvote.bounding_box()
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
                    
                    title_box = target_post.bounding_box()
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
                                box = btn.bounding_box()
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
                print(f"      + Quyết định: Gõ trực tiếp lên thanh địa chỉ URL từ khóa '{query}'.")
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
                                box = post.bounding_box()
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
                    box = target_post.bounding_box()
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
                                box = btn.bounding_box()
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

        # Bản đồ các hành động cốt lõi (Không chứa YouTube)
        action_map = {
            "read_news": (self.action_read_news, 0.35),
            "search_google": (self.action_search_and_read_news, 0.25),
            "action_interact_reddit": (self.action_interact_reddit, 0.3),
            "action_search_weather": (self.action_search_weather, 0.1),
            "action_google_finance": (self.action_google_finance, 0.1),
        }

        # Loại bỏ 2 hành động "từ khóa ngẫu nhiên" (không liên quan chủ đề) nếu người dùng tick ô "Bỏ qua"
        if getattr(self, 'skip_random_keywords', False):
            action_map.pop("action_search_weather", None)
            action_map.pop("action_google_finance", None)
            print("      [!] Chế độ BỎ QUA TỪ KHÓA NGẪU NHIÊN đang bật. Sẽ không tra thời tiết/tài chính ngẫu nhiên.")

        # Chỉ bổ sung kịch bản YouTube vào lịch trình nếu người dùng KHÔNG tick ô "Bỏ qua"
        if getattr(self, 'skip_youtube', False) == False:
            action_map["watch_video"] = (self.action_watch_video, 0.40)
            action_map["action_search_youtube"] = (self.action_search_youtube, 0.60)
        else:
            print("      [!] Chế độ BỎ QUA YOUTUBE đang bật. Sẽ chỉ lướt web và đọc báo.")
        
        last_action_name = None 

        for i in range(total_actions):
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
            
            # 4. Thực thi
            action_function(page)
            
            self.random_sleep(5, 10)

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
        parts = time_str.split(":")
        if len(parts) == 2:
            return int(parts[0]) * 60 + int(parts[1])
        elif len(parts) == 3:
            return int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
        return 120

    def _watch_single_video_logic(self, page, videos_remaining_to_watch=1):
        """
        Hàm xử lý logic xem video liên hoàn:
        - Xem đủ % thời lượng.
        - Random Like.
        - Sub nếu > 70% (và được phép).
        - Nếu vẫn còn số lượng video trong chuỗi (videos_remaining_to_watch > 1), 
          sẽ tự động chọn video tiếp theo ở cột phải để xem tiếp.
        """
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
            
            print(f"      + Thời lượng thực: {total_seconds}s. Sẽ xem: {watch_percent*100:.1f}% (~{watch_seconds}s).")
            
            # 3. Tiến hành xem và lướt qua ad giữa video
            end_time = time.time() + watch_seconds
            while time.time() < end_time:
                self._check_and_skip_ad(page)
                self.random_sleep(4, 8)
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

            # 6. KIỂM TRA CHUỖI XEM LIÊN HOÀN (2-3 VIDEO)
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
            box = element.bounding_box()
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
        
        for selector in close_selectors:
            try:
                # Tìm xem có nút nào đang hiển thị trên màn hình không
                elements = page.locator(f"{selector}:visible").all()
                for el in elements:
                    print(f"      [+] Phát hiện popup quảng cáo chặn màn hình. Đang đóng...")
                    # Click tắt với timeout cực ngắn để không làm chậm bot
                    el.click(timeout=2000)
                    self.random_sleep(1, 2)
            except:
                pass # Bỏ qua nếu có lỗi không click được

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
    
    