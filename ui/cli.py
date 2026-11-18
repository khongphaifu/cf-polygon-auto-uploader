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
from core.ai_engine.llm_client import LLMClient
from core.ai_engine.pipeline import AIPipeline
from core.polygon.client import PolygonClient, PolygonAPIError
from core.polygon.automation import PolygonAutomation, run_upload_pipeline
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
        io_label = "<ten_bai>.inp/.out" if self.config.generation.use_file_io else "stdin/stdout"
        banner_text = (
            "[bold cyan]🚀 CODEFORCES & POLYGON AUTO UPLOADER v2.0 (10-STEP PIPELINE)[/bold cyan]\n"
            "[italic white]Quy trình chuẩn: Đọc đề/PDF/Ảnh -> Statement (Scoring) -> Checker/Val -> Gen -> Solution C++23 -> Tests 100đ -> Commit -> Package -> Access -> CF Link[/italic white]\n"
            f"[dim]AI: {self.config.ai.model_name} | Lang: {self.config.generation.statement_lang} | IO: {io_label} | Policy: {self.config.generation.points_policy} | Tests: {self.config.generation.num_tests}[/dim]"
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

    def process_single_url(
        self,
        url: str,
        num_tests: Optional[int] = None,
        lang_mode: Optional[str] = None,
        use_file_io: Optional[bool] = None,
        ignore_cache: bool = False,
        points_policy: Optional[str] = None,
    ) -> Optional[PolygonProblemRecord]:
        """Full 10-step pipeline for one problem URL or local file."""
        eff_num_tests = num_tests if num_tests is not None else self.config.generation.num_tests
        eff_lang = (lang_mode or self.config.generation.statement_lang or "both").strip().lower()

        console.print(f"\n[bold cyan]🎯 Bắt đầu xử lý bài tập:[/bold cyan] [underline blue]{url}[/underline blue]")
        console.print(f"  [dim]Số tests: {eff_num_tests} | Ngôn ngữ Statement: {eff_lang}[/dim]")

        def _on_log(msg: str, step: str, pct: int) -> None:
            if msg.startswith("❌"):
                console.print(f"  [bold red]{msg}[/bold red]")
            elif msg.startswith("⚠️"):
                console.print(f"  [bold yellow]{msg}[/bold yellow]")
            elif msg.startswith("✓") or msg.startswith("⚡"):
                console.print(f"  [green]{msg}[/green]")
            else:
                console.print(f"  [cyan]{msg}[/cyan]")

        def _on_parsed(problem_data: ProblemData, target_tests: int) -> None:
            if problem_data.subtasks:
                sub_table = Table(title="📑 Phân Bổ Subtasks Chuẩn Đề Bài (Tổng 100đ)", show_header=True, header_style="bold magenta")
                sub_table.add_column("Subtask / Group", justify="center", style="cyan")
                sub_table.add_column("Điểm (%)", justify="center", style="green")
                sub_table.add_column("Dự Kiến Tests", justify="center", style="yellow")
                sub_table.add_column("Ràng Buộc (Constraints)", style="white")

                total_pts = sum(s.points for s in problem_data.subtasks) or 100.0
                for s in problem_data.subtasks:
                    est_tests = max(2, int(round((s.points / total_pts) * target_tests)))
                    sub_table.add_row(
                        f"Subtask {s.subtask_id} (sub{s.subtask_id})",
                        f"{s.points} pts",
                        f"{est_tests} tests",
                        s.description,
                    )
                console.print(sub_table)

        record = run_upload_pipeline(
            source=url,
            config=self.config,
            polygon_auto=self.polygon_auto,
            ai_pipeline=self.ai_pipeline,
            exporter=self.exporter,
            notifier=self.notifier,
            num_tests=num_tests,
            lang_mode=lang_mode,
            use_file_io=use_file_io,
            ignore_cache=ignore_cache,
            points_policy=points_policy,
            on_log=_on_log,
            on_problem_parsed=_on_parsed,
        )

        if record.status == "SUCCESS":
            console.print(f"\n[bold green]🎉 Bước 10: HOÀN TẤT BÀI TẬP: {record.name}[/bold green]")
            console.print(Panel(
                f"[bold white]Link Nhập Codeforces (CF Import URL):[/bold white]\n"
                f"[bold yellow]{record.cf_import_url}[/bold yellow]\n\n"
                f"[bold white]Link Quản Trị Polygon:[/bold white]\n"
                f"[cyan]{record.url}[/cyan]\n\n"
                f"[dim]Tổng số tests: {record.total_tests} | Subtasks: {record.subtasks_summary} | Package ID: {record.package_id or 'queued'} ({record.package_state})[/dim]",
                title="🔗 KẾT QUẢ XUẤT BÀI HOÀN CHỈNH",
                border_style="bright_green",
            ))

        excel_path = Path(self.config.export.excel_file_path).resolve()
        console.print(f"[dim]📁 File Excel tổng hợp: {excel_path}[/dim]")
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
            console.print("  [bold cyan][2][/bold cyan] Nạp bài từ File cục bộ (PDF / Ảnh / TXT)")
            console.print("  [bold cyan][3][/bold cyan] Xử lý hàng loạt từ danh sách link (Batch URLs)")
            console.print("  [bold cyan][4][/bold cyan] Xem danh sách bài trên Polygon & Xuất Excel")
            console.print("  [bold cyan][5][/bold cyan] Khởi chạy Web Dashboard (http://127.0.0.1:8080)")
            console.print("  [bold cyan][6][/bold cyan] Cấu hình nhanh (Ngôn ngữ VI/EN/Song ngữ, File I/O, Điểm)")
            console.print("  [bold cyan][7][/bold cyan] Kiểm tra kết nối Polygon & Gemini API")
            console.print("  [bold cyan][8][/bold cyan] Thoát")

            choice = Prompt.ask("\nChọn chức năng", choices=["1", "2", "3", "4", "5", "6", "7", "8"], default="1")

            if choice in ("1", "2"):
                prompt_label = "\n[bold green]Nhập đường link bài tập[/bold green]" if choice == "1" else "\n[bold green]Nhập đường dẫn file cục bộ (.pdf, .png, .jpg, .txt)[/bold green]"
                src = Prompt.ask(prompt_label).strip().strip('"').strip("'")
                if src:
                    num_tests_input = Prompt.ask(
                        "[bold cyan]Nhập số lượng test cần sinh (chia theo subtask)[/bold cyan]",
                        default=str(self.config.generation.num_tests),
                    )
                    try:
                        num_tests = int(num_tests_input)
                    except Exception:
                        num_tests = self.config.generation.num_tests
                    self.process_single_url(src, num_tests=num_tests)
                    Prompt.ask("\nNhấn [bold green]Enter[/bold green] để quay lại menu")
            elif choice == "3":
                self.batch_process()
            elif choice == "4":
                self.view_polygon_problems()
            elif choice == "5":
                from ui.web_app import start_web_dashboard
                console.print("[bold green]Đang mở Web Dashboard tại http://127.0.0.1:8080 ... (Nhấn Ctrl+C để dừng)[/bold green]")
                start_web_dashboard(port=8080, open_browser=True)
            elif choice == "6":
                lang = Prompt.ask("Ngôn ngữ Statement", choices=["both", "vi", "en", "auto"], default=self.config.generation.statement_lang)
                self.config.generation.statement_lang = lang
                fio = Confirm.ask("Bật chế độ đọc/ghi qua file <ten_bai>.inp / .out?", default=self.config.generation.use_file_io)
                self.config.generation.use_file_io = fio
                pol = Prompt.ask("Chế độ tính điểm Subtask", choices=["EACH_TEST", "COMPLETE_GROUP"], default=self.config.generation.points_policy)
                self.config.generation.points_policy = pol
                console.print("[green]✓ Đã cập nhật cấu hình cho phiên làm việc hiện tại.[/green]")
                time.sleep(1)
            elif choice == "7":
                self.test_connections()
                Prompt.ask("\nNhấn [bold green]Enter[/bold green] để quay lại menu")
            elif choice == "8":
                console.print("[bold cyan]Tạm biệt và chúc bạn một ngày làm việc hiệu quả! 👋[/bold cyan]")
                break
