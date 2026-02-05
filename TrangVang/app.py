#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Company Scraper v3.0 - Flask Backend
Tính năng:
- Scrape danh sách công ty từ Trang Vàng Việt Nam
- Check trùng thông minh với chuẩn hóa tên
- Lưu vào file Excel tổng hợp tự động
- API đầy đủ cho frontend
"""

import os
import time
import tempfile
import traceback
import re
import unicodedata
from urllib.parse import urlparse, parse_qs, urlencode, urlunparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from flask import Flask, request, jsonify, send_file, send_from_directory
from flask_cors import CORS
import requests
from bs4 import BeautifulSoup
import pandas as pd
from datetime import datetime

# ==================== CONFIG ====================
DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)
REQUEST_TIMEOUT = 20
DELAY_BETWEEN_PAGES = 1.0
DELAY_BETWEEN_DETAILS = 0.3
MAX_WORKERS = 3
MASTER_EXCEL_FILE = 'companies_master.xlsx'

# ==================== FLASK APP ====================
app = Flask(__name__, static_folder='static')
CORS(app)


# ==================== HELPER: NORMALIZE NAME ====================
def normalize_company_name(name):
    """
    Chuẩn hóa tên công ty để so sánh trùng lặp
    """
    if not name or not isinstance(name, str):
        return ""

    # Chuyển về chữ thường
    name = name.lower().strip()

    # Loại bỏ dấu tiếng Việt
    name = unicodedata.normalize('NFD', name)
    name = ''.join(char for char in name if unicodedata.category(char) != 'Mn')

    # Chuẩn hóa các từ viết tắt
    replacements = {
        'cong ty tnhh': 'tnhh',
        'cong ty co phan': 'cp',
        'cong ty': 'cty',
        'ctcp': 'cp',
        'cttnhh': 'tnhh',
        'limited': 'ltd',
        'company': 'co',
        'corporation': 'corp',
    }

    for old, new in replacements.items():
        name = name.replace(old, new)

    # Loại bỏ ký tự đặc biệt, chỉ giữ chữ và số
    name = re.sub(r'[^a-z0-9\s]', '', name)

    # Loại bỏ khoảng trắng thừa
    name = re.sub(r'\s+', ' ', name).strip()

    return name


def is_duplicate_company(company, existing_companies, similarity_threshold=0.95):
    """
    Kiểm tra xem công ty có trùng với danh sách hiện có không
    """
    if not company.get('name'):
        return False, None

    normalized_name = normalize_company_name(company['name'])

    for existing in existing_companies:
        existing_normalized = normalize_company_name(existing.get('name', ''))

        # Check exact match
        if normalized_name == existing_normalized:
            return True, existing

        # Check fuzzy match
        if normalized_name and existing_normalized:
            similarity = calculate_similarity(normalized_name, existing_normalized)
            if similarity >= similarity_threshold:
                return True, existing

    return False, None


def calculate_similarity(str1, str2):
    """
    Tính độ tương đồng giữa 2 chuỗi (Jaccard similarity)
    """
    if not str1 or not str2:
        return 0.0

    set1 = set(str1.split())
    set2 = set(str2.split())

    if not set1 or not set2:
        return 0.0

    intersection = len(set1.intersection(set2))
    union = len(set1.union(set2))

    return intersection / union if union > 0 else 0.0


# ==================== HELPER: FETCH WITH RETRY ====================
def fetch_url_with_retry(url, max_retries=3):
    """
    Fetch URL với retry và timeout tốt hơn
    """
    headers = {
        'User-Agent': DEFAULT_USER_AGENT,
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'vi-VN,vi;q=0.9,en;q=0.8',
        'Accept-Encoding': 'gzip, deflate',
        'Connection': 'keep-alive',
        'Upgrade-Insecure-Requests': '1'
    }

    for attempt in range(max_retries):
        try:
            print(f"    Thu lan {attempt + 1}/{max_retries}...")
            resp = requests.get(
                url,
                headers=headers,
                timeout=REQUEST_TIMEOUT,
                allow_redirects=True
            )
            resp.raise_for_status()

            # Kiểm tra content có hợp lệ không
            if len(resp.content) < 1000:
                print(f"    Content qua ngan ({len(resp.content)} bytes), retry...")
                if attempt < max_retries - 1:
                    time.sleep(1)
                    continue

            print(f"    Lay thanh cong ({len(resp.content)} bytes)")
            return resp

        except requests.Timeout:
            print(f"    Timeout lan {attempt + 1}")
            if attempt < max_retries - 1:
                time.sleep(1)
        except requests.RequestException as e:
            print(f"    Loi request lan {attempt + 1}: {e}")
            if attempt < max_retries - 1:
                time.sleep(1)
        except Exception as e:
            print(f"    Loi khong xac dinh: {e}")
            if attempt == max_retries - 1:
                raise e
            time.sleep(1)

    print(f"    That bai sau {max_retries} lan thu")
    return None


# ==================== HELPER: PARSE LIST PAGE ====================
def extract_companies_from_list(html_content):
    """
    Trích xuất dữ liệu từ trang danh sách công ty
    """
    soup = BeautifulSoup(html_content, 'html.parser')

    # Thử nhiều selector khác nhau
    company_blocks = []

    # Selector 1: For categories URLs (div with h-auto w-100 p-2)
    company_blocks = soup.select('div.h-auto.w-100.p-2')

    # Selector 2: For gindex URLs (div_list_cty > div with specific classes)
    if not company_blocks:
        company_blocks = soup.select('div.div_list_cty > div.bg-white.border-bottom.mt-3.p-2.pb-3.pt-3.rounded-3.w-100')

    # Selector 3: Original selector
    if not company_blocks:
        company_blocks = soup.select('.div_list_cty > .shadow.rounded-3')

    # Fallback selector 1
    if not company_blocks:
        company_blocks = soup.select('.shadow.rounded-3')

    # Fallback selector 2 - Updated to handle both formats
    if not company_blocks:
        company_blocks = soup.select('div.div_list_cty > div')
        # Filter only divs that have company links
        company_blocks = [b for b in company_blocks if b.select_one('h2 a') or b.select_one('h3 a') or b.select_one('h4 a') or
                        (b.select('a[href]') and any('trangvangvietnam.com' in a.get('href', '') for a in b.select('a[href]')))]

    # NEW: Selector for numbered format (like the one user showed)
    if not company_blocks:
        # Look for numbered companies pattern
        # This format has companies numbered like 147, 164, 165, etc.
        numbered_companies = []

        # Find all text elements that start with a number
        for element in soup.find_all(string=True):
            text = element.strip()
            if text and text[0].isdigit():
                try:
                    num = int(text.split()[0])
                    if num > 100:  # Looking for numbers like 147, 164, etc.
                        # Get the parent element
                        parent = element.parent
                        if parent:
                            # Look for company name in following text
                            next_sibling = parent.next_sibling
                            company_name = None
                            company_info = {'address': '', 'phone': '', 'email': '', 'website': ''}

                            # Try to extract company name and info
                            current = next_sibling
                            info_count = 0
                            while current and info_count < 10:
                                if hasattr(current, 'get_text'):
                                    current_text = current.get_text(strip=True)
                                    if 'Công Ty' in current_text or 'TNHH' in current_text or 'Công Ty Cổ Phần' in current_text or 'COMPANY' in current_text or 'LIMITED' in current_text:
                                        company_name = current_text
                                    elif 'Địa chỉ:' in current_text:
                                        company_info['address'] = current_text.replace('Địa chỉ:', '').strip()
                                    elif 'Điện thoại:' in current_text or 'Phone:' in current_text:
                                        company_info['phone'] = current_text.replace('Điện thoại:', '').replace('Phone:', '').strip()
                                    elif 'Email:' in current_text:
                                        company_info['email'] = current_text.replace('Email:', '').strip()
                                    elif 'Website:' in current_text:
                                        company_info['website'] = current_text.replace('Website:', '').strip()
                                    elif company_name:  # If we found company name, count this as info
                                        info_count += 1
                                current = current.next_sibling

                            if company_name:
                                numbered_companies.append({
                                    'name': company_name,
                                    'address': company_info.get('address', ''),
                                    'phone': company_info.get('phone', ''),
                                    'email': company_info.get('email', ''),
                                    'website': company_info.get('website', ''),
                                    'url': '',
                                    'is_numbered_format': True
                                })
                except:
                    pass

        if numbered_companies:
            company_blocks = numbered_companies

    # Fallback selector 3.5 - Tìm các div chứa link công ty
    if not company_blocks:
        company_links = []
        all_links = soup.find_all('a', href=True)
        for link in all_links:
            text = link.get_text(strip=True)
            href = link.get('href', '')
            if (len(text) > 5 and len(text) < 100 and
                'trangvangvietnam.com' in href):
                # Tìm div cha chứa link này
                parent = link.find_parent('div')
                if parent:
                    company_links.append(parent)

        # Loại bỏ trùng lặp
        unique_blocks = []
        seen = set()
        for block in company_links:
            block_id = id(block)
            if block_id not in seen:
                seen.add(block_id)
                unique_blocks.append(block)
        company_blocks = unique_blocks

    # Fallback selector 4 - tìm các div có text trông như tên công ty
    if not company_blocks:
        all_divs = soup.find_all('div')
        for div in all_divs:
            text = div.get_text(strip=True)
            # Nếu div có text trông như tên công ty và có link
            if (len(text) > 10 and len(text) < 100 and
                any(word in text.upper() for word in ['CÔNG TY', 'TNHH', 'CP', 'COMPANY']) and
                div.select_one('a[href]')):
                company_blocks.append(div)

    # Fallback selector 5 - lấy tất cả các div có link và text hợp lý
    if not company_blocks:
        all_divs = soup.find_all('div')
        for div in all_divs:
            links = div.select('a[href]')
            if links:
                for link in links:
                    text = link.get_text(strip=True)
                    href = link.get('href', '')
                    if (len(text) > 5 and len(text) < 100 and
                        not any(skip in text.lower() for skip in ['xem thêm', 'chi tiết', 'liên hệ', 'gọi']) and
                        ('trangvangvietnam.com' in href or href.startswith('/'))):
                        company_blocks.append(div)
                        break

    print(f"  Tim thay {len(company_blocks)} blocks trong HTML")
    companies = []

    for idx, block in enumerate(company_blocks, 1):
        try:
            # Check if this is a numbered format company (dict object)
            if isinstance(block, dict) and block.get('is_numbered_format'):
                # For numbered format, the data is already extracted
                companies.append({
                    'stt': idx,
                    'name': block['name'],
                    'link': block.get('url', ''),
                    'industry': '',
                    'address': block['address'],
                    'phone': block['phone'],
                    'email': block.get('email', ''),
                    'website': block.get('website', ''),
                    'hotline': '',
                    'nganh_nghe': '',
                    'fax': '',
                    'description': '',
                    'products': '',
                    'info': '',
                    'raw_html': ''
                })
                continue

            # Regular HTML element processing
            # Tên và link công ty - thử nhiều cách
            name = ''
            link = ''

            # Cách 1: h2 a (cách cũ)
            name_element = block.select_one('h2 a')
            if name_element:
                name = name_element.get_text(strip=True)
                link = name_element.get('href', '')

            # Cách 2: h3 a
            if not name:
                name_element = block.select_one('h3 a')
                if name_element:
                    name = name_element.get_text(strip=True)
                    link = name_element.get('href', '')

            # Cách 3: h4 a
            if not name:
                name_element = block.select_one('h4 a')
                if name_element:
                    name = name_element.get_text(strip=True)
                    link = name_element.get('href', '')

            # Cách 4: a đầu tiên trong block có text hợp lý
            if not name:
                links = block.select('a[href]')
                for a_tag in links:
                    text = a_tag.get_text(strip=True)
                    href = a_tag.get('href', '')
                    if (len(text) > 5 and len(text) < 100 and
                        not any(skip in text.lower() for skip in ['xem thêm', 'chi tiết', 'liên hệ', 'gọi', 'tel:', 'mailto:']) and
                        ('trangvangvietnam.com' in href or href.startswith('/') or '/cty/' in href or '/company/' in href)):
                        name = text
                        link = href
                        break

            # Cách 5: text trong div nếu có link
            if not name:
                text = block.get_text(strip=True)
                links = block.select('a[href]')
                if links and len(text) > 5 and len(text) < 100:
                    name = text
                    link = links[0].get('href', '')

            # Địa chỉ
            address = ''
            addr_icon = block.select_one('.fa-location-dot')
            if addr_icon and addr_icon.parent:
                address = addr_icon.parent.get_text(separator=' ', strip=True)

            if not address:
                logo_diachi = block.select('.logo_congty_diachi div')
                for div in logo_diachi:
                    text = div.get_text(strip=True)
                    if ('NGÀNH:' not in text and
                            not div.select('.listing_dienthoai') and
                            not div.select('i.fa-phone-volume') and
                            not div.select('i.fa-mobile-screen-button') and
                            'Hotline:' not in text):
                        small_tag = div.select_one('small')
                        if small_tag:
                            address = small_tag.get_text(separator=' ', strip=True)
                            break
                        elif text and len(text) > 10:
                            address = text
                            break

            if not address:
                nologo_diachi = block.select('.listing_diachi_nologo div')
                for div in nologo_diachi:
                    text = div.get_text(strip=True)
                    if ('NGÀNH:' not in text and
                            not div.select('i.fa-phone-volume') and
                            not div.select('i.fa-mobile-screen-button')):
                        small_tag = div.select_one('small')
                        if small_tag:
                            address = small_tag.get_text(separator=' ', strip=True)
                            break
                        elif text and len(text) > 10:
                            address = text
                            break

            # Điện thoại
            phone_elements = []
            phone_elements = block.select('.pt-0.pb-2.ps-3.pe-4.listing_dienthoai a')

            if not phone_elements:
                phone_elements = block.select('.listing_dienthoai a')

            if not phone_elements:
                phone_divs = block.select('.p-2.pt-0.ps-0.pe-4.pb-0')
                for div in phone_divs:
                    if div.select('i.fa-phone-volume'):
                        phone_elements = div.select('a')
                        break

            if not phone_elements:
                phone_icon = block.select_one('.fa.fa-solid.fa-phone-volume.text-black-50.pe-1')
                if not phone_icon:
                    phone_icon = block.select_one('.fa-phone-volume')
                if phone_icon and phone_icon.parent:
                    phone_a = phone_icon.parent.select_one('a')
                    if phone_a:
                        phone_elements = [phone_a]

            phones = ', '.join([p.get_text(strip=True) for p in phone_elements]) if phone_elements else ''

            # Hotline
            hotline = ''
            hot_icon = block.select_one('.fa.fa-solid.fa-mobile-screen-button.pe-1.text-black-50')
            if not hot_icon:
                hot_icon = block.select_one('.fa-mobile-screen-button')

            if hot_icon:
                parent = hot_icon.parent
                if parent:
                    a_tag = parent.select_one('a')
                    if a_tag:
                        hotline = a_tag.get_text(strip=True)
                    else:
                        text = parent.get_text(strip=True)
                        text = text.replace(hot_icon.get_text(strip=True), '').strip()
                        text = text.replace('Hotline:', '').strip()
                        hotline = text

            # Email
            email_el = block.select_one('a[href^="mailto:"]')
            email = email_el.get('href', '').replace('mailto:', '') if email_el else ''

            # Website
            website_el = block.select_one('a[rel="nofollow"]')
            website = website_el.get_text(strip=True) if website_el else ''

            # Ngành nghề
            industry_el = block.select_one('.nganh_listing_txt')
            industry = industry_el.get_text(strip=True) if industry_el else ''

            # Gộp phones và hotline
            phone_combined = []
            if phones:
                phone_combined.append(phones)
            if hotline:
                phone_combined.append(hotline)
            phone_final = ' / '.join(phone_combined) if phone_combined else ''

            if name:
                full_link = link if link.startswith('http') else f'https://trangvangvietnam.com{link}'
                companies.append({
                    'stt': idx,
                    'name': name,
                    'link': full_link,
                    'industry': industry,
                    'address': address,
                    'phone': phone_final,
                    'email': email,
                    'website': website,
                })
        except Exception as e:
            print(f"Loi parse block {idx}: {e}")
            continue

    return companies


# ==================== HELPER: PARSE DETAIL PAGE ====================
def extract_company_detail(detail_url):
    """
    Trích xuất thông tin chi tiết từ trang công ty
    """
    try:
        resp = fetch_url_with_retry(detail_url)
        if not resp:
            return {}

        soup = BeautifulSoup(resp.text, 'html.parser')

        detail = {
            'tax_code': '',
            'representative': '',
            'established_year': '',
            'field': '',
            'email_detail': '',
            'website_detail': '',
            'phone_detail': '',
            'address_detail': ''
        }

        # Tìm các thẻ chứa thông tin
        candidates = []
        candidates += soup.select('.company_info_detail p')
        candidates += soup.select('.company_info_detail li')
        candidates += soup.select('.info_company p')
        candidates += soup.select('.info_company li')
        candidates += soup.select('.company_profile p')
        candidates += soup.select('.company_profile li')

        if not candidates:
            candidates = soup.find_all(['p', 'li', 'div'], text=True)

        # Duyệt và tìm thông tin
        for node in candidates:
            try:
                text = node.get_text(separator=' ', strip=True)
                lower_text = text.lower()

                if 'mã số thuế' in lower_text or 'mst' in lower_text:
                    detail['tax_code'] = text.split(':')[-1].strip()
                elif 'người đại diện' in lower_text:
                    detail['representative'] = text.split(':')[-1].strip()
                elif 'năm thành lập' in lower_text:
                    detail['established_year'] = text.split(':')[-1].strip()
                elif 'lĩnh vực' in lower_text or 'ngành nghề' in lower_text:
                    detail['field'] = text.split(':')[-1].strip()
                elif 'email' in lower_text and '@' in text:
                    detail['email_detail'] = text.split(':')[-1].strip().replace('mailto:', '')
                elif 'website' in lower_text or 'trang web' in lower_text:
                    detail['website_detail'] = text.split(':')[-1].strip()
                elif 'điện thoại' in lower_text or 'sđt' in lower_text or 'hotline' in lower_text:
                    detail['phone_detail'] = text.split(':')[-1].strip()
                elif 'địa chỉ' in lower_text and not detail['address_detail']:
                    detail['address_detail'] = text.split(':')[-1].strip()
            except Exception:
                continue

        # Fallback email
        if not detail['email_detail']:
            email_tag = soup.select_one('a[href^="mailto:"]')
            if email_tag:
                detail['email_detail'] = email_tag.get('href', '').replace('mailto:', '').strip()

        # Fallback website
        if not detail['website_detail']:
            web_tag = soup.select_one('a[rel="nofollow"]')
            if web_tag:
                detail['website_detail'] = web_tag.get_text(strip=True) or web_tag.get('href', '')
            else:
                http_tag = soup.select_one('a[href^="http"]')
                if http_tag:
                    detail['website_detail'] = http_tag.get('href')

        return detail

    except Exception as e:
        print(f"Loi extract detail {detail_url}: {e}")
        return {}


# ==================== HELPER: FETCH DETAIL PARALLEL ====================
def fetch_detail_parallel(companies_list, max_workers=MAX_WORKERS):
    """
    Lấy thông tin chi tiết song song để tăng tốc
    """
    print(f"Bat dau lay {len(companies_list)} detail voi {max_workers} luong...")

    def fetch_one(company):
        try:
            if company.get('link'):
                detail = extract_company_detail(company['link'])
                company.update(detail)
                time.sleep(DELAY_BETWEEN_DETAILS)
        except Exception as e:
            print(f"Loi detail {company.get('name')}: {e}")
        return company

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(fetch_one, c): c for c in companies_list}

        completed = 0
        for future in as_completed(futures):
            completed += 1
            if completed % 10 == 0:
                print(f"  Da xu ly {completed}/{len(companies_list)} cong ty")

    print(f"Hoan thanh lay detail cho {len(companies_list)} cong ty")
    return companies_list


# ==================== CORE SCRAPING ====================
def scrape_companies(base_url, start_page=1, end_page=1, fetch_detail=False, max_companies=None):
    """
    Scrape công ty từ trang list với check trùng nâng cao
    """
    all_companies = []
    duplicate_count = 0

    for page in range(start_page, end_page + 1):
        try:
            # Build page URL - Fixed pagination logic
            parsed_url = urlparse(base_url)
            query_params = parse_qs(parsed_url.query)

            # Remove existing page parameter if exists
            query_params.pop('page', None)

            # Add new page parameter
            query_params['page'] = [str(page)]

            # Rebuild URL
            new_query = urlencode(query_params, doseq=True)
            page_url = urlunparse((
                parsed_url.scheme,
                parsed_url.netloc,
                parsed_url.path,
                parsed_url.params,
                new_query,
                parsed_url.fragment
            ))

            print(f"Dang lay trang {page}: {page_url}")

            # Request list page
            resp = fetch_url_with_retry(page_url)
            if not resp:
                print(f"Khong the lay trang {page}")
                continue

            resp.encoding = 'utf-8'
            content_length = len(resp.text)
            print(f"  Nhan duoc {content_length} ky tu HTML")

            # Parse companies
            companies = extract_companies_from_list(resp.text)
            print(f"  Parse duoc {len(companies)} cong ty tu HTML")

            # Filter duplicate
            page_duplicate_count = 0
            for c in companies:
                is_dup, matched = is_duplicate_company(c, all_companies)

                if is_dup:
                    duplicate_count += 1
                    page_duplicate_count += 1
                    safe_name1 = c['name'].encode('ascii', 'ignore').decode('ascii')
                    safe_name2 = matched['name'].encode('ascii', 'ignore').decode('ascii')
                    print(f"  Bo qua trung: '{safe_name1}' ~ '{safe_name2}'")
                else:
                    c['stt'] = len(all_companies) + 1
                    c['page'] = page
                    c['normalized_name'] = normalize_company_name(c['name'])
                    all_companies.append(c)

            print(
                f"  Trang {page}: Parse {len(companies)}, trung {page_duplicate_count}, them {len(companies) - page_duplicate_count}")

            # Check max limit
            if max_companies and len(all_companies) >= max_companies:
                print(f"Da dat gioi han {max_companies} cong ty")
                all_companies = all_companies[:max_companies]
                break

            # Delay
            if page < end_page:
                print(f"  Cho {DELAY_BETWEEN_PAGES}s...")
                time.sleep(DELAY_BETWEEN_PAGES)

        except Exception as e:
            print(f"Loi xu ly trang {page}: {e}")
            traceback.print_exc()
            continue

    print("Tong ket scrape:")
    print(f"   - Cong ty unique: {len(all_companies)}")
    print(f"   - Cong ty trung da loai: {duplicate_count}")

    # Fetch detail nếu cần
    if fetch_detail and all_companies:
        all_companies = fetch_detail_parallel(all_companies, max_workers=MAX_WORKERS)

    print(f"Hoan thanh: {len(all_companies)} cong ty")
    return all_companies


# ==================== HELPER: SAVE TO MASTER ====================
def save_to_master_excel(companies_list):
    """
    Lưu danh sách công ty vào file Excel tổng hợp với check trùng nâng cao
    """
    try:
        if not companies_list:
            return {
                'success': False,
                'message': 'Không có dữ liệu để lưu',
                'total_saved': 0,
                'new_records': 0,
                'duplicate_removed': 0
            }

        # Chuẩn bị DataFrame mới
        new_df = pd.DataFrame(companies_list)
        new_df['scraped_at'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        # Đảm bảo có cột normalized_name
        if 'normalized_name' not in new_df.columns:
            new_df['normalized_name'] = new_df['name'].apply(normalize_company_name)

        # Sắp xếp cột
        cols_order = [
            'stt', 'page', 'name', 'normalized_name', 'industry', 'address', 'address_detail',
            'phone', 'phone_detail', 'email', 'email_detail',
            'website', 'website_detail', 'tax_code', 'representative',
            'established_year', 'field', 'link', 'scraped_at'
        ]
        cols_order = [c for c in cols_order if c in new_df.columns]
        remaining = [c for c in new_df.columns if c not in cols_order]
        new_df = new_df[cols_order + remaining]

        # Kiểm tra file đã tồn tại chưa
        if os.path.exists(MASTER_EXCEL_FILE):
            print(f"File master ton tai, dang merge...")

            # Đọc dữ liệu cũ
            old_df = pd.read_excel(MASTER_EXCEL_FILE, engine='openpyxl')
            print(f"  Du lieu cu: {len(old_df)} cong ty")

            # Đảm bảo old_df có normalized_name
            if 'normalized_name' not in old_df.columns:
                old_df['normalized_name'] = old_df['name'].apply(normalize_company_name)

            old_count = len(old_df)
            new_count = len(new_df)

            # Gộp dữ liệu
            combined_df = pd.concat([old_df, new_df], ignore_index=True)

            # Loại trùng theo normalized_name
            print(f"  🔍 Check trùng theo tên chuẩn hóa...")
            before_dedup = len(combined_df)

            combined_df = combined_df.drop_duplicates(
                subset=['normalized_name'],
                keep='last'
            ).reset_index(drop=True)

            after_dedup = len(combined_df)
            duplicates_removed = before_dedup - after_dedup

            # Cập nhật lại STT
            combined_df['stt'] = range(1, len(combined_df) + 1)

            print(f"  Ket qua merge:")
            print(f"     - Dữ liệu cũ: {old_count}")
            print(f"     - Dữ liệu mới: {new_count}")
            print(f"     - Tổng trước loại trùng: {before_dedup}")
            print(f"     - Đã loại trùng: {duplicates_removed}")
            print(f"     - Tổng sau loại trùng: {after_dedup}")

            # Lưu file
            combined_df.to_excel(MASTER_EXCEL_FILE, index=False, engine='openpyxl')

            new_records = after_dedup - old_count
            return {
                'success': True,
                'message': f'Thêm {new_records} mới, loại {duplicates_removed} trùng',
                'total_saved': after_dedup,
                'new_records': max(0, new_records),
                'duplicate_removed': duplicates_removed,
                'file_path': os.path.abspath(MASTER_EXCEL_FILE)
            }
        else:
            print(f"📝 Tạo file master mới...")

            # Loại trùng trong chính dữ liệu mới
            before_dedup = len(new_df)
            new_df = new_df.drop_duplicates(
                subset=['normalized_name'],
                keep='first'
            ).reset_index(drop=True)
            after_dedup = len(new_df)
            duplicates_removed = before_dedup - after_dedup

            # Cập nhật lại STT
            new_df['stt'] = range(1, len(new_df) + 1)

            # Tạo file mới
            new_df.to_excel(MASTER_EXCEL_FILE, index=False, engine='openpyxl')

            print(f"  File moi: {after_dedup} cong ty (loai {duplicates_removed} trung noi bo)")

            return {
                'success': True,
                'message': f'Tạo file master với {after_dedup} công ty',
                'total_saved': after_dedup,
                'new_records': after_dedup,
                'duplicate_removed': duplicates_removed,
                'file_path': os.path.abspath(MASTER_EXCEL_FILE)
            }

    except Exception as e:
        print(f"Loi luu master: {e}")
        traceback.print_exc()
        return {
            'success': False,
            'message': f'Lỗi: {str(e)}',
            'total_saved': 0,
            'new_records': 0,
            'duplicate_removed': 0
        }


# ==================== API ENDPOINTS ====================

@app.route('/api/scrape', methods=['POST'])
def api_scrape():
    """API scrape và trả về JSON + Tự động lưu vào file master"""
    try:
        data = request.get_json(force=True)
        url = data.get('url')
        start_page = int(data.get('start_page', 1))
        end_page = int(data.get('end_page', start_page))
        fetch_detail = bool(data.get('fetch_detail', False))
        max_companies = data.get('max_companies')
        auto_save = bool(data.get('auto_save', True))

        if max_companies:
            try:
                max_companies = int(max_companies)
            except:
                max_companies = None

        if not url:
            return jsonify({
                'success': False,
                'error': 'URL không được để trống'
            }), 400

        companies = scrape_companies(
            base_url=url,
            start_page=start_page,
            end_page=end_page,
            fetch_detail=fetch_detail,
            max_companies=max_companies
        )

        # Tự động lưu vào file master
        save_result = None
        if auto_save and companies:
            print(f"Dang luu {len(companies)} cong ty vao file master...")
            save_result = save_to_master_excel(companies)
            print(f"{save_result.get('message')}")

        response_data = {
            'success': True,
            'total': len(companies),
            'companies': companies
        }

        if save_result:
            response_data['saved_to_master'] = save_result

        return jsonify(response_data)

    except Exception as e:
        print(f"API /api/scrape error: {e}")
        traceback.print_exc()
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/api/export', methods=['POST'])
def api_export():
    """API scrape và xuất file Excel (cũng lưu vào master)"""
    try:
        data = request.get_json(force=True)
        url = data.get('url')
        start_page = int(data.get('start_page', 1))
        end_page = int(data.get('end_page', start_page))
        max_companies = data.get('max_companies')

        if max_companies:
            try:
                max_companies = int(max_companies)
            except:
                max_companies = None

        if not url:
            return jsonify({
                'success': False,
                'error': 'URL không được để trống'
            }), 400

        # Luôn fetch detail khi export
        companies = scrape_companies(
            base_url=url,
            start_page=start_page,
            end_page=end_page,
            fetch_detail=True,
            max_companies=max_companies
        )

        if not companies:
            return jsonify({
                'success': False,
                'error': 'Không lấy được dữ liệu'
            }), 200

        # Lưu vào file master
        print(f"Dang luu vao file master...")
        save_result = save_to_master_excel(companies)
        print(f"{save_result.get('message')}")

        # Chuyển sang DataFrame
        df = pd.DataFrame(companies)
        df['exported_at'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        # Sắp xếp cột
        cols_order = [
            'stt', 'page', 'name', 'industry', 'address', 'address_detail',
            'phone', 'phone_detail', 'email', 'email_detail',
            'website', 'website_detail', 'tax_code', 'representative',
            'established_year', 'field', 'link', 'exported_at'
        ]
        cols_order = [c for c in cols_order if c in df.columns]
        remaining = [c for c in df.columns if c not in cols_order]
        df = df[cols_order + remaining]

        # Ghi file Excel tạm
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix='.xlsx')
        tmp_path = tmp.name
        tmp.close()

        df.to_excel(tmp_path, index=False, engine='openpyxl')

        return send_file(
            tmp_path,
            as_attachment=True,
            download_name=f'companies_export_{datetime.now().strftime("%Y%m%d_%H%M%S")}.xlsx',
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )

    except Exception as e:
        print(f"API /api/export error: {e}")
        traceback.print_exc()
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/api/master/download', methods=['GET'])
def download_master():
    """Download file Excel tổng hợp"""
    try:
        if not os.path.exists(MASTER_EXCEL_FILE):
            return jsonify({
                'success': False,
                'error': 'File master chưa tồn tại'
            }), 404

        return send_file(
            MASTER_EXCEL_FILE,
            as_attachment=True,
            download_name=f'companies_master_{datetime.now().strftime("%Y%m%d_%H%M%S")}.xlsx',
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/api/master/info', methods=['GET'])
def master_info():
    """Lấy thông tin về file Excel tổng"""
    try:
        if not os.path.exists(MASTER_EXCEL_FILE):
            return jsonify({
                'success': True,
                'exists': False,
                'message': 'File master chưa tồn tại'
            })

        # Đọc file để lấy thông tin
        df = pd.read_excel(MASTER_EXCEL_FILE, engine='openpyxl')
        file_size = os.path.getsize(MASTER_EXCEL_FILE)
        modified_time = datetime.fromtimestamp(
            os.path.getmtime(MASTER_EXCEL_FILE)
        ).strftime('%Y-%m-%d %H:%M:%S')

        return jsonify({
            'success': True,
            'exists': True,
            'total_companies': len(df),
            'file_size': f'{file_size / 1024:.2f} KB',
            'last_modified': modified_time,
            'file_path': os.path.abspath(MASTER_EXCEL_FILE)
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/api/master/clear', methods=['POST'])
def clear_master():
    """Xóa file Excel tổng"""
    try:
        if os.path.exists(MASTER_EXCEL_FILE):
            os.remove(MASTER_EXCEL_FILE)
            return jsonify({
                'success': True,
                'message': 'Đã xóa file master'
            })
        else:
            return jsonify({
                'success': True,
                'message': 'File master không tồn tại'
            })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/api/health', methods=['GET'])
def health():
    """Health check endpoint"""
    master_exists = os.path.exists(MASTER_EXCEL_FILE)
    master_count = 0

    if master_exists:
        try:
            df = pd.read_excel(MASTER_EXCEL_FILE, engine='openpyxl')
            master_count = len(df)
        except:
            pass

    return jsonify({
        'status': 'ok',
        'message': 'Server đang hoạt động',
        'version': '3.0.0',
        'master_file': {
            'exists': master_exists,
            'total_companies': master_count,
            'file_name': MASTER_EXCEL_FILE
        }
    })


@app.route('/', methods=['GET'])
def index():
    """Serve index.html hoặc info"""
    try:
        # Tìm trong templates folder trước
        templates_path = os.path.join(os.path.dirname(__file__), 'templates')
        index_path = os.path.join(templates_path, 'index.html')
        if os.path.exists(index_path):
            return send_file(index_path)
    except Exception:
        pass

    return jsonify({
        'message': 'Company Scraper API v3.0',
        'endpoints': {
            'POST /api/scrape': 'Scrape và trả JSON (tự động lưu master)',
            'POST /api/export': 'Scrape và xuất Excel (cũng lưu master)',
            'GET /api/master/download': 'Download file master',
            'GET /api/master/info': 'Xem thông tin file master',
            'POST /api/master/clear': 'Xóa file master',
            'GET /api/health': 'Health check'
        },
        'master_file': MASTER_EXCEL_FILE
    })


# ==================== MAIN ====================
if __name__ == '__main__':
    print("=" * 80)
    print("COMPANY SCRAPER v3.0 - FULL REWRITE")
    print("=" * 80)
    print("Server: http://localhost:5003")
    print("")
    print("API Endpoints:")
    print("   POST /api/scrape          - Scrape và trả JSON (tự động lưu master)")
    print("   POST /api/export          - Scrape và xuất Excel (cũng lưu master)")
    print("   GET  /api/master/download - Download file Excel tổng")
    print("   GET  /api/master/info     - Xem thông tin file master")
    print("   POST /api/master/clear    - Xóa file master")
    print("   GET  /api/health          - Health check")
    print("")
    print(f"File Excel tong: {MASTER_EXCEL_FILE}")
    print("")
    print("Tinh nang v3.0:")
    print("   - Check trùng thông minh với chuẩn hóa tên")
    print("   - Tự động lưu vào file master")
    print("   - Retry logic mạnh mẽ")
    print("   - Multi-selector parsing")
    print("   - Parallel detail fetching")
    print("=" * 80)
    app.run(debug=True, host='0.0.0.0', port=5003)