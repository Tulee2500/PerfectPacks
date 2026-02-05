import time, requests, csv
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

def get_form_build_id():
    print("1️⃣ Đang mở trang GS1 để lấy form_build_id...")

    chrome_opts = Options()
    chrome_opts.add_argument("--headless")
    chrome_opts.add_argument("--no-sandbox")
    chrome_opts.add_argument("--disable-dev-shm-usage")
    driver = webdriver.Chrome(options=chrome_opts)

    driver.get("https://www.gs1.org/services/verified-by-gs1/search")

    try:
        # Đợi phần tử form_build_id xuất hiện
        elem = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.NAME, "form_build_id"))
        )
        form_build_id = elem.get_attribute("value")
        form_id = driver.find_element(By.NAME, "form_id").get_attribute("value")

        cookies = {c["name"]: c["value"] for c in driver.get_cookies()}
        print(f" - form_build_id: {form_build_id}")
        print(f" - form_id: {form_id}")
        return form_build_id, form_id, cookies

    except Exception as e:
        print(f"❌ Không tìm thấy form_build_id: {e}")
        driver.save_screenshot("debug_form.png")
        print("Ảnh chụp lưu tại debug_form.png để kiểm tra giao diện.")
        return None, None, None

    finally:
        driver.quit()


def fetch_gs1_ajax(form_build_id, form_id, cookies, keyword="My Pham", country="VN"):
    print("\n2️⃣ Gửi request tới API nội bộ GS1...")

    url = "https://www.gs1.org/services/verified-by-gs1/results?ajax_form=1&_wrapper_format=drupal_ajax"

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
        "X-Requested-With": "XMLHttpRequest",
        "Content-Type": "application/x-www-form-urlencoded"
    }

    data = {
        "company_name": keyword,
        "country": country,
        "form_id": form_id,
        "form_build_id": form_build_id,
        "_triggering_element_name": "licensee_submit",
        "ajax_page_state[theme]": "gs1_theme",
        "ajax_page_state[theme_token]": "",
        "ajax_page_state[libraries]": "core/html5shiv,core/jquery,core/drupal.ajax,gs1_theme/global-styling",
    }

    response = requests.post(url, headers=headers, data=data, cookies=cookies)
    print(f" - Status code: {response.status_code}")

    text = response.text
    if "<table" not in text:
        print("⚠️ Không có bảng trong HTML, có thể form_build_id hết hạn hoặc thiếu field.")
        print(text[:400])
        return []

    soup = BeautifulSoup(text, "html.parser")
    table = soup.find("table")

    if not table:
        print("❗ Không tìm thấy bảng kết quả trong HTML.")
        return []

    rows = []
    for tr in table.find_all("tr")[1:]:
        cols = [td.text.strip() for td in tr.find_all("td")]
        if cols:
            rows.append(cols)

    print(f"✅ Lấy được {len(rows)} dòng dữ liệu.")
    return rows


def save_csv(rows):
    if not rows:
        print("❗ Không có dữ liệu để lưu.")
        return
    with open("gs1_companies.csv", "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["Company", "GTIN Prefix", "Country", "GLN", "Status"])
        writer.writerows(rows)
    print("💾 Đã lưu file gs1_companies.csv")


if __name__ == "__main__":
    fb_id, fid, cookies = get_form_build_id()
    if not fb_id:
        print("❗ Không thể tiếp tục vì không lấy được form_build_id.")
    else:
        data = fetch_gs1_ajax(fb_id, fid, cookies, keyword="My Pham", country="VN")
        save_csv(data)
