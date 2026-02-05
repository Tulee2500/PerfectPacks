"""
Facebook Auto Comment Bot - Scheduled Version
Chạy tự động cả ngày: Sáng + Chiều comment vào 10 nhóm
"""
from flask import Flask, render_template_string, request, jsonify
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager
from selenium.common.exceptions import StaleElementReferenceException, NoSuchElementException
import time
import random
import threading
from datetime import datetime, timedelta
import schedule

app = Flask(__name__)

# Biến toàn cục
bot_running = False
scheduler_running = False
bot_instance = None

# HTML Template
HTML_TEMPLATE = '''
<!DOCTYPE html>
<html lang="vi">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Facebook Auto Scheduler Bot</title>
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }
        
        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            padding: 20px;
        }
        
        .container {
            max-width: 900px;
            margin: 0 auto;
        }
        
        .card {
            background: white;
            border-radius: 12px;
            box-shadow: 0 8px 32px rgba(0,0,0,0.1);
            padding: 30px;
            margin-bottom: 20px;
        }
        
        .header {
            text-align: center;
            margin-bottom: 30px;
        }
        
        .header h1 {
            color: #667eea;
            font-size: 2em;
            margin-bottom: 10px;
        }
        
        .header .subtitle {
            color: #666;
            font-size: 1.1em;
        }
        
        .form-group {
            margin-bottom: 20px;
        }
        
        .form-group label {
            display: block;
            margin-bottom: 8px;
            color: #333;
            font-weight: 500;
        }
        
        .form-group input,
        .form-group textarea {
            width: 100%;
            padding: 12px;
            border: 2px solid #e0e0e0;
            border-radius: 8px;
            font-size: 14px;
            transition: border-color 0.3s;
        }
        
        .form-group input:focus,
        .form-group textarea:focus {
            outline: none;
            border-color: #667eea;
        }
        
        .form-group textarea {
            min-height: 100px;
            resize: vertical;
        }
        
        .time-inputs {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 15px;
        }
        
        .group-links {
            margin-bottom: 20px;
        }
        
        .group-item {
            margin-bottom: 15px;
            padding: 15px;
            background: #f9f9f9;
            border-radius: 8px;
            position: relative;
        }
        
        .group-item input {
            width: 100%;
            padding: 10px;
            border: 1px solid #ddd;
            border-radius: 6px;
        }
        
        .remove-btn {
            position: absolute;
            top: 10px;
            right: 10px;
            background: #ff4444;
            color: white;
            border: none;
            border-radius: 50%;
            width: 30px;
            height: 30px;
            cursor: pointer;
            font-size: 18px;
            line-height: 1;
        }
        
        .add-group-btn {
            background: #4CAF50;
            color: white;
            padding: 10px 20px;
            border: none;
            border-radius: 8px;
            cursor: pointer;
            font-size: 14px;
            margin-bottom: 20px;
        }
        
        .add-group-btn:hover {
            background: #45a049;
        }
        
        .comments-section {
            margin-bottom: 20px;
        }
        
        .comment-item {
            margin-bottom: 15px;
            padding: 15px;
            background: #f9f9f9;
            border-radius: 8px;
            position: relative;
        }
        
        .comment-item textarea {
            width: 100%;
            padding: 10px;
            border: 1px solid #ddd;
            border-radius: 6px;
            min-height: 80px;
        }
        
        .add-comment-btn {
            background: #4CAF50;
            color: white;
            padding: 10px 20px;
            border: none;
            border-radius: 8px;
            cursor: pointer;
            font-size: 14px;
            margin-bottom: 20px;
        }
        
        .add-comment-btn:hover {
            background: #45a049;
        }
        
        .btn-group {
            display: flex;
            gap: 10px;
            margin-top: 20px;
        }
        
        .btn {
            flex: 1;
            padding: 15px;
            border: none;
            border-radius: 8px;
            font-size: 16px;
            font-weight: 600;
            cursor: pointer;
            transition: all 0.3s;
        }
        
        .btn-primary {
            background: #667eea;
            color: white;
        }
        
        .btn-primary:hover {
            background: #5568d3;
        }
        
        .btn-danger {
            background: #ff4444;
            color: white;
        }
        
        .btn-danger:hover {
            background: #cc0000;
        }
        
        .btn:disabled {
            background: #ccc;
            cursor: not-allowed;
        }
        
        .status-card {
            background: #f0f8ff;
            border-left: 4px solid #667eea;
            padding: 20px;
            border-radius: 8px;
            margin-bottom: 20px;
        }
        
        .status-card h3 {
            color: #667eea;
            margin-bottom: 15px;
        }
        
        .status-item {
            display: flex;
            justify-content: space-between;
            padding: 8px 0;
            border-bottom: 1px solid #e0e0e0;
        }
        
        .status-item:last-child {
            border-bottom: none;
        }
        
        .status-label {
            font-weight: 500;
            color: #555;
        }
        
        .status-value {
            color: #333;
            font-weight: 600;
        }
        
        .status-running {
            color: #4CAF50;
        }
        
        .status-stopped {
            color: #ff4444;
        }
        
        .log-card {
            margin-top: 20px;
        }
        
        .log-container {
            background: #1e1e1e;
            color: #00ff00;
            padding: 20px;
            border-radius: 8px;
            max-height: 400px;
            overflow-y: auto;
            font-family: 'Courier New', monospace;
            font-size: 13px;
        }
        
        .log-entry {
            margin-bottom: 8px;
            padding: 5px;
        }
        
        .log-info { color: #00bfff; }
        .log-success { color: #00ff00; }
        .log-warning { color: #ffa500; }
        .log-error { color: #ff4444; }
        .log-step { color: #ffff00; font-weight: bold; }
        
        .hidden {
            display: none;
        }
        
        .spinner {
            border: 3px solid #f3f3f3;
            border-top: 3px solid #667eea;
            border-radius: 50%;
            width: 20px;
            height: 20px;
            animation: spin 1s linear infinite;
            display: inline-block;
            margin-right: 10px;
        }
        
        @keyframes spin {
            0% { transform: rotate(0deg); }
            100% { transform: rotate(360deg); }
        }
        
        .schedule-info {
            background: #fff3cd;
            border: 2px solid #ffc107;
            padding: 15px;
            border-radius: 8px;
            margin-bottom: 20px;
        }
        
        .schedule-info h4 {
            color: #856404;
            margin-bottom: 10px;
        }
        
        .schedule-info ul {
            margin-left: 20px;
            color: #856404;
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="card">
            <div class="header">
                <h1>🤖 Facebook Auto Scheduler Bot</h1>
                <p class="subtitle">Tự động comment cả ngày - Sáng & Chiều</p>
            </div>
            
            <div class="schedule-info">
                <h4>📅 Lịch trình hoạt động:</h4>
                <ul>
                    <li><strong>Buổi sáng:</strong> Comment 2 bài/nhóm vào tất cả 10 nhóm</li>
                    <li><strong>Buổi chiều:</strong> Comment 2 bài/nhóm vào tất cả 10 nhóm</li>
                    <li><strong>Tự động:</strong> Chạy liên tục đến khi bạn tắt</li>
                </ul>
            </div>
            
            <div id="statusCard" class="status-card hidden">
                <h3>📊 Trạng thái hệ thống</h3>
                <div class="status-item">
                    <span class="status-label">Trạng thái:</span>
                    <span class="status-value" id="statusText">Đang chờ</span>
                </div>
                <div class="status-item">
                    <span class="status-label">Phiên tiếp theo:</span>
                    <span class="status-value" id="nextSession">-</span>
                </div>
                <div class="status-item">
                    <span class="status-label">Tổng nhóm:</span>
                    <span class="status-value" id="totalGroups">0</span>
                </div>
                <div class="status-item">
                    <span class="status-label">Bài/nhóm:</span>
                    <span class="status-value">2 bài (sáng) + 2 bài (chiều)</span>
                </div>
            </div>
            
            <form id="botForm">
                <div class="form-group">
                    <label>📧 Email/Số điện thoại Facebook:</label>
                    <input type="text" id="email" required>
                </div>
                
                <div class="form-group">
                    <label>🔐 Mật khẩu:</label>
                    <input type="password" id="password" required>
                </div>
                
                <div class="form-group">
                    <label>⏰ Cấu hình thời gian:</label>
                    <div class="time-inputs">
                        <div>
                            <label style="font-size: 0.9em; color: #666;">Giờ chạy buổi sáng (VD: 08:00)</label>
                            <input type="time" id="morningTime" value="08:00" required>
                        </div>
                        <div>
                            <label style="font-size: 0.9em; color: #666;">Giờ chạy buổi chiều (VD: 14:00)</label>
                            <input type="time" id="afternoonTime" value="14:00" required>
                        </div>
                    </div>
                </div>
                
                <div class="group-links">
                    <label>🔗 Link 10 nhóm Facebook:</label>
                    <button type="button" class="add-group-btn" onclick="addGroup()">➕ Thêm nhóm</button>
                    <div id="groupsList">
                        <div class="group-item" data-index="1">
                            <label>Nhóm 1:</label>
                            <input type="url" class="group-input" placeholder="https://www.facebook.com/groups/..." required>
                        </div>
                    </div>
                </div>
                
                <div class="comments-section">
                    <label>💬 Nội dung comment (sẽ xoay vòng):</label>
                    <button type="button" class="add-comment-btn" onclick="addComment()">➕ Thêm comment</button>
                    <div id="commentsList">
                        <div class="comment-item" data-index="1">
                            <label>Comment 1:</label>
                            <textarea class="comment-input" placeholder="Nhập nội dung comment..." required></textarea>
                        </div>
                    </div>
                </div>
                
                <div class="form-group">
                    <label>⏱️ Delay giữa các bài viết (phút):</label>
                    <input type="number" id="delayMinutes" min="1" max="10" value="2" required>
                </div>
                
                <div class="form-group">
                    <label>⏱️ Delay giữa các nhóm (phút):</label>
                    <input type="number" id="groupDelayMinutes" min="2" max="30" value="5" required>
                </div>
                
                <div class="btn-group">
                    <button type="submit" class="btn btn-primary" id="startBtn">
                        🚀 Bắt đầu Scheduler
                    </button>
                    <button type="button" class="btn btn-danger hidden" id="stopBtn" onclick="stopScheduler()">
                        ⏹️ Dừng Scheduler
                    </button>
                </div>
            </form>
        </div>
        
        <div class="card log-card hidden" id="logCard">
            <h3>📋 Nhật ký hoạt động:</h3>
            <div class="log-container" id="logContainer"></div>
        </div>
    </div>
    
    <script>
        let groupCount = 1;
        let commentCount = 1;
        
        function addGroup() {
            if (groupCount >= 10) {
                alert('⚠️ Tối đa 10 nhóm!');
                return;
            }
            
            groupCount++;
            const groupsList = document.getElementById('groupsList');
            const newGroup = document.createElement('div');
            newGroup.className = 'group-item';
            newGroup.setAttribute('data-index', groupCount);
            newGroup.innerHTML = `
                <label>Nhóm ${groupCount}:</label>
                <input type="url" class="group-input" placeholder="https://www.facebook.com/groups/..." required>
                <button type="button" class="remove-btn" onclick="removeGroup(this)">×</button>
            `;
            groupsList.appendChild(newGroup);
        }
        
        function removeGroup(btn) {
            if (groupCount <= 1) {
                alert('⚠️ Phải có ít nhất 1 nhóm!');
                return;
            }
            
            btn.parentElement.remove();
            groupCount--;
            
            const groups = document.querySelectorAll('.group-item');
            groups.forEach((item, index) => {
                item.setAttribute('data-index', index + 1);
                item.querySelector('label').textContent = `Nhóm ${index + 1}:`;
            });
        }
        
        function addComment() {
            if (commentCount >= 20) {
                alert('⚠️ Tối đa 20 nội dung comment!');
                return;
            }
            
            commentCount++;
            const commentsList = document.getElementById('commentsList');
            const newComment = document.createElement('div');
            newComment.className = 'comment-item';
            newComment.setAttribute('data-index', commentCount);
            newComment.innerHTML = `
                <label>Comment ${commentCount}:</label>
                <textarea class="comment-input" placeholder="Nhập nội dung comment..."></textarea>
                <button type="button" class="remove-btn" onclick="removeComment(this)">×</button>
            `;
            commentsList.appendChild(newComment);
        }
        
        function removeComment(btn) {
            if (commentCount <= 1) {
                alert('⚠️ Phải có ít nhất 1 nội dung comment!');
                return;
            }
            
            btn.parentElement.remove();
            commentCount--;
            
            const comments = document.querySelectorAll('.comment-item');
            comments.forEach((item, index) => {
                item.setAttribute('data-index', index + 1);
                item.querySelector('label').textContent = `Comment ${index + 1}:`;
            });
        }
        
        document.getElementById('botForm').addEventListener('submit', async (e) => {
            e.preventDefault();
            
            const groupInputs = document.querySelectorAll('.group-input');
            const groups = [];
            
            groupInputs.forEach((input) => {
                const value = input.value.trim();
                if (value) groups.push(value);
            });
            
            if (groups.length === 0) {
                alert('⚠️ Vui lòng nhập ít nhất 1 nhóm!');
                return;
            }
            
            const commentInputs = document.querySelectorAll('.comment-input');
            const comments = [];
            
            commentInputs.forEach((input) => {
                const value = input.value.trim();
                if (value) comments.push(value);
            });
            
            if (comments.length === 0) {
                alert('⚠️ Vui lòng nhập ít nhất 1 nội dung comment!');
                return;
            }
            
            const formData = {
                email: document.getElementById('email').value,
                password: document.getElementById('password').value,
                groups: groups,
                comments: comments,
                morningTime: document.getElementById('morningTime').value,
                afternoonTime: document.getElementById('afternoonTime').value,
                delayMinutes: parseInt(document.getElementById('delayMinutes').value),
                groupDelayMinutes: parseInt(document.getElementById('groupDelayMinutes').value)
            };
            
            document.getElementById('logCard').classList.remove('hidden');
            document.getElementById('statusCard').classList.remove('hidden');
            document.getElementById('logContainer').innerHTML = '<div class="log-entry log-info">🚀 Đang khởi động scheduler...</div>';
            
            document.getElementById('startBtn').disabled = true;
            document.getElementById('startBtn').innerHTML = '<div class="spinner"></div><span>Đang chạy...</span>';
            document.getElementById('stopBtn').classList.remove('hidden');
            
            document.getElementById('totalGroups').textContent = groups.length;
            document.getElementById('statusText').textContent = 'Đang chạy';
            document.getElementById('statusText').classList.add('status-running');
            
            try {
                const response = await fetch('/start_scheduler', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(formData)
                });
                
                const result = await response.json();
                
                if (!result.success) {
                    addLog('error', `❌ ${result.message}`);
                    resetButtons();
                }
            } catch (error) {
                addLog('error', `❌ Lỗi: ${error.message}`);
                resetButtons();
            }
        });
        
        function stopScheduler() {
            if (confirm('Bạn có chắc muốn dừng scheduler?')) {
                fetch('/stop_scheduler', { method: 'POST' })
                    .then(response => response.json())
                    .then(result => {
                        addLog('warning', result.message);
                        resetButtons();
                    });
            }
        }
        
        function resetButtons() {
            document.getElementById('startBtn').disabled = false;
            document.getElementById('startBtn').innerHTML = '🚀 Bắt đầu Scheduler';
            document.getElementById('stopBtn').classList.add('hidden');
            document.getElementById('statusText').textContent = 'Đã dừng';
            document.getElementById('statusText').classList.remove('status-running');
            document.getElementById('statusText').classList.add('status-stopped');
        }
        
        function addLog(type, message) {
            const logContainer = document.getElementById('logContainer');
            const entry = document.createElement('div');
            entry.className = `log-entry log-${type}`;
            const timestamp = new Date().toLocaleTimeString('vi-VN');
            entry.textContent = `[${timestamp}] ${message}`;
            logContainer.appendChild(entry);
            logContainer.scrollTop = logContainer.scrollHeight;
        }
        
        // SSE để nhận log real-time
        let eventSource;
        
        function startLogStream() {
            eventSource = new EventSource('/logs');
            eventSource.onmessage = (event) => {
                const data = JSON.parse(event.data);
                addLog(data.type, data.message);
                
                if (data.next_session) {
                    document.getElementById('nextSession').textContent = data.next_session;
                }
            };
        }
        
        startLogStream();
        
        // Update time every minute
        setInterval(() => {
            const now = new Date();
            const timeStr = now.toLocaleTimeString('vi-VN');
            // Update if needed
        }, 60000);
    </script>
</body>
</html>
'''

class FacebookSchedulerBot:
    def __init__(self, config):
        self.config = config
        self.driver = None
        self.wait = None
        self.logs = []
        self.is_logged_in = False

    def log(self, message, log_type='info'):
        """Ghi log"""
        timestamp = time.strftime("%H:%M:%S")
        log_entry = {'type': log_type, 'message': message, 'timestamp': timestamp}
        self.logs.append(log_entry)
        print(f"[{timestamp}] {message}")

    def get_logs(self):
        """Lấy tất cả logs"""
        return self.logs

    def random_delay(self, min_sec, max_sec):
        """Delay ngẫu nhiên"""
        delay = random.uniform(min_sec, max_sec)
        time.sleep(delay)

    def slow_type(self, element, text):
        """Gõ chậm như người thật"""
        for char in text:
            element.send_keys(char)
            time.sleep(random.uniform(0.05, 0.15))

    def setup_driver(self):
        """Khởi tạo Chrome driver"""
        try:
            self.log("Đang khởi tạo Chrome driver...", 'info')

            chrome_options = Options()
            chrome_options.add_argument('--disable-blink-features=AutomationControlled')
            chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
            chrome_options.add_experimental_option('useAutomationExtension', False)
            chrome_options.add_argument('--disable-notifications')
            chrome_options.add_argument('--start-maximized')
            chrome_options.add_argument('--lang=vi')

            service = Service(ChromeDriverManager().install())
            self.driver = webdriver.Chrome(service=service, options=chrome_options)
            self.wait = WebDriverWait(self.driver, 10)

            self.driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")

            self.log("✓ Chrome driver đã sẵn sàng!", 'success')
            return True

        except Exception as e:
            self.log(f"❌ Lỗi khởi tạo driver: {str(e)}", 'error')
            return False

    def login_facebook(self):
        """Đăng nhập Facebook (chỉ 1 lần)"""
        if self.is_logged_in:
            self.log("✓ Đã đăng nhập từ trước", 'info')
            return True

        try:
            self.log("🔐 Đang đăng nhập Facebook...", 'step')
            self.driver.get("https://www.facebook.com")
            self.random_delay(3, 5)

            # Nhập email
            email_input = self.wait.until(EC.presence_of_element_located((By.ID, "email")))
            self.slow_type(email_input, self.config['email'])
            self.random_delay(1, 2)

            # Nhập password
            password_input = self.driver.find_element(By.ID, "pass")
            self.slow_type(password_input, self.config['password'])
            self.random_delay(1, 2)

            # Click đăng nhập
            login_btn = self.driver.find_element(By.NAME, "login")
            login_btn.click()

            self.log("⏳ Đang chờ Facebook xử lý...", 'info')
            self.random_delay(8, 12)

            current_url = self.driver.current_url

            # Kiểm tra đăng nhập thành công
            login_success = False
            if "login" not in current_url.lower():
                login_success = True

            try:
                self.driver.find_element(By.XPATH, "//input[@type='search']")
                login_success = True
            except:
                pass

            if "checkpoint" in current_url.lower():
                self.log("⚠️ Facebook yêu cầu xác minh! Vui lòng xác minh trong 60 giây...", 'warning')
                for i in range(60):
                    time.sleep(1)
                    new_url = self.driver.current_url
                    if "checkpoint" not in new_url.lower() and "login" not in new_url.lower():
                        self.log("✓ Đã xác minh thành công!", 'success')
                        login_success = True
                        break

            if login_success:
                self.log("✓ Đăng nhập thành công!", 'success')
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
        """Mở nhóm và scroll để load bài viết"""
        try:
            self.log(f"📂 Đang mở nhóm: {group_url[:50]}...", 'info')
            self.driver.get(group_url)
            self.random_delay(5, 7)

            # Scroll để load bài
            max_scrolls = 15
            for i in range(max_scrolls):
                current_forms = len(self.driver.find_elements(By.TAG_NAME, "form"))

                if current_forms >= post_count:
                    self.log(f"✓ Đã load đủ {current_forms} form", 'success')
                    break

                self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                self.random_delay(2, 3)

                if (i + 1) % 5 == 0:
                    self.log(f"   Scroll lần {i+1}, có {current_forms} form", 'info')

            # Scroll lên đầu
            self.driver.execute_script("window.scrollTo(0, 0);")
            self.random_delay(1, 2)
            self.driver.execute_script("window.scrollTo(0, 300);")
            self.random_delay(1, 2)

            final_forms = len(self.driver.find_elements(By.TAG_NAME, "form"))
            self.log(f"✓ Sẵn sàng comment {min(final_forms, post_count)} bài", 'success')

            return min(final_forms, post_count)

        except Exception as e:
            self.log(f"❌ Lỗi mở nhóm: {str(e)}", 'error')
            return 0

    def find_and_click_comment_area(self, post_index):
        """Click vào khu vực comment"""
        try:
            forms = self.driver.find_elements(By.TAG_NAME, "form")
            if post_index >= len(forms):
                return None

            form = forms[post_index]
            self.driver.execute_script(
                "arguments[0].scrollIntoView({behavior: 'smooth', block: 'center'});",
                form
            )
            self.random_delay(1.5, 2)

            click_selectors = [
                (By.XPATH, ".//div[contains(@aria-label, 'Write a comment')]"),
                (By.XPATH, ".//div[contains(@aria-label, 'Viết bình luận')]"),
                (By.XPATH, ".//div[contains(text(), 'Write a comment')]"),
                (By.XPATH, ".//div[contains(text(), 'Viết bình luận')]"),
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

            # Fallback: click vào form
            self.driver.execute_script("arguments[0].click();", form)
            self.random_delay(1, 1.5)
            return form

        except Exception as e:
            return None

    def find_comment_box(self, post_index):
        """Tìm ô comment"""
        try:
            forms = self.driver.find_elements(By.TAG_NAME, "form")
            if post_index >= len(forms):
                return None

            form = forms[post_index]

            selectors = [
                (By.XPATH, ".//p[@contenteditable='true']"),
                (By.XPATH, ".//div[@contenteditable='true' and @role='textbox']"),
                (By.XPATH, ".//*[@role='textbox']"),
                (By.XPATH, ".//*[@contenteditable='true']"),
            ]

            for by, selector in selectors:
                try:
                    element = form.find_element(by, selector)
                    if element.is_displayed() and element.is_enabled():
                        return element
                except:
                    continue

            return None

        except Exception as e:
            return None

    def comment_on_group(self, group_url, post_count=2):
        """Comment vào 1 nhóm"""
        global bot_running

        try:
            available_posts = self.open_group_and_scroll(group_url, post_count)

            if available_posts == 0:
                self.log("⚠️ Không tìm thấy bài viết nào", 'warning')
                return 0

            comments = self.config['comments']
            delay_minutes = self.config['delayMinutes']
            success_count = 0

            for i in range(min(available_posts, post_count)):
                if not bot_running:
                    break

                comment_text = comments[i % len(comments)]
                self.log(f"📝 Bài {i+1}/{post_count}: {comment_text[:30]}...", 'info')

                # Click vào khu vực comment
                form = self.find_and_click_comment_area(i)
                if not form:
                    self.log(f"⚠️ Không thể click bài {i+1}", 'warning')
                    continue

                # Tìm ô comment
                comment_box = self.find_comment_box(i)
                if not comment_box:
                    self.log(f"⚠️ Không tìm thấy ô comment bài {i+1}", 'warning')
                    continue

                # Gõ comment
                try:
                    self.slow_type(comment_box, comment_text)
                    self.random_delay(1, 2)

                    # Gửi
                    comment_box = self.find_comment_box(i)
                    if comment_box:
                        comment_box.send_keys(Keys.RETURN)
                        self.random_delay(2, 3)
                        success_count += 1
                        self.log(f"✅ Đã comment bài {i+1}", 'success')
                    else:
                        self.log(f"⚠️ Mất ô comment sau khi gõ", 'warning')

                except Exception as e:
                    self.log(f"⚠️ Lỗi gõ/gửi bài {i+1}: {str(e)[:50]}", 'warning')
                    continue

                # Delay giữa các bài
                if i < post_count - 1:
                    self.log(f"⏱️ Chờ {delay_minutes} phút...", 'info')
                    time.sleep(delay_minutes * 60)

            return success_count

        except Exception as e:
            self.log(f"❌ Lỗi comment nhóm: {str(e)}", 'error')
            return 0

    def run_session(self, session_name):
        """Chạy 1 phiên (sáng hoặc chiều)"""
        global bot_running

        try:
            self.log(f"{'='*50}", 'step')
            self.log(f"🎯 BẮT ĐẦU PHIÊN {session_name.upper()}", 'step')
            self.log(f"{'='*50}", 'step')

            groups = self.config['groups']
            group_delay = self.config['groupDelayMinutes']
            total_success = 0

            for idx, group_url in enumerate(groups):
                if not bot_running:
                    break

                self.log(f"\n{'─'*50}", 'info')
                self.log(f"📍 Nhóm {idx+1}/{len(groups)}", 'step')
                self.log(f"{'─'*50}", 'info')

                success = self.comment_on_group(group_url, post_count=2)
                total_success += success

                # Delay giữa các nhóm
                if idx < len(groups) - 1:
                    self.log(f"⏱️ Chờ {group_delay} phút trước nhóm tiếp theo...", 'info')
                    time.sleep(group_delay * 60)

            self.log(f"\n{'='*50}", 'success')
            self.log(f"✅ HOÀN THÀNH PHIÊN {session_name.upper()}", 'success')
            self.log(f"   → Comment thành công: {total_success} bài", 'success')
            self.log(f"{'='*50}", 'success')

        except Exception as e:
            self.log(f"❌ Lỗi phiên {session_name}: {str(e)}", 'error')

# Scheduler
def schedule_worker(bot_config):
    """Worker chạy schedule"""
    global bot_running, scheduler_running, bot_instance

    scheduler_running = True
    bot_instance = FacebookSchedulerBot(bot_config)

    # Setup driver và login 1 lần
    if not bot_instance.setup_driver():
        scheduler_running = False
        return

    if not bot_instance.login_facebook():
        scheduler_running = False
        return

    bot_instance.log("✅ Scheduler đã sẵn sàng!", 'success')

    # Thiết lập schedule
    morning_time = bot_config['morningTime']
    afternoon_time = bot_config['afternoonTime']

    def morning_job():
        if bot_running:
            bot_instance.run_session("Buổi sáng")

    def afternoon_job():
        if bot_running:
            bot_instance.run_session("Buổi chiều")

    schedule.every().day.at(morning_time).do(morning_job)
    schedule.every().day.at(afternoon_time).do(afternoon_job)

    bot_instance.log(f"📅 Đã lên lịch:", 'info')
    bot_instance.log(f"   🌅 Sáng: {morning_time}", 'info')
    bot_instance.log(f"   🌆 Chiều: {afternoon_time}", 'info')

    # Kiểm tra xem có phiên nào sắp chạy không (trong 5 phút)
    now = datetime.now()
    morning_dt = datetime.strptime(morning_time, "%H:%M").replace(
        year=now.year, month=now.month, day=now.day
    )
    afternoon_dt = datetime.strptime(afternoon_time, "%H:%M").replace(
        year=now.year, month=now.month, day=now.day
    )

    # Nếu giờ hiện tại gần giờ chạy (trong 5 phút) hoặc đã qua, chạy ngay
    if (morning_dt - now).total_seconds() < 300 and (morning_dt - now).total_seconds() > 0:
        bot_instance.log(f"⚡ Phiên sáng sắp chạy trong {int((morning_dt - now).total_seconds() / 60)} phút!", 'warning')
    elif (afternoon_dt - now).total_seconds() < 300 and (afternoon_dt - now).total_seconds() > 0:
        bot_instance.log(f"⚡ Phiên chiều sắp chạy trong {int((afternoon_dt - now).total_seconds() / 60)} phút!", 'warning')
    elif now.time() > morning_dt.time() and now.time() < afternoon_dt.time():
        bot_instance.log(f"⏭️ Đã qua giờ sáng, chờ phiên chiều {afternoon_time}", 'info')
    elif now.time() < morning_dt.time():
        bot_instance.log(f"⏭️ Chờ phiên sáng {morning_time}", 'info')
    else:
        bot_instance.log(f"⏭️ Hôm nay đã hết lịch, chờ ngày mai", 'info')

    # Chạy schedule loop
    while bot_running and scheduler_running:
        schedule.run_pending()
        time.sleep(30)

    bot_instance.log("🛑 Scheduler đã dừng", 'warning')
    if bot_instance.driver:
        bot_instance.driver.quit()

# Flask Routes
@app.route('/')
def index():
    return render_template_string(HTML_TEMPLATE)

@app.route('/start_scheduler', methods=['POST'])
def start_scheduler():
    global bot_running, scheduler_running

    if scheduler_running:
        return jsonify({'success': False, 'message': 'Scheduler đang chạy!'})

    config = request.json
    bot_running = True

    thread = threading.Thread(target=schedule_worker, args=(config,))
    thread.daemon = True
    thread.start()

    return jsonify({'success': True, 'message': 'Scheduler đã khởi động!'})

@app.route('/stop_scheduler', methods=['POST'])
def stop_scheduler():
    global bot_running, scheduler_running
    bot_running = False
    scheduler_running = False
    schedule.clear()
    return jsonify({'success': True, 'message': '⏹️ Đang dừng scheduler...'})

@app.route('/logs')
def stream_logs():
    """Stream logs qua SSE"""
    def generate():
        global bot_instance
        last_log_count = 0

        while True:
            if bot_instance and len(bot_instance.logs) > last_log_count:
                for log in bot_instance.logs[last_log_count:]:
                    # Tính toán phiên tiếp theo
                    next_session = "Đang tính..."
                    try:
                        now = datetime.now()
                        morning = datetime.strptime(bot_instance.config['morningTime'], "%H:%M").replace(
                            year=now.year, month=now.month, day=now.day
                        )
                        afternoon = datetime.strptime(bot_instance.config['afternoonTime'], "%H:%M").replace(
                            year=now.year, month=now.month, day=now.day
                        )

                        if now.time() < morning.time():
                            next_session = f"Sáng {bot_instance.config['morningTime']}"
                        elif now.time() < afternoon.time():
                            next_session = f"Chiều {bot_instance.config['afternoonTime']}"
                        else:
                            next_session = f"Sáng {bot_instance.config['morningTime']} (ngày mai)"
                    except:
                        pass

                    yield f"data: {{'type': '{log['type']}', 'message': '{log['message']}', 'next_session': '{next_session}'}}\n\n"
                last_log_count = len(bot_instance.logs)

            time.sleep(0.5)

            if not bot_running and not scheduler_running:
                break

    return app.response_class(generate(), mimetype='text/event-stream')

if __name__ == '__main__':
    print("=" * 60)
    print("🤖 Facebook Auto Scheduler Bot")
    print("=" * 60)
    print("📱 Mở trình duyệt và truy cập:")
    print("   http://localhost:5000")
    print("=" * 60)
    print("⏰ Chức năng:")
    print("   - Tự động comment vào 10 nhóm")
    print("   - Buổi sáng: 2 bài/nhóm")
    print("   - Buổi chiều: 2 bài/nhóm")
    print("   - Chạy liên tục đến khi tắt")
    print("=" * 60)
    app.run(debug=False, host='0.0.0.0', port=1111)