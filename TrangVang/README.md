# 🔍 Web Scraper - Công cụ lấy thông tin công ty

Hệ thống hoàn chỉnh để trích xuất thông tin công ty từ Trang Vàng Việt Nam.

## 📋 Tính năng

✅ Lấy thông tin công ty từ nhiều trang  
✅ Trích xuất: Tên, ngành nghề, địa chỉ, SĐT, email, website  
✅ Giao diện web đẹp, dễ sử dụng  
✅ Xuất file CSV (hỗ trợ tiếng Việt)  
✅ Backend API với Python Flask  
✅ Frontend với HTML + TailwindCSS  

---

## 📁 Cấu trúc thư mục

```
company-scraper/
├── app.py              # Backend Flask Server
├── requirements.txt    # Python dependencies
├── index.html          # Frontend giao diện
└── README.md          # File này
```

---

## 🚀 Cài đặt và chạy

### Bước 1: Cài đặt Python

- Tải Python từ: https://www.python.org/downloads/
- Chọn phiên bản **3.8 trở lên**
- ⚠️ **Quan trọng**: Tick vào **"Add Python to PATH"** khi cài đặt

### Bước 2: Tạo thư mục project

```bash
mkdir company-scraper
cd company-scraper
```

### Bước 3: Tạo các file

1. **Tạo file `app.py`**
   - Copy toàn bộ code từ artifact "app.py - Backend Flask Server"
   - Lưu vào thư mục `company-scraper/app.py`

2. **Tạo file `requirements.txt`**
   - Copy toàn bộ code từ artifact "requirements.txt"
   - Lưu vào thư mục `company-scraper/requirements.txt`

3. **Tạo file `index.html`**
   - Copy toàn bộ code từ artifact "index.html - Frontend HTML"
   - Lưu vào thư mục `company-scraper/index.html`

### Bước 4: Cài đặt thư viện Python

```bash
pip install -r requirements.txt
```

Hoặc cài đặt từng thư viện:

```bash
pip install flask flask-cors requests beautifulsoup4 lxml
```

### Bước 5: Chạy Backend Server

```bash
python app.py
```

✅ Server sẽ chạy tại: **http://localhost:5000**

Bạn sẽ thấy:
```
🚀 COMPANY SCRAPER - BACKEND SERVER
📍 Server đang khởi động tại: http://localhost:5000
📝 API Endpoint: POST http://localhost:5000/api/scrape
💚 Health Check: GET http://localhost:5000/api/health
⚡ Server sẵn sàng! Hãy chạy frontend để bắt đầu...
```

### Bước 6: Mở Frontend

- Mở file `index.html` bằng trình duyệt (Chrome, Firefox, Edge...)
- Hoặc click đúp vào file `index.html`

---

## 💻 Cách sử dụng

1. **Nhập URL** trang web cần lấy dữ liệu
   - Mặc định: `https://trangvangvietnam.com/categories/235360/tra-che-san-xuat-va-kinh-doanh.html`

2. **Chọn phạm vi trang**
   - Từ trang: `1`
   - Đến trang: `3`

3. **Nhấn "Bắt đầu lấy dữ liệu"**
   - Chờ hệ thống xử lý (khoảng 1-2 giây/trang)

4. **Xem kết quả**
   - Dữ liệu hiển thị dạng bảng

5. **Xuất CSV**
   - Nhấn nút "Xuất CSV" để tải file
   - File có format: `danh_sach_cong_ty_[timestamp].csv`

---

## 🔧 API Endpoints

### POST `/api/scrape`

Scrape dữ liệu công ty

**Request Body:**
```json
{
  "url": "https://trangvangvietnam.com/...",
  "start_page": 1,
  "end_page": 3
}
```

**Response:**
```json
{
  "success": true,
  "companies": [...],
  "total": 38,
  "pages_scraped": 3
}
```

### GET `/api/health`

Kiểm tra server

**Response:**
```json
{
  "status": "ok",
  "message": "Server đang chạy tốt",
  "version": "1.0.0"
}
```

---

## 📊 Dữ liệu trích xuất

Mỗi công ty có các thông tin:

| Field | Mô tả |
|-------|-------|
| `stt` | Số thứ tự |
| `name` | Tên công ty |
| `industry` | Ngành nghề |
| `address` | Địa chỉ |
| `phones` | Số điện thoại |
| `hotline` | Hotline |
| `email` | Email |
| `website` | Website |
| `link` | Link chi tiết |
| `page` | Trang số |

---

## ⚠️ Lưu ý

1. **Backend phải chạy trước frontend**
   - Chạy `python app.py` trước
   - Sau đó mở `index.html`

2. **Port 5000 phải trống**
   - Nếu bị chiếm, thay đổi port trong `app.py`
   - Cập nhật URL trong `index.html`

3. **Cần kết nối internet**
   - Để scrape dữ liệu từ website

4. **Thời gian xử lý**
   - Khoảng 1-2 giây mỗi trang
   - Có delay để tránh spam server

5. **File CSV**
   - Mã hóa UTF-8 với BOM
   - Mở bằng Excel/Google Sheets

---

## 🐛 Xử lý lỗi thường gặp

### Lỗi: "Module not found"

```bash
pip install -r requirements.txt
```

### Lỗi: "Address already in use"

Port 5000 bị chiếm. Thay đổi port:

```python
# Trong app.py, dòng cuối
app.run(debug=True, host='0.0.0.0', port=5001)  # Đổi 5000 -> 5001
```

### Lỗi: "Cannot connect to server"

- Kiểm tra backend đã chạy chưa
- Kiểm tra URL trong frontend: `http://localhost:5000`

### Lỗi: "CORS"

Đã có `flask-cors`, nếu vẫn lỗi:

```bash
pip install --upgrade flask-cors
```

---

## 📝 Ví dụ sử dụng

### Test API bằng curl:

```bash
curl -X POST http://localhost:5000/api/scrape \
  -H "Content-Type: application/json" \
  -d '{
    "url": "https://trangvangvietnam.com/categories/235360/tra-che-san-xuat-va-kinh-doanh.html",
    "start_page": 1,
    "end_page": 2
  }'
```

### Test API bằng Python:

```python
import requests

response = requests.post('http://localhost:5000/api/scrape', json={
    'url': 'https://trangvangvietnam.com/categories/235360/tra-che-san-xuat-va-kinh-doanh.html',
    'start_page': 1,
    'end_page': 2
})

data = response.json()
print(f"Tìm thấy {data['total']} công ty")
```

---

## 🎯 Mở rộng

### Thêm tính năng mới:

1. **Lọc theo ngành nghề**
2. **Tìm kiếm theo địa chỉ**
3. **Export Excel**
4. **Lưu vào database**
5. **Gửi email báo cáo**

### Tối ưu hiệu suất:

1. **Multi-threading** cho nhiều trang
2. **Caching** kết quả
3. **Rate limiting** thông minh

---

## 📞 Hỗ trợ

Nếu gặp vấn đề:

1. Kiểm tra Python version: `python --version`
2. Kiểm tra pip: `pip --version`
3. Xem log backend khi chạy
4. Kiểm tra Console trong trình duyệt (F12)

---

## 📄 License

MIT License - Sử dụng tự do cho mục đích cá nhân và thương mại.

---

## 🙏 Credits

- **BeautifulSoup4**: HTML parsing
- **Flask**: Web framework
- **TailwindCSS**: UI styling
- **Trang Vàng Việt Nam**: Data source

---

**Chúc bạn sử dụng thành công! 🎉**