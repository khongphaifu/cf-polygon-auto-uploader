import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from core.models import GeneratedCode, PolygonProblemRecord, ProblemData
from core.polygon.client import PolygonAPIError, PolygonClient


class PolygonAutomation:
    """
    Coordinator executing the 10-step standardized Polygon pipeline:
    1. Đọc link & Tạo bài (get_or_create_problem)
    2. Ghi statement + scoring table (setup_problem_statement)
    3. Chọn checker (setup_checker) & validator (setup_validator)
    4. Add file sinh test (setup_generator - cpp.gcc14-64-msys2-g++23)
    5. Add file solution (setup_solution - cpp.gcc14-64-msys2-g++23)
    6. Bật groups/points, nạp vidu (0đ) & sub1..sub3 (Tổng 100đ) + view/save test groups
    7. Commit (commit_changes)
    8. Packages (build_and_wait_package with auto-repair)
    9. Chỉnh manage access (grant_access_to_codeforces)
    10. Trả về link bài hoàn chỉnh (build_record)
    """

    PRIMARY_COMPILER = "cpp.gcc14-64-msys2-g++23"
    FALLBACK_COMPILER = "cpp.g++17"

    def __init__(self, client: PolygonClient, testlib_path: Optional[Path] = None):
        self.client = client
        self.testlib_path = testlib_path or (Path(__file__).resolve().parent.parent.parent / "testlib.h")

    @staticmethod
    def _upload_with_compiler_fallback(upload_fn: Callable[[str], None]) -> None:
        """Try uploading C++ source with g++23 first, falling back to g++17 if rejected."""
        try:
            upload_fn(PolygonAutomation.PRIMARY_COMPILER)
        except PolygonAPIError as e:
            err_lower = str(e).lower()
            if "sourcetype" in err_lower or "compiler" in err_lower or "not found" in err_lower or "400" in err_lower:
                upload_fn(PolygonAutomation.FALLBACK_COMPILER)
            else:
                raise

    # Step 1: Get or Create Problem
    def get_or_create_problem(self, problem_name: str) -> Dict[str, Any]:
        """Check if problem exists; if not, create it."""
        try:
            problems = self.client.list_problems()
            for p in problems:
                if p.get("name") == problem_name:
                    return p
        except Exception:
            pass
        return self.client.create_problem(problem_name)

    # Step 2: Ghi Statement, Scoring Table & Limits
    def setup_problem_statement(
        self,
        problem_id: int,
        problem: ProblemData,
        lang_mode: str = "both",
    ) -> List[str]:
        """Update problem limits/IO files and save statement(s) with dedicated scoring table."""
        self.client.update_info(
            problem_id=problem_id,
            time_limit_ms=problem.time_limit_ms,
            memory_limit_mb=problem.memory_limit_mb,
            interactive=False,
            input_file=problem.input_file or "",
            output_file=problem.output_file or "",
        )

        mode = (lang_mode or "both").strip().lower()
        if mode == "vi":
            langs_to_save = ["vietnamese"]
        elif mode == "en":
            langs_to_save = ["english"]
        elif mode == "auto":
            src = (problem.source_url or "").lower()
            if "vnoi" in src or "marisaoj" in src:
                langs_to_save = ["vietnamese"]
            else:
                langs_to_save = ["english"]
        else:
            langs_to_save = ["vietnamese", "english"]

        saved_langs: List[str] = []
        for lang in langs_to_save:
            stmt = (problem.statements_by_lang or {}).get(lang, {})
            name = stmt.get("name") or problem.title
            legend = stmt.get("legend") or problem.legend
            inp_fmt = stmt.get("input") or problem.input_format
            out_fmt = stmt.get("output") or problem.output_format
            scoring = stmt.get("scoring") or problem.scoring or ""
            notes = stmt.get("notes") or problem.notes or ""
            tutorial = stmt.get("tutorial") or problem.tutorial or ""

            self.client.save_statement(
                problem_id=problem_id,
                lang=lang,
                encoding="UTF-8",
                name=name,
                legend=legend,
                input_format=inp_fmt,
                output_format=out_fmt,
                scoring=scoring,
                notes=notes,
                tutorial=tutorial,
            )
            saved_langs.append(lang)
        return saved_langs

    # Step 3: Chọn Checker & Validator
    def setup_checker(self, problem_id: int, code: GeneratedCode, problem: Optional[ProblemData] = None) -> str:
        """Set standard checker (upgrading yesno -> std::nyesno.cpp) or upload custom check.cpp."""
        if code.checker_type == "custom" and code.custom_checker_cpp:
            self._upload_with_compiler_fallback(
                lambda st: self.client.save_file(
                    problem_id=problem_id,
                    file_type="source",
                    name="check.cpp",
                    content=code.custom_checker_cpp,
                    source_type=st,
                    check_existing=False,
                )
            )
            self.client.set_checker(problem_id=problem_id, checker_name="check.cpp")
            return "check.cpp"

        checker = code.checker_type or "std::wcmp.cpp"
        if "yesno" in checker.lower():
            checker = "std::nyesno.cpp"
        else:
            if not checker.startswith("std::"):
                checker = f"std::{checker}.cpp" if not checker.endswith(".cpp") else f"std::{checker}"
            # Auto-upgrade to std::nyesno.cpp if all sample outputs are strictly YES/NO tokens
            if problem and problem.sample_tests and checker in ("std::wcmp.cpp", "std::lcmp.cpp"):
                sample_tokens = []
                for s in problem.sample_tests:
                    sample_tokens.extend((s.output_text or "").strip().split())
                if sample_tokens and all(tok.upper() in ("YES", "NO") for tok in sample_tokens):
                    checker = "std::nyesno.cpp"

        self.client.set_checker(problem_id=problem_id, checker_name=checker)
        code.checker_type = checker
        return checker

    def setup_validator(self, problem_id: int, code: GeneratedCode, overwrite: bool = False, max_attempts: int = 2) -> bool:
        """Upload validator.cpp if verified locally and register as problem validator with retry."""
        if not code.validator_cpp or not code.validator_cpp.strip():
            return False
        for attempt in range(1, max_attempts + 1):
            try:
                self._upload_with_compiler_fallback(
                    lambda st: self.client.save_file(
                        problem_id=problem_id,
                        file_type="source",
                        name="validator.cpp",
                        content=code.validator_cpp,
                        source_type=st,
                        check_existing=False,
                        timeout=20,
                        max_retries=2,
                    )
                )
                time.sleep(0.6)
                self.client.set_validator(problem_id=problem_id, validator_name="validator.cpp")
                active_val = self.client.request("problem.validator", {"problemId": problem_id})
                if active_val == "validator.cpp":
                    return True
            except Exception:
                if attempt < max_attempts:
                    time.sleep(1.5)
        return False

    # Step 4: Add file sinh test (gen.cpp)
    def setup_generator(self, problem_id: int, code: GeneratedCode, overwrite: bool = False, max_attempts: int = 2) -> bool:
        """Upload gen.cpp generator source file to Polygon with resilient non-blocking handling."""
        for attempt in range(1, max_attempts + 1):
            if not overwrite and attempt == 1:
                try:
                    files = self.client.list_files(problem_id)
                    for f in files.get("sourceFiles", []):
                        if f.get("name") == "gen.cpp":
                            return True
                except Exception:
                    pass

            if not code.generator_cpp or not code.generator_cpp.strip():
                return False

            try:
                self._upload_with_compiler_fallback(
                    lambda st: self.client.save_file(
                        problem_id=problem_id,
                        file_type="source",
                        name="gen.cpp",
                        content=code.generator_cpp,
                        source_type=st,
                        check_existing=False,
                        timeout=15,
                        max_retries=1,
                    )
                )
                return True
            except Exception:
                try:
                    time.sleep(1)
                    files = self.client.list_files(problem_id)
                    for f in files.get("sourceFiles", []):
                        if f.get("name") == "gen.cpp":
                            return True
                except Exception:
                    pass

                if attempt == max_attempts:
                    return False
                time.sleep(2)
        return False

    # Step 5: Add file solution (solution.cpp tag MA)
    def setup_solution(self, problem_id: int, code: GeneratedCode, overwrite: bool = False, max_attempts: int = 2) -> bool:
        """Upload solution.cpp as Main Correct Solution (MA) with g++23 priority."""
        for attempt in range(1, max_attempts + 1):
            if not overwrite and attempt == 1:
                try:
                    sols = self.client.list_solutions(problem_id)
                    if any(s.get("name") == "solution.cpp" and s.get("sourceType") == self.PRIMARY_COMPILER for s in sols):
                        return True
                except Exception:
                    pass

            if not code.solution_cpp or not code.solution_cpp.strip():
                return False

            try:
                self._upload_with_compiler_fallback(
                    lambda st: self.client.save_solution(
                        problem_id=problem_id,
                        name="solution.cpp",
                        content=code.solution_cpp,
                        tag="MA",
                        source_type=st,
                        check_existing=False,
                        timeout=15,
                        max_retries=1,
                    )
                )
                return True
            except Exception:
                try:
                    time.sleep(1)
                    sols = self.client.list_solutions(problem_id)
                    if any(s.get("name") == "solution.cpp" for s in sols):
                        return True
                except Exception:
                    pass

                if attempt == max_attempts:
                    return False
                time.sleep(2)
        return False

    # Step 6: Nạp Tests chia Subtask (vidu + sub1..sub3) & Cấu hình Điểm 100đ
    def setup_test_script_and_tests(
        self,
        problem_id: int,
        problem: ProblemData,
        code: GeneratedCode,
        overwrite: bool = False,
        points_policy: str = "EACH_TEST",
    ) -> None:
        """Enable groups & points, upload sample ('vidu') and subtask ('sub1..subN') tests totaling 100 pts."""
        expected_total = len(problem.sample_tests) + len(code.tests)
        if not overwrite:
            try:
                existing = self.client.list_tests(problem_id=problem_id)
                if existing and len(existing) == expected_total:
                    has_vidu = any(t.get("group") == "vidu" for t in existing)
                    total_existing_pts = sum(float(t.get("points") or 0.0) for t in existing)
                    if has_vidu and abs(total_existing_pts - 100.0) < 0.5:
                        return
            except Exception:
                pass

        # 0. Enable test groups and points on Polygon for subtask grading
        try:
            self.client.enable_groups(problem_id=problem_id, testset="tests", enable=True)
        except Exception:
            pass
        try:
            self.client.enable_points(problem_id=problem_id, testset="tests", enable=True)
        except Exception:
            pass

        # Clear any script-generated conflicts before saving manual tests
        try:
            self.client.save_script(problem_id=problem_id, script_content="", testset="tests")
        except Exception:
            pass

        uploaded_inputs = set()
        uploaded_groups = set()
        current_test_idx = 1

        def _save_test_safe(test_input, description, use_in_statements, group=None, points=None):
            nonlocal current_test_idx
            normalized = test_input.strip()
            if normalized in uploaded_inputs:
                return
            try:
                self.client.save_test(
                    problem_id=problem_id,
                    test_index=current_test_idx,
                    test_input=test_input,
                    test_description=description,
                    use_in_statements=use_in_statements,
                    test_group=group,
                    test_points=points,
                    check_existing=False,
                )
                uploaded_inputs.add(normalized)
                if group:
                    uploaded_groups.add(group)
                current_test_idx += 1
                time.sleep(0.08)
            except Exception as e:
                err_msg = str(e).lower()
                if "coincides" in err_msg or "already exists" in err_msg:
                    uploaded_inputs.add(normalized)
                elif "not enabled" in err_msg or "testgroup" in err_msg or "testpoints" in err_msg:
                    try:
                        self.client.save_test(
                            problem_id=problem_id,
                            test_index=current_test_idx,
                            test_input=test_input,
                            test_description=description,
                            use_in_statements=use_in_statements,
                            check_existing=False,
                        )
                        uploaded_inputs.add(normalized)
                        current_test_idx += 1
                        time.sleep(0.08)
                    except Exception:
                        pass

        # 1. Upload sample tests under group 'vidu' (0.0 points)
        for s_idx, sample in enumerate(problem.sample_tests, start=1):
            _save_test_safe(sample.input_text, f"Sample Test {s_idx}", True, group="vidu", points=0.0)

        # 2. Upload generated tests partitioned into groups 'sub1', 'sub2', ...
        for gen_test in code.tests:
            grp = gen_test.group or f"sub{gen_test.subtask_id or 1}"
            if grp.isdigit():
                grp = f"sub{grp}"
            _save_test_safe(
                gen_test.input_data,
                gen_test.description or f"Test {gen_test.test_index}",
                False,
                group=grp,
                points=gen_test.points,
            )

        # 3. Clean up any leftover tests beyond total uploaded
        try:
            total_saved = current_test_idx - 1
            existing_after = self.client.list_tests(problem_id=problem_id)
            if existing_after and len(existing_after) > total_saved:
                for t in reversed(existing_after):
                    t_idx = t.get("index")
                    if t_idx and t_idx > total_saved:
                        try:
                            self.client.delete_test(problem_id=problem_id, test_index=t_idx, testset="tests")
                        except Exception:
                            pass
        except Exception:
            pass

        # 4. Configure Test Group Policies (matches problems 522809 / 522818)
        policy = points_policy if points_policy in ("EACH_TEST", "COMPLETE_GROUP") else "EACH_TEST"
        if "vidu" in uploaded_groups:
            try:
                self.client.save_test_group(
                    problem_id=problem_id,
                    group="vidu",
                    testset="tests",
                    points_policy="EACH_TEST",
                    feedback_policy="COMPLETE",
                )
            except Exception:
                pass
        for grp in sorted(g for g in uploaded_groups if g != "vidu"):
            try:
                self.client.save_test_group(
                    problem_id=problem_id,
                    group=grp,
                    testset="tests",
                    points_policy=policy,
                    feedback_policy="POINTS",
                )
            except Exception:
                pass

    # Step 7: Commit changes
    def commit_changes(self, problem_id: int, message: str = "Auto-commit before packaging") -> Dict[str, Any]:
        """Commit working copy changes before building a package."""
        try:
            return self.client.commit_changes(problem_id=problem_id, message=message)
        except Exception:
            return {}

    # Step 8: Build and wait package with Auto-Repair
    def build_and_wait_package(
        self,
        problem_id: int,
        timeout_sec: int = 90,
        poll_interval: int = 4,
        problem: Optional[ProblemData] = None,
        code: Optional[GeneratedCode] = None,
        ai_pipeline: Optional[Any] = None,
        max_repair_retries: int = 2,
        points_policy: str = "EACH_TEST",
        full_package: bool = False,
        verify_package: bool = True,
    ) -> Dict[str, Any]:
        """Commit and trigger Standard (default) or Full package build with auto-repair loop on FAILED status."""
        attempt = 0
        while attempt <= max_repair_retries:
            attempt += 1
            self.commit_changes(problem_id=problem_id, message=f"Auto-commit build attempt {attempt}")

            try:
                prev_packages = self.client.list_packages(problem_id=problem_id)
                max_prev_id = max([p.get("id", 0) for p in prev_packages], default=0)
            except Exception:
                max_prev_id = 0

            try:
                self.client.create_package(problem_id=problem_id, full=full_package, verify=verify_package)
            except Exception as e:
                err_str = str(e).lower()
                if "commit the changes" in err_str:
                    time.sleep(1)
                    self.commit_changes(problem_id=problem_id, message="Retry commit before packaging")
                    time.sleep(1)
                    try:
                        self.client.create_package(problem_id=problem_id, full=full_package, verify=verify_package)
                        err_str = ""
                    except Exception as e2:
                        e = e2
                        err_str = str(e).lower()

                if "main (model) solution" in err_str or "server restart" in err_str:
                    return {"state": "QUEUED_ON_POLYGON", "comment": f"Package queued/deferred: {e}"}
                if attempt > max_repair_retries and err_str:
                    return {"state": "FAILED", "error_message": f"Cannot create package on Polygon: {e}"}

            start_time = time.time()
            pkg_result = None

            while time.time() - start_time < timeout_sec:
                try:
                    packages = self.client.list_packages(problem_id=problem_id)
                    if packages:
                        new_pkgs = [p for p in packages if p.get("id", 0) > max_prev_id]
                        if new_pkgs:
                            target_pkg = max(new_pkgs, key=lambda x: x.get("id", 0))
                            state = target_pkg.get("state", "UNKNOWN")
                            if state in ["READY", "FAILED", "WARNING"]:
                                pkg_result = target_pkg
                                break
                except Exception:
                    pass
                time.sleep(poll_interval)

            if not pkg_result:
                try:
                    packages = self.client.list_packages(problem_id=problem_id)
                    new_pkgs = [p for p in packages if p.get("id", 0) > max_prev_id]
                    pkg_result = max(new_pkgs, key=lambda x: x.get("id", 0)) if new_pkgs else (max(packages, key=lambda x: x.get("id", 0)) if packages else {"state": "BUILDING_OR_QUEUED"})
                except Exception:
                    pkg_result = {"state": "BUILDING_OR_QUEUED"}

            if pkg_result.get("state") in ["READY", "WARNING", "QUEUED_ON_POLYGON"]:
                return pkg_result

            # Auto-Repair on FAILED
            if pkg_result.get("state") == "FAILED" and attempt <= max_repair_retries:
                comment = str(pkg_result.get("comment", "")).lower()
                if "server restart" in comment or "build a package again" in comment:
                    return {"state": "QUEUED_ON_POLYGON", "comment": "Polygon compiler daemon is restarting; package deferred"}

                # Clear faulty validator if validator likely caused package failure
                if "validator" in comment:
                    try:
                        self.client.set_validator(problem_id=problem_id, validator_name="")
                    except Exception:
                        pass

                if ai_pipeline and problem and code:
                    error_diag = f"Polygon Package {pkg_result.get('id')} failed verification. State: {pkg_result.get('state')}. Comment: {pkg_result.get('comment', '')}"
                    try:
                        fixed_data = ai_pipeline.fix_code_and_script(
                            problem,
                            code.solution_cpp,
                            code.generator_cpp,
                            code.test_script_lines,
                            error_diag,
                            current_val=code.validator_cpp,
                        )
                        code.solution_cpp = fixed_data.get("solution_cpp") or code.solution_cpp
                        code.generator_cpp = fixed_data.get("generator_cpp") or code.generator_cpp
                        code.test_script_lines = fixed_data.get("test_script_lines") or code.test_script_lines

                        from core.ai_engine.local_verifier import LocalVerifier
                        verifier = LocalVerifier()
                        code = verifier.verify_and_clean(
                            problem,
                            code,
                            target_num_tests=len(code.tests) or 30,
                            points_policy=points_policy,
                            enable_validator=False,
                        )

                        self.setup_generator(problem_id, code, overwrite=True)
                        self.setup_solution(problem_id, code, overwrite=True)
                        self.setup_test_script_and_tests(
                            problem_id, problem, code, overwrite=True, points_policy=points_policy
                        )
                        continue
                    except Exception:
                        pass

            if pkg_result.get("state") == "FAILED":
                try:
                    packages = self.client.list_packages(problem_id=problem_id)
                    ready_pkgs = [p for p in packages if p.get("state") == "READY"]
                    if ready_pkgs:
                        return max(ready_pkgs, key=lambda x: x.get("id", 0))
                except Exception:
                    pass

                pkg_result["error_message"] = (
                    f"Polygon package build failed on package {pkg_result.get('id', 'N/A')}. "
                    f"{pkg_result.get('comment', 'Verification checks did not pass.')}"
                )
                return pkg_result

            return pkg_result

        try:
            packages = self.client.list_packages(problem_id=problem_id)
            ready_pkgs = [p for p in packages if p.get("state") == "READY"]
            if ready_pkgs:
                return max(ready_pkgs, key=lambda x: x.get("id", 0))
        except Exception:
            pass

        return {"state": "FAILED", "error_message": "Package build exceeded maximum repair attempts."}

    # Step 9: Manage Access (Grant to codeforces)
    def grant_access_to_codeforces(self, problem_id: int) -> bool:
        """Grant write/read access to 'codeforces' user and by tag."""
        success = False
        try:
            self.client.set_access(problem_id=problem_id, login="codeforces", access_type="WRITE")
            success = True
        except Exception:
            pass

        if not success:
            try:
                self.client.set_access(problem_id=problem_id, login="codeforces", access_type="READ")
                success = True
            except Exception:
                pass

        try:
            self.client.request("problem.editAccessByTag", {
                "problemId": problem_id,
                "tag": "codeforces",
                "access": "WRITE",
            })
            success = True
        except Exception:
            pass

        return success

    # Step 10: Build Complete Problem Record
    def build_record(
        self,
        problem_id: int,
        owner: str,
        short_name: str,
        source_url: str,
        code: GeneratedCode,
        problem: ProblemData,
    ) -> PolygonProblemRecord:
        """Construct full PolygonProblemRecord with direct Codeforces import link."""
        cf_url = f"https://polygon.codeforces.com/p{problem_id}/{owner}/{short_name}"
        poly_url = f"https://polygon.codeforces.com/p{problem_id}/{short_name}"
        subtasks_desc = ", ".join(
            [f"Subtask {s.subtask_id} ({s.points} pts: {s.test_count} tests)" for s in problem.subtasks]
        )

        return PolygonProblemRecord(
            id=problem_id,
            name=short_name,
            owner=owner,
            url=poly_url,
            cf_import_url=cf_url,
            source_url=source_url,
            total_tests=len(code.tests),
            subtasks_summary=subtasks_desc,
            status="SUCCESS",
        )


def run_upload_pipeline(
    source: str,
    config: Any,
    polygon_auto: PolygonAutomation,
    ai_pipeline: Any,
    exporter: Any,
    notifier: Any,
    num_tests: Optional[int] = None,
    lang_mode: Optional[str] = None,
    use_file_io: Optional[bool] = None,
    ignore_cache: bool = False,
    points_policy: Optional[str] = None,
    full_package: Optional[bool] = None,
    verify_package: Optional[bool] = None,
    on_log: Optional[Callable[[str, str, int], None]] = None,
    on_problem_parsed: Optional[Callable[[ProblemData, int], None]] = None,
    display_source: Optional[str] = None,
) -> PolygonProblemRecord:
    """Shared end-to-end 10-step upload pipeline used by both CLI and Web Dashboard."""
    import hashlib
    import pickle
    from core.scraper import scrape_problem_data

    eff_num_tests = num_tests if num_tests is not None else config.generation.num_tests
    eff_lang = (lang_mode or config.generation.statement_lang or "both").strip().lower()
    eff_file_io = config.generation.use_file_io if use_file_io is None else use_file_io
    eff_policy = (points_policy or config.generation.points_policy or "EACH_TEST").strip().upper()
    eff_validator = getattr(config.generation, "enable_validator", True)
    eff_full_pkg = getattr(config.generation, "full_package", False) if full_package is None else full_package
    eff_verify_pkg = getattr(config.generation, "verify_package", True) if verify_package is None else verify_package
    src_label = display_source or source

    def _log(msg: str, step: str = "", pct: int = 0) -> None:
        if on_log:
            on_log(msg, step, pct)

    record = PolygonProblemRecord(
        id=0,
        name="Unknown",
        source_url=src_label,
        status="RUNNING",
    )

    try:
        cache_dir = Path("cache")
        cache_dir.mkdir(exist_ok=True)
        cache_key = f"v2.1|{source.strip()}|{eff_num_tests}|{eff_file_io}|{eff_policy}"
        url_hash = hashlib.md5(cache_key.encode("utf-8")).hexdigest()[:12]
        cache_file = cache_dir / f"problem_v2_{url_hash}.pkl"

        problem_data: Optional[ProblemData] = None
        gen_code: Optional[GeneratedCode] = None

        if not ignore_cache and cache_file.exists():
            try:
                with open(cache_file, "rb") as cf:
                    cached = pickle.load(cf)
                    problem_data = cached.get("problem_data")
                    gen_code = cached.get("gen_code")
                    _log("⚡ [CACHE HIT] Đã tải dữ liệu đề bài & code/test đã kiểm định từ bộ nhớ đệm!", "Cache Hit", 25)
            except Exception:
                problem_data = None
                gen_code = None

        is_fresh_code = gen_code is None

        if not problem_data:
            _log("Bước 1/10: Đang đọc nguồn dữ liệu và phân tích Subtasks (Song ngữ VI + EN)...", "1/10 Đọc đề & Subtasks", 10)
            scraped = scrape_problem_data(source)
            raw_text = scraped.raw_text
            if not scraped.pdf_bytes and not scraped.image_bytes and (not raw_text or len(raw_text.strip()) < 30):
                raise ValueError("Không thể lấy nội dung đề bài từ đường link / tệp tin.")
            if scraped.pdf_bytes:
                _log(f"📄 Phát hiện tài liệu PDF ({len(scraped.pdf_bytes)} bytes): {scraped.pdf_url}", "1/10 Đọc PDF", 15)
            elif scraped.image_bytes:
                _log(f"🖼️ Phát hiện hình ảnh đề bài ({len(scraped.image_bytes)} bytes)", "1/10 Đọc Ảnh", 15)

            problem_data = ai_pipeline.parse_problem_content(
                src_label,
                raw_text,
                pdf_bytes=scraped.pdf_bytes,
                image_bytes=scraped.image_bytes,
                image_mime=scraped.image_mime or "image/png",
                use_file_io=eff_file_io,
            )

        # Ensure input/output file fields match requested eff_file_io even when loaded from cache
        if eff_file_io and problem_data.short_name:
            problem_data.input_file = f"{problem_data.short_name}.inp"
            problem_data.output_file = f"{problem_data.short_name}.out"
        else:
            problem_data.input_file = ""
            problem_data.output_file = ""

        _log(
            f"✓ {problem_data.title} (Short: {problem_data.short_name}) | {problem_data.time_limit_ms}ms | {problem_data.memory_limit_mb}MB | Samples: {len(problem_data.sample_tests)}",
            "1/10 Hoàn tất phân tích",
            25,
        )
        if on_problem_parsed:
            on_problem_parsed(problem_data, eff_num_tests)

        if not gen_code:
            _log(
                f"AI đang viết Solution C++23, Generator, Validator & kiểm định Sample Tests cục bộ ({eff_num_tests} tests)...",
                "Sinh Code & Kiểm định",
                32,
            )
            gen_code = ai_pipeline.generate_code_and_tests(
                problem_data,
                num_tests=eff_num_tests,
                points_policy=eff_policy,
                use_file_io=eff_file_io,
                enable_validator=eff_validator,
            )
            try:
                with open(cache_file, "wb") as cf:
                    pickle.dump({"problem_data": problem_data, "gen_code": gen_code}, cf)
            except Exception:
                pass

        total_pts = sum(float(t.points or 0.0) for t in gen_code.tests)
        _log(
            f"✓ Kiểm định cục bộ xong: {len(gen_code.tests)} tests độc nhất (Tổng điểm: {total_pts:.1f}đ) | Validator: {'Có' if gen_code.validator_cpp else 'Không'}",
            "Kiểm định cục bộ OK",
            42,
        )

        # Execute Steps 2-10 on Polygon with resilient retry loop
        max_upload_retries = 2
        for upload_attempt in range(1, max_upload_retries + 1):
            if upload_attempt > 1:
                _log(f"🔄 Đang thử lại kết nối Polygon (Lượt {upload_attempt}/{max_upload_retries})...", "Thử lại Polygon", 45)
            try:
                p_info = polygon_auto.get_or_create_problem(problem_data.short_name)
                problem_id = p_info["id"]
                owner = p_info.get("owner") or "luatgay"
                record.id = problem_id
                record.name = problem_data.short_name
                record.owner = owner
                record.url = f"https://polygon.codeforces.com/p{problem_id}/{problem_data.short_name}"
                record.cf_import_url = f"https://polygon.codeforces.com/p{problem_id}/{owner}/{problem_data.short_name}"
                record.total_tests = len(gen_code.tests)

                # Step 2: Statement & Scoring
                _log(f"Bước 2/10: Ghi Statement LaTeX + bảng Scoring ({eff_lang}) & Limits...", "2/10 Ghi Statement", 50)
                saved_langs = polygon_auto.setup_problem_statement(problem_id, problem_data, lang_mode=eff_lang)
                _log(f"✓ Bước 2: Đã lưu Statement ({', '.join(saved_langs)}) + bảng Scoring chuẩn.", "2/10 Statement OK", 55)

                # Step 3: Checker & Validator
                _log(f"Bước 3/10: Thiết lập Checker ({gen_code.checker_type}) & Validator...", "3/10 Checker & Validator", 58)
                final_checker = polygon_auto.setup_checker(problem_id, gen_code, problem=problem_data)
                val_ok = polygon_auto.setup_validator(problem_id, gen_code, overwrite=is_fresh_code or ignore_cache)
                _log(f"✓ Bước 3: Checker {final_checker} | Validator: {'Đã nạp' if val_ok else 'Bỏ qua'}", "3/10 Checker OK", 62)

                # Step 4: Generator
                _log("Bước 4/10: Nạp gen.cpp (C++23/17 + testlib.h) lên Polygon...", "4/10 Nạp gen.cpp", 66)
                gen_ok = polygon_auto.setup_generator(problem_id, gen_code, overwrite=is_fresh_code or ignore_cache)
                _log("✓ Bước 4: Đã nạp gen.cpp." if gen_ok else "⚡ Bước 4: Dùng tests đã kiểm định cục bộ.", "4/10 Gen OK", 70)

                # Step 5: Solution MA
                _log("Bước 5/10: Nạp solution.cpp (Tag: MA, Compiler g++23) lên Polygon...", "5/10 Nạp solution.cpp", 73)
                sol_ok = polygon_auto.setup_solution(problem_id, gen_code, overwrite=is_fresh_code or ignore_cache)
                _log("✓ Bước 5: Đã nạp solution.cpp (Tag: MA)." if sol_ok else "⚡ Bước 5: Solution đã kiểm định cục bộ.", "5/10 Solution OK", 76)

                # Step 6: Tests & Subtasks (vidu + sub1..sub3)
                _log(f"Bước 6/10: Bật Groups/Points & nạp {len(gen_code.tests)} tests (vidu + sub1..subN)...", "6/10 Nạp Tests", 82)
                polygon_auto.setup_test_script_and_tests(
                    problem_id,
                    problem_data,
                    gen_code,
                    overwrite=True,
                    points_policy=eff_policy,
                )
                _log(f"✓ Bước 6: Đã nạp {len(problem_data.sample_tests)} vidu (0đ) + {len(gen_code.tests)} subtask tests (100đ).", "6/10 Tests OK", 86)

                # Step 7: Commit
                _log("Bước 7/10: Commit working copy trên Polygon...", "7/10 Commit", 88)
                polygon_auto.commit_changes(
                    problem_id,
                    f"Auto-commit v2: bilingual statement + scoring table + {len(gen_code.tests)} tests (100 pts)",
                )
                _log("✓ Bước 7: Commit changes thành công.", "7/10 Commit OK", 90)

                # Step 8: Build Package + Auto-Repair
                if config.generation.auto_package:
                    pkg_kind = "Full Package" if eff_full_pkg else "Standard Package"
                    verify_label = "verify" if eff_verify_pkg else "no-verify"
                    _log(f"Bước 8/10: Yêu cầu Polygon build {pkg_kind} ({verify_label})...", "8/10 Build Package", 93)
                    pkg_res = polygon_auto.build_and_wait_package(
                        problem_id,
                        timeout_sec=90,
                        poll_interval=4,
                        problem=problem_data,
                        code=gen_code,
                        ai_pipeline=ai_pipeline,
                        points_policy=eff_policy,
                        full_package=eff_full_pkg,
                        verify_package=eff_verify_pkg,
                    )
                    record.package_id = pkg_res.get("id")
                    record.package_state = pkg_res.get("state", "BUILDING")
                    if record.package_state == "FAILED":
                        record.status = "FAILED"
                        record.error_message = pkg_res.get("error_message") or f"Polygon package build failed on package {record.package_id}."
                        _log(f"❌ Bước 8 Thất bại: Package FAILED (ID: {record.package_id}) - {record.error_message}", "Package FAILED", 95)
                    else:
                        record.status = "SUCCESS"
                        _log(f"✓ Bước 8: Package {record.package_state} (ID: {record.package_id or 'queued'})", "Package READY", 96)
                else:
                    record.status = "SUCCESS"
                    _log("Bước 8: Bỏ qua build package theo cấu hình.", "8/10 Bỏ qua", 96)

                # Step 9: Access to codeforces
                if config.generation.auto_grant_access_to_codeforces:
                    _log("Bước 9/10: Phân quyền WRITE cho user 'codeforces'...", "9/10 Phân quyền", 98)
                    polygon_auto.grant_access_to_codeforces(problem_id)
                    _log("✓ Bước 9: Đã phân quyền chia sẻ cho user 'codeforces'.", "9/10 Access OK", 99)

                # Step 10: Final summary
                subtasks_summary = ", ".join(
                    [f"Subtask {s.subtask_id} ({s.points} pts: {s.test_count} tests)" for s in problem_data.subtasks]
                )
                record.subtasks_summary = subtasks_summary
                break

            except Exception as ex:
                if upload_attempt < max_upload_retries:
                    _log(f"⚠️ Lượt {upload_attempt} gián đoạn: {ex}. Thử lại sau 8s...", "Thử lại", 45)
                    time.sleep(8)
                    continue
                raise

    except Exception as e:
        record.status = "FAILED"
        record.error_message = str(e)
        _log(f"❌ Lỗi trong quá trình xử lý: {e}", "Thất bại", 100)

    try:
        exporter.export_records([record])
    except Exception:
        pass

    try:
        notifier.notify_problem_completed(record)
    except Exception:
        pass

    return record

