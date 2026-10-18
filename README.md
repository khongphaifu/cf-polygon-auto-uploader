# 🚀 Codeforces & Polygon Auto Uploader

Hệ thống tự động hóa toàn diện quy trình lấy đề bài từ bất kỳ đường link nào (Codeforces, AtCoder, CSES, VNOJ, MarisaOJ,...), sử dụng AI Gemini để bóc tách đề bài, sinh lời giải chuẩn C++20 tối ưu, viết **generator C++ (`testlib.h`)** để sinh **20 test cases lớn (max constraints)** qua **Polygon FreeMarker Script**, tự động khởi tạo bài trên **Polygon Codeforces**, nạp code, build Full Package và xuất bảng tổng hợp ra **Excel (.xlsx)**.

---

## 🌟 Tính Năng Chính

1. **Bóc tách đề bài đa nguồn**:
   - Hỗ trợ Codeforces, AtCoder, CSES, VNOJ, **MarisaOJ** (bypass Cloudflare với `cloudscraper`), và Generic Scraper thông minh cho mọi trang web khác.
   - Tự động nhận diện và làm sạch tiếng Việt (Unicode UTF-8).

2. **AI Problem Engine (Google Gemini)**:
   - Phân tích đề bài, nhận diện constraints chính xác.
   - Viết lời giải chuẩn C++20 tối ưu, tránh tràn số (`long long`, `__int128`), fast I/O.
   - Viết **`gen.cpp`** chuẩn `testlib.h` với **20 nhánh test phân tầng** (edge cases → stress → max constraints $N = 10^5, 2 \times 10^5, 10^6, 10^{18}$).
   - Tự động chọn checker phù hợp, mặc định **`std::lcmp.cpp`** (Lines Comparer) để tránh lỗi `PRESENTATION_ERROR`.

3. **Chiến lược sinh Test Cases thông minh**:
   - Sinh **generator C++ (`gen.cpp`)** nhận tham số `int test = atoi(argv[1])` để Polygon tự sinh test lớn.
   - Upload **Polygon FreeMarker Script**:
     ```freemarker
     <#list 1..20 as i>
         gen ${i} > $
     </#list>
     ```
   - Polygon tự động compile và chạy `gen.exe` để sinh test max constraints — **không bị giới hạn token LLM**.
   - Verify cục bộ bằng `g++ -O2 -std=c++20` trước khi upload.

4. **Polygon Automation (Retry & Auto-Repair)**:
   - Tự động tạo bài với short-name chuẩn.
   - Nạp đề bài (LaTeX Markdown) định dạng chuẩn Polygon.
   - Upload `gen.cpp` + `solution.cpp` + Polygon Script + sample tests.
   - Retry tự động 7 lần với exponential backoff khi gặp lỗi 502/503/504/Cloudflare.
   - Build Full Package + **Auto-Repair loop** khi package FAILED (AI tự fix `solution.cpp`).
   - Phân quyền tag `codeforces` để sẵn sàng import vào Mashup/Gym.

5. **Xuất Báo Cáo Excel**:
   - Tự động ghi lại và cập nhật vào `problems_summary.xlsx` với hyperlink và màu sắc trạng thái.

---

## 🛠️ Hướng Dẫn Cài Đặt & Chạy

### 1. Cài đặt môi trường
Yêu cầu Python 3.10+ và g++ (MinGW hoặc GCC).
```bash
python -m venv .venv

# Windows:
.\.venv\Scripts\pip install -r requirements.txt

# Linux/macOS:
./.venv/bin/pip install -r requirements.txt
```

### 2. Đặt `testlib.h` vào thư mục gốc
Tải [`testlib.h`](https://github.com/MikeMirzayanov/testlib/blob/master/testlib.h) và đặt tại `D:\cf-polygon-auto-uploader\testlib.h` để local verifier có thể compile `gen.cpp`.

### 3. Cấu hình API (`config/config.yaml`)
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
  model_name: "gemini-3.6-flash"

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

### Chạy menu tương tác (Web Dashboard hoặc CLI)
```bash
# Windows:
run.bat

# Hoặc trực tiếp Python:
.\.venv\Scripts\python.exe run.py
```

### Chạy trực tiếp 1 đường link
```bash
.\.venv\Scripts\python.exe run.py --url "https://codeforces.com/problemset/problem/1/A"
```

### Chạy hàng loạt từ file danh sách
```bash
.\.venv\Scripts\python.exe run.py --batch urls.txt
```

### Kiểm tra kết nối API Polygon & Gemini
```bash
.\.venv\Scripts\python.exe run.py --test
```

### Xem danh sách bài trên Polygon và xuất ra file Excel
```bash
.\.venv\Scripts\python.exe run.py --list
```

---

## 📂 Cấu Trúc Dự Án

```
cf-polygon-auto-uploader/
├── config/
│   └── config.yaml              # API keys & cấu hình
├── core/
│   ├── ai_engine/
│   │   ├── llm_client.py        # Google Gemini client (multi-key pool)
│   │   ├── pipeline.py          # AI pipeline: phân tích + sinh code
│   │   ├── prompts.py           # Prompt templates (generator 20 nhánh)
│   │   └── local_verifier.py    # Compile & verify gen.cpp + solution.cpp
│   ├── polygon/
│   │   ├── client.py            # Polygon REST API client (retry + backoff)
│   │   └── automation.py        # Upload gen.cpp, script, tests, package build
│   ├── scraper/
│   │   ├── __init__.py          # Danh sách scrapers
│   │   ├── codeforces.py
│   │   ├── atcoder.py
│   │   ├── marisaoj.py          # MarisaOJ (bypass Cloudflare)
│   │   └── ...
│   └── models.py                # Data models (ProblemData, GeneratedCode)
├── ui/
│   ├── cli.py                   # Interactive CLI menu (UTF-8)
│   └── dashboard/               # Web dashboard (Flask)
├── testlib.h                    # Đặt file này vào đây (tải từ GitHub)
├── run.py                       # Entry point
├── run.bat                      # Windows shortcut
├── requirements.txt
└── problems_summary.xlsx        # Báo cáo Excel tự động
```

---

## 🔑 Lưu Ý Quan Trọng

- **Checker**: Luôn dùng `std::lcmp.cpp` (Lines Comparer) mặc định. **Không dùng `std::yesno.cpp`** vì gây `PRESENTATION_ERROR` với bài nhiều test cases ($t$ queries).
- **Generator**: `gen.cpp` phải include `testlib.h`, gọi `registerGen(argc, argv, 1)` và seed `mt19937_64 rng(13022007ULL + test * 999983ULL)`.
- **Polygon Script**: Script FreeMarker `<#list 1..20 as i> gen ${i} > $ </#list>` sẽ được Polygon tự compile và chạy để sinh test lớn.
- **MarisaOJ / trang Việt Nam**: Hỗ trợ đầy đủ Unicode tiếng Việt và bypass Cloudflare.

---

## 📄 License

MIT License
