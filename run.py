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

    args = parser.parse_args()
    config_path = Path(args.config) if args.config else None
    cli = AutoUploaderCLI(config_path=config_path)

    if args.test:
        cli.test_connections()
    elif args.list:
        cli.view_polygon_problems()
    elif args.url:
        cli.process_single_url(args.url)
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
            rec = cli.process_single_url(u)
            if rec:
                results.append(rec)
        cli.display_summary_table(results)
    else:
        # Interactive mode
        cli.run()


if __name__ == "__main__":
    main()
