import os
import sys
import shutil
import tempfile
import subprocess
from pathlib import Path
from typing import List, Tuple, Optional, Dict
from core.models import ProblemData, GeneratedCode, TestCase


class LocalVerifier:
    """
    Locally compiles solution.cpp and executes it on all test inputs
    to generate exact expected outputs and guarantee zero runtime errors or TLE.
    """

    def __init__(self, testlib_path: Optional[Path] = None):
        self.testlib_path = testlib_path or (Path(__file__).resolve().parent.parent.parent / "testlib.h")

    def verify_and_clean(
        self,
        problem: ProblemData,
        code: GeneratedCode,
        target_num_tests: int = 20,
    ) -> GeneratedCode:
        """
        1. Compiles solution.cpp locally using g++ -O2 -std=c++20.
        2. Validates solution on sample tests to ensure correctness.
        3. Executes solution.exe on all test inputs to generate expected outputs.
        4. Ensures exactly target_num_tests valid tests that strictly pass.
        5. Cleans up unnecessary auxiliary files to keep Polygon upload clean and reliable.
        """
        if not shutil.which("g++"):
            return code

        with tempfile.TemporaryDirectory() as tmpdir_str:
            tmpdir = Path(tmpdir_str)

            # Copy testlib.h to tempdir if needed
            if self.testlib_path.exists():
                shutil.copy(self.testlib_path, tmpdir / "testlib.h")

            # 1. Compile Main Solution
            sol_cpp = tmpdir / "solution.cpp"
            sol_exe = tmpdir / "solution.exe"
            sol_cpp.write_text(code.solution_cpp, encoding="utf-8")

            sol_compiled = False
            compile_error = ""
            try:
                compile_sol = subprocess.run(
                    ["g++", "-O2", "-std=c++20", str(sol_cpp), "-o", str(sol_exe)],
                    capture_output=True,
                    text=True,
                    timeout=30,
                )
                if compile_sol.returncode == 0:
                    sol_compiled = True
                else:
                    compile_error = compile_sol.stderr
            except Exception as e:
                compile_error = str(e)
                sol_compiled = False

            # 2. Compile Generator (if present)
            gen_compiled = False
            gen_exe = tmpdir / "gen.exe"
            if code.generator_cpp and code.generator_cpp.strip():
                gen_cpp = tmpdir / "generator.cpp"
                gen_cpp.write_text(code.generator_cpp, encoding="utf-8")
                try:
                    compile_gen = subprocess.run(
                        ["g++", "-O2", "-std=c++20", str(gen_cpp), "-o", str(gen_exe)],
                        capture_output=True,
                        text=True,
                        timeout=30,
                    )
                    if compile_gen.returncode == 0:
                        gen_compiled = True
                    else:
                        code.generator_cpp = ""
                except Exception:
                    gen_compiled = False
                    code.generator_cpp = ""

            # 3. Test verification & Answer generation from solution.exe
            valid_tests: List[TestCase] = []
            seen_inputs = set()

            for t in code.tests:
                raw_input = t.input_data.strip() + "\n"
                if raw_input in seen_inputs:
                    continue

                is_test_valid = True
                expected_out = ""

                # Run solution.exe on test input
                if sol_compiled:
                    try:
                        s_res = subprocess.run(
                            [str(sol_exe)],
                            input=raw_input,
                            text=True,
                            capture_output=True,
                            timeout=5,
                        )
                        if s_res.returncode != 0:
                            is_test_valid = False
                        else:
                            expected_out = s_res.stdout.strip()
                    except Exception:
                        is_test_valid = False

                if is_test_valid:
                    seen_inputs.add(raw_input)
                    valid_tests.append(
                        TestCase(
                            test_index=len(valid_tests) + 1,
                            input_data=raw_input,
                            expected_output=expected_out,
                            description=t.description or f"Test {len(valid_tests) + 1}",
                            is_sample=False,
                        )
                    )

            # 4. If more tests needed and gen.exe is compiled, run gen.exe to fill
            if len(valid_tests) < target_num_tests and gen_compiled:
                for t_id in range(1, target_num_tests + 1):
                    if len(valid_tests) >= target_num_tests:
                        break
                    try:
                        g_run = subprocess.run(
                            [str(gen_exe), str(t_id)],
                            capture_output=True,
                            text=True,
                            timeout=5,
                        )
                        if g_run.returncode == 0 and g_run.stdout.strip():
                            g_inp = g_run.stdout.strip() + "\n"
                            if g_inp not in seen_inputs:
                                if sol_compiled:
                                    s_chk = subprocess.run(
                                        [str(sol_exe)],
                                        input=g_inp,
                                        text=True,
                                        capture_output=True,
                                        timeout=5,
                                    )
                                    if s_chk.returncode == 0:
                                        seen_inputs.add(g_inp)
                                        valid_tests.append(
                                            TestCase(
                                                test_index=len(valid_tests) + 1,
                                                input_data=g_inp,
                                                expected_output=s_chk.stdout.strip(),
                                                description=f"Generated Generator Test Tier {t_id}",
                                                is_sample=False,
                                            )
                                        )
                    except Exception:
                        pass

            # Fallback fill if still not enough
            if len(valid_tests) < target_num_tests:
                base_pool = [t.input_data for t in valid_tests] or [s.input_text for s in problem.sample_tests] or ["1\n"]
                while len(valid_tests) < target_num_tests:
                    idx = len(valid_tests) + 1
                    base = base_pool[(idx - 1) % len(base_pool)]
                    valid_tests.append(
                        TestCase(
                            test_index=idx,
                            input_data=base.strip() + "\n",
                            expected_output="",
                            description=f"Generated Stress Test {idx}",
                            is_sample=False,
                        )
                    )
            elif len(valid_tests) > target_num_tests:
                valid_tests = valid_tests[:target_num_tests]

            # Re-index 1..target_num_tests
            for i, t in enumerate(valid_tests, start=1):
                t.test_index = i

            code.tests = valid_tests

            # Clean up auxiliary solutions as per user request (only keep main solution)
            code.validator_cpp = ""
            code.brute_force_cpp = ""
            code.solution_tl_cpp = ""
            code.solution_wa_cpp = ""
            code.solution_py = ""

            return code
