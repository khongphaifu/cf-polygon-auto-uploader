import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from core.ai_engine.llm_client import LLMClient
from core.ai_engine.local_verifier import LocalVerifier
from core.ai_engine.prompts import (
    FIX_CODE_PROMPT,
    GENERATE_CODE_PROMPT,
    PARSE_IMAGE_PROMPT,
    PARSE_PROBLEM_PROMPT,
)
from core.models import GeneratedCode, ProblemData, SampleTestCase, SubtaskData


class AIPipeline:
    """Orchestrates bilingual problem parsing, Polygon LaTeX sanitization, subtask splitting, and self-healing code generation."""

    def __init__(self, llm_client: LLMClient):
        self.llm = llm_client

    @staticmethod
    def _sanitize_polygon_latex(text: str) -> str:
        """Clean and enforce Polygon-compatible LaTeX syntax (restore corrupted escapes, no #, **, or bare %)."""
        if not text:
            return ""
        res = text.strip()

        # Recover single-backslash LaTeX commands corrupted into JSON control chars (\t, \b, \f, \r)
        res = re.sub(r"\t(ext[a-z]*|abular|imes|heta|o\b|riangle|iny)", r"\\t\1", res)
        res = re.sub(r"\x08(egin|mod|inom|ig[glrm]?|f\b|ar)", r"\\b\1", res)
        res = re.sub(r"\x0c(rac|orall)", r"\\f\1", res)
        res = re.sub(r"\r(ight|floor|ceil|angle)", r"\\r\1", res)

        # Convert Markdown headings (### Heading) -> \textbf{Heading}
        res = re.sub(r"(?m)^#{1,6}\s+(.+?)\s*$", r"\\textbf{\1}", res)
        # Convert Markdown bold (**text**) -> \textbf{text}
        res = re.sub(r"\*\*(.+?)\*\*", r"\\textbf{\1}", res)
        # Convert raw HTML sup/sub if any leaked through
        res = re.sub(r"<sup>(.*?)</sup>", r"^{\1}", res, flags=re.IGNORECASE | re.DOTALL)
        res = re.sub(r"<sub>(.*?)</sub>", r"_{\1}", res, flags=re.IGNORECASE | re.DOTALL)
        res = re.sub(r"<br\s*/?>", "\n\n", res, flags=re.IGNORECASE)
        res = res.replace("&le;", "\\le ").replace("&ge;", "\\ge ").replace("&ne;", "\\neq ").replace("&lt;", "<").replace("&gt;", ">")

        # Escape bare percent signs (%) not preceded by backslash so TeX doesn't treat them as comments
        res = re.sub(r"(?<!\\)%", r"\\%", res)

        # Normalize triple backticks in statements if any leaked
        res = re.sub(r"```[a-zA-Z]*\n(.*?)```", r"\\begin{verbatim}\n\1\\end{verbatim}", res, flags=re.DOTALL)

        # Balance itemize / enumerate blocks if truncated
        for env in ("itemize", "enumerate", "center", "tabular"):
            opens = len(re.findall(rf"\\begin\{{{env}\}}", res))
            closes = len(re.findall(rf"\\end\{{{env}\}}", res))
            if opens > closes:
                res += ("\n\\end{" + env + "}") * (opens - closes)

        return res.strip()

    @staticmethod
    def _build_scoring_table_latex(subtasks: List[SubtaskData], lang: str = "vi") -> str:
        """Build Polygon scoring LaTeX tabular matching user's reference style (problems 522809/522818)."""
        if not subtasks:
            return ""
        if lang == "vi":
            headers = "\\textbf{Subtask} & \\textbf{Điểm} & \\textbf{Giới hạn} \\\\"
            default_full = "Không có ràng buộc gì thêm"
        else:
            headers = "\\textbf{Subtask} & \\textbf{Points} & \\textbf{Constraints} \\\\"
            default_full = "No additional constraints"

        rows = [
            "\\begin{center}",
            "\\begin{tabular}{|c|c|c|}",
            "\\hline",
            headers,
            "\\hline",
        ]
        for s in subtasks:
            pts_str = str(int(s.points)) if float(s.points).is_integer() else str(round(s.points, 1))
            desc = (s.description or "").strip() or default_full
            if lang == "vi" and "no additional constraint" in desc.lower():
                desc = "Không có ràng buộc gì thêm"
            elif lang == "en" and "không có ràng buộc" in desc.lower():
                desc = "No additional constraints"
            desc = AIPipeline._sanitize_polygon_latex(desc)
            rows.append(f"{s.subtask_id} & {pts_str} & {desc} \\\\")
            rows.append("\\hline")
        rows.append("\\end{tabular}")
        rows.append("\\end{center}")
        return "\n".join(rows)

    def parse_problem_from_image(self, image_path: Path, use_file_io: bool = False) -> ProblemData:
        """Parse problem statement, formulas, constraints, subtasks and samples from an image or PDF."""
        raw_bytes = image_path.read_bytes()
        suffix = image_path.suffix.lower()
        if suffix == ".pdf":
            return self.parse_problem_content(str(image_path), f"[Local PDF: {image_path.name}]", pdf_bytes=raw_bytes, use_file_io=use_file_io)
        mime_type = "image/jpeg" if suffix in [".jpg", ".jpeg"] else ("image/webp" if suffix == ".webp" else "image/png")
        return self.parse_problem_content(
            str(image_path),
            f"[Local Image: {image_path.name}]",
            image_bytes=raw_bytes,
            image_mime=mime_type,
            use_file_io=use_file_io,
        )

    def _build_problem_data_from_json(
        self,
        source_url: str,
        parsed_json: Dict[str, Any],
        raw_content: str,
        use_file_io: bool = False,
    ) -> ProblemData:
        sample_tests = []
        for s in parsed_json.get("sample_tests", []):
            sample_tests.append(
                SampleTestCase(
                    input_text=str(s.get("input_text", "")).strip() + "\n",
                    output_text=str(s.get("output_text", "")).strip() + "\n",
                    explanation=s.get("explanation"),
                )
            )

        title = parsed_json.get("title") or parsed_json.get("title_en") or parsed_json.get("title_vi") or "Problem"
        short_name = parsed_json.get("short_name", "")
        if not short_name:
            short_name = re.sub(r"[^a-zA-Z0-9]+", "-", title.lower()).strip("-")
        short_name = re.sub(r"[^a-zA-Z0-9_-]", "-", short_name).lower()
        if len(short_name) > 30:
            short_name = short_name[:30].rstrip("-")
        if not short_name:
            short_name = "problem-task"

        # Subtasks extraction
        subtasks: List[SubtaskData] = []
        raw_subtasks = parsed_json.get("subtasks", [])
        if raw_subtasks and isinstance(raw_subtasks, list):
            for st in raw_subtasks:
                try:
                    subtasks.append(
                        SubtaskData(
                            subtask_id=int(st.get("subtask_id", len(subtasks) + 1)),
                            points=float(st.get("points", 0.0)),
                            description=str(st.get("description", "")),
                            generator_args_hint=str(st.get("generator_args_hint", "")),
                        )
                    )
                except Exception:
                    pass

        if not subtasks:
            subtasks = [
                SubtaskData(subtask_id=1, points=30.0, description="Small constraints ($N \\le 100$)", generator_args_hint="small"),
                SubtaskData(subtask_id=2, points=30.0, description="Medium constraints ($N \\le 2000$)", generator_args_hint="medium_overflow"),
                SubtaskData(subtask_id=3, points=40.0, description="No additional constraints", generator_args_hint="max_stress"),
            ]

        total_pts = sum(s.points for s in subtasks)
        if abs(total_pts - 100.0) > 1e-3 and total_pts > 0:
            running = 0.0
            for idx, s in enumerate(subtasks):
                if idx < len(subtasks) - 1:
                    s.points = round((s.points / total_pts) * 100.0, 1)
                    running += s.points
                else:
                    s.points = round(100.0 - running, 1)

        # Build bilingual statement maps (vietnamese & english)
        scoring_vi_raw = parsed_json.get("scoring_vi", "")
        scoring_en_raw = parsed_json.get("scoring_en", "")
        scoring_vi = self._sanitize_polygon_latex(scoring_vi_raw) if "\\begin{tabular}" in scoring_vi_raw else self._build_scoring_table_latex(subtasks, lang="vi")
        scoring_en = self._sanitize_polygon_latex(scoring_en_raw) if "\\begin{tabular}" in scoring_en_raw else self._build_scoring_table_latex(subtasks, lang="en")

        stmt_vi = {
            "name": (parsed_json.get("title_vi") or title).strip(),
            "legend": self._sanitize_polygon_latex(parsed_json.get("legend_vi") or parsed_json.get("legend") or ""),
            "input": self._sanitize_polygon_latex(parsed_json.get("input_format_vi") or parsed_json.get("input_format") or ""),
            "output": self._sanitize_polygon_latex(parsed_json.get("output_format_vi") or parsed_json.get("output_format") or ""),
            "scoring": scoring_vi,
            "notes": self._sanitize_polygon_latex(parsed_json.get("notes_vi") or parsed_json.get("notes") or ""),
            "tutorial": self._sanitize_polygon_latex(parsed_json.get("tutorial_vi") or parsed_json.get("tutorial") or ""),
        }
        stmt_en = {
            "name": (parsed_json.get("title_en") or title).strip(),
            "legend": self._sanitize_polygon_latex(parsed_json.get("legend_en") or parsed_json.get("legend") or ""),
            "input": self._sanitize_polygon_latex(parsed_json.get("input_format_en") or parsed_json.get("input_format") or ""),
            "output": self._sanitize_polygon_latex(parsed_json.get("output_format_en") or parsed_json.get("output_format") or ""),
            "scoring": scoring_en,
            "notes": self._sanitize_polygon_latex(parsed_json.get("notes_en") or parsed_json.get("notes") or ""),
            "tutorial": self._sanitize_polygon_latex(parsed_json.get("tutorial_en") or parsed_json.get("tutorial") or ""),
        }

        input_file = f"{short_name}.inp" if use_file_io else ""
        output_file = f"{short_name}.out" if use_file_io else ""

        return ProblemData(
            source_url=source_url,
            title=stmt_en["name"] or stmt_vi["name"] or title,
            short_name=short_name,
            legend=stmt_en["legend"] or stmt_vi["legend"],
            input_format=stmt_en["input"] or stmt_vi["input"],
            output_format=stmt_en["output"] or stmt_vi["output"],
            constraints=self._sanitize_polygon_latex(parsed_json.get("constraints", "")),
            scoring=scoring_en or scoring_vi,
            notes=stmt_en["notes"] or stmt_vi["notes"],
            tutorial=stmt_en["tutorial"] or stmt_vi["tutorial"],
            time_limit_ms=int(parsed_json.get("time_limit_ms", 1000)),
            memory_limit_mb=int(parsed_json.get("memory_limit_mb", 256)),
            input_file=input_file,
            output_file=output_file,
            checker_type=parsed_json.get("checker_type", "std::wcmp.cpp"),
            sample_tests=sample_tests,
            subtasks=subtasks,
            statements_by_lang={
                "vietnamese": stmt_vi,
                "english": stmt_en,
            },
            raw_html=raw_content,
        )

    def parse_problem_content(
        self,
        source_url: str,
        raw_content: str,
        pdf_bytes: Optional[bytes] = None,
        image_bytes: Optional[bytes] = None,
        image_mime: str = "image/png",
        use_file_io: bool = False,
    ) -> ProblemData:
        """Parse raw crawled content, PDF binary, or image bytes into structured bilingual ProblemData."""
        if pdf_bytes:
            parsed_json = self.llm.generate_from_image(
                prompt=PARSE_IMAGE_PROMPT,
                image_bytes=pdf_bytes,
                mime_type="application/pdf",
            )
            return self._build_problem_data_from_json(
                source_url, parsed_json, raw_content=f"[PDF Document: {len(pdf_bytes)} bytes]", use_file_io=use_file_io
            )

        if image_bytes:
            parsed_json = self.llm.generate_from_image(
                prompt=PARSE_IMAGE_PROMPT,
                image_bytes=image_bytes,
                mime_type=image_mime,
            )
            return self._build_problem_data_from_json(
                source_url, parsed_json, raw_content=f"[Image Document: {len(image_bytes)} bytes]", use_file_io=use_file_io
            )

        prompt = PARSE_PROBLEM_PROMPT.replace("{raw_content}", raw_content[:25000])
        parsed_json = self.llm.generate_json(prompt)
        return self._build_problem_data_from_json(source_url, parsed_json, raw_content, use_file_io=use_file_io)

    @staticmethod
    def _sanitize_cpp_code(code: str, is_testlib: bool = False) -> str:
        if not code:
            return ""
        code = code.strip()
        if code.startswith("```"):
            lines = code.splitlines()
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            code = "\n".join(lines).strip()

        if is_testlib:
            if '#include "testlib.h"' not in code and "<testlib.h>" not in code:
                code = '#include "testlib.h"\n\n' + code
            if "using namespace std;" not in code:
                if '#include "testlib.h"' in code:
                    code = code.replace('#include "testlib.h"', '#include "testlib.h"\nusing namespace std;')
                else:
                    code = "using namespace std;\n" + code
            code = code.replace("println();", 'cout << "\\n";')
        else:
            if "<bits/stdc++.h>" not in code and "<iostream>" not in code:
                code = "#include <bits/stdc++.h>\n" + code
            if "using namespace std;" not in code:
                code = code.replace("#include <bits/stdc++.h>", "#include <bits/stdc++.h>\nusing namespace std;")
                if "using namespace std;" not in code:
                    code = "using namespace std;\n" + code

        return code

    @staticmethod
    def _inject_file_io(solution_cpp: str, input_file: str, output_file: str) -> str:
        """Inject freopen statements inside main() for Olympiad-style .inp/.out file I/O."""
        if not solution_cpp or not input_file or not output_file:
            return solution_cpp
        if input_file in solution_cpp or "freopen(" in solution_cpp:
            return solution_cpp
        match = re.search(r"int\s+main\s*\([^)]*\)\s*\{", solution_cpp)
        if not match:
            return solution_cpp
        inject = (
            f'\n    if (FILE *f = fopen("{input_file}", "r")) {{\n'
            f'        fclose(f);\n'
            f'        freopen("{input_file}", "r", stdin);\n'
            f'        freopen("{output_file}", "w", stdout);\n'
            f'    }}\n'
        )
        pos = match.end()
        return solution_cpp[:pos] + inject + solution_cpp[pos:]

    def generate_code_and_tests(
        self,
        problem: ProblemData,
        num_tests: int = 30,
        points_policy: str = "EACH_TEST",
        use_file_io: bool = False,
        enable_validator: bool = True,
    ) -> GeneratedCode:
        """Generate C++ solution, generator, validator, test script, and run local verification + self-healing."""
        sample_tests_json = json.dumps(
            [
                {
                    "input": s.input_text,
                    "output": s.output_text,
                    "explanation": s.explanation,
                }
                for s in problem.sample_tests
            ],
            indent=2,
        )

        subtasks = problem.subtasks or [
            SubtaskData(1, 30.0, "Small constraints", "small"),
            SubtaskData(2, 30.0, "Medium constraints", "medium"),
            SubtaskData(3, 40.0, "Full constraints", "max"),
        ]

        total_pts = sum(s.points for s in subtasks) or 100.0
        allocated = 0
        distribution_lines = []
        for s in subtasks:
            s_tests = max(2, int(round((s.points / total_pts) * num_tests)))
            s.test_count = s_tests
            allocated += s_tests
            distribution_lines.append(f"- Subtask {s.subtask_id} ({s.points} pts): {s_tests} tests. Description: {s.description}")

        diff = num_tests - allocated
        if diff != 0:
            subtasks[-1].test_count = max(1, subtasks[-1].test_count + diff)
            distribution_lines[-1] = (
                f"- Subtask {subtasks[-1].subtask_id} ({subtasks[-1].points} pts): "
                f"{subtasks[-1].test_count} tests. Description: {subtasks[-1].description}"
            )

        subtasks_json = json.dumps([s.to_dict() for s in subtasks], indent=2)
        subtasks_hint = "\n".join(distribution_lines)

        code_prompt = GENERATE_CODE_PROMPT.replace("{title}", problem.title)
        code_prompt = code_prompt.replace("{constraints}", problem.constraints or "Standard CP constraints")
        code_prompt = code_prompt.replace("{subtasks_json}", subtasks_json)
        code_prompt = code_prompt.replace("{legend}", (problem.legend or "")[:4000])
        code_prompt = code_prompt.replace("{input_format}", (problem.input_format or "")[:2000])
        code_prompt = code_prompt.replace("{output_format}", (problem.output_format or "")[:2000])
        code_prompt = code_prompt.replace("{sample_tests_json}", sample_tests_json)
        code_prompt = code_prompt.replace("{checker_type}", problem.checker_type)
        code_prompt = code_prompt.replace("{num_tests}", str(num_tests))
        code_prompt = code_prompt.replace("{subtasks_distribution_hint}", subtasks_hint)

        try:
            code_result = self.llm.generate_json(code_prompt)
        except Exception as e:
            raise RuntimeError(
                f"Toàn bộ Gemini API key/model đều hết quota hoặc gặp lỗi khi sinh lời giải & test: {e}"
            ) from e

        sol_cpp = self._sanitize_cpp_code(code_result.get("solution_cpp", ""), is_testlib=False)
        gen_cpp = self._sanitize_cpp_code(code_result.get("generator_cpp", ""), is_testlib=True)
        val_cpp = self._sanitize_cpp_code(code_result.get("validator_cpp", ""), is_testlib=True) if enable_validator else ""

        raw_script = code_result.get("test_script_lines", [])
        if isinstance(raw_script, str):
            raw_script = [line.strip() for line in raw_script.splitlines() if line.strip()]

        chk_cpp = code_result.get("custom_checker_cpp")
        if chk_cpp:
            chk_cpp = self._sanitize_cpp_code(chk_cpp, is_testlib=True)

        chk_type = code_result.get("checker_type") or problem.checker_type or "std::wcmp.cpp"

        gen_code = GeneratedCode(
            solution_cpp=sol_cpp,
            validator_cpp=val_cpp,
            generator_cpp=gen_cpp,
            checker_type=chk_type,
            custom_checker_cpp=chk_cpp,
            tests=[],
            test_script_lines=raw_script,
            subtasks=subtasks,
        )

        # Step 2: Local Verification + Self-Healing Loop (up to 3 attempts)
        verifier = LocalVerifier()
        max_local_heal_attempts = 3
        for attempt in range(1, max_local_heal_attempts + 1):
            gen_code = verifier.verify_and_clean(
                problem=problem,
                code=gen_code,
                target_num_tests=num_tests,
                points_policy=points_policy,
                enable_validator=enable_validator,
                allow_early_abort=(attempt < max_local_heal_attempts),
            )
            if not verifier.last_errors:
                break
            if attempt < max_local_heal_attempts:
                err_text = "\n".join(verifier.last_errors)
                fixed = self.fix_code_and_script(
                    problem=problem,
                    current_sol=gen_code.solution_cpp,
                    current_gen=gen_code.generator_cpp,
                    current_script=gen_code.test_script_lines,
                    error_details=err_text,
                    current_val=gen_code.validator_cpp,
                )
                gen_code.solution_cpp = fixed.get("solution_cpp") or gen_code.solution_cpp
                gen_code.generator_cpp = fixed.get("generator_cpp") or gen_code.generator_cpp
                if enable_validator and fixed.get("validator_cpp"):
                    gen_code.validator_cpp = fixed.get("validator_cpp")
                gen_code.test_script_lines = fixed.get("test_script_lines") or gen_code.test_script_lines

        # Step 3: Inject optional File I/O (.inp/.out) after verification passes cleanly
        if use_file_io and problem.input_file and problem.output_file:
            gen_code.solution_cpp = self._inject_file_io(gen_code.solution_cpp, problem.input_file, problem.output_file)

        return gen_code

    def fix_code_and_script(
        self,
        problem: ProblemData,
        current_sol: str,
        current_gen: str,
        current_script: List[str],
        error_details: str,
        current_val: str = "",
    ) -> Dict[str, Any]:
        """Call AI with FIX_CODE_PROMPT to repair solution_cpp, generator_cpp, validator_cpp, or script."""
        sample_tests_json = json.dumps(
            [
                {
                    "input": s.input_text,
                    "output": s.output_text,
                    "explanation": s.explanation,
                }
                for s in problem.sample_tests
            ],
            indent=2,
        )
        prompt = FIX_CODE_PROMPT.replace("{title}", problem.title)
        prompt = prompt.replace("{constraints}", problem.constraints or "Standard CP constraints")
        prompt = prompt.replace("{legend}", (problem.legend or "")[:2000])
        prompt = prompt.replace("{input_format}", (problem.input_format or "")[:2000])
        prompt = prompt.replace("{output_format}", (problem.output_format or "")[:2000])
        prompt = prompt.replace("{sample_tests_json}", sample_tests_json)
        prompt = prompt.replace("{current_solution_cpp}", current_sol)
        prompt = prompt.replace("{current_generator_cpp}", current_gen)
        prompt = prompt.replace("{current_validator_cpp}", current_val or "/* none */")
        prompt = prompt.replace("{current_script_lines}", "\n".join(current_script))
        prompt = prompt.replace("{error_details}", str(error_details)[:4000])

        try:
            res = self.llm.generate_json(prompt)
            raw_script = res.get("test_script_lines") or current_script
            if isinstance(raw_script, str):
                raw_script = [line.strip() for line in raw_script.splitlines() if line.strip()]
            fixed_val = res.get("validator_cpp")
            return {
                "solution_cpp": self._sanitize_cpp_code(res.get("solution_cpp") or current_sol, is_testlib=False),
                "generator_cpp": self._sanitize_cpp_code(res.get("generator_cpp") or current_gen, is_testlib=True),
                "validator_cpp": self._sanitize_cpp_code(fixed_val, is_testlib=True) if fixed_val else current_val,
                "test_script_lines": raw_script,
                "explanation": res.get("explanation", ""),
            }
        except Exception:
            return {
                "solution_cpp": current_sol,
                "generator_cpp": current_gen,
                "validator_cpp": current_val,
                "test_script_lines": current_script,
                "explanation": "Failed to call AI fix",
            }
