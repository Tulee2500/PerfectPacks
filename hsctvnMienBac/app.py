#!/usr/bin/env python3
# ============================================================================
# HSCTVN Company Scraper — tích hợp EasyOCR auto-scan
# ============================================================================
# Cài đặt:
#   pip install flask flask-cors requests beautifulsoup4 pandas openpyxl easyocr pillow
#
# (pytesseract vẫn được dùng làm fallback nếu EasyOCR thất bại)
#
# Chạy:
#   python app.py
# Mở: http://localhost:5001
# ============================================================================
# https://hsctvn.com/industry-46493/ban-buon-nuoc-hoa-hang-my-pham-va-che-pham-ve-sinh/69524/page-1050
from flask import Flask, jsonify, request, send_file
from flask_cors import CORS
import requests
from bs4 import BeautifulSoup
import re
import time
import csv
import json
import io
import base64
import hashlib
from datetime import datetime
from threading import Thread, Lock
import pandas as pd
import os

# ── EasyOCR (primary) ────────────────────────────────────────────────────────
try:
    import easyocr as _easyocr
    from PIL import Image, ImageFile
    import numpy as np
    EASYOCR_AVAILABLE = True
except ImportError:
    EASYOCR_AVAILABLE = False

# ── Pytesseract (fallback) ───────────────────────────────────────────────────
try:
    from PIL import Image, ImageFile
    import pytesseract
    import numpy as np
    TESSERACT_AVAILABLE = True
except ImportError:
    TESSERACT_AVAILABLE = False

OCR_AVAILABLE = EASYOCR_AVAILABLE or TESSERACT_AVAILABLE

app = Flask(__name__)
CORS(app)

BASE_DIR          = os.path.dirname(os.path.abspath(__file__))
PHONE_DICT_FILE   = os.path.join(BASE_DIR, 'phone_dict.json')
UNKNOWN_DIR       = os.path.join(BASE_DIR, 'unknown_phones')

# ── EasyOCR singleton ────────────────────────────────────────────────────────
_easyocr_reader      = None
_easyocr_reader_lock = Lock()

def get_easyocr():
    global _easyocr_reader
    if not EASYOCR_AVAILABLE:
        return None
    if _easyocr_reader is None:
        with _easyocr_reader_lock:
            if _easyocr_reader is None:
                print("⏳ Đang tải model EasyOCR...")
                _easyocr_reader = _easyocr.Reader(['vi', 'en'], gpu=False)
                print("✅ EasyOCR sẵn sàng!")
    return _easyocr_reader

# ── Scraping state ────────────────────────────────────────────────────────────
scraping_progress = {
    'status': 'idle', 'progress': 0, 'total': 0,
    'current_task': '', 'companies': [], 'logs': []
}

PHONE_RE = re.compile(r'(\+84|0)(3[2-9]|5[25689]|7[06-9]|8[0-9]|9[0-9])\d{7}')


# ═══════════════════════════════════════════════════════════════════════════════
# OCR HELPERS
# ═══════════════════════════════════════════════════════════════════════════════

def _scale_img_bytes(img_bytes):
    """Trả về bytes ảnh đã scale lên nếu quá nhỏ, kèm PIL Image."""
    try:
        ImageFile.LOAD_TRUNCATED_IMAGES = True
        img = Image.open(io.BytesIO(img_bytes)).convert('RGB')
        w, h = img.size
        if w < 400 or h < 60:
            scale = max(400 / w, 60 / h, 3.0)
            img = img.resize((int(w * scale), int(h * scale)), Image.LANCZOS)
        buf = io.BytesIO()
        img.save(buf, format='PNG')
        return buf.getvalue(), img
    except Exception:
        return img_bytes, None


def _clean_phone(text):
    """Trích số điện thoại Việt Nam hợp lệ từ chuỗi text."""
    digits = re.sub(r'\D', '', text)
    # Thử khớp regex chuẩn
    m = PHONE_RE.search(text)
    if m:
        return m.group(0)
    # Fallback: 10 chữ số bắt đầu bằng 0
    if len(digits) == 10 and digits[0] == '0':
        return digits
    if len(digits) == 11 and digits[0] == '0':
        return digits
    return ''


def _format_phone(raw):
    digits = re.sub(r'\D', '', raw)
    if len(digits) == 10:
        return f"{digits[:4]} {digits[4:7]} {digits[7:]}"
    elif len(digits) == 11:
        return f"{digits[:4]} {digits[4:8]} {digits[8:]}"
    return digits


def ocr_with_easyocr(img_bytes):
    """Chạy EasyOCR, trả về (phone_str, confidence 0-1) hoặc ('', 0)."""
    reader = get_easyocr()
    if not reader:
        return '', 0
    try:
        scaled, _ = _scale_img_bytes(img_bytes)
        results = reader.readtext(scaled)
        if not results:
            return '', 0
        best_phone = ''
        best_conf  = 0.0
        full_text  = ' '.join(r[1] for r in results)
        phone = _clean_phone(full_text)
        if phone:
            avg_conf = sum(r[2] for r in results) / len(results)
            return _format_phone(phone), round(avg_conf, 3)
        # Thử từng vùng
        for (_, text, conf) in sorted(results, key=lambda x: -x[2]):
            p = _clean_phone(text)
            if p and conf > best_conf:
                best_phone = _format_phone(p)
                best_conf  = conf
        return best_phone, round(best_conf, 3)
    except Exception:
        return '', 0


def ocr_with_tesseract(img_bytes):
    """Fallback pytesseract, trả về phone_str hoặc ''."""
    if not TESSERACT_AVAILABLE:
        return ''
    try:
        from collections import Counter
        ImageFile.LOAD_TRUNCATED_IMAGES = True
        scaled, img = _scale_img_bytes(img_bytes)
        if img is None:
            img = Image.open(io.BytesIO(scaled)).convert('RGB')
        gray = img.convert('L')
        arr  = np.array(gray)
        candidates = []
        for thresh in [80, 100, 128, 150, 170]:
            binary = Image.fromarray((arr < thresh).astype('uint8') * 255)
            padded = Image.new('L', (binary.width + 40, binary.height + 40), 255)
            padded.paste(binary, (20, 20))
            for psm in [7, 8, 13]:
                cfg = f'--psm {psm} --oem 3 -c tessedit_char_whitelist=0123456789'
                txt = pytesseract.image_to_string(padded, config=cfg).strip()
                p = _clean_phone(txt)
                if p:
                    candidates.append(_format_phone(p))
        if not candidates:
            return ''
        from collections import Counter
        return Counter(candidates).most_common(1)[0][0]
    except Exception:
        return ''


def ocr_best(img_bytes):
    """Thử EasyOCR trước, fallback Tesseract. Trả về (phone, confidence)."""
    phone, conf = ocr_with_easyocr(img_bytes)
    if phone:
        return phone, conf
    phone = ocr_with_tesseract(img_bytes)
    return phone, 0.5 if phone else 0.0


# ═══════════════════════════════════════════════════════════════════════════════
# SCRAPER CLASS
# ═══════════════════════════════════════════════════════════════════════════════

class HSCTVNScraper:
    def __init__(self, delay=1):
        self.base_url = "https://hsctvn.com"
        self.delay    = delay
        self.session  = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })

    def log(self, message, log_type='info'):
        scraping_progress['logs'].append({
            'time': datetime.now().strftime('%H:%M:%S'),
            'type': log_type, 'message': message
        })

    def update_progress(self, current, total, task):
        scraping_progress['progress']     = current
        scraping_progress['total']        = total
        scraping_progress['current_task'] = task

    def get_page(self, url):
        for _ in range(3):
            try:
                r = self.session.get(url, timeout=25)
                r.raise_for_status()
                return r.text
            except Exception as e:
                last = e
                time.sleep(self.delay)
        self.log(f"Lỗi tải {url}: {last}", 'error')
        return None

    def extract_province(self, address):
        provinces = [
            'Hà Nội','Hồ Chí Minh','Đà Nẵng','Hải Phòng','Cần Thơ',
            'An Giang','Bà Rịa - Vũng Tàu','Bắc Giang','Bắc Kạn','Bạc Liêu',
            'Bắc Ninh','Bến Tre','Bình Định','Bình Dương','Bình Phước',
            'Bình Thuận','Cà Mau','Cao Bằng','Đắk Lắk','Đắk Nông',
            'Điện Biên','Đồng Nai','Đồng Tháp','Gia Lai','Hà Giang',
            'Hà Nam','Hà Tĩnh','Hải Dương','Hậu Giang','Hòa Bình',
            'Hưng Yên','Khánh Hòa','Kiên Giang','Kon Tum','Lai Châu',
            'Lâm Đồng','Lạng Sơn','Lào Cai','Long An','Nam Định',
            'Nghệ An','Ninh Bình','Ninh Thuận','Phú Thọ','Phú Yên',
            'Quảng Bình','Quảng Nam','Quảng Ngãi','Quảng Ninh','Quảng Trị',
            'Sóc Trăng','Sơn La','Tây Ninh','Thái Bình','Thái Nguyên',
            'Thanh Hóa','Thừa Thiên Huế','Tiền Giang','Trà Vinh','Tuyên Quang',
            'Vĩnh Long','Vĩnh Phúc','Yên Bái'
        ]
        for p in provinces:
            if p in address:
                return p
        parts = address.split(',')
        return parts[-1].strip() if parts else address

    def parse_company_list(self, html):
        soup      = BeautifulSoup(html, 'html.parser')
        companies = []
        for item in soup.find_all('li'):
            h3 = item.find('h3')
            if not h3:
                continue
            link = h3.find('a')
            if not link:
                continue
            href       = link.get('href', '').lstrip('/')
            detail_url = self.base_url + '/' + href
            company    = {
                'name': link.get_text(strip=True),
                'detail_url': detail_url,
                'tax_code': '', 'address': '', 'phone': '', 'phone_img_key': ''
            }
            div = item.find('div')
            if div:
                text = div.get_text()
                am = re.search(r'Địa chỉ:\s*(.+?)(?:Mã số thuế:|$)', text)
                if am:
                    company['address'] = self.extract_province(am.group(1).strip())
                tm = re.search(r'Mã số thuế:\s*(\d+)', text)
                if tm:
                    company['tax_code'] = tm.group(1)
            companies.append(company)
        return companies

    # ── Phone dict helpers ────────────────────────────────────────────────────
    def _load_phone_dict(self):
        try:
            if os.path.exists(PHONE_DICT_FILE):
                raw = open(PHONE_DICT_FILE, 'r', encoding='utf-8').read().strip()
                if raw:
                    return json.loads(raw)
        except Exception:
            pass
        return {}

    def _save_phone_dict(self, d):
        try:
            with open(PHONE_DICT_FILE, 'w', encoding='utf-8') as f:
                json.dump(d if isinstance(d, dict) else {}, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    @staticmethod
    def _img_key(b64_data):
        return hashlib.md5(b64_data.encode()).hexdigest()

    def _save_unknown_img(self, b64_data, key):
        """Lưu ảnh gốc vào unknown_phones/ để hiển thị trên UI."""
        try:
            os.makedirs(UNKNOWN_DIR, exist_ok=True)
            img_path = os.path.join(UNKNOWN_DIR, f'{key}.png')
            if not os.path.exists(img_path):
                img_bytes = base64.b64decode(b64_data)
                # Lưu ảnh đã scale lớn hơn cho dễ nhìn
                scaled, _ = _scale_img_bytes(img_bytes)
                with open(img_path, 'wb') as f:
                    f.write(scaled)
            return img_path
        except Exception:
            return None

    # ── OCR từ base64 ─────────────────────────────────────────────────────────
    def ocr_phone_from_base64(self, src):
        """Trả về (phone, img_key)."""
        try:
            _, data   = src.split(',', 1)
            img_bytes = base64.b64decode(data)
            key       = self._img_key(data)

            # Dict cache
            phone_dict = self._load_phone_dict()
            if key in phone_dict:
                self.log(f'  📖 Dict hit: {phone_dict[key]}', 'success')
                return phone_dict[key], key

            # Lưu ảnh cho UI
            self._save_unknown_img(data, key)

            # OCR (EasyOCR → Tesseract)
            phone, conf = ocr_best(img_bytes)

            if phone:
                phone_dict[key] = phone
                self._save_phone_dict(phone_dict)
                self.log(f'  🔍 OCR: {phone} (conf={conf:.0%})', 'success')
                return phone, key

            self.log(f'  ⚠ OCR thất bại (key={key[:8]}...) → Phone Dictionary', 'warning')
            return '', key
        except Exception as e:
            self.log(f'OCR error: {e}', 'warning')
            return '', ''

    # ── Lấy SĐT từ trang chi tiết ────────────────────────────────────────────
    def get_phone_from_detail(self, url):
        try:
            time.sleep(self.delay)
            html = self.get_page(url)
            if not html:
                return '', ''
            soup = BeautifulSoup(html, 'html.parser')

            phone_li = None
            for li in soup.find_all('li'):
                if li.find('i', class_=lambda c: c and 'fa-phone' in c):
                    phone_li = li; break
            if not phone_li:
                for li in soup.find_all('li'):
                    if 'Điện thoại' in li.get_text():
                        phone_li = li; break

            scope = phone_li if phone_li else soup

            # Ảnh base64
            for img in scope.find_all('img'):
                src = img.get('src', '')
                if src.startswith('data:image'):
                    return self.ocr_phone_from_base64(src)

            # Text
            text = scope.get_text(separator=' ', strip=True)
            for pat in [
                r'(?:Điện thoại|Số điện thoại|Hotline|Phone|Tel|ĐT)[:\s]*([0-9][0-9\s\.\-\(\)]{8,18})',
                r'(?:Di động|Mobile|SĐT)[:\s]*([0-9][0-9\s\.\-\(\)]{8,18})',
            ]:
                for m in re.findall(pat, text, re.IGNORECASE):
                    d = re.sub(r'[^\d]', '', m.strip())
                    if 9 <= len(d) <= 11:
                        return _format_phone(d), ''
            return '', ''
        except Exception as e:
            self.log(f'get_phone_from_detail: {e}', 'warning')
            return '', ''

    # ── Main scrape ───────────────────────────────────────────────────────────
    def scrape(self, area=None, month=None, from_page=1, to_page=2,
               get_phones=True, start_url=None):
        try:
            scraping_progress.update({'status':'running','companies':[],'logs':[]})
            MAX_PAGES = 50
            to_page   = min(to_page, from_page + MAX_PAGES - 1)

            engine = 'EasyOCR' if EASYOCR_AVAILABLE else ('pytesseract' if TESSERACT_AVAILABLE else 'Không có OCR')
            dict_count = len(self._load_phone_dict())
            self.log(f'OCR engine: {engine} | Phone Dict: {dict_count} entries', 'success')
            self.log(f'Scraping trang {from_page}–{to_page}', 'info')

            all_companies = []
            total_pages   = to_page - from_page + 1

            for page in range(from_page, to_page + 1):
                if start_url:
                    norm  = start_url.rstrip('/')
                    pm    = re.match(r'^(.*?/page-)(\d+)$', norm)
                    url   = f"{pm.group(1)}{page}" if pm else (norm if page == 1 else f"{norm}/page-{page}")
                else:
                    url = (f"{self.base_url}/{month}-{area}" if page == 1
                           else f"{self.base_url}/{month}-{area}/page-{page}")

                self.log(f'Trang {page}/{to_page}: {url}', 'info')
                self.update_progress(page - from_page, total_pages, f'Tải trang {page}')
                html = self.get_page(url)
                if html:
                    cs = self.parse_company_list(html)
                    self.log(f'✓ {len(cs)} công ty', 'success')
                    all_companies.extend(cs)
                else:
                    self.log(f'✗ Không tải được trang {page}', 'error')
                time.sleep(self.delay)

            if get_phones and all_companies:
                self.log(f'Lấy SĐT cho {len(all_companies)} công ty...', 'info')
                for i, c in enumerate(all_companies):
                    self.update_progress(i+1, len(all_companies), f'SĐT: {c["name"]}')
                    self.log(f'[{i+1}/{len(all_companies)}] {c["name"]}', 'info')
                    phone, key = self.get_phone_from_detail(c['detail_url'])
                    c['phone'] = phone; c['phone_img_key'] = key
                    self.log(f'  {"✓ " + phone if phone else "- Không có SĐT"}', 'success' if phone else 'info')
                    scraping_progress['companies'] = all_companies

            total      = len(all_companies)
            with_phone = sum(1 for c in all_companies if c['phone'])
            pending    = len([f for f in os.listdir(UNKNOWN_DIR) if f.endswith('.png')
                              and f[:-4] not in self._load_phone_dict()]) if os.path.exists(UNKNOWN_DIR) else 0

            scraping_progress.update({'companies': all_companies, 'status': 'completed'})
            self.log(f'✓ Xong! {total} công ty | {with_phone} có SĐT | {total-with_phone} không có', 'success')
            if pending:
                self.log(f'⚠ {pending} ảnh SĐT chưa đọc được → tab Phone Dictionary để auto-scan', 'warning')
        except Exception as e:
            scraping_progress['status'] = 'error'
            self.log(f'✗ Lỗi: {e}', 'error')


# ═══════════════════════════════════════════════════════════════════════════════
# API ROUTES
# ═══════════════════════════════════════════════════════════════════════════════

@app.route('/api/scrape', methods=['POST'])
def start_scraping():
    data      = request.json
    raw_url   = re.sub(r'^[^h]*(?=https?://)', '', data.get('startUrl','').strip())
    start_url = raw_url if raw_url.startswith('http') else None
    scraping_progress.update({'status':'running','progress':0,'total':0,'companies':[],'logs':[]})
    def run():
        HSCTVNScraper(delay=float(data.get('delay',1))).scrape(
            area=data.get('area','ha-noi'), month=data.get('month','thang-11/2025'),
            from_page=int(data.get('fromPage',1)), to_page=int(data.get('toPage',2)),
            get_phones=data.get('getPhones',True), start_url=start_url)
    Thread(target=run, daemon=True).start()
    return jsonify({'status': 'started'})


@app.route('/api/progress')
def get_progress():
    return jsonify(scraping_progress)


# ── NEW: Auto-OCR endpoint cho Phone Dictionary UI ───────────────────────────
@app.route('/api/ocr-image/<key>')
def ocr_image(key):
    """FE gọi endpoint này để auto-scan ảnh unknown bằng EasyOCR."""
    try:
        safe = os.path.basename(key)
        if not safe.endswith('.png'):
            safe += '.png'
        img_path = os.path.join(UNKNOWN_DIR, safe)
        if not os.path.exists(img_path):
            return jsonify({'error': 'Không tìm thấy ảnh'}), 404

        with open(img_path, 'rb') as f:
            img_bytes = f.read()

        phone, conf = ocr_best(img_bytes)

        # Nếu tìm được → tự lưu vào dict
        if phone:
            d = {}
            if os.path.exists(PHONE_DICT_FILE):
                try:
                    d = json.loads(open(PHONE_DICT_FILE,'r',encoding='utf-8').read().strip() or '{}')
                except Exception:
                    d = {}
            real_key = safe[:-4]
            if real_key not in d:           # chỉ lưu nếu chưa có
                d[real_key] = phone
                with open(PHONE_DICT_FILE,'w',encoding='utf-8') as f:
                    json.dump(d, f, ensure_ascii=False, indent=2)
                # Backfill bảng kết quả
                for c in scraping_progress.get('companies', []):
                    if c.get('phone_img_key') == real_key and not c.get('phone'):
                        c['phone'] = phone

        return jsonify({'phone': phone, 'confidence': conf})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/phone-dict', methods=['GET'])
def get_phone_dict():
    d = {}
    try:
        if os.path.exists(PHONE_DICT_FILE):
            raw = open(PHONE_DICT_FILE,'r',encoding='utf-8').read().strip()
            d   = json.loads(raw) if raw else {}
        else:
            with open(PHONE_DICT_FILE,'w',encoding='utf-8') as f:
                json.dump({}, f)
    except Exception:
        d = {}
    unknown_files   = [f[:-4] for f in os.listdir(UNKNOWN_DIR) if f.endswith('.png')] if os.path.exists(UNKNOWN_DIR) else []
    unknown_pending = [k for k in unknown_files if k not in d]
    return jsonify({'count': len(d), 'entries': d, 'unknown_pending': unknown_pending, 'unknown_count': len(unknown_pending)})


@app.route('/api/phone-dict', methods=['POST'])
def add_phone_dict():
    try:
        data  = request.json
        phone = data.get('phone','').strip()
        if not phone:
            return jsonify({'error': 'Thiếu phone'}), 400
        key = data.get('key') or (hashlib.md5(data['img_b64'].encode()).hexdigest() if 'img_b64' in data else None)
        if not key:
            return jsonify({'error': 'Cần key hoặc img_b64'}), 400
        phone = _format_phone(phone)
        d = {}
        if os.path.exists(PHONE_DICT_FILE):
            try:
                d = json.loads(open(PHONE_DICT_FILE,'r',encoding='utf-8').read().strip() or '{}')
            except Exception:
                d = {}
        d[key] = phone
        with open(PHONE_DICT_FILE,'w',encoding='utf-8') as f:
            json.dump(d, f, ensure_ascii=False, indent=2)
        updated = 0
        for c in scraping_progress.get('companies', []):
            if c.get('phone_img_key') == key and not c.get('phone'):
                c['phone'] = phone; updated += 1
        return jsonify({'status':'ok','key':key,'phone':phone,'updated_rows':updated})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/phone-dict/<key>', methods=['DELETE'])
def delete_phone_dict(key):
    try:
        d = {}
        if os.path.exists(PHONE_DICT_FILE):
            d = json.loads(open(PHONE_DICT_FILE,'r',encoding='utf-8').read().strip() or '{}')
        d.pop(key, None)
        with open(PHONE_DICT_FILE,'w',encoding='utf-8') as f:
            json.dump(d, f, ensure_ascii=False, indent=2)
        return jsonify({'status':'ok'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/unknown-phones/<filename>')
def serve_unknown_image(filename):
    try:
        safe = os.path.basename(filename)
        if not safe.endswith('.png'): safe += '.png'
        path = os.path.join(UNKNOWN_DIR, safe)
        if not os.path.exists(path):
            return jsonify({'error': 'Not found'}), 404
        return send_file(path, mimetype='image/png')
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/download/excel')
def download_excel():
    try:
        companies = scraping_progress.get('companies', [])
        if not companies:
            return jsonify({'error': 'Không có dữ liệu'}), 404
        df = pd.DataFrame([{
            'STT': i+1, 'Tên công ty': c['name'], 'Mã số thuế': c['tax_code'],
            'Số điện thoại': c['phone'], 'Tỉnh/Thành phố': c['address'],
            'Ngày lấy': datetime.now().strftime('%d/%m/%Y %H:%M:%S')
        } for i, c in enumerate(companies)])
        out = io.BytesIO()
        df.to_excel(out, index=False, engine='openpyxl')
        out.seek(0)
        return send_file(out, mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            as_attachment=True, download_name=f"companies_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx")
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/download/csv')
def download_csv():
    companies = scraping_progress['companies']
    out = io.StringIO()
    out.write('\ufeff')
    w = csv.writer(out)
    w.writerow(['STT','Tên công ty','Mã số thuế','Số điện thoại','Tỉnh/Thành phố'])
    for i, c in enumerate(companies, 1):
        w.writerow([i, c['name'], c['tax_code'], f"'{c['phone']}" if c['phone'] else '', c['address']])
    out.seek(0)
    return send_file(io.BytesIO(out.getvalue().encode('utf-8-sig')), mimetype='text/csv',
        as_attachment=True, download_name=f"companies_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv")


@app.route('/api/download/json')
def download_json():
    out = json.dumps(scraping_progress['companies'], ensure_ascii=False, indent=2)
    return send_file(io.BytesIO(out.encode('utf-8')), mimetype='application/json',
        as_attachment=True, download_name=f"companies_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json")


# ═══════════════════════════════════════════════════════════════════════════════
# FRONTEND
# ═══════════════════════════════════════════════════════════════════════════════

@app.route('/')
def index():
    return r'''<!DOCTYPE html>
<html lang="vi">
<head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>HSCTVN Company Scraper</title>
<link href="https://fonts.googleapis.com/css2?family=Space+Mono:wght@400;700&family=Syne:wght@400;600;800&display=swap" rel="stylesheet">
<style>
*{margin:0;padding:0;box-sizing:border-box}
:root{
  --bg:#f5f2eb;--surface:#fff;--border:#e0dbd0;--text:#1a1814;
  --muted:#888;--accent:#1a1814;--orange:#d4590a;
  --purple:#6d28d9;--green:#059669;--red:#dc2626;--blue:#1d4ed8;
}
body{font-family:'Syne',sans-serif;background:var(--bg);color:var(--text);min-height:100vh}
body::before{
  content:'';position:fixed;inset:0;pointer-events:none;
  background-image:linear-gradient(rgba(0,0,0,.03) 1px,transparent 1px),
    linear-gradient(90deg,rgba(0,0,0,.03) 1px,transparent 1px);
  background-size:40px 40px;
}

/* ── HEADER ── */
.header{
  background:linear-gradient(135deg,#1a1814 0%,#2d1f14 50%,#1a0f08 100%);
  color:var(--bg);padding:36px 40px;text-align:center;position:relative;overflow:hidden;
}
.header::before{
  content:'';position:absolute;inset:0;
  background:radial-gradient(ellipse at 30% 50%,rgba(212,89,10,.15) 0%,transparent 60%),
             radial-gradient(ellipse at 70% 50%,rgba(109,40,217,.1) 0%,transparent 60%);
}
.header h1{position:relative;font-size:2.2em;font-weight:800;letter-spacing:-1px;margin-bottom:6px}
.header h1 span{color:#d4590a}
.header p{position:relative;opacity:.7;font-family:'Space Mono',monospace;font-size:.85em;letter-spacing:1px}

/* ── TABS ── */
.tabs{display:flex;background:var(--surface);border-bottom:2px solid var(--border)}
.tab{
  padding:14px 28px;cursor:pointer;font-weight:700;color:var(--muted);font-size:.95em;
  border-bottom:3px solid transparent;transition:all .2s;display:flex;align-items:center;gap:8px;
}
.tab:hover{color:var(--orange);background:#fdf6f0}
.tab.active{color:var(--orange);border-bottom-color:var(--orange);background:var(--surface)}
.badge{
  background:var(--red);color:#fff;border-radius:10px;padding:1px 8px;
  font-size:.72em;font-weight:700;font-family:'Space Mono',monospace;
}

/* ── LAYOUT ── */
.tab-content{display:none;padding:28px 32px 40px;max-width:1280px;margin:0 auto}
.tab-content.active{display:block}
.section{
  background:var(--surface);padding:24px 26px;border-radius:10px;
  margin-bottom:24px;border:1px solid var(--border);
  box-shadow:0 4px 20px rgba(0,0,0,.05);
}
.section h2{
  margin-bottom:16px;color:var(--text);font-size:1.2em;font-weight:800;
  display:flex;align-items:center;gap:10px;
}

/* ── FORM ── */
.form-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:16px;margin-bottom:18px}
.form-group.full{grid-column:1/-1}
.form-group label{display:block;margin-bottom:7px;font-weight:700;font-size:.9em;color:var(--muted)}
.form-group input{
  width:100%;padding:11px 14px;border:2px solid var(--border);
  border-radius:6px;font-size:.95em;transition:border .2s;background:var(--bg);
}
.form-group input:focus{outline:none;border-color:var(--orange);background:var(--surface)}
.checkbox-group{display:flex;align-items:center;gap:10px;margin-top:14px}
.checkbox-group input[type=checkbox]{width:18px;height:18px;accent-color:var(--orange)}

/* ── BUTTONS ── */
.btn{
  background:var(--accent);color:var(--bg);border:none;
  padding:14px 36px;border-radius:6px;font-size:1em;cursor:pointer;
  font-weight:800;font-family:'Syne',sans-serif;transition:all .2s;
  display:inline-flex;align-items:center;gap:10px;margin-top:20px;
}
.btn:hover:not(:disabled){background:#2e2b24;transform:translateY(-2px);box-shadow:0 8px 24px rgba(0,0,0,.15)}
.btn:disabled{opacity:.35;cursor:not-allowed;transform:none}
.btn-sm{
  padding:7px 14px;font-size:.85em;border-radius:5px;border:none;
  cursor:pointer;font-weight:700;transition:all .15s;font-family:'Syne',sans-serif;
}
.btn-green{background:var(--green);color:#fff}.btn-green:hover{background:#047857}
.btn-red{background:var(--red);color:#fff}.btn-red:hover{background:#b91c1c}
.btn-blue{background:var(--blue);color:#fff}.btn-blue:hover{background:#1e40af}

/* ── PROGRESS ── */
.progress-section{display:none}
.pbar-wrap{height:36px;background:#e9ecef;border-radius:18px;overflow:hidden;margin-bottom:16px;box-shadow:inset 0 2px 4px rgba(0,0,0,.07)}
.pbar-fill{
  height:100%;background:linear-gradient(90deg,var(--orange) 0%,var(--purple) 100%);
  width:0%;transition:width .3s;display:flex;align-items:center;justify-content:center;
  color:#fff;font-weight:700;font-size:1em;font-family:'Space Mono',monospace;
}
.pbar-text{text-align:center;color:var(--muted);font-family:'Space Mono',monospace;font-size:.85em;margin-bottom:12px}
.log-box{
  background:#111;border-radius:8px;padding:18px;max-height:280px;overflow-y:auto;
  font-family:'Space Mono',monospace;font-size:.82em;
}
.log-box::-webkit-scrollbar{width:4px}.log-box::-webkit-scrollbar-thumb{background:#333;border-radius:2px}
.log-entry{margin-bottom:6px;line-height:1.5}
.log-time{color:#555}.log-info{color:#0ff}.log-success{color:#0f0}.log-error{color:#f55}.log-warning{color:#ff0}

/* ── STATS ── */
.stats{display:grid;grid-template-columns:repeat(3,1fr);gap:16px;margin-bottom:20px}
.stat-card{
  background:var(--text);color:var(--bg);padding:22px;border-radius:10px;text-align:center;
}
.stat-card .n{font-size:2.6em;font-weight:800;letter-spacing:-1px;color:var(--orange)}
.stat-card .l{opacity:.7;font-size:.85em;font-family:'Space Mono',monospace;margin-top:4px}

/* ── TABLE ── */
.results-section{display:none}
.search-box input{
  width:100%;padding:13px 16px;border:2px solid var(--border);border-radius:6px;
  font-size:.95em;margin-bottom:16px;background:var(--bg);
}
.search-box input:focus{outline:none;border-color:var(--orange);background:var(--surface)}
.table-wrap{overflow-x:auto;border-radius:8px;border:1px solid var(--border)}
table{width:100%;border-collapse:collapse;background:var(--surface)}
thead{background:var(--accent);color:var(--bg)}
th,td{padding:13px 16px;text-align:left;border-bottom:1px solid var(--border);font-size:.9em}
tbody tr:hover{background:#fdf6f0}
tbody tr:nth-child(even){background:#faf8f4}
.download-bar{display:flex;gap:12px;flex-wrap:wrap;margin-top:20px;justify-content:center}
.dl-btn{
  padding:11px 24px;background:var(--green);color:#fff;border:none;border-radius:6px;
  font-weight:700;cursor:pointer;transition:all .2s;font-family:'Syne',sans-serif;
  display:inline-flex;align-items:center;gap:8px;
}
.dl-btn:hover{background:#047857;transform:translateY(-2px);box-shadow:0 6px 20px rgba(5,150,105,.3)}

/* ═══════════════════════════════════════════════════
   PHONE DICTIONARY — auto-scan styles
═══════════════════════════════════════════════════ */
.dict-stats{display:flex;gap:14px;margin-bottom:20px;flex-wrap:wrap}
.dict-stat{
  background:var(--text);color:var(--bg);padding:14px 20px;border-radius:8px;
  text-align:center;min-width:120px;
}
.dict-stat.warn{background:linear-gradient(135deg,#b45309,var(--red))}
.dict-stat .n{font-size:1.9em;font-weight:800;color:var(--orange)}
.dict-stat.warn .n{color:#fde68a}
.dict-stat .l{font-size:.75em;opacity:.8;font-family:'Space Mono',monospace;margin-top:2px}

.dict-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(270px,1fr));gap:16px;margin-top:12px}
.dict-empty{text-align:center;color:var(--muted);padding:32px;font-family:'Space Mono',monospace;font-size:.9em}

/* Card */
.dict-card{
  border:2px solid var(--border);border-radius:10px;
  background:var(--surface);overflow:hidden;transition:border .2s;
}
.dict-card.scanning{border-color:var(--orange)}
.dict-card.found{border-color:var(--green)}
.dict-card.saved{border-color:var(--green);background:#f0fdf4}
.dict-card.error-state{border-color:var(--red)}

/* Image area with scan overlay */
.card-img-wrap{
  position:relative;background:#111;min-height:60px;
  display:flex;align-items:center;justify-content:center;padding:14px;
}
.card-img-wrap img{max-width:100%;image-rendering:pixelated;display:block}

/* Scan beam overlay */
.card-scan-overlay{
  position:absolute;inset:0;
  background:rgba(17,17,17,.75);
  display:flex;flex-direction:column;align-items:center;justify-content:center;
  gap:10px;opacity:0;pointer-events:none;transition:opacity .2s;
}
.card-scan-overlay.active{opacity:1}
.scan-beam{
  width:70%;height:2px;
  background:linear-gradient(90deg,transparent,var(--orange),transparent);
  animation:beam 1.1s ease-in-out infinite;
}
@keyframes beam{
  0%{transform:translateY(-24px);opacity:0}20%{opacity:1}80%{opacity:1}100%{transform:translateY(24px);opacity:0}
}
.scan-txt{font-family:'Space Mono',monospace;font-size:.7em;color:var(--orange);letter-spacing:2px}

/* Timer ring */
.card-timer{
  position:absolute;top:6px;right:6px;
  width:30px;height:30px;display:none;
}
.card-timer svg{width:30px;height:30px;transform:rotate(-90deg)}
.card-timer circle.trk{fill:rgba(255,255,255,.1);stroke:#555;stroke-width:2.5}
.card-timer circle.prg{fill:none;stroke:var(--orange);stroke-width:2.5;stroke-dasharray:72;stroke-dashoffset:72;stroke-linecap:round;transition:stroke-dashoffset .08s linear}
.card-timer .tnum{
  position:absolute;inset:0;display:flex;align-items:center;justify-content:center;
  font-family:'Space Mono',monospace;font-size:.65em;font-weight:700;color:var(--orange);
}

/* Card body */
.card-body{padding:14px}
.card-key{font-family:'Space Mono',monospace;font-size:.68em;color:var(--muted);margin-bottom:10px;word-break:break-all}

/* Confidence bar */
.conf-row{display:flex;justify-content:space-between;font-family:'Space Mono',monospace;font-size:.72em;color:var(--muted);margin-bottom:4px}
.conf-bar{height:3px;background:var(--border);border-radius:2px;overflow:hidden;margin-bottom:10px}
.conf-fill{height:100%;border-radius:2px;transition:width .5s ease}

.input-row{display:flex;gap:8px}
.input-row input{
  flex:1;padding:8px 11px;border:2px solid var(--border);border-radius:6px;
  font-size:.95em;font-family:'Space Mono',monospace;background:var(--bg);transition:border .15s;
}
.input-row input:focus{outline:none;border-color:var(--orange);background:var(--surface)}
.input-row input.ocr-filled{border-color:var(--green);background:#f0fdf4}

.ocr-hint{
  margin-top:6px;font-family:'Space Mono',monospace;font-size:.72em;
  color:var(--green);display:none;
}
.saved-phone{
  text-align:center;font-size:1.4em;font-weight:800;
  color:var(--green);margin-top:8px;font-family:'Space Mono',monospace;letter-spacing:1px;
}

/* Known entries */
.known-entry{
  display:flex;align-items:center;gap:12px;padding:10px 14px;
  border:1px solid #d1fae5;border-radius:8px;background:#f0fdf4;margin-bottom:8px;
}
.known-img{height:28px;image-rendering:pixelated;background:#111;padding:2px 6px;border-radius:4px}
.known-key{font-family:'Space Mono',monospace;font-size:.75em;color:var(--muted);flex:1}
.known-phone{font-weight:700;color:var(--green);min-width:130px;font-family:'Space Mono',monospace}

/* Alert */
.alert{padding:12px 16px;border-radius:7px;margin-bottom:16px;font-size:.9em;font-weight:600}
.alert-info{background:#dbeafe;color:var(--blue);border:1px solid #93c5fd}
.alert-success{background:#d1fae5;color:var(--green);border:1px solid #6ee7b7}

/* Spinner */
@keyframes spin{to{transform:rotate(360deg)}}
.spinner{
  display:inline-block;width:18px;height:18px;
  border:2.5px solid rgba(245,242,235,.3);border-top-color:var(--bg);
  border-radius:50%;animation:spin .7s linear infinite;
}

/* Toast */
.toast{
  position:fixed;bottom:24px;right:24px;
  background:var(--text);color:var(--bg);
  font-family:'Space Mono',monospace;font-size:.85em;
  padding:12px 20px;border-radius:6px;
  opacity:0;pointer-events:none;transition:all .25s;
  transform:translateY(12px);z-index:9999;
  box-shadow:0 6px 24px rgba(0,0,0,.2);
}
.toast.show{opacity:1;transform:translateY(0)}
</style>
</head>
<body>

<div class="header">
  <h1>🏢 HSCTVN <span>Scraper</span></h1>
  <p>EASYOCR AUTO-SCAN · PHONE DICTIONARY · EXPORT EXCEL/CSV/JSON</p>
</div>

<div class="tabs">
  <div class="tab active" onclick="switchTab('scraper',event)">🚀 Scraper</div>
  <div class="tab" onclick="switchTab('dict',event)">
    📖 Phone Dictionary
    <span class="badge" id="unknownBadge" style="display:none">0</span>
  </div>
</div>

<!-- ═══ TAB SCRAPER ═══════════════════════════════════════════════════════════ -->
<div id="tab-scraper" class="tab-content active">
  <div class="section">
    <h2>⚙️ Cấu hình Scraping</h2>
    <div class="form-grid">
      <div class="form-group full">
        <label>🔗 URL trang 1</label>
        <input type="text" id="startUrl" placeholder="https://hsctvn.com/industry-...">
      </div>
      <div class="form-group"><label>📄 Từ trang</label><input type="number" id="fromPage" value="1" min="1"></div>
      <div class="form-group"><label>📄 Đến trang</label><input type="number" id="toPage" value="2" min="1"></div>
      <div class="form-group"><label>⏱ Delay (giây)</label><input type="number" id="delay" value="1" min="0.5" step="0.5"></div>
    </div>
    <div class="checkbox-group">
      <input type="checkbox" id="getPhones" checked>
      <label for="getPhones">Lấy số điện thoại từ trang chi tiết</label>
    </div>
    <button class="btn" id="startBtn" onclick="startScraping()">
      <span id="btnText">🚀 Bắt đầu scraping</span>
    </button>
  </div>

  <div class="section progress-section" id="progressSection">
    <h2>⏳ Tiến trình</h2>
    <div class="pbar-wrap"><div class="pbar-fill" id="progressFill">0%</div></div>
    <div class="pbar-text" id="progressText">Đang chuẩn bị...</div>
    <div class="log-box" id="logContainer"></div>
  </div>

  <div class="section results-section" id="resultsSection">
    <h2>📊 Kết quả</h2>
    <div class="stats">
      <div class="stat-card"><div class="n" id="totalCompanies">0</div><div class="l">Tổng công ty</div></div>
      <div class="stat-card"><div class="n" id="withPhones">0</div><div class="l">Có số điện thoại</div></div>
      <div class="stat-card"><div class="n" id="withoutPhones">0</div><div class="l">Không có SĐT</div></div>
    </div>
    <div class="search-box"><input type="text" id="searchInput" placeholder="🔍 Tìm kiếm..." oninput="filterResults()"></div>
    <div class="table-wrap">
      <table><thead><tr><th>#</th><th>Tên công ty</th><th>Mã số thuế</th><th>Số điện thoại</th><th>Tỉnh/Thành phố</th></tr></thead>
      <tbody id="resultsBody"></tbody></table>
    </div>
    <div class="download-bar">
      <button class="dl-btn" onclick="location.href=API+'/api/download/csv'">📥 CSV</button>
      <button class="dl-btn" onclick="location.href=API+'/api/download/json'">📥 JSON</button>
      <button class="dl-btn" onclick="location.href=API+'/api/download/excel'">📊 Excel</button>
      <button class="dl-btn" onclick="copyAll()">📋 Copy</button>
    </div>
  </div>
</div>

<!-- ═══ TAB PHONE DICTIONARY ══════════════════════════════════════════════════ -->
<div id="tab-dict" class="tab-content">
  <div class="section">
    <h2>📖 Phone Dictionary — Auto-scan</h2>
    <div class="alert alert-info" id="dictAlert">
      ⚡ EasyOCR sẽ <strong>tự động quét</strong> từng ảnh sau 0.8 giây.
      Nếu đọc được → tự điền vào ô nhập. Kiểm tra rồi bấm <strong>💾 Lưu</strong>.
      Nếu sai → sửa tay rồi lưu.
    </div>
    <div class="dict-stats" id="dictStats">
      <div class="dict-stat"><div class="n">...</div><div class="l">Đã nhận diện</div></div>
    </div>

    <div id="unknownSection">
      <h3 style="margin-bottom:12px;color:#92400e;font-weight:800">⚠ Chưa nhận diện</h3>
      <div class="dict-grid" id="unknownGrid">
        <div class="dict-empty">Đang tải...</div>
      </div>
    </div>

    <div id="knownSection" style="margin-top:28px">
      <h3 style="margin-bottom:12px;color:var(--green);font-weight:800">✅ Đã nhận diện</h3>
      <div id="knownList"></div>
    </div>
  </div>
</div>

<div class="toast" id="toast"></div>

<script>
const API = window.location.origin;
let currentData = [], filteredData = [], progressInterval = null;

// ── Tab switch ──────────────────────────────────────────────────────────────
function switchTab(name, e) {
  document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
  document.querySelectorAll('.tab-content').forEach(t => t.classList.remove('active'));
  e.currentTarget.classList.add('active');
  document.getElementById('tab-' + name).classList.add('active');
  if (name === 'dict') loadPhoneDict();
}

// ── Scraper ─────────────────────────────────────────────────────────────────
async function startScraping() {
  const cfg = {
    startUrl: document.getElementById('startUrl').value.trim().replace(/^[^h]*(?=https?:\/\/)/,''),
    fromPage: +document.getElementById('fromPage').value,
    toPage:   +document.getElementById('toPage').value,
    delay:    +document.getElementById('delay').value,
    getPhones: document.getElementById('getPhones').checked
  };
  if (!cfg.startUrl) { alert('Vui lòng nhập URL!'); return; }
  if (cfg.fromPage > cfg.toPage) { alert('Từ trang phải ≤ Đến trang!'); return; }
  document.getElementById('startBtn').disabled = true;
  document.getElementById('btnText').innerHTML = '<span class="spinner"></span> Đang scraping...';
  document.getElementById('progressSection').style.display = 'block';
  document.getElementById('resultsSection').style.display  = 'none';
  document.getElementById('logContainer').innerHTML = '';
  try {
    await fetch(API+'/api/scrape',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(cfg)});
    progressInterval = setInterval(checkProgress, 1000);
  } catch(e) { alert('Lỗi: '+e.message); resetUI(); }
}

async function checkProgress() {
  try {
    const d = await (await fetch(API+'/api/progress')).json();
    if (d.total > 0) {
      const pct = Math.round(d.progress/d.total*100);
      document.getElementById('progressFill').style.width = pct+'%';
      document.getElementById('progressFill').textContent = pct+'%';
    }
    document.getElementById('progressText').textContent = d.current_task||'Đang xử lý...';
    const lc = document.getElementById('logContainer');
    lc.innerHTML = d.logs.map(l=>
      `<div class="log-entry"><span class="log-time">[${l.time}]</span> <span class="log-${l.type}">${l.message}</span></div>`
    ).join('');
    lc.scrollTop = lc.scrollHeight;
    if (d.companies?.length) { currentData = d.companies; updateResultsLive(d.companies); }
    if (d.status === 'completed') {
      clearInterval(progressInterval); currentData = d.companies; displayResults(); resetUI(); loadDictBadge();
    } else if (d.status === 'error') {
      clearInterval(progressInterval); alert('Có lỗi xảy ra!'); resetUI();
    }
  } catch(e) { console.error(e); }
}

function updateResultsLive(cs) {
  const wp = cs.filter(c=>c.phone).length;
  document.getElementById('totalCompanies').textContent   = cs.length;
  document.getElementById('withPhones').textContent       = wp;
  document.getElementById('withoutPhones').textContent    = cs.length - wp;
  if (!document.getElementById('searchInput').value) { filteredData=[...cs]; renderTable(filteredData); }
  document.getElementById('resultsSection').style.display = 'block';
}
function displayResults() {
  filteredData = [...currentData];
  updateResultsLive(currentData);
  renderTable(filteredData);
}
function renderTable(data) {
  document.getElementById('resultsBody').innerHTML = data.map((c,i)=>
    `<tr><td>${i+1}</td><td>${esc(c.name)}</td><td>${c.tax_code}</td><td>${c.phone||'—'}</td><td>${c.address}</td></tr>`
  ).join('');
}
function filterResults() {
  const s = document.getElementById('searchInput').value.toLowerCase();
  filteredData = currentData.filter(c =>
    c.name.toLowerCase().includes(s)||c.address.toLowerCase().includes(s)||
    (c.phone||'').includes(s)||c.tax_code.includes(s)
  );
  renderTable(filteredData);
}
function copyAll() {
  navigator.clipboard.writeText(filteredData.map(c=>`${c.name}\t${c.tax_code}\t${c.phone}\t${c.address}`).join('\n'))
    .then(()=>showToast('✓ Đã copy!'));
}
function resetUI() {
  document.getElementById('startBtn').disabled = false;
  document.getElementById('btnText').innerHTML = '🚀 Bắt đầu scraping';
}

// ══════════════════════════════════════════════════
// PHONE DICTIONARY — auto-scan logic
// ══════════════════════════════════════════════════
const SCAN_DELAY = 800;  // ms trước khi tự quét

async function loadPhoneDict() {
  try {
    const res  = await fetch(API+'/api/phone-dict');
    const data = await res.json();

    const dictCount    = data.count || 0;
    const unknownCount = data.unknown_count || 0;
    document.getElementById('dictStats').innerHTML =
      `<div class="dict-stat"><div class="n">${dictCount}</div><div class="l">Đã nhận diện</div></div>` +
      `<div class="dict-stat warn"><div class="n">${unknownCount}</div><div class="l">Chưa nhận diện</div></div>`;

    const grid    = document.getElementById('unknownGrid');
    const pending = data.unknown_pending || [];

    if (!pending.length) {
      grid.innerHTML = '<div class="dict-empty">✅ Không có ảnh nào cần xử lý</div>';
    } else {
      grid.innerHTML = pending.map(key => buildCard(key)).join('');
      // Stagger auto-scan: mỗi card cách nhau SCAN_DELAY + 400ms để tránh flood
      pending.forEach((key, idx) => {
        setTimeout(() => autoScanCard(key), SCAN_DELAY + idx * 450);
      });
    }

    // Known list
    const knownList = document.getElementById('knownList');
    const entries   = data.entries || {};
    const keys      = Object.keys(entries);
    knownList.innerHTML = !keys.length
      ? '<div class="dict-empty">Chưa có entry nào</div>'
      : keys.map(k => `
        <div class="known-entry">
          <img class="known-img" src="${API}/api/unknown-phones/${k}.png" onerror="this.style.display='none'">
          <span class="known-key">${k.substring(0,18)}...</span>
          <span class="known-phone">${entries[k]}</span>
          <button class="btn-sm btn-red" onclick="deleteEntry('${k}')">🗑 Xoá</button>
        </div>`).join('');
  } catch(e) { console.error(e); }
}

function buildCard(key) {
  return `
  <div class="dict-card" id="card-${key}">
    <div class="card-img-wrap">
      <img src="${API}/api/unknown-phones/${key}.png"
           onerror="this.parentElement.innerHTML='<span style=color:#666;font-size:.8em>Không tải được ảnh</span>'">
      <!-- Scan overlay -->
      <div class="card-scan-overlay" id="overlay-${key}">
        <div class="scan-beam"></div>
        <div class="scan-txt">ĐANG QUÉT...</div>
      </div>
      <!-- Timer ring -->
      <div class="card-timer" id="timer-${key}">
        <svg viewBox="0 0 30 30">
          <circle class="trk" cx="15" cy="15" r="11.5"/>
          <circle class="prg" cx="15" cy="15" r="11.5" id="tcirc-${key}"/>
        </svg>
        <div class="tnum" id="tnum-${key}"></div>
      </div>
    </div>
    <div class="card-body">
      <div class="card-key">Key: ${key.substring(0,16)}…</div>
      <!-- Confidence bar (hidden until scan) -->
      <div id="conf-${key}" style="display:none">
        <div class="conf-row"><span>Độ tin cậy EasyOCR</span><span id="cpct-${key}" style="font-weight:700">—</span></div>
        <div class="conf-bar"><div class="conf-fill" id="cfill-${key}" style="width:0%"></div></div>
      </div>
      <div class="input-row">
        <input type="text" id="inp-${key}" placeholder="Nhập SĐT…"
               onkeydown="if(event.key==='Enter')savePhone('${key}')">
        <button class="btn-sm btn-green" onclick="savePhone('${key}')">💾 Lưu</button>
      </div>
      <div class="ocr-hint" id="hint-${key}">⚡ OCR tự động điền — kiểm tra rồi lưu</div>
    </div>
  </div>`;
}

// ── Countdown + Auto-scan ────────────────────────────────────────────────────
function autoScanCard(key) {
  const timerEl   = document.getElementById('timer-' + key);
  const circEl    = document.getElementById('tcirc-' + key);
  const tnumEl    = document.getElementById('tnum-' + key);
  const overlayEl = document.getElementById('overlay-' + key);
  if (!timerEl) return;  // card đã bị remove

  const circumference = 2 * Math.PI * 11.5; // ~72.3
  timerEl.style.display = 'block';

  const start = performance.now();
  let rafId;
  function tick(now) {
    const elapsed  = now - start;
    const remain   = Math.max(0, SCAN_DELAY - elapsed);
    const progress = elapsed / SCAN_DELAY;
    circEl.style.strokeDashoffset = circumference * (1 - Math.min(progress, 1));
    tnumEl.textContent = remain > 100 ? (remain/1000).toFixed(1).replace(/\.0$/,'') : '';
    if (elapsed < SCAN_DELAY) {
      rafId = requestAnimationFrame(tick);
    } else {
      timerEl.style.display = 'none';
      runOCR(key, overlayEl);
    }
  }
  rafId = requestAnimationFrame(tick);
}

async function runOCR(key, overlayEl) {
  if (overlayEl) overlayEl.classList.add('active');
  try {
    const res  = await fetch(`${API}/api/ocr-image/${key}`);
    const data = await res.json();

    if (overlayEl) overlayEl.classList.remove('active');

    const card  = document.getElementById('card-' + key);
    const input = document.getElementById('inp-' + key);
    if (!card || !input) return;

    if (data.phone) {
      // Điền vào input
      input.value = data.phone;
      input.classList.add('ocr-filled');
      document.getElementById('hint-' + key).style.display = 'block';
      card.classList.add('found');

      // Hiện confidence bar
      const pct   = Math.round((data.confidence || 0) * 100);
      const color = pct > 75 ? '#059669' : pct > 50 ? '#d97706' : '#dc2626';
      document.getElementById('conf-' + key).style.display     = 'block';
      document.getElementById('cpct-' + key).textContent        = pct + '%';
      document.getElementById('cpct-' + key).style.color        = color;
      document.getElementById('cfill-' + key).style.width       = pct + '%';
      document.getElementById('cfill-' + key).style.background  = color;

      // Nếu confidence cao → flash lưu được tự động
      if (pct >= 90) {
        showToast(`✅ Auto-scan: ${data.phone} (${pct}%)`);
        // Tự mark là saved
        setTimeout(() => markSaved(key, data.phone), 500);
      }
    } else {
      card.classList.add('error-state');
      input.placeholder = 'OCR thất bại — nhập tay';
    }
  } catch(e) {
    if (overlayEl) overlayEl.classList.remove('active');
    const card = document.getElementById('card-' + key);
    if (card) card.classList.add('error-state');
  }
}

// ── Save phone ───────────────────────────────────────────────────────────────
async function savePhone(key) {
  const input = document.getElementById('inp-' + key);
  const phone = (input?.value || '').trim();
  if (!phone) { input?.focus(); return; }

  const res  = await fetch(API+'/api/phone-dict', {
    method:'POST', headers:{'Content-Type':'application/json'},
    body: JSON.stringify({ key, phone })
  });
  const data = await res.json();
  if (data.status === 'ok') {
    markSaved(key, data.phone);
    if (data.updated_rows > 0) {
      refreshTable();
      showToast(`✅ Đã cập nhật ${data.updated_rows} công ty trong bảng`);
    } else {
      showToast('✅ Đã lưu: ' + data.phone);
    }
    loadDictBadge();
  } else { alert('Lỗi: ' + (data.error||'unknown')); }
}

function markSaved(key, phone) {
  const card = document.getElementById('card-' + key);
  if (!card) return;
  card.className = 'dict-card saved';
  card.innerHTML = `
    <div class="card-img-wrap">
      <img src="${API}/api/unknown-phones/${key}.png" onerror="this.style.display='none'">
    </div>
    <div class="card-body">
      <div class="saved-phone">${phone}</div>
      <div style="text-align:center;color:var(--green);font-family:'Space Mono',monospace;font-size:.75em;margin-top:6px">✅ Đã lưu</div>
    </div>`;
}

async function refreshTable() {
  try {
    const d = await (await fetch(API+'/api/progress')).json();
    if (d.companies?.length) {
      currentData  = d.companies;
      filteredData = [...currentData];
      renderTable(filteredData);
      updateResultsLive(currentData);
    }
  } catch(e) {}
}

async function deleteEntry(key) {
  if (!confirm('Xoá entry này?')) return;
  await fetch(API+'/api/phone-dict/'+key, {method:'DELETE'});
  loadPhoneDict();
}

async function loadDictBadge() {
  try {
    const d = await (await fetch(API+'/api/phone-dict')).json();
    const b = document.getElementById('unknownBadge');
    if (d.unknown_count > 0) { b.textContent = d.unknown_count; b.style.display='inline-block'; }
    else { b.style.display='none'; }
  } catch(e) {}
}

function showToast(msg) {
  const t = document.getElementById('toast');
  t.textContent = msg; t.classList.add('show');
  setTimeout(() => t.classList.remove('show'), 2500);
}

function esc(s) {
  return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
}

// Init
loadDictBadge();
setInterval(loadDictBadge, 5000);
</script>
</body></html>'''


# ═══════════════════════════════════════════════════════════════════════════════
if __name__ == '__main__':
    # Pre-load EasyOCR model khi khởi động
    if EASYOCR_AVAILABLE:
        Thread(target=get_easyocr, daemon=True).start()

    print("=" * 65)
    print("  🚀 HSCTVN Scraper — EasyOCR Auto-scan Edition")
    print("=" * 65)
    ocr_status = "EasyOCR ✅" if EASYOCR_AVAILABLE else ("pytesseract ⚠" if TESSERACT_AVAILABLE else "Không có OCR ❌")
    print(f"  OCR Engine : {ocr_status}")
    print(f"  Server     : http://localhost:5001")
    print("=" * 65 + "\n")
    app.run(debug=True, host='0.0.0.0', port=5001)