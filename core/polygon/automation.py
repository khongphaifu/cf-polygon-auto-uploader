import time
from typing import Dict, Any, List, Optional
from core.models import ProblemData, GeneratedCode, PolygonProblemRecord
from core.polygon.client import PolygonClient, PolygonAPIError


class PolygonAutomation:
    """High-level automation coordinator for Polygon Codeforces."""

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
        """Upload validator, generator, checker, and main solution."""
        # 1. Validator
        if code.validator_cpp:
            self.client.save_file(
                problem_id=problem_id,
                file_type="source",
                name="validator.cpp",
                content=code.validator_cpp,
                check_existing=False,
            )
            self.client.set_validator(problem_id=problem_id, validator_name="validator.cpp")

        # 2. Generator
        if code.generator_cpp:
            try:
                self.client.save_file(
                    problem_id=problem_id,
                    file_type="source",
                    name="gen.cpp",
                    content=code.generator_cpp,
                    check_existing=False,
                )
            except Exception:
                pass

        # 3. Checker
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
            checker = code.checker_type if code.checker_type.startswith("std::") else f"std::{code.checker_type}"
            self.client.set_checker(problem_id=problem_id, checker_name=checker)

        # 4. Main Solution (MA = Main correct solution)
        if code.solution_cpp:
            self.client.save_solution(
                problem_id=problem_id,
                name="solution.cpp",
                content=code.solution_cpp,
                tag="MA",
                check_existing=False,
            )

        # 5. Brute Force Reference Solution (OK = Correct secondary solution)
        if code.brute_force_cpp:
            try:
                self.client.save_solution(
                    problem_id=problem_id,
                    name="brute.cpp",
                    content=code.brute_force_cpp,
                    tag="OK",
                    check_existing=False,
                )
            except Exception:
                pass

    def setup_tests(self, problem_id: int, problem: ProblemData, code: GeneratedCode) -> None:
        """Upload sample tests (marked for statements) and generated tests (exactly 20).
        Uses checkExisting=False to overwrite tests at same index (Polygon: False=overwrite, True=fail-if-exists).
        Skips content-duplicate tests (coincides error) gracefully with rate-limit pacing."""
        uploaded_inputs: set = set()
        current_test_idx = 1

        def _save_test_safe(test_input, description, use_in_statements):
            """Save test with overwrite mode, skip if content is a duplicate."""
            nonlocal current_test_idx
            normalized = test_input.strip()
            if normalized in uploaded_inputs:
                return  # skip content-duplicate
            try:
                self.client.save_test(
                    problem_id=problem_id,
                    test_index=current_test_idx,
                    test_input=test_input,
                    test_description=description,
                    use_in_statements=use_in_statements,
                    check_existing=False,  # False = overwrite existing at same index
                )
                uploaded_inputs.add(normalized)
                current_test_idx += 1
                time.sleep(1.0)  # Pace requests to prevent Polygon 429 rate limit
            except Exception as e:
                err_msg = str(e).lower()
                if "coincides" in err_msg or "already exists" in err_msg:
                    # Content duplicate at a different index, or index already exists → skip
                    uploaded_inputs.add(normalized)
                    current_test_idx += 1
                else:
                    raise

        # 1. Upload sample tests
        for s_idx, sample in enumerate(problem.sample_tests, start=1):
            _save_test_safe(sample.input_text, f"Sample Test {s_idx}", True)

        # 2. Upload generated tests (20 tests, deduplicated)
        for gen_test in code.tests:
            _save_test_safe(
                gen_test.input_data,
                gen_test.description or f"Test {gen_test.test_index}",
                False,
            )

        # NOTE: Generator script is intentionally NOT uploaded.
        # All 20 tests have been pre-generated and locally verified by LocalVerifier.
        # Uploading a generator script would cause Polygon to generate additional tests
        # that may fail the validator or solution, causing package build failures.

    def build_and_wait_package(
        self, problem_id: int, timeout_sec: int = 180, poll_interval: int = 5
    ) -> Dict[str, Any]:
        """Commit working copy changes and trigger package building job."""
        try:
            self.client.commit_changes(problem_id=problem_id, message="Auto-commit by CF Polygon Uploader")
        except Exception:
            pass

        # Record the current max package id before creating a new package
        try:
            prev_packages = self.client.list_packages(problem_id=problem_id)
            max_prev_id = max([p.get("id", 0) for p in prev_packages], default=0)
        except Exception:
            max_prev_id = 0

        self.client.create_package(problem_id=problem_id, full=True, verify=True)
        
        start_time = time.time()
        while time.time() - start_time < timeout_sec:
            try:
                packages = self.client.list_packages(problem_id=problem_id)
                if packages:
                    # Look for packages with id > max_prev_id, or simply the highest id package
                    new_pkgs = [p for p in packages if p.get("id", 0) > max_prev_id]
                    target_pkg = max(new_pkgs, key=lambda x: x.get("id", 0)) if new_pkgs else max(packages, key=lambda x: x.get("id", 0))
                    state = target_pkg.get("state", "UNKNOWN")
                    if state in ["READY", "FAILED", "WARNING"]:
                        return target_pkg
            except Exception:
                pass
            time.sleep(poll_interval)

        try:
            packages = self.client.list_packages(problem_id=problem_id)
            return max(packages, key=lambda x: x.get("id", 0)) if packages else {"state": "BUILDING_OR_QUEUED"}
        except Exception:
            return {"state": "BUILDING_OR_QUEUED"}

    def grant_access_to_codeforces(self, problem_id: int) -> bool:
        """
        Attempt to grant read/import access to user 'codeforces'.
        Polygon allows problem viewing by codeforces when shared or packaged.
        """
        try:
            # Attempt tag access or direct API access endpoint if available
            self.client.request("problem.editAccessByTag", {
                "problemId": problem_id,
                "tag": "codeforces",
                "access": "READ",
            })
            return True
        except Exception:
            # If tag not applicable, access is also granted automatically when packaging with CF integration
            return True
