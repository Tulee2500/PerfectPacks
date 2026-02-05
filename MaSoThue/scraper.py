# ==================== FILE: scraper.py ====================
import requests
from bs4 import BeautifulSoup
import pandas as pd
import time
import re
from urllib.parse import urljoin
import os


class MaSoThueScraper:
    def __init__(self):
        self.base_url = "https://masothue.com"
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        self.results = []
        self.progress = {
            'current_page': 0,
            'total_pages': 0,
            'current_company': 0,
            'total_companies': 0,
            'status': 'idle',
            'message': ''
        }

    def get_page_content(self, url):
        """Lấy nội dung trang web"""
        try:
            response = requests.get(url, headers=self.headers, timeout=10)
            response.raise_for_status()
            return BeautifulSoup(response.content, 'html.parser')
        except Exception as e:
            print(f"❌ Lỗi khi truy cập {url}: {str(e)}")
            return None

    def extract_company_list(self, soup):
        """Trích xuất danh sách công ty từ trang danh sách"""
        companies = []

        # Tìm tất cả các block công ty (mỗi block bắt đầu bằng h3)
        company_blocks = soup.find_all('h3')

        for h3 in company_blocks:
            try:
                # Lấy link và tên công ty từ h3 > a
                link_tag = h3.find('a')
                if not link_tag:
                    continue

                detail_url = urljoin(self.base_url, link_tag['href'])
                company_name = link_tag.get_text(strip=True)

                # Tìm parent container chứa thông tin chi tiết
                parent = h3.parent

                # Lấy mã số thuế
                mst = "N/A"
                mst_text = parent.get_text()
                mst_match = re.search(r'Mã số thuế:\s*([0-9\-]+)', mst_text)
                if mst_match:
                    mst = mst_match.group(1).strip()

                # Lấy người đại diện
                representative = "N/A"
                rep_tag = parent.find('em')
                if rep_tag:
                    representative = rep_tag.get_text(strip=True)

                # Lấy địa chỉ (thường ở cuối block, không có tag đặc biệt)
                address = "N/A"
                # Tìm text sau "Người đại diện:"
                all_text = parent.get_text()
                # Loại bỏ các phần đã biết để lấy địa chỉ
                lines = [line.strip() for line in all_text.split('\n') if line.strip()]
                for i, line in enumerate(lines):
                    if not any(x in line for x in ['Mã số thuế:', 'Người đại diện:', company_name]):
                        # Đây có thể là địa chỉ
                        if len(line) > 20:  # Địa chỉ thường dài
                            address = line
                            break

                companies.append({
                    'mst': mst,
                    'ten_cong_ty': company_name,
                    'nguoi_dai_dien': representative,
                    'dia_chi': address,
                    'detail_url': detail_url
                })

            except Exception as e:
                print(f"⚠️ Lỗi khi xử lý một công ty: {str(e)}")
                continue

        return companies

    def get_company_details(self, url):
        """Lấy thông tin chi tiết từ trang công ty"""
        soup = self.get_page_content(url)
        if not soup:
            return "N/A", "N/A", "N/A"

        details = {
            'phone': "N/A",
            'year': "N/A",
            'industry_detail': "N/A"
        }

        try:
            # Tìm table chứa thông tin thuế
            table = soup.find('table', class_='table-taxinfo')
            if not table:
                return details['phone'], details['year'], details['industry_detail']

            rows = table.find_all('tr')

            for row in rows:
                cells = row.find_all('td')
                if len(cells) < 2:
                    continue

                header = cells[0].get_text(strip=True)
                value_cell = cells[1]

                # Lấy số điện thoại
                if 'Điện thoại' in header:
                    phone_tag = value_cell.find('span', class_='copy')
                    if phone_tag:
                        details['phone'] = phone_tag.get_text(strip=True)

                # Lấy năm thành lập
                elif 'Ngày hoạt động' in header or 'Ngày cấp' in header:
                    date_tag = value_cell.find('span', class_='copy')
                    if date_tag:
                        date_text = date_tag.get_text(strip=True)
                        # Trích xuất năm (4 số đầu tiên)
                        year_match = re.match(r'(\d{4})', date_text)
                        if year_match:
                            details['year'] = year_match.group(1)

                # Lấy ngành nghề chi tiết
                elif 'Ngành nghề chính' in header:
                    full_text = value_cell.get_text(strip=True)
                    # Tìm phần trong ngoặc (Chi tiết: ...)
                    detail_match = re.search(r'\(Chi tiết:\s*(.+?)\)', full_text)
                    if detail_match:
                        details['industry_detail'] = detail_match.group(1).strip()
                    else:
                        # Nếu không có trong ngoặc, lấy text từ link
                        industry_link = value_cell.find('a')
                        if industry_link:
                            details['industry_detail'] = industry_link.get_text(strip=True)

        except Exception as e:
            print(f"⚠️ Lỗi khi lấy chi tiết: {str(e)}")

        return details['phone'], details['year'], details['industry_detail']

    def scrape(self, start_url, from_page, to_page, filter_year=None, filter_industry=None):
        """Scrape dữ liệu từ nhiều trang"""
        self.results = []
        self.progress['status'] = 'running'
        self.progress['total_pages'] = to_page - from_page + 1

        for page in range(from_page, to_page + 1):
            self.progress['current_page'] = page - from_page + 1
            self.progress['message'] = f'Đang xử lý trang {page}...'

            # Xây dựng URL cho mỗi trang
            if '?' in start_url:
                page_url = re.sub(r'page=\d+', f'page={page}', start_url)
                if f'page={page}' not in page_url:
                    page_url += f'&page={page}'
            else:
                page_url = f"{start_url}?page={page}"

            print(f"📄 Đang scrape: {page_url}")

            soup = self.get_page_content(page_url)
            if not soup:
                continue

            companies = self.extract_company_list(soup)
            self.progress['total_companies'] = len(companies)

            print(f"✅ Tìm thấy {len(companies)} công ty ở trang {page}")

            for idx, company in enumerate(companies, 1):
                self.progress['current_company'] = idx
                self.progress['message'] = f'Trang {page}: Đang xử lý công ty {idx}/{len(companies)}'

                if company['detail_url']:
                    phone, year, industry = self.get_company_details(company['detail_url'])
                    company['sdt'] = phone
                    company['nam_thanh_lap'] = year
                    company['nganh_nghe_chi_tiet'] = industry

                    # Áp dụng bộ lọc
                    should_add = True

                    if filter_year and year != filter_year:
                        should_add = False

                    if filter_industry and should_add:
                        keywords = [k.strip().lower() for k in re.split(r',|và|\|', filter_industry)]
                        industry_lower = industry.lower()
                        has_match = any(keyword in industry_lower for keyword in keywords if keyword)

                        if not has_match:
                            should_add = False

                    if should_add:
                        self.results.append(company)
                        print(f"  ✓ Thêm: {company['ten_cong_ty']} - {company['mst']}")

                    time.sleep(1)  # Delay giữa các request
                else:
                    company['sdt'] = "N/A"
                    company['nam_thanh_lap'] = "N/A"
                    company['nganh_nghe_chi_tiet'] = "N/A"

            time.sleep(2)  # Delay giữa các trang

        self.progress['status'] = 'completed'
        self.progress['message'] = f'Hoàn thành! Tìm thấy {len(self.results)} công ty phù hợp'
        print(f"\n🎉 Hoàn thành! Tổng cộng: {len(self.results)} công ty")
        return len(self.results)

    def export_to_excel(self, filename="ket_qua.xlsx"):
        """Xuất kết quả ra file Excel"""
        if not self.results:
            return None

        os.makedirs('output', exist_ok=True)
        filepath = os.path.join('output', filename)

        df = pd.DataFrame(self.results)
        df = df[['mst', 'ten_cong_ty', 'nguoi_dai_dien', 'sdt', 'dia_chi',
                 'nam_thanh_lap', 'nganh_nghe_chi_tiet']]

        df.columns = ['Mã số thuế', 'Tên công ty', 'Người đại diện', 'Số điện thoại',
                      'Địa chỉ', 'Năm thành lập', 'Ngành nghề chi tiết']

        df.to_excel(filepath, index=False, engine='openpyxl')
        print(f"💾 Đã lưu file: {filepath}")
        return filepath

    def get_progress(self):
        """Lấy tiến trình hiện tại"""
        return self.progress


# ==================== TEST SCRIPT ====================
if __name__ == "__main__":
    print("=" * 60)
    print("MASOTHUE.COM SCRAPER - PHIÊN BẢN SỬA LỖI")
    print("=" * 60)

    scraper = MaSoThueScraper()

    # URL test
    url = "https://masothue.com/tra-cuu-ma-so-thue-theo-nganh-nghe/ban-buon-do-dung-khac-cho-gia-dinh-4649"

    # Scrape từ trang 1 đến 3 (test nhỏ trước)
    print("\n🚀 Bắt đầu scraping...")
    total = scraper.scrape(url, from_page=1, to_page=3)

    # Xuất kết quả
    if total > 0:
        scraper.export_to_excel("test_ket_qua.xlsx")
    else:
        print("\n⚠️ Không tìm thấy công ty nào!")