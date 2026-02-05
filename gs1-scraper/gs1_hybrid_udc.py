"""
gs1_hybrid_udc.py
Hybrid scraper for GS1 Verified by GS1:
- Use undetected_chromedriver to open the page (bypass bot blocking)
- Extract form_build_id, form_id and cookies
- Use requests.Session with those cookies to POST to the ajax endpoint (fast)
- Parse returned HTML for table rows and save to CSV
- Fallback: if API returns blocked/empty, use the browser to extract table and paginate

Config near top.
"""

import time
import json
import os
import requests
import pandas as pd
from bs4 import BeautifulSoup

# undetected_chromedriver wraps selenium
import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

# ================= CONFIG =================
KEYWORD = "My Pham"
COUNTRY = "VN"
MAX_PAGES = 5            # set None for no limit
OUTPUT_CSV = "gs1_vietnam_mypham.csv"
APPEND_TO_CSV = True     # append to file if exists
HEADLESS = False         # set True to run headless (may be more detectable)
AJAX_API = "https://www.gs1.org/services/verified-by-gs1/results?ajax_form=1&_wrapper_format=drupal_ajax"
# ==========================================

def start_undetected_browser(headless=HEADLESS, wait_seconds=30):
    opts = uc.ChromeOptions()
    if headless:
        opts.add_argument("--headless=new")
    opts.add_argument("--disable-gpu")
    opts.add_argument("--no-sandbox")
    # optional: tweak language to look like real user
    opts.add_argument("--lang=en-US,en")
    driver = uc.Chrome(options=opts)
    driver.set_page_load_timeout(60)
    return driver

def wait_for_form_and_cookies(driver, keyword=KEYWORD, country=COUNTRY, timeout=40):
    """
    Open the results page (with query) and wait for the Drupal form_build_id input to appear.
    Returns form_build_id, form_id, cookies list, user_agent
    """
    url = f"https://www.gs1.org/services/verified-by-gs1/results?company_name={keyword.replace(' ', '+')}&country={country}"
    driver.get(url)

    # wait for possible Cloudflare challenge to clear up and for form input to appear
    try:
        # Wait for either form_build_id or for a blocked-page indicator
        el = WebDriverWait(driver, timeout).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "input[name='form_build_id'], input[name='form_id'], body"))
        )
    except Exception as e:
        raise RuntimeError("Timed out waiting for page to load / form to appear.") from e

    # if blocked, page body may contain "The request is blocked"
    body_text = driver.page_source.lower()
    if "the request is blocked" in body_text or "service unavailable" in body_text:
        # screenshot saved for debugging
        driver.save_screenshot("gs1_blocked_debug.png")
        raise RuntimeError("The request is blocked by the server (Cloudflare/Firewall). Screenshot saved: gs1_blocked_debug.png")

    # accept cookie popup if present (try a few selectors)
    try:
        WebDriverWait(driver, 3).until(EC.element_to_be_clickable((By.ID, "onetrust-accept-btn-handler"))).click()
        time.sleep(0.5)
    except Exception:
        pass
    try:
        WebDriverWait(driver, 3).until(EC.element_to_be_clickable((By.XPATH, "//button[contains(text(), 'Accept')]"))).click()
        time.sleep(0.5)
    except Exception:
        pass

    # try to find hidden inputs - wait a bit for JS render
    form_build_id = None
    form_id = None
    try:
        fb = WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.NAME, "form_build_id")))
        form_build_id = fb.get_attribute("value")
    except Exception:
        # fallback parse page_source for hidden input
        soup = BeautifulSoup(driver.page_source, "html.parser")
        fb = soup.find("input", {"name": "form_build_id"})
        if fb:
            form_build_id = fb.get("value")

    try:
        fi = driver.find_element(By.NAME, "form_id")
        form_id = fi.get_attribute("value")
    except Exception:
        soup = BeautifulSoup(driver.page_source, "html.parser")
        fi = soup.find("input", {"name": "form_id"})
        if fi:
            form_id = fi.get("value")

    if not form_build_id:
        # save debug screenshot and page source
        driver.save_screenshot("gs1_no_form_debug.png")
        with open("gs1_no_form_source.html", "w", encoding="utf-8") as f:
            f.write(driver.page_source)
        raise RuntimeError("Could not find form_build_id on the page. Debug saved: gs1_no_form_debug.png and gs1_no_form_source.html")

    cookies = driver.get_cookies()  # list of dicts
    user_agent = driver.execute_script("return navigator.userAgent;")
    return form_build_id, form_id or "verified_search_form", cookies, user_agent

def cookies_to_requests_session(session, cookies):
    for c in cookies:
        name = c.get("name")
        value = c.get("value")
        # set cookie without domain to let requests manage domain
        session.cookies.set(name, value)

def parse_drupal_ajax_response(text):
    """
    Drupal ajax endpoint often returns JSON array of command objects OR raw HTML.
    We extract HTML that contains a table and return BeautifulSoup or None.
    """
    # try JSON parse
    try:
        parsed = json.loads(text)
        # parsed should be a list of dicts often
        html_parts = []
        if isinstance(parsed, dict):
            parsed = [parsed]
        for cmd in parsed:
            if isinstance(cmd, dict):
                # common keys: 'data' or 'html'
                for key in ("data", "html", "value"):
                    if key in cmd and isinstance(cmd[key], str):
                        html_parts.append(cmd[key])
        combined = "".join(html_parts)
        if "<table" in combined:
            return BeautifulSoup(combined, "html.parser")
    except Exception:
        pass

    # fallback: treat text as HTML
    if "<table" in text:
        return BeautifulSoup(text, "html.parser")

    return None

def extract_table_rows_from_soup(soup):
    rows = []
    if not soup:
        return rows
    table = soup.select_one("table.views-table") or soup.find("table")
    if not table:
        return rows
    tbody = table.find("tbody") or table
    for tr in tbody.find_all("tr"):
        cols = [td.get_text(strip=True) for td in tr.find_all("td")]
        if cols:
            rows.append(cols)
    return rows

def save_dataframe(records, output_csv=OUTPUT_CSV, append=APPEND_TO_CSV):
    if not records:
        print("No records to save.")
        return
    df = pd.DataFrame(records)
    # drop duplicates conservatively
    df = df.drop_duplicates()
    mode = "a" if append and os.path.exists(output_csv) else "w"
    header = not (append and os.path.exists(output_csv))
    df.to_csv(output_csv, index=False, encoding="utf-8-sig", mode=mode, header=header)
    print(f"Saved {len(df)} records to {output_csv} (mode={mode})")

def fast_api_flow(form_build_id, form_id, cookies, user_agent, max_pages=MAX_PAGES):
    """
    Use requests with cookies to call GS1 ajax endpoint page by page.
    Returns list of dict records.
    """
    session = requests.Session()
    cookies_to_requests_session(session, cookies)
    headers = {
        "User-Agent": user_agent,
        "X-Requested-With": "XMLHttpRequest",
        "Accept": "text/html, */*; q=0.01",
        "Referer": f"https://www.gs1.org/services/verified-by-gs1/results?company_name={KEYWORD.replace(' ','+')}&country={COUNTRY}"
    }

    all_records = []
    page = 0
    while True:
        if max_pages is not None and page >= max_pages:
            print("Reached max_pages limit.")
            break

        payload = {
            "company_name": KEYWORD,
            "country": COUNTRY,
            "form_id": form_id,
            "form_build_id": form_build_id,
            "_triggering_element_name": "licensee_submit",
            "_triggering_element_value": "Search",
            # include typical ajax_page_state items to mimic real request
            "ajax_page_state[theme]": "gs1_theme",
            "ajax_page_state[libraries]": "",  # optional
            "ajax_form": "1",
            "page": str(page)
        }

        print(f"POST ajax page={page} ...")
        r = session.post(AJAX_API, headers=headers, data=payload, timeout=30)
        if r.status_code != 200:
            print("HTTP error", r.status_code)
            print("Response snippet:", r.text[:400].replace("\n"," "))
            break

        # quick blocked check
        if "The request is blocked" in r.text or "Service unavailable" in r.text:
            print("Server blocked the request (returned blocked page).")
            return None  # indicate blocked

        soup = parse_drupal_ajax_response(r.text)
        if not soup:
            print("Could not parse HTML with table from ajax response (page {})".format(page))
            print("Response snippet:", r.text[:600].replace("\n"," "))
            return None

        rows = extract_table_rows_from_soup(soup)
        print(f"Found {len(rows)} rows on page {page}")

        if not rows:
            print("No rows returned -> end.")
            break

        # convert row lists into dicts where possible (common 4-column layout)
        for cols in rows:
            if len(cols) >= 4:
                all_records.append({
                    "License Key": cols[0],
                    "Company Name": cols[1],
                    "City": cols[2],
                    "Country": cols[3]
                })
            else:
                all_records.append({"Raw": " | ".join(cols)})

        page += 1
        time.sleep(0.6)

    return all_records

def fallback_browser_scrape(driver, max_pages=MAX_PAGES):
    """ If requests path blocked, use the browser itself to paginate and read tables. """
    print("FALLBACK: using browser to scrape visible table and click Next.")
    records = []
    page = 1
    while True:
        try:
            WebDriverWait(driver, 20).until(EC.presence_of_all_elements_located((By.CSS_SELECTOR, "table tbody tr")))
        except Exception:
            print("No table rows found on browser page.")
            break

        rows = driver.find_elements(By.CSS_SELECTOR, "table tbody tr")
        print(f"Browser page {page} rows: {len(rows)}")
        for r in rows:
            try:
                cols = r.find_elements(By.TAG_NAME, "td")
                vals = [c.text.strip() for c in cols]
                if len(vals) >= 4:
                    records.append({
                        "License Key": vals[0],
                        "Company Name": vals[1],
                        "City": vals[2],
                        "Country": vals[3]
                    })
                else:
                    records.append({"Raw": " | ".join(vals)})
            except Exception:
                continue

        if max_pages and page >= max_pages:
            print("Reached max_pages in browser fallback.")
            break

        # try next button
        try:
            nxt = driver.find_element(By.XPATH, "//a[contains(text(),'›') or contains(text(),'Next')]")
            if "disabled" in (nxt.get_attribute("class") or "").lower():
                break
            driver.execute_script("arguments[0].scrollIntoView(true);", nxt)
            time.sleep(0.5)
            nxt.click()
            page += 1
            time.sleep(2.5)
            continue
        except Exception:
            print("No next button or cannot click next: stopping browser pagination.")
            break

    return records

def main():
    print("Starting GS1 hybrid scraper...")

    # start browser (undetected)
    driver = None
    try:
        driver = start_undetected_browser()
        form_build_id, form_id, cookies, user_agent = wait_for_form_and_cookies(driver, KEYWORD, COUNTRY, timeout=40)
        print("Got form_build_id:", form_build_id)
    except Exception as e:
        print("Error while initializing browser / getting form_build_id:", e)
        if driver:
            driver.quit()
        return

    # try fast API flow via requests + cookies
    try:
        api_records = fast_api_flow(form_build_id, form_id, cookies, user_agent, max_pages=MAX_PAGES)
        if api_records is None:
            # blocked or couldn't parse -> fallback to browser scraping
            print("API path failed/blocked -> fallback to in-browser scraping.")
            browser_records = fallback_browser_scrape(driver, max_pages=MAX_PAGES)
            save_records = browser_records
        else:
            save_records = api_records
    except Exception as e:
        print("Error in API flow:", e)
        print("Falling back to browser scraping.")
        save_records = fallback_browser_scrape(driver, max_pages=MAX_PAGES)

    # save and exit
    if save_records:
        save_dataframe(save_records, OUTPUT_CSV, APPEND_TO_CSV)
    else:
        print("No records collected.")

    # clean up
    try:
        driver.quit()
    except Exception:
        pass

if __name__ == "__main__":
    main()
