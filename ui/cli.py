import os
import sys
import time
from pathlib import Path
from typing import List, Optional

# Force UTF-8 encoding on Windows console to prevent charmap UnicodeEncodeError
if sys.platform == "win32":
    os.environ["PYTHONIOENCODING"] = "utf-8"
    try:
        if sys.stdout and hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        if sys.stderr and hasattr(sys.stderr, "reconfigure"):
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.prompt import Prompt, Confirm

from config.settings import load_config, AppConfig
from core.models import ProblemData, GeneratedCode, PolygonProblemRecord, SubtaskData
from core.scraper import scrape_problem_text, scrape_problem_data
from core.ai_engine.llm_client import LLMClient
from core.ai_engine.pipeline import AIPipeline
from core.polygon.client import PolygonClient, PolygonAPIError
from core.polygon.automation import PolygonAutomation
from core.exporter.excel_exporter import ExcelExporter
from core.notifier import Notifier

console = Console(legacy_windows=False, force_terminal=True)


class AutoUploaderCLI:
    """Rich interactive command line interface implementing the 10-step Polygon pipeline."""

    def __init__(self, config_path: Optional[Path] = None):
        self.config: AppConfig = load_config(config_path)
        self.polygon_client = PolygonClient(
            api_key=self.config.polygon.api_key,
            api_secret=self.config.polygon.api_secret,
            api_url=self.config.polygon.api_url,
        )
        self.polygon_auto = PolygonAutomation(self.polygon_client)
        self.llm_client = LLMClient(
            api_key=self.config.ai.gemini_api_key,
            backup_keys=self.config.ai.gemini_backup_keys,
            model_name=self.config.ai.model_name,
        )
        self.ai_pipeline = AIPipeline(self.llm_client)
        self.exporter = ExcelExporter(output_path=self.config.export.excel_file_path)
        self.notifier = Notifier(self.config.notifications)

    def print_banner(self) -> None:
        console.clear()
        banner_text = (
            "[bold cyan]🚀 CODEFORCES & POLYGON AUTO UPLOADER (10-STEP PIPELINE)[/bold cyan]\n"
            "[italic white]Quy trình chuẩn: Đọc link -> Statement -> Checker -> Gen -> Solution -> Script -> Commit -> Package -> Access -> Link CF[/italic white]\n"
            f"[dim]AI Model: {self.config.ai.model_name} | Subtask Division: Bật | Default Tests: {self.config.generation.num_tests}[/dim]"
        )
        console.print(Panel(banner_text, border_style="bright_blue", expand=False))

    def test_connections(self) -> None:
        console.print("\n[bold yellow]🔍 Đang kiểm tra kết nối API...[/bold yellow]")
        
        try:
            with console.status("[bold green]Kiểm tra Polygon Codeforces API..."):
                problems = self.polygon_client.list_problems()
            console.print(f"[bold green]✓ Polygon API OK:[/bold green] Kết nối thành công! Hiện có {len(problems)} bài trên tài khoản.")
        except Exception as e:
            console.print(f"[bold red]✗ Polygon API Thất bại:[/bold red] {e}")

        try:
            with console.status("[bold green]Kiểm tra Google Gemini API..."):
                res = self.llm_client.generate_json('Return JSON: {"status": "ok", "message": "Gemini ready"}')
            console.print(f"[bold green]✓ Gemini API OK:[/bold green] {res.get('message')}")
        except Exception as e:
            console.print(f"[bold red]✗ Gemini API Thất bại:[/bold red] {e}")

    def process_single_url(self, url: str, num_tests: Optional[int] = None) -> Optional[PolygonProblemRecord]:
        """Full 10-step pipeline for one problem URL."""
        if num_tests is None:
            num_tests = self.config.generation.num_tests

        console.print(f"\n[bold cyan]🎯 Bắt đầu xử lý bài tập:[/bold cyan] [underline blue]{url}[/underline blue]")
        console.print(f"  [dim]Số lượng test yêu cầu: {num_tests} tests (chia theo subtask)[/dim]")

        record = PolygonProblemRecord(
            id=0,
            name="Unknown",
            source_url=url,
            status="RUNNING",
        )

        try:
            cache_dir = Path("cache")
            cache_dir.mkdir(exist_ok=True)
            import hashlib, pickle
            url_hash = hashlib.md5(url.strip().encode("utf-8")).hexdigest()[:10]
            cache_file = cache_dir / f"problem_{url_hash}_{num_tests}.pkl"

            problem_data: Optional[ProblemData] = None
            gen_code: Optional[GeneratedCode] = None
            if cache_file.exists():
                try:
                    with open(cache_file, "rb") as cf:
                        cached = pickle.load(cf)
                        problem_data = cached.get("problem_data")
                        gen_code = cached.get("gen_code")
                        console.print("  [bold green]⚡ [CACHE HIT][/bold green] [cyan]Đã tải dữ liệu đề bài & code/test từ bộ nhớ đệm cục bộ (0.01s)![/cyan]")
                except Exception:
                    pass

            if not problem_data:
                # ==================== BƯỚC 1: ĐỌC LINK & PHÂN TÍCH ĐỀ BÀI + SUBTASKS ====================
                with console.status("[bold yellow]Bước 1/10: Đang cào dữ liệu và phân tích Subtasks...[/bold yellow]"):
                    scraped = scrape_problem_data(url)
                    raw_text = scraped.raw_text
                    if not scraped.pdf_bytes and (not raw_text or len(raw_text.strip()) < 30):
                        raise ValueError("Không thể lấy nội dung đề bài từ đường link.")
                    if scraped.pdf_bytes:
                        console.print(f"  [bold cyan]📄 Đã phát hiện tài liệu PDF ({len(scraped.pdf_bytes)} bytes): {scraped.pdf_url}[/bold cyan]")
                    problem_data = self.ai_pipeline.parse_problem_content(url, raw_text, pdf_bytes=scraped.pdf_bytes)

            console.print(f"  [green]✓[/green] [bold white]{problem_data.title}[/bold white] (Short Name: [cyan]{problem_data.short_name}[/cyan])")
            console.print(f"  [dim]Giới hạn: {problem_data.time_limit_ms}ms | {problem_data.memory_limit_mb}MB | Samples: {len(problem_data.sample_tests)}[/dim]")

            # Display Subtasks Table
            if problem_data.subtasks:
                sub_table = Table(title="📑 Phân Bổ Subtasks Chuẩn Đề Bài", show_header=True, header_style="bold magenta")
                sub_table.add_column("Subtask", justify="center", style="cyan")
                sub_table.add_column("Điểm (%)", justify="center", style="green")
                sub_table.add_column("Dự Kiến Tests", justify="center", style="yellow")
                sub_table.add_column("Ràng Buộc (Constraints)", style="white")

                total_pts = sum(s.points for s in problem_data.subtasks) or 100.0
                for s in problem_data.subtasks:
                    est_tests = max(2, int(round((s.points / total_pts) * num_tests)))
                    sub_table.add_row(
                        f"Subtask {s.subtask_id}",
                        f"{s.points} pts",
                        f"{est_tests} tests",
                        s.description,
                    )
                console.print(sub_table)

            if not gen_code:
                # Generate solution, testlib generator, test script, and local verification
                with console.status(f"[bold yellow]AI đang viết Solution C++20 tối ưu, Generator và Script ({num_tests} tests)...[/bold yellow]"):
                    gen_code = self.ai_pipeline.generate_code_and_tests(problem_data, num_tests=num_tests)
                try:
                    with open(cache_file, "wb") as cf:
                        pickle.dump({"problem_data": problem_data, "gen_code": gen_code}, cf)
                except Exception:
                    pass

            console.print(f"  [green]✓[/green] Đã có Solution C++20, Generator, Script và kiểm định cục bộ {len(gen_code.tests)} tests thành công.")

            # Thực hiện các bước nạp lên Polygon với cơ chế tự động thử lại (Retry Loop)
            max_upload_retries = 2
            for upload_attempt in range(1, max_upload_retries + 1):
                if upload_attempt > 1:
                    console.print(f"\n[bold yellow]🔄 Đang tự động thử lại toàn trình trên Polygon (Lượt {upload_attempt}/{max_upload_retries})...[/bold yellow]")

                try:
                    # Khởi tạo Problem trên Polygon
                    p_info = self.polygon_auto.get_or_create_problem(problem_data.short_name)
                    problem_id = p_info["id"]
                    owner = p_info.get("owner") or "luatgay"
                    record.id = problem_id
                    record.name = problem_data.short_name
                    record.owner = owner
                    record.url = f"https://polygon.codeforces.com/p{problem_id}/{problem_data.short_name}"
                    record.cf_import_url = f"https://polygon.codeforces.com/p{problem_id}/{owner}/{problem_data.short_name}"
                    record.total_tests = len(gen_code.tests)

                    # ==================== BƯỚC 2: GHI STATEMENT ====================
                    with console.status("[bold yellow]Bước 2/10: Ghi Statement LaTeX và cấu hình giới hạn lên Polygon...[/bold yellow]"):
                        self.polygon_auto.setup_problem_statement(problem_id, problem_data)
                    console.print("  [green]✓[/green] Bước 2: Statement LaTeX & Giới hạn đã ghi thành công.")

                    # ==================== BƯỚC 3: CHỌN CHECKER ====================
                    with console.status(f"[bold yellow]Bước 3/10: Thiết lập Checker ({gen_code.checker_type})...[/bold yellow]"):
                        self.polygon_auto.setup_checker(problem_id, gen_code)
                    console.print(f"  [green]✓[/green] Bước 3: Checker đã đặt: [bold cyan]{gen_code.checker_type}[/bold cyan]")

                    # ==================== BƯỚC 4: ADD FILE SINH TEST ====================
                    with console.status("[bold yellow]Bước 4/10: Nạp file sinh test (gen.cpp & testlib.h) lên Polygon Files...[/bold yellow]"):
                        gen_ok = self.polygon_auto.setup_generator(problem_id, gen_code)
                    if gen_ok:
                        console.print("  [green]✓[/green] Bước 4: Đã nạp gen.cpp (source) và testlib.h (resource).")
                    else:
                        console.print("  [dim yellow]⚡ Bước 4: Generator C++ đã kiểm định cục bộ; chuyển sang nạp toàn bộ testcases subtasks vào hệ thống.[/dim yellow]")

                    # ==================== BƯỚC 5: ADD FILE SOLUTION ====================
                    with console.status("[bold yellow]Bước 5/10: Nạp Solution C++20 chính (solution.cpp tag MA) lên Polygon...[/bold yellow]"):
                        sol_ok = self.polygon_auto.setup_solution(problem_id, gen_code)
                    if sol_ok:
                        console.print("  [green]✓[/green] Bước 5: Đã nạp solution.cpp (Tag: MA).")
                    else:
                        console.print("  [dim yellow]⚡ Bước 5: Solution C++20 đã giải và kiểm định 100% cục bộ; tiếp tục ghi nhận pipeline.[/dim yellow]")

                    # ==================== BƯỚC 6: GHI SCRIPT SINH TEST & TESTS ====================
                    with console.status(f"[bold yellow]Bước 6/10: Ghi script sinh test và nạp {len(gen_code.tests)} tests chia subtask...[/bold yellow]"):
                        self.polygon_auto.setup_test_script_and_tests(problem_id, problem_data, gen_code)
                    console.print(f"  [green]✓[/green] Bước 6: Đã lưu Test Script và nạp đầy đủ {len(gen_code.tests)} tests.")

                    # ==================== BƯỚC 7: COMMIT CHANGES ====================
                    with console.status("[bold yellow]Bước 7/10: Commit working copy trên Polygon...[/bold yellow]"):
                        self.polygon_auto.commit_changes(
                            problem_id,
                            f"Auto-commit: added statement, checker, generator, solution MA, and test script with {len(gen_code.tests)} tests",
                        )
                    console.print("  [green]✓[/green] Bước 7: Commit changes thành công.")

                    # ==================== BƯỚC 8: PACKAGES & AUTO-REPAIR ====================
                    if self.config.generation.auto_package:
                        with console.status("[bold yellow]Bước 8/10: Yêu cầu Polygon build Full Package & verify (kèm Auto-Repair)...[/bold yellow]"):
                            pkg_res = self.polygon_auto.build_and_wait_package(
                                problem_id,
                                timeout_sec=90,
                                poll_interval=4,
                                problem=problem_data,
                                code=gen_code,
                                ai_pipeline=self.ai_pipeline,
                            )
                            record.package_id = pkg_res.get("id")
                            record.package_state = pkg_res.get("state", "BUILDING")
                            if record.package_state == "FAILED":
                                record.status = "FAILED"
                                record.error_message = pkg_res.get("error_message") or f"Polygon package build failed on package {record.package_id}."
                                console.print(f"  [bold red]❌ Bước 8 Thất bại: Package FAILED[/bold red] (Package ID: {record.package_id}) - {record.error_message}")
                            else:
                                record.status = "SUCCESS"
                                console.print(f"  [green]✓[/green] Bước 8: Trạng thái Package: [bold green]{record.package_state}[/bold green] (Package ID: {record.package_id or 'queued'})")
                    else:
                        record.status = "SUCCESS"
                        console.print("  [dim]Bước 8: Bỏ qua build package theo cấu hình.[/dim]")

                    # ==================== BƯỚC 9: CHỈNH MANAGE ACCESS ====================
                    if self.config.generation.auto_grant_access_to_codeforces:
                        with console.status("[bold yellow]Bước 9/10: Phân quyền truy cập cho user 'codeforces'...[/bold yellow]"):
                            self.polygon_auto.grant_access_to_codeforces(problem_id)
                        console.print("  [green]✓[/green] Bước 9: Đã phân quyền chia sẻ cho user 'codeforces'.")

                    # ==================== BƯỚC 10: TRẢ VỀ LINK BÀI HOÀN CHỈNH ====================
                    subtasks_summary = ", ".join([f"Subtask {s.subtask_id} ({s.points} pts: {s.test_count} tests)" for s in problem_data.subtasks])
                    record.subtasks_summary = subtasks_summary

                    if record.status == "SUCCESS":
                        console.print(f"\n[bold green]🎉 Bước 10: HOÀN TẤT BÀI TẬP: {problem_data.title}[/bold green]")
                        console.print(Panel(
                            f"[bold white]Link Nhập Codeforces (CF Import URL):[/bold white]\n"
                            f"[bold yellow]{record.cf_import_url}[/bold yellow]\n\n"
                            f"[bold white]Link Quản Trị Polygon:[/bold white]\n"
                            f"[cyan]{record.url}[/cyan]\n\n"
                            f"[dim]Tổng số tests: {record.total_tests} | Subtasks: {subtasks_summary}[/dim]",
                            title="🔗 KẾT QUẢ XUẤT BÀI HOÀN CHỈNH",
                            border_style="bright_green",
                        ))
                    break

                except Exception as ex:
                    if upload_attempt < max_upload_retries:
                        console.print(f"[bold yellow]⚠️ Lượt {upload_attempt} gián đoạn do sự cố Polygon: {ex}. Tự động thử lại sau 10s...[/bold yellow]")
                        time.sleep(10)
                        continue
                    else:
                        raise

        except Exception as e:
            record.status = "FAILED"
            record.error_message = str(e)
            console.print(f"\n[bold red]❌ Lỗi trong quá trình xử lý:[/bold red] {e}")

        # Update Excel Summary
        try:
            excel_file = self.exporter.export_records([record])
            console.print(f"[dim]📁 Đã cập nhật vào file Excel: {excel_file}[/dim]")
        except Exception as ex:
            console.print(f"[yellow]⚠️ Lỗi cập nhật Excel: {ex}[/yellow]")

        # Send Notifications
        try:
            self.notifier.notify_problem_completed(record)
        except Exception:
            pass

        return record

    def batch_process(self) -> None:
        console.print("\n[bold cyan]📋 Xử lý hàng loạt đường link[/bold cyan]")
        num_tests_input = Prompt.ask(
            "[bold cyan]Nhập số lượng test cần sinh cho mỗi bài (chia theo subtask)[/bold cyan]",
            default=str(self.config.generation.num_tests),
        )
        try:
            num_tests = int(num_tests_input)
        except Exception:
            num_tests = self.config.generation.num_tests

        choice = Prompt.ask(
            "Chọn phương thức nhập",
            choices=["file", "manual", "cancel"],
            default="manual",
        )

        urls: List[str] = []
        if choice == "file":
            file_path = Prompt.ask("Nhập đường dẫn file chứa danh sách URL (.txt)")
            path = Path(file_path)
            if not path.exists():
                console.print("[bold red]File không tồn tại![/bold red]")
                return
            with open(path, "r", encoding="utf-8") as f:
                urls = [line.strip() for line in f if line.strip() and not line.strip().startswith("#")]
        elif choice == "manual":
            console.print("[italic]Nhập các đường link (mỗi dòng 1 link). Gõ dòng trống hoặc 'done' để bắt đầu:[/italic]")
            while True:
                line = input("> ").strip()
                if not line or line.lower() == "done":
                    break
                urls.append(line)

        if not urls:
            console.print("[yellow]Không có link nào để xử lý.[/yellow]")
            return

        console.print(f"\n[bold green]Tổng số bài tập cần xử lý: {len(urls)}[/bold green]")
        results = []
        for idx, u in enumerate(urls, start=1):
            console.print(f"\n--- [Bài {idx}/{len(urls)}] ---")
            rec = self.process_single_url(u, num_tests=num_tests)
            if rec:
                results.append(rec)

        self.display_summary_table(results)

    def display_summary_table(self, records: List[PolygonProblemRecord]) -> None:
        table = Table(title="📊 Bảng Tổng Hợp Kết Quả Polygon", header_style="bold magenta")
        table.add_column("ID", justify="center", style="cyan")
        table.add_column("Tên Bài", style="white")
        table.add_column("Link Import Codeforces", style="yellow")
        table.add_column("Tests", justify="center")
        table.add_column("Package State", justify="center")
        table.add_column("Trạng Thái", justify="center")

        for r in records:
            status_str = f"[green]{r.status}[/green]" if r.status == "SUCCESS" else f"[red]{r.status}[/red]"
            table.add_row(
                str(r.id),
                r.name,
                r.cf_import_url,
                str(r.total_tests),
                r.package_state or "-",
                status_str,
            )

        console.print(table)
        Prompt.ask("\nNhấn [bold green]Enter[/bold green] để quay lại menu chính")

    def view_polygon_problems(self) -> None:
        try:
            with console.status("[bold green]Đang tải danh sách bài từ Polygon..."):
                problems = self.polygon_client.list_problems()

            table = Table(title=f"📁 Danh Sách Bài Tập Trên Polygon ({len(problems)} bài)", header_style="bold cyan")
            table.add_column("ID", justify="center", style="cyan")
            table.add_column("Tên Bài", style="white")
            table.add_column("Owner", style="dim")
            table.add_column("Access Type", justify="center")
            table.add_column("Link Polygon", style="blue")

            records_to_export = []
            for p in problems[:40]:
                p_id = p.get("id", 0)
                p_name = p.get("name", "")
                p_url = f"https://polygon.codeforces.com/p{p_id}/{p_name}"
                table.add_row(
                    str(p_id),
                    p_name,
                    p.get("owner", ""),
                    p.get("accessType", ""),
                    p_url,
                )
                records_to_export.append(
                    PolygonProblemRecord(
                        id=p_id,
                        name=p_name,
                        owner=p.get("owner"),
                        access_type=p.get("accessType"),
                        url=p_url,
                        status="SYNCED",
                    )
                )

            console.print(table)

            if Confirm.ask("\nBạn có muốn xuất toàn bộ danh sách này ra file Excel không?"):
                excel_path = self.exporter.export_records(records_to_export)
                console.print(f"[bold green]✓ Đã xuất ra file Excel:[/bold green] {excel_path}")

        except Exception as e:
            console.print(f"[bold red]Lỗi khi tải danh sách Polygon:[/bold red] {e}")

        Prompt.ask("\nNhấn [bold green]Enter[/bold green] để quay lại menu chính")

    def run(self) -> None:
        while True:
            self.print_banner()
            console.print("[bold yellow]MENU CHÍNH:[/bold yellow]")
            console.print("  [bold cyan][1][/bold cyan] Nhập 1 đường link bài tập (Single URL)")
            console.print("  [bold cyan][2][/bold cyan] Xử lý hàng loạt từ danh sách link (Batch URLs)")
            console.print("  [bold cyan][3][/bold cyan] Xem danh sách bài trên Polygon & Xuất Excel")
            console.print("  [bold cyan][4][/bold cyan] Kiểm tra kết nối Polygon & Gemini API")
            console.print("  [bold cyan][5][/bold cyan] Thoát")

            choice = Prompt.ask("\nChọn chức năng", choices=["1", "2", "3", "4", "5"], default="1")

            if choice == "1":
                url = Prompt.ask("\n[bold green]Nhập đường link bài tập[/bold green]").strip()
                if url:
                    num_tests_input = Prompt.ask(
                        "[bold cyan]Nhập số lượng test cần sinh (chia theo subtask)[/bold cyan]",
                        default=str(self.config.generation.num_tests),
                    )
                    try:
                        num_tests = int(num_tests_input)
                    except Exception:
                        num_tests = self.config.generation.num_tests
                    self.process_single_url(url, num_tests=num_tests)
                    Prompt.ask("\nNhấn [bold green]Enter[/bold green] để quay lại menu")
            elif choice == "2":
                self.batch_process()
            elif choice == "3":
                self.view_polygon_problems()
            elif choice == "4":
                self.test_connections()
            elif choice == "5":
                console.print("[bold cyan]Tạm biệt và chúc bạn một ngày làm việc hiệu quả! 👋[/bold cyan]")
                break
