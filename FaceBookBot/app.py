"""
=====================================================================
FACEBOOK AUTO SCHEDULER BOT - WITH DEFAULT DATA
=====================================================================
Đã điền sẵn 10 nhóm và 3 comment mặc định
Giới hạn tối đa: 25 nhóm
=====================================================================
"""

import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager
import time
import random
import threading
from datetime import datetime
import schedule
import queue


# =====================================================================
# DỮ LIỆU MẶC ĐỊNH
# =====================================================================

DEFAULT_GROUPS = [
    "https://www.facebook.com/groups/361061586498042/",
    "https://www.facebook.com/groups/506185624433677/",
    "https://www.facebook.com/groups/660923452103625/",
    "https://www.facebook.com/groups/195709665090056/",
    "https://www.facebook.com/groups/2012327815581790/",
    "https://www.facebook.com/groups/6874627039310237/",
    "https://www.facebook.com/groups/525175321925202/",
    "https://www.facebook.com/groups/timnhaphanphoidaily/",
    "https://www.facebook.com/groups/758873051432100/",
    "https://www.facebook.com/groups/725766802930483/",
    "https://www.facebook.com/groups/957808471691923/",
    "https://www.facebook.com/groups/820226839627977/",
    "https://www.facebook.com/groups/290855111880560/",
    "https://www.facebook.com/groups/681392726175453/",
    "https://www.facebook.com/groups/725766802930483/"
]

DEFAULT_COMMENTS = [
    "Nhận in Hộp giấy, tem nhãn, đáp ứng mọi số lượng. Miễn phí thiết kế. call 24/7: 0982.704.995",
    "Xưởng in, gia công Hộp giấy, tem nhãn, túi giấy mọi số lượng. Miễn phí thiết kế. call: 0982.704.995",
    "Xưởng in Hộp giấy, tem nhãn, túi giấy mọi số lượng. Miễn phí thiết kế. call 24/7: 0982.704.995"
]


# =====================================================================
# CLASS FACEBOOKBOT
# =====================================================================

class FacebookBot:
    def __init__(self, config, log_queue):
        self.config = config
        self.log_queue = log_queue
        self.driver = None
        self.wait = None
        self.is_logged_in = False
        self.should_stop = False

    def log(self, message, log_type='info'):
        try:
            timestamp = time.strftime("%H:%M:%S")
            self.log_queue.put({
                'timestamp': timestamp,
                'message': message,
                'type': log_type
            })
            print(f"[{timestamp}] {message}")
        except:
            pass

    def random_delay(self, min_sec, max_sec):
        time.sleep(random.uniform(min_sec, max_sec))

    def slow_type(self, element, text):
        for char in text:
            if self.should_stop:
                return
            element.send_keys(char)
            time.sleep(random.uniform(0.05, 0.15))

    def setup_driver(self):
        try:
            self.log("🔧 Đang khởi tạo Chrome driver...", 'info')

            chrome_options = Options()
            chrome_options.add_argument('--disable-blink-features=AutomationControlled')
            chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
            chrome_options.add_experimental_option('useAutomationExtension', False)
            chrome_options.add_argument('--disable-notifications')
            chrome_options.add_argument('--start-maximized')
            chrome_options.add_argument('--lang=vi')
            chrome_options.add_argument('--no-sandbox')
            chrome_options.add_argument('--disable-dev-shm-usage')

            service = Service(ChromeDriverManager().install())
            self.driver = webdriver.Chrome(service=service, options=chrome_options)
            self.wait = WebDriverWait(self.driver, 10)

            self.driver.execute_script(
                "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
            )

            self.log("✅ Chrome driver đã sẵn sàng!", 'success')
            return True

        except Exception as e:
            self.log(f"❌ Lỗi khởi tạo driver: {str(e)}", 'error')
            return False

    def login_facebook(self):
        if self.is_logged_in:
            self.log("✅ Đã đăng nhập từ trước", 'info')
            return True

        try:
            self.log("🔐 Đang đăng nhập Facebook...", 'step')
            self.driver.get("https://www.facebook.com")
            self.random_delay(3, 5)

            if self.should_stop:
                return False

            email_input = self.wait.until(EC.presence_of_element_located((By.ID, "email")))
            self.slow_type(email_input, self.config['email'])
            self.random_delay(1, 2)

            if self.should_stop:
                return False

            password_input = self.driver.find_element(By.ID, "pass")
            self.slow_type(password_input, self.config['password'])
            self.random_delay(1, 2)

            login_btn = self.driver.find_element(By.NAME, "login")
            login_btn.click()

            self.log("⏳ Đang chờ Facebook xử lý...", 'info')
            self.random_delay(8, 12)

            if self.should_stop:
                return False

            current_url = self.driver.current_url
            login_success = False

            if "login" not in current_url.lower():
                login_success = True

            try:
                self.driver.find_element(By.XPATH, "//input[@type='search']")
                login_success = True
            except:
                pass

            if "checkpoint" in current_url.lower():
                self.log("⚠️ Facebook yêu cầu xác minh! Có 60 giây...", 'warning')

                for i in range(60):
                    if self.should_stop:
                        return False
                    time.sleep(1)
                    new_url = self.driver.current_url
                    if "checkpoint" not in new_url.lower() and "login" not in new_url.lower():
                        self.log("✅ Đã xác minh thành công!", 'success')
                        login_success = True
                        break

            if login_success:
                self.log("✅ Đăng nhập thành công!", 'success')
                self.is_logged_in = True
                self.random_delay(2, 3)
                return True
            else:
                self.log("❌ Đăng nhập thất bại!", 'error')
                return False

        except Exception as e:
            self.log(f"❌ Lỗi đăng nhập: {str(e)}", 'error')
            return False

    def open_group_and_scroll(self, group_url, post_count=2):
        try:
            self.log(f"📂 Đang mở nhóm...", 'info')
            self.driver.get(group_url)
            self.random_delay(5, 7)

            if self.should_stop:
                return 0

            max_scrolls = 20
            target_forms = post_count

            for i in range(max_scrolls):
                if self.should_stop:
                    return 0

                current_forms = len(self.driver.find_elements(By.TAG_NAME, "form"))

                if current_forms >= target_forms:
                    self.log(f"✅ Đã load đủ {current_forms} form", 'success')
                    break

                self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                self.random_delay(2, 3)

                if (i + 1) % 5 == 0:
                    self.log(f"   📊 Scroll lần {i+1}, có {current_forms} form", 'info')

            self.driver.execute_script("window.scrollTo(0, 0);")
            self.random_delay(1, 2)
            self.driver.execute_script("window.scrollTo(0, 300);")
            self.random_delay(1, 2)

            final_forms = len(self.driver.find_elements(By.TAG_NAME, "form"))
            self.log(f"✅ Load được {final_forms} bài để thử comment", 'success')
            return final_forms

        except Exception as e:
            self.log(f"❌ Lỗi mở nhóm: {str(e)}", 'error')
            return 0

    def find_and_click_comment_area(self, post_index):
        try:
            forms = self.driver.find_elements(By.TAG_NAME, "form")
            if post_index >= len(forms):
                return None

            form = forms[post_index]
            self.driver.execute_script(
                "arguments[0].scrollIntoView({behavior: 'smooth', block: 'center'});", form
            )
            self.random_delay(1.5, 2)

            click_selectors = [
                (By.XPATH, ".//div[contains(@aria-label, 'Write a comment')]"),
                (By.XPATH, ".//div[contains(@aria-label, 'Viết bình luận')]"),
            ]

            for by, selector in click_selectors:
                try:
                    element = form.find_element(by, selector)
                    if element.is_displayed():
                        self.driver.execute_script("arguments[0].click();", element)
                        self.random_delay(1, 1.5)
                        return form
                except:
                    continue

            self.driver.execute_script("arguments[0].click();", form)
            self.random_delay(1, 1.5)
            return form

        except:
            return None

    def find_comment_box(self, post_index):
        try:
            forms = self.driver.find_elements(By.TAG_NAME, "form")
            if post_index >= len(forms):
                return None

            form = forms[post_index]

            selectors = [
                (By.XPATH, ".//p[@contenteditable='true']"),
                (By.XPATH, ".//div[@contenteditable='true' and @role='textbox']"),
            ]

            for by, selector in selectors:
                try:
                    element = form.find_element(by, selector)
                    if element.is_displayed() and element.is_enabled():
                        return element
                except:
                    continue
            return None

        except:
            return None

    def comment_on_group(self, group_url, post_count=2):
        try:
            available_posts = self.open_group_and_scroll(group_url, post_count * 2)
            if available_posts == 0:
                self.log("⚠️ Không tìm thấy bài viết", 'warning')
                return 0

            comments = self.config['comments']
            delay_minutes = self.config['delayMinutes']
            success_count = 0
            post_index = 0
            comment_index = 0

            while success_count < post_count and post_index < available_posts:
                if self.should_stop:
                    break

                comment_text = comments[comment_index % len(comments)]
                self.log(f"📝 Thử bài {post_index+1} (đã comment: {success_count}/{post_count}): {comment_text[:30]}...", 'info')

                form = self.find_and_click_comment_area(post_index)
                if not form:
                    self.log(f"⚠️ Không thể click bài {post_index+1}, chuyển bài tiếp...", 'warning')
                    post_index += 1
                    continue

                comment_box = self.find_comment_box(post_index)
                if not comment_box:
                    self.log(f"⚠️ Không tìm thấy ô comment bài {post_index+1}, chuyển bài tiếp...", 'warning')
                    post_index += 1
                    continue

                try:
                    self.slow_type(comment_box, comment_text)
                    self.random_delay(1, 2)

                    if self.should_stop:
                        break

                    comment_box = self.find_comment_box(post_index)
                    if comment_box:
                        comment_box.send_keys(Keys.RETURN)
                        self.random_delay(2, 3)
                        success_count += 1
                        comment_index += 1
                        self.log(f"✅ Đã comment bài {post_index+1} - Tổng: {success_count}/{post_count}", 'success')

                        if success_count < post_count and not self.should_stop:
                            self.log(f"⏱️ Chờ {delay_minutes} phút trước bài tiếp...", 'info')
                            for _ in range(delay_minutes * 60):
                                if self.should_stop:
                                    break
                                time.sleep(1)
                    else:
                        self.log(f"⚠️ Mất ô comment sau khi gõ, chuyển bài tiếp...", 'warning')

                except Exception as e:
                    self.log(f"⚠️ Lỗi comment bài {post_index+1}, chuyển bài tiếp...", 'warning')

                post_index += 1

            if success_count > 0:
                self.log(f"📊 Kết quả: {success_count}/{post_count} bài thành công", 'success')
            else:
                self.log(f"⚠️ Không comment được bài nào trong nhóm này", 'warning')

            return success_count

        except Exception as e:
            self.log(f"❌ Lỗi comment nhóm: {str(e)}", 'error')
            return 0

    def run_session(self, session_name):
        try:
            self.log(f"{'='*50}", 'step')
            self.log(f"🎯 BẮT ĐẦU PHIÊN {session_name.upper()}", 'step')
            self.log(f"{'='*50}", 'step')

            groups = self.config['groups']
            group_delay = self.config['groupDelayMinutes']
            total_success = 0

            for idx, group_url in enumerate(groups):
                if self.should_stop:
                    break

                self.log(f"\n📍 Nhóm {idx+1}/{len(groups)}", 'step')

                success = self.comment_on_group(group_url, post_count=2)
                total_success += success

                if idx < len(groups) - 1 and not self.should_stop:
                    self.log(f"⏱️ Chờ {group_delay} phút trước nhóm tiếp...", 'info')
                    for _ in range(group_delay * 60):
                        if self.should_stop:
                            break
                        time.sleep(1)

            self.log(f"\n{'='*50}", 'success')
            self.log(f"✅ HOÀN THÀNH {session_name.upper()}", 'success')
            self.log(f"   → Thành công: {total_success} bài", 'success')
            self.log(f"{'='*50}", 'success')

        except Exception as e:
            self.log(f"❌ Lỗi: {str(e)}", 'error')

    def cleanup(self):
        try:
            if self.driver:
                self.driver.quit()
        except:
            pass


# =====================================================================
# CLASS GUI - VỚI DỮ LIỆU MẶC ĐỊNH
# =====================================================================

class FacebookSchedulerApp:
    def __init__(self, root):
        self.root = root
        self.root.title("🤖 Facebook Auto Scheduler Bot")
        self.root.geometry("1050x750")
        self.root.resizable(False, False)

        self.bot_running = False
        self.scheduler_running = False
        self.bot_instance = None
        self.log_queue = queue.Queue()

        self.setup_ui()
        self.process_log_queue()
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)

    def setup_ui(self):
        style = ttk.Style()
        style.theme_use('clam')

        main_canvas = tk.Canvas(self.root)
        main_scrollbar = ttk.Scrollbar(self.root, orient="vertical", command=main_canvas.yview)
        main_frame = ttk.Frame(main_canvas, padding="10")

        main_canvas.create_window((0, 0), window=main_frame, anchor="nw")
        main_canvas.configure(yscrollcommand=main_scrollbar.set)

        main_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        main_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        # HEADER
        header = ttk.Frame(main_frame)
        header.grid(row=0, column=0, columnspan=2, pady=(0, 10), sticky='ew')

        ttk.Label(header, text="🤖 Facebook Auto Scheduler Bot",
                 font=("Arial", 16, "bold"), foreground="#667eea").pack()
        ttk.Label(header, text="Tự động comment - Sáng & Chiều (Đã điền sẵn dữ liệu mặc định)",
                 font=("Arial", 9), foreground="#666").pack()

        # INFO
        info = ttk.LabelFrame(main_frame, text="📅 Lịch trình", padding="8")
        info.grid(row=1, column=0, columnspan=2, sticky='ew', pady=(0, 10))

        ttk.Label(info, text="• Sáng: 2 bài/nhóm | Chiều: 2 bài/nhóm | Đã điền sẵn 10 nhóm + 3 comment | Tối đa 25 nhóm",
                 foreground="#333").pack()

        # LEFT
        left = ttk.Frame(main_frame)
        left.grid(row=2, column=0, sticky='nsew', padx=(0, 5))

        # Email
        ttk.Label(left, text="📧 Email/SĐT:", font=("Arial", 9, "bold")).pack(anchor='w')
        self.email_var = tk.StringVar()
        ttk.Entry(left, textvariable=self.email_var, width=40).pack(anchor='w', pady=(2, 8))

        # Password
        ttk.Label(left, text="🔐 Mật khẩu:", font=("Arial", 9, "bold")).pack(anchor='w')
        self.password_var = tk.StringVar()
        ttk.Entry(left, textvariable=self.password_var, show="*", width=40).pack(anchor='w', pady=(2, 8))

        # Time
        time_f = ttk.LabelFrame(left, text="⏰ Thời gian", padding="8")
        time_f.pack(fill='x', pady=(0, 8))

        t1 = ttk.Frame(time_f)
        t1.pack(fill='x')
        ttk.Label(t1, text="Sáng:").pack(side='left')
        self.morning_var = tk.StringVar(value="08:00")
        ttk.Entry(t1, textvariable=self.morning_var, width=10).pack(side='left', padx=5)

        t2 = ttk.Frame(time_f)
        t2.pack(fill='x', pady=(5, 0))
        ttk.Label(t2, text="Chiều:").pack(side='left')
        self.afternoon_var = tk.StringVar(value="14:00")
        ttk.Entry(t2, textvariable=self.afternoon_var, width=10).pack(side='left', padx=5)

        # Groups
        grp_f = ttk.LabelFrame(left, text="🔗 Nhóm (Đã điền sẵn 10 nhóm, tối đa 25 nhóm)", padding="8")
        grp_f.pack(fill='both', expand=True, pady=(0, 8))

        grp_canvas = tk.Canvas(grp_f, height=100, bg="white")
        grp_scroll = ttk.Scrollbar(grp_f, orient="vertical", command=grp_canvas.yview)
        self.groups_inner = ttk.Frame(grp_canvas)

        grp_canvas.create_window((0, 0), window=self.groups_inner, anchor="nw")
        grp_canvas.configure(yscrollcommand=grp_scroll.set)

        grp_canvas.pack(side='left', fill='both', expand=True)
        grp_scroll.pack(side='right', fill='y')

        self.group_entries = []

        # ĐIỀN SẴN 10 NHÓM MẶC ĐỊNH
        for i, default_group in enumerate(DEFAULT_GROUPS):
            self.add_group_entry(default_value=default_group)

        grp_btn = ttk.Frame(grp_f)
        grp_btn.pack(fill='x', pady=(5, 0))
        ttk.Button(grp_btn, text="➕", command=lambda: self.add_group_entry(), width=5).pack(side='left', padx=(0, 3))
        ttk.Button(grp_btn, text="➖", command=self.remove_group_entry, width=5).pack(side='left')

        self.groups_inner.bind("<Configure>", lambda e: grp_canvas.configure(scrollregion=grp_canvas.bbox("all")))

        # Comments
        cmt_f = ttk.LabelFrame(left, text="💬 Comment (Đã điền sẵn 3 comment)", padding="8")
        cmt_f.pack(fill='both', expand=True, pady=(0, 8))

        cmt_canvas = tk.Canvas(cmt_f, height=100, bg="white")
        cmt_scroll = ttk.Scrollbar(cmt_f, orient="vertical", command=cmt_canvas.yview)
        self.comments_inner = ttk.Frame(cmt_canvas)

        cmt_canvas.create_window((0, 0), window=self.comments_inner, anchor="nw")
        cmt_canvas.configure(yscrollcommand=cmt_scroll.set)

        cmt_canvas.pack(side='left', fill='both', expand=True)
        cmt_scroll.pack(side='right', fill='y')

        self.comment_entries = []

        # ĐIỀN SẴN 3 COMMENT MẶC ĐỊNH
        for i, default_comment in enumerate(DEFAULT_COMMENTS):
            self.add_comment_entry(default_value=default_comment)

        cmt_btn = ttk.Frame(cmt_f)
        cmt_btn.pack(fill='x', pady=(5, 0))
        ttk.Button(cmt_btn, text="➕", command=lambda: self.add_comment_entry(), width=5).pack(side='left', padx=(0, 3))
        ttk.Button(cmt_btn, text="➖", command=self.remove_comment_entry, width=5).pack(side='left')

        self.comments_inner.bind("<Configure>", lambda e: cmt_canvas.configure(scrollregion=cmt_canvas.bbox("all")))

        # Delay
        delay_f = ttk.Frame(left)
        delay_f.pack(fill='x', pady=(0, 8))

        ttk.Label(delay_f, text="⏱️ Delay bài:").pack(side='left')
        self.delay_var = tk.StringVar(value="2")
        ttk.Entry(delay_f, textvariable=self.delay_var, width=5).pack(side='left', padx=3)

        ttk.Label(delay_f, text="phút  |  Delay nhóm:").pack(side='left', padx=(5, 0))
        self.group_delay_var = tk.StringVar(value="5")
        ttk.Entry(delay_f, textvariable=self.group_delay_var, width=5).pack(side='left', padx=3)
        ttk.Label(delay_f, text="phút").pack(side='left')

        # BUTTONS
        btn_f = ttk.Frame(left)
        btn_f.pack(fill='x', pady=(10, 0))

        self.start_btn = ttk.Button(btn_f, text="🚀 BẮT ĐẦU", command=self.start_scheduler)
        self.start_btn.pack(side='left', fill='x', expand=True, padx=(0, 3))

        self.stop_btn = ttk.Button(btn_f, text="⏹️ DỪNG", command=self.stop_scheduler, state='disabled')
        self.stop_btn.pack(side='left', fill='x', expand=True)

        # RIGHT
        right = ttk.Frame(main_frame)
        right.grid(row=2, column=1, sticky='nsew', padx=(5, 0))

        # Status
        stat = ttk.LabelFrame(right, text="📊 Trạng thái", padding="8")
        stat.pack(fill='x', pady=(0, 8))

        s1 = ttk.Frame(stat)
        s1.pack(fill='x')
        ttk.Label(s1, text="Trạng thái:", font=("Arial", 9, "bold")).pack(side='left')
        self.status_label = ttk.Label(s1, text="Chờ", foreground="#ff4444")
        self.status_label.pack(side='left', padx=(10, 0))

        s2 = ttk.Frame(stat)
        s2.pack(fill='x', pady=(3, 0))
        ttk.Label(s2, text="Phiên tiếp:", font=("Arial", 9, "bold")).pack(side='left')
        self.next_session_label = ttk.Label(s2, text="-")
        self.next_session_label.pack(side='left', padx=(10, 0))

        s3 = ttk.Frame(stat)
        s3.pack(fill='x', pady=(3, 0))
        ttk.Label(s3, text="Tổng nhóm:", font=("Arial", 9, "bold")).pack(side='left')
        self.total_groups_label = ttk.Label(s3, text="10")  # Hiển thị 10 nhóm mặc định
        self.total_groups_label.pack(side='left', padx=(10, 0))

        # Log
        log_f = ttk.LabelFrame(right, text="📋 Nhật ký", padding="8")
        log_f.pack(fill='both', expand=True)

        self.log_text = scrolledtext.ScrolledText(
            log_f, width=48, height=28,
            bg="#1e1e1e", fg="#00ff00",
            font=("Courier New", 8), wrap='word'
        )
        self.log_text.pack(fill='both', expand=True)

        self.log_text.tag_config("info", foreground="#00bfff")
        self.log_text.tag_config("success", foreground="#00ff00")
        self.log_text.tag_config("warning", foreground="#ffa500")
        self.log_text.tag_config("error", foreground="#ff4444")
        self.log_text.tag_config("step", foreground="#ffff00")

        main_frame.update_idletasks()
        main_canvas.configure(scrollregion=main_canvas.bbox("all"))

    def add_group_entry(self, default_value=""):
        if len(self.group_entries) >= 25:
            messagebox.showwarning("Cảnh báo", "Tối đa 25 nhóm!")
            return

        f = ttk.Frame(self.groups_inner)
        f.pack(fill='x', pady=1)

        ttk.Label(f, text=f"{len(self.group_entries)+1}.", width=2).pack(side='left')
        e = ttk.Entry(f, width=32)
        e.pack(side='left', fill='x', expand=True)

        # Điền giá trị mặc định nếu có
        if default_value:
            e.insert(0, default_value)

        self.group_entries.append(e)

    def remove_group_entry(self):
        if len(self.group_entries) <= 1:
            messagebox.showwarning("Cảnh báo", "Cần ít nhất 1 nhóm!")
            return
        self.group_entries.pop().master.destroy()

    def add_comment_entry(self, default_value=""):
        if len(self.comment_entries) >= 20:
            messagebox.showwarning("Cảnh báo", "Tối đa 20 comment!")
            return

        f = ttk.Frame(self.comments_inner)
        f.pack(fill='x', pady=1)

        ttk.Label(f, text=f"{len(self.comment_entries)+1}.", width=2).pack(side='left', anchor='n')
        t = tk.Text(f, width=28, height=2, wrap='word')
        t.pack(side='left', fill='x', expand=True)

        # Điền giá trị mặc định nếu có
        if default_value:
            t.insert('1.0', default_value)

        self.comment_entries.append(t)

    def remove_comment_entry(self):
        if len(self.comment_entries) <= 1:
            messagebox.showwarning("Cảnh báo", "Cần ít nhất 1 comment!")
            return
        self.comment_entries.pop().master.destroy()

    def add_log(self, log_data):
        ts = log_data.get('timestamp', '')
        msg = log_data.get('message', '')
        typ = log_data.get('type', 'info')

        self.log_text.insert('end', f"[{ts}] {msg}\n", typ)
        self.log_text.see('end')

    def process_log_queue(self):
        try:
            while True:
                self.add_log(self.log_queue.get_nowait())
        except queue.Empty:
            pass
        self.root.after(100, self.process_log_queue)

    def validate_inputs(self):
        if not self.email_var.get().strip():
            messagebox.showerror("Lỗi", "Nhập Email/SĐT!")
            return False
        if not self.password_var.get().strip():
            messagebox.showerror("Lỗi", "Nhập mật khẩu!")
            return False

        groups = [e.get().strip() for e in self.group_entries if e.get().strip()]
        if not groups:
            messagebox.showerror("Lỗi", "Nhập ít nhất 1 nhóm!")
            return False

        comments = [t.get("1.0", 'end').strip() for t in self.comment_entries if t.get("1.0", 'end').strip()]
        if not comments:
            messagebox.showerror("Lỗi", "Nhập ít nhất 1 comment!")
            return False

        try:
            int(self.delay_var.get())
            int(self.group_delay_var.get())
        except:
            messagebox.showerror("Lỗi", "Delay phải là số!")
            return False

        return True

    def start_scheduler(self):
        if not self.validate_inputs():
            return

        groups = [e.get().strip() for e in self.group_entries if e.get().strip()]
        comments = [t.get("1.0", 'end').strip() for t in self.comment_entries if t.get("1.0", 'end').strip()]

        config = {
            'email': self.email_var.get().strip(),
            'password': self.password_var.get().strip(),
            'groups': groups,
            'comments': comments,
            'morningTime': self.morning_var.get().strip(),
            'afternoonTime': self.afternoon_var.get().strip(),
            'delayMinutes': int(self.delay_var.get()),
            'groupDelayMinutes': int(self.group_delay_var.get())
        }

        self.start_btn.config(state='disabled')
        self.stop_btn.config(state='normal')
        self.status_label.config(text="Đang chạy", foreground="#00ff00")
        self.total_groups_label.config(text=str(len(groups)))

        self.bot_running = True
        threading.Thread(target=self.run_scheduler, args=(config,), daemon=True).start()

    def stop_scheduler(self):
        if messagebox.askyesno("Xác nhận", "Dừng bot?"):
            self.bot_running = False
            self.scheduler_running = False

            if self.bot_instance:
                self.bot_instance.should_stop = True

            schedule.clear()

            self.start_btn.config(state='normal')
            self.stop_btn.config(state='disabled')
            self.status_label.config(text="Đã dừng", foreground="#ff4444")

            self.log_queue.put({
                'timestamp': time.strftime("%H:%M:%S"),
                'message': '⏹️ Đã dừng',
                'type': 'warning'
            })

    def run_scheduler(self, config):
        self.scheduler_running = True
        self.bot_instance = FacebookBot(config, self.log_queue)

        if not self.bot_instance.setup_driver():
            self.scheduler_running = False
            self.root.after(0, self.reset_ui)
            return

        if not self.bot_instance.login_facebook():
            self.scheduler_running = False
            self.bot_instance.cleanup()
            self.root.after(0, self.reset_ui)
            return

        morning = config['morningTime']
        afternoon = config['afternoonTime']

        def morning_job():
            if self.bot_running and not self.bot_instance.should_stop:
                self.bot_instance.run_session("Buổi sáng")

        def afternoon_job():
            if self.bot_running and not self.bot_instance.should_stop:
                self.bot_instance.run_session("Buổi chiều")

        schedule.every().day.at(morning).do(morning_job)
        schedule.every().day.at(afternoon).do(afternoon_job)

        self.bot_instance.log(f"📅 Lịch: Sáng {morning} | Chiều {afternoon}", 'info')

        self.root.after(0, lambda: self.update_next_session(config))

        while self.bot_running and self.scheduler_running:
            schedule.run_pending()
            time.sleep(1)

        self.bot_instance.log("🛑 Đã dừng", 'warning')
        self.bot_instance.cleanup()

    def update_next_session(self, config):
        try:
            now = datetime.now()
            morning = datetime.strptime(config['morningTime'], "%H:%M").replace(
                year=now.year, month=now.month, day=now.day
            )
            afternoon = datetime.strptime(config['afternoonTime'], "%H:%M").replace(
                year=now.year, month=now.month, day=now.day
            )

            if now.time() < morning.time():
                txt = f"Sáng {config['morningTime']}"
            elif now.time() < afternoon.time():
                txt = f"Chiều {config['afternoonTime']}"
            else:
                txt = f"Sáng {config['morningTime']} (mai)"

            self.next_session_label.config(text=txt)
        except:
            pass

    def reset_ui(self):
        self.start_btn.config(state='normal')
        self.stop_btn.config(state='disabled')
        self.status_label.config(text="Lỗi", foreground="#ff4444")

    def on_closing(self):
        if self.bot_running:
            if messagebox.askokcancel("Thoát", "Bot đang chạy. Thoát?"):
                self.bot_running = False
                if self.bot_instance:
                    self.bot_instance.should_stop = True
                    self.bot_instance.cleanup()
                self.root.destroy()
        else:
            self.root.destroy()


# =====================================================================
# MAIN
# =====================================================================

def main():
    print("="*60)
    print("🤖 FACEBOOK AUTO SCHEDULER BOT")
    print("="*60)
    print("✅ Đã khởi động!")
    print("📝 Đã điền sẵn 10 nhóm + 3 comment mặc định")
    print("📊 Giới hạn tối đa: 25 nhóm")
    print("="*60)

    root = tk.Tk()
    app = FacebookSchedulerApp(root)
    root.mainloop()


if __name__ == '__main__':
    main()