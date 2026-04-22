from flask import Flask, render_template, request, jsonify, send_file
from scraper import MaSoThueScraper
import threading
import os
from datetime import datetime

app = Flask(__name__)
scraper = MaSoThueScraper()
scraping_thread = None


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/scrape', methods=['POST'])
def scrape():
    global scraping_thread

    data = request.json
    url = data.get('url')
    from_page = int(data.get('from_page'))
    to_page = int(data.get('to_page'))
    filter_year = data.get('filter_year') if data.get('filter_year') else None
    filter_industry = data.get('filter_industry') if data.get('filter_industry') else None

    if scraping_thread and scraping_thread.is_alive():
        return jsonify({'error': 'Đang có tiến trình scraping khác đang chạy'}), 400

    def run_scraper():
        scraper.scrape(url, from_page, to_page, filter_year, filter_industry)

    scraping_thread = threading.Thread(target=run_scraper)
    scraping_thread.start()

    return jsonify({'message': 'Bắt đầu scraping'})


@app.route('/progress')
def progress():
    return jsonify(scraper.get_progress())


@app.route('/download')
def download():
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    filename = f'ket_qua_{timestamp}.xlsx'
    filepath = scraper.export_to_excel(filename)

    if filepath and os.path.exists(filepath):
        return send_file(filepath, as_attachment=True, download_name=filename)
    else:
        return jsonify({'error': 'Không có dữ liệu để tải'}), 404


if __name__ == '__main__':
    app.run(debug=True, port=1111)