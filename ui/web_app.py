import json
import logging
import os
import sys
import threading
import time
import webbrowser
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from typing import Dict, Any, List, Optional
from urllib.parse import parse_qs, urlparse

from config.settings import load_config, AppConfig
from core.ai_engine.llm_client import LLMClient
from core.ai_engine.pipeline import AIPipeline
from core.exporter.excel_exporter import ExcelExporter, PolygonProblemRecord
from core.models import GeneratedCode, ProblemData
from core.notifier import Notifier
from core.polygon.automation import PolygonAutomation
from core.polygon.client import PolygonClient
from core.scraper import scrape_problem_text

logger = logging.getLogger(__name__)

# Global Live Dashboard State
DASHBOARD_STATE = {
    "is_running": False,
    "current_url": "",
    "current_step": "Sẵn sàng",
    "step_progress": 0,
    "logs": [],
    "recent_records": [],
    "last_problem_data": None,
    "model_name": "gemini-3.1-pro-preview",
}


def add_dashboard_log(message: str, step: str = "", progress: int = 0):
    timestamp = time.strftime("%H:%M:%S")
    DASHBOARD_STATE["logs"].append(f"[{timestamp}] {message}")
    if step:
        DASHBOARD_STATE["current_step"] = step
    if progress:
        DASHBOARD_STATE["step_progress"] = progress


HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="vi">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>CF Polygon Auto Uploader Dashboard</title>
    <!-- Tailwind CSS CDN -->
    <script src="https://cdn.tailwindcss.com"></script>
    <!-- FontAwesome -->
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
</head>
<body class="bg-slate-950 text-slate-100 min-h-screen font-sans antialiased">
    <!-- Navbar -->
    <header class="bg-slate-900 border-b border-slate-800 sticky top-0 z-50 px-6 py-4 flex items-center justify-between shadow-lg">
        <div class="flex items-center space-x-3">
            <div class="w-10 h-10 rounded-xl bg-gradient-to-tr from-blue-600 to-indigo-500 flex items-center justify-center text-xl font-bold shadow-md shadow-blue-500/20">
                <i class="fa-solid fa-rocket"></i>
            </div>
            <div>
                <h1 class="text-lg font-bold bg-gradient-to-r from-blue-400 to-indigo-300 bg-clip-text text-transparent">CF Polygon Auto Uploader</h1>
                <p class="text-xs text-slate-400">10-Step Pipeline | Subtask Division | testlib.h Generator & Script</p>
            </div>
        </div>
        <div class="flex items-center space-x-4">
            <span class="inline-flex items-center px-3 py-1 rounded-full text-xs font-medium bg-emerald-950 text-emerald-400 border border-emerald-800/50">
                <span class="w-2 h-2 mr-2 rounded-full bg-emerald-400 animate-pulse"></span>
                Gemini 3.1 Pro
            </span>
            <a href="/download-excel" class="px-4 py-2 text-xs font-semibold rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-200 border border-slate-700 flex items-center space-x-2 transition shadow">
                <i class="fa-solid fa-file-excel text-emerald-400"></i>
                <span>Tải problems_summary.xlsx</span>
            </a>
        </div>
    </header>

    <main class="max-w-7xl mx-auto px-6 py-8 grid grid-cols-1 lg:grid-cols-3 gap-8">
        <!-- Left 2 Cols: Submit Form & Live Logs -->
        <div class="lg:col-span-2 space-y-6">
            <!-- URL Submission Box -->
            <div class="bg-slate-900 border border-slate-800 rounded-2xl p-6 shadow-xl">
                <h2 class="text-base font-semibold text-slate-200 flex items-center mb-4">
                    <i class="fa-solid fa-link text-blue-400 mr-2"></i> Nhập link bài tập & cấu hình tests
                </h2>
                <div class="space-y-4">
                    <div class="grid grid-cols-1 md:grid-cols-4 gap-4">
                        <div class="md:col-span-3">
                            <label class="block text-xs font-medium text-slate-400 mb-1">Đường dẫn bài tập (Codeforces, AtCoder, CSES, VNOJ...)</label>
                            <input type="text" id="urlInput" placeholder="https://codeforces.com/problemset/problem/158/A"
                                class="w-full bg-slate-950 border border-slate-800 rounded-xl px-4 py-3 text-sm focus:outline-none focus:border-blue-500 text-slate-100 placeholder-slate-600 transition">
                        </div>
                        <div>
                            <label class="block text-xs font-medium text-slate-400 mb-1">Số lượng tests</label>
                            <input type="number" id="numTestsInput" value="30" min="5" max="100"
                                class="w-full bg-slate-950 border border-slate-800 rounded-xl px-4 py-3 text-sm focus:outline-none focus:border-blue-500 text-slate-100 transition text-center font-mono font-bold">
                        </div>
                    </div>
                    <div class="flex items-center space-x-3">
                        <button onclick="startUpload()" id="btnStart"
                            class="flex-1 bg-blue-600 hover:bg-blue-500 active:scale-[0.99] text-white font-medium py-3 px-6 rounded-xl shadow-lg shadow-blue-600/30 flex items-center justify-center space-x-2 transition">
                            <i class="fa-solid fa-cloud-arrow-up"></i>
                            <span>Bắt đầu Quy Trình 10 Bước Lên Polygon</span>
                        </button>
                    </div>
                </div>
            </div>

            <!-- Live Progress & Log Stream -->
            <div class="bg-slate-900 border border-slate-800 rounded-2xl p-6 shadow-xl">
                <div class="flex items-center justify-between mb-4">
                    <h2 class="text-base font-semibold text-slate-200 flex items-center">
                        <i class="fa-solid fa-terminal text-emerald-400 mr-2"></i> Tiến độ & Nhật ký 10 bước
                    </h2>
                    <span id="badgeStep" class="text-xs font-mono px-2.5 py-1 rounded bg-slate-800 text-slate-300">Sẵn sàng</span>
                </div>
                <!-- Progress Bar -->
                <div class="w-full bg-slate-950 rounded-full h-2.5 mb-4 overflow-hidden border border-slate-800">
                    <div id="progressBar" class="bg-gradient-to-r from-blue-500 to-emerald-400 h-2.5 rounded-full transition-all duration-500" style="width: 0%"></div>
                </div>
                <!-- Logs Console -->
                <div id="logBox" class="bg-slate-950 border border-slate-800 rounded-xl p-4 h-72 overflow-y-auto font-mono text-xs text-slate-300 space-y-1.5 scrollbar-thin scrollbar-thumb-slate-800">
                    <div class="text-slate-600 italic">// Hệ thống sẵn sàng tiếp nhận bài tập mới...</div>
                </div>
            </div>
        </div>

        <!-- Right Col: Summary & Badges -->
        <div class="space-y-6">
            <!-- Summary Stats -->
            <div class="bg-slate-900 border border-slate-800 rounded-2xl p-6 shadow-xl">
                <h3 class="text-sm font-semibold text-slate-300 mb-4 flex items-center">
                    <i class="fa-solid fa-circle-check text-emerald-400 mr-2"></i> Bài đã nạp thành công
                </h3>
                <div id="recentList" class="space-y-3">
                    <div class="text-xs text-slate-500 italic text-center py-4">Chưa có bài nào trong phiên này</div>
                </div>
            </div>

            <!-- Feature Badges -->
            <div class="bg-slate-900 border border-slate-800 rounded-2xl p-6 shadow-xl space-y-3">
                <h4 class="text-xs font-bold text-slate-400 uppercase tracking-wider">Chuẩn 10 Bước Polygon</h4>
                <div class="text-xs space-y-2 text-slate-300">
                    <div class="flex items-center"><i class="fa-solid fa-check text-emerald-400 mr-2"></i> 1. Đọc link & Chia Subtask</div>
                    <div class="flex items-center"><i class="fa-solid fa-check text-emerald-400 mr-2"></i> 2. Ghi Statement LaTeX</div>
                    <div class="flex items-center"><i class="fa-solid fa-check text-emerald-400 mr-2"></i> 3. Chọn Checker (wcmp/ncmp/custom)</div>
                    <div class="flex items-center"><i class="fa-solid fa-check text-emerald-400 mr-2"></i> 4. Add gen.cpp (testlib.h)</div>
                    <div class="flex items-center"><i class="fa-solid fa-check text-emerald-400 mr-2"></i> 5. Add solution.cpp (tag MA)</div>
                    <div class="flex items-center"><i class="fa-solid fa-check text-emerald-400 mr-2"></i> 6. Ghi Script sinh test & groups</div>
                    <div class="flex items-center"><i class="fa-solid fa-check text-emerald-400 mr-2"></i> 7. Commit changes</div>
                    <div class="flex items-center"><i class="fa-solid fa-check text-emerald-400 mr-2"></i> 8. Build Packages & Auto-Repair</div>
                    <div class="flex items-center"><i class="fa-solid fa-check text-emerald-400 mr-2"></i> 9. Manage access (codeforces)</div>
                    <div class="flex items-center"><i class="fa-solid fa-check text-emerald-400 mr-2"></i> 10. Link CF & Cập nhật Excel</div>
                </div>
            </div>
        </div>
    </main>

    <script>
        function copyText(text) {
            navigator.clipboard.writeText(text);
            alert("Đã sao chép link Import Codeforces:\n" + text);
        }

        async function startUpload() {
            const url = document.getElementById('urlInput').value.trim();
            const numTests = parseInt(document.getElementById('numTestsInput').value) || 30;
            if (!url) {
                alert("Vui lòng nhập đường link bài tập!");
                return;
            }
            document.getElementById('btnStart').disabled = true;
            document.getElementById('btnStart').classList.add('opacity-50');

            try {
                await fetch('/api/start', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({url: url, num_tests: numTests})
                });
            } catch (err) {
                console.error(err);
            }
        }

        async function pollStatus() {
            try {
                const res = await fetch('/api/status');
                const data = await res.json();

                document.getElementById('badgeStep').innerText = data.current_step || "Sẵn sàng";
                document.getElementById('progressBar').style.width = (data.step_progress || 0) + "%";

                const logBox = document.getElementById('logBox');
                if (data.logs && data.logs.length > 0) {
                    logBox.innerHTML = data.logs.map(l => `<div class="leading-relaxed">` + escapeHtml(l) + `</div>`).join('');
                    logBox.scrollTop = logBox.scrollHeight;
                }

                if (data.is_running) {
                    document.getElementById('btnStart').disabled = true;
                    document.getElementById('btnStart').classList.add('opacity-50');
                } else {
                    document.getElementById('btnStart').disabled = false;
                    document.getElementById('btnStart').classList.remove('opacity-50');
                }

                if (data.recent_records && data.recent_records.length > 0) {
                    const listHtml = data.recent_records.map(r => `
                        <div class="p-3 bg-slate-950 rounded-xl border border-slate-800 hover:border-slate-700 transition space-y-1.5">
                            <div class="flex items-center justify-between">
                                <span class="font-bold text-xs text-white">${r.name}</span>
                                <span class="px-2 py-0.5 rounded text-[10px] font-bold ${r.package_state === 'READY' ? 'bg-emerald-950 text-emerald-400 border border-emerald-800' : 'bg-amber-950 text-amber-400 border border-amber-800'}">
                                    ${r.package_state || r.status}
                                </span>
                            </div>
                            <div class="text-[11px] text-slate-400">ID: <span class="text-cyan-400 font-mono">${r.id}</span> | Tests: <span class="text-yellow-400 font-mono">${r.total_tests || 0}</span></div>
                            <div class="text-[10px] text-slate-500 truncate">${r.subtasks_summary || ""}</div>
                            <div class="pt-1 flex items-center space-x-2">
                                <button onclick="copyText('${r.cf_import_url}')" class="text-[11px] px-2.5 py-1 rounded bg-blue-950 hover:bg-blue-900 text-blue-300 border border-blue-800 flex items-center space-x-1 transition">
                                    <i class="fa-solid fa-copy"></i>
                                    <span>Copy CF Link</span>
                                </button>
                                <a href="${r.url}" target="_blank" class="text-[11px] px-2.5 py-1 rounded bg-slate-800 hover:bg-slate-700 text-slate-300 transition">
                                    <i class="fa-solid fa-arrow-up-right-from-square"></i>
                                </a>
                            </div>
                        </div>
                    `).join('');
                    document.getElementById('recentList').innerHTML = listHtml;
                }
            } catch (e) {
                console.error(e);
            }
        }

        function escapeHtml(str) {
            return str.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
        }

        setInterval(pollStatus, 1500);
        pollStatus();
    </script>
</body>
</html>
"""


class DashboardRequestHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/" or parsed.path == "/index.html":
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(HTML_TEMPLATE.encode("utf-8"))

        elif parsed.path == "/api/status":
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.end_headers()
            self.wfile.write(json.dumps(DASHBOARD_STATE).encode("utf-8"))

        elif parsed.path == "/download-excel":
            config = load_config()
            excel_path = Path(config.export.excel_file_path)
            if excel_path.exists():
                self.send_response(200)
                self.send_header("Content-Type", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
                self.send_header("Content-Disposition", f"attachment; filename={excel_path.name}")
                self.end_headers()
                self.wfile.write(excel_path.read_bytes())
            else:
                self.send_response(404)
                self.end_headers()
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        parsed = urlparse(self.path)
        if parsed.path == "/api/start":
            content_length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_length).decode("utf-8")
            try:
                data = json.loads(body)
                url = data.get("url", "").strip()
                num_tests = int(data.get("num_tests", 30))
            except Exception:
                url = ""
                num_tests = 30

            if not url or DASHBOARD_STATE["is_running"]:
                self.send_response(400)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"error": "Already running or invalid URL"}).encode("utf-8"))
                return

            threading.Thread(target=run_pipeline_background, args=(url, num_tests), daemon=True).start()

            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"status": "started", "url": url, "num_tests": num_tests}).encode("utf-8"))
        else:
            self.send_response(404)
            self.end_headers()


def run_pipeline_background(url: str, num_tests: int = 30):
    DASHBOARD_STATE["is_running"] = True
    DASHBOARD_STATE["current_url"] = url
    DASHBOARD_STATE["logs"] = []
    add_dashboard_log(f"Bắt đầu xử lý bài tập: {url} (Yêu cầu {num_tests} tests)", step="Khởi động", progress=5)

    config: AppConfig = load_config()
    polygon_client = PolygonClient(
        api_key=config.polygon.api_key,
        api_secret=config.polygon.api_secret,
        api_url=config.polygon.api_url,
    )
    polygon_auto = PolygonAutomation(polygon_client)
    llm_client = LLMClient(
        api_key=config.ai.gemini_api_key,
        backup_keys=config.ai.gemini_backup_keys,
        model_name=config.ai.model_name,
    )
    ai_pipeline = AIPipeline(llm_client)
    exporter = ExcelExporter(output_path=config.export.excel_file_path)
    notifier = Notifier(config.notifications)

    record = PolygonProblemRecord(id=0, name="Unknown", source_url=url, status="RUNNING")

    try:
        # Bước 1: Đọc link & Phân tích đề bài + Subtasks
        add_dashboard_log("Bước 1/10: Đang cào dữ liệu và phân tích Subtasks...", step="1/10 Đọc link & Subtasks", progress=10)
        raw_text = scrape_problem_text(url)
        if not raw_text or len(raw_text.strip()) < 30:
            raise ValueError("Không thể lấy nội dung bài tập từ link.")
        problem_data: ProblemData = ai_pipeline.parse_problem_content(url, raw_text)
        add_dashboard_log(f"Đã phân tích: {problem_data.title} ({problem_data.short_name})", step="1/10 Hoàn tất AI", progress=20)

        # Log Subtasks
        for s in problem_data.subtasks:
            add_dashboard_log(f"  * Subtask {s.subtask_id} ({s.points} pts): {s.description}")

        # AI Code, Generator, Script & Local Dual-Verification
        add_dashboard_log(f"AI đang viết Solution C++20 tối ưu, Generator và Script ({num_tests} tests)...", step="Sinh Code & Script", progress=30)
        gen_code: GeneratedCode = ai_pipeline.generate_code_and_tests(problem_data, num_tests=num_tests)
        add_dashboard_log(f"Đã kiểm định cục bộ và sinh đáp án trực tiếp cho {len(gen_code.tests)} tests.", step="Kiểm định cục bộ OK", progress=40)

        # Khởi tạo Problem trên Polygon
        p_info = polygon_auto.get_or_create_problem(problem_data.short_name)
        problem_id = p_info["id"]
        owner = p_info.get("owner") or "luatgay"
        record.id = problem_id
        record.name = problem_data.short_name
        record.owner = owner
        record.url = f"https://polygon.codeforces.com/p{problem_id}/{problem_data.short_name}"
        record.cf_import_url = f"https://polygon.codeforces.com/p{problem_id}/{owner}/{problem_data.short_name}"
        record.total_tests = len(gen_code.tests)

        # Bước 2: Ghi Statement
        add_dashboard_log("Bước 2/10: Đang ghi Statement LaTeX & Giới hạn lên Polygon...", step="2/10 Ghi Statement", progress=50)
        polygon_auto.setup_problem_statement(problem_id, problem_data)

        # Bước 3: Chọn Checker
        add_dashboard_log(f"Bước 3/10: Thiết lập Checker ({gen_code.checker_type})...", step="3/10 Chọn Checker", progress=55)
        polygon_auto.setup_checker(problem_id, gen_code)

        # Bước 4: Add file sinh test
        add_dashboard_log("Bước 4/10: Nạp file sinh test (gen.cpp dùng testlib.h) lên Polygon Files...", step="4/10 Add gen.cpp", progress=60)
        polygon_auto.setup_generator(problem_id, gen_code)

        # Bước 5: Add file solution
        add_dashboard_log("Bước 5/10: Nạp Solution C++20 chính (solution.cpp tag MA) lên Polygon...", step="5/10 Add solution.cpp", progress=65)
        polygon_auto.setup_solution(problem_id, gen_code)

        # Bước 6: Ghi script sinh test & tests
        add_dashboard_log(f"Bước 6/10: Ghi Script sinh test và nạp {len(gen_code.tests)} tests chia subtask...", step="6/10 Ghi Script Tests", progress=70)
        polygon_auto.setup_test_script_and_tests(problem_id, problem_data, gen_code)

        # Bước 7: Commit changes
        add_dashboard_log("Bước 7/10: Commit working copy trên Polygon...", step="7/10 Commit Changes", progress=75)
        polygon_auto.commit_changes(problem_id, f"Auto-commit: added statement, checker, generator, solution MA, and test script with {len(gen_code.tests)} tests")

        # Bước 8: Package with Auto-Repair
        if config.generation.auto_package:
            add_dashboard_log("Bước 8/10: Yêu cầu Polygon build Full Package & verify (kèm Auto-Repair)...", step="8/10 Build Package", progress=85)
            pkg_res = polygon_auto.build_and_wait_package(
                problem_id,
                timeout_sec=60,
                poll_interval=4,
                problem=problem_data,
                code=gen_code,
                ai_pipeline=ai_pipeline,
            )
            record.package_id = pkg_res.get("id")
            record.package_state = pkg_res.get("state", "BUILDING")
            if record.package_state == "FAILED":
                record.status = "FAILED"
                record.error_message = pkg_res.get("error_message") or f"Polygon package build failed on package {record.package_id}."
                add_dashboard_log(f"❌ Package FAILED: {record.error_message}", step="Thất bại", progress=100)
            else:
                record.status = "SUCCESS"
                add_dashboard_log(f"✓ Package READY (ID: {record.package_id})", step="Package READY", progress=90)
        else:
            record.status = "SUCCESS"

        # Bước 9: Manage Access
        if config.generation.auto_grant_access_to_codeforces:
            add_dashboard_log("Bước 9/10: Cấp quyền chia sẻ cho user 'codeforces'...", step="9/10 Phân quyền", progress=95)
            polygon_auto.grant_access_to_codeforces(problem_id)

        # Bước 10: Link hoàn chỉnh & Excel
        subtasks_summary = ", ".join([f"Subtask {s.subtask_id} ({s.points} pts: {s.test_count} tests)" for s in problem_data.subtasks])
        record.subtasks_summary = subtasks_summary

        if record.status == "SUCCESS":
            add_dashboard_log(f"🎉 Bước 10/10: HOÀN TẤT THÀNH CÔNG BÀI TẬP: {problem_data.title}!", step="Hoàn thành", progress=100)
            add_dashboard_log(f"👉 Link Import Codeforces: {record.cf_import_url}", step="Hoàn thành", progress=100)

    except Exception as e:
        record.status = "FAILED"
        record.error_message = str(e)
        add_dashboard_log(f"❌ Lỗi: {e}", step="Thất bại", progress=100)

    # Export to Excel
    try:
        exporter.export_records([record])
        add_dashboard_log(f"Đã lưu thông tin vào problems_summary.xlsx")
    except Exception:
        pass

    # Send Notification
    try:
        notifier.notify_problem_completed(record)
    except Exception:
        pass

    DASHBOARD_STATE["recent_records"].insert(0, {
        "id": record.id,
        "name": record.name,
        "package_state": record.package_state,
        "status": record.status,
        "cf_import_url": record.cf_import_url,
        "url": record.url,
        "total_tests": record.total_tests,
        "subtasks_summary": record.subtasks_summary,
    })
    DASHBOARD_STATE["is_running"] = False


def start_web_dashboard(port: int = 8080, open_browser: bool = True):
    server = HTTPServer(("127.0.0.1", port), DashboardRequestHandler)
    print(f"\n=======================================================")
    print(f"🚀 CF Polygon Auto Uploader Web Dashboard đã sẵn sàng!")
    print(f"🌐 Truy cập tại: http://127.0.0.1:{port}")
    print(f"=======================================================\n")
    if open_browser:
        threading.Thread(target=lambda: (time.sleep(1), webbrowser.open(f"http://127.0.0.1:{port}"))).start()
    server.serve_forever()


if __name__ == "__main__":
    start_web_dashboard()
