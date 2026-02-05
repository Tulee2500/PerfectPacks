from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import pandas as pd
import time
import os

options = Options()
# options.add_argument("--headless")
options.add_argument("--disable-gpu")
options.add_argument("--no-sandbox")
options.add_argument("--start-maximized")

driver = webdriver.Chrome(options=options)
url = "https://www.gs1.org/services/verified-by-gs1/results?company_name=My+Pham&country=VN"
driver.get(url)

all_data = []

try:
    print("⏳ Đang tải trang GS1...")

    # 🧩 Chấp nhận cookie
    try:
        cookie_accept = WebDriverWait(driver, 15).until(
            EC.element_to_be_clickable((By.XPATH, '//*[@id="onetrust-accept-btn-handler"]'))
        )
        cookie_accept.click()
        print("🍪 Đã chấp nhận cookie")
        time.sleep(2)
    except:
        print("⚠️ Không thấy popup cookie, bỏ qua...")

    # 🧩 Chấp nhận điều khoản
    try:
        terms_accept = WebDriverWait(driver, 15).until(
            EC.element_to_be_clickable((By.XPATH, '/html/body/div[6]/div[3]/div/button[1]'))
        )
        terms_accept.click()
        print("📜 Đã chấp nhận điều khoản sử dụng")
        time.sleep(2)
    except:
        print("⚠️ Không thấy popup điều khoản, bỏ qua...")

    # 🧩 Lặp qua 5 trang
    page = 1
    max_pages = 5
    while page <= max_pages:
        WebDriverWait(driver, 30).until(
            EC.presence_of_all_elements_located((By.CSS_SELECTOR, "table tbody tr"))
        )
        time.sleep(1.5)

        rows = driver.find_elements(By.CSS_SELECTOR, "table tbody tr")
        print(f"📄 Trang {page}: {len(rows)} dòng")

        page_data = []
        for row in rows:
            try:
                cols = row.find_elements(By.TAG_NAME, "td")
                if len(cols) >= 4:
                    page_data.append({
                        "License Key": cols[0].text.strip(),
                        "Company Name": cols[1].text.strip(),
                        "City": cols[2].text.strip(),
                        "Country": cols[3].text.strip()
                    })
            except:
                continue

        all_data.extend(page_data)
        print(f"➕ Thêm {len(page_data)} dòng (Tổng: {len(all_data)})")

        if page >= max_pages:
            print("✅ Đã lấy đủ 5 trang, dừng lại.")
            break

        try:
            next_btn = WebDriverWait(driver, 10).until(
                EC.element_to_be_clickable((By.XPATH, "//a[contains(text(), '›')]"))
            )
            driver.execute_script("arguments[0].scrollIntoView(true);", next_btn)
            driver.execute_script("arguments[0].click();", next_btn)
            page += 1
            print("➡️ Chuyển sang trang tiếp theo...")
            time.sleep(4)
        except:
            print("✅ Hết trang, dừng thu thập dữ liệu.")
            break

    # --- Xuất file (thêm dữ liệu mới xuống dưới) ---
    df = pd.DataFrame(all_data)
    df = df.drop_duplicates()

    file_path = "gs1_vietnam_mypham.csv"
    file_exists = os.path.isfile(file_path)

    df.to_csv(file_path, index=False, encoding="utf-8-sig", mode="a", header=not file_exists)
    print(f"💾 Đã ghi {len(df)} dòng mới vào cuối file gs1_vietnam_mypham.csv")

except Exception as e:
    print("❌ Lỗi:", e)

finally:
    driver.quit()
