import requests
from bs4 import BeautifulSoup
import urllib.parse
import re
import time

BASE_URL = "https://masothue.com"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
}


def extract_phone(text):
    """Trích xuất số điện thoại"""
    if not text:
        return None

    text = re.sub(r'\s+', ' ', text)
    patterns = [
        r'0\d{9,10}',
        r'0\d[\s\-]\d{3,4}[\s\-]\d{3,4}',
        r'\+84\d{9,10}',
    ]

    for pattern in patterns:
        matches = re.findall(pattern, text)
        if matches:
            for match in matches:
                clean = match.replace(' ', '').replace('-', '')
                if 10 <= len(clean) <= 13:
                    return match.strip()
    return None


def get_company_detail(url):
    """Lấy thông tin chi tiết công ty"""
    try:
        res = requests.get(url, headers=HEADERS, timeout=10)
        res.raise_for_status()
        soup = BeautifulSoup(res.text, "html.parser")

        info = {
            "url": url,
            "name": None,
            "tax_code": None,
            "address": None,
            "phone": None,
            "representative": None
        }

        # 1. Tên công ty từ h1
        title = soup.select_one("h1")
        if title:
            name_text = title.get_text(strip=True)
            name_text = re.sub(r'\s*-\s*Mã số thuế.*$', '', name_text, flags=re.IGNORECASE)
            if name_text and len(name_text) > 3:
                info["name"] = name_text

        # 2. Từ bảng table
        table = soup.find('table', class_='table')
        if table:
            for row in table.find_all('tr'):
                cells = row.find_all(['td', 'th'])
                if len(cells) >= 2:
                    label = cells[0].get_text(strip=True).lower()
                    value = cells[1].get_text(strip=True)

                    if 'tên công ty' in label or 'tên doanh nghiệp' in label:
                        if value and len(value) > 5:
                            info["name"] = value
                    elif 'mã số thuế' in label:
                        mst_match = re.search(r'(\d{10,13}(?:\-\d{3})?)', value)
                        if mst_match:
                            info["tax_code"] = mst_match.group(1)
                    elif 'địa chỉ' in label:
                        if value and len(value) > 5:
                            info["address"] = value
                    elif 'điện thoại' in label:
                        phone = extract_phone(value)
                        if phone:
                            info["phone"] = phone

        # 3. Mã số thuế từ itemprop
        if not info["tax_code"]:
            tax_td = soup.find('td', {'itemprop': 'taxID'})
            if tax_td:
                tax_span = tax_td.find('span', class_='copy')
                if tax_span:
                    tax_code = tax_span.get_text(strip=True)
                    if re.match(r'\d{10,13}(?:\-\d{3})?', tax_code):
                        info["tax_code"] = tax_code

        # 4. Địa chỉ từ itemprop
        if not info["address"]:
            addr_td = soup.find('td', {'itemprop': 'address'})
            if addr_td:
                addr_span = addr_td.find('span', class_='copy')
                if addr_span:
                    address = addr_span.get_text(strip=True)
                    if len(address) > 5:
                        info["address"] = address

        # 5. Điện thoại từ itemprop
        if not info["phone"]:
            phone_td = soup.find('td', {'itemprop': 'telephone'})
            if phone_td:
                phone_span = phone_td.find('span', class_='copy')
                if phone_span:
                    phone = extract_phone(phone_span.get_text(strip=True))
                    if phone:
                        info["phone"] = phone

        # 6. Người đại diện
        for td in soup.find_all('td'):
            span_name = td.find('span', {'itemprop': 'name'})
            if span_name:
                link = span_name.find('a')
                rep_name = link.get_text(strip=True) if link else span_name.get_text(strip=True)

                if rep_name and 3 < len(rep_name) < 100:
                    if not any(kw in rep_name.lower() for kw in ['luật pháp', 'phân tích', 'chi tiết']):
                        info["representative"] = rep_name
                        break

        # Làm sạch
        for key in info:
            if isinstance(info[key], str):
                info[key] = re.sub(r'\s+', ' ', info[key]).strip()

        return info

    except Exception as e:
        print(f"❌ Lỗi scrape {url}: {str(e)}")
        return {
            "url": url,
            "name": None,
            "tax_code": None,
            "address": None,
            "phone": None,
            "representative": None,
            "error": str(e)
        }


def search_company(name):
    """Tìm kiếm công ty - luôn lấy kết quả đầu tiên"""
    url = f"{BASE_URL}/Search/?q={urllib.parse.quote(name)}&type=auto&force-search=1"

    try:
        res = requests.get(url, headers=HEADERS, timeout=10)
        res.raise_for_status()
        soup = BeautifulSoup(res.text, "html.parser")

        # Kiểm tra redirect
        if '/Search/' not in res.url:
            detail = get_company_detail(res.url)
            if detail.get('name') and detail.get('tax_code'):
                return {"detail": detail}

        # Tìm trong tax-listing
        tax_listing = soup.find('div', class_='tax-listing')
        if tax_listing:
            first_h3 = tax_listing.find('h3')
            if first_h3:
                first_link = first_h3.find('a')
                if first_link:
                    href = first_link.get('href', '')
                    if href:
                        link = BASE_URL + href if not href.startswith('http') else href
                        detail = get_company_detail(link)

                        if detail.get('name') and detail.get('tax_code'):
                            return {"detail": detail}

        return {"error": "Không tìm thấy"}

    except Exception as e:
        return {"error": str(e)}


def search_companies_batch(company_names):
    """Tìm kiếm hàng loạt công ty"""
    results = []
    total = len(company_names)

    print("\n" + "=" * 60)
    print(f"🔍 BẮT ĐẦU TÌM KIẾM {total} CÔNG TY")
    print("=" * 60)

    for idx, name in enumerate(company_names, 1):
        try:
            name = name.strip()
            if not name:
                continue

            print(f"\n[{idx}/{total}] Tìm: {name}")
            data = search_company(name)

            if "detail" in data:
                detail = data["detail"]

                # Kiểm tra có dữ liệu hợp lệ không
                has_valid_data = (
                        detail.get("name") and
                        detail.get("tax_code") and
                        len(str(detail.get("name", ""))) > 3 and
                        re.match(r'\d{10,13}', str(detail.get("tax_code", "")))
                )

                if has_valid_data:
                    results.append({
                        "company_name": name,
                        "name": detail.get("name"),
                        "tax_code": detail.get("tax_code"),
                        "address": detail.get("address") or "Không có",
                        "phone": detail.get("phone") or "Không có",
                        "representative": detail.get("representative") or "Không có",
                        "url": detail.get("url", ""),
                        "status": "found"
                    })
                    print(f"   ✅ Tìm thấy: {detail.get('name')}")
                else:
                    results.append({
                        "company_name": name,
                        "name": "Không có",
                        "tax_code": "Không có",
                        "address": "Không có",
                        "phone": "Không có",
                        "representative": "Không có",
                        "url": "",
                        "status": "not_found"
                    })
                    print(f"   ❌ Dữ liệu không hợp lệ")
            else:
                results.append({
                    "company_name": name,
                    "name": "Không có",
                    "tax_code": "Không có",
                    "address": "Không có",
                    "phone": "Không có",
                    "representative": "Không có",
                    "url": "",
                    "status": "not_found",
                    "error": data.get("error", "Không tìm thấy")
                })
                print(f"   ❌ Không tìm thấy: {data.get('error', 'N/A')}")

            # Delay để tránh bị block
            time.sleep(1.5)

        except Exception as e:
            print(f"   ⚠️ Lỗi: {str(e)}")
            results.append({
                "company_name": name,
                "name": "Không có",
                "tax_code": "Không có",
                "address": "Không có",
                "phone": "Không có",
                "representative": "Không có",
                "url": "",
                "status": "error",
                "error": str(e)
            })

    print("\n" + "=" * 60)
    print("✅ HOÀN THÀNH TÌM KIẾM")
    print("=" * 60)

    # Thống kê
    found = sum(1 for r in results if r['status'] == 'found')
    not_found = sum(1 for r in results if r['status'] == 'not_found')
    error = sum(1 for r in results if r['status'] == 'error')

    print(f"📊 Tìm thấy: {found} | Không tìm thấy: {not_found} | Lỗi: {error}")
    print("=" * 60 + "\n")

    return results