# ============================================================================
# BACKEND - Flask API Server (app.py)
# VERSION: Kết nối vào Chrome cá nhân đang chạy (Remote Debugging)
# KHÔNG mở Chrome mới - dùng Chrome của bạn đang dùng
# ============================================================================

from flask import Flask, jsonify, request, send_file
from flask_cors import CORS
from bs4 import BeautifulSoup
import re
import time
import csv
import json
import io
from datetime import datetime
from threading import Thread, Event
import pandas as pd
import os
from pathlib import Path

# pip install selenium
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

app = Flask(__name__)
CORS(app)

# Sự kiện để chờ/nhả xác nhận từ người dùng
_confirm_event = Event()

# Sự kiện để dừng scraping giữa chừng
_stop_event = Event()

# Global variable để tracking progress
scraping_progress = {
    'status': 'idle',           # idle | waiting_confirm | running | completed | error
    'progress': 0,
    'total': 0,
    'current_task': '',
    'waiting_confirm': False,
    'confirm_message': '',
    'companies': [],
    'logs': [],
    'chrome_connected': False   # Trạng thái kết nối Chrome
}

# Cổng remote debugging của Chrome (mặc định 9222)
CHROME_DEBUG_PORT = 9222


# ============================================================================
# SCRAPER CLASS
# ============================================================================

class HSCTVNScraper:
    def __init__(self, delay=1):
        self.base_url = "https://hsctvn.com"
        self.delay = delay
        self.driver = None

    # ── Helpers ──────────────────────────────────────────────────────────────

    def extract_province(self, full_address):
        if not full_address:
            return ''
        parts = [p.strip() for p in full_address.split(',') if p.strip()]
        if not parts:
            return ''
        while parts and re.match(r'^Việt\s*Nam$', parts[-1], re.IGNORECASE):
            parts.pop()
        if not parts:
            return ''
        last_part = parts[-1]
        province = re.sub(
            r'^(Tỉnh|Thành phố|Thành Phố|TP\.|TP|T\.P\.?)\s+',
            '',
            last_part,
            flags=re.IGNORECASE
        ).strip()
        return province if province else last_part

    def log(self, message, log_type='info'):
        timestamp = datetime.now().strftime('%H:%M:%S')
        scraping_progress['logs'].append({
            'time': timestamp,
            'type': log_type,
            'message': message
        })

    def update_progress(self, current, total, task):
        scraping_progress['progress'] = current
        scraping_progress['total'] = total
        scraping_progress['current_task'] = task

    # ── Kết nối Chrome cá nhân ───────────────────────────────────────────────

    def _connect_to_chrome(self):
        """Kết nối vào Chrome cá nhân đang chạy qua Remote Debugging Port."""
        try:
            options = Options()
            # Kết nối vào Chrome đang chạy thay vì mở Chrome mới
            options.add_experimental_option("debuggerAddress", f"127.0.0.1:{CHROME_DEBUG_PORT}")

            self.driver = webdriver.Chrome(options=options)
            self.log(f'✅ Đã kết nối vào Chrome cá nhân (port {CHROME_DEBUG_PORT})', 'success')
            scraping_progress['chrome_connected'] = True
            return True
        except Exception as e:
            error_msg = str(e)
            if 'unable to connect' in error_msg.lower() or 'connection refused' in error_msg.lower():
                self.log(
                    f'❌ Không kết nối được Chrome! '
                    f'Hãy bật Chrome với lệnh remote debugging (xem hướng dẫn trên UI)',
                    'error'
                )
            else:
                self.log(f'❌ Lỗi kết nối Chrome: {error_msg}', 'error')
            scraping_progress['chrome_connected'] = False
            return False

    def _disconnect(self):
        """Ngắt kết nối Selenium — KHÔNG đóng tab, KHÔNG quit Chrome."""
        # driver.close() đóng tab hiện tại → Chrome về New Tab → SAI
        # driver.quit()  đóng toàn bộ Chrome          → SAI
        # Đúng: chỉ bỏ tham chiếu, để Chrome tự nhiên
        self.driver = None
        scraping_progress['chrome_connected'] = False

    # ── Confirm gate ─────────────────────────────────────────────────────────

    def _wait_for_confirm(self, message='Vui lòng xác nhận để tiếp tục...'):
        _confirm_event.clear()
        scraping_progress['waiting_confirm'] = True
        scraping_progress['confirm_message'] = message
        scraping_progress['status'] = 'waiting_confirm'
        self.log(f'⏸  {message}', 'warning')
        _confirm_event.wait()
        scraping_progress['waiting_confirm'] = False
        scraping_progress['confirm_message'] = ''
        scraping_progress['status'] = 'running'
        self.log('▶  Tiếp tục...', 'success')

    # ── Fetch page ───────────────────────────────────────────────────────────

    def get_page(self, url):
        max_retries = 3
        for attempt in range(1, max_retries + 1):

            # ✅ THÊM: thoát ngay đầu mỗi lần retry
            if _stop_event.is_set():
                return None

            try:
                self.log(f'Đang tải: {url} (lần {attempt}/{max_retries})', 'info')
                self.driver.execute_script(f"window.location.href = arguments[0]", url)
                WebDriverWait(self.driver, 8).until(  # ✅ Bước 3: đổi 20 → 8
                    EC.presence_of_element_located((By.TAG_NAME, 'body'))
                )
                current_url = self.driver.current_url
                if 'google.com' in current_url or current_url in ('chrome://newtab/', 'about:blank'):
                    raise Exception(f'Chrome vẫn đang ở New Tab/Google thay vì tải {url}')
                time.sleep(self.delay)
                return self.driver.page_source

            except Exception as e:
                self.log(f'Lỗi tải {url} (lần {attempt}): {str(e)}', 'warning')

                if attempt < max_retries:
                    # ✅ THÊM: kiểm tra trước khi thử lại fallback
                    if _stop_event.is_set():
                        return None
                    try:
                        self.driver.get(url)
                        time.sleep(self.delay)
                        return self.driver.page_source
                    except Exception:
                        pass

                # ✅ THÊM: kiểm tra trước khi sleep chờ retry
                if _stop_event.is_set():
                    return None
                time.sleep(self.delay)

        self.log(f'✗ Không thể tải {url} sau {max_retries} lần', 'error')
        return None

    # ── Parse ─────────────────────────────────────────────────────────────────

    def parse_company_list(self, html):
        soup = BeautifulSoup(html, 'html.parser')
        companies = []

        for item in soup.find_all('li'):
            h3 = item.find('h3')
            if not h3:
                continue
            link = h3.find('a')
            if not link:
                continue

            href = link.get('href', '')
            if href.startswith('http'):
                detail_url = href
            elif href.startswith('/'):
                detail_url = self.base_url + href
            else:
                detail_url = self.base_url + '/' + href

            company = {
                'name': link.get_text(strip=True),
                'detail_url': detail_url,
                'tax_code': '',
                'address': '',
                'phone': '',
                'industry': ''
            }

            div = item.find('div')
            if div:
                text = div.get_text()
                addr_match = re.search(r'Địa chỉ:\s*(.+?)(?:Mã số thuế:|$)', text)
                if addr_match:
                    company['address'] = self.extract_province(addr_match.group(1).strip())
                tax_match = re.search(r'Mã số thuế:\s*(\d+)', text)
                if tax_match:
                    company['tax_code'] = tax_match.group(1)

            companies.append(company)

        return companies

    def get_details_from_detail(self, url):
        try:
            html = self.get_page(url)
            if _stop_event.is_set():
                return {'phone': '', 'industry': ''}


            if _stop_event.is_set():
                return {'phone': '', 'industry': ''}
            html = self.get_page(url)
            if not html:
                return {'phone': '', 'industry': ''}

            soup = BeautifulSoup(html, 'html.parser')
            detail_block = soup.select_one('div.module_data.detail') or soup

            # --- Số điện thoại ---
            phone_li = None
            for li in detail_block.find_all('li'):
                icon = li.find('i', class_=lambda c: c and 'fa-phone' in c)
                if icon:
                    phone_li = li
                    break

            text_source = (phone_li.get_text(separator=' ', strip=True) if phone_li
                           else detail_block.get_text(separator=' ', strip=True))

            phone = ''
            phone_patterns = [
                r'(?:Điện thoại|Điện thoại liên hệ|Số điện thoại|Hotline|Phone|Tel|ĐT)[:\s]*([0-9\s\.\-\(\)]{9,20})',
                r'(?:Di động|Mobile)[:\s]*([0-9\s\.\-\(\)]{9,20})',
                r'(?:SĐT|SDT)[:\s]*([0-9\s\.\-\(\)]{9,20})'
            ]
            for pattern in phone_patterns:
                matches = re.findall(pattern, text_source, re.IGNORECASE)
                if matches:
                    p = re.sub(r'\s+', ' ', matches[0].strip())
                    if len(re.sub(r'[^\d]', '', p)) >= 9:
                        phone = p
                        break

            # --- Ngành nghề chính ---
            industry = ''
            for li in detail_block.find_all('li'):
                icon = li.find('i', class_=lambda c: c and 'fa-anchor' in c)
                if icon:
                    a_tag = li.find('a')
                    if a_tag:
                        industry = a_tag.get_text(strip=True)
                    else:
                        text = li.get_text(separator=' ', strip=True)
                        m = re.search(r'Ngành nghề chính[:\s]*(.+)', text)
                        if m:
                            industry = m.group(1).strip()
                    break

            return {'phone': phone, 'industry': industry}

        except Exception as e:
            self.log(f'Lỗi get_details {url}: {str(e)}', 'error')
            return {'phone': '', 'industry': ''}

    # ── Main scrape ───────────────────────────────────────────────────────────

    def scrape(self, area=None, month=None, from_page=None, to_page=None,
               get_phones=True, start_url=None):
        try:
            scraping_progress['status'] = 'running'
            scraping_progress['companies'] = []
            scraping_progress['logs'] = []

            MAX_PAGES = 50
            if from_page is None:
                from_page = 1
            if to_page is None or to_page < from_page:
                to_page = from_page
            if (to_page - from_page + 1) > MAX_PAGES:
                to_page = from_page + MAX_PAGES - 1
                self.log(f'⚠ Giới hạn tối đa {MAX_PAGES} trang → đến trang {to_page}', 'warning')

            self.log(f'Bắt đầu scraping từ trang {from_page} đến {to_page}', 'info')
            total_pages = to_page - from_page + 1
            all_companies = []

            # ── 1. Kết nối Chrome cá nhân ─────────────────────────────────
            self.log('🔌 Đang kết nối vào Chrome cá nhân...', 'info')
            if not self._connect_to_chrome():
                scraping_progress['status'] = 'error'
                return []

            # ── 2. Tính URL đúng cho from_page rồi mới mở ────────────────
            def build_page_url(page_num):
                if start_url:
                    normalized = start_url.rstrip('/')
                    pm = re.match(r'^(.*?/page-)(\d+)$', normalized)
                    if pm:
                        return f"{pm.group(1)}{page_num}"
                    else:
                        return normalized if page_num == 1 else f"{normalized}/page-{page_num}"
                else:
                    return (f"{self.base_url}/{month}-{area}" if page_num == 1
                            else f"{self.base_url}/{month}-{area}/page-{page_num}")

            # ── FIX PAGE BUG: Mở đúng trang from_page (không phải URL gốc) ──
            first_url = build_page_url(from_page)
            self.log(f'Mở trang: {first_url}', 'info')
            self.driver.get(first_url)

            self._wait_for_confirm(
                f'Trang {from_page} đã mở trong Chrome. '
                'Nếu có Cloudflare → tick "Verify you are human" → chờ trang load xong → nhấn ✅ Xác nhận.'
            )

            # ── FIX CLOUDFLARE: Kiểm tra trang đã vượt qua Cloudflare chưa ──
            time.sleep(1)
            current_src = self.driver.page_source
            if 'Performing security verification' in current_src or 'cf-browser-verification' in current_src:
                self.log('⚠️  Cloudflare chưa được vượt qua! Hãy tick checkbox rồi xác nhận lại.', 'warning')
                self._wait_for_confirm('Cloudflare vẫn đang chặn. Tick "Verify you are human" → chờ load → nhấn ✅ Xác nhận.')
                time.sleep(2)

            # ── 3. Phase 1: Thu thập danh sách công ty ───────────────────
            _stop_event.clear()
            for page in range(from_page, to_page + 1):
                # ── Kiểm tra lệnh dừng ──
                if _stop_event.is_set():
                    self.log('🛑 Đã dừng theo yêu cầu.', 'warning')
                    break

                url = build_page_url(page)

                self.log(f'Đang xử lý trang {page}/{to_page}: {url}', 'info')
                self.update_progress(page - from_page, total_pages, f'Đang tải trang {page}/{to_page}')

                # ── FIX: from_page đã điều hướng đúng ở trên → dùng page_source ──
                if page == from_page:
                    self.log('✓ Dùng trang đang hiển thị', 'success')
                    html = self.driver.page_source
                else:
                    html = self.get_page(url)

                if html:
                    # ── Kiểm tra Cloudflare block giữa chừng ──
                    if 'Performing security verification' in html:
                        self.log(f'⚠️  Trang {page} bị Cloudflare chặn!', 'warning')
                        self._wait_for_confirm(f'Trang {page} bị Cloudflare chặn. Giải captcha rồi nhấn ✅ Xác nhận.')
                        time.sleep(2)
                        html = self.driver.page_source

                    companies = self.parse_company_list(html)
                    self.log(f'✓ Tìm thấy {len(companies)} công ty ở trang {page}', 'success')
                    all_companies.extend(companies)
                else:
                    self.log(f'✗ Không thể tải trang {page}', 'error')

                time.sleep(self.delay)

            self.log(f'✓ Phase 1 xong. Tổng: {len(all_companies)} công ty', 'success')

            # ── 4. Phase 2: Lấy SĐT & ngành nghề ────────────────────────
            if get_phones and all_companies:
                self.log(f'Bắt đầu lấy SĐT cho {len(all_companies)} công ty...', 'info')

                for i, company in enumerate(all_companies):
                    # ── Kiểm tra lệnh dừng ──
                    if _stop_event.is_set():
                        self.log('🛑 Đã dừng theo yêu cầu (phase 2).', 'warning')
                        break

                    self.update_progress(
                        i + 1, len(all_companies),
                        f'[{i+1}/{len(all_companies)}] Đang lấy SĐT: {company["name"]}'
                    )
                    self.log(f'[{i+1}/{len(all_companies)}] {company["name"]}', 'info')

                    details = self.get_details_from_detail(company['detail_url'])
                    company['phone'] = details['phone']
                    company['industry'] = details['industry']

                    if details['phone']:
                        self.log(f'  ✓ SĐT: {details["phone"]}', 'success')
                    if details['industry']:
                        self.log(f'  ✓ Ngành: {details["industry"]}', 'success')

                    scraping_progress['companies'] = list(all_companies)

            scraping_progress['companies'] = all_companies
            scraping_progress['status'] = 'completed'
            self.log(f'🎉 Hoàn thành! Tổng cộng {len(all_companies)} công ty', 'success')
            return all_companies

        except Exception as e:
            scraping_progress['status'] = 'error'
            self.log(f'✗ Lỗi nghiêm trọng: {str(e)}', 'error')
            return []
        finally:
            self._disconnect()


# ============================================================================
# API ENDPOINTS
# ============================================================================

@app.route('/api/scrape', methods=['POST'])
def start_scraping():
    data = request.json

    start_url  = data.get('startUrl')
    area       = data.get('area', 'ha-noi')
    month      = data.get('month', 'thang-11/2025')
    from_page  = int(data.get('fromPage', 1))
    to_page    = int(data.get('toPage', 2))
    delay      = float(data.get('delay', 1))
    get_phones = data.get('getPhones', True)

    scraping_progress.update({
        'status': 'running',
        'progress': 0,
        'total': 0,
        'current_task': '',
        'waiting_confirm': False,
        'confirm_message': '',
        'companies': [],
        'logs': [],
        'chrome_connected': False
    })
    _confirm_event.clear()
    _stop_event.clear()

    def run_scraper():
        scraper = HSCTVNScraper(delay=delay)
        scraper.scrape(area, month, from_page, to_page, get_phones, start_url=start_url)

    thread = Thread(target=run_scraper, daemon=True)
    thread.start()

    return jsonify({'status': 'started'})


@app.route('/api/progress', methods=['GET'])
def get_progress():
    return jsonify(scraping_progress)


@app.route('/api/confirm', methods=['POST'])
def confirm_scraping():
    if scraping_progress.get('waiting_confirm'):
        _confirm_event.set()
        return jsonify({'status': 'confirmed'})
    return jsonify({'status': 'not_waiting'}), 400


@app.route('/api/stop', methods=['POST'])
def stop_scraping():
    """Dừng scraping giữa chừng. Dữ liệu đã thu thập vẫn được giữ lại."""
    _stop_event.set()
    # Nếu đang chờ confirm, unblock luôn để vòng lặp thoát được
    _confirm_event.set()
    scraping_progress['status'] = 'completed'
    scraping_progress['current_task'] = '🛑 Đã dừng theo yêu cầu'
    return jsonify({'status': 'stopped'})


@app.route('/api/chrome-status', methods=['GET'])
def chrome_status():
    """Kiểm tra Chrome có đang chạy với remote debugging không."""
    import socket
    try:
        s = socket.create_connection(('127.0.0.1', CHROME_DEBUG_PORT), timeout=1)
        s.close()
        return jsonify({'connected': True, 'port': CHROME_DEBUG_PORT})
    except Exception:
        return jsonify({'connected': False, 'port': CHROME_DEBUG_PORT})


@app.route('/api/download/excel', methods=['GET'])
def download_excel():
    try:
        companies = scraping_progress.get('companies', [])
        if not companies:
            return jsonify({'error': 'Không có dữ liệu để xuất Excel'}), 404

        df_data = []
        for i, company in enumerate(companies, 1):
            df_data.append({
                'STT': i,
                'Tên công ty': company.get('name', ''),
                'Mã số thuế': company.get('tax_code', ''),
                'Số điện thoại': company.get('phone', ''),
                'Ngành nghề chính': company.get('industry', ''),
                'Địa chỉ': company.get('address', ''),
                'Ngày lấy dữ liệu': datetime.now().strftime('%d/%m/%Y %H:%M:%S')
            })

        df = pd.DataFrame(df_data)
        output = io.BytesIO()
        df.to_excel(output, index=False, engine='openpyxl')
        output.seek(0)

        filename = f"companies_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
        return send_file(
            output,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            as_attachment=True,
            download_name=filename
        )
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/download/csv', methods=['GET'])
def download_csv():
    companies = scraping_progress.get('companies', [])
    output = io.StringIO()
    output.write('\ufeff')
    writer = csv.writer(output)
    writer.writerow(['STT', 'Tên công ty', 'Mã số thuế', 'Số điện thoại', 'Ngành nghề chính', 'Địa chỉ'])

    for i, company in enumerate(companies, 1):
        phone_text = company.get('phone', '')
        if phone_text and not phone_text.startswith("'"):
            phone_text = f"'{phone_text}"
        writer.writerow([
            i,
            company.get('name', ''),
            company.get('tax_code', ''),
            phone_text,
            company.get('industry', ''),
            company.get('address', '')
        ])

    output.seek(0)
    return send_file(
        io.BytesIO(output.getvalue().encode('utf-8-sig')),
        mimetype='text/csv',
        as_attachment=True,
        download_name=f'companies_{datetime.now().strftime("%Y%m%d_%H%M%S")}.csv'
    )


@app.route('/api/download/json', methods=['GET'])
def download_json():
    companies = scraping_progress.get('companies', [])
    output = json.dumps(companies, ensure_ascii=False, indent=2)
    return send_file(
        io.BytesIO(output.encode('utf-8')),
        mimetype='application/json',
        as_attachment=True,
        download_name=f'companies_{datetime.now().strftime("%Y%m%d_%H%M%S")}.json'
    )


# ============================================================================
# FRONTEND
# ============================================================================

@app.route('/')
def index():
    return '''<!DOCTYPE html>
<html lang="vi">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>HSCTVN Company Scraper</title>
    <style>
        *{margin:0;padding:0;box-sizing:border-box}
        body{
            font-family:'Segoe UI',Tahoma,Geneva,Verdana,sans-serif;
            background:linear-gradient(135deg,#eef2ff 0%,#e5e7eb 50%,#f9fafb 100%);
            min-height:100vh;padding:30px 15px;
        }
        .container{
            max-width:1320px;margin:0 auto;background:#fff;
            border-radius:18px;box-shadow:0 18px 45px rgba(15,23,42,.18);overflow:hidden;
        }
        .header{
            background:linear-gradient(135deg,#4f46e5 0%,#7c3aed 40%,#ec4899 100%);
            color:#fff;padding:36px 40px;text-align:center;
        }
        .header h1{font-size:2.4em;margin-bottom:8px;text-shadow:0 8px 20px rgba(15,23,42,.35)}
        .header p{opacity:.96;font-size:1.05em}
        .content{padding:30px 34px 36px;background:linear-gradient(180deg,#f9fafb 0%,#fff 40%)}
        .section{
            background:#fff;padding:24px 26px;border-radius:16px;margin-bottom:26px;
            border:1px solid #e5e7eb;box-shadow:0 8px 24px rgba(15,23,42,.06);
        }
        .section h2{
            margin-bottom:14px;color:#111827;display:flex;align-items:center;
            gap:10px;font-size:1.3em;font-weight:700;
        }

        /* ── Hướng dẫn Chrome ── */
        .guide-box{
            background:#f0f9ff;border:2px solid #0ea5e9;border-radius:12px;
            padding:18px 22px;margin-bottom:20px;
        }
        .guide-box h3{color:#0369a1;margin-bottom:12px;font-size:1.05em}
        .guide-box .os-tabs{display:flex;gap:8px;margin-bottom:14px}
        .os-tab{
            padding:6px 16px;border-radius:6px;border:2px solid #0ea5e9;
            background:#fff;color:#0369a1;font-weight:600;cursor:pointer;font-size:.9em;
        }
        .os-tab.active{background:#0ea5e9;color:#fff}
        .cmd-block{
            background:#1e1e1e;border-radius:8px;padding:14px 18px;
            font-family:'Courier New',monospace;font-size:.9em;color:#a3e635;
            position:relative;display:none;
        }
        .cmd-block.visible{display:block}
        .cmd-copy{
            position:absolute;top:10px;right:12px;
            background:#374151;border:none;color:#9ca3af;
            border-radius:5px;padding:4px 10px;cursor:pointer;font-size:.8em;
        }
        .cmd-copy:hover{background:#4b5563;color:#fff}

        /* ── Chrome status indicator ── */
        .chrome-status{
            display:flex;align-items:center;gap:10px;padding:12px 18px;
            border-radius:10px;margin-bottom:20px;font-weight:600;font-size:.95em;
        }
        .chrome-status.connected{background:#dcfce7;color:#16a34a;border:2px solid #86efac}
        .chrome-status.disconnected{background:#fef2f2;color:#dc2626;border:2px solid #fca5a5}
        .status-dot{width:12px;height:12px;border-radius:50%;flex-shrink:0}
        .connected .status-dot{background:#16a34a;box-shadow:0 0 0 3px rgba(22,163,74,.3)}
        .disconnected .status-dot{background:#dc2626}

        .form-grid{
            display:grid;grid-template-columns:repeat(3,minmax(0,1fr));
            column-gap:20px;row-gap:16px;margin-bottom:20px;
        }
        .form-group.full{grid-column:1/-1}
        .form-group label{display:block;margin-bottom:8px;font-weight:600;color:#333}
        .form-group input,.form-group select{
            width:100%;padding:12px;border:2px solid #e0e0e0;
            border-radius:8px;font-size:1em;transition:all .3s;
        }
        .form-group input:focus{outline:none;border-color:#667eea;box-shadow:0 0 0 3px rgba(102,126,234,.1)}
        .checkbox-group{display:flex;align-items:center;gap:10px;margin-top:15px}
        .checkbox-group input[type=checkbox]{width:20px;height:20px;cursor:pointer}

        .btn{
            background:linear-gradient(135deg,#667eea 0%,#764ba2 100%);
            color:#fff;border:none;padding:15px 40px;border-radius:10px;
            font-size:1.1em;cursor:pointer;transition:all .3s;font-weight:600;
            display:inline-flex;align-items:center;gap:10px;
        }
        .btn:hover:not(:disabled){transform:translateY(-2px);box-shadow:0 10px 30px rgba(102,126,234,.4)}
        .btn:disabled{background:#ccc;cursor:not-allowed;transform:none}
        .btn-check{
            background:linear-gradient(135deg,#0ea5e9 0%,#0284c7 100%);
            color:#fff;border:none;padding:10px 22px;border-radius:8px;
            font-size:.95em;cursor:pointer;font-weight:600;
        }

        .btn-confirm{
            background:linear-gradient(135deg,#16a34a 0%,#15803d 100%);
            color:#fff;border:none;padding:15px 40px;border-radius:10px;
            font-size:1.1em;cursor:pointer;font-weight:700;
            display:none;align-items:center;gap:10px;
            box-shadow:0 8px 28px rgba(22,163,74,.45);
            animation:pulse-confirm 1.4s ease-in-out infinite;
        }
        .btn-confirm.visible{display:inline-flex}

        .btn-stop{
            background:linear-gradient(135deg,#dc2626 0%,#b91c1c 100%);
            color:#fff;border:none;padding:15px 34px;border-radius:10px;
            font-size:1.05em;cursor:pointer;font-weight:700;
            display:none;align-items:center;gap:8px;
            box-shadow:0 8px 24px rgba(220,38,38,.4);transition:all .2s;
        }
        .btn-stop:hover{transform:translateY(-1px);box-shadow:0 12px 30px rgba(220,38,38,.55)}
        .btn-stop.visible{display:inline-flex}
        @keyframes pulse-confirm{
            0%,100%{transform:scale(1)}
            50%{transform:scale(1.04);box-shadow:0 12px 36px rgba(22,163,74,.65)}
        }

        .confirm-banner{
            display:none;background:#fef9c3;border:2px solid #fbbf24;
            border-radius:12px;padding:16px 22px;margin-bottom:20px;
            align-items:center;gap:14px;flex-wrap:wrap;
        }
        .confirm-banner.visible{display:flex}
        .confirm-banner p{flex:1;font-weight:600;color:#92400e}

        .progress-section{display:none}
        .progress-bar{
            width:100%;height:40px;background:#e0e0e0;border-radius:20px;
            overflow:hidden;margin-bottom:20px;box-shadow:inset 0 2px 5px rgba(0,0,0,.1);
        }
        .progress-fill{
            height:100%;background:linear-gradient(90deg,#667eea 0%,#764ba2 100%);
            width:0%;transition:width .3s;display:flex;align-items:center;
            justify-content:center;color:#fff;font-weight:700;font-size:1.1em;
        }
        .progress-text{text-align:center;color:#666;font-size:1em;margin-bottom:15px;font-weight:500}
        .log-container{
            background:#1e1e1e;border-radius:10px;padding:20px;
            max-height:300px;overflow-y:auto;
            font-family:'Courier New',monospace;font-size:.9em;
        }
        .log-entry{margin-bottom:8px;line-height:1.5}
        .log-time{color:#888}
        .log-info{color:#0ff}
        .log-success{color:#0f0}
        .log-error{color:#f00}
        .log-warning{color:#ff0}

        .results-section{display:none}
        .stats{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:20px;margin-bottom:30px}
        .stat-card{
            background:linear-gradient(135deg,#667eea 0%,#764ba2 100%);
            color:#fff;padding:25px;border-radius:15px;text-align:center;
        }
        .stat-card .number{font-size:3em;font-weight:bold;margin-bottom:5px}
        .stat-card .label{opacity:.9;font-size:1em}
        .search-box{margin-bottom:20px}
        .search-box input{width:100%;padding:15px;border:2px solid #e0e0e0;border-radius:10px;font-size:1em}
        .table-container{overflow-x:auto;border-radius:10px;box-shadow:0 5px 20px rgba(0,0,0,.1)}
        table{width:100%;border-collapse:collapse;background:#fff}
        thead{background:#667eea;color:#fff}
        th,td{padding:15px;text-align:left;border-bottom:1px solid #e0e0e0}
        tbody tr:hover{background:#f8f9fa}
        tbody tr:nth-child(even){background:#fafbfc}
        .download-section{display:flex;gap:15px;justify-content:center;flex-wrap:wrap;margin-top:30px}
        .download-btn{
            padding:12px 30px;background:#28a745;color:#fff;border:none;
            border-radius:8px;font-weight:600;cursor:pointer;transition:all .3s;
        }
        .download-btn:hover{transform:translateY(-2px);box-shadow:0 5px 15px rgba(40,167,69,.4)}
        @keyframes spin{0%{transform:rotate(0deg)}100%{transform:rotate(360deg)}}
        .spinner{
            display:inline-block;width:20px;height:20px;
            border:3px solid rgba(255,255,255,.3);border-top-color:#fff;
            border-radius:50%;animation:spin .8s linear infinite;
        }
    </style>
</head>
<body>
<div class="container">
    <div class="header">
        <h1>🏢 HSCTVN Company Scraper</h1>
        <p>Dùng Chrome cá nhân của bạn · Không mở cửa sổ mới · Kết nối qua Remote Debugging</p>
    </div>

    <div class="content">

        <!-- ── Hướng dẫn bật Chrome ── -->
        <div class="section">
            <h2>📋 Bước 1 — Bật Chrome với Remote Debugging</h2>

            <!-- Kill Chrome trước -->
            <div style="background:#fff7ed;border:2px solid #f97316;border-radius:12px;padding:16px 20px;margin-bottom:16px">
                <div style="font-weight:700;color:#c2410c;margin-bottom:10px;font-size:1em">
                    ⚠️ QUAN TRỌNG — Phải tắt Chrome hoàn toàn trước!
                </div>
                <div style="color:#7c2d12;font-size:.93em;margin-bottom:12px">
                    Nếu Chrome đang chạy → lệnh bên dưới sẽ KHÔNG có tác dụng (chỉ mở tab mới trong Chrome cũ, không có debug port).
                </div>
                <div style="display:flex;gap:10px;flex-wrap:wrap">
                    <div style="background:#1e1e1e;border-radius:8px;padding:10px 16px;font-family:monospace;font-size:.88em;color:#fbbf24;flex:1;min-width:280px;position:relative">
                        <button class="cmd-copy" style="position:absolute;top:8px;right:10px" onclick="copyKill()">Copy</button>
                        <span id="kill-cmd">taskkill /F /IM chrome.exe /T</span>
                    </div>
                    <div style="display:flex;flex-direction:column;gap:6px">
                        <span style="font-size:.85em;color:#92400e;font-weight:600">Hoặc thủ công:</span>
                        <span style="font-size:.83em;color:#78350f">Ctrl+Shift+Esc → tìm Chrome → End Task</span>
                    </div>
                </div>
            </div>

            <!-- Mở Chrome với debug port -->
            <div class="guide-box">
                <h3>Sau khi đóng Chrome xong → Chạy lệnh này để mở Chrome với debug port:</h3>
                <div class="os-tabs">
                    <button class="os-tab active" onclick="showOS(event, \'win\')">🪟 Windows</button>
                    <button class="os-tab" onclick="showOS(event, \'mac\')">🍎 macOS</button>
                    <button class="os-tab" onclick="showOS(event, \'linux\')">🐧 Linux</button>
                </div>

                <div class="cmd-block visible" id="cmd-win">
                    <button class="cmd-copy" onclick="copyCmd(\'win\')">Copy</button>
                    <span id="text-win">"C:\Program Files\Google\Chrome\Application\chrome.exe" --remote-debugging-port=9222 --user-data-dir="C:\ScraperData" --no-first-run --no-default-browser-check</span>
                </div>
                <div class="cmd-block" id="cmd-mac">
                    <button class="cmd-copy" onclick="copyCmd(\'mac\')">Copy</button>
                    <span id="text-mac">/Applications/Google\\ Chrome.app/Contents/MacOS/Google\\ Chrome --remote-debugging-port=9222 --user-data-dir="$HOME/Library/Application Support/Google/Chrome"</span>
                </div>
                <div class="cmd-block" id="cmd-linux">
                    <button class="cmd-copy" onclick="copyCmd(\'linux\')">Copy</button>
                    <span id="text-linux">google-chrome --remote-debugging-port=9222 --user-data-dir="$HOME/.config/google-chrome"</span>
                </div>

                <div style="margin-top:14px;background:#e0f2fe;border-radius:8px;padding:12px 16px;font-size:.9em;color:#0369a1">
                    ✅ <strong>Thành công khi:</strong> Cửa sổ CMD <strong>không thoát ra</strong> (giữ nguyên trong khi Chrome đang chạy).
                    Nếu CMD thoát ngay → Chrome vẫn còn chạy, chạy lệnh taskkill trên rồi thử lại.
                </div>
            </div>

            <div style="display:flex;align-items:center;gap:14px">
                <div class="chrome-status disconnected" id="chromeStatus" style="flex:1">
                    <div class="status-dot"></div>
                    <span id="chromeStatusText">Chưa kết nối Chrome — Làm theo hướng dẫn bên trên</span>
                </div>
                <button class="btn-check" onclick="checkChrome()">🔍 Kiểm tra kết nối</button>
            </div>
        </div>

        <!-- ── Cấu hình scraping ── -->
        <div class="section">
            <h2>⚙️ Bước 2 — Cấu hình Scraping</h2>

            <div class="form-grid">
                <div class="form-group full">
                    <label>🔗 Đường dẫn trang 1 (URL danh sách công ty):</label>
                    <input type="text" id="startUrl"
                        value="https://hsctvn.com/thang-11/2025-ha-noi"
                        placeholder="Ví dụ: https://hsctvn.com/thang-11/2025-ha-noi">
                </div>
                <div class="form-group">
                    <label>📄 Từ trang:</label>
                    <input type="number" id="fromPage" value="1" min="1">
                </div>
                <div class="form-group">
                    <label>📄 Đến trang (tối đa 50):</label>
                    <input type="number" id="toPage" value="2" min="1" max="50">
                </div>
                <div class="form-group">
                    <label>⏱️ Delay giữa các trang (giây):</label>
                    <input type="number" id="delay" value="1" min="0.5" step="0.5">
                </div>
            </div>

            <div class="checkbox-group">
                <input type="checkbox" id="getPhones" checked>
                <label for="getPhones">Lấy số điện thoại & ngành nghề từ trang chi tiết</label>
            </div>

            <div style="margin-top:25px;display:flex;align-items:center;gap:16px;flex-wrap:wrap">
                <button class="btn" id="startBtn" onclick="startScraping()">
                    <span id="btnText">🚀 Bắt đầu scraping</span>
                </button>
                <button class="btn-confirm" id="confirmBtn" onclick="sendConfirm()">
                    ✅ Xác nhận – Tiếp tục
                </button>
                <button class="btn-stop" id="stopBtn" onclick="stopScraping()">
                    🛑 Dừng lại
                </button>
            </div>
        </div>

        <!-- ── Banner chờ xác nhận ── -->
        <div class="confirm-banner" id="confirmBanner">
            <p id="confirmMsg">Đang chờ xác nhận...</p>
        </div>

        <!-- ── Tiến trình ── -->
        <div class="section progress-section" id="progressSection">
            <h2>⏳ Tiến trình</h2>
            <div class="progress-bar">
                <div class="progress-fill" id="progressFill">0%</div>
            </div>
            <div class="progress-text" id="progressText">Đang chuẩn bị...</div>
            <div class="log-container" id="logContainer"></div>
        </div>

        <!-- ── Kết quả ── -->
        <div class="section results-section" id="resultsSection">
            <h2>📊 Kết quả</h2>
            <div class="stats">
                <div class="stat-card">
                    <div class="number" id="totalCompanies">0</div>
                    <div class="label">Tổng công ty</div>
                </div>
                <div class="stat-card">
                    <div class="number" id="withPhones">0</div>
                    <div class="label">Có số điện thoại</div>
                </div>
                <div class="stat-card">
                    <div class="number" id="withoutPhones">0</div>
                    <div class="label">Không có SĐT</div>
                </div>
            </div>

            <div class="search-box">
                <input type="text" id="searchInput"
                    placeholder="🔍 Tìm theo tên, địa chỉ, SĐT, mã số thuế..."
                    onkeyup="filterResults()">
            </div>

            <div class="table-container">
                <table>
                    <thead>
                        <tr>
                            <th>#</th>
                            <th>Tên công ty</th>
                            <th>Mã số thuế</th>
                            <th>Số điện thoại</th>
                            <th>Ngành nghề chính</th>
                            <th>Địa chỉ</th>
                        </tr>
                    </thead>
                    <tbody id="resultsBody"></tbody>
                </table>
            </div>

            <div class="download-section">
                <button class="download-btn" onclick="downloadCSV()">📥 Tải CSV</button>
                <button class="download-btn" onclick="downloadJSON()">📥 Tải JSON</button>
                <button class="download-btn" onclick="downloadExcel()">📊 Tải Excel</button>
                <button class="download-btn" onclick="copyToClipboard()">📋 Copy</button>
            </div>
        </div>

    </div>
</div>

<script>
    const API_URL = window.location.origin;
    let currentData = [];
    let filteredData = [];
    let progressInterval = null;
    let currentOS = 'win';

    // ── OS tabs ────────────────────────────────────────────────────────────
    function showOS(evt, os) {
        currentOS = os;
        document.querySelectorAll('.os-tab').forEach(t => t.classList.remove('active'));
        evt.target.classList.add('active');
        document.querySelectorAll('.cmd-block').forEach(b => b.classList.remove('visible'));
        document.getElementById('cmd-' + os).classList.add('visible');
    }

    function copyCmd(os) {
        const text = document.getElementById('text-' + os).textContent;
        navigator.clipboard.writeText(text).then(() => {
            const btn = document.querySelector('#cmd-' + os + ' .cmd-copy');
            btn.textContent = '✓ Copied!';
            setTimeout(() => btn.textContent = 'Copy', 2000);
        });
    }

    function copyKill() {
        const text = document.getElementById('kill-cmd').textContent;
        navigator.clipboard.writeText(text).then(() => {
            event.target.textContent = '✓ Copied!';
            setTimeout(() => event.target.textContent = 'Copy', 2000);
        });
    }

    // ── Kiểm tra Chrome ────────────────────────────────────────────────────
    async function checkChrome() {
        const btn = document.querySelector('.btn-check');
        btn.textContent = '⏳ Đang kiểm tra...';
        btn.disabled = true;

        try {
            const res  = await fetch(`${API_URL}/api/chrome-status`);
            const data = await res.json();
            updateChromeStatus(data.connected);
            if (data.connected) {
                showToast('✅ Chrome đã kết nối thành công!', 'success');
            } else {
                showToast('❌ Chưa thấy Chrome — Hãy làm theo hướng dẫn', 'error');
            }
        } catch {
            updateChromeStatus(false);
            showToast('❌ Không kết nối được server Flask', 'error');
        } finally {
            btn.textContent = '🔍 Kiểm tra kết nối';
            btn.disabled = false;
        }
    }

    function updateChromeStatus(connected) {
        const el   = document.getElementById('chromeStatus');
        const text = document.getElementById('chromeStatusText');
        el.className = 'chrome-status ' + (connected ? 'connected' : 'disconnected');
        text.textContent = connected
            ? '✅ Chrome đã kết nối — Sẵn sàng scraping!'
            : '❌ Chưa kết nối Chrome — Làm theo hướng dẫn bên trên';
    }

    function showToast(msg, type) {
        let t = document.getElementById('toast');
        if (!t) {
            t = document.createElement('div');
            t.id = 'toast';
            t.style.cssText = `
                position:fixed;bottom:30px;right:30px;z-index:9999;
                padding:14px 22px;border-radius:10px;font-weight:700;font-size:1em;
                box-shadow:0 8px 24px rgba(0,0,0,.2);transition:opacity .4s;
            `;
            document.body.appendChild(t);
        }
        t.textContent = msg;
        t.style.background  = type === 'success' ? '#16a34a' : '#dc2626';
        t.style.color       = '#fff';
        t.style.opacity     = '1';
        clearTimeout(t._timer);
        t._timer = setTimeout(() => t.style.opacity = '0', 3000);
    }

    // Auto-check khi tải trang
    checkChrome();
    setInterval(checkChrome, 5000);

    async function startScraping() {
        const startUrl  = document.getElementById('startUrl').value.trim();
        const fromPage  = parseInt(document.getElementById('fromPage').value);
        const toPage    = parseInt(document.getElementById('toPage').value);
        const delay     = parseFloat(document.getElementById('delay').value);
        const getPhones = document.getElementById('getPhones').checked;

        if (!startUrl) { alert('Vui lòng nhập URL trang 1!'); return; }
        if (!fromPage || !toPage || fromPage <= 0 || toPage < fromPage) {
            alert('Khoảng trang không hợp lệ!'); return;
        }

        document.getElementById('startBtn').disabled = true;
        document.getElementById('btnText').innerHTML = '<span class="spinner"></span> Đang scraping...';
        document.getElementById('stopBtn').classList.add('visible');
        document.getElementById('progressSection').style.display = 'block';
        document.getElementById('resultsSection').style.display = 'none';
        document.getElementById('logContainer').innerHTML = '';

        try {
            const res = await fetch(`${API_URL}/api/scrape`, {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({ startUrl, fromPage, toPage, delay, getPhones })
            });
            if (!res.ok) throw new Error('Không thể kết nối tới server');
            progressInterval = setInterval(checkProgress, 1000);
        } catch (err) {
            alert('Lỗi: ' + err.message);
            resetUI();
        }
    }

    async function stopScraping() {
        if (!confirm('Dừng scraping? Dữ liệu đã thu thập sẽ được giữ lại.')) return;
        try {
            await fetch(`${API_URL}/api/stop`, { method: 'POST' });
            showToast('🛑 Đã gửi lệnh dừng...', 'success');
        } catch (err) { console.error(err); }
    }

    // ── Poll progress ──────────────────────────────────────────────────────
    async function checkProgress() {
        try {
            const res  = await fetch(`${API_URL}/api/progress`);
            const data = await res.json();

            if (data.total > 0) {
                const pct = Math.round((data.progress / data.total) * 100);
                document.getElementById('progressFill').style.width = pct + '%';
                document.getElementById('progressFill').textContent = pct + '%';
            }
            document.getElementById('progressText').textContent = data.current_task || 'Đang xử lý...';

            const logBox = document.getElementById('logContainer');
            logBox.innerHTML = data.logs.map(l =>
                `<div class="log-entry">
                    <span class="log-time">[${l.time}]</span>
                    <span class="log-${l.type}"> ${l.message}</span>
                 </div>`
            ).join('');
            logBox.scrollTop = logBox.scrollHeight;

            setConfirmUI(data.waiting_confirm, data.waiting_confirm ? '⚠️ ' + data.confirm_message : '');
            updateChromeStatus(data.chrome_connected || false);

            if (data.status === 'completed') {
                clearInterval(progressInterval);
                currentData = data.companies;
                displayResults();
                resetUI();
            } else if (data.status === 'error') {
                clearInterval(progressInterval);
                alert('Có lỗi xảy ra! Xem log để biết chi tiết.');
                resetUI();
            }
        } catch (err) {
            console.error('Poll error:', err);
        }
    }

    // ── Confirm ────────────────────────────────────────────────────────────
    async function sendConfirm() {
        try {
            await fetch(`${API_URL}/api/confirm`, { method: 'POST' });
            setConfirmUI(false, '');
        } catch (err) { console.error(err); }
    }

    function setConfirmUI(show, message) {
        const btn    = document.getElementById('confirmBtn');
        const banner = document.getElementById('confirmBanner');
        const msg    = document.getElementById('confirmMsg');
        if (show) {
            btn.classList.add('visible');
            banner.classList.add('visible');
            msg.textContent = message;
        } else {
            btn.classList.remove('visible');
            banner.classList.remove('visible');
        }
    }

    // ── Display results ────────────────────────────────────────────────────
    function displayResults() {
        filteredData = [...currentData];
        const withPhones = currentData.filter(c => c.phone).length;
        document.getElementById('totalCompanies').textContent = currentData.length;
        document.getElementById('withPhones').textContent = withPhones;
        document.getElementById('withoutPhones').textContent = currentData.length - withPhones;
        renderTable(filteredData);
        document.getElementById('resultsSection').style.display = 'block';
    }

    function renderTable(data) {
        document.getElementById('resultsBody').innerHTML = data.map((c, i) => `
            <tr>
                <td>${i + 1}</td>
                <td>${c.name || ''}</td>
                <td>${c.tax_code || ''}</td>
                <td>${c.phone || '-'}</td>
                <td>${c.industry || '-'}</td>
                <td>${c.address || ''}</td>
            </tr>`
        ).join('');
    }

    function filterResults() {
        const q = document.getElementById('searchInput').value.toLowerCase();
        filteredData = currentData.filter(c =>
            (c.name || '').toLowerCase().includes(q) ||
            (c.address || '').toLowerCase().includes(q) ||
            (c.phone || '').includes(q) ||
            (c.tax_code || '').includes(q) ||
            (c.industry || '').toLowerCase().includes(q)
        );
        renderTable(filteredData);
    }

    // ── Downloads ──────────────────────────────────────────────────────────
    function downloadCSV()   { window.location.href = `${API_URL}/api/download/csv`; }
    function downloadJSON()  { window.location.href = `${API_URL}/api/download/json`; }
    function downloadExcel() { window.location.href = `${API_URL}/api/download/excel`; }

    function copyToClipboard() {
        const text = filteredData.map(c =>
            [c.name, c.tax_code, c.phone, c.industry, c.address].join('\\t')
        ).join('\\n');
        navigator.clipboard.writeText(text).then(() => alert('✓ Đã copy vào clipboard!'));
    }

    function resetUI() {
        document.getElementById('startBtn').disabled = false;
        document.getElementById('btnText').innerHTML = '🚀 Bắt đầu scraping';
        document.getElementById('stopBtn').classList.remove('visible');
        setConfirmUI(false, '');
    }
</script>
</body>
</html>'''


# ============================================================================
if __name__ == '__main__':
    print("=" * 70)
    print("🚀 HSCTVN SCRAPER — Chrome Cá Nhân (Remote Debugging)")
    print("=" * 70)
    print("📌 Trước khi chạy: Mở Chrome bằng lệnh remote debugging")
    print("   Xem hướng dẫn tại: http://localhost:5001")
    print("=" * 70)
    print("📡 http://localhost:5001")
    print("=" * 70)
    app.run(debug=True, host='0.0.0.0', port=5001)