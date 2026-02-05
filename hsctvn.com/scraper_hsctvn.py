import requests
from bs4 import BeautifulSoup
import urllib.parse
import re
import time

BASE_URL = "https://hsctvn.com"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "vi-VN,vi;q=0.9,en-US;q=0.8,en;q=0.7",
}


def is_valid_company_info(detail):
    """Kiểm tra thông tin công ty có hợp lệ không"""
    name = detail.get("name", "")
    tax_code = detail.get("tax_code", "")

    if tax_code == "Khong co" or tax_code == "Không có" or not tax_code:
        return False

    if name == "Khong co" or name == "Không có" or len(name) < 5:
        return False

    return True


def extract_phone(text):
    """Trích xuất số điện thoại từ text"""
    if not text:
        return None

    text = re.sub(r'\s+', ' ', text)

    patterns = [
        r'0\d{9,10}',
        r'0\d[\s\-.]\d{3,4}[\s\-.]\d{3,4}',
        r'\+84\d{9,10}',
    ]

    for pattern in patterns:
        matches = re.findall(pattern, text)
        if matches:
            for match in matches:
                clean = match.replace(' ', '').replace('-', '').replace('.', '')
                if 10 <= len(clean) <= 13:
                    return match.strip()
    return None


def search_by_tax_code(tax_code):
    """
    Tìm kiếm công ty theo mã số thuế trên hsctvn.com
    URL: https://hsctvn.com/search?key=MST&opt=0&p=0&d=0
    """
    # Làm sạch mã số thuế
    tax_code = tax_code.strip()

    url = f"{BASE_URL}/search?key={urllib.parse.quote(tax_code)}&opt=0&p=0&d=0"

    print(f"\n[SEARCH] Tim kiem MST: {tax_code}")
    print(f"[SEARCH] URL: {url}")

    try:
        res = requests.get(url, headers=HEADERS, timeout=10)
        res.raise_for_status()
        soup = BeautifulSoup(res.text, "html.parser")

        # XPath: /html/body/div/div[1]/div[2]/div/div[2]/div/ul/li[1]/h3/a
        # CSS: body > div > div:nth-child(1) > div:nth-child(2) > div > div:nth-child(2) > div > ul > li:first-child h3 a

        # Cách 1: Tìm ul > li đầu tiên > h3 > a
        first_result = soup.select_one("ul li:first-child h3 a")

        # Cách 2: Fallback - tìm li đầu tiên có h3 a
        if not first_result:
            print("[SEARCH] Cach 1 that bai, thu cach 2...")
            first_result = soup.select_one("li h3 a")

        # Cách 3: Tìm bất kỳ h3 a nào
        if not first_result:
            print("[SEARCH] Cach 2 that bai, thu cach 3...")
            first_result = soup.select_one("h3 a")

        if first_result:
            href = first_result.get('href', '')
            company_name = first_result.get_text(strip=True)

            # Tạo full URL
            if href.startswith('http'):
                detail_url = href
            elif href.startswith('/'):
                detail_url = BASE_URL + href
            else:
                detail_url = BASE_URL + '/' + href

            print(f"[SEARCH] Tim thay: {company_name}")
            print(f"[SEARCH] Link: {detail_url}")

            # Lấy thông tin chi tiết
            detail = get_company_detail(detail_url, tax_code)

            if is_valid_company_info(detail):
                return {"detail": detail}
            else:
                print(f"[SEARCH] Thong tin khong hop le")
                return {"error": "Thong tin khong hop le"}
        else:
            print(f"[SEARCH] Khong tim thay ket qua nao")
            return {"error": "Khong tim thay ket qua"}

    except Exception as e:
        print(f"[ERROR] {str(e)}")
        return {"error": str(e)}


def get_company_detail(url, tax_code):
    """Lấy thông tin chi tiết công ty từ trang chi tiết"""
    print(f"[DETAIL] Truy cap trang chi tiet: {url}")

    try:
        res = requests.get(url, headers=HEADERS, timeout=10)
        res.raise_for_status()
        soup = BeautifulSoup(res.text, "html.parser")

        info = {
            "url": url,
            "tax_code": tax_code,
            "name": "Không có",
            "address": "Không có",
            "phone": "Không có",
            "representative": "Không có",
            "status": "Không có"
        }

        # Ưu tiên: parse theo cấu trúc thực tế của hsctvn (ul.hsct ...)
        try:
            container = soup.select_one('.module_data.detail .box_content') or soup
            # Tên công ty: ul.hsct li h1
            h1_in_ul = container.select_one('ul.hsct li h1')
            if h1_in_ul:
                name = h1_in_ul.get_text(strip=True)
                if name and len(name) > 5:
                    info["name"] = name
                    print(f"[DETAIL] Ten: {name}")

            # Quét tất cả các li để tìm địa chỉ, điện thoại, đại diện, trạng thái
            for li in container.select('ul.hsct li'):
                text = li.get_text(separator=' ', strip=True)
                if not text:
                    continue

                # Địa chỉ
                if ('Địa chỉ' in text or 'Địa chỉ thuế' in text or 'Trụ sở' in text) and info["address"] == "Không có":
                    m = re.search(r'(Địa chỉ(?: thuế)?|Trụ sở)\s*:\s*(.+)', text, flags=re.I)
                    if m:
                        address = m.group(2).strip()
                        # Cắt tại các nhãn tiếp theo nếu có
                        stop_tokens = ['Đại diện', 'Điện thoại', 'Email', 'Ngành nghề', 'Trạng thái', 'Ngày cấp', 'Mã số thuế', 'Mọi thắc mắc', 'Report', 'Cập nhật']
                        cut = len(address)
                        for tok in stop_tokens:
                            idx = address.find(tok)
                            if idx != -1:
                                cut = min(cut, idx)
                        address = address[:cut].strip(' -;,.')
                        if len(address) > 5:
                            info["address"] = address
                            print(f"[DETAIL] Dia chi: {address[:60]}...")

                # Điện thoại (chỉ lấy phần sau nhãn để tránh nhầm MST)
                if ('Điện thoại' in text or 'Phone' in text or 'Tel' in text) and info["phone"] == "Không có":
                    m = re.search(r'(Điện thoại|Phone|Tel)\s*:\s*(.+)', text, flags=re.I)
                    if m:
                        after_label = m.group(2).strip()
                        # Cắt tại các nhãn khác nếu có
                        stop_tokens = ['Đại diện', 'Email', 'Ngành nghề', 'Trạng thái', 'Ngày cấp', 'Mã số thuế', 'Mọi thắc mắc', 'Report', 'Cập nhật', 'Địa chỉ']
                        cut = len(after_label)
                        for tok in stop_tokens:
                            idx = after_label.find(tok)
                            if idx != -1:
                                cut = min(cut, idx)
                        candidate = after_label[:cut]
                        phone = extract_phone(candidate)
                        if phone:
                            info["phone"] = phone
                            print(f"[DETAIL] SDT: {phone}")

                # Người đại diện
                if ('Đại diện pháp luật' in text or 'Người đại diện' in text or 'Giám đốc' in text) and info["representative"] == "Không có":
                    parts = text.split(':', 1)
                    if len(parts) > 1:
                        rep = parts[1].strip()
                        if 3 < len(rep) < 100:
                            info["representative"] = rep
                            print(f"[DETAIL] Nguoi dai dien: {rep}")

                # Trạng thái
                if ('Trạng thái' in text or 'Tình trạng' in text) and info["status"] == "Không có":
                    parts = text.split(':', 1)
                    if len(parts) > 1:
                        status = parts[1].strip()
                        if status:
                            info["status"] = status
                            print(f"[DETAIL] Trang thai: {status}")
        except Exception as _:
            pass

        # Lấy tên công ty từ h1 hoặc title (fallback)
        h1 = soup.find('h1')
        if h1:
            name = h1.get_text(strip=True)
            if name and len(name) > 5:
                info["name"] = name
                print(f"[DETAIL] Ten: {name}")

        # Tìm thông tin trong các table hoặc div
        # Thử tìm theo class hoặc structure phổ biến

        # Tìm tất cả các row có label và value
        rows = soup.find_all(['tr', 'div'], class_=re.compile(r'(row|info|detail)', re.I))

        for row in rows:
            text = row.get_text(strip=True)

            # Địa chỉ
            if (('Địa chỉ' in text or 'Trụ sở' in text) and info["address"] == "Không có"):
                m = re.search(r'(Địa chỉ(?: thuế)?|Trụ sở)\s*:\s*(.+)', text, flags=re.I)
                if m:
                    address = m.group(2).strip()
                    stop_tokens = ['Đại diện', 'Điện thoại', 'Email', 'Ngành nghề', 'Trạng thái', 'Ngày cấp', 'Mã số thuế', 'Mọi thắc mắc', 'Report', 'Cập nhật']
                    cut = len(address)
                    for tok in stop_tokens:
                        idx = address.find(tok)
                        if idx != -1:
                            cut = min(cut, idx)
                    address = address[:cut].strip(' -;,.')
                    if len(address) > 5:
                        info["address"] = address
                        print(f"[DETAIL] Dia chi: {address[:60]}...")

            # Điện thoại (chỉ lấy phần sau nhãn)
            if ('Điện thoại' in text or 'Phone' in text or 'Tel' in text) and info["phone"] == "Không có":
                m = re.search(r'(Điện thoại|Phone|Tel)\s*:\s*(.+)', text, flags=re.I)
                if m:
                    after_label = m.group(2).strip()
                    stop_tokens = ['Đại diện', 'Email', 'Ngành nghề', 'Trạng thái', 'Ngày cấp', 'Mã số thuế', 'Mọi thắc mắc', 'Report', 'Cập nhật', 'Địa chỉ']
                    cut = len(after_label)
                    for tok in stop_tokens:
                        idx = after_label.find(tok)
                        if idx != -1:
                            cut = min(cut, idx)
                    candidate = after_label[:cut]
                    phone = extract_phone(candidate)
                    if phone:
                        info["phone"] = phone
                        print(f"[DETAIL] SDT: {phone}")

            # Người đại diện
            if 'Người đại diện' in text or 'Giám đốc' in text or 'Đại diện' in text:
                parts = text.split(':', 1)
                if len(parts) > 1:
                    rep = parts[1].strip()
                    if len(rep) > 3 and len(rep) < 100:
                        info["representative"] = rep
                        print(f"[DETAIL] Nguoi dai dien: {rep}")

            # Trạng thái
            if 'Trạng thái' in text or 'Tình trạng' in text:
                parts = text.split(':', 1)
                if len(parts) > 1:
                    status = parts[1].strip()
                    if status:
                        info["status"] = status
                        print(f"[DETAIL] Trang thai: {status}")

        # Fallback: tìm trong table
        table = soup.find('table')
        if table:
            for row in table.find_all('tr'):
                cells = row.find_all(['td', 'th'])
                if len(cells) >= 2:
                    label = cells[0].get_text(strip=True)
                    value = cells[1].get_text(strip=True)

                    if 'Tên' in label and info["name"] == "Không có":
                        if value and len(value) > 5:
                            info["name"] = value

                    elif 'Địa chỉ' in label and info["address"] == "Không có":
                        if value and len(value) > 10:
                            info["address"] = value

                    elif 'Điện thoại' in label and info["phone"] == "Không có":
                        phone = extract_phone(value)
                        if phone:
                            info["phone"] = phone

                    elif 'Người đại diện' in label and info["representative"] == "Không có":
                        if value and 3 < len(value) < 100:
                            info["representative"] = value

                    elif 'Trạng thái' in label and info["status"] == "Không có":
                        if value:
                            info["status"] = value

        # Làm sạch dữ liệu
        for key in info:
            if isinstance(info[key], str):
                info[key] = re.sub(r'\s+', ' ', info[key]).strip()
                if not info[key] or info[key] == '-':
                    info[key] = "Khong co"

        return info

    except Exception as e:
        print(f"[ERROR] Loi khi lay chi tiet: {str(e)}")
        return {
            "url": url,
            "tax_code": tax_code,
            "error": str(e),
            "name": "Khong co",
            "address": "Khong co",
            "phone": "Khong co",
            "representative": "Khong co",
            "status": "Khong co"
        }


def search_companies_batch(tax_codes):
    """Tìm kiếm hàng loạt theo mã số thuế"""
    results = []
    total = len(tax_codes)

    print("\n" + "=" * 60)
    print(f"BAT DAU TIM KIEM {total} MA SO THUE")
    print("=" * 60)

    for idx, tax_code in enumerate(tax_codes, 1):
        try:
            tax_code = str(tax_code).strip()
            if not tax_code or tax_code == 'nan':
                continue

            print(f"\n[{idx}/{total}] MST: {tax_code}")

            data = search_by_tax_code(tax_code)

            if "detail" in data:
                detail = data["detail"]
                results.append({
                    "tax_code_search": tax_code,
                    "name": detail.get("name", "Khong co"),
                    "tax_code": detail.get("tax_code", "Khong co"),
                    "address": detail.get("address", "Khong co"),
                    "phone": detail.get("phone", "Khong co"),
                    "representative": detail.get("representative", "Khong co"),
                    "status": detail.get("status", "Khong co"),
                    "url": detail.get("url", ""),
                    "result_status": "found"
                })
                print(f"   ✓ Thanh cong")
            else:
                results.append({
                    "tax_code_search": tax_code,
                    "name": "Khong co",
                    "tax_code": tax_code,
                    "address": "Khong co",
                    "phone": "Khong co",
                    "representative": "Khong co",
                    "status": "Khong co",
                    "url": "",
                    "result_status": "not_found",
                    "error": data.get("error", "Khong tim thay")
                })
                print(f"   ✗ Khong tim thay")

            # Delay để tránh bị block
            time.sleep(2)

        except Exception as e:
            print(f"   ✗ Loi: {str(e)}")
            results.append({
                "tax_code_search": tax_code,
                "name": "Khong co",
                "tax_code": tax_code,
                "address": "Khong co",
                "phone": "Khong co",
                "representative": "Khong co",
                "status": "Khong co",
                "url": "",
                "result_status": "error",
                "error": str(e)
            })

    print("\n" + "=" * 60)
    print("HOAN THANH TIM KIEM")
    print("=" * 60)

    return results