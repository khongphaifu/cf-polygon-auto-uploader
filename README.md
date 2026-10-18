# 🚀 Codeforces & Polygon Auto Uploader

Hệ thống tự động hóa toàn diện quy trình lấy đề bài lập trình thi đấu (Competitive Programming) từ bất kỳ đường link nào (**Codeforces, AtCoder, CSES, VNOJ - kể cả đề PDF nhúng, MarisaOJ, LeetCode,...**), sử dụng AI Gemini để phân tích cấu trúc đề bài, sinh lời giải chuẩn **C++20 tối ưu**, viết **generator C++ (`testlib.h`)** phân chia **Subtasks & Điểm số**, kiểm định cục bộ 100% bằng MinGW GCC, tự động nạp lên **Polygon Codeforces**, build **Full Package** kèm cơ chế **Auto-Repair**, cấp quyền cho tài khoản `codeforces` và xuất kết quả ra file **Excel (`problems_summary.xlsx`)**.

---

## 🌟 Các Tính Năng Cốt Lõi & Cải Tiến

### 1. Bóc tách đề bài đa nguồn thông minh (Hỗ trợ cả HTML & PDF)
- **Đa nền tảng**: Hỗ trợ Codeforces, AtCoder, CSES, VNOJ, MarisaOJ (vượt Cloudflare với `cloudscraper`), LeetCode và Generic Scraper cho các trang web bất kỳ.
- **Hỗ trợ đề bài dạng PDF trên VNOJ**: Tự động nhận diện các thẻ `<object data="...pdf">`, `<iframe>`, thẻ `<a>` chứa file PDF đề bài (ví dụ các bài Free Contest trên VNOJ), tự động tải binary PDF và truyền vào **Gemini Multimodal API (`application/pdf`)** để phân tích đề bài, giới hạn và test ví dụ chính xác tuyệt đối.
- **Làm sạch Unicode & LaTeX**: Giữ nguyên công thức toán LaTeX chuẩn `$...$`, bảng biểu và dữ liệu tiếng Việt UTF-8.

### 2. AI Problem Engine & Phân chia Subtasks tự động
- **Phân bổ Subtasks & Điểm số**: Tự động chia các tầng dữ liệu theo điểm (mặc định tỉ lệ `30:30:40` hoặc đọc trực tiếp từ yêu cầu đề bài), sinh testcases tương ứng cho từng subtask ($N \le 10$, $N \le 20$, Max constraints $N = 10^5, 2 \times 10^5, 10^{18}$).
- **Lời giải chuẩn C++20 tối ưu**: Tự động áp dụng Fast I/O, kiểu dữ liệu lớn (`long long`, `__int128`), thuật toán tối ưu (DP, Segment Tree, Math, Bitwise,...), tránh tràn số và TLE.
- **Generator C++ (`gen.cpp`) với `testlib.h`**: Nhận tham số dòng lệnh theo subtask, seed ngẫu nhiên và kiểu test (min, max, random, stress, extreme, corner cases).
- **Chuẩn hóa Checker**: Mặc định sử dụng **`std::wcmp.cpp`** hoặc **`std::lcmp.cpp`** để so khớp kết quả dòng/từ, không bị lỗi `PRESENTATION_ERROR` khi xử lý bài có nhiều test cases ($t$ queries).

### 3. Local Verification Engine (Kiểm định cục bộ trước khi Upload)
- Tự động gọi trình biên dịch `g++ -O2 -std=c++20` để biên dịch `solution.cpp`.
- Tự động gọi `g++ -O2 -std=c++17` cùng thư viện `testlib.h` để biên dịch `generator.cpp`.
- Thực thi generator cục bộ để sinh toàn bộ test input cho từng subtask, sau đó chạy `solution.exe` sinh output chuẩn.
- **Cam kết chất lượng**: Loại bỏ 100% test trùng lặp, đảm bảo 0 lỗi biên dịch, 0 runtime crash, 0 TLE trước khi đẩy lên Polygon.

### 4. Quy trình tự động hóa 10 bước chuẩn Polygon (10-Step Automation Pipeline)
Hệ thống tự động thực thi tuần tự 10 bước qua Polygon REST API:
1. **Bước 1 (Get/Create Problem)**: Kiểm tra bài tập trên Polygon theo short-name; nếu chưa có thì tự động tạo mới.
2. **Bước 2 (Statement & Limits)**: Cấu hình giới hạn thời gian (Time Limit ms), bộ nhớ (Memory Limit MB), nạp đề bài định dạng LaTeX Polygon kèm mô tả subtask.
3. **Bước 3 (Checker)**: Thiết lập Checker chuẩn (`std::wcmp.cpp` / `std::lcmp.cpp`) hoặc nạp `check.cpp` tùy chỉnh.
4. **Bước 4 (Generator Files)**: Nạp mã nguồn `gen.cpp` (C++17) và thư viện `testlib.h` vào mục Files của Polygon.
5. **Bước 5 (Solution MA)**: Nạp lời giải `solution.cpp` với Tag `MA` (Main Correct Solution).
6. **Bước 6 (Subtask Tests & Script)**:
   - Tự động gọi `enableGroups` và `enablePoints` trên testset `tests`.
   - Nạp toàn bộ testcases phân tầng trực tiếp vào Tab Tests với nhãn nhóm (`group`) và điểm số (`points`).
   - Ghi Script sinh test vào Tab Tests -> Script để lưu trữ và tái lập.
7. **Bước 7 (Commit Working Copy)**: Tự động commit các thay đổi trên Polygon trước khi đóng gói.
8. **Bước 8 (Full Package & Auto-Repair)**: Kích hoạt build Full Package có xác minh (verification). Nếu gặp lỗi, kích hoạt vòng lặp **Auto-Repair** để AI phân tích lỗi và vá code tự động.
9. **Bước 9 (Manage Access)**: Phân quyền `WRITE` cho người dùng `codeforces` qua API `problem.setAccess` để sẵn sàng import vào Codeforces Mashup / Gym.
10. **Bước 10 (Export Link & Excel)**: Trả về link bài hoàn chỉnh (`cf_import_url`: `https://polygon.codeforces.com/p.../owner/short_name`) và tự động ghi vào `problems_summary.xlsx`.

### 5. Multi-Key Rotation & Khả năng chịu lỗi cao
- **Cơ chế xoay vòng Key Gemini**: Tự động chuyển sang danh sách `gemini_backup_keys` khi key chính chạm giới hạn quota hoặc rate-limit (HTTP 429).
- **Polygon Resilient Client**: Tự động retry với exponential backoff khi Polygon API trả về mã lỗi 502/503/504 hoặc Cloudflare challenge.
- **Cache cục bộ**: Lưu cache dữ liệu đề bài và code đã kiểm định trong thư mục `cache/`, giúp tiếp tục tiến trình ngay lập tức mà không cần gọi lại AI.

---

## 🛠️ Hướng Dẫn Cài Đặt

### 1. Yêu cầu hệ thống
- **Python**: Phiên bản 3.10 trở lên.
- **Trình biên dịch C++**: MinGW-w64 (Windows) hoặc GCC (Linux/macOS) hỗ trợ chuẩn C++20 và C++17 trên PATH (`g++ --version`).
- **Thư viện testlib.h**: Đặt file [`testlib.h`](https://github.com/MikeMirzayanov/testlib/blob/master/testlib.h) tại thư mục gốc của dự án.

### 2. Cài đặt môi trường ảo & Thư viện
```bash
# Tạo môi trường ảo
python -m venv .venv

# Kích hoạt môi trường và cài đặt dependencies
# Trên Windows:
.\.venv\Scripts\pip install -r requirements.txt

# Trên Linux/macOS:
./.venv/bin/pip install -r requirements.txt
```

### 3. Cấu hình API (`config/config.yaml`)
Chỉnh sửa file `config/config.yaml` để khai báo API key của bạn:
```yaml
polygon:
  api_key: "YOUR_POLYGON_API_KEY"
  api_secret: "YOUR_POLYGON_API_SECRET"
  api_url: "https://polygon.codeforces.com/api/"

ai:
  provider: "gemini"
  gemini_api_key: "YOUR_PRIMARY_GEMINI_KEY"
  gemini_backup_keys:
    # Danh sách key dự phòng tự động chuyển khi gặp giới hạn hạn ngạch
    # - "AIzaSy..."
  model_name: "gemini-3.6-flash"

generation:
  num_tests: 30
  enable_subtasks: true
  default_subtask_split: "30:30:40"
  include_samples_in_statements: true
  default_time_limit_ms: 1000
  default_memory_limit_mb: 256
  auto_grant_access_to_codeforces: true
  auto_package: true

export:
  excel_file_path: "problems_summary.xlsx"
```

---

## 💻 Hướng Dẫn Sử Dụng

### 1. Chạy trực tiếp một bài tập bằng đường link
```bash
# Nạp bài từ VNOJ (hỗ trợ cả bài có đề PDF như fc020_accepted):
.\.venv\Scripts\python.exe run.py -u "https://oj.vnoi.info/problem/fc020_accepted" -n 15

# Nạp bài từ Codeforces:
.\.venv\Scripts\python.exe run.py -u "https://codeforces.com/problemset/problem/1850/A" -n 20

# Nạp bài từ AtCoder / CSES / MarisaOJ:
.\.venv\Scripts\python.exe run.py -u "https://cses.fi/problemset/task/1068"
```

### 2. Menu tương tác CLI & Dashboard
```bash
# Khởi chạy menu điều khiển qua file batch:
run.bat

# Hoặc khởi chạy qua Python CLI:
.\.venv\Scripts\python.exe run.py
```

### 3. Xử lý hàng loạt từ file danh sách (`batch mode`)
Tạo file `urls.txt` chứa mỗi dòng 1 link bài tập:
```text
https://codeforces.com/problemset/problem/4/A
https://codeforces.com/problemset/problem/71/A
https://oj.vnoi.info/problem/fc020_accepted
```
Chạy lệnh batch:
```bash
.\.venv\Scripts\python.exe run.py --batch urls.txt -n 20
```

### 4. Kiểm tra kết nối API Polygon & Gemini
```bash
.\.venv\Scripts\python.exe run.py --test
```

### 5. Xuất danh sách bài tập hiện có trên Polygon ra Excel
```bash
.\.venv\Scripts\python.exe run.py --list
```

---

## 📂 Cấu Trúc Thư Mục Dự Án

```
cf-polygon-auto-uploader/
├── config/
│   ├── config.yaml              # Cấu hình API Keys, model AI và tham số sinh test
│   └── settings.py              # Đọc và ánh xạ dữ liệu config thành Dataclass
├── core/
│   ├── ai_engine/
│   │   ├── llm_client.py        # Gemini Client hỗ trợ pool xoay vòng API keys
│   │   ├── pipeline.py          # AI Pipeline: bóc tách đề bài, sinh code & test
│   │   ├── prompts.py           # Bộ prompt tối ưu cho C++20, testlib và subtasks
│   │   └── local_verifier.py    # Kiểm định biên dịch C++ và sinh test cục bộ
│   ├── polygon/
│   │   ├── client.py            # Client tương tác REST API Polygon (retry, backoff)
│   │   └── automation.py        # Điều phối 10 bước tự động hóa Polygon
│   ├── scraper/
│   │   ├── __init__.py          # Entrypoint điều hướng scraper phù hợp theo URL
│   │   ├── base.py              # ScrapedProblem dataclass & BaseScraper interface
│   │   ├── codeforces.py        # Scraper bài tập Codeforces
│   │   ├── atcoder.py           # Scraper bài tập AtCoder
│   │   ├── cses.py              # Scraper bài tập CSES
│   │   ├── vnoj.py              # Scraper VNOJ (nhận diện đề HTML & đề PDF binary)
│   │   ├── marisaoj.py          # Scraper MarisaOJ (vượt Cloudflare)
│   │   └── generic.py           # Generic Scraper thông minh cho các trang khác
│   └── models.py                # Định nghĩa cấu trúc dữ liệu toàn hệ thống
├── ui/
│   ├── cli.py                   # Giao diện dòng lệnh phong phú với Rich library
│   └── dashboard/               # Giao diện Web Dashboard (Flask)
├── testlib.h                    # Thư viện sinh test chuẩn Codeforces
├── run.py                       # Điểm vào chính của chương trình
├── run.bat                      # Phím tắt khởi chạy nhanh trên Windows
├── requirements.txt             # Danh mục thư viện Python yêu cầu
├── problems_summary.xlsx        # Bảng tổng hợp tiến độ và link Import Codeforces
└── cache/                       # Bộ nhớ đệm lưu trữ kết quả phân tích & sinh test
```

---

## 📊 Minh Họa Báo Cáo Xuất Ra Excel (`problems_summary.xlsx`)

Sau mỗi lần nạp bài thành công, hệ thống tự động cập nhật bảng tổng hợp với đầy đủ thông tin:

| STT | Tên Bài | Polygon ID | Link Nhập Codeforces (Import URL) | Số Test | Subtasks & Điểm | Trạng Thái Package | Sẵn Sàng Import |
| :-: | :--- | :-: | :--- | :-: | :--- | :-: | :-: |
| 1 | `watermelon` | `577334` | `.../p577334/luatgay/watermelon` | 20 | Subtask 1 (30đ), Subtask 2 (30đ), Subtask 3 (40đ) | `READY` | **YES** |
| 2 | `way-too-long-words` | `577349` | `.../p577349/luatgay/way-too-long-words` | 20 | Subtask 1 (30đ), Subtask 2 (30đ), Subtask 3 (40đ) | `READY` | **YES** |
| 3 | `accepted` (VNOJ PDF) | `606912` | `.../p606912/luatgay/accepted` | 15 | Subtask 1 (30đ), Subtask 2 (30đ), Subtask 3 (40đ) | `READY` | **YES** |
| 4 | `to-my-critics` | `606645` | `.../p606645/luatgay/to-my-critics` | 15 | Subtask 1 (30đ), Subtask 2 (30đ), Subtask 3 (40đ) | `READY` | **YES** |

---

## 📜 Giấy Phép (License)

Dự án được phân phối dưới giấy phép **MIT License**. Mọi đóng góp và cải tiến đều được hoan nghênh!
