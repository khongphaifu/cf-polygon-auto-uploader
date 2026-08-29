import time
from typing import Dict, Any, List, Optional, Callable
from core.models import ProblemData, GeneratedCode, PolygonProblemRecord
from core.polygon.client import PolygonClient, PolygonAPIError


class PolygonAutomation:
    """High-level automation coordinator for Polygon Codeforces with auto-repair and permission management."""

    def __init__(self, client: PolygonClient):
        self.client = client

    def get_or_create_problem(self, problem_name: str) -> Dict[str, Any]:
        """Check if problem exists; if not, create it."""
        try:
            problems = self.client.list_problems()
            for p in problems:
                if p.get("name") == problem_name:
                    return p
        except Exception:
            pass

        # Create new problem
        return self.client.create_problem(problem_name)

    def setup_problem_statement(self, problem_id: int, problem: ProblemData) -> None:
        """Update problem limits and save statement."""
        # 1. Update limits
        self.client.update_info(
            problem_id=problem_id,
            time_limit_ms=problem.time_limit_ms,
            memory_limit_mb=problem.memory_limit_mb,
            interactive=False,
        )

        # 2. Save Statement (English)
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

    def setup_code_files(self, problem_id: int, code: GeneratedCode) -> None:
        """Upload checker (default std::lcmp.cpp), main solution (MA tag) and generator (if present)."""
        # 1. Checker (Always use std::lcmp.cpp for line-by-line comparison unless custom checker is provided)
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

        # 2. Main Solution (MA = Main correct solution)
        if code.solution_cpp:
            self.client.save_solution(
                problem_id=problem_id,
                name="solution.cpp",
                content=code.solution_cpp,
                tag="MA",
                check_existing=False,
            )

        # 3. Generator (upload gen.cpp as source file so Polygon can compile it)
        if code.generator_cpp and code.generator_cpp.strip():
            self.client.save_file(
                problem_id=problem_id,
                file_type="source",
                name="gen.cpp",
                content=code.generator_cpp,
                source_type="cpp.g++17",
                check_existing=False,
            )

    def setup_tests(self, problem_id: int, problem: ProblemData, code: GeneratedCode) -> None:
        """Upload sample tests, then either use Polygon generator script (if gen.cpp present) or upload static tests."""
        uploaded_inputs: set = set()
        current_test_idx = 1

        def _save_test_safe(test_input, description, use_in_statements):
            """Save test with overwrite mode, skip if content is a duplicate."""
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
                    check_existing=False,
                )
                uploaded_inputs.add(normalized)
                current_test_idx += 1
                time.sleep(1.0)  # Pace requests to prevent Polygon rate limit
            except Exception as e:
                err_msg = str(e).lower()
                if "coincides" in err_msg or "already exists" in err_msg:
                    uploaded_inputs.add(normalized)
                    current_test_idx += 1
                else:
                    raise

        # 1. Upload sample tests (always with use_in_statements=True)
        for s_idx, sample in enumerate(problem.sample_tests, start=1):
            _save_test_safe(sample.input_text, f"Sample Test {s_idx}", True)

        # 2a. If generator exists: use Polygon FreeMarker script to generate large tests
        if code.generator_cpp and code.generator_cpp.strip():
            num_gen_tests = max(1, 20 - len(problem.sample_tests))
            script_lines = [f"<#list 1..{num_gen_tests} as i>", "    gen ${i} > $", "</#list>"]
            # Use custom script lines if provided by pipeline
            if hasattr(code, "test_script_lines") and code.test_script_lines:
                script_lines = code.test_script_lines
            script_content = "\n".join(script_lines)
            try:
                self.client.save_script(
                    problem_id=problem_id,
                    script_content=script_content,
                )
            except Exception as e:
                # Fallback to static upload if script fails
                for gen_test in code.tests:
                    _save_test_safe(
                        gen_test.input_data,
                        gen_test.description or f"Test {gen_test.test_index}",
                        False,
                    )
        else:
            # 2b. No generator: upload static tests as usual
            for gen_test in code.tests:
                _save_test_safe(
                    gen_test.input_data,
                    gen_test.description or f"Test {gen_test.test_index}",
                    False,
                )

    def grant_access_to_codeforces(self, problem_id: int) -> bool:
        """
        Save 'codeforces' tag on Polygon for seamless Codeforces Mashup / Contest import.
        """
        try:
            self.client.save_tags(problem_id, "codeforces")
            return True
        except Exception:
            return False

    def build_and_wait_package(
        self,
        problem_id: int,
        timeout_sec: int = 180,
        poll_interval: int = 5,
        problem: Optional[ProblemData] = None,
        code: Optional[GeneratedCode] = None,
        ai_pipeline: Optional[Any] = None,
        max_repair_retries: int = 2,
    ) -> Dict[str, Any]:
        """
        Commit changes and trigger package building job.
        Includes automatic self-healing retry loop if package build fails.
        """
        attempt = 0
        while attempt <= max_repair_retries:
            attempt += 1
            try:
                self.client.commit_changes(problem_id=problem_id, message=f"Auto-commit build attempt {attempt}")
            except Exception:
                pass

            # Record max prev package id
            try:
                prev_packages = self.client.list_packages(problem_id=problem_id)
                max_prev_id = max([p.get("id", 0) for p in prev_packages], default=0)
            except Exception:
                max_prev_id = 0

            try:
                self.client.create_package(problem_id=problem_id, full=True, verify=True)
            except Exception as e:
                if attempt > max_repair_retries:
                    return {"state": "FAILED", "error_message": f"Cannot create package on Polygon: {e}"}

            start_time = time.time()
            pkg_result = None

            while time.time() - start_time < timeout_sec:
                try:
                    packages = self.client.list_packages(problem_id=problem_id)
                    if packages:
                        new_pkgs = [p for p in packages if p.get("id", 0) > max_prev_id]
                        target_pkg = max(new_pkgs, key=lambda x: x.get("id", 0)) if new_pkgs else max(packages, key=lambda x: x.get("id", 0))
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
                    pkg_result = max(packages, key=lambda x: x.get("id", 0)) if packages else {"state": "BUILDING_OR_QUEUED"}
                except Exception:
                    pkg_result = {"state": "BUILDING_OR_QUEUED"}

            # If Package succeeded, return immediately
            if pkg_result.get("state") in ["READY", "WARNING"]:
                return pkg_result

            # If Package FAILED and we have retry attempts left, trigger Auto-Repair with AI
            if pkg_result.get("state") == "FAILED" and attempt <= max_repair_retries and ai_pipeline and problem and code:
                error_diag = f"Polygon Package {pkg_result.get('id')} failed verification. State: {pkg_result.get('state')}."
                try:
                    # Request AI to repair solution_cpp
                    fixed_code = ai_pipeline.fix_solution(problem, code.solution_cpp, error_diag)
                    if fixed_code and fixed_code != code.solution_cpp:
                        code.solution_cpp = fixed_code
                        # Re-verify locally
                        from core.ai_engine.local_verifier import LocalVerifier
                        verifier = LocalVerifier()
                        code = verifier.verify_and_clean(problem, code, target_num_tests=len(code.tests))
                        # Re-upload fixed solution
                        self.setup_code_files(problem_id, code)
                        continue
                except Exception:
                    pass

            # If no repair possible or final attempt reached
            if pkg_result.get("state") == "FAILED":
                comment = pkg_result.get("comment", "").strip()
                pkg_result["error_message"] = f"Polygon package {pkg_result.get('id', 'N/A')} failed: {comment}" if comment else f"Polygon package build failed on package {pkg_result.get('id', 'N/A')}."
                return pkg_result

            return pkg_result

        return {"state": "FAILED", "error_message": "Package build exceeded maximum repair attempts."}
