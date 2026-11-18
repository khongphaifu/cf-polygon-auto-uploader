import argparse
import sys
import io
import os
from pathlib import Path

# Force UTF-8 encoding on Windows console
if sys.platform == "win32":
    os.environ["PYTHONIOENCODING"] = "utf-8"
    try:
        if sys.stdout.encoding.lower() != "utf-8":
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        if sys.stderr.encoding.lower() != "utf-8":
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from ui.cli import AutoUploaderCLI


def main():
    parser = argparse.ArgumentParser(
        description="Codeforces & Polygon Auto Uploader: Tự động hóa tạo bài tập lên Polygon Codeforces từ đường link."
    )
    parser.add_argument(
        "--url", "-u",
        type=str,
        help="Đường link bài tập cần cào và tải lên Polygon (e.g. LeetCode, AtCoder, Codeforces, VNOJ, CSES).",
    )
    parser.add_argument(
        "--num-tests", "-n",
        type=int,
        default=None,
        help="Số lượng test cần sinh (mặc định theo cấu hình: 30 test, tự động chia theo subtask).",
    )
    parser.add_argument(
        "--batch", "-b",
        type=str,
        help="Đường dẫn file txt chứa danh sách link bài tập (mỗi dòng một link).",
    )
    parser.add_argument(
        "--test", "-t",
        action="store_true",
        help="Kiểm tra kết nối Polygon API và Gemini API.",
    )
    parser.add_argument(
        "--list", "-l",
        action="store_true",
        help="Liệt kê danh sách bài trên Polygon và xuất ra file Excel.",
    )
    parser.add_argument(
        "--config", "-c",
        type=str,
        default=None,
        help="Đường dẫn file config.yaml tùy chỉnh.",
    )
    parser.add_argument(
        "--web", "-w",
        action="store_true",
        help="Khởi chạy giao diện Web Dashboard (http://127.0.0.1:8080).",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8080,
        help="Cổng chạy Web Dashboard (mặc định: 8080).",
    )
    parser.add_argument(
        "--file", "-f",
        type=str,
        default=None,
        help="Đường dẫn tệp đề bài cục bộ (.pdf, .png, .jpg, .txt, .md).",
    )
    parser.add_argument(
        "--lang",
        type=str,
        choices=["vi", "en", "both", "auto"],
        default=None,
        help="Ngôn ngữ đề bài xuất lên Polygon: vi, en, both (song ngữ), auto.",
    )
    parser.add_argument(
        "--file-io",
        action="store_true",
        default=None,
        help="Bật chế độ đọc/ghi qua file <ten_bai>.inp / <ten_bai>.out.",
    )
    parser.add_argument(
        "--points-policy",
        type=str,
        choices=["EACH_TEST", "COMPLETE_GROUP"],
        default=None,
        help="Cách tính điểm Subtask: EACH_TEST (chia đều từng test) hoặc COMPLETE_GROUP.",
    )
    parser.add_argument(
        "--no-cache",
        action="store_true",
        help="Bỏ qua bộ nhớ đệm cục bộ, phân tích và sinh lại toàn bộ từ đầu.",
    )
    parser.add_argument(
        "--full-package",
        action="store_true",
        default=None,
        help="Build Full Package (Standard + Windows + Linux) thay vì mặc định chỉ Standard.",
    )
    parser.add_argument(
        "--no-verify",
        action="store_true",
        default=None,
        help="Tắt bước verify trên server Polygon khi build package để tạo gói siêu nhanh.",
    )

    args = parser.parse_args()
    if args.web:
        from ui.web_app import start_web_dashboard
        start_web_dashboard(port=args.port, open_browser=True)
        return

    config_path = Path(args.config) if args.config else None
    cli = AutoUploaderCLI(config_path=config_path)

    eff_full_pkg = True if args.full_package else None
    eff_verify_pkg = False if args.no_verify else None

    if args.test:
        cli.test_connections()
    elif args.list:
        cli.view_polygon_problems()
    elif args.file or args.url:
        target = args.file or args.url
        cli.process_single_url(
            target,
            num_tests=args.num_tests,
            lang_mode=args.lang,
            use_file_io=True if args.file_io else None,
            ignore_cache=args.no_cache,
            points_policy=args.points_policy,
            full_package=eff_full_pkg,
            verify_package=eff_verify_pkg,
        )
    elif args.batch:
        batch_file = Path(args.batch)
        if not batch_file.exists():
            print(f"Error: File '{args.batch}' not found.")
            sys.exit(1)
        with open(batch_file, "r", encoding="utf-8") as f:
            urls = [line.strip() for line in f if line.strip() and not line.strip().startswith("#")]
        print(f"Bắt đầu xử lý {len(urls)} URLs từ {args.batch}...")
        results = []
        for u in urls:
            rec = cli.process_single_url(
                u,
                num_tests=args.num_tests,
                lang_mode=args.lang,
                use_file_io=True if args.file_io else None,
                ignore_cache=args.no_cache,
                points_policy=args.points_policy,
                full_package=eff_full_pkg,
                verify_package=eff_verify_pkg,
            )
            if rec:
                results.append(rec)
        cli.display_summary_table(results)
    else:
        # Interactive mode
        cli.run()


if __name__ == "__main__":
    main()
