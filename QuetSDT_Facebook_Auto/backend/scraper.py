from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from selenium.common.exceptions import TimeoutException, NoSuchElementException
import time
import logging
from datetime import datetime
import sys
import os
import re

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    from config import Config
except ImportError:
    from .config import Config


class FacebookScraper:
    def __init__(self, headless=False):
        self.driver = None
        self.wait = None
        self.headless = headless
        self.logger = self._setup_logger()

    def _setup_logger(self):
        """Cấu hình logging - Fix Unicode cho Windows"""
        logger = logging.getLogger('FacebookScraper')
        logger.setLevel(logging.INFO)

        if not logger.handlers:
            log_dir = Config.LOG_DIR if hasattr(Config, 'LOG_DIR') else 'logs'
            os.makedirs(log_dir, exist_ok=True)

            # File handler với UTF-8 encoding
            fh = logging.FileHandler(
                f'{log_dir}/scraper_{datetime.now().strftime("%Y%m%d")}.log',
                encoding='utf-8'  # Fix Unicode
            )
            fh.setLevel(logging.INFO)

            formatter = logging.Formatter(
                '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
            )
            fh.setFormatter(formatter)
            logger.addHandler(fh)

        return logger

    def setup_driver(self):
        """Khởi tạo Chrome driver - Fixed cho Windows"""
        try:
            self.logger.info("Setting up Chrome driver...")

            options = webdriver.ChromeOptions()

            if self.headless:
                options.add_argument('--headless=new')

            # Essential options
            options.add_argument('--start-maximized')
            options.add_argument('--disable-blink-features=AutomationControlled')
            options.add_argument('--disable-dev-shm-usage')
            options.add_argument('--no-sandbox')
            options.add_argument('--disable-gpu')
            options.add_argument('--window-size=1920,1080')
            options.add_argument('--ignore-certificate-errors')
            options.add_argument('--ignore-ssl-errors')

            # Prevent detection
            options.add_experimental_option("excludeSwitches", ["enable-automation"])
            options.add_experimental_option('useAutomationExtension', False)

            # FIX: Clear cache và cài lại ChromeDriver
            self.logger.info("Installing ChromeDriver...")

            try:
                # Xóa cache cũ
                import shutil
                cache_path = os.path.join(os.path.expanduser('~'), '.wdm')
                if os.path.exists(cache_path):
                    try:
                        shutil.rmtree(cache_path)
                        self.logger.info("Cleared ChromeDriver cache")
                    except:
                        pass

                # Cài ChromeDriver mới
                service = Service(ChromeDriverManager().install())

            except Exception as e:
                self.logger.error(f"ChromeDriver installation error: {str(e)}")
                raise Exception("Could not install ChromeDriver. Please check your internet connection.")

            # Initialize driver
            self.logger.info("Starting Chrome browser...")
            self.driver = webdriver.Chrome(service=service, options=options)

            wait_timeout = Config.WAIT_TIMEOUT if hasattr(Config, 'WAIT_TIMEOUT') else 20
            self.wait = WebDriverWait(self.driver, wait_timeout)

            self.logger.info("Chrome driver initialized successfully")
            return True

        except Exception as e:
            self.logger.error(f"Failed to initialize driver: {str(e)}")
            self.logger.error("Troubleshooting:")
            self.logger.error("1. Check internet connection")
            self.logger.error("2. Run: pip uninstall selenium webdriver-manager -y")
            self.logger.error("3. Run: pip install selenium==4.16.0 webdriver-manager==4.0.1")
            self.logger.error("4. Delete folder: C:\\Users\\YourUser\\.wdm")
            return False

    def login(self, email, password):
        """Đăng nhập Facebook"""
        try:
            self.logger.info("Starting Facebook login...")
            self.driver.get("https://www.facebook.com")
            time.sleep(5)

            email_input = self.wait.until(
                EC.presence_of_element_located((By.ID, "email"))
            )
            email_input.clear()
            email_input.send_keys(email)
            time.sleep(3)

            password_input = self.driver.find_element(By.ID, "pass")
            password_input.clear()
            password_input.send_keys(password)
            time.sleep(3)

            login_button = self.driver.find_element(By.NAME, "login")
            login_button.click()
            time.sleep(5)

            if "login" in self.driver.current_url.lower():
                self.logger.error("Login failed - still on login page")
                return False

            self.logger.info("Login successful")
            return True

        except Exception as e:
            self.logger.error(f"Login error: {str(e)}")
            return False

    def search(self, keyword):
        """Tìm kiếm trên Facebook"""
        try:
            self.logger.info(f"Searching for: {keyword}")

            search_selectors = [
                "input[type='search'][placeholder*='Tìm kiếm']",
                "input[aria-label*='Tìm kiếm']",
                "input[placeholder*='Search']",
                "input[placeholder*='Tìm kiếm trên Facebook']"
            ]

            search_box = None
            for selector in search_selectors:
                try:
                    search_box = self.wait.until(
                        EC.presence_of_element_located((By.CSS_SELECTOR, selector))
                    )
                    break
                except:
                    continue

            if not search_box:
                self.logger.error("Could not find search box")
                return False

            search_box.clear()
            time.sleep(3)
            search_box.send_keys(keyword)
            time.sleep(3)
            search_box.send_keys(Keys.RETURN)
            time.sleep(5)

            if not self._click_pages_tab():
                self.logger.error("Could not click Pages tab")
                return False

            time.sleep(5)
            self.logger.info("Successfully navigated to Pages tab")
            return True

        except Exception as e:
            self.logger.error(f"Search error: {str(e)}")
            return False

    def _click_pages_tab(self):
        """Click vào tab Trang (Pages)"""
        try:
            self.logger.info("Trying to click Pages tab...")

            pages_tab_selectors = [
                "//span[contains(text(), 'Trang')]",
                "//span[text()='Trang']",
                "//span[contains(text(), 'Pages')]",
                "//span[text()='Pages']",
                "//a[contains(@href, '/search/pages/')]",
                "//a[@aria-label='Trang']",
                "//a[@aria-label='Pages']",
                "//div[@role='navigation']//span[contains(text(), 'Trang')]",
            ]

            for selector in pages_tab_selectors:
                try:
                    element = self.driver.find_element(By.XPATH, selector)
                    self.driver.execute_script("arguments[0].scrollIntoView(true);", element)
                    time.sleep(2)

                    try:
                        element.click()
                    except:
                        self.driver.execute_script("arguments[0].click();", element)

                    self.logger.info(f"Successfully clicked Pages tab")
                    return True

                except:
                    continue

            self.logger.error("Could not find Pages tab")
            self.take_screenshot("pages_tab_not_found.png")
            return False

        except Exception as e:
            self.logger.error(f"Error clicking Pages tab: {str(e)}")
            return False

    def extract_data(self):
        """Lấy dữ liệu danh sách TRANG và chi tiết"""
        try:
            self.logger.info("Extracting Pages data...")

            # Scroll để load trang
            self.logger.info("Scrolling to load more pages...")
            self._continuous_scroll(duration_seconds=60)

            data = []

            # Tìm page containers
            self.logger.info("Finding page containers...")
            page_container_selectors = [
                "div[role='article']",
                "div[data-pagelet*='SearchResult']",
                "div[class*='x1yztbdb']",
            ]

            page_containers = []
            for selector in page_container_selectors:
                try:
                    found = self.driver.find_elements(By.CSS_SELECTOR, selector)
                    if found:
                        page_containers = found
                        self.logger.info(f"Found {len(page_containers)} page containers")
                        break
                except:
                    continue

            if not page_containers:
                self.logger.warning("No page containers found")
                return []

            # Lấy danh sách link
            page_links = []
            for idx, container in enumerate(page_containers, 1):
                try:
                    name = None
                    name_selectors = [
                        "span.x193iq5w.xeuugli",
                        "a[role='link'] span",
                        "h2 span",
                    ]
                    for sel in name_selectors:
                        try:
                            name_elem = container.find_element(By.CSS_SELECTOR, sel)
                            text = name_elem.text.strip()
                            if text and len(text) > 3 and len(text) < 200:
                                name = text
                                break
                        except:
                            continue

                    if not name:
                        continue

                    link = None
                    link_selectors = [
                        "a[href*='/profile.php?id=']",
                        "a[href*='facebook.com/'][role='link']",
                        "a[role='link']",
                    ]
                    for sel in link_selectors:
                        try:
                            link_elem = container.find_element(By.CSS_SELECTOR, sel)
                            href = link_elem.get_attribute('href')
                            if href and 'facebook.com' in href:
                                link = href
                                break
                        except:
                            continue

                    if link:
                        page_links.append({'name': name, 'link': link})
                        self.logger.info(f"Found page {idx}: {name[:40]}")

                except Exception as e:
                    continue

            # Loại duplicate
            unique_links = []
            seen = set()
            for item in page_links:
                if item['link'] not in seen:
                    seen.add(item['link'])
                    unique_links.append(item)

            self.logger.info(f"Found {len(unique_links)} unique pages")

            # Lấy chi tiết từng trang
            self.logger.info("Extracting detailed information...")

            for idx, page in enumerate(unique_links, 1):
                self.logger.info(f"Processing page {idx}/{len(unique_links)}: {page['name'][:40]}")

                page_detail = self._extract_page_details(page['link'])

                if page_detail:
                    page_detail['name'] = page['name']
                    page_detail['link'] = page['link']
                    data.append(page_detail)
                else:
                    data.append({
                        'name': page['name'],
                        'link': page['link'],
                        'phone': 'N/A',
                        'address': 'N/A',
                        'description': 'N/A'
                    })

                time.sleep(3)

            self.logger.info(f"Completed extracting {len(data)} pages")
            return data

        except Exception as e:
            self.logger.error(f"Data extraction error: {str(e)}")
            return []

    def _extract_page_details(self, page_url):
        """Lấy thông tin chi tiết từ trang"""
        try:
            self.driver.get(page_url)
            time.sleep(5)

            self.driver.execute_script("window.scrollTo(0, 800);")
            time.sleep(2)

            page_data = {
                'phone': 'N/A',
                'address': 'N/A',
                'description': 'N/A'
            }

            # Lấy mô tả
            description_selectors = [
                "//div[contains(@class, 'x2b8uid')]//span[contains(@class, 'xdmh292')]",
                "//div[@class='xieb3on']//span[contains(@class, 'xdmh292')]",
                "//span[contains(@style, 'font-size: 15px')]",
            ]

            for selector in description_selectors:
                try:
                    desc_elements = self.driver.find_elements(By.XPATH, selector)
                    for elem in desc_elements:
                        text = elem.text.strip()
                        if text and len(text) > 50 and 'facebook.com' not in text.lower():
                            page_data['description'] = text[:500]
                            break
                    if page_data['description'] != 'N/A':
                        break
                except:
                    continue

            # Lấy số điện thoại
            phone_patterns = [
                r'\+?\d{1,4}[\s\-]?\d{1,4}[\s\-]?\d{1,4}[\s\-]?\d{1,4}',
                r'\d{10,11}',
            ]

            page_text = self.driver.find_element(By.TAG_NAME, 'body').text

            for pattern in phone_patterns:
                matches = re.findall(pattern, page_text)
                if matches:
                    for match in matches:
                        digits = re.sub(r'\D', '', match)
                        if 9 <= len(digits) <= 12:
                            page_data['phone'] = match
                            break
                if page_data['phone'] != 'N/A':
                    break

            # Lấy địa chỉ
            address_keywords = ['vietnam', 'hà nội', 'hồ chí minh', 'đà nẵng', 'city', 'district']
            address_selectors = [
                "//span[contains(text(), 'Vietnam')]",
                "//span[contains(text(), 'City')]",
            ]

            for selector in address_selectors:
                try:
                    address_elements = self.driver.find_elements(By.XPATH, selector)
                    for elem in address_elements:
                        text = elem.text.strip()
                        if text and any(keyword in text.lower() for keyword in address_keywords):
                            if 20 < len(text) < 200:
                                page_data['address'] = text
                                break
                    if page_data['address'] != 'N/A':
                        break
                except:
                    continue

            self.logger.info(f"Phone: {page_data['phone']}, Address: {page_data['address'][:30]}")
            return page_data

        except Exception as e:
            self.logger.error(f"Error extracting details: {str(e)}")
            return None

    def _continuous_scroll(self, duration_seconds=60):
        """Scroll liên tục"""
        try:
            start_time = time.time()
            scroll_count = 0
            last_height = self.driver.execute_script("return document.body.scrollHeight")

            while (time.time() - start_time) < duration_seconds:
                self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                scroll_count += 1
                time.sleep(3)

                new_height = self.driver.execute_script("return document.body.scrollHeight")

                if new_height > last_height:
                    last_height = new_height
                else:
                    self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight - 1000);")
                    time.sleep(1)

            self.logger.info(f"Completed {scroll_count} scrolls")

        except Exception as e:
            self.logger.error(f"Scroll error: {str(e)}")

    def take_screenshot(self, filename):
        """Chụp màn hình"""
        try:
            log_dir = Config.LOG_DIR if hasattr(Config, 'LOG_DIR') else 'logs'
            os.makedirs(log_dir, exist_ok=True)

            filepath = f"{log_dir}/{filename}"
            self.driver.save_screenshot(filepath)
            self.logger.info(f"Screenshot saved: {filepath}")
            return filepath
        except Exception as e:
            self.logger.error(f"Screenshot error: {str(e)}")
            return None

    def close(self):
        """Đóng browser"""
        if self.driver:
            try:
                self.driver.quit()
                self.logger.info("Browser closed")
            except Exception as e:
                self.logger.error(f"Error closing browser: {str(e)}")