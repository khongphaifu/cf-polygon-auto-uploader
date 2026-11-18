import re
import shlex
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Dict, List, Optional

from core.models import GeneratedCode, ProblemData, SubtaskData, TestCase


class LocalVerifier:
    """
    Locally compiles solution.cpp, generator.cpp, and optional validator.cpp using g++ and testlib.h,
    verifies solution.exe against all sample tests, checks multi-testcase t/q diversity and safe API size,
    runs solution.exe to compute expected outputs, and assigns groups & 100-point allocations.
    """

    MAX_TEST_BYTES = 3_800_000  # Keep each manual API test safely under 4 MB for fast Polygon upload

    def __init__(self, testlib_path: Optional[Path] = None):
        self.testlib_path = testlib_path or (Path(__file__).resolve().parent.parent.parent / "testlib.h")
        self.last_errors: List[str] = []

    @staticmethod
    def _is_multi_testcase_problem(problem: ProblemData) -> Optional[int]:
        """Detect if problem expects multiple testcases `t`, returning Sample #1's t (>=2) if confirmed."""
        if not problem.sample_tests:
            return None
        first_line = problem.sample_tests[0].input_text.strip().splitlines()[0].strip() if problem.sample_tests[0].input_text.strip() else ""
        if not re.fullmatch(r"\d+", first_line):
            return None
        sample_t = int(first_line)
        if sample_t < 2:
            return None
        text_blob = " ".join([
            problem.input_format or "",
            problem.constraints or "",
            (problem.statements_by_lang or {}).get("vietnamese", {}).get("input", ""),
            (problem.statements_by_lang or {}).get("english", {}).get("input", ""),
        ])
        if re.search(
            r"(number of test\s*cases|số(?: lượng)? bộ test|test\s*cases|mỗi bộ test|each test\s*case|\\tau\b|\$t\$)",
            text_blob,
            re.IGNORECASE,
        ):
            return sample_t
        return None

    @staticmethod
    def _compare_outputs(expected: str, actual: str, checker_type: str) -> bool:
        """Compare solution output against sample expected output locally."""
        chk = (checker_type or "").lower()
        if "custom" in chk:
            return bool(actual.strip())

        exp_tokens = expected.strip().split()
        act_tokens = actual.strip().split()

        if "yesno" in chk or (exp_tokens and all(t.upper() in ("YES", "NO") for t in exp_tokens)):
            return [t.upper() for t in exp_tokens] == [t.upper() for t in act_tokens]

        if "rcmp" in chk or "fcmp" in chk:
            if "rcmp" in chk:
                if len(exp_tokens) != len(act_tokens):
                    return False
                tol = 1e-8 if "9" in chk else 1e-5
                try:
                    for e_tok, a_tok in zip(exp_tokens, act_tokens):
                        e_val, a_val = float(e_tok), float(a_tok)
                        if abs(e_val - a_val) > tol * max(1.0, abs(e_val)):
                            return False
                    return True
                except ValueError:
                    return exp_tokens == act_tokens
            exp_lines = [line.rstrip() for line in expected.strip().splitlines()]
            act_lines = [line.rstrip() for line in actual.strip().splitlines()]
            return exp_lines == act_lines

        return exp_tokens == act_tokens

    def verify_and_clean(
        self,
        problem: ProblemData,
        code: GeneratedCode,
        target_num_tests: int = 30,
        points_policy: str = "EACH_TEST",
        enable_validator: bool = True,
        allow_early_abort: bool = True,
    ) -> GeneratedCode:
        """
        1. Compiles solution.cpp locally using g++ -O2 -std=c++20 (falls back to c++17 if needed).
        2. Verifies solution.exe against all problem.sample_tests (records mismatches in self.last_errors).
        3. Compiles generator.cpp and optional validator.cpp with testlib.h.
        4. Executes test_script_lines and additional subtask seeds to produce unique valid tests.
        5. Assigns group names (sub1, sub2, sub3) and exact per-test points summing to 100.0.
        """
        self.last_errors = []

        if not shutil.which("g++"):
            return code

        subtasks = code.subtasks or problem.subtasks
        subtask_map = {s.subtask_id: s for s in subtasks} if subtasks else {}

        with tempfile.TemporaryDirectory() as tmpdir_str:
            tmpdir = Path(tmpdir_str)

            if self.testlib_path.exists():
                shutil.copy(self.testlib_path, tmpdir / "testlib.h")

            # 1. Compile Main Solution
            sol_cpp = tmpdir / "solution.cpp"
            sol_exe = tmpdir / "solution.exe"
            sol_cpp.write_text(code.solution_cpp, encoding="utf-8")

            sol_compiled = False
            compile_err = ""
            for std_flag in ["-std=c++20", "-std=c++17"]:
                try:
                    compile_sol = subprocess.run(
                        ["g++", "-O2", std_flag, str(sol_cpp), "-o", str(sol_exe)],
                        capture_output=True,
                        text=True,
                        timeout=30,
                    )
                    if compile_sol.returncode == 0:
                        sol_compiled = True
                        break
                    compile_err = compile_sol.stderr
                except Exception as ex:
                    compile_err = str(ex)

            if not sol_compiled:
                self.last_errors.append(f"solution.cpp compilation error:\n{compile_err[:1500]}")

            # 1.5 Verify Solution against Sample Tests
            if sol_compiled and problem.sample_tests:
                for s_idx, sample in enumerate(problem.sample_tests, start=1):
                    s_inp = sample.input_text.strip() + "\n"
                    s_exp = (sample.output_text or "").strip()
                    if not s_exp:
                        continue
                    try:
                        s_run = subprocess.run(
                            [str(sol_exe)],
                            input=s_inp,
                            text=True,
                            capture_output=True,
                            timeout=5,
                        )
                        if s_run.returncode != 0:
                            self.last_errors.append(
                                f"Sample Test #{s_idx} runtime error (exit code {s_run.returncode}): {s_run.stderr[:500]}"
                            )
                        else:
                            if not self._compare_outputs(s_exp, s_run.stdout, code.checker_type or problem.checker_type):
                                self.last_errors.append(
                                    f"Sample Test #{s_idx} Wrong Answer!\n"
                                    f"Input:\n{s_inp[:500]}\n"
                                    f"Expected:\n{s_exp[:500]}\n"
                                    f"Actual:\n{s_run.stdout.strip()[:500]}"
                                )
                    except subprocess.TimeoutExpired:
                        self.last_errors.append(f"Sample Test #{s_idx} Time Limit Exceeded (>5s).")
                    except Exception as ex:
                        self.last_errors.append(f"Sample Test #{s_idx} execution error: {ex}")

            # 2. Compile Generator
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
                    else:
                        self.last_errors.append(f"generator.cpp compilation error:\n{compile_gen.stderr[:1500]}")
                except Exception as ex:
                    self.last_errors.append(f"generator.cpp compile exception: {ex}")

            # 2.5 Compile Optional Validator (non-fatal if invalid)
            val_compiled = False
            val_exe = tmpdir / "validator.exe"
            if enable_validator and code.validator_cpp and code.validator_cpp.strip():
                val_cpp = tmpdir / "validator.cpp"
                val_cpp.write_text(code.validator_cpp, encoding="utf-8")
                try:
                    compile_val = subprocess.run(
                        ["g++", "-O2", "-std=c++17", str(val_cpp), "-o", str(val_exe)],
                        capture_output=True,
                        text=True,
                        timeout=30,
                    )
                    if compile_val.returncode == 0:
                        val_compiled = True
                    else:
                        code.validator_cpp = ""
                except Exception:
                    code.validator_cpp = ""
            else:
                code.validator_cpp = ""

            # If there were compilation or sample WA errors and retries remain, abort early for fast self-healing
            if self.last_errors and allow_early_abort:
                return code

            # Helper to validate input with validator.exe
            val_rejected_count = 0
            val_checked_count = 0

            def _validate_input(inp_data: str) -> bool:
                nonlocal val_compiled, val_rejected_count, val_checked_count
                if not val_compiled:
                    return True
                val_checked_count += 1
                try:
                    v_res = subprocess.run(
                        [str(val_exe)],
                        input=inp_data,
                        text=True,
                        capture_output=True,
                        timeout=3,
                    )
                    if v_res.returncode == 0:
                        return True
                    val_rejected_count += 1
                    # Disable overly strict/buggy validator if it rejects >50% after >=4 checks
                    if val_checked_count >= 4 and val_rejected_count > val_checked_count * 0.5:
                        val_compiled = False
                        code.validator_cpp = ""
                        return True
                    return False
                except Exception:
                    return True

            # Pre-seed seen_inputs with sample inputs so generated tests don't duplicate samples on Polygon
            seen_inputs = set()
            for sample in problem.sample_tests:
                norm_s = sample.input_text.strip()
                if norm_s:
                    seen_inputs.add(norm_s + "\n")

            valid_tests: List[TestCase] = []
            valid_script_lines: List[str] = []

            current_subtask_id = 1
            current_group = "sub1"
            current_points = subtask_map.get(1).points if (subtask_map and 1 in subtask_map) else None

            def _run_gen_and_sol(args: List[str], st_id: int, desc: str) -> bool:
                nonlocal valid_tests, valid_script_lines
                try:
                    run_gen = subprocess.run(
                        [str(gen_exe)] + args,
                        capture_output=True,
                        text=True,
                        timeout=5,
                    )
                    if run_gen.returncode != 0 or not run_gen.stdout.strip():
                        return False
                    inp = run_gen.stdout.strip() + "\n"
                    if len(inp.encode("utf-8", errors="ignore")) > self.MAX_TEST_BYTES:
                        return False
                    if inp in seen_inputs:
                        return False
                    if not _validate_input(inp):
                        return False

                    expected_out = ""
                    if sol_compiled:
                        s_res = subprocess.run(
                            [str(sol_exe)],
                            input=inp,
                            text=True,
                            capture_output=True,
                            timeout=5,
                        )
                        if s_res.returncode != 0:
                            return False
                        expected_out = s_res.stdout.strip()

                    seen_inputs.add(inp)
                    args_str = " ".join(args)
                    grp = f"sub{st_id}"
                    valid_script_lines.append(f"gen {args_str} > $")
                    valid_tests.append(
                        TestCase(
                            test_index=len(valid_tests) + 1,
                            input_data=inp,
                            expected_output=expected_out,
                            description=desc,
                            subtask_id=st_id,
                            group=grp,
                            points=subtask_map.get(st_id).points if st_id in subtask_map else 0.0,
                            script_command=f"gen {args_str} > $",
                            is_sample=False,
                        )
                    )
                    return True
                except Exception:
                    return False

            # 3. Execute explicit generator script lines
            if gen_compiled and code.test_script_lines:
                for line in code.test_script_lines:
                    if len(valid_tests) >= target_num_tests:
                        break
                    line_clean = line.strip()
                    if not line_clean or line_clean.startswith("#") or line_clean.startswith("//"):
                        continue

                    if line_clean.startswith("> group") or line_clean.startswith("> subtask"):
                        parts = line_clean.split()
                        if len(parts) >= 3:
                            try:
                                current_subtask_id = int(re.sub(r"[^0-9]", "", parts[2])) or 1
                            except Exception:
                                current_subtask_id = 1
                            current_group = f"sub{current_subtask_id}"
                            if current_subtask_id in subtask_map:
                                current_points = subtask_map[current_subtask_id].points
                        valid_script_lines.append(f"> group {current_group}")
                        continue

                    if line_clean.startswith("> points"):
                        continue

                    cmd_match = re.match(r"^(?:gen|generator)\s+(.*?)(?:\s*>\s*\$?.*)?$", line_clean)
                    if cmd_match:
                        args_str = cmd_match.group(1).strip()
                        args = shlex.split(args_str) if args_str else []
                        _run_gen_and_sol(args, current_subtask_id, f"Subtask {current_subtask_id} Test ({args_str})")

            # 4. Fill remaining tests across subtasks using generator seeds (no duplicate copying!)
            active_subtasks = subtasks if subtasks else [
                SubtaskData(1, 30.0, "Small limits", "small"),
                SubtaskData(2, 30.0, "Medium limits", "medium"),
                SubtaskData(3, 40.0, "Full limits", "max"),
            ]

            if len(valid_tests) < target_num_tests and gen_compiled:
                subtask_test_counts: Dict[int, int] = {}
                total_pts = sum(s.points for s in active_subtasks) or 100.0
                allocated = 0
                for s in active_subtasks:
                    count = max(2, int(round((s.points / total_pts) * target_num_tests)))
                    subtask_test_counts[s.subtask_id] = count
                    allocated += count
                diff = target_num_tests - allocated
                if diff != 0:
                    subtask_test_counts[active_subtasks[-1].subtask_id] = max(
                        1, subtask_test_counts[active_subtasks[-1].subtask_id] + diff
                    )

                type_hints = ["min", "small", "mid", "overflow", "random", "stress", "max", "dense"]
                for s in active_subtasks:
                    st_id = s.subtask_id
                    target_for_st = subtask_test_counts.get(st_id, 5)
                    st_tests_count = sum(1 for t in valid_tests if t.subtask_id == st_id)
                    if not any(l == f"> group sub{st_id}" for l in valid_script_lines):
                        valid_script_lines.append(f"> group sub{st_id}")

                    for offset in range(1, target_for_st * 4 + 10):
                        if st_tests_count >= target_for_st or len(valid_tests) >= target_num_tests:
                            break
                        seed = 1000 * st_id + offset
                        type_flag = type_hints[offset % len(type_hints)]
                        args = [str(st_id), str(seed), type_flag]
                        if _run_gen_and_sol(args, st_id, f"Subtask {st_id} Test ({type_flag})"):
                            st_tests_count += 1

                # Second pass if any global shortage remains (using full-constraint subtask)
                extra_seed = 9000
                while len(valid_tests) < target_num_tests and extra_seed < 9150:
                    extra_seed += 1
                    last_st = active_subtasks[-1].subtask_id
                    type_flag = type_hints[extra_seed % len(type_hints)]
                    _run_gen_and_sol(
                        [str(last_st), str(extra_seed), type_flag],
                        last_st,
                        f"Subtask {last_st} Extra Test ({extra_seed})",
                    )

            # 4.2 Anti-(t=1) Hardcode Check: catch generators that output t=1 on every multi-testcase test
            expected_sample_t = self._is_multi_testcase_problem(problem)
            if allow_early_abort and expected_sample_t is not None and len(valid_tests) >= 5:
                first_lines = [
                    (t.input_data.strip().splitlines()[0].strip() if t.input_data.strip() else "")
                    for t in valid_tests
                ]
                ones_count = sum(1 for fl in first_lines if fl == "1")
                if ones_count >= int(0.75 * len(valid_tests)):
                    self.last_errors.append(
                        f"Multi-testcase generator bug: {ones_count}/{len(valid_tests)} generated tests hardcoded t = 1 on line 1 "
                        f"(whereas Sample #1 has t = {expected_sample_t}). Rewrite generator.cpp so it NEVER hardcodes t = 1: "
                        f"use varied t (2..20 in subtask 1, 3..30 in subtask 2, and in subtask 3 mix high-t 500..5000 with small n, "
                        f"medium-t 5..25 summing to full scale, and t=1..3 with large n <= min(N_max, 200000)), keeping sum(n) valid and each test <= 3.5 MB."
                    )
                    return code

            # 4.5 Deterministic fallback synthesis if generator failed or produced too few tests
            if len(valid_tests) < target_num_tests:
                import random
                rng = random.Random(20261118)
                base_samples = [s.input_text.strip() for s in problem.sample_tests if s.input_text.strip()]
                base_template = base_samples[0] if base_samples else "3\n1 2 3"
                lines = base_template.splitlines()
                fallback_offset = 0
                while len(valid_tests) < target_num_tests and fallback_offset < target_num_tests * 10:
                    fallback_offset += 1
                    st_idx = active_subtasks[(len(valid_tests)) % len(active_subtasks)].subtask_id
                    mutated_lines = []
                    for l_idx, raw_l in enumerate(lines):
                        toks = raw_l.split()
                        if toks and all(re.fullmatch(r"-?\d+", tok) for tok in toks):
                            # Keep header/testcount line intact when len==1 on multi-line input, mutate payload tokens slightly
                            if l_idx == 0 and len(lines) > 1 and len(toks) == 1:
                                mutated_lines.append(raw_l)
                            else:
                                new_toks = [
                                    str(int(tok) + rng.randint(1, 20) + fallback_offset if int(tok) >= 0 else int(tok) - rng.randint(1, 10))
                                    for tok in toks
                                ]
                                mutated_lines.append(" ".join(new_toks))
                        else:
                            mutated_lines.append(raw_l)
                    cand_inp = "\n".join(mutated_lines).strip() + "\n"
                    if cand_inp in seen_inputs:
                        cand_toks = base_template.split()
                        if cand_toks and cand_toks[-1].lstrip("-").isdigit():
                            prefix = " ".join(lines[:-1])
                            last_tokens = lines[-1].split()
                            last_tokens[-1] = str(int(last_tokens[-1]) + fallback_offset)
                            cand_inp = ((prefix + "\n") if prefix else "") + " ".join(last_tokens) + "\n"
                    if cand_inp in seen_inputs:
                        continue
                    seen_inputs.add(cand_inp)
                    expected_out = ""
                    if sol_compiled:
                        try:
                            s_res = subprocess.run([str(sol_exe)], input=cand_inp, text=True, capture_output=True, timeout=5)
                            if s_res.returncode == 0:
                                expected_out = s_res.stdout.strip()
                        except Exception:
                            pass
                    valid_tests.append(
                        TestCase(
                            test_index=len(valid_tests) + 1,
                            input_data=cand_inp,
                            expected_output=expected_out,
                            description=f"Subtask {st_idx} Fallback Test {len(valid_tests) + 1}",
                            subtask_id=st_idx,
                            group=f"sub{st_idx}",
                            points=0.0,
                            is_sample=False,
                        )
                    )

            # 5. Trim if exceeded
            if len(valid_tests) > target_num_tests:
                valid_tests = valid_tests[:target_num_tests]

            # 6. Normalize Group Names (sub1, sub2, ...) & Exact 100.0 Point Distribution
            tests_by_subtask: Dict[int, List[TestCase]] = {}
            for i, t in enumerate(valid_tests, start=1):
                t.test_index = i
                st_id = t.subtask_id or 1
                t.group = f"sub{st_id}"
                tests_by_subtask.setdefault(st_id, []).append(t)

            # Recompute subtask test counts and ensure points sum cleanly to subtask.points (total 100.0)
            active_map = {s.subtask_id: s for s in active_subtasks}
            # Ensure points across subtasks that actually have tests sum to 100.0 if any subtask got 0 tests
            active_pts_total = sum(active_map[st_id].points for st_id in tests_by_subtask if st_id in active_map) or 100.0
            for st_id, st_tests in tests_by_subtask.items():
                st_obj = active_map.get(st_id)
                st_total_pts = (st_obj.points if st_obj else 0.0)
                if abs(active_pts_total - 100.0) > 1e-3 and active_pts_total > 0:
                    st_total_pts = round((st_total_pts / active_pts_total) * 100.0, 2)
                if st_obj:
                    st_obj.test_count = len(st_tests)

                k = len(st_tests)
                if k > 0:
                    per_test = round(st_total_pts / k, 2)
                    for idx_in_sub, tc in enumerate(st_tests):
                        if idx_in_sub < k - 1:
                            tc.points = per_test
                        else:
                            tc.points = round(st_total_pts - per_test * (k - 1), 2)

            code.tests = valid_tests
            code.test_script_lines = valid_script_lines
            code.subtasks = active_subtasks

            # Clean auxiliary unused solutions while keeping validator_cpp intact if valid
            code.brute_force_cpp = ""
            code.solution_tl_cpp = ""
            code.solution_wa_cpp = ""
            code.solution_py = ""

            return code
