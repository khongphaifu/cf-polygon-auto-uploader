import json
import re
from typing import Dict, Any, List
from core.models import ProblemData, SampleTestCase, GeneratedCode, TestCase
from core.ai_engine.llm_client import LLMClient
from core.ai_engine.prompts import PARSE_PROBLEM_PROMPT, GENERATE_CODE_PROMPT, GENERATE_TESTS_PROMPT
from core.ai_engine.local_verifier import LocalVerifier


class AIPipeline:
    """Orchestrates problem parsing and code/test generation using LLM."""

    def __init__(self, llm_client: LLMClient):
        self.llm = llm_client

    def parse_problem_content(self, source_url: str, raw_content: str) -> ProblemData:
        """Parse raw crawled content into structured ProblemData."""
        prompt = PARSE_PROBLEM_PROMPT.replace("{raw_content}", raw_content[:25000])
        parsed_json = self.llm.generate_json(prompt)
        
        # Format sample tests
        sample_tests = []
        for s in parsed_json.get("sample_tests", []):
            sample_tests.append(
                SampleTestCase(
                    input_text=s.get("input_text", "").strip() + "\n",
                    output_text=s.get("output_text", "").strip() + "\n",
                    explanation=s.get("explanation"),
                )
            )

        # Sanitize short_name
        title = parsed_json.get("title", "Problem")
        short_name = parsed_json.get("short_name", "")
        if not short_name:
            short_name = re.sub(r"[^a-zA-Z0-9]+", "-", title.lower()).strip("-")
        short_name = re.sub(r"[^a-zA-Z0-9_-]", "-", short_name).lower()
        if len(short_name) > 30:
            short_name = short_name[:30].rstrip("-")

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
            raw_html=raw_content,
        )

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

    def generate_code_and_tests(self, problem: ProblemData, num_tests: int = 20) -> GeneratedCode:
        """Generate C++ solution, testlib validator, generator, and tests in separate optimized steps."""
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

        # 1. Step 1: Generate Code (Solution, Validator, Generator, Script)
        code_prompt = GENERATE_CODE_PROMPT.replace("{title}", problem.title)
        code_prompt = code_prompt.replace("{constraints}", problem.constraints or "Standard CP constraints")
        code_prompt = code_prompt.replace("{legend}", problem.legend[:4000])
        code_prompt = code_prompt.replace("{input_format}", problem.input_format[:2000])
        code_prompt = code_prompt.replace("{output_format}", problem.output_format[:2000])
        code_prompt = code_prompt.replace("{sample_tests_json}", sample_tests_json)
        code_prompt = code_prompt.replace("{checker_type}", problem.checker_type)

        code_result = self.llm.generate_json(code_prompt)

        sol_cpp = self._sanitize_cpp_code(code_result.get("solution_cpp", ""), is_testlib=False)
        brute_cpp = self._sanitize_cpp_code(code_result.get("brute_force_cpp", ""), is_testlib=False)
        val_cpp = self._sanitize_cpp_code(code_result.get("validator_cpp", ""), is_testlib=True)
        gen_cpp = self._sanitize_cpp_code(code_result.get("generator_cpp", ""), is_testlib=True)
        chk_cpp = code_result.get("custom_checker_cpp")
        if chk_cpp:
            chk_cpp = self._sanitize_cpp_code(chk_cpp, is_testlib=True)

        # 2. Step 2: Generate Tests (Standalone lightweight prompt)
        test_prompt = GENERATE_TESTS_PROMPT.replace("{title}", problem.title)
        test_prompt = test_prompt.replace("{constraints}", problem.constraints or "Standard CP constraints")
        test_prompt = test_prompt.replace("{input_format}", problem.input_format[:2000])
        test_prompt = test_prompt.replace("{sample_tests_json}", sample_tests_json)

        try:
            tests_result = self.llm.generate_json(test_prompt)
            raw_tests = tests_result.get("tests", [])
        except Exception:
            raw_tests = []

        test_cases: List[TestCase] = []
        for idx, t in enumerate(raw_tests, start=1):
            input_data = t.get("input_data", "")
            if not input_data.endswith("\n"):
                input_data += "\n"
            desc = t.get("description", f"Test {idx}")
            test_cases.append(
                TestCase(
                    test_index=idx,
                    input_data=input_data,
                    description=desc,
                    is_sample=False,
                )
            )

        # Ensure we have at least num_tests
        if len(test_cases) < num_tests:
            while len(test_cases) < num_tests:
                next_idx = len(test_cases) + 1
                base_test = test_cases[-1].input_data if test_cases else "1\n"
                test_cases.append(
                    TestCase(
                        test_index=next_idx,
                        input_data=base_test,
                        description=f"Generated Stress Test {next_idx}",
                        is_sample=False,
                    )
                )
        elif len(test_cases) > num_tests:
            test_cases = test_cases[:num_tests]

        for i, t in enumerate(test_cases, start=1):
            t.test_index = i

        gen_code = GeneratedCode(
            solution_cpp=sol_cpp,
            brute_force_cpp=brute_cpp,
            validator_cpp=val_cpp,
            generator_cpp=gen_cpp,
            checker_type=code_result.get("checker_type", problem.checker_type or "std::wcmp.cpp"),
            custom_checker_cpp=chk_cpp,
            tests=test_cases,
            test_script_lines=code_result.get("test_script_lines", []),
        )

        verifier = LocalVerifier()
        return verifier.verify_and_clean(problem=problem, code=gen_code, target_num_tests=num_tests)
