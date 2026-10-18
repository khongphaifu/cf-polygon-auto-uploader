import json
import re
from typing import Dict, Any, List, Optional
from pathlib import Path
from core.models import ProblemData, SampleTestCase, GeneratedCode, TestCase, SubtaskData
from core.ai_engine.llm_client import LLMClient
from core.ai_engine.prompts import (
    PARSE_PROBLEM_PROMPT,
    GENERATE_CODE_PROMPT,
    GENERATE_TESTS_FALLBACK_PROMPT,
    FIX_CODE_PROMPT,
    PARSE_IMAGE_PROMPT,
)
from core.ai_engine.local_verifier import LocalVerifier


class AIPipeline:
    """Orchestrates problem parsing, subtask splitting, and code/test generation using LLM."""

    def __init__(self, llm_client: LLMClient):
        self.llm = llm_client

    def parse_problem_from_image(self, image_path: Path) -> ProblemData:
        """Parse problem statement, formulas, constraints, subtasks and samples from an image/PDF."""
        image_bytes = image_path.read_bytes()
        suffix = image_path.suffix.lower()
        mime_type = "image/jpeg" if suffix in [".jpg", ".jpeg"] else ("image/webp" if suffix == ".webp" else "image/png")
        
        parsed_json = self.llm.generate_from_image(
            prompt=PARSE_IMAGE_PROMPT,
            image_bytes=image_bytes,
            mime_type=mime_type,
        )
        return self._build_problem_data_from_json(str(image_path), parsed_json, raw_content="[Parsed from Image]")

    def _build_problem_data_from_json(self, source_url: str, parsed_json: Dict[str, Any], raw_content: str) -> ProblemData:
        sample_tests = []
        for s in parsed_json.get("sample_tests", []):
            sample_tests.append(
                SampleTestCase(
                    input_text=s.get("input_text", "").strip() + "\n",
                    output_text=s.get("output_text", "").strip() + "\n",
                    explanation=s.get("explanation"),
                )
            )

        title = parsed_json.get("title", "Problem")
        short_name = parsed_json.get("short_name", "")
        if not short_name:
            short_name = re.sub(r"[^a-zA-Z0-9]+", "-", title.lower()).strip("-")
        short_name = re.sub(r"[^a-zA-Z0-9_-]", "-", short_name).lower()
        if len(short_name) > 30:
            short_name = short_name[:30].rstrip("-")

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

        # If no subtasks found, create standard 3-subtask division
        if not subtasks:
            subtasks = [
                SubtaskData(subtask_id=1, points=30.0, description="Small constraints ($n \\le 100$)", generator_args_hint="small"),
                SubtaskData(subtask_id=2, points=30.0, description="Medium constraints & 32-bit overflow ($n \\le 2000$)", generator_args_hint="medium_overflow"),
                SubtaskData(subtask_id=3, points=40.0, description="Full constraints ($n = N_{\\max}$)", generator_args_hint="max_stress"),
            ]

        # Ensure points sum up to 100
        total_pts = sum(s.points for s in subtasks)
        if abs(total_pts - 100.0) > 1e-3 and total_pts > 0:
            for s in subtasks:
                s.points = round((s.points / total_pts) * 100.0, 1)

        return ProblemData(
            source_url=source_url,
            title=title,
            short_name=short_name,
            legend=parsed_json.get("legend", ""),
            input_format=parsed_json.get("input_format", ""),
            output_format=parsed_json.get("output_format", ""),
            constraints=parsed_json.get("constraints", ""),
            notes=parsed_json.get("notes", ""),
            tutorial=parsed_json.get("tutorial", ""),
            time_limit_ms=int(parsed_json.get("time_limit_ms", 1000)),
            memory_limit_mb=int(parsed_json.get("memory_limit_mb", 256)),
            checker_type=parsed_json.get("checker_type", "std::wcmp.cpp"),
            sample_tests=sample_tests,
            subtasks=subtasks,
            raw_html=raw_content,
        )

    def parse_problem_content(self, source_url: str, raw_content: str, pdf_bytes: Optional[bytes] = None) -> ProblemData:
        """Parse raw crawled content or PDF binary into structured ProblemData with subtasks."""
        if pdf_bytes:
            parsed_json = self.llm.generate_from_image(
                prompt=PARSE_IMAGE_PROMPT,
                image_bytes=pdf_bytes,
                mime_type="application/pdf",
            )
            return self._build_problem_data_from_json(source_url, parsed_json, raw_content=f"[PDF Document: {len(pdf_bytes)} bytes]")

        prompt = PARSE_PROBLEM_PROMPT.replace("{raw_content}", raw_content[:25000])
        parsed_json = self.llm.generate_json(prompt)
        return self._build_problem_data_from_json(source_url, parsed_json, raw_content)

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

    def generate_code_and_tests(self, problem: ProblemData, num_tests: int = 30) -> GeneratedCode:
        """Generate C++ solution, testlib generator, test script, and verify tests divided by subtasks."""
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

        # Allocate tests across subtasks based on points
        total_pts = sum(s.points for s in subtasks) or 100.0
        allocated = 0
        distribution_lines = []
        for s in subtasks:
            s_tests = max(2, int(round((s.points / total_pts) * num_tests)))
            s.test_count = s_tests
            allocated += s_tests
            distribution_lines.append(f"- Subtask {s.subtask_id} ({s.points} pts): {s_tests} tests. Description: {s.description}")

        # Adjust remaining tests to match num_tests exactly
        diff = num_tests - allocated
        if diff != 0:
            subtasks[-1].test_count += diff
            distribution_lines[-1] = f"- Subtask {subtasks[-1].subtask_id} ({subtasks[-1].points} pts): {subtasks[-1].test_count} tests. Description: {subtasks[-1].description}"

        subtasks_json = json.dumps([s.to_dict() for s in subtasks], indent=2)
        subtasks_hint = "\n".join(distribution_lines)

        # Step 1: Generate Solution, Generator & Test Script
        code_prompt = GENERATE_CODE_PROMPT.replace("{title}", problem.title)
        code_prompt = code_prompt.replace("{constraints}", problem.constraints or "Standard CP constraints")
        code_prompt = code_prompt.replace("{subtasks_json}", subtasks_json)
        code_prompt = code_prompt.replace("{legend}", problem.legend[:4000])
        code_prompt = code_prompt.replace("{input_format}", problem.input_format[:2000])
        code_prompt = code_prompt.replace("{output_format}", problem.output_format[:2000])
        code_prompt = code_prompt.replace("{sample_tests_json}", sample_tests_json)
        code_prompt = code_prompt.replace("{checker_type}", problem.checker_type)
        code_prompt = code_prompt.replace("{num_tests}", str(num_tests))
        code_prompt = code_prompt.replace("{subtasks_distribution_hint}", subtasks_hint)

        code_result = self.llm.generate_json(code_prompt)

        sol_cpp = self._sanitize_cpp_code(code_result.get("solution_cpp", ""), is_testlib=False)
        gen_cpp = self._sanitize_cpp_code(code_result.get("generator_cpp", ""), is_testlib=True)
        raw_script = code_result.get("test_script_lines", [])
        if isinstance(raw_script, str):
            raw_script = [line.strip() for line in raw_script.splitlines() if line.strip()]

        chk_cpp = code_result.get("custom_checker_cpp")
        if chk_cpp:
            chk_cpp = self._sanitize_cpp_code(chk_cpp, is_testlib=True)

        chk_type = code_result.get("checker_type") or problem.checker_type or "std::wcmp.cpp"

        gen_code = GeneratedCode(
            solution_cpp=sol_cpp,
            validator_cpp="",
            generator_cpp=gen_cpp,
            checker_type=chk_type,
            custom_checker_cpp=chk_cpp,
            tests=[],
            test_script_lines=raw_script,
            subtasks=subtasks,
        )

        # Step 2: Local Verification & Output Generation
        verifier = LocalVerifier()
        verified_code = verifier.verify_and_clean(problem=problem, code=gen_code, target_num_tests=num_tests)
        return verified_code

    def fix_code_and_script(
        self,
        problem: ProblemData,
        current_sol: str,
        current_gen: str,
        current_script: List[str],
        error_details: str,
    ) -> Dict[str, Any]:
        """Call AI with FIX_CODE_PROMPT to repair solution_cpp, generator_cpp, or script."""
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
        prompt = prompt.replace("{input_format}", problem.input_format[:2000])
        prompt = prompt.replace("{output_format}", problem.output_format[:2000])
        prompt = prompt.replace("{sample_tests_json}", sample_tests_json)
        prompt = prompt.replace("{current_solution_cpp}", current_sol)
        prompt = prompt.replace("{current_generator_cpp}", current_gen)
        prompt = prompt.replace("{current_script_lines}", "\n".join(current_script))
        prompt = prompt.replace("{error_details}", str(error_details)[:4000])

        try:
            res = self.llm.generate_json(prompt)
            return {
                "solution_cpp": self._sanitize_cpp_code(res.get("solution_cpp") or current_sol, is_testlib=False),
                "generator_cpp": self._sanitize_cpp_code(res.get("generator_cpp") or current_gen, is_testlib=True),
                "test_script_lines": res.get("test_script_lines") or current_script,
                "explanation": res.get("explanation", ""),
            }
        except Exception:
            return {
                "solution_cpp": current_sol,
                "generator_cpp": current_gen,
                "test_script_lines": current_script,
                "explanation": "Failed to call AI fix",
            }
