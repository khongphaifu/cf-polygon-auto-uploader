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
from core.models import ProblemData, GeneratedCode, PolygonProblemRecord
from core.scraper import scrape_problem_text
from core.ai_engine.llm_client import LLMClient
from core.ai_engine.pipeline import AIPipeline
from core.polygon.client import PolygonClient, PolygonAPIError
from core.polygon.automation import PolygonAutomation
from core.exporter.excel_exporter import ExcelExporter
from core.notifier import Notifier

console = Console(legacy_windows=False, force_terminal=True)


class AutoUploaderCLI:
    """Rich interactive command line interface."""

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
            "[bold cyan]🚀 CODEFORCES & POLYGON AUTO UPLOADER[/bold cyan]\n"
            "[italic white]Tu dong boc tach de bai, sinh 20 test, tao bai & build package len Polygon[/italic white]\n"
            f"[dim]AI Provider: Google Gemini ({self.config.ai.model_name}) | Polygon API: Ready[/dim]"
        )
        console.print(Panel(banner_text, border_style="bright_blue", expand=False))

    def test_connections(self) -> None:
        console.print("\n[bold yellow]🔍 Dang kiem tra ket noi API...[/bold yellow]")
        
        # Test Polygon API
        try:
            with console.status("[bold green]Kiem tra Polygon Codeforces API..."):
                problems = self.polygon_client.list_problems()
            console.print(f"[bold green]✓ Polygon API OK:[/bold green] Ket noi thanh cong! Hien co {len(problems)} bai tren tai khoan.")
        except Exception as e:
            console.print(f"[bold red]✗ Polygon API That bai:[/bold red] {e}")

        # Test Gemini API
        try:
            with console.status("[bold green]Kiem tra Google Gemini API..."):
                res = self.llm_client.generate_json('Return JSON: {"status": "ok", "message": "Gemini ready"}')
            console.print(f"[bold green]✓ Gemini API OK:[/bold green] {res.get('message')}")
        except Exception as e:
            console.print(f"[bold red]✗ Gemini API That bai:[/bold red] {e}")

    def process_single_url(self, url: str) -> Optional[PolygonProblemRecord]:
        """Full pipeline for one problem URL."""
        console.print(f"\n[bold cyan]🎯 Bat dau xu ly bai tap:[/bold cyan] [underline blue]{url}[/underline blue]")

        record = PolygonProblemRecord(
            id=0,
            name="Unknown",
            source_url=url,
            status="RUNNING",
        )

        try:
            # 1. Scrape Problem Statement
            with console.status("[bold yellow]1. Dang cao du lieu de bai tu link...[/bold yellow]"):
                raw_text = scrape_problem_text(url)
                if not raw_text or len(raw_text.strip()) < 30:
                    raise ValueError("Khong the lay noi dung de bai tu duong link.")
            console.print("  [green]✓[/green] Cao de bai thanh cong.")

            # 2. AI Parsing & Formatting
            with console.status("[bold yellow]2. AI dang phan tich de bai, rang buoc va test vi du...[/bold yellow]"):
                problem_data: ProblemData = self.ai_pipeline.parse_problem_content(url, raw_text)
            console.print(f"  [green]✓[/green] Tieu de: [bold white]{problem_data.title}[/bold white] (Short Name: [cyan]{problem_data.short_name}[/cyan])")
            console.print(f"  [dim]Gioi han: {problem_data.time_limit_ms}ms | {problem_data.memory_limit_mb}MB | Samples: {len(problem_data.sample_tests)}[/dim]")

            # 3. AI Code & Test Generation
            with console.status("[bold yellow]3. AI dang viet Solution C++20 toi uu va sinh 20 bo test chat che...[/bold yellow]"):
                gen_code: GeneratedCode = self.ai_pipeline.generate_code_and_tests(
                    problem_data, num_tests=self.config.generation.num_tests
                )
            console.print(f"  [green]✓[/green] Da sinh Solution C++20 toi uu, chay sinh dap an truc tiep va [bold green]{len(gen_code.tests)} test cases[/bold green] (khong tinh test mau).")

            # 4. Polygon Problem Initialization
            with console.status("[bold yellow]4. Dang tao / kiem tra bai tap tren Polygon Codeforces...[/bold yellow]"):
                p_info = self.polygon_auto.get_or_create_problem(problem_data.short_name)
                problem_id = p_info["id"]
                owner = p_info.get("owner") or "luatgay"
                record.id = problem_id
                record.name = problem_data.short_name
                record.owner = owner
                record.url = f"https://polygon.codeforces.com/p{problem_id}/{problem_data.short_name}"
                record.cf_import_url = f"https://polygon.codeforces.com/p{problem_id}/{owner}/{problem_data.short_name}"
            console.print(f"  [green]✓[/green] Polygon Problem ID: [bold cyan]{problem_id}[/bold cyan] ({record.url})")
            console.print(f"  [dim]Link Add Codeforces: {record.cf_import_url}[/dim]")

            # 5. Upload Statements & Limits
            with console.status("[bold yellow]5. Dang tai Statement va cau hinh gioi han len Polygon...[/bold yellow]"):
                self.polygon_auto.setup_problem_statement(problem_id, problem_data)
            console.print("  [green]✓[/green] Tai Statement LaTeX & Gioi han thanh cong.")

            # 6. Upload Source Codes & Checker
            with console.status("[bold yellow]6. Dang nap Solution C++20 chinh va Checker len Polygon...[/bold yellow]"):
                self.polygon_auto.setup_code_files(problem_id, gen_code)
            console.print(f"  [green]✓[/green] Da nap solution.cpp (Checker: {gen_code.checker_type}).")

            # 7. Upload Tests
            with console.status(f"[bold yellow]7. Dang dua {len(problem_data.sample_tests)} test mau va {len(gen_code.tests)} test tu sinh len Polygon...[/bold yellow]"):
                self.polygon_auto.setup_tests(problem_id, problem_data, gen_code)
            console.print(f"  [green]✓[/green] Tai thanh cong toan bo {len(problem_data.sample_tests) + len(gen_code.tests)} tests.")

            # 8. Access Management
            if self.config.generation.auto_grant_access_to_codeforces:
                with console.status("[bold yellow]8. Dang phan quyen chia se cho user 'codeforces'...[/bold yellow]"):
                    self.polygon_auto.grant_access_to_codeforces(problem_id)
                console.print("  [green]✓[/green] Da kich hoat phan quyen cho user 'codeforces'.")

            # 9. Packaging with Auto-Repair
            if self.config.generation.auto_package:
                with console.status("[bold yellow]9. Dang yeu cau Polygon build Full Package & verify (kem Auto-Repair)...[/bold yellow]"):
                    pkg_res = self.polygon_auto.build_and_wait_package(
                        problem_id,
                        timeout_sec=120,
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
                        console.print(f"  [bold red]❌ Trang thai Package: FAILED[/bold red] (Package ID: {record.package_id}) - {record.error_message}")
                    else:
                        record.status = "SUCCESS"
                        console.print(f"  [green]✓[/green] Trang thai Package: [bold green]{record.package_state}[/bold green] (Package ID: {record.package_id or 'queued'})")
            else:
                record.status = "SUCCESS"

            if record.status == "SUCCESS":
                console.print(f"\n[bold green]🎉 Hoan tat bai tap: {problem_data.title}[/bold green]")

        except Exception as e:
            record.status = "FAILED"
            record.error_message = str(e)
            console.print(f"\n[bold red]❌ Loi trong qua trinh xu ly:[/bold red] {e}")

        # 10. Export to Excel
        try:
            excel_file = self.exporter.export_records([record])
            console.print(f"[dim]📁 Da cap nhat vao file Excel: {excel_file}[/dim]")
        except Exception as ex:
            console.print(f"[yellow]⚠️ Loi cap nhat Excel: {ex}[/yellow]")

        # 11. Send Notifications (Discord / Telegram)
        try:
            self.notifier.notify_problem_completed(record)
        except Exception:
            pass

        return record

    def batch_process(self) -> None:
        console.print("\n[bold cyan]📋 Xu ly hang loat duong link[/bold cyan]")
        choice = Prompt.ask(
            "Chon phuong thuc nhap",
            choices=["file", "manual", "cancel"],
            default="manual",
        )

        urls: List[str] = []
        if choice == "file":
            file_path = Prompt.ask("Nhap duong dan file chua danh sach URL (.txt)")
            path = Path(file_path)
            if not path.exists():
                console.print("[bold red]File khong ton tai![/bold red]")
                return
            with open(path, "r", encoding="utf-8") as f:
                urls = [line.strip() for line in f if line.strip() and not line.strip().startswith("#")]
        elif choice == "manual":
            console.print("[italic]Nhap cac duong link (moi dong 1 link). Go dong trong hoac 'done' de bat dau:[/italic]")
            while True:
                line = input("> ").strip()
                if not line or line.lower() == "done":
                    break
                urls.append(line)

        if not urls:
            console.print("[yellow]Khong co link nao de xu ly.[/yellow]")
            return

        console.print(f"\n[bold green]Tong so bai tap can xu ly: {len(urls)}[/bold green]")
        results = []
        for idx, u in enumerate(urls, start=1):
            console.print(f"\n--- [Bai {idx}/{len(urls)}] ---")
            rec = self.process_single_url(u)
            if rec:
                results.append(rec)

        self.display_summary_table(results)

    def display_summary_table(self, records: List[PolygonProblemRecord]) -> None:
        table = Table(title="📊 Bang Tong Hop Ket Qua Polygon", header_style="bold magenta")
        table.add_column("ID", justify="center", style="cyan")
        table.add_column("Ten Bai", style="white")
        table.add_column("Link Polygon", style="blue")
        table.add_column("Package State", justify="center")
        table.add_column("CF Ready", justify="center")
        table.add_column("Trang Thai", justify="center")

        for r in records:
            cf_ready = "[green]YES[/green]" if r.package_state == "READY" else "[yellow]NO[/yellow]"
            status_str = f"[green]{r.status}[/green]" if r.status == "SUCCESS" else f"[red]{r.status}[/red]"
            table.add_row(
                str(r.id),
                r.name,
                r.url,
                r.package_state or "-",
                cf_ready,
                status_str,
            )

        console.print(table)
        Prompt.ask("\nNhan [bold green]Enter[/bold green] de quay lai menu chinh")

    def view_polygon_problems(self) -> None:
        try:
            with console.status("[bold green]Dang tai danh sach bai tu Polygon..."):
                problems = self.polygon_client.list_problems()

            table = Table(title=f"📁 Danh Sach Bai Tap Tren Polygon ({len(problems)} bai)", header_style="bold cyan")
            table.add_column("ID", justify="center", style="cyan")
            table.add_column("Ten Bai", style="white")
            table.add_column("Owner", style="dim")
            table.add_column("Access Type", justify="center")
            table.add_column("Link Polygon", style="blue")

            records_to_export = []
            for p in problems[:40]:  # Show latest 40
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

            if Confirm.ask("\nBan co muon xuat toan bo danh sach nay ra file Excel khong?"):
                excel_path = self.exporter.export_records(records_to_export)
                console.print(f"[bold green]✓ Da xuat ra file Excel:[/bold green] {excel_path}")

        except Exception as e:
            console.print(f"[bold red]Loi khi tai danh sach Polygon:[/bold red] {e}")

        Prompt.ask("\nNhan [bold green]Enter[/bold green] de quay lai menu chinh")

    def run(self) -> None:
        while True:
            self.print_banner()
            console.print("[bold yellow]MENU CHINH:[/bold yellow]")
            console.print("  [bold cyan][1][/bold cyan] Nhap 1 duong link bai tap (Single URL)")
            console.print("  [bold cyan][2][/bold cyan] Xu ly hang loat tu danh sach link (Batch URLs)")
            console.print("  [bold cyan][3][/bold cyan] Xem danh sach bai tren Polygon & Xuat Excel")
            console.print("  [bold cyan][4][/bold cyan] Kiem tra ket noi Polygon & Gemini API")
            console.print("  [bold cyan][5][/bold cyan] Thoat")

            choice = Prompt.ask("\nChon chuc nang", choices=["1", "2", "3", "4", "5"], default="1")

            if choice == "1":
                url = Prompt.ask("\n[bold green]Nhap duong link bai tap[/bold green]").strip()
                if url:
                    self.process_single_url(url)
                    Prompt.ask("\nNhan [bold green]Enter[/bold green] de quay lai menu")
            elif choice == "2":
                self.batch_process()
            elif choice == "3":
                self.view_polygon_problems()
            elif choice == "4":
                self.test_connections()
            elif choice == "5":
                console.print("[bold cyan]Tam biet va chuc ban mot ngay lam viec hieu qua! 👋[/bold cyan]")
                break
