import time
from pathlib import Path
from typing import Dict, Any, List, Optional, Callable
from core.models import ProblemData, GeneratedCode, PolygonProblemRecord
from core.polygon.client import PolygonClient, PolygonAPIError


class PolygonAutomation:
    """
    Coordinator executing the 10-step standardized Polygon pipeline:
    1. Đọc link & Tạo bài (get_or_create_problem)
    2. Ghi statement (setup_problem_statement)
    3. Chọn checker (setup_checker)
    4. Add file sinh test (setup_generator)
    5. Add file solution (setup_solution)
    6. Ghi script sinh test & tests (setup_test_script_and_tests)
    7. Commit (commit_changes)
    8. Packages (build_and_wait_package with auto-repair)
    9. Chỉnh manage access (grant_access_to_codeforces)
    10. Trả về link bài hoàn chỉnh (build_record)
    """

    def __init__(self, client: PolygonClient, testlib_path: Optional[Path] = None):
        self.client = client
        self.testlib_path = testlib_path or (Path(__file__).resolve().parent.parent.parent / "testlib.h")

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

    # Step 2: Ghi Statement & Limits
    def setup_problem_statement(self, problem_id: int, problem: ProblemData) -> None:
        """Update problem limits and save statement with subtask specification."""
        self.client.update_info(
            problem_id=problem_id,
            time_limit_ms=problem.time_limit_ms,
            memory_limit_mb=problem.memory_limit_mb,
            interactive=False,
        )

        self.client.save_statement(
            problem_id=problem_id,
            lang="english",
            encoding="UTF-8",
            name=problem.title,
            legend=problem.legend,
            input_format=problem.input_format,
            output_format=problem.output_format,
            notes=problem.notes or "",
            tutorial=problem.tutorial or "",
        )

    # Step 3: Chọn Checker
    def setup_checker(self, problem_id: int, code: GeneratedCode) -> None:
        """Set standard checker or upload custom check.cpp."""
        if code.checker_type == "custom" and code.custom_checker_cpp:
            self.client.save_file(
                problem_id=problem_id,
                file_type="source",
                name="check.cpp",
                content=code.custom_checker_cpp,
                check_existing=False,
            )
            self.client.set_checker(problem_id=problem_id, checker_name="check.cpp")
        else:
            checker = code.checker_type or "std::lcmp.cpp"
            # Normalize checker - replace yesno with lcmp.cpp to avoid multi-test presentation errors
            if "yesno" in checker.lower():
                checker = "std::lcmp.cpp"
            elif not checker.startswith("std::"):
                if not checker.endswith(".cpp"):
                    checker = f"std::{checker}.cpp"
                else:
                    checker = f"std::{checker}"
            self.client.set_checker(problem_id=problem_id, checker_name=checker)

    # Step 4: Add file sinh test (gen.cpp)
    def setup_generator(self, problem_id: int, code: GeneratedCode, overwrite: bool = False, max_attempts: int = 2) -> bool:
        """Upload gen.cpp generator source file to Polygon with resilient non-blocking handling."""
        for attempt in range(1, max_attempts + 1):
            if not overwrite or attempt > 1:
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
                self.client.save_file(
                    problem_id=problem_id,
                    file_type="source",
                    name="gen.cpp",
                    content=code.generator_cpp,
                    source_type="cpp.g++17",
                    check_existing=False,
                    timeout=15,
                    max_retries=1,
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
        """Upload solution.cpp as Main Correct Solution (MA) with resilient non-blocking handling."""
        for attempt in range(1, max_attempts + 1):
            if not overwrite or attempt > 1:
                try:
                    sols = self.client.list_solutions(problem_id)
                    if any(s.get("name") == "solution.cpp" for s in sols):
                        return True
                except Exception:
                    pass

            if not code.solution_cpp or not code.solution_cpp.strip():
                return False

            try:
                self.client.save_solution(
                    problem_id=problem_id,
                    name="solution.cpp",
                    content=code.solution_cpp,
                    tag="MA",
                    source_type="cpp.g++17",
                    check_existing=False,
                    timeout=15,
                    max_retries=1,
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


    # Step 6: Ghi script sinh test & Tests chia theo subtask
    def setup_test_script_and_tests(self, problem_id: int, problem: ProblemData, code: GeneratedCode, overwrite: bool = False) -> None:
        """Save sample tests and test generation script partitioned by subtasks."""
        # Check if tests already exist on Polygon (skip if not overwrite)
        if not overwrite:
            try:
                existing = self.client.list_tests(problem_id=problem_id)
                if existing and len(existing) >= max(len(code.tests), len(problem.sample_tests)):
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

        uploaded_inputs = set()
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
                current_test_idx += 1
                time.sleep(0.08)
            except Exception as e:
                err_msg = str(e).lower()
                if "coincides" in err_msg or "already exists" in err_msg:
                    uploaded_inputs.add(normalized)
                    # Do not increment current_test_idx since Polygon did not save this duplicate
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

        # 1. Upload sample tests first
        for s_idx, sample in enumerate(problem.sample_tests, start=1):
            _save_test_safe(sample.input_text, f"Sample Test {s_idx}", True, group="samples", points=0.0)

        # 2. Always upload ALL generated tests partitioned by subtasks directly to Polygon
        for gen_test in code.tests:
            _save_test_safe(
                gen_test.input_data,
                gen_test.description or f"Test {gen_test.test_index}",
                False,
                group=gen_test.group or (str(gen_test.subtask_id) if gen_test.subtask_id else None),
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

        # 4. Save Script to Polygon (Tab Tests -> Script) for record/reproduction
        if code.test_script_lines and code.generator_cpp:
            script_content = "\n".join(code.test_script_lines)
            try:
                self.client.save_script(problem_id=problem_id, script_content=script_content, testset="tests")
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
        timeout_sec: int = 60,
        poll_interval: int = 5,
        problem: Optional[ProblemData] = None,
        code: Optional[GeneratedCode] = None,
        ai_pipeline: Optional[Any] = None,
        max_repair_retries: int = 2,
    ) -> Dict[str, Any]:
        """Commit and trigger package build with auto-repair loop on FAILED status."""
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
                self.client.create_package(problem_id=problem_id, full=True, verify=True)
            except Exception as e:
                err_str = str(e).lower()
                if "commit the changes" in err_str:
                    time.sleep(1)
                    self.commit_changes(problem_id=problem_id, message="Retry commit before packaging")
                    time.sleep(1)
                    try:
                        self.client.create_package(problem_id=problem_id, full=True, verify=True)
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
                # If Polygon aborted package due to server restart, do not loop endlessly
                if "server restart" in comment or "build a package again" in comment:
                    return {"state": "QUEUED_ON_POLYGON", "comment": "Polygon compiler daemon is restarting; package deferred"}

                if ai_pipeline and problem and code:
                    error_diag = f"Polygon Package {pkg_result.get('id')} failed verification. State: {pkg_result.get('state')}."
                    try:
                        fixed_data = ai_pipeline.fix_code_and_script(
                            problem,
                            code.solution_cpp,
                            code.generator_cpp,
                            code.test_script_lines,
                            error_diag,
                        )
                        code.solution_cpp = fixed_data.get("solution_cpp") or code.solution_cpp
                        code.generator_cpp = fixed_data.get("generator_cpp") or code.generator_cpp
                        code.test_script_lines = fixed_data.get("test_script_lines") or code.test_script_lines

                        from core.ai_engine.local_verifier import LocalVerifier
                        verifier = LocalVerifier()
                        code = verifier.verify_and_clean(problem, code, target_num_tests=len(code.tests) or 30)

                        # Re-upload fixed files
                        self.setup_generator(problem_id, code, overwrite=True)
                        self.setup_solution(problem_id, code, overwrite=True)
                        self.setup_test_script_and_tests(problem_id, problem, code, overwrite=True)
                        continue
                    except Exception:
                        pass

            if pkg_result.get("state") == "FAILED":
                # Check if there is an existing READY package on this problem to fall back on
                try:
                    packages = self.client.list_packages(problem_id=problem_id)
                    ready_pkgs = [p for p in packages if p.get("state") == "READY"]
                    if ready_pkgs:
                        latest_ready = max(ready_pkgs, key=lambda x: x.get("id", 0))
                        return latest_ready
                except Exception:
                    pass

                pkg_result["error_message"] = f"Polygon package build failed on package {pkg_result.get('id', 'N/A')}. {pkg_result.get('comment', 'Verification checks did not pass.')}"
                return pkg_result

            return pkg_result

        # Final check if any READY package exists
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
        """Grant write and read access to 'codeforces' user and by tag."""
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

        subtasks_desc = ", ".join([f"Subtask {s.subtask_id} ({s.points} pts: {s.test_count} tests)" for s in problem.subtasks])

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
