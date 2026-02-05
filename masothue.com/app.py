from flask import Flask, render_template, request, jsonify, send_file
import requests
from bs4 import BeautifulSoup
import csv
import os
from datetime import datetime
import time

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = 'exports'

# Tạo folder exports nếu chưa tồn tại
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)


def scrape_companies(url, start_page, end_page):
    """Lấy dữ liệu công ty từ website"""
    companies = []
    # Xử lý URL để đảm bảo không có tham số page trong URL gốc
    base_url = url.split('?')[0]  # Lấy phần trước dấu ?

    for page in range(start_page, end_page + 1):
        try:
            url = f"{base_url}?page={page}"
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            }
            response = requests.get(url, headers=headers, timeout=10)
            response.encoding = 'utf-8'
            soup = BeautifulSoup(response.content, 'html.parser')

            # Tìm tất cả công ty trên trang
            items = soup.select('.tax-listing > div[data-prefetch]')

            if not items:
                break  # Không tìm thấy công ty, dừng lại

            for item in items:
                try:
                    name_elem = item.select_one('h3 a')
                    tax_id_elem = item.find('i', class_='fa-hashtag')
                    rep_elem = item.find('i', class_='fa-user')
                    addr_elem = item.find('i', class_='fa-map-marker')

                    if not name_elem:
                        continue

                    name = name_elem.text.strip()

                    # Lấy mã số thuế
                    tax_id = "N/A"
                    if tax_id_elem:
                        tax_text = tax_id_elem.parent.text
                        tax_id = tax_text.replace('Mã số thuế:', '').strip()
                        tax_id = tax_id.split('\n')[0]

                    # Lấy người đại diện
                    representative = "N/A"
                    if rep_elem:
                        rep_text = rep_elem.parent.text
                        representative = rep_text.replace('Người đại diện:', '').strip()
                        representative = representative.split('\n')[0]

                    # Lấy địa chỉ
                    address = "N/A"
                    if addr_elem:
                        address = addr_elem.parent.text.strip()

                    companies.append({
                        'Tên công ty': name,
                        'Mã số thuế': tax_id,
                        'Người đại diện': representative,
                        'Địa chỉ': address
                    })
                except Exception as e:
                    print(f"Lỗi khi parse item: {e}")
                    continue

            print(f"✓ Đã lấy trang {page} - {len(items)} công ty")
            time.sleep(1)  # Delay 1 giây giữa các request

        except Exception as e:
            print(f"Lỗi trang {page}: {e}")
            continue

    return companies


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/api/scrape', methods=['POST'])
def scrape():
    data = request.json
    url = data.get('url', '').strip()
    start_page = int(data.get('start_page', 1))
    end_page = int(data.get('end_page', 1))

    # Validate input
    if not url:
        return jsonify({'error': 'Vui lòng nhập URL tra cứu'}), 400
    
    if not url.startswith('https://masothue.com/'):
        return jsonify({'error': 'URL không hợp lệ. Vui lòng sử dụng URL từ trang masothue.com'}), 400

    if start_page < 1 or end_page < start_page:
        return jsonify({'error': 'Số trang không hợp lệ'}), 400

    if end_page - start_page > 50:
        return jsonify({'error': 'Tối đa 50 trang mỗi lần'}), 400

    try:
        companies = scrape_companies(url, start_page, end_page)

        if not companies:
            return jsonify({'error': 'Không tìm thấy công ty nào'}), 404

        # Lưu file CSV
        filename = f"companies_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)

        with open(filepath, 'w', encoding='utf-8-sig', newline='') as f:
            fieldnames = ['Tên công ty', 'Mã số thuế', 'Người đại diện', 'Địa chỉ']
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(companies)

        return jsonify({
            'success': True,
            'count': len(companies),
            'filename': filename,
            'data': companies[:10]  # Gửi 10 dòng đầu tiên
        })

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/download/<filename>')
def download(filename):
    filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    if os.path.exists(filepath):
        return send_file(filepath, as_attachment=True)
    return jsonify({'error': 'File không tồn tại'}), 404


if __name__ == '__main__':
    app.run(debug=True, port=5001)