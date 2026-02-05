# app.py - Backend API với Python Flask + Selenium
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
import time
import re
import os

app = Flask(__name__, static_folder='static')
CORS(app)


def setup_driver():
    """Cấu hình Chrome driver"""
    chrome_options = Options()
    chrome_options.add_argument('--headless')
    chrome_options.add_argument('--no-sandbox')
    chrome_options.add_argument('--disable-dev-shm-usage')
    chrome_options.add_argument('--disable-blink-features=AutomationControlled')
    chrome_options.add_argument(
        'user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')

    driver = webdriver.Chrome(options=chrome_options)
    driver.set_page_load_timeout(60)
    return driver


def scroll_results(driver):
    """Scroll để load thêm kết quả"""
    try:
        scrollable_div = driver.find_element(By.CSS_SELECTOR, '[role="feed"]')
        print("Found scrollable feed")

        last_height = driver.execute_script("return arguments[0].scrollHeight", scrollable_div)
        scroll_attempts = 0
        max_scrolls = 15

        while scroll_attempts < max_scrolls:
            driver.execute_script("arguments[0].scrollBy(0, 1000)", scrollable_div)
            time.sleep(1.5)

            new_height = driver.execute_script("return arguments[0].scrollHeight", scrollable_div)

            if new_height == last_height:
                print(f"Reached end after {scroll_attempts} scrolls")
                break

            last_height = new_height
            scroll_attempts += 1

        print(f"Total scrolls: {scroll_attempts}")
    except Exception as e:
        print(f"Scroll error: {e}")


def extract_data(driver):
    """Trích xuất dữ liệu từ trang"""
    results = []

    try:
        print("Waiting for results to load...")
        WebDriverWait(driver, 30).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, '[role="article"]'))
        )

        scroll_results(driver)
        time.sleep(2)

        places = driver.find_elements(By.CSS_SELECTOR, '[role="article"]')
        print(f"Found {len(places)} places")

        for idx, place in enumerate(places):
            try:
                # Tên công ty
                try:
                    name = place.find_element(By.CSS_SELECTOR, '.qBF1Pd').text.strip()
                except:
                    try:
                        name = place.find_element(By.CSS_SELECTOR, '.fontHeadlineSmall').text.strip()
                    except:
                        name = 'N/A'

                if name == 'N/A' or len(name) < 2:
                    continue

                # Địa chỉ
                address = 'N/A'
                try:
                    address_elements = place.find_elements(By.CSS_SELECTOR, '.W4Efsd')
                    if len(address_elements) >= 2:
                        address = address_elements[1].text.strip()
                    elif len(address_elements) == 1:
                        address = address_elements[0].text.strip()
                except:
                    pass

                # Số điện thoại
                phone = 'N/A'
                try:
                    place_text = place.text
                    phone_patterns = [
                        r'(\+84|84|0)\s*[1-9]\d{1,2}\s*\d{3}\s*\d{4}',
                        r'(\+84|0)[0-9\s\-\.]{9,12}'
                    ]
                    for pattern in phone_patterns:
                        phone_match = re.search(pattern, place_text)
                        if phone_match:
                            phone = phone_match.group(0).strip()
                            break
                except:
                    pass

                # Rating
                rating = 'N/A'
                try:
                    rating = place.find_element(By.CSS_SELECTOR, '.MW4etd').text.strip()
                except:
                    pass

                # Reviews
                reviews = 'N/A'
                try:
                    reviews_element = place.find_element(By.CSS_SELECTOR, '[aria-label*="reviews"]')
                    reviews = reviews_element.get_attribute('aria-label')
                except:
                    try:
                        reviews_element = place.find_element(By.CSS_SELECTOR, '.UY7F9')
                        reviews = reviews_element.text.strip()
                    except:
                        pass

                # Link
                link = 'N/A'
                try:
                    link_element = place.find_element(By.CSS_SELECTOR, 'a[href*="maps/place"]')
                    link = link_element.get_attribute('href')
                except:
                    pass

                result = {
                    'stt': len(results) + 1,
                    'name': name,
                    'address': address,
                    'phone': phone,
                    'rating': rating,
                    'reviews': reviews,
                    'link': link
                }

                results.append(result)
                print(f"Extracted {idx + 1}: {name}")

            except Exception as e:
                print(f"Error parsing place {idx}: {e}")
                continue

    except Exception as e:
        print(f"Extraction error: {e}")

    return results


@app.route('/')
def index():
    """Serve trang HTML chính"""
    return send_from_directory('static', 'index.html')


@app.route('/api/health', methods=['GET'])
def health_check():
    """Kiểm tra server"""
    return jsonify({
        'status': 'OK',
        'message': 'Python Flask Backend is running',
        'version': '1.0.0'
    })


@app.route('/api/scrape-maps', methods=['POST'])
def scrape_maps():
    """API endpoint scrape Google Maps"""
    data = request.get_json()
    url = data.get('url', '').strip()

    if not url:
        return jsonify({
            'success': False,
            'error': 'URL là bắt buộc'
        }), 400

    if 'google.com/maps' not in url:
        return jsonify({
            'success': False,
            'error': 'URL không hợp lệ. Vui lòng nhập link Google Maps'
        }), 400

    driver = None
    try:
        print(f"\n{'=' * 60}")
        print(f"Starting scrape for: {url}")
        print(f"{'=' * 60}\n")

        driver = setup_driver()

        print("Loading Google Maps page...")
        driver.get(url)

        print("Extracting data...")
        results = extract_data(driver)

        print(f"\n{'=' * 60}")
        print(f"✅ Successfully scraped {len(results)} places")
        print(f"{'=' * 60}\n")

        return jsonify({
            'success': True,
            'count': len(results),
            'data': results,
            'message': f'Đã tìm thấy {len(results)} công ty'
        })

    except Exception as e:
        error_msg = str(e)
        print(f"\n❌ Error: {error_msg}\n")
        return jsonify({
            'success': False,
            'error': error_msg
        }), 500

    finally:
        if driver:
            try:
                driver.quit()
                print("Browser closed")
            except:
                pass


if __name__ == '__main__':
    # Tạo thư mục static nếu chưa có
    if not os.path.exists('static'):
        os.makedirs('static')
        print("Created 'static' folder")

    print("\n" + "=" * 60)
    print("🚀 Google Maps Scraper Backend")
    print("=" * 60)
    print(f"📍 Server: http://localhost:4000")
    print(f"📍 API Health: http://localhost:4000/api/health")
    print(f"📍 Frontend: http://localhost:4000")
    print(f"📍 API Endpoint: http://localhost:4000/api/scrape-maps")
    print("=" * 60 + "\n")

    app.run(debug=True, host='0.0.0.0', port=4000)