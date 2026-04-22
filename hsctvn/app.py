# ============================================================================
# BACKEND - Flask API Server (app.py)
# ============================================================================
    # # https://hsctvn.com/thang-12/2025-thanh-hoa
# page = 5

from flask import Flask, jsonify, request, send_file
from flask_cors import CORS
import requests
from bs4 import BeautifulSoup
import re
import time
import csv
import json
import io
from datetime import datetime
from threading import Thread
import pandas as pd
import os
from pathlib import Path

app = Flask(__name__)
CORS(app)

# Global variable để tracking progress
scraping_progress = {
    'status': 'idle',  # idle, running, completed, error
    'progress': 0,
    'total': 0,
    'current_task': '',
    'companies': [],
    'logs': []
}


class HSCTVNScraper:
    def __init__(self, delay=1):
        self.base_url = "https://hsctvn.com"
        self.delay = delay
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        })

    def extract_province(self, full_address):
        """Trích xuất tên tỉnh/thành phố từ địa chỉ đầy đủ"""
        if not full_address:
            return ''

        parts = [p.strip() for p in full_address.split(',') if p.strip()]
        if not parts:
            return ''

        # Bỏ qua "Việt Nam" ở cuối nếu có
        while parts and re.match(r'^Việt\s*Nam$', parts[-1], re.IGNORECASE):
            parts.pop()

        if not parts:
            return ''

        last_part = parts[-1]

        # Bỏ tiền tố "Tỉnh ", "Thành phố ", "TP. ", v.v.
        province = re.sub(
            r'^(Tỉnh|Thành phố|Thành Phố|TP\.|TP|T\.P\.?)\s+',
            '',
            last_part,
            flags=re.IGNORECASE
        ).strip()

        return province if province else last_part
    def log(self, message, log_type='info'):
        """Add log message"""
        timestamp = datetime.now().strftime('%H:%M:%S')
        scraping_progress['logs'].append({
            'time': timestamp,
            'type': log_type,
            'message': message
        })

    def update_progress(self, current, total, task):
        """Update progress"""
        scraping_progress['progress'] = current
        scraping_progress['total'] = total
        scraping_progress['current_task'] = task

    def get_page(self, url):
        """Fetch page content"""
        try:
            # Thử nhiều lần với timeout dài hơn để tránh lỗi Read timed out
            max_retries = 3
            timeout = 25

            last_error = None
            for attempt in range(1, max_retries + 1):
                try:
                    self.log(f"Đang tải {url} (lần {attempt}/{max_retries})", 'info')
                    response = self.session.get(url, timeout=timeout)
                    response.raise_for_status()
                    return response.text
                except Exception as e:
                    last_error = e
                    self.log(f"Lỗi khi tải {url} (lần {attempt}): {str(e)}", 'warning')
                    time.sleep(self.delay)

            # Sau khi thử đủ số lần mà vẫn lỗi thì báo lỗi cuối cùng
            self.log(f"Lỗi khi tải {url}: {str(last_error)}", 'error')
            return None

        except Exception as e:
            self.log(f"Lỗi khi tải {url}: {str(e)}", 'error')
            return None

    def parse_company_list(self, html):
        """Parse company list from HTML"""
        soup = BeautifulSoup(html, 'html.parser')
        companies = []

        items = soup.find_all('li')

        for item in items:
            h3 = item.find('h3')
            if not h3:
                continue

            link = h3.find('a')
            if not link:
                continue

            company = {
                'name': link.get_text(strip=True),
                'detail_url': self.base_url + '/' + link.get('href', ''),
                'tax_code': '',
                'address': '',
                'phone': '',
                'industry': ''  # ← THÊM DÒNG NÀY
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
        """Get phone and industry from detail page"""
        try:
            time.sleep(self.delay)
            html = self.get_page(url)
            if not html:
                return {'phone': '', 'industry': ''}
            soup = BeautifulSoup(html, 'html.parser')

            detail_block = soup.select_one('div.module_data.detail') or soup

            # --- Lấy số điện thoại ---
            phone_li = None
            for li in detail_block.find_all('li'):
                icon = li.find('i', class_=lambda c: c and 'fa-phone' in c)
                if icon:
                    phone_li = li
                    break

            text_source = phone_li.get_text(separator=' ', strip=True) if phone_li \
                else detail_block.get_text(separator=' ', strip=True)

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

            # --- Lấy ngành nghề chính ---
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
            self.log(f'Lỗi get_details_from_detail {url}: {str(e)}', 'error')
            return {'phone': '', 'industry': ''}
    def save_to_excel(self, companies, filename=None):
        """(KHÔNG còn dùng tự động) - Hàm cũ giữ lại cho tương thích, không còn được gọi trong luồng chính"""
        try:
            if not companies:
                self.log("Không có dữ liệu để lưu", 'warning')
                return None

            df_data = []
            for i, company in enumerate(companies, 1):
                df_data.append({
                    'STT': i,
                    'Tên công ty': company['name'],
                    'Mã số thuế': company['tax_code'],
                    'Số điện thoại': company['phone'] if company['phone'] else '',
                    'Ngành nghề chính': company.get('industry', ''),  # ← THÊM
                    'Địa chỉ': company['address'],
                    'Ngày lấy dữ liệu': datetime.now().strftime('%d/%m/%Y %H:%M:%S')
                })

            df = pd.DataFrame(df_data)
            output = io.BytesIO()
            df.to_excel(output, index=False, engine='openpyxl')
            output.seek(0)
            return output

        except Exception as e:
            self.log(f'Lỗi khi tạo Excel: {str(e)}', 'error')
            return None

    def scrape(self, area=None, month=None, from_page=None, to_page=None, get_phones=True, start_url=None):
        """Main scraping function

        Nếu start_url được truyền vào thì sẽ ưu tiên sử dụng đường dẫn này
        để lấy dữ liệu từ trang from_page đến to_page. Giả định start_url
        là đường dẫn của trang đầu tiên trong danh sách (thường là trang 1),
        các trang tiếp theo sẽ có dạng: start_url + '/page-X'.
        """
        try:
            scraping_progress['status'] = 'running'
            scraping_progress['companies'] = []
            scraping_progress['logs'] = []

            # Giới hạn số trang tối đa cho mỗi lần lấy để tránh bị chặn / quá tải
            MAX_PAGES = 50
            if from_page is None:
                from_page = 1
            if to_page is None or to_page < from_page:
                to_page = from_page

            requested_pages = to_page - from_page + 1
            if requested_pages > MAX_PAGES:
                to_page = from_page + MAX_PAGES - 1
                self.log(f'Giới hạn tối đa {MAX_PAGES} trang mỗi lần. Tự động điều chỉnh đến trang {to_page}.', 'warning')

            self.log(f'Bắt đầu scraping từ trang {from_page} đến {to_page}', 'info')

            all_companies = []
            total_pages = to_page - from_page + 1

            # Phase 1: Get company lists
            for page in range(from_page, to_page + 1):
                # Nếu người dùng truyền start_url thì ưu tiên dùng start_url
                if start_url:
                    # Chuẩn hóa URL, bỏ dấu "/" ở cuối nếu có
                    normalized = start_url.rstrip('/')

                    # Trường hợp start_url có dạng .../page-1, .../page-2
                    page_match = re.match(r"^(.*?/page-)(\d+)$", normalized)
                    if page_match:
                        # Giữ nguyên phần đầu, chỉ thay số trang
                        url = f"{page_match.group(1)}{page}"
                    else:
                        # Trường hợp start_url là link danh sách trang 1, không có /page-1 ở cuối
                        if page == 1:
                            url = normalized
                        else:
                            url = f"{normalized}/page-{page}"
                else:
                    # Cách cũ: build URL từ month + area
                    if page == 1:
                        url = f"{self.base_url}/{month}-{area}"
                    else:
                        url = f"{self.base_url}/{month}-{area}/page-{page}"

                self.log(f'Đang xử lý trang {page}/{to_page}...', 'info')
                self.update_progress(page - from_page, total_pages, f'Đang tải trang {page}')

                html = self.get_page(url)
                if html:
                    companies = self.parse_company_list(html)
                    self.log(f'✓ Tìm thấy {len(companies)} công ty ở trang {page}', 'success')
                    all_companies.extend(companies)
                else:
                    self.log(f'✗ Không thể tải trang {page}', 'error')

                time.sleep(self.delay)

            # Phase 2: Get phone numbers
            # Phase 2: Get phone numbers
            if get_phones and all_companies:
                self.log(f'Bắt đầu lấy số điện thoại cho {len(all_companies)} công ty...', 'info')

                for i, company in enumerate(all_companies):
                    self.update_progress(i + 1, len(all_companies),
                                         f'Đang lấy SĐT: {company["name"]}')
                    self.log(f'[{i + 1}/{len(all_companies)}] {company["name"]}', 'info')

                    details = self.get_details_from_detail(company['detail_url'])  # ← ĐỔI
                    company['phone'] = details['phone']
                    company['industry'] = details['industry']  # ← THÊM

                    if details['phone']:
                        self.log(f'  ✓ SĐT: {details["phone"]}', 'success')
                    if details['industry']:
                        self.log(f'  ✓ Ngành: {details["industry"]}', 'success')

                    scraping_progress['companies'] = all_companies

            scraping_progress['companies'] = all_companies
            scraping_progress['status'] = 'completed'
            self.log(f'✓ Hoàn thành! Tổng cộng {len(all_companies)} công ty', 'success')

            return all_companies

        except Exception as e:
            scraping_progress['status'] = 'error'
            self.log(f'✗ Lỗi: {str(e)}', 'error')
            return []


# ============================================================================
# API ENDPOINTS
# ============================================================================

@app.route('/api/scrape', methods=['POST'])
def start_scraping():
    """Start scraping process"""
    data = request.json

    # Cho phép truyền trực tiếp đường dẫn trang 1
    start_url = data.get('startUrl')

    # Các tham số cũ vẫn giữ để tương thích, nhưng nếu có startUrl thì sẽ ưu tiên dùng
    area = data.get('area', 'ha-noi')
    month = data.get('month', 'thang-11/2025')
    from_page = int(data.get('fromPage', 1))
    to_page = int(data.get('toPage', 2))
    delay = float(data.get('delay', 1))
    get_phones = data.get('getPhones', True)

    # Reset progress
    scraping_progress['status'] = 'running'
    scraping_progress['progress'] = 0
    scraping_progress['total'] = 0
    scraping_progress['companies'] = []
    scraping_progress['logs'] = []

    # Run scraping in background thread
    def run_scraper():
        scraper = HSCTVNScraper(delay=delay)
        scraper.scrape(area, month, from_page, to_page, get_phones, start_url=start_url)

    thread = Thread(target=run_scraper)
    thread.daemon = True
    thread.start()

    return jsonify({'status': 'started'})


@app.route('/api/progress', methods=['GET'])
def get_progress():
    """Get scraping progress"""
    return jsonify(scraping_progress)


@app.route('/api/download/excel', methods=['GET'])
def download_excel():
    """Tạo và tải file Excel từ kết quả hiện tại, không lưu vào ổ đĩa"""
    try:
        companies = scraping_progress.get('companies', [])
        if not companies:
            return jsonify({'error': 'Không có dữ liệu để xuất Excel'}), 404

        df_data = []
        for i, company in enumerate(companies, 1):
            df_data.append({
                'STT': i,
                'Tên công ty': company['name'],
                'Mã số thuế': company['tax_code'],
                'Số điện thoại': company['phone'] if company['phone'] else '',
                'Địa chỉ': company['address'],
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


@app.route('/api/excel-files', methods=['GET'])
def list_excel_files():
    """List all Excel files in data folder"""
    try:
        data_dir = Path("data")
        if not data_dir.exists():
            return jsonify({'files': []})

        excel_files = []
        for file_path in data_dir.glob("*.xlsx"):
            stat = file_path.stat()
            excel_files.append({
                'name': file_path.name,
                'size': stat.st_size,
                'modified': datetime.fromtimestamp(stat.st_mtime).strftime('%d/%m/%Y %H:%M:%S')
            })

        # Sắp xếp theo thời gian sửa đổi (mới nhất trước)
        excel_files.sort(key=lambda x: x['modified'], reverse=True)

        return jsonify({'files': excel_files})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/download/csv', methods=['GET'])
def download_csv():
    companies = scraping_progress['companies']

    output = io.StringIO()
    output.write('\ufeff')
    writer = csv.writer(output)

    writer.writerow(['STT', 'Tên công ty', 'Mã số thuế', 'Số điện thoại', 'Ngành nghề chính', 'Địa chỉ'])  # ← THÊM

    for i, company in enumerate(companies, 1):
        phone_text = company['phone'] if company['phone'] else ''
        if phone_text and not phone_text.startswith("'"):
            phone_text = f"'{phone_text}"
        writer.writerow([
            i,
            company['name'],
            company['tax_code'],
            phone_text,
            company.get('industry', ''),   # ← THÊM
            company['address']
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
    """Download results as JSON"""
    companies = scraping_progress['companies']

    output = json.dumps(companies, ensure_ascii=False, indent=2)

    return send_file(
        io.BytesIO(output.encode('utf-8')),
        mimetype='application/json',
        as_attachment=True,
        download_name=f'companies_{datetime.now().strftime("%Y%m%d_%H%M%S")}.json'
    )


@app.route('/')
def index():
    """Serve frontend"""
    return '''
<!DOCTYPE html>
<html lang="vi">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>HSCTVN Company Phone Scraper</title>
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }

        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background: linear-gradient(135deg, #eef2ff 0%, #e5e7eb 50%, #f9fafb 100%);
            min-height: 100vh;
            padding: 30px 15px;
        }

        .container {
            max-width: 1320px;
            margin: 0 auto;
            background: white;
            border-radius: 18px;
            box-shadow: 0 18px 45px rgba(15,23,42,0.18);
            overflow: hidden;
        }

        .header {
            background: linear-gradient(135deg, #4f46e5 0%, #7c3aed 40%, #ec4899 100%);
            color: white;
            padding: 36px 40px;
            text-align: center;
        }

        .header h1 {
            font-size: 2.4em;
            margin-bottom: 8px;
            text-shadow: 0 8px 20px rgba(15,23,42,0.35);
        }

        .header p {
            opacity: 0.96;
            font-size: 1.05em;
        }

        .content {
            padding: 30px 34px 36px;
            background: linear-gradient(180deg, #f9fafb 0%, #ffffff 40%);
        }

        .section {
            background: #ffffff;
            padding: 24px 26px;
            border-radius: 16px;
            margin-bottom: 26px;
            border: 1px solid #e5e7eb;
            box-shadow: 0 8px 24px rgba(15,23,42,0.06);
        }

        .section h2 {
            margin-bottom: 14px;
            color: #111827;
            display: flex;
            align-items: center;
            gap: 10px;
            font-size: 1.3em;
            font-weight: 700;
        }

        .form-grid {
            display: grid;
            grid-template-columns: repeat(3, minmax(0, 1fr));
            column-gap: 20px;
            row-gap: 16px;
            margin-bottom: 20px;
        }

        .form-group.form-group--full {
            grid-column: 1 / -1;
        }

        .form-group label {
            display: block;
            margin-bottom: 8px;
            font-weight: 600;
            color: #333;
        }

        .form-group input, .form-group select {
            width: 100%;
            padding: 12px;
            border: 2px solid #e0e0e0;
            border-radius: 8px;
            font-size: 1em;
            transition: all 0.3s;
        }

        .form-group input:focus {
            outline: none;
            border-color: #667eea;
            box-shadow: 0 0 0 3px rgba(102, 126, 234, 0.1);
        }

        .checkbox-group {
            display: flex;
            align-items: center;
            gap: 10px;
            margin-top: 15px;
        }

        .checkbox-group input[type="checkbox"] {
            width: 20px;
            height: 20px;
            cursor: pointer;
        }

        .btn {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            border: none;
            padding: 15px 40px;
            border-radius: 10px;
            font-size: 1.1em;
            cursor: pointer;
            transition: all 0.3s;
            font-weight: 600;
            display: inline-flex;
            align-items: center;
            gap: 10px;
        }

        .btn:hover:not(:disabled) {
            transform: translateY(-2px);
            box-shadow: 0 10px 30px rgba(102, 126, 234, 0.4);
        }

        .btn:disabled {
            background: #ccc;
            cursor: not-allowed;
            transform: none;
        }

        .progress-section {
            display: none;
        }

        .progress-bar {
            width: 100%;
            height: 40px;
            background: #e0e0e0;
            border-radius: 20px;
            overflow: hidden;
            margin-bottom: 20px;
            box-shadow: inset 0 2px 5px rgba(0,0,0,0.1);
        }

        .progress-fill {
            height: 100%;
            background: linear-gradient(90deg, #667eea 0%, #764ba2 100%);
            width: 0%;
            transition: width 0.3s;
            display: flex;
            align-items: center;
            justify-content: center;
            color: white;
            font-weight: 700;
            font-size: 1.1em;
        }

        .progress-text {
            text-align: center;
            color: #666;
            font-size: 1em;
            margin-bottom: 15px;
            font-weight: 500;
        }

        .log-container {
            background: #1e1e1e;
            border-radius: 10px;
            padding: 20px;
            max-height: 300px;
            overflow-y: auto;
            font-family: 'Courier New', monospace;
            font-size: 0.9em;
        }

        .log-entry {
            margin-bottom: 8px;
            line-height: 1.5;
        }

        .log-time {
            color: #888;
        }

        .log-info { color: #0ff; }
        .log-success { color: #0f0; }
        .log-error { color: #f00; }
        .log-warning { color: #ff0; }

        .stats {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 20px;
            margin-bottom: 30px;
        }

        .stat-card {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 25px;
            border-radius: 15px;
            text-align: center;
            box-shadow: 0 5px 20px rgba(0,0,0,0.2);
        }

        .stat-card .number {
            font-size: 3em;
            font-weight: bold;
            margin-bottom: 5px;
        }

        .stat-card .label {
            opacity: 0.9;
            font-size: 1em;
        }

        .results-section {
            display: none;
        }

        .search-box {
            margin-bottom: 20px;
        }

        .search-box input {
            width: 100%;
            padding: 15px;
            border: 2px solid #e0e0e0;
            border-radius: 10px;
            font-size: 1em;
        }

        .table-container {
            overflow-x: auto;
            border-radius: 10px;
            box-shadow: 0 5px 20px rgba(0,0,0,0.1);
        }

        table {
            width: 100%;
            border-collapse: collapse;
            background: white;
        }

        thead {
            background: #667eea;
            color: white;
        }

        th, td {
            padding: 15px;
            text-align: left;
            border-bottom: 1px solid #e0e0e0;
        }

        tbody tr:hover {
            background: #f8f9fa;
        }

        tbody tr:nth-child(even) {
            background: #fafbfc;
        }

        .download-section {
            display: flex;
            gap: 15px;
            justify-content: center;
            flex-wrap: wrap;
            margin-top: 30px;
        }

        .download-btn {
            padding: 12px 30px;
            background: #28a745;
            color: white;
            border: none;
            border-radius: 8px;
            font-weight: 600;
            cursor: pointer;
            transition: all 0.3s;
            display: inline-flex;
            align-items: center;
            gap: 8px;
        }

        .download-btn:hover {
            transform: translateY(-2px);
            box-shadow: 0 5px 15px rgba(40, 167, 69, 0.4);
        }

        @keyframes spin {
            0% { transform: rotate(0deg); }
            100% { transform: rotate(360deg); }
        }

        .spinner {
            display: inline-block;
            width: 20px;
            height: 20px;
            border: 3px solid rgba(255,255,255,0.3);
            border-top-color: white;
            border-radius: 50%;
            animation: spin 0.8s linear infinite;
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🏢 HSCTVN Company Scraper</h1>
            <p>Công cụ lấy thông tin công ty và số điện thoại - Full Stack Application</p>
        </div>

        <div class="content">
            <!-- Input Section -->
            <div class="section">
                <h2>⚙️ Cấu hình Scraping</h2>
                <p style="margin-bottom:15px;color:#555;">Nhập đường dẫn trang 1 của danh sách công ty và chọn khoảng trang cần lấy (tối đa 50 trang mỗi lần).</p>

                <div class="form-grid">
                    <div class="form-group form-group--full">
                        <label>🔗 Đường dẫn trang 1 (URL danh sách công ty):</label>
                        <input type="text" id="startUrl" value="https://hsctvn.com/thang-11/2025-ha-noi" placeholder="Dán link trang 1, ví dụ: https://hsctvn.com/thang-11/2025-ha-noi">
                    </div>

                    <div class="form-group">
                        <label>📄 Từ trang:</label>
                        <input type="number" id="fromPage" value="1" min="1">
                    </div>

                    <div class="form-group">
                        <label>📄 Đến trang (tối đa 50 trang mỗi lần):</label>
                        <input type="number" id="toPage" value="2" min="1" max="50">
                    </div>

                    <div class="form-group">
                        <label>⏱️ Delay (giây):</label>
                        <input type="number" id="delay" value="1" min="0.5" step="0.5">
                    </div>
                </div>

                <div class="checkbox-group">
                    <input type="checkbox" id="getPhones" checked>
                    <label for="getPhones">Lấy số điện thoại từ trang chi tiết</label>
                </div>

                <div class="checkbox-group">
                    <input type="checkbox" id="autoSaveExcel" checked>
                    <label for="autoSaveExcel">Tự động lưu vào file Excel (ghi vào bản ghi cuối cùng)</label>
                </div>

                <div style="margin-top: 25px;">
                    <button class="btn" id="startBtn" onclick="startScraping()">
                        <span id="btnText">🚀 Bắt đầu scraping</span>
                    </button>
                </div>
            </div>

            <!-- Progress Section -->
            <div class="section progress-section" id="progressSection">
                <h2>⏳ Tiến trình</h2>
                <div class="progress-bar">
                    <div class="progress-fill" id="progressFill">0%</div>
                </div>
                <div class="progress-text" id="progressText">Đang chuẩn bị...</div>
                <div class="log-container" id="logContainer"></div>
            </div>

            <!-- Results Section -->
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
                    <input type="text" id="searchInput" placeholder="🔍 Tìm kiếm theo tên, địa chỉ, số điện thoại..." onkeyup="filterResults()">
                </div>

                <div class="table-container">
                    <table>
                        <thead>
                            <tr>
                                <th>#</th>
                                <th>Tên công ty</th>
                                <th>Mã số thuế</th>
                                <th>Số điện thoại</th>
                                <th>Địa chỉ</th>
                                <th>Ngành nghề chính</th> 
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

        async function startScraping() {
            const config = {
                startUrl: document.getElementById('startUrl').value.trim(),
                fromPage: parseInt(document.getElementById('fromPage').value),
                toPage: parseInt(document.getElementById('toPage').value),
                delay: parseFloat(document.getElementById('delay').value),
                getPhones: document.getElementById('getPhones').checked,
                autoSaveExcel: document.getElementById('autoSaveExcel').checked
            };

            // Validate
            if (!config.startUrl) {
                alert('Vui lòng nhập đường dẫn trang 1!');
                return;
            }
            if (!config.fromPage || !config.toPage || config.fromPage <= 0 || config.toPage < config.fromPage) {
                alert('Vui lòng nhập khoảng trang hợp lệ (từ trang <= đến trang, và >= 1)!');
                return;
            }

            // UI updates
            document.getElementById('startBtn').disabled = true;
            document.getElementById('btnText').innerHTML = '<span class="spinner"></span> Đang scraping...';
            document.getElementById('progressSection').style.display = 'block';
            document.getElementById('resultsSection').style.display = 'none';
            document.getElementById('logContainer').innerHTML = '';

            try {
                // Start scraping
                const response = await fetch(`${API_URL}/api/scrape`, {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify(config)
                });

                if (!response.ok) throw new Error('Không thể kết nối tới server');

                // Poll progress
                progressInterval = setInterval(checkProgress, 1000);

            } catch (error) {
                alert('Lỗi: ' + error.message);
                resetUI();
            }
        }

        async function checkProgress() {
            try {
                const response = await fetch(`${API_URL}/api/progress`);
                const data = await response.json();

                // Update progress bar
                if (data.total > 0) {
                    const percent = Math.round((data.progress / data.total) * 100);
                    document.getElementById('progressFill').style.width = percent + '%';
                    document.getElementById('progressFill').textContent = percent + '%';
                }

                document.getElementById('progressText').textContent = data.current_task || 'Đang xử lý...';

                // Update logs
                const logContainer = document.getElementById('logContainer');
                logContainer.innerHTML = data.logs.map(log => 
                    `<div class="log-entry">
                        <span class="log-time">[${log.time}]</span>
                        <span class="log-${log.type}"> ${log.message}</span>
                    </div>`
                ).join('');
                logContainer.scrollTop = logContainer.scrollHeight;

                // Check if completed
                if (data.status === 'completed') {
                    clearInterval(progressInterval);
                    currentData = data.companies;
                    displayResults();
                    resetUI();
                } else if (data.status === 'error') {
                    clearInterval(progressInterval);
                    alert('Có lỗi xảy ra trong quá trình scraping!');
                    resetUI();
                }

            } catch (error) {
                console.error('Error checking progress:', error);
            }
        }

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
            const tbody = document.getElementById('resultsBody');
            tbody.innerHTML = data.map((company, index) => `
                <tr>
                    <td>${index + 1}</td>
                    <td>${company.name}</td>
                    <td>${company.tax_code}</td>
                    <td>${company.phone || '-'}</td>
                    <td>${company.address}</td>
                    <td>${company.industry || '-'}</td> 
                </tr>
            `).join('');
        }

        function filterResults() {
            const search = document.getElementById('searchInput').value.toLowerCase();
            filteredData = currentData.filter(c => 
                c.name.toLowerCase().includes(search) ||
                c.address.toLowerCase().includes(search) ||
                c.phone.includes(search) ||
                c.tax_code.includes(search)
            );
            renderTable(filteredData);
        }

        function downloadCSV() {
            window.location.href = `${API_URL}/api/download/csv`;
        }

        function downloadJSON() {
            window.location.href = `${API_URL}/api/download/json`;
        }

        function downloadExcel() {
            window.location.href = `${API_URL}/api/download/excel`;
        }

        function copyToClipboard() {
            const text = filteredData.map(c => 
                `${c.name}\\t${c.tax_code}\\t${c.phone}\\t${c.address}`
                `${c.name}\t${c.tax_code}\t${c.phone}\t${c.industry || ''}\t${c.address}`
            ).join('\\n');

            navigator.clipboard.writeText(text).then(() => {
                alert('✓ Đã copy dữ liệu vào clipboard!');
            });
        }

        function resetUI() {
            document.getElementById('startBtn').disabled = false;
            document.getElementById('btnText').innerHTML = '🚀 Bắt đầu scraping';
        }
    </script>
</body>
</html>
    '''


if __name__ == '__main__':
    print("=" * 70)
    print("🚀 HSCTVN SCRAPER - FULL STACK APPLICATION")
    print("=" * 70)
    print("📡 Server đang chạy tại: http://localhost:5001")
    print("🌐 Mở trình duyệt và truy cập địa chỉ trên để sử dụng")
    print("=" * 70)
    app.run(debug=True, host='0.0.0.0', port=5001)