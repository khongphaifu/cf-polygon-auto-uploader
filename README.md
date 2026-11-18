# 🚀 Codeforces & Polygon Auto Uploader (v2.0)

Hệ thống tự động hóa toàn diện quy trình lấy đề bài lập trình thi đấu (Competitive Programming) từ bất kỳ nguồn nào (**Codeforces, AtCoder, CSES, VNOJ HTML/PDF, MarisaOJ, LeetCode, hoặc tệp PDF/Ảnh/TXT cục bộ**), sử dụng AI Gemini đa phương thức để bóc tách đề bài song ngữ **Tiếng Việt + Tiếng Anh**, chuẩn hóa **LaTeX & bảng Scoring chuẩn Polygon**, tự viết lời giải **C++23** + **Generator & Validator (`testlib.h`)**, kiểm định **Sample Tests & Tự sửa lỗi cục bộ (Local Self-Healing)** trước khi nạp lên **Polygon Codeforces**, chia nhóm test `vidu` + `sub1..sub3` **tổng 100 điểm**, build **Full Package** kèm **Auto-Repair**, cấp quyền `WRITE` cho `codeforces` và xuất báo cáo ra **Excel (`problems_summary.xlsx`)**.

---

## 🌟 Tính Năng Mới Nổi Bật (Phiên bản v2.0)

### 1. Statement Song Ngữ (VI / EN / Song ngữ) & Bảng `Scoring` Chuẩn Polygon
- **Chuẩn hóa từ các bài mẫu thực tế**: Học trực tiếp phong cách trình bày LaTeX Polygon (`\textbf{Yêu cầu:}`, phần chú thích chân trang `\_\_\_\_\_\_\_\_\_\_`, phần giải thích ví dụ `\begin{itemize}...\end{itemize}`) và tự động tách bảng Subtasks ra ô **`Scoring`** riêng biệt của Polygon:
  ```latex
  \begin{center}
  \begin{tabular}{|c|c|c|}
  \hline
  \textbf{Subtask} & \textbf{Điểm} & \textbf{Giới hạn} \\
  \hline
  1 & 30 & $N \le 10$ \\
  ...
  ```
- **Chế độ ngôn ngữ linh hoạt (`--lang`)**: Hỗ trợ `both` (lưu đồng thời cả 2 bản `vietnamese` và `english` trên Polygon), `vi` (chỉ Tiếng Việt), `en` (chỉ Tiếng Anh), hoặc `auto`.
- **Làm sạch & phục hồi LaTeX tự động**: Tự động loại bỏ ký tự `#`, `**`, thoát ký tự `%` thành `\%`, cân bằng khối `\begin{...}/\end{...}`, và khôi phục các lệnh TeX như `\textbf`, `\begin`, `\times` nếu bị thoát nhầm khi parse JSON.

### 2. Kiểm Định Cục Bộ (`LocalVerifier`) & Tự Sửa Lỗi Sớm (Local Self-Healing)
- **Kiểm tra Sample Tests bắt buộc**: Biên dịch `solution.cpp` (`g++ -O2 -std=c++20`) và chạy đối chiếu trực tiếp với toàn bộ **Sample Input/Output** của đề bài.
- **Vòng lặp Self-Healing tại máy (tối đa 3 lần)**: Nếu phát hiện lỗi biên dịch, TLE/RE hoặc sai Sample Test (`Wrong Answer`), hệ thống lập tức gửi log lỗi cho AI sửa lại code ngay tại máy trước khi đẩy lên Polygon.
- **Validator (`testlib.h`) tích hợp**: Sinh và biên dịch `validator.cpp` kiểm tra ràng buộc input sinh ra (có cơ chế fallback an toàn để không chặn pipeline nếu validator quá chặt).

### 3. Chia Nhóm `vidu` + `sub1..sub3` & Tính Điểm Chuẩn Tổng 100 Điểm
- **Tên nhóm chuẩn**: Test ví dụ đặt vào nhóm `vidu` (`0.0` điểm, `feedbackPolicy="COMPLETE"`), các subtask đặt vào `sub1`, `sub2`, `sub3`,... (`feedbackPolicy="POINTS"`).
- **Tổng điểm chuẩn 100.0đ**: Tự động phân bổ điểm từng test (`subtask_points / test_count`) sao cho tổng điểm toàn bài trên Polygon luôn chính xác **100.0 điểm**, hỗ trợ cả `EACH_TEST` và `COMPLETE_GROUP`.
- **Compiler hiện đại**: Nạp `solution.cpp`, `gen.cpp`, `validator.cpp` với chuẩn `cpp.gcc14-64-msys2-g++23` (kèm fallback `cpp.g++17`).
- **Tùy chọn File I/O (`--file-io`)**: Mặc định dùng `stdin/stdout`, hỗ trợ bật nhanh chế độ đọc/ghi file `<ten_bai>.inp` / `<ten_bai>.out`.

### 4. Scraper Đa Định Dạng & Vượt Cloudflare
- Bảo toàn số mũ (`<sup>5</sup>` $\rightarrow$ `^{5}`), chỉ số dưới (`<sub>i</sub>` $\rightarrow$ `_{i}`) và khối `<pre>` khi bóc tách HTML.
- Tự động nhận diện và tải đề bài **PDF nhúng trên VNOJ**, cũng như hỗ trợ nạp trực tiếp **tệp PDF / Ảnh (PNG, JPG, WebP) / TXT cục bộ** (`--file`).
- Tích hợp `cloudscraper` fallback trực tiếp vào `BaseScraper`.

### 5. Hợp Nhất CLI & Web Dashboard (`--web`)
- CLI và Web Dashboard dùng chung luồng thực thi 10 bước, bộ nhớ đệm `cache/` (`v2`) và hỗ trợ tải file PDF/Ảnh + chọn ngôn ngữ ngay trên giao diện Web (`http://127.0.0.1:8080`).

---

## 🛠️ Hướng Dẫn Cài Đặt

### 1. Yêu cầu hệ thống
- **Python**: 3.10 trở lên.
- **GCC / MinGW-w64**: `g++` trên PATH hỗ trợ `-std=c++20` / `-std=c++17`.
- **testlib.h**: Đặt file [`testlib.h`](https://github.com/MikeMirzayanov/testlib/blob/master/testlib.h) tại thư mục gốc của dự án.

### 2. Cài đặt dependencies
```bash
python -m venv .venv

# Windows:
.\.venv\Scripts\pip install -r requirements.txt

# Linux/macOS:
./.venv/bin/pip install -r requirements.txt
```

### 3. Cấu hình API (`config/config.yaml`)
Sao chép từ `config/config.example.yaml` sang `config/config.yaml` và điền thông tin:
```yaml
polygon:
  api_key: "YOUR_POLYGON_API_KEY"
  api_secret: "YOUR_POLYGON_API_SECRET"
  api_url: "https://polygon.codeforces.com/api/"

ai:
  provider: "gemini"
  gemini_api_key: "YOUR_PRIMARY_GEMINI_KEY"
  gemini_backup_keys:
    # - "AIzaSy..."
  model_name: "gemini-3.1-flash-lite"

generation:
  num_tests: 30
  enable_subtasks: true
  default_subtask_split: "30:30:40"
  statement_lang: "both"        # "vi", "en", "both", hoặc "auto"
  points_policy: "EACH_TEST"    # "EACH_TEST" hoặc "COMPLETE_GROUP"
  use_file_io: false            # true để dùng <ten_bai>.inp/.out
  enable_validator: true
  include_samples_in_statements: true
  default_time_limit_ms: 1000
  default_memory_limit_mb: 256
  auto_grant_access_to_codeforces: true
  auto_package: true

export:
  excel_file_path: "problems_summary.xlsx"
```

---

## 💻 Cách Sử Dụng

### 1. Chạy từ dòng lệnh (CLI)
```bash
# Chạy 1 đường link VNOJ (kể cả đề PDF) với Statement song ngữ VI + EN:
.\.venv\Scripts\python.exe run.py -u "https://oj.vnoi.info/problem/fc020_accepted" -n 15 --lang both

# Nạp bài từ file PDF hoặc ảnh đề bài cục bộ:
.\.venv\Scripts\python.exe run.py --file "D:\DeThi\bai1.pdf" -n 20 --lang vi --file-io

# Chạy mới hoàn toàn (bỏ qua Cache) và chia điểm theo nhóm COMPLETE_GROUP:
.\.venv\Scripts\python.exe run.py -u "https://codeforces.com/problemset/problem/1850/A" -n 20 --points-policy COMPLETE_GROUP --no-cache

# Xử lý hàng loạt từ file danh sách link:
.\.venv\Scripts\python.exe run.py --batch urls.txt -n 20 --lang both

# Kiểm tra nhanh kết nối Polygon API & Gemini API:
.\.venv\Scripts\python.exe run.py --test

# Liệt kê danh sách bài trên Polygon và xuất ra Excel:
.\.venv\Scripts\python.exe run.py --list
```

### 2. Mở Web Dashboard (Giao diện trực quan)
```bash
.\.venv\Scripts\python.exe run.py --web --port 8080
```
Sau đó truy cập `http://127.0.0.1:8080` để dán link hoặc tải trực tiếp tệp PDF/Ảnh đề bài, chọn ngôn ngữ (`Song ngữ` / `Tiếng Việt` / `Tiếng Anh`), theo dõi log trực tiếp 10 bước và sao chép link Import Codeforces.

### 3. Chạy Menu Tương Tác
```bash
# Windows:
run.bat

# Hoặc trực tiếp Python:
.\.venv\Scripts\python.exe run.py
```

---

## 📂 Cấu Trúc Dự Án

```
cf-polygon-auto-uploader/
├── config/
│   ├── config.yaml              # API keys & cấu hình thực tế (ignored trong git)
│   ├── config.example.yaml      # File cấu hình mẫu
│   └── settings.py              # Load cấu hình thành Dataclass
├── core/
│   ├── ai_engine/
│   │   ├── llm_client.py        # Gemini API Client (multi-key + fast failover)
│   │   ├── pipeline.py          # Bóc tách đề song ngữ, chuẩn LaTeX, local self-healing
│   │   ├── prompts.py           # Prompt học chuẩn Polygon (tqt/nak/lit) + Validator
│   │   └── local_verifier.py    # Biên dịch g++, kiểm Sample Tests, chạy Validator & chia 100đ
│   ├── exporter/
│   │   └── excel_exporter.py    # Xuất báo cáo & hyperlink ra problems_summary.xlsx
│   ├── polygon/
│   │   ├── client.py            # Polygon REST API client (saveStatement+scoring, saveTestGroup...)
│   │   └── automation.py        # Điều phối 10 bước + run_upload_pipeline dùng chung
│   ├── scraper/
│   │   ├── __init__.py          # Điều phối URL + File cục bộ (.pdf/.png/.jpg/.txt)
│   │   ├── base.py              # BaseScraper (clean_html_preserve_math + cloudscraper)
│   │   ├── codeforces.py
│   │   ├── atcoder.py
│   │   ├── cses.py
│   │   ├── vnoj.py              # VNOJ (HTML + PDF nhúng)
│   │   ├── marisaoj.py
│   │   ├── leetcode.py
│   │   └── generic.py
│   ├── models.py                # ProblemData, GeneratedCode, PolygonProblemRecord...
│   └── notifier.py              # Discord / Telegram webhook notifications
├── ui/
│   ├── cli.py                   # Interactive Rich CLI Menu
│   └── web_app.py               # Live Web Dashboard (URL + Upload PDF/Ảnh + Ngôn ngữ)
├── run.py                       # Entrypoint CLI & Web
├── run.bat                      # Windows quick launcher
├── requirements.txt
└── problems_summary.xlsx        # Bảng tổng hợp các bài đã nạp
```

---

## 📄 Giấy Phép

Phát hành theo giấy phép **MIT License**.
