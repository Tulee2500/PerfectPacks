"""
=====================================================================
FACEBOOK AUTO SCHEDULER BOT v4.0
=====================================================================
✅ ĐĂNG BÀI: Text + Nhiều ảnh (tùy số lượng)
✅ COMMENT: Text + 1 ảnh đính kèm
✅ Tab riêng: Nhóm đăng bài | Nhóm comment
✅ Logic: Đăng hết bài tất cả nhóm → mới comment
✅ Lưu/Load danh sách nhóm (JSON)
✅ Xuống dòng bằng ký tự | trong text
✅ Retry tự động khi thất bại (3 lần)
✅ Lịch tự động Sáng & Chiều
✅ Tối đa 25 nhóm mỗi tab, 20 comment, 10 nội dung bài đăng
=====================================================================
"""

import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox, filedialog
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.action_chains import ActionChains
from webdriver_manager.chrome import ChromeDriverManager
import time
import random
import threading
from datetime import datetime
import schedule
import queue
import os
import json
import pyperclip

# =====================================================================
# DỮ LIỆU MẶC ĐỊNH
# =====================================================================
DEFAULT_POST_GROUPS = [
    "https://www.facebook.com/groups/361061586498042/",
    "https://www.facebook.com/groups/506185624433677/",
    "https://www.facebook.com/groups/660923452103625/",
    "https://www.facebook.com/groups/195709665090056/",
    "https://www.facebook.com/groups/2012327815581790/",
    "https://www.facebook.com/groups/6874627039310237/",
    "https://www.facebook.com/groups/525175321925202/",
    "https://www.facebook.com/groups/timnhaphanphoidaily/",
]

DEFAULT_COMMENT_GROUPS = [
    "https://www.facebook.com/groups/758873051432100/",
    "https://www.facebook.com/groups/725766802930483/",
    "https://www.facebook.com/groups/957808471691923/",
    "https://www.facebook.com/groups/820226839627977/",
    "https://www.facebook.com/groups/290855111880560/",
    "https://www.facebook.com/groups/681392726175453/",
    "https://www.facebook.com/groups/158721900459265/",
    "https://www.facebook.com/groups/3227331463945627/",
]

DEFAULT_POST_CONTENTS = [
    """ Xưởng Tại Hà nội
        📦 Chuyên sản xuất trực tiếp: Tem nhãn, Vỏ hộp, Túi giấy, Túi phức hợp (túi zip,  màng ghép...). 

        🔥 Đặc quyền cho khách hàng: 
        ✅ Nhận in SỐ LƯỢNG ÍT - Hỗ trợ shop nhỏ, không lo đọng vốn!     
        ✅ MIỄN PHÍ THIẾT KẾ 100% - Chỉnh sửa đến khi ưng ý. 
        ✅ GIAO HÀNG TOÀN QUỐC tận nơi.
        Bao bì xịn - Chốt đơn mịn! Cần tư vấn cứ ném ngay ý tưởng vào Inbox hoặc liên hệ: 
        👉 Fanpage: Bao Bì Trọn Gói 
        ☎️ Hotline/Zalo: 0982 704 995
    """
]

DEFAULT_COMMENTS = [
    "Nhận in Hộp giấy, tem nhãn, đáp ứng mọi số lượng. Miễn phí thiết kế. call 24/7: 0982.704.995",
    "Xưởng in, gia công Hộp giấy, tem nhãn, túi giấy mọi số lượng. Miễn phí thiết kế. call: 0982.704.995",
    "Xưởng in Hộp giấy, tem nhãn, túi giấy mọi số lượng. Miễn phí thiết kế. call 24/7: 0982.704.995"
]

SAVE_FILE = "bot_groups.json"


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

    # ── LOGGING ──────────────────────────────────────────────────────

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

    # ── UTILS ─────────────────────────────────────────────────────────

    def random_delay(self, min_sec, max_sec):
        time.sleep(random.uniform(min_sec, max_sec))

    def slow_type(self, element, text):
        for char in text:
            if self.should_stop:
                return
            element.send_keys(char)
            time.sleep(random.uniform(0.05, 0.15))

    def type_multiline(self, element, text):
        """
        Nhập text vào element có hỗ trợ xuống dòng.
        Dùng ký tự | để xuống dòng.
        Chiến lược: paste từ clipboard (nhanh + giữ newline).
        Fallback: gõ từng ký tự nếu clipboard thất bại.
        """
        final_text = text.replace('|', '\n')

        # Xóa nội dung cũ
        element.send_keys(Keys.CONTROL + 'a')
        time.sleep(0.2)
        element.send_keys(Keys.DELETE)
        time.sleep(0.2)

        try:
            pyperclip.copy(final_text)
            time.sleep(0.2)
            self.driver.execute_script("arguments[0].click();", element)
            time.sleep(0.3)
            ActionChains(self.driver).key_down(Keys.CONTROL).send_keys('v').key_up(Keys.CONTROL).perform()
            time.sleep(0.8)

            current = self.driver.execute_script(
                "return arguments[0].innerText || arguments[0].textContent || '';",
                element
            )
            if current and current.strip():
                self.log(f"   ✅ Paste thành công: {current[:40].replace(chr(10),' ')}...", 'info')
                return
        except Exception as e:
            self.log(f"   ⚠️ Clipboard lỗi: {str(e)[:60]}, fallback gõ tay...", 'warning')

        # Fallback: gõ từng ký tự (không xuống dòng)
        fallback = text.replace('|', ' ')
        self.driver.execute_script("arguments[0].click();", element)
        time.sleep(0.3)
        for char in fallback:
            if self.should_stop:
                return
            element.send_keys(char)
            time.sleep(0.04)

    # ── SETUP DRIVER ──────────────────────────────────────────────────

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

            self.log("✅ Chrome driver sẵn sàng!", 'success')
            return True

        except Exception as e:
            self.log(f"❌ Lỗi khởi tạo driver: {str(e)}", 'error')
            return False

    # ── LOGIN ─────────────────────────────────────────────────────────

    def login_facebook(self):
        if self.is_logged_in:
            self.log("✅ Đã đăng nhập từ trước", 'info')
            return True

        try:
            self.log("🔐 Đang đăng nhập Facebook...", 'step')
            self.driver.get("https://www.facebook.com")
            self.random_delay(5, 8)

            if self.should_stop:
                return False

            email_input = None
            for by, sel in [
                (By.ID, "email"),
                (By.NAME, "email"),
                (By.XPATH, "//input[@type='email']"),
            ]:
                try:
                    email_input = WebDriverWait(self.driver, 10).until(
                        EC.element_to_be_clickable((by, sel))
                    )
                    break
                except:
                    continue

            if not email_input:
                self.log("❌ Không tìm thấy ô email!", 'error')
                return False

            self.driver.execute_script("arguments[0].click();", email_input)
            self.random_delay(0.5, 1)
            email_input.clear()
            self.slow_type(email_input, self.config['email'])
            self.random_delay(1, 2)

            password_input = None
            for by, sel in [
                (By.ID, "pass"),
                (By.NAME, "pass"),
                (By.XPATH, "//input[@type='password']"),
            ]:
                try:
                    password_input = self.driver.find_element(by, sel)
                    break
                except:
                    continue

            if not password_input:
                self.log("❌ Không tìm thấy ô mật khẩu!", 'error')
                return False

            self.driver.execute_script("arguments[0].click();", password_input)
            self.random_delay(0.5, 1)
            password_input.clear()
            self.slow_type(password_input, self.config['password'])
            self.random_delay(1, 2)
            password_input.send_keys(Keys.RETURN)

            self.log("⏳ Chờ Facebook xử lý...", 'info')
            self.random_delay(10, 15)

            if self.should_stop:
                return False

            current_url = self.driver.current_url
            login_success = "login" not in current_url.lower()

            if "checkpoint" in current_url.lower():
                self.log("⚠️ Facebook yêu cầu xác minh! Có 60 giây...", 'warning')
                for _ in range(60):
                    if self.should_stop:
                        return False
                    time.sleep(1)
                    new_url = self.driver.current_url
                    if "checkpoint" not in new_url.lower() and "login" not in new_url.lower():
                        self.log("✅ Xác minh thành công!", 'success')
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

    # ── ĐĂNG BÀI ─────────────────────────────────────────────────────

    def post_to_group(self, group_url, post_text, post_images=None):
        """
        Đăng bài lên nhóm: text + nhiều ảnh tùy ý.
        GIỮ NGUYÊN logic gốc, không thay đổi.
        """
        if post_images is None:
            post_images = []

        valid_images = [p for p in post_images if p and os.path.exists(p)]
        img_count = len(valid_images)

        try:
            self.log(f"📝 Đăng bài {'+ ' + str(img_count) + ' ảnh' if img_count else '(text only)'}...", 'step')
            self.driver.get(group_url)
            self.random_delay(5, 8)

            if self.should_stop:
                return False

            # ── BƯỚC 1: Click ô "Viết gì đó..." ──────────────────────
            self.log("🔍 Tìm ô soạn bài...", 'info')

            write_box = None
            for by, sel in [
                (By.XPATH, "//div[@aria-label='Viết gì đó...']"),
                (By.XPATH, "//div[@aria-label='Write something...']"),
                (By.XPATH, "//div[@aria-label='Bạn đang nghĩ gì?']"),
                (By.XPATH, "//div[@aria-label=\"What's on your mind?\"]"),
                (By.XPATH, "//span[contains(text(),'Viết gì đó')]"),
                (By.XPATH, "//span[contains(text(),'Write something')]"),
                (By.XPATH, "//div[contains(@class,'x1i10hfl') and @role='button']//span[contains(text(),'gì')]"),
            ]:
                try:
                    write_box = WebDriverWait(self.driver, 8).until(
                        EC.element_to_be_clickable((by, sel))
                    )
                    if write_box:
                        self.log("✅ Tìm thấy ô soạn bài", 'success')
                        break
                except:
                    continue

            if not write_box:
                self.log("❌ Không tìm thấy ô soạn bài!", 'error')
                return False

            self.driver.execute_script(
                "arguments[0].scrollIntoView({behavior:'smooth', block:'center'});",
                write_box
            )
            self.random_delay(1, 1.5)
            self.driver.execute_script("arguments[0].click();", write_box)
            self.random_delay(2, 3)

            # ── BƯỚC 2: Tìm textarea trong modal ─────────────────────
            self.log("🔍 Tìm textarea trong modal...", 'info')

            textarea = None
            for by, sel in [
                (By.XPATH, "//div[@role='dialog']//div[@contenteditable='true'][@role='textbox']"),
                (By.XPATH, "//div[@role='dialog']//p[@data-lexical-editor='true']"),
                (By.XPATH, "//div[@role='dialog']//div[@data-lexical-editor='true']"),
                (By.XPATH, "//div[@role='dialog']//p[@contenteditable='true']"),
                (By.XPATH, "//div[@contenteditable='true'][@aria-label='Bạn đang nghĩ gì?']"),
                (By.XPATH, "//div[@contenteditable='true'][@aria-label=\"What's on your mind?\"]"),
            ]:
                try:
                    textarea = WebDriverWait(self.driver, 8).until(
                        EC.element_to_be_clickable((by, sel))
                    )
                    if textarea:
                        self.log("✅ Tìm thấy textarea", 'success')
                        break
                except:
                    continue

            if not textarea:
                self.log("❌ Không tìm thấy textarea!", 'error')
                return False

            # ── BƯỚC 3: Nhập nội dung ─────────────────────────────────
            self.driver.execute_script("arguments[0].click();", textarea)
            self.random_delay(0.5, 1)
            self.log("✍️ Nhập nội dung bài...", 'info')
            self.type_multiline(textarea, post_text)
            self.random_delay(1.5, 2.5)

            box_content = self.driver.execute_script(
                "return arguments[0].innerText || arguments[0].textContent || '';",
                textarea
            )
            if not box_content.strip():
                self.log("⚠️ Textarea trống, thử lại...", 'warning')
                self.driver.execute_script("arguments[0].click();", textarea)
                self.random_delay(0.5, 1)
                self.type_multiline(textarea, post_text)
                self.random_delay(1.5, 2)

            # ── BƯỚC 4: Upload ảnh (nếu có) ──────────────────────────
            if valid_images:
                self.log(f"🖼️ Upload {img_count} ảnh...", 'info')
                uploaded = self._upload_post_images(valid_images)
                if uploaded:
                    self.log(f"✅ Upload {img_count} ảnh thành công", 'success')
                    self.random_delay(3, 5)
                else:
                    self.log("⚠️ Upload ảnh thất bại, đăng text thôi", 'warning')

            # ── BƯỚC 5: Click nút Đăng ───────────────────────────────
            self.log("🔍 Tìm nút Đăng...", 'info')

            post_btn = None
            for by, sel in [
                (By.XPATH, "//div[@role='dialog']//div[@aria-label='Post']"),
                (By.XPATH, "//div[@role='dialog']//div[@aria-label='Đăng']"),
                (By.XPATH, "//div[@role='dialog']//div[@role='button'][.//span[text()='Post']]"),
                (By.XPATH, "//div[@role='dialog']//div[@role='button'][.//span[text()='Đăng']]"),
                (By.XPATH, "//div[@role='dialog']//span[text()='Post']/ancestor::div[@role='button']"),
                (By.XPATH, "//div[@role='dialog']//span[text()='Đăng']/ancestor::div[@role='button']"),
            ]:
                try:
                    post_btn = WebDriverWait(self.driver, 8).until(
                        EC.element_to_be_clickable((by, sel))
                    )
                    if post_btn:
                        self.log("✅ Tìm thấy nút Đăng", 'success')
                        break
                except:
                    continue

            if not post_btn:
                self.log("❌ Không tìm thấy nút Đăng!", 'error')
                return False

            self.driver.execute_script("arguments[0].click();", post_btn)
            self.log("⏳ Chờ bài đăng xử lý...", 'info')
            self.random_delay(5, 8)

            try:
                WebDriverWait(self.driver, 8).until(
                    EC.invisibility_of_element_located((By.XPATH, "//div[@role='dialog']"))
                )
                self.log("✅ Đăng bài thành công!", 'success')
            except:
                self.log("⚠️ Không xác nhận modal đóng, tiếp tục...", 'warning')

            return True

        except Exception as e:
            self.log(f"❌ Lỗi đăng bài: {str(e)}", 'error')
            return False

    def _upload_post_images(self, image_paths):
        try:
            file_input = None

            for by, sel in [
                (By.XPATH, "//div[@role='dialog']//input[@type='file']"),
                (By.XPATH, "//input[@type='file' and contains(@accept,'image')]"),
                (By.XPATH, "//input[@type='file']"),
            ]:
                try:
                    inputs = self.driver.find_elements(by, sel)
                    if inputs:
                        file_input = inputs[0]
                        break
                except:
                    continue

            if not file_input:
                photo_btn = None
                for by, sel in [
                    (By.XPATH, "//div[@role='dialog']//div[@aria-label='Photo/video']"),
                    (By.XPATH, "//div[@role='dialog']//div[@aria-label='Ảnh/video']"),
                    (By.XPATH, "//div[@role='dialog']//div[contains(@aria-label,'Photo')]"),
                    (By.XPATH, "//div[@role='dialog']//div[contains(@aria-label,'Ảnh')]"),
                ]:
                    try:
                        photo_btn = self.driver.find_element(by, sel)
                        if photo_btn:
                            break
                    except:
                        continue

                if photo_btn:
                    self.driver.execute_script("""
                        HTMLInputElement.prototype._originalClick = HTMLInputElement.prototype.click;
                        HTMLInputElement.prototype.click = function() {
                            if (this.type === 'file') return;
                            this._originalClick();
                        };
                    """)
                    self.driver.execute_script("arguments[0].click();", photo_btn)
                    self.random_delay(1, 2)

                    self.driver.execute_script("""
                        if (HTMLInputElement.prototype._originalClick) {
                            HTMLInputElement.prototype.click = HTMLInputElement.prototype._originalClick;
                        }
                    """)

                    for by, sel in [
                        (By.XPATH, "//div[@role='dialog']//input[@type='file']"),
                        (By.XPATH, "//input[@type='file' and contains(@accept,'image')]"),
                        (By.XPATH, "//input[@type='file']"),
                    ]:
                        try:
                            inputs = self.driver.find_elements(by, sel)
                            if inputs:
                                file_input = inputs[0]
                                break
                        except:
                            continue

            if not file_input:
                self.log("⚠️ Không tìm thấy file input", 'warning')
                return False

            self.driver.execute_script("""
                arguments[0].style.display = 'block';
                arguments[0].style.visibility = 'visible';
                arguments[0].style.opacity = '1';
                arguments[0].style.position = 'fixed';
                arguments[0].style.top = '-9999px';
            """, file_input)

            all_paths = "\n".join(image_paths)
            file_input.send_keys(all_paths)
            self.log(f"   📎 Đã gửi {len(image_paths)} file tới input", 'info')
            self.random_delay(3, 5)
            return True

        except Exception as e:
            self.log(f"⚠️ Lỗi upload ảnh bài: {str(e)}", 'warning')
            return False

    # ── COMMENT ───────────────────────────────────────────────────────

    def open_group_and_scroll(self, group_url, post_count=2):
        try:
            self.log(f"📂 Mở nhóm để comment...", 'info')
            self.driver.get(group_url)
            self.random_delay(5, 7)

            if self.should_stop:
                return 0

            for i in range(20):
                if self.should_stop:
                    return 0

                current_forms = len(self.driver.find_elements(By.TAG_NAME, "form"))
                if current_forms >= post_count:
                    break

                self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                self.random_delay(2, 3)

            self.driver.execute_script("window.scrollTo(0, 0);")
            self.random_delay(1, 2)
            self.driver.execute_script("window.scrollTo(0, 300);")
            self.random_delay(1, 2)

            final_forms = len(self.driver.find_elements(By.TAG_NAME, "form"))
            self.log(f"✅ Load được {final_forms} form", 'success')
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
                "arguments[0].scrollIntoView({behavior:'smooth', block:'center'});", form
            )
            self.random_delay(1.5, 2)

            for by, sel in [
                (By.XPATH, ".//div[contains(@aria-label, 'Write a comment')]"),
                (By.XPATH, ".//div[contains(@aria-label, 'Viết bình luận')]"),
            ]:
                try:
                    el = form.find_element(by, sel)
                    if el.is_displayed():
                        self.driver.execute_script("arguments[0].click();", el)
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
            for by, sel in [
                (By.XPATH, ".//p[@contenteditable='true']"),
                (By.XPATH, ".//div[@contenteditable='true' and @role='textbox']"),
            ]:
                try:
                    el = form.find_element(by, sel)
                    if el.is_displayed() and el.is_enabled():
                        return el
                except:
                    continue
            return None

        except:
            return None

    def upload_image_to_comment(self, post_index, image_path):
        try:
            if not image_path or not os.path.exists(image_path):
                return False

            forms = self.driver.find_elements(By.TAG_NAME, "form")
            if post_index >= len(forms):
                return False

            form = forms[post_index]

            file_input = None
            for by, sel in [
                (By.XPATH, ".//input[@type='file' and contains(@accept,'image')]"),
                (By.XPATH, ".//input[@type='file']"),
            ]:
                try:
                    inputs = form.find_elements(by, sel)
                    if inputs:
                        file_input = inputs[0]
                        break
                except:
                    continue

            if not file_input:
                for by, sel in [
                    (By.XPATH, ".//div[@aria-label='Photo/video']"),
                    (By.XPATH, ".//div[@aria-label='Ảnh/video']"),
                    (By.XPATH, ".//div[contains(@aria-label,'Photo')]"),
                    (By.XPATH, ".//div[contains(@aria-label,'Ảnh')]"),
                ]:
                    try:
                        btn = form.find_element(by, sel)
                        if btn.is_displayed():
                            self.driver.execute_script("arguments[0].click();", btn)
                            self.random_delay(1, 2)
                            break
                    except:
                        continue

                try:
                    file_input = self.driver.find_element(
                        By.XPATH, "//input[@type='file' and contains(@accept,'image')]"
                    )
                except:
                    try:
                        file_input = self.driver.find_element(By.XPATH, "//input[@type='file']")
                    except:
                        pass

            if file_input:
                self.driver.execute_script(
                    "arguments[0].style.display='block'; arguments[0].style.visibility='visible';",
                    file_input
                )
                file_input.send_keys(image_path)
                self.log(f"✅ Upload ảnh comment: {os.path.basename(image_path)}", 'success')
                self.random_delay(2, 4)
                return True

            return False

        except Exception as e:
            self.log(f"⚠️ Lỗi upload ảnh comment: {str(e)}", 'warning')
            return False

    def comment_with_retry(self, post_index, comment_text, comment_image, max_retries=3):
        for attempt in range(1, max_retries + 1):
            if self.should_stop:
                return False

            self.log(f"   🔄 Lần thử {attempt}/{max_retries}...", 'info')

            try:
                form = self.find_and_click_comment_area(post_index)
                if not form:
                    self.log(f"   ⚠️ Không click được vùng comment", 'warning')
                    self.random_delay(2, 4)
                    continue

                comment_box = self.find_comment_box(post_index)
                if not comment_box:
                    self.log(f"   ⚠️ Không tìm thấy comment box", 'warning')
                    self.random_delay(2, 4)
                    continue

                if comment_image and os.path.exists(comment_image):
                    img_ok = self.upload_image_to_comment(post_index, comment_image)
                    if img_ok:
                        self.random_delay(3, 5)
                        comment_box = self.find_comment_box(post_index)
                        if not comment_box:
                            self.log(f"   ⚠️ Mất comment box sau upload ảnh", 'warning')
                            self.random_delay(2, 3)
                            continue

                if comment_text:
                    self.type_multiline(comment_box, comment_text)
                    self.random_delay(1.5, 2.5)

                try:
                    box_content = self.driver.execute_script(
                        "return arguments[0].innerText || arguments[0].textContent || '';",
                        comment_box
                    )
                    if not box_content.strip() and not comment_image:
                        self.log(f"   ⚠️ Box trống, thử lại", 'warning')
                        self.random_delay(2, 3)
                        continue
                except:
                    pass

                self.driver.execute_script("arguments[0].focus();", comment_box)
                time.sleep(0.3)
                comment_box.send_keys(Keys.RETURN)
                self.random_delay(2, 3)

                self.log(f"   ✅ Thành công lần {attempt}", 'success')
                return True

            except Exception as e:
                self.log(f"   ❌ Lỗi lần {attempt}: {str(e)[:80]}", 'warning')
                self.random_delay(3, 5)

        self.log(f"   ❌ Hết {max_retries} lần thử, bỏ qua bài này", 'error')
        return False

    def comment_on_group(self, group_url, post_count=2):
        try:
            available = self.open_group_and_scroll(group_url, post_count * 2)
            if available == 0:
                self.log("⚠️ Không tìm thấy bài viết", 'warning')
                return 0

            comments      = self.config['comments']
            delay_minutes = self.config['delayMinutes']
            success_count = 0
            post_index    = 0
            comment_index = 0

            while success_count < post_count and post_index < available:
                if self.should_stop:
                    break

                comment_data  = comments[comment_index % len(comments)]
                comment_text  = comment_data['text']
                comment_image = comment_data.get('image', '')

                img_info = " + 🖼️" if (comment_image and os.path.exists(comment_image)) else ""
                disp = comment_text[:40] + "..." if len(comment_text) > 40 else comment_text
                self.log(f"📝 Bài {post_index+1} [{success_count+1}/{post_count}]: {disp}{img_info}", 'info')

                ok = self.comment_with_retry(post_index, comment_text, comment_image)

                if ok:
                    success_count += 1
                    comment_index += 1

                    if success_count < post_count and not self.should_stop:
                        self.log(f"⏱️ Chờ {delay_minutes} phút trước bài tiếp...", 'info')
                        for _ in range(delay_minutes * 60):
                            if self.should_stop:
                                break
                            time.sleep(1)

                post_index += 1

            self.log(f"📊 Comment: {success_count}/{post_count} thành công", 'success')
            return success_count

        except Exception as e:
            self.log(f"❌ Lỗi comment nhóm: {str(e)}", 'error')
            return 0

    # ── RUN SESSION (MỚI: Đăng hết bài → rồi mới comment) ────────────

    def run_session(self, session_name):
        """
        Logic mới:
          GIAI ĐOẠN 1: Đăng bài lên tất cả nhóm đăng bài
          GIAI ĐOẠN 2: Comment lên tất cả nhóm comment
        """
        try:
            self.log(f"{'='*55}", 'step')
            self.log(f"🎯 BẮT ĐẦU PHIÊN {session_name.upper()}", 'step')
            self.log(f"{'='*55}", 'step')

            post_groups   = self.config.get('post_groups', [])
            comment_groups= self.config.get('comment_groups', [])
            group_delay   = self.config['groupDelayMinutes']
            post_contents = self.config.get('post_contents', [])

            # ════════════════════════════════════════════════════════
            # GIAI ĐOẠN 1: ĐĂNG BÀI
            # ════════════════════════════════════════════════════════
            if post_groups and post_contents:
                self.log(f"\n{'─'*45}", 'step')
                self.log(f"📤 GIAI ĐOẠN 1: ĐĂNG BÀI ({len(post_groups)} nhóm)", 'step')
                self.log(f"{'─'*45}", 'step')

                post_success = 0
                for idx, group_url in enumerate(post_groups):
                    if self.should_stop:
                        break

                    self.log(f"\n📍 [{idx+1}/{len(post_groups)}] Đăng bài: {group_url.split('/')[-2] or group_url.split('/')[-1]}", 'step')

                    pc        = post_contents[idx % len(post_contents)]
                    post_text = pc.get('text', '')
                    post_imgs = pc.get('images', [])

                    posted = self.post_to_group(group_url, post_text, post_imgs)

                    if posted:
                        post_success += 1
                        self.log(f"✅ Đăng bài thành công nhóm {idx+1}", 'success')
                    else:
                        self.log(f"⚠️ Đăng bài thất bại nhóm {idx+1}", 'warning')

                    if idx < len(post_groups) - 1 and not self.should_stop:
                        self.log(f"⏱️ Chờ {group_delay} phút trước nhóm đăng bài tiếp...", 'info')
                        for _ in range(group_delay * 60):
                            if self.should_stop:
                                break
                            time.sleep(1)

                self.log(f"\n📊 Kết quả đăng bài: {post_success}/{len(post_groups)} nhóm", 'success')
            else:
                if not post_groups:
                    self.log("ℹ️ Không có nhóm đăng bài, bỏ qua giai đoạn 1", 'info')
                else:
                    self.log("ℹ️ Không có nội dung bài đăng, bỏ qua giai đoạn 1", 'info')

            if self.should_stop:
                self.log("⏹️ Đã dừng giữa chừng", 'warning')
                return

            # ════════════════════════════════════════════════════════
            # GIAI ĐOẠN 2: COMMENT
            # ════════════════════════════════════════════════════════
            if comment_groups:
                self.log(f"\n{'─'*45}", 'step')
                self.log(f"💬 GIAI ĐOẠN 2: COMMENT ({len(comment_groups)} nhóm)", 'step')
                self.log(f"{'─'*45}", 'step')

                total_comment_success = 0
                for idx, group_url in enumerate(comment_groups):
                    if self.should_stop:
                        break

                    self.log(f"\n📍 [{idx+1}/{len(comment_groups)}] Comment: {group_url.split('/')[-2] or group_url.split('/')[-1]}", 'step')

                    success = self.comment_on_group(group_url, post_count=2)
                    total_comment_success += success

                    if idx < len(comment_groups) - 1 and not self.should_stop:
                        self.log(f"⏱️ Chờ {group_delay} phút trước nhóm comment tiếp...", 'info')
                        for _ in range(group_delay * 60):
                            if self.should_stop:
                                break
                            time.sleep(1)

                self.log(f"\n📊 Tổng comment: {total_comment_success} bài thành công", 'success')
            else:
                self.log("ℹ️ Không có nhóm comment, bỏ qua giai đoạn 2", 'info')

            self.log(f"\n{'='*55}", 'success')
            self.log(f"✅ HOÀN THÀNH PHIÊN {session_name.upper()}", 'success')
            self.log(f"{'='*55}", 'success')

        except Exception as e:
            self.log(f"❌ Lỗi phiên: {str(e)}", 'error')

    def cleanup(self):
        try:
            if self.driver:
                self.driver.quit()
        except:
            pass


# =====================================================================
# WIDGET: DANH SÁCH NHÓM (dùng chung cho cả 2 tab)
# =====================================================================

class GroupListWidget(ttk.Frame):
    """
    Widget quản lý danh sách nhóm:
    - Hiển thị danh sách với checkbox chọn/bỏ chọn
    - Thêm / Xóa / Lưu / Load
    - Tối đa 25 nhóm
    """
    def __init__(self, parent, label, default_groups=None, max_groups=25, **kwargs):
        super().__init__(parent, **kwargs)
        self.label = label
        self.max_groups = max_groups
        self.group_vars = []   # list of (StringVar url, BooleanVar enabled)
        self._build()
        if default_groups:
            for g in default_groups:
                self._add_group(g, enabled=True)

    def _build(self):
        # Toolbar
        toolbar = ttk.Frame(self)
        toolbar.pack(fill='x', pady=(0, 4))

        ttk.Button(toolbar, text="➕ Thêm", command=self._add_empty, width=9).pack(side='left', padx=(0,2))
        ttk.Button(toolbar, text="➖ Xóa chọn", command=self._remove_selected, width=12).pack(side='left', padx=(0,2))
        ttk.Button(toolbar, text="☑ Chọn tất", command=self._select_all, width=10).pack(side='left', padx=(0,2))
        ttk.Button(toolbar, text="☐ Bỏ chọn", command=self._deselect_all, width=10).pack(side='left', padx=(0,2))
        ttk.Button(toolbar, text="💾 Lưu", command=self._save, width=7).pack(side='right', padx=(2,0))
        ttk.Button(toolbar, text="📂 Load", command=self._load, width=8).pack(side='right', padx=(2,0))

        # Canvas scrollable
        canvas_frame = ttk.Frame(self)
        canvas_frame.pack(fill='both', expand=True)

        self.canvas = tk.Canvas(canvas_frame, height=155, bg="white", highlightthickness=0)
        scroll = ttk.Scrollbar(canvas_frame, orient="vertical", command=self.canvas.yview)
        self.inner = ttk.Frame(self.canvas)

        self.canvas.create_window((0, 0), window=self.inner, anchor="nw")
        self.canvas.configure(yscrollcommand=scroll.set)
        self.canvas.pack(side='left', fill='both', expand=True)
        scroll.pack(side='right', fill='y')

        self.inner.bind("<Configure>",
            lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self.canvas.bind_all("<MouseWheel>",
            lambda e: self.canvas.yview_scroll(int(-1*(e.delta/120)), "units"))

        # Count label
        self.count_label = ttk.Label(self, text="0 nhóm", foreground="#888", font=("Arial",8))
        self.count_label.pack(anchor='e', pady=(2,0))

    def _refresh_rows(self):
        for w in self.inner.winfo_children():
            w.destroy()

        for i, (url_var, enabled_var) in enumerate(self.group_vars):
            row = ttk.Frame(self.inner)
            row.pack(fill='x', pady=1)

            cb = ttk.Checkbutton(row, variable=enabled_var)
            cb.pack(side='left')

            ttk.Label(row, text=f"{i+1}.", width=3, font=("Arial",8)).pack(side='left')

            entry = ttk.Entry(row, textvariable=url_var, width=46)
            entry.pack(side='left', fill='x', expand=True, padx=(2,0))

        count = len(self.group_vars)
        self.count_label.config(
            text=f"{count}/{self.max_groups} nhóm",
            foreground="#006600" if count > 0 else "#888"
        )

    def _add_group(self, url="", enabled=True):
        if len(self.group_vars) >= self.max_groups:
            messagebox.showwarning("Cảnh báo", f"Tối đa {self.max_groups} nhóm!")
            return
        url_var     = tk.StringVar(value=url)
        enabled_var = tk.BooleanVar(value=enabled)
        self.group_vars.append((url_var, enabled_var))
        self._refresh_rows()

    def _add_empty(self):
        self._add_group("", enabled=True)

    def _remove_selected(self):
        # Xóa các dòng được tích chọn
        selected = [i for i, (_, ev) in enumerate(self.group_vars) if ev.get()]
        if not selected:
            messagebox.showinfo("Thông báo", "Chọn (tích) nhóm muốn xóa trước!")
            return
        if not messagebox.askyesno("Xác nhận", f"Xóa {len(selected)} nhóm đã chọn?"):
            return
        self.group_vars = [(uv, ev) for i, (uv, ev) in enumerate(self.group_vars)
                           if i not in selected]
        self._refresh_rows()

    def _select_all(self):
        for _, ev in self.group_vars:
            ev.set(True)

    def _deselect_all(self):
        for _, ev in self.group_vars:
            ev.set(False)

    def _save(self):
        path = filedialog.asksaveasfilename(
            title=f"Lưu danh sách {self.label}",
            defaultextension=".json",
            initialfile=f"groups_{self.label.replace(' ','_').lower()}.json",
            filetypes=[("JSON files","*.json"),("Tất cả","*.*")]
        )
        if not path:
            return
        data = [
            {"url": uv.get().strip(), "enabled": ev.get()}
            for uv, ev in self.group_vars if uv.get().strip()
        ]
        try:
            with open(path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            messagebox.showinfo("Thành công", f"Đã lưu {len(data)} nhóm vào:\n{path}")
        except Exception as e:
            messagebox.showerror("Lỗi", f"Không lưu được: {str(e)}")

    def _load(self):
        path = filedialog.askopenfilename(
            title=f"Load danh sách {self.label}",
            filetypes=[("JSON files","*.json"),("Tất cả","*.*")]
        )
        if not path:
            return
        try:
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)

            if messagebox.askyesno("Xác nhận", f"Thay thế hay thêm vào?\n[Yes = Thay thế hết]\n[No = Thêm vào cuối]"):
                self.group_vars.clear()

            for item in data:
                if isinstance(item, str):
                    url, enabled = item, True
                else:
                    url     = item.get('url', '')
                    enabled = item.get('enabled', True)
                if url and len(self.group_vars) < self.max_groups:
                    url_var     = tk.StringVar(value=url)
                    enabled_var = tk.BooleanVar(value=enabled)
                    self.group_vars.append((url_var, enabled_var))

            self._refresh_rows()
            messagebox.showinfo("Thành công", f"Đã load {len(data)} nhóm từ:\n{path}")
        except Exception as e:
            messagebox.showerror("Lỗi", f"Không đọc được file: {str(e)}")

    def get_active_groups(self):
        """Trả về list URL của các nhóm đang được tick chọn."""
        return [uv.get().strip() for uv, ev in self.group_vars
                if ev.get() and uv.get().strip()]

    def get_all_groups(self):
        """Trả về tất cả URL (bao gồm cả không được tick)."""
        return [uv.get().strip() for uv, _ in self.group_vars if uv.get().strip()]


# =====================================================================
# WIDGET: BÀI ĐĂNG (Text + Nhiều ảnh)
# =====================================================================

class PostWidget(ttk.Frame):
    def __init__(self, parent, index, **kwargs):
        super().__init__(parent, **kwargs)
        self.index = index
        self.image_paths = []
        self._build()

    def _build(self):
        header = ttk.Frame(self)
        header.pack(fill='x')
        ttk.Label(header, text=f"Nội dung #{self.index}",
                  font=("Arial", 8, "bold"), foreground="#0056b3").pack(side='left')

        self.text_widget = tk.Text(self, width=40, height=4, wrap='word',
                                   font=("Arial", 9), relief='solid', borderwidth=1)
        self.text_widget.pack(fill='x', pady=(3, 2))

        ttk.Label(self, text="↵ Dùng | để xuống dòng",
                  font=("Arial", 7), foreground="#888").pack(anchor='w')

        img_outer = ttk.LabelFrame(self, text="🖼️ Ảnh đính kèm", padding="4")
        img_outer.pack(fill='x', pady=(4, 0))

        self.img_list_frame = ttk.Frame(img_outer)
        self.img_list_frame.pack(fill='x')

        btn_row = ttk.Frame(img_outer)
        btn_row.pack(fill='x', pady=(4, 0))
        ttk.Button(btn_row, text="➕ Thêm ảnh", command=self._add_images, width=12).pack(side='left')
        ttk.Button(btn_row, text="🗑️ Xóa tất cả", command=self._clear_images, width=12).pack(side='left', padx=4)
        self.img_count_label = ttk.Label(btn_row, text="0 ảnh", foreground="#888", font=("Arial", 8))
        self.img_count_label.pack(side='left')

    def _add_images(self):
        paths = filedialog.askopenfilenames(
            title="Chọn ảnh cho bài đăng",
            filetypes=[("Hình ảnh", "*.jpg *.jpeg *.png *.gif *.webp *.bmp"), ("Tất cả", "*.*")]
        )
        for p in paths:
            if p not in self.image_paths:
                self.image_paths.append(p)
        self._refresh_img_list()

    def _clear_images(self):
        self.image_paths.clear()
        self._refresh_img_list()

    def _remove_image(self, path):
        if path in self.image_paths:
            self.image_paths.remove(path)
        self._refresh_img_list()

    def _refresh_img_list(self):
        for w in self.img_list_frame.winfo_children():
            w.destroy()

        for p in self.image_paths:
            row = ttk.Frame(self.img_list_frame)
            row.pack(fill='x', pady=1)
            fname = os.path.basename(p)
            display = fname if len(fname) <= 28 else fname[:25] + "..."
            ttk.Label(row, text=f"  📷 {display}", font=("Arial", 8),
                      foreground="#006600").pack(side='left')
            ttk.Button(row, text="✖", width=3,
                       command=lambda pp=p: self._remove_image(pp)).pack(side='right')

        count = len(self.image_paths)
        self.img_count_label.config(
            text=f"{count} ảnh",
            foreground="#006600" if count > 0 else "#888"
        )

    def get_text(self):
        return self.text_widget.get("1.0", 'end').strip()

    def get_images(self):
        return [p for p in self.image_paths if os.path.exists(p)]

    def set_text(self, text):
        self.text_widget.delete("1.0", 'end')
        self.text_widget.insert("1.0", text)


# =====================================================================
# WIDGET: COMMENT (Text + 1 ảnh)
# =====================================================================

class CommentWidget(ttk.Frame):
    def __init__(self, parent, index, **kwargs):
        super().__init__(parent, **kwargs)
        self.index = index
        self.image_path = tk.StringVar(value="")
        self._build()

    def _build(self):
        ttk.Label(self, text=f"{self.index}.", width=3,
                  font=("Arial", 8, "bold")).grid(row=0, column=0, sticky='nw', padx=(0, 2), pady=2)

        right_f = ttk.Frame(self)
        right_f.grid(row=0, column=1, sticky='ew')
        right_f.columnconfigure(0, weight=1)

        self.text_widget = tk.Text(right_f, width=35, height=3, wrap='word',
                                   font=("Arial", 9), relief='solid', borderwidth=1)
        self.text_widget.grid(row=0, column=0, columnspan=3, sticky='ew', pady=(0, 2))

        ttk.Label(right_f, text="↵ Dùng | để xuống dòng",
                  font=("Arial", 7), foreground="#888").grid(row=1, column=0, sticky='w')

        img_row = ttk.Frame(right_f)
        img_row.grid(row=2, column=0, columnspan=3, sticky='ew', pady=(2, 0))

        ttk.Button(img_row, text="🖼️ Chọn ảnh", command=self._choose_image, width=12).pack(side='left')
        self.img_label = ttk.Label(img_row, text="Chưa chọn ảnh",
                                    foreground="#888", font=("Arial", 8))
        self.img_label.pack(side='left', padx=5)
        ttk.Button(img_row, text="✖", command=self._clear_image, width=3).pack(side='left')

    def _choose_image(self):
        path = filedialog.askopenfilename(
            title="Chọn ảnh cho comment",
            filetypes=[("Hình ảnh", "*.jpg *.jpeg *.png *.gif *.webp *.bmp"), ("Tất cả", "*.*")]
        )
        if path:
            self.image_path.set(path)
            fname = os.path.basename(path)
            display = fname if len(fname) <= 25 else fname[:22] + "..."
            self.img_label.config(text=f"✅ {display}", foreground="#00aa00")

    def _clear_image(self):
        self.image_path.set("")
        self.img_label.config(text="Chưa chọn ảnh", foreground="#888")

    def get_text(self):
        return self.text_widget.get("1.0", 'end').strip()

    def get_image(self):
        return self.image_path.get().strip()

    def set_text(self, text):
        self.text_widget.delete("1.0", 'end')
        self.text_widget.insert("1.0", text)


# =====================================================================
# CLASS GUI CHÍNH
# =====================================================================

class FacebookSchedulerApp:
    def __init__(self, root):
        self.root = root
        self.root.title("🤖 Facebook Auto Scheduler Bot v4.0 — Đăng bài + Comment tách nhóm")
        self.root.geometry("1200x950")
        self.root.resizable(True, True)

        self.bot_running       = False
        self.scheduler_running = False
        self.bot_instance      = None
        self.log_queue         = queue.Queue()

        self.post_widgets    = []
        self.comment_widgets = []

        self.setup_ui()
        self.process_log_queue()
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)

    # ── BUILD UI ──────────────────────────────────────────────────────

    def setup_ui(self):
        style = ttk.Style()
        style.theme_use('clam')
        style.configure("Accent.TButton", foreground="white", background="#0056b3")
        style.configure("Stop.TButton", foreground="white", background="#cc0000")

        # Scrollable main canvas
        main_canvas    = tk.Canvas(self.root)
        main_scrollbar = ttk.Scrollbar(self.root, orient="vertical", command=main_canvas.yview)
        main_frame     = ttk.Frame(main_canvas, padding="10")

        main_canvas.create_window((0, 0), window=main_frame, anchor="nw")
        main_canvas.configure(yscrollcommand=main_scrollbar.set)
        main_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        main_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        main_canvas.bind_all("<MouseWheel>",
            lambda e: main_canvas.yview_scroll(int(-1*(e.delta/120)), "units"))

        main_frame.columnconfigure(0, weight=3)
        main_frame.columnconfigure(1, weight=2)

        # ── HEADER ────────────────────────────────────────────────────
        header = ttk.Frame(main_frame)
        header.grid(row=0, column=0, columnspan=2, pady=(0, 8), sticky='ew')

        ttk.Label(header, text="🤖 Facebook Auto Scheduler Bot v4.0",
                  font=("Arial", 15, "bold"), foreground="#667eea").pack()
        ttk.Label(header,
            text="📤 Đăng bài tất cả nhóm đăng → 💬 Comment tất cả nhóm comment  |  Lưu/Load nhóm  |  Retry tự động",
            font=("Arial", 9), foreground="#444"
        ).pack()

        # ── CỘT TRÁI ──────────────────────────────────────────────────
        left = ttk.Frame(main_frame)
        left.grid(row=1, column=0, sticky='nsew', padx=(0, 6))

        # Email & Pass
        cred_f = ttk.LabelFrame(left, text="🔐 Tài khoản Facebook", padding="8")
        cred_f.pack(fill='x', pady=(0, 8))

        for label_text, attr, show in [
            ("📧 Email/SĐT:", "email_var", ""),
            ("🔑 Mật khẩu:", "password_var", "*"),
        ]:
            row = ttk.Frame(cred_f)
            row.pack(fill='x', pady=3)
            ttk.Label(row, text=label_text, width=14, font=("Arial", 9, "bold")).pack(side='left')
            var = tk.StringVar()
            setattr(self, attr, var)
            kw = {"show": show} if show else {}
            ttk.Entry(row, textvariable=var, width=38, **kw).pack(side='left', fill='x', expand=True)

        # ── TAB NHÓM (Đăng bài / Comment) ────────────────────────────
        group_nb = ttk.Notebook(left)
        group_nb.pack(fill='both', expand=False, pady=(0, 8))

        # Tab 1: Nhóm đăng bài
        tab_post = ttk.Frame(group_nb, padding="6")
        group_nb.add(tab_post, text="  📤 Nhóm đăng bài  ")

        ttk.Label(tab_post,
            text="💡 Chỉ nhóm được ✓ tích mới tham gia đăng bài",
            font=("Arial", 8), foreground="#0056b3"
        ).pack(anchor='w', pady=(0, 4))

        self.post_group_widget = GroupListWidget(
            tab_post, label="Nhóm đăng bài",
            default_groups=DEFAULT_POST_GROUPS
        )
        self.post_group_widget.pack(fill='both', expand=True)

        # Tab 2: Nhóm comment
        tab_cmt = ttk.Frame(group_nb, padding="6")
        group_nb.add(tab_cmt, text="  💬 Nhóm comment  ")

        ttk.Label(tab_cmt,
            text="💡 Chỉ nhóm được ✓ tích mới tham gia comment  |  Comment sau khi đăng hết bài",
            font=("Arial", 8), foreground="#664d00"
        ).pack(anchor='w', pady=(0, 4))

        self.comment_group_widget = GroupListWidget(
            tab_cmt, label="Nhóm comment",
            default_groups=DEFAULT_COMMENT_GROUPS
        )
        self.comment_group_widget.pack(fill='both', expand=True)

        # ── NỘI DUNG BÀI ĐĂNG ─────────────────────────────────────────
        post_f = ttk.LabelFrame(left,
            text="📤 Nội dung bài đăng (xoay vòng qua các nhóm đăng bài)",
            padding="8"
        )
        post_f.pack(fill='both', expand=True, pady=(0, 8))

        ph = tk.Frame(post_f, bg="#e8f4fd", bd=1, relief='solid')
        ph.pack(fill='x', pady=(0, 6))
        ttk.Label(ph,
            text="💡 Mỗi ô = 1 nội dung, xoay vòng qua nhóm  |  Để trống = bỏ qua đăng bài  |  Dùng | xuống dòng",
            font=("Arial", 8), background="#e8f4fd", foreground="#0056b3"
        ).pack(anchor='w', padx=5, pady=3)

        post_canvas = tk.Canvas(post_f, height=300, bg="white")
        post_scroll = ttk.Scrollbar(post_f, orient="vertical", command=post_canvas.yview)
        self.posts_inner = ttk.Frame(post_canvas)
        post_canvas.create_window((0, 0), window=self.posts_inner, anchor="nw")
        post_canvas.configure(yscrollcommand=post_scroll.set)
        post_canvas.pack(side='left', fill='both', expand=True)
        post_scroll.pack(side='right', fill='y')
        self.posts_inner.bind("<Configure>",
            lambda e: post_canvas.configure(scrollregion=post_canvas.bbox("all")))

        for pc in DEFAULT_POST_CONTENTS:
            self._add_post_widget(pc)

        post_btn_f = ttk.Frame(post_f)
        post_btn_f.pack(fill='x', pady=(5, 0))
        ttk.Button(post_btn_f, text="➕ Thêm nội dung",
                   command=lambda: self._add_post_widget(), width=16).pack(side='left', padx=(0, 3))
        ttk.Button(post_btn_f, text="➖ Xóa cuối",
                   command=self._remove_post_widget, width=12).pack(side='left')

        # ── COMMENT ───────────────────────────────────────────────────
        cmt_f = ttk.LabelFrame(left,
            text="💬 Nội dung comment (Text + Ảnh, xoay vòng)",
            padding="8"
        )
        cmt_f.pack(fill='both', expand=True, pady=(0, 8))

        ch = tk.Frame(cmt_f, bg="#fffbe6", bd=1, relief='solid')
        ch.pack(fill='x', pady=(0, 6))
        ttk.Label(ch,
            text="💡 Dùng | để xuống dòng  |  Mỗi comment có thể gắn ảnh riêng",
            font=("Arial", 8), background="#fffbe6", foreground="#664d00"
        ).pack(anchor='w', padx=5, pady=3)

        cmt_canvas = tk.Canvas(cmt_f, height=220, bg="white")
        cmt_scroll = ttk.Scrollbar(cmt_f, orient="vertical", command=cmt_canvas.yview)
        self.comments_inner = ttk.Frame(cmt_canvas)
        cmt_canvas.create_window((0, 0), window=self.comments_inner, anchor="nw")
        cmt_canvas.configure(yscrollcommand=cmt_scroll.set)
        cmt_canvas.pack(side='left', fill='both', expand=True)
        cmt_scroll.pack(side='right', fill='y')
        self.comments_inner.bind("<Configure>",
            lambda e: cmt_canvas.configure(scrollregion=cmt_canvas.bbox("all")))

        for c in DEFAULT_COMMENTS:
            self._add_comment_widget(c)

        cmt_btn_f = ttk.Frame(cmt_f)
        cmt_btn_f.pack(fill='x', pady=(5, 0))
        ttk.Button(cmt_btn_f, text="➕ Thêm comment",
                   command=lambda: self._add_comment_widget(), width=16).pack(side='left', padx=(0, 3))
        ttk.Button(cmt_btn_f, text="➖ Xóa cuối",
                   command=self._remove_comment_widget, width=12).pack(side='left')

        # Delay
        delay_f = ttk.LabelFrame(left, text="⏱️ Thời gian chờ", padding="6")
        delay_f.pack(fill='x', pady=(0, 8))

        delay_row = ttk.Frame(delay_f)
        delay_row.pack(fill='x')
        ttk.Label(delay_row, text="Delay bài (phút):").pack(side='left')
        self.delay_var = tk.StringVar(value="2")
        ttk.Entry(delay_row, textvariable=self.delay_var, width=5).pack(side='left', padx=5)

        ttk.Label(delay_row, text="Delay nhóm (phút):").pack(side='left', padx=(15, 0))
        self.group_delay_var = tk.StringVar(value="5")
        ttk.Entry(delay_row, textvariable=self.group_delay_var, width=5).pack(side='left', padx=5)

        # Thời gian lịch
        time_f = ttk.LabelFrame(left, text="⏰ Lịch tự động", padding="6")
        time_f.pack(fill='x', pady=(0, 8))

        time_row = ttk.Frame(time_f)
        time_row.pack(fill='x')
        for label, attr, default in [("🌅 Sáng:", "morning_var", "09:30"),
                                      ("🌇 Chiều:", "afternoon_var", "14:02")]:
            ttk.Label(time_row, text=label, width=8).pack(side='left')
            var = tk.StringVar(value=default)
            setattr(self, attr, var)
            ttk.Entry(time_row, textvariable=var, width=8).pack(side='left', padx=(0, 15))

        # Buttons
        btn_f = ttk.Frame(left)
        btn_f.pack(fill='x', pady=(6, 0))

        self.start_btn = tk.Button(
            btn_f, text="🚀 BẮT ĐẦU LỊCH",
            command=self.start_scheduler,
            bg="#0056b3", fg="white", font=("Arial", 10, "bold"),
            relief='flat', padx=10, pady=6
        )
        self.start_btn.pack(side='left', fill='x', expand=True, padx=(0, 3))

        self.stop_btn = tk.Button(
            btn_f, text="⏹️ DỪNG",
            command=self.stop_scheduler,
            bg="#cc0000", fg="white", font=("Arial", 10, "bold"),
            relief='flat', padx=10, pady=6, state='disabled'
        )
        self.stop_btn.pack(side='left', fill='x', expand=True, padx=(0, 3))

        self.test_btn = tk.Button(
            btn_f, text="▶ CHẠY NGAY (TEST)",
            command=self.run_now_test,
            bg="#28a745", fg="white", font=("Arial", 10, "bold"),
            relief='flat', padx=10, pady=6
        )
        self.test_btn.pack(side='left', fill='x', expand=True)

        # ── CỘT PHẢI ──────────────────────────────────────────────────
        right = ttk.Frame(main_frame)
        right.grid(row=1, column=1, sticky='nsew', padx=(6, 0))

        # Status
        stat = ttk.LabelFrame(right, text="📊 Trạng thái", padding="8")
        stat.pack(fill='x', pady=(0, 8))

        for label_text, attr in [
            ("Trạng thái:", "status_label"),
            ("Phiên tiếp:", "next_session_label"),
            ("Nhóm đăng:", "post_groups_label"),
            ("Nhóm comment:", "comment_groups_label"),
        ]:
            row = ttk.Frame(stat)
            row.pack(fill='x', pady=2)
            ttk.Label(row, text=label_text, font=("Arial", 9, "bold"), width=15).pack(side='left')
            lbl = ttk.Label(row, text="-")
            lbl.pack(side='left')
            setattr(self, attr, lbl)

        self.status_label.config(text="⏸ Chờ", foreground="#888")

        # Flow diagram nhỏ
        flow_f = tk.Frame(right, bg="#f0f4ff", bd=1, relief='solid')
        flow_f.pack(fill='x', pady=(0, 8))
        ttk.Label(flow_f,
            text="🔄 Luồng hoạt động:\n"
                 "  1️⃣  Đăng bài → tất cả nhóm đăng bài (tuần tự)\n"
                 "  2️⃣  Comment → tất cả nhóm comment (tuần tự)\n"
                 "  ✓   Nhóm không tích = bỏ qua",
            font=("Arial", 8), background="#f0f4ff", foreground="#333",
            justify='left'
        ).pack(anchor='w', padx=8, pady=5)

        # Log
        log_f = ttk.LabelFrame(right, text="📋 Nhật ký hoạt động", padding="8")
        log_f.pack(fill='both', expand=True)

        self.log_text = scrolledtext.ScrolledText(
            log_f, width=52, height=40,
            bg="#1e1e1e", fg="#00ff00",
            font=("Courier New", 8), wrap='word'
        )
        self.log_text.pack(fill='both', expand=True)

        for tag, color in [("info","#00bfff"), ("success","#00ff00"),
                            ("warning","#ffa500"), ("error","#ff4444"), ("step","#ffff00")]:
            self.log_text.tag_config(tag, foreground=color)

        main_frame.update_idletasks()
        main_canvas.configure(scrollregion=main_canvas.bbox("all"))

    # ── POST WIDGETS ──────────────────────────────────────────────────

    def _add_post_widget(self, default=""):
        if len(self.post_widgets) >= 10:
            messagebox.showwarning("Cảnh báo", "Tối đa 10 nội dung bài đăng!")
            return

        sep = ttk.Separator(self.posts_inner, orient='horizontal')
        sep.pack(fill='x', pady=3)

        idx = len(self.post_widgets) + 1
        w = PostWidget(self.posts_inner, index=idx)
        w.pack(fill='x', pady=2, padx=2)

        if default:
            w.set_text(default)

        self.post_widgets.append(w)

    def _remove_post_widget(self):
        if not self.post_widgets:
            return
        w = self.post_widgets.pop()
        children = list(self.posts_inner.winfo_children())
        idx = children.index(w)
        if idx > 0:
            children[idx - 1].destroy()
        w.destroy()

    # ── COMMENT WIDGETS ───────────────────────────────────────────────

    def _add_comment_widget(self, default=""):
        if len(self.comment_widgets) >= 20:
            messagebox.showwarning("Cảnh báo", "Tối đa 20 comment!")
            return

        sep = ttk.Separator(self.comments_inner, orient='horizontal')
        sep.pack(fill='x', pady=2)

        idx = len(self.comment_widgets) + 1
        w = CommentWidget(self.comments_inner, index=idx)
        w.pack(fill='x', pady=2, padx=2)

        if default:
            w.set_text(default)

        self.comment_widgets.append(w)

    def _remove_comment_widget(self):
        if len(self.comment_widgets) <= 1:
            messagebox.showwarning("Cảnh báo", "Cần ít nhất 1 comment!")
            return
        w = self.comment_widgets.pop()
        children = list(self.comments_inner.winfo_children())
        idx = children.index(w)
        if idx > 0:
            children[idx - 1].destroy()
        w.destroy()

    # ── LOG ───────────────────────────────────────────────────────────

    def add_log(self, log_data):
        ts  = log_data.get('timestamp', '')
        msg = log_data.get('message', '')
        typ = log_data.get('type', 'info')
        self.log_text.insert('end', f"[{ts}] {msg}\n", typ)
        self.log_text.see('end')

        lines = int(self.log_text.index('end-1c').split('.')[0])
        if lines > 2000:
            self.log_text.delete('1.0', '200.0')

    def process_log_queue(self):
        try:
            while True:
                self.add_log(self.log_queue.get_nowait())
        except queue.Empty:
            pass
        self.root.after(100, self.process_log_queue)

    # ── VALIDATION & CONFIG ───────────────────────────────────────────

    @staticmethod
    def _normalize_time(raw: str) -> str:
        t = raw.strip().replace('.', ':').replace(' ', '')
        if ':' not in t and t.isdigit():
            if len(t) == 3:
                t = '0' + t[0] + ':' + t[1:]
            elif len(t) == 4:
                t = t[:2] + ':' + t[2:]
            else:
                raise ValueError(f"Không nhận dạng được giờ: {raw}")

        parts = t.split(':')
        if len(parts) < 2:
            raise ValueError(f"Không nhận dạng được giờ: {raw}")

        hh = int(parts[0])
        mm = int(parts[1])
        if not (0 <= hh <= 23 and 0 <= mm <= 59):
            raise ValueError(f"Giờ ngoài phạm vi: {raw}")
        return f"{hh:02d}:{mm:02d}"

    def validate_inputs(self):
        if not self.email_var.get().strip():
            messagebox.showerror("Lỗi", "Nhập Email/SĐT!")
            return False
        if not self.password_var.get().strip():
            messagebox.showerror("Lỗi", "Nhập mật khẩu!")
            return False

        post_groups    = self.post_group_widget.get_active_groups()
        comment_groups = self.comment_group_widget.get_active_groups()

        if not post_groups and not comment_groups:
            messagebox.showerror("Lỗi", "Cần ít nhất 1 nhóm (đăng bài hoặc comment) được tích chọn!")
            return False

        if not [w for w in self.comment_widgets if w.get_text()] and comment_groups:
            messagebox.showerror("Lỗi", "Có nhóm comment nhưng chưa nhập nội dung comment!")
            return False

        try:
            int(self.delay_var.get())
            int(self.group_delay_var.get())
        except:
            messagebox.showerror("Lỗi", "Delay phải là số!")
            return False

        for attr, label in [("morning_var", "Giờ sáng"), ("afternoon_var", "Giờ chiều")]:
            raw = getattr(self, attr).get()
            try:
                normalized = self._normalize_time(raw)
                getattr(self, attr).set(normalized)
            except ValueError:
                messagebox.showerror("Lỗi định dạng giờ",
                    f"{label}: '{raw}' không hợp lệ!\nVí dụ: 09:30 hoặc 14:02")
                return False

        return True

    def build_config(self):
        post_groups    = self.post_group_widget.get_active_groups()
        comment_groups = self.comment_group_widget.get_active_groups()

        comments = [
            {'text': w.get_text(), 'image': w.get_image()}
            for w in self.comment_widgets if w.get_text()
        ]

        post_contents = [
            {'text': w.get_text(), 'images': w.get_images()}
            for w in self.post_widgets if w.get_text()
        ]

        return {
            'email':             self.email_var.get().strip(),
            'password':          self.password_var.get().strip(),
            'post_groups':       post_groups,
            'comment_groups':    comment_groups,
            'comments':          comments,
            'post_contents':     post_contents,
            'morningTime':       self._normalize_time(self.morning_var.get()),
            'afternoonTime':     self._normalize_time(self.afternoon_var.get()),
            'delayMinutes':      int(self.delay_var.get()),
            'groupDelayMinutes': int(self.group_delay_var.get()),
        }

    def _update_status_labels(self, config):
        pg = len(config.get('post_groups', []))
        cg = len(config.get('comment_groups', []))
        self.post_groups_label.config(
            text=f"{pg} nhóm {'✓' if pg else '(bỏ qua)'}",
            foreground="#006600" if pg else "#888"
        )
        self.comment_groups_label.config(
            text=f"{cg} nhóm {'✓' if cg else '(bỏ qua)'}",
            foreground="#006600" if cg else "#888"
        )

    # ── START / STOP / TEST ───────────────────────────────────────────

    def start_scheduler(self):
        if not self.validate_inputs():
            return

        config = self.build_config()
        self.start_btn.config(state='disabled')
        self.stop_btn.config(state='normal')
        self.test_btn.config(state='disabled')
        self.status_label.config(text="🟢 Đang chạy", foreground="#00cc00")
        self._update_status_labels(config)
        self.bot_running = True

        threading.Thread(target=self.run_scheduler, args=(config,), daemon=True).start()

    def run_now_test(self):
        if self.bot_running:
            messagebox.showwarning("Cảnh báo", "Bot đang chạy! Dừng trước.")
            return
        if not self.validate_inputs():
            return

        config = self.build_config()
        self.start_btn.config(state='disabled')
        self.stop_btn.config(state='normal')
        self.test_btn.config(state='disabled')
        self.status_label.config(text="🟡 Đang test...", foreground="#ffa500")
        self._update_status_labels(config)
        self.bot_running = True

        def test_run():
            bot = FacebookBot(config, self.log_queue)
            self.bot_instance = bot

            if not bot.setup_driver():
                self.root.after(0, self.reset_ui)
                return
            if not bot.login_facebook():
                bot.cleanup()
                self.root.after(0, self.reset_ui)
                return

            bot.run_session("TEST — Chạy ngay")
            bot.cleanup()
            self.bot_running = False
            self.root.after(0, self.reset_ui)

        threading.Thread(target=test_run, daemon=True).start()

    def stop_scheduler(self):
        if messagebox.askyesno("Xác nhận", "Dừng bot?"):
            self.bot_running       = False
            self.scheduler_running = False

            if self.bot_instance:
                self.bot_instance.should_stop = True

            schedule.clear()
            self.start_btn.config(state='normal')
            self.stop_btn.config(state='disabled')
            self.test_btn.config(state='normal')
            self.status_label.config(text="🔴 Đã dừng", foreground="#cc0000")

            self.log_queue.put({
                'timestamp': time.strftime("%H:%M:%S"),
                'message': '⏹️ Đã dừng bot',
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

        morning   = config['morningTime']
        afternoon = config['afternoonTime']

        def morning_job():
            if self.bot_running and not self.bot_instance.should_stop:
                self.bot_instance.run_session("Buổi sáng")

        def afternoon_job():
            if self.bot_running and not self.bot_instance.should_stop:
                self.bot_instance.run_session("Buổi chiều")

        try:
            schedule.every().day.at(morning).do(morning_job)
            schedule.every().day.at(afternoon).do(afternoon_job)
        except Exception as e:
            self.bot_instance.log(f"❌ Lỗi đặt lịch: {str(e)}", 'error')
            self.scheduler_running = False
            self.bot_instance.cleanup()
            self.root.after(0, self.reset_ui)
            return

        pg = len(config.get('post_groups', []))
        cg = len(config.get('comment_groups', []))
        pc = len(config.get('post_contents', []))
        cm = len(config.get('comments', []))

        self.bot_instance.log(f"📅 Lịch: Sáng {morning} | Chiều {afternoon}", 'info')
        self.bot_instance.log(f"📤 Nhóm đăng bài: {pg} | 💬 Nhóm comment: {cg}", 'info')
        self.bot_instance.log(f"📌 {pc} bài đăng | {cm} comment xoay vòng", 'info')

        self.root.after(0, lambda: self._update_next_session(config))

        while self.bot_running and self.scheduler_running:
            schedule.run_pending()
            time.sleep(1)

        self.bot_instance.log("🛑 Đã dừng scheduler", 'warning')
        self.bot_instance.cleanup()

    def _update_next_session(self, config):
        try:
            now  = datetime.now()
            morn = datetime.strptime(config['morningTime'], "%H:%M").replace(
                year=now.year, month=now.month, day=now.day)
            aftn = datetime.strptime(config['afternoonTime'], "%H:%M").replace(
                year=now.year, month=now.month, day=now.day)

            if now.time() < morn.time():
                txt = f"Sáng {config['morningTime']}"
            elif now.time() < aftn.time():
                txt = f"Chiều {config['afternoonTime']}"
            else:
                txt = f"Sáng {config['morningTime']} (ngày mai)"

            self.next_session_label.config(text=txt)
        except:
            pass

    def reset_ui(self):
        self.start_btn.config(state='normal')
        self.stop_btn.config(state='disabled')
        self.test_btn.config(state='normal')
        self.status_label.config(text="⏸ Sẵn sàng", foreground="#888")

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
    print("=" * 65)
    print("🤖 FACEBOOK AUTO SCHEDULER BOT v4.0")
    print("=" * 65)
    print("✅ Tính năng mới:")
    print("   📋  Tab nhóm đăng bài RIÊNG | Tab nhóm comment RIÊNG")
    print("   💾  Lưu/Load danh sách nhóm ra file JSON")
    print("   ☑   Tích chọn từng nhóm muốn bật/tắt")
    print("   🔄  Logic: Đăng hết bài → rồi mới comment")
    print("   📤  Đăng bài: Text + Nhiều ảnh tùy ý")
    print("   💬  Comment: Text + 1 ảnh đính kèm")
    print("   🔁  Retry tự động 3 lần khi thất bại")
    print("   ⏰  Lịch tự động Sáng & Chiều")
    print("=" * 65)

    root = tk.Tk()
    FacebookSchedulerApp(root)
    root.mainloop()


if __name__ == '__main__':
    main()