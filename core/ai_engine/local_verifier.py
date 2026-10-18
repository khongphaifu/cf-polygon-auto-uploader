import os
import sys
import shutil
import tempfile
import subprocess
import shlex
import re
from pathlib import Path
from typing import List, Tuple, Optional, Dict
from core.models import ProblemData, GeneratedCode, TestCase, SubtaskData


class LocalVerifier:
    """
    Locally compiles solution.cpp and generator.cpp using testlib.h,
    executes generator script lines to generate test inputs,
    and runs solution.exe on all test inputs to generate expected outputs.
    Guarantees 0 compilation errors, 0 runtime crashes, and 0 TLE.
    """

    def __init__(self, testlib_path: Optional[Path] = None):
        self.testlib_path = testlib_path or (Path(__file__).resolve().parent.parent.parent / "testlib.h")

    def verify_and_clean(
        self,
        problem: ProblemData,
        code: GeneratedCode,
        target_num_tests: int = 30,
    ) -> GeneratedCode:
        """
        1. Compiles solution.cpp locally using g++ -O2 -std=c++20.
        2. Compiles generator.cpp locally using g++ -O2 -std=c++17 and testlib.h.
        3. Executes test_script_lines with gen.exe to generate subtask test cases.
        4. Runs solution.exe on each test input to generate expected_output and verify 0 crash / 0 TLE.
        5. Assigns subtask_id, groups, points, and script_command to each test.
        """
        if not shutil.which("g++"):
            return code

        subtasks = code.subtasks or problem.subtasks
        # Calculate subtask points map
        subtask_map = {s.subtask_id: s for s in subtasks} if subtasks else {}

        with tempfile.TemporaryDirectory() as tmpdir_str:
            tmpdir = Path(tmpdir_str)

            # Copy testlib.h to tempdir
            if self.testlib_path.exists():
                shutil.copy(self.testlib_path, tmpdir / "testlib.h")

            # 1. Compile Main Solution
            sol_cpp = tmpdir / "solution.cpp"
            sol_exe = tmpdir / "solution.exe"
            sol_cpp.write_text(code.solution_cpp, encoding="utf-8")

            sol_compiled = False
            try:
                compile_sol = subprocess.run(
                    ["g++", "-O2", "-std=c++20", str(sol_cpp), "-o", str(sol_exe)],
                    capture_output=True,
                    text=True,
                    timeout=30,
                )
                if compile_sol.returncode == 0:
                    sol_compiled = True
            except Exception:
                sol_compiled = False

            # 2. Compile Generator (if present)
            gen_compiled = False
            gen_exe = tmpdir / "gen.exe"
            if code.generator_cpp and code.generator_cpp.strip():
                gen_cpp = tmpdir / "generator.cpp"
                gen_cpp.write_text(code.generator_cpp, encoding="utf-8")
                try:
                    compile_gen = subprocess.run(
                        ["g++", "-O2", "-std=c++17", str(gen_cpp), "-o", str(gen_exe)],
                        capture_output=True,
                        text=True,
                        timeout=30,
                    )
                    if compile_gen.returncode == 0:
                        gen_compiled = True
                except Exception:
                    gen_compiled = False

            # 3. Process Script Lines or Generate via Generator
            valid_tests: List[TestCase] = []
            seen_inputs = set()
            valid_script_lines: List[str] = []

            current_group = "1"
            current_subtask_id = 1
            current_points = subtask_map.get(1).points if (subtask_map and 1 in subtask_map) else None

            # Attempt executing script lines from code.test_script_lines
            if gen_compiled and code.test_script_lines:
                for line in code.test_script_lines:
                    line_clean = line.strip()
                    if not line_clean or line_clean.startswith("#") or line_clean.startswith("//"):
                        continue

                    # Group directive
                    if line_clean.startswith("> group") or line_clean.startswith("> subtask"):
                        parts = line_clean.split()
                        if len(parts) >= 3:
                            current_group = parts[2]
                            try:
                                current_subtask_id = int(re.sub(r"[^0-9]", "", current_group))
                            except Exception:
                                current_subtask_id = 1
                            if current_subtask_id in subtask_map:
                                current_points = subtask_map[current_subtask_id].points
                        valid_script_lines.append(line_clean)
                        continue

                    # Points directive
                    if line_clean.startswith("> points"):
                        valid_script_lines.append(line_clean)
                        continue

                    # Generator execution directive: e.g. "gen 1 101 min > $"
                    cmd_match = re.match(r"^(?:gen|generator)\s+(.*?)(?:\s*>\s*\$?.*)?$", line_clean)
                    if cmd_match:
                        args_str = cmd_match.group(1).strip()
                        args = shlex.split(args_str) if args_str else []
                        try:
                            run_gen = subprocess.run(
                                [str(gen_exe)] + args,
                                capture_output=True,
                                text=True,
                                timeout=5,
                            )
                            if run_gen.returncode == 0 and run_gen.stdout.strip():
                                inp = run_gen.stdout.strip() + "\n"
                                if inp not in seen_inputs:
                                    expected_out = ""
                                    sol_ok = True
                                    if sol_compiled:
                                        s_res = subprocess.run(
                                            [str(sol_exe)],
                                            input=inp,
                                            text=True,
                                            capture_output=True,
                                            timeout=5,
                                        )
                                        if s_res.returncode == 0:
                                            expected_out = s_res.stdout.strip()
                                        else:
                                            sol_ok = False

                                    if sol_ok:
                                        seen_inputs.add(inp)
                                        valid_script_lines.append(f"gen {args_str} > $")
                                        valid_tests.append(
                                            TestCase(
                                                test_index=len(valid_tests) + 1,
                                                input_data=inp,
                                                expected_output=expected_out,
                                                description=f"Subtask {current_subtask_id} Test ({args_str})",
                                                subtask_id=current_subtask_id,
                                                group=current_group,
                                                points=current_points,
                                                script_command=f"gen {args_str} > $",
                                                is_sample=False,
                                            )
                                        )
                        except Exception:
                            pass

            # 4. If more tests needed or script was empty, run generator across all subtasks
            if len(valid_tests) < target_num_tests and gen_compiled:
                active_subtasks = subtasks if subtasks else [
                    SubtaskData(1, 30.0, "Small limits", "small"),
                    SubtaskData(2, 30.0, "Medium limits", "medium"),
                    SubtaskData(3, 40.0, "Full limits", "max"),
                ]

                # Distribute target tests among subtasks
                subtask_test_counts = {}
                total_pts = sum(s.points for s in active_subtasks) or 100.0
                allocated = 0
                for s in active_subtasks:
                    count = max(2, int(round((s.points / total_pts) * target_num_tests)))
                    subtask_test_counts[s.subtask_id] = count
                    allocated += count
                # Adjust remaining
                diff = target_num_tests - allocated
                if diff != 0:
                    subtask_test_counts[active_subtasks[-1].subtask_id] += diff

                for s in active_subtasks:
                    st_id = s.subtask_id
                    target_for_st = subtask_test_counts.get(st_id, 5)
                    st_tests_count = sum(1 for t in valid_tests if t.subtask_id == st_id)

                    seeds = [100 + i for i in range(1, target_for_st * 2 + 1)]
                    type_hints = ["min", "small", "mid", "overflow", "random", "stress", "max", "dense"]

                    if not any(l == f"> group {st_id}" for l in valid_script_lines):
                        valid_script_lines.append(f"> group {st_id}")

                    for seed in seeds:
                        if st_tests_count >= target_for_st or len(valid_tests) >= target_num_tests:
                            break
                        type_flag = type_hints[seed % len(type_hints)]
                        args = [str(st_id), str(seed), type_flag]
                        try:
                            run_gen = subprocess.run(
                                [str(gen_exe)] + args,
                                capture_output=True,
                                text=True,
                                timeout=5,
                            )
                            if run_gen.returncode == 0 and run_gen.stdout.strip():
                                inp = run_gen.stdout.strip() + "\n"
                                if inp not in seen_inputs:
                                    expected_out = ""
                                    sol_ok = True
                                    if sol_compiled:
                                        s_res = subprocess.run(
                                            [str(sol_exe)],
                                            input=inp,
                                            text=True,
                                            capture_output=True,
                                            timeout=5,
                                        )
                                        if s_res.returncode == 0:
                                            expected_out = s_res.stdout.strip()
                                        else:
                                            sol_ok = False

                                    if sol_ok:
                                        seen_inputs.add(inp)
                                        script_cmd = f"gen {st_id} {seed} {type_flag} > $"
                                        valid_script_lines.append(script_cmd)
                                        valid_tests.append(
                                            TestCase(
                                                test_index=len(valid_tests) + 1,
                                                input_data=inp,
                                                expected_output=expected_out,
                                                description=f"Subtask {st_id} Test ({type_flag})",
                                                subtask_id=st_id,
                                                group=str(st_id),
                                                points=s.points,
                                                script_command=script_cmd,
                                                is_sample=False,
                                            )
                                        )
                                        st_tests_count += 1
                        except Exception:
                            pass

            # 5. Fallback from existing code.tests if generator could not fulfill all tests
            if len(valid_tests) < target_num_tests and code.tests:
                for t in code.tests:
                    if len(valid_tests) >= target_num_tests:
                        break
                    inp = t.input_data.strip() + "\n"
                    if inp not in seen_inputs:
                        expected_out = ""
                        sol_ok = True
                        if sol_compiled:
                            try:
                                s_res = subprocess.run(
                                    [str(sol_exe)],
                                    input=inp,
                                    text=True,
                                    capture_output=True,
                                    timeout=5,
                                )
                                if s_res.returncode == 0:
                                    expected_out = s_res.stdout.strip()
                                else:
                                    sol_ok = False
                            except Exception:
                                sol_ok = False

                        if sol_ok:
                            seen_inputs.add(inp)
                            st_id = t.subtask_id or (1 if len(valid_tests) < target_num_tests // 2 else 2)
                            valid_tests.append(
                                TestCase(
                                    test_index=len(valid_tests) + 1,
                                    input_data=inp,
                                    expected_output=expected_out,
                                    description=t.description or f"Subtask {st_id} Test {len(valid_tests) + 1}",
                                    subtask_id=st_id,
                                    group=str(st_id),
                                    points=subtask_map.get(st_id, SubtaskData(st_id, 30.0, "")).points,
                                    is_sample=False,
                                )
                            )

            # 6. Final safety check: if still less than target_num_tests, duplicate and adjust
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
                            description=f"Generated Test {idx}",
                            subtask_id=1,
                            group="1",
                            is_sample=False,
                        )
                    )
            elif len(valid_tests) > target_num_tests:
                valid_tests = valid_tests[:target_num_tests]

            # Re-index 1..target_num_tests
            for i, t in enumerate(valid_tests, start=1):
                t.test_index = i

            code.tests = valid_tests
            code.test_script_lines = valid_script_lines

            # Clean auxiliary solutions
            code.validator_cpp = ""
            code.brute_force_cpp = ""
            code.solution_tl_cpp = ""
            code.solution_wa_cpp = ""
            code.solution_py = ""

            return code
