# 🚀 Codeforces & Polygon Auto Uploader

Hệ thống tự động hóa toàn diện quy trình lấy đề bài từ bất kỳ đường link nào (LeetCode, AtCoder, Codeforces, CSES, VNOJ,...), sử dụng AI để bóc tách đề bài, sinh lời giải chuẩn C++20, validator theo chuẩn `testlib.h`, generator sinh **20 test cases** phong phú, tự động khởi tạo bài trên **Polygon Codeforces**, nạp code, thiết lập test, build Full Package, phân quyền user `codeforces` và xuất bảng tổng hợp ra **Excel (.xlsx)**.

---

## 🌟 Tính Năng Chính

1. **Bóc tách đề bài đa nguồn**: Hỗ trợ chuyên sâu LeetCode, AtCoder, Codeforces, CSES, VNOJ và Generic Scraper thông minh cho mọi trang web.
2. **AI Problem Engine**:
   - Viết lời giải chuẩn C++20 tối ưu, tránh tràn số (`long long`), fast I/O.
   - Viết `validator.cpp` chuẩn `testlib.h` kiểm tra tính hợp lệ của dữ liệu vào.
   - Viết `gen.cpp` chuẩn `testlib.h` sinh test ngẫu nhiên theo tham số.
   - Tự động chọn checker (`std::wcmp.cpp`, `std::ncmp.cpp`, `std::rcmp6.cpp`, `std::yesno.cpp`, hoặc custom).
3. **Chiến lược sinh 20 Test Cases**:
   - Sinh đúng **20 test cases** đa dạng: test biên cực tiểu, các trường hợp góc (toàn 0, âm, giống nhau, đã sort/đảo ngược), test ngẫu nhiên, test cực đại ($N = N_{\max}$) chống hack.
   - Test ví dụ tự động được cấu hình hiển thị trong đề bài (`useInStatements = true`).
4. **Polygon Automation**:
   - Tự động tạo bài tập với short-name chuẩn.
   - Nạp đề bài (LaTeX Markdown) định dạng chuẩn Polygon.
   - Nạp solution, validator, generator, checker và testset.
   - Tự động yêu cầu Polygon build Full Package.
   - Tự động phân quyền (Manage Access) cho user `codeforces` để sẵn sàng import vào Mashup / Gym Contest trên Codeforces.
5. **Xuất Báo Cáo Excel**:
   - Tự động ghi lại và cập nhật vào `problems_summary.xlsx` với hyperlink và màu sắc trạng thái.

---

## 🛠️ Hướng Dẫn Cài Đặt & Chạy

### 1. Cài đặt môi trường
Hệ thống sử dụng Python 3.10+ và các thư viện cần thiết.
Nếu chưa cài đặt thư viện:
```bash
python -m venv .venv
# Trên Windows:
.\.venv\bin\pip install -r requirements.txt
```

### 2. Cấu hình API (`config/config.yaml`)
File `config/config.yaml` đã được thiết lập sẵn với thông tin của bạn:
```yaml
polygon:
  api_key: "YOUR_POLYGON_API_KEY"
  api_secret: "YOUR_POLYGON_API_SECRET"
  api_url: "https://polygon.codeforces.com/api/"

ai:
  provider: "gemini"
  gemini_api_key: "YOUR_GEMINI_API_KEY"
  gemini_backup_keys:
    # - "AIzaSy..."
  model_name: "gemini-3.7-flash"

generation:
  num_tests: 20
  include_samples_in_statements: true
  auto_grant_access_to_codeforces: true
  auto_package: true

export:
  excel_file_path: "problems_summary.xlsx"
```

---

## 💻 Cách Sử Dụng

### Chế độ Giao diện Dòng Lệnh Tương Tác (Interactive Menu)
```bash
.\.venv\bin\python.exe run.py
```

### Chạy trực tiếp 1 đường link
```bash
.\.venv\bin\python.exe run.py --url "https://leetcode.com/problems/two-sum/"
```

### Chạy hàng loạt từ file danh sách
```bash
.\.venv\bin\python.exe run.py --batch urls.txt
```

### Kiểm tra kết nối API Polygon & Gemini
```bash
.\.venv\bin\python.exe run.py --test
```

### Xem danh sách bài trên Polygon và xuất ra file Excel
```bash
.\.venv\bin\python.exe run.py --list
```
