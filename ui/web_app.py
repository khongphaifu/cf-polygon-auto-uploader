import base64
import json
import logging
import os
import re
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

from config.settings import AppConfig, load_config
from core.ai_engine.llm_client import LLMClient
from core.ai_engine.pipeline import AIPipeline
from core.exporter.excel_exporter import ExcelExporter
from core.models import ProblemData
from core.notifier import Notifier
from core.polygon.automation import PolygonAutomation, run_upload_pipeline
from core.polygon.client import PolygonClient

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
    "model_name": "gemini-3.1-flash-lite",
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
    <title>CF Polygon Auto Uploader v2.0 Dashboard</title>
    <script src="https://cdn.tailwindcss.com"></script>
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
                <h1 class="text-lg font-bold bg-gradient-to-r from-blue-400 to-indigo-300 bg-clip-text text-transparent">CF Polygon Auto Uploader v2.0</h1>
                <p class="text-xs text-slate-400">10-Step Pipeline | Song ngữ VI/EN | Bảng Scoring | Validator | Subtasks 100đ</p>
            </div>
        </div>
        <div class="flex items-center space-x-4">
            <span class="inline-flex items-center px-3 py-1 rounded-full text-xs font-medium bg-emerald-950 text-emerald-400 border border-emerald-800/50">
                <span class="w-2 h-2 mr-2 rounded-full bg-emerald-400 animate-pulse"></span>
                Gemini 3.1 Flash Lite
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
            <!-- URL & File Submission Box -->
            <div class="bg-slate-900 border border-slate-800 rounded-2xl p-6 shadow-xl">
                <h2 class="text-base font-semibold text-slate-200 flex items-center mb-4">
                    <i class="fa-solid fa-link text-blue-400 mr-2"></i> Nhập Link Bài Tập hoặc Tải File PDF / Ảnh
                </h2>
                <div class="space-y-4">
                    <div class="grid grid-cols-1 md:grid-cols-4 gap-4">
                        <div class="md:col-span-3">
                            <label class="block text-xs font-medium text-slate-400 mb-1">Đường dẫn bài tập (Codeforces, VNOJ HTML/PDF, AtCoder, CSES, MarisaOJ...)</label>
                            <input type="text" id="urlInput" placeholder="https://oj.vnoi.info/problem/fc020_accepted"
                                class="w-full bg-slate-950 border border-slate-800 rounded-xl px-4 py-3 text-sm focus:outline-none focus:border-blue-500 text-slate-100 placeholder-slate-600 transition">
                        </div>
                        <div>
                            <label class="block text-xs font-medium text-slate-400 mb-1">Số lượng tests</label>
                            <input type="number" id="numTestsInput" value="30" min="5" max="100"
                                class="w-full bg-slate-950 border border-slate-800 rounded-xl px-4 py-3 text-sm focus:outline-none focus:border-blue-500 text-slate-100 transition text-center font-mono font-bold">
                        </div>
                    </div>

                    <!-- Options Row: Language, File Upload, Checkboxes -->
                    <div class="grid grid-cols-1 md:grid-cols-3 gap-4 items-end">
                        <div>
                            <label class="block text-xs font-medium text-slate-400 mb-1">Ngôn ngữ Đề bài (Statement)</label>
                            <select id="langSelect" class="w-full bg-slate-950 border border-slate-800 rounded-xl px-3 py-2.5 text-sm text-slate-100 focus:outline-none focus:border-blue-500">
                                <option value="both" selected>Song ngữ (Tiếng Việt + Tiếng Anh)</option>
                                <option value="vi">Chỉ Tiếng Việt</option>
                                <option value="en">Chỉ Tiếng Anh</option>
                                <option value="auto">Tự động theo nguồn</option>
                            </select>
                        </div>
                        <div>
                            <label class="block text-xs font-medium text-slate-400 mb-1">Hoặc chọn File đề (PDF / Ảnh / TXT)</label>
                            <input type="file" id="fileInput" accept=".pdf,.png,.jpg,.jpeg,.webp,.txt,.md"
                                class="w-full text-xs text-slate-400 file:mr-3 file:py-2 file:px-3 file:rounded-lg file:border-0 file:text-xs file:font-semibold file:bg-slate-800 file:text-blue-400 hover:file:bg-slate-700 cursor-pointer">
                        </div>
                        <div class="flex flex-col space-y-2 text-xs text-slate-300 pb-1">
                            <label class="inline-flex items-center space-x-2 cursor-pointer">
                                <input type="checkbox" id="fileIoCheck" class="rounded bg-slate-950 border-slate-700 text-blue-500">
                                <span>Dùng File I/O (.inp / .out)</span>
                            </label>
                            <label class="inline-flex items-center space-x-2 cursor-pointer">
                                <input type="checkbox" id="noCacheCheck" class="rounded bg-slate-950 border-slate-700 text-blue-500">
                                <span>Chạy mới (Bỏ qua Cache)</span>
                            </label>
                        </div>
                    </div>

                    <div class="flex items-center space-x-3 pt-1">
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
                <div class="w-full bg-slate-950 rounded-full h-2.5 mb-4 overflow-hidden border border-slate-800">
                    <div id="progressBar" class="bg-gradient-to-r from-blue-500 to-emerald-400 h-2.5 rounded-full transition-all duration-500" style="width: 0%"></div>
                </div>
                <div id="logBox" class="bg-slate-950 border border-slate-800 rounded-xl p-4 h-72 overflow-y-auto font-mono text-xs text-slate-300 space-y-1.5 scrollbar-thin scrollbar-thumb-slate-800">
                    <div class="text-slate-600 italic">// Hệ thống v2.0 sẵn sàng tiếp nhận URL hoặc tệp đề bài mới...</div>
                </div>
            </div>
        </div>

        <!-- Right Col: Summary & Badges -->
        <div class="space-y-6">
            <div class="bg-slate-900 border border-slate-800 rounded-2xl p-6 shadow-xl">
                <h3 class="text-sm font-semibold text-slate-300 mb-4 flex items-center">
                    <i class="fa-solid fa-circle-check text-emerald-400 mr-2"></i> Bài đã nạp thành công
                </h3>
                <div id="recentList" class="space-y-3">
                    <div class="text-xs text-slate-500 italic text-center py-4">Chưa có bài nào trong phiên này</div>
                </div>
            </div>

            <div class="bg-slate-900 border border-slate-800 rounded-2xl p-6 shadow-xl space-y-3">
                <h4 class="text-xs font-bold text-slate-400 uppercase tracking-wider">Chuẩn 10 Bước Polygon v2.0</h4>
                <div class="text-xs space-y-2 text-slate-300">
                    <div class="flex items-center"><i class="fa-solid fa-check text-emerald-400 mr-2"></i> 1. Đọc URL / PDF / Ảnh & Subtasks</div>
                    <div class="flex items-center"><i class="fa-solid fa-check text-emerald-400 mr-2"></i> 2. Statement Song ngữ + Ô Scoring</div>
                    <div class="flex items-center"><i class="fa-solid fa-check text-emerald-400 mr-2"></i> 3. Checker + Validator (testlib.h)</div>
                    <div class="flex items-center"><i class="fa-solid fa-check text-emerald-400 mr-2"></i> 4. Self-Healing Sample Check</div>
                    <div class="flex items-center"><i class="fa-solid fa-check text-emerald-400 mr-2"></i> 5. Nạp gen.cpp & solution.cpp (g++23)</div>
                    <div class="flex items-center"><i class="fa-solid fa-check text-emerald-400 mr-2"></i> 6. Nạp vidu (0đ) + sub1..sub3 (100đ)</div>
                    <div class="flex items-center"><i class="fa-solid fa-check text-emerald-400 mr-2"></i> 7. Commit working copy</div>
                    <div class="flex items-center"><i class="fa-solid fa-check text-emerald-400 mr-2"></i> 8. Build Package & Auto-Repair</div>
                    <div class="flex items-center"><i class="fa-solid fa-check text-emerald-400 mr-2"></i> 9. Cấp quyền WRITE cho codeforces</div>
                    <div class="flex items-center"><i class="fa-solid fa-check text-emerald-400 mr-2"></i> 10. Link Import CF & Xuất Excel</div>
                </div>
            </div>
        </div>
    </main>

    <script>
        function copyText(text) {
            navigator.clipboard.writeText(text);
            alert("Đã sao chép link Import Codeforces:\\n" + text);
        }

        function readFileAsBase64(file) {
            return new Promise((resolve, reject) => {
                const reader = new FileReader();
                reader.onload = () => resolve(reader.result.split(',')[1]);
                reader.onerror = reject;
                reader.readAsDataURL(file);
            });
        }

        async function startUpload() {
            const url = document.getElementById('urlInput').value.trim();
            const fileInput = document.getElementById('fileInput');
            const numTests = parseInt(document.getElementById('numTestsInput').value) || 30;
            const langMode = document.getElementById('langSelect').value;
            const useFileIo = document.getElementById('fileIoCheck').checked;
            const ignoreCache = document.getElementById('noCacheCheck').checked;

            const hasFile = fileInput.files && fileInput.files.length > 0;
            if (!url && !hasFile) {
                alert("Vui lòng nhập đường link bài tập hoặc chọn tệp PDF/Ảnh!");
                return;
            }

            document.getElementById('btnStart').disabled = true;
            document.getElementById('btnStart').classList.add('opacity-50');

            try {
                if (hasFile) {
                    const file = fileInput.files[0];
                    const b64 = await readFileAsBase64(file);
                    await fetch('/api/upload-file', {
                        method: 'POST',
                        headers: {'Content-Type': 'application/json'},
                        body: JSON.stringify({
                            filename: file.name,
                            content_b64: b64,
                            num_tests: numTests,
                            lang_mode: langMode,
                            use_file_io: useFileIo,
                            ignore_cache: ignoreCache
                        })
                    });
                    fileInput.value = "";
                } else {
                    await fetch('/api/start', {
                        method: 'POST',
                        headers: {'Content-Type': 'application/json'},
                        body: JSON.stringify({
                            url: url,
                            num_tests: numTests,
                            lang_mode: langMode,
                            use_file_io: useFileIo,
                            ignore_cache: ignoreCache
                        })
                    });
                }
            } catch (err) {
                console.error(err);
                document.getElementById('btnStart').disabled = false;
                document.getElementById('btnStart').classList.remove('opacity-50');
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
        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length).decode("utf-8")

        if parsed.path == "/api/start":
            try:
                data = json.loads(body)
                url = data.get("url", "").strip()
                num_tests = int(data.get("num_tests", 30))
                lang_mode = data.get("lang_mode", "both")
                use_file_io = bool(data.get("use_file_io", False))
                ignore_cache = bool(data.get("ignore_cache", False))
            except Exception:
                url = ""
                num_tests, lang_mode, use_file_io, ignore_cache = 30, "both", False, False

            if not url or DASHBOARD_STATE["is_running"]:
                self.send_response(400)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"error": "Already running or invalid URL"}).encode("utf-8"))
                return

            threading.Thread(
                target=run_pipeline_background,
                args=(url, num_tests, lang_mode, use_file_io, ignore_cache, None),
                daemon=True,
            ).start()

            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"status": "started", "url": url, "num_tests": num_tests}).encode("utf-8"))

        elif parsed.path == "/api/upload-file":
            try:
                data = json.loads(body)
                filename = Path(data.get("filename", "problem.pdf")).name
                filename = re.sub(r"[^a-zA-Z0-9_.-]", "_", filename)
                file_bytes = base64.b64decode(data.get("content_b64", ""))
                num_tests = int(data.get("num_tests", 30))
                lang_mode = data.get("lang_mode", "both")
                use_file_io = bool(data.get("use_file_io", False))
                ignore_cache = bool(data.get("ignore_cache", False))
            except Exception as ex:
                self.send_response(400)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"error": f"Invalid upload payload: {ex}"}).encode("utf-8"))
                return

            if not file_bytes or DASHBOARD_STATE["is_running"]:
                self.send_response(400)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"error": "Empty file or job already running"}).encode("utf-8"))
                return

            upload_dir = Path("cache") / "uploads"
            upload_dir.mkdir(parents=True, exist_ok=True)
            saved_path = upload_dir / filename
            saved_path.write_bytes(file_bytes)

            threading.Thread(
                target=run_pipeline_background,
                args=(str(saved_path), num_tests, lang_mode, use_file_io, ignore_cache, f"local:{filename}"),
                daemon=True,
            ).start()

            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"status": "started", "file": filename, "num_tests": num_tests}).encode("utf-8"))
        else:
            self.send_response(404)
            self.end_headers()


def run_pipeline_background(
    url: str,
    num_tests: int = 30,
    lang_mode: str = "both",
    use_file_io: bool = False,
    ignore_cache: bool = False,
    display_source: Optional[str] = None,
):
    DASHBOARD_STATE["is_running"] = True
    DASHBOARD_STATE["current_url"] = display_source or url
    DASHBOARD_STATE["logs"] = []
    add_dashboard_log(
        f"Bắt đầu xử lý: {display_source or url} (Tests: {num_tests}, Lang: {lang_mode})",
        step="Khởi động",
        progress=5,
    )

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

    def _on_parsed(problem_data: ProblemData, _target_tests: int) -> None:
        for s in problem_data.subtasks:
            add_dashboard_log(f"  * Subtask {s.subtask_id} ({s.points} pts): {s.description}")

    record = run_upload_pipeline(
        source=url,
        config=config,
        polygon_auto=polygon_auto,
        ai_pipeline=ai_pipeline,
        exporter=exporter,
        notifier=notifier,
        num_tests=num_tests,
        lang_mode=lang_mode,
        use_file_io=use_file_io,
        ignore_cache=ignore_cache,
        on_log=add_dashboard_log,
        on_problem_parsed=_on_parsed,
        display_source=display_source,
    )

    if record.status == "SUCCESS":
        add_dashboard_log(f"🎉 Bước 10/10: HOÀN TẤT THÀNH CÔNG BÀI TẬP: {record.name}!", step="Hoàn thành", progress=100)
        add_dashboard_log(f"👉 Link Import Codeforces: {record.cf_import_url}", step="Hoàn thành", progress=100)
    else:
        add_dashboard_log(f"❌ Thất bại: {record.error_message}", step="Thất bại", progress=100)

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
    print("\n=======================================================")
    print("🚀 CF Polygon Auto Uploader v2.0 Web Dashboard đã sẵn sàng!")
    print(f"🌐 Truy cập tại: http://127.0.0.1:{port}")
    print("=======================================================\n")
    if open_browser:
        threading.Thread(target=lambda: (time.sleep(1), webbrowser.open(f"http://127.0.0.1:{port}"))).start()
    server.serve_forever()


if __name__ == "__main__":
    start_web_dashboard()
