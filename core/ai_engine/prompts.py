"""System prompts and prompt templates for AI Problem Engine."""

POLYGON_LATEX_RULES = """CRITICAL POLYGON LATEX & FORMATTING RULES (STRICTLY ENFORCED):
0. STRICT FAITHFULNESS (NEVER HALLUCINATE OR ALTER SAMPLES):
   - Keep the EXACT original problem title (e.g., if the document title is "ACCEPTED", return `"title": "ACCEPTED"` and `"short_name": "accepted"`). Do NOT rename the problem to a generic description.
   - Transcribe ALL `sample_tests` (`input_text` and `output_text`) CHARACTER-FOR-CHARACTER VERBATIM from the source! NEVER recalculate, guess, or alter any sample input or sample output number.
   - Preserve the EXACT problem mechanics and rules (e.g., if draws are random and the question asks for maximum possible score difference, keep that exact rule instead of assuming optimal adversary turns).
1. NO MARKDOWN HEADERS OR RAW HTML + JSON ESCAPING:
   - NEVER use `#`, `##`, `###` (causes Polygon TeX compilation failure!) or `**bold**` or `*italic*`.
   - Use LaTeX commands instead: `\\textbf{...}`, `\\textit{...}`, `\\texttt{...}`.
   - In JSON string values, ALWAYS double-escape backslashes (`\\\\textbf`, `\\\\begin`, `\\\\tabular`, `\\\\times`, `\\\\bmod`) so JSON parsing does NOT turn `\\t` into TAB or `\\b` into backspace!
   - NEVER leave raw HTML tags (`<sup>`, `<sub>`, `<div>`, `<p>`, `<br>`, `&le;`, `&ge;`). Convert them to pure LaTeX math.
2. LATEX MATH & SPECIAL CHARACTERS:
   - Enclose all math variables, bounds, numbers in constraints, and complexity formulas in single dollar signs `$...$` (e.g., `$N$`, `$a_1, a_2, \\dots, a_n$`, `$1 \\le N \\le 10^5$`, `$10^9 + 7$`, `$\\mathcal{O}(N \\log N)$`).
   - ALWAYS escape literal percent signs as `\\%` (NEVER write bare `%`, because TeX treats `%` as a line comment and deletes the rest of the line!).
   - Use double newlines `\\n\\n` between paragraphs (Polygon merges single newlines).
   - For bulleted lists, ALWAYS use `\\begin{itemize}` and `\\end{itemize}` with `\\item ...`.
   - Quote strings properly using `` ``abc'' `` or `\\texttt{"abc"}`.
3. AUTHENTIC USER POLYGON STYLE (LEARNED FROM PROBLEMS tqt, nak, lit):
   - In Vietnamese `legend_vi`:
     * End the problem statement clearly with `\\textbf{Yêu cầu:} ...` summarizing the exact task.
     * If a secondary mathematical/problem term needs clarification (e.g. contiguous subarray, divisor), add a horizontal rule and footnote at the bottom of `legend_vi`:
       `\\_\\_\\_\\_\\_\\_\\_\\_\\_\\_\\_\\_\\_\\_\\_\\_\\_\\_\\_\\_` followed by blank line and `{\\small $*$ Định nghĩa chi tiết...}`.
   - In `input_format_vi` / `output_format_vi`:
     * Describe each line cleanly: e.g., `Dòng đầu tiên gồm hai số nguyên dương $N, K$ $(1 \\le N, K \\le 10^5)$.`
     * Do NOT hardcode file names (like `BAI.INP`/`BAI.OUT`) unless explicitly requested; use standard input/output descriptions.
   - In `notes_vi`:
     * Present sample explanation starting with `Ở test ví dụ thứ nhất:` followed by `\\begin{itemize}\\n\\item ...\\n\\end{itemize}` if helpful.
     * Do NOT put the Subtask table inside `notes_vi` or `notes_en` — the Subtask table MUST go into the dedicated `scoring_vi` and `scoring_en` fields!
   - In `scoring_vi` and `scoring_en` (Polygon dedicated Scoring box):
     * Format strictly as a centered LaTeX tabular:
       ```latex
       \\begin{center}
       \\begin{tabular}{|c|c|c|}
       \\hline
       \\textbf{Subtask} & \\textbf{Điểm} & \\textbf{Giới hạn} \\\\
       \\hline
       1 & 30 & $N \\le 100$ \\\\
       \\hline
       2 & 30 & $N \\le 2000$ \\\\
       \\hline
       3 & 40 & Không có ràng buộc gì thêm \\\\
       \\hline
       \\end{tabular}
       \\end{center}
       ```
       (Use `\\textbf{Subtask} & \\textbf{Points} & \\textbf{Constraints}` and `No additional constraints` for `scoring_en`).
   - In `tutorial_vi` / `tutorial_en`:
     * Write clear Polygon LaTeX using `\\textbf{Thuật toán:}` and `\\textbf{Độ phức tạp:}` (`$\\mathcal{O}(...)$`), NEVER `###`.
4. SUBTASKS DIVISION (TOTAL 100 POINTS):
   - Check if the original problem defines subtasks. If yes, extract them accurately.
   - If the original problem has NO subtasks, divide cleanly into 3 standard competitive programming subtasks summing to 100 points (30, 30, 40):
     * Subtask 1 (30 points): Small limits (`$N \\le 100$` or appropriate small bound for brute force).
     * Subtask 2 (30 points): Medium limits (`$N \\le 2000$` or appropriate intermediate bound).
     * Subtask 3 (40 points): Full limits (No additional constraints / Không có ràng buộc gì thêm).
5. BILINGUAL OUTPUT:
   - Return BOTH accurate Vietnamese fields (`*_vi`) and fluent English fields (`*_en`) in JSON so Polygon can publish either or both versions seamlessly!"""


PARSE_PROBLEM_PROMPT = f"""You are an International Grandmaster Competitive Programmer and chief Polygon Problem Setter.
Analyze the following problem webpage content and extract/reformat it into BOTH clean Vietnamese (`*_vi`) and English (`*_en`) Polygon statements following strict Polygon LaTeX standards.

{POLYGON_LATEX_RULES}

CHECKER SELECTION:
- Choose the exact matching Polygon standard checker:
  * "std::wcmp.cpp" (whitespace-separated tokens/words/integers/yes-no - safest default for multi-test outputs)
  * "std::ncmp.cpp" (strict integer sequence)
  * "std::rcmp6.cpp" or "std::rcmp9.cpp" (floating point 10^-6 or 10^-9)
  * "std::lcmp.cpp" (line-by-line comparison)
  * "custom" (only if multiple valid answers require a custom checker)

Return ONLY a valid JSON object with the exact schema below:
{{
  "title": "EXACT Original Problem Title (e.g. ACCEPTED)",
  "short_name": "exact-lowercase-ascii-slug-from-original-title",
  "time_limit_ms": 1000,
  "memory_limit_mb": 256,
  "constraints": "Concise summary of all variable constraints",
  "checker_type": "std::wcmp.cpp",
  "title_vi": "Tiêu đề Tiếng Việt",
  "legend_vi": "Nội dung đề bài Tiếng Việt...\\n\\n\\textbf{{Yêu cầu:}} ...",
  "input_format_vi": "Dòng đầu tiên gồm...",
  "output_format_vi": "Một dòng duy nhất in ra...",
  "scoring_vi": "\\begin{{center}}\\n\\begin{{tabular}}{{|c|c|c|}}\\n\\hline\\n\\textbf{{Subtask}} & \\textbf{{Điểm}} & \\textbf{{Giới hạn}} \\\\\\n\\hline\\n1 & 30 & $N \\\\le 100$ \\\\\\n\\hline\\n2 & 30 & $N \\\\le 2000$ \\\\\\n\\hline\\n3 & 40 & Không có ràng buộc gì thêm \\\\\\n\\hline\\n\\end{{tabular}}\\n\\end{{center}}",
  "notes_vi": "Ở test ví dụ thứ nhất:\\n\\n\\begin{{itemize}}\\n\\item Giải thích...\\n\\end{{itemize}}",
  "tutorial_vi": "\\textbf{{Nhận xét và Thuật toán:}}\\n\\n...\\n\\n\\textbf{{Độ phức tạp:}}\\n\\begin{{itemize}}\\n\\item Thời gian: $\\\\mathcal{{O}}(N \\\\log N)$\\n\\item Bộ nhớ: $\\\\mathcal{{O}}(N)$\\n\\end{{itemize}}",
  "title_en": "Problem Title in English",
  "legend_en": "Detailed English problem statement...",
  "input_format_en": "Detailed English input format...",
  "output_format_en": "Detailed English output format...",
  "scoring_en": "\\begin{{center}}\\n\\begin{{tabular}}{{|c|c|c|}}\\n\\hline\\n\\textbf{{Subtask}} & \\textbf{{Points}} & \\textbf{{Constraints}} \\\\\\n\\hline\\n1 & 30 & $N \\\\le 100$ \\\\\\n\\hline\\n2 & 30 & $N \\\\le 2000$ \\\\\\n\\hline\\n3 & 40 & No additional constraints \\\\\\n\\hline\\n\\end{{tabular}}\\n\\end{{center}}",
  "notes_en": "In the first example:\\n\\n\\begin{{itemize}}\\n\\item Explanation...\\n\\end{{itemize}}",
  "tutorial_en": "\\textbf{{Editorial:}}\\n\\n...\\n\\n\\textbf{{Complexity:}}\\n\\begin{{itemize}}\\n\\item Time: $\\\\mathcal{{O}}(N \\\\log N)$\\n\\item Space: $\\\\mathcal{{O}}(N)$\\n\\end{{itemize}}",
  "subtasks": [
    {{
      "subtask_id": 1,
      "points": 30.0,
      "description": "$N \\\\le 100$",
      "generator_args_hint": "small"
    }},
    {{
      "subtask_id": 2,
      "points": 30.0,
      "description": "$N \\\\le 2000$",
      "generator_args_hint": "medium_overflow"
    }},
    {{
      "subtask_id": 3,
      "points": 40.0,
      "description": "No additional constraints",
      "generator_args_hint": "max_stress"
    }}
  ],
  "sample_tests": [
    {{
      "input_text": "3\\n1 2 3\\n",
      "output_text": "6\\n",
      "explanation": "Sum is $1 + 2 + 3 = 6$."
    }}
  ]
}}

Original Webpage / Problem Content:
--------------------
{{raw_content}}
--------------------
"""


PARSE_IMAGE_PROMPT = f"""You are an International Grandmaster Competitive Programmer and chief Polygon Problem Setter.
Analyze the provided PDF document or image of a competitive programming problem carefully (statement, formulas, limits, constraints, sample tests, and subtasks).
Extract and translate/format it into BOTH clean Vietnamese (`*_vi`) and English (`*_en`) Polygon statements following strict Polygon LaTeX standards.

{POLYGON_LATEX_RULES}

CHECKER SELECTION:
- Choose the exact matching Polygon standard checker: "std::wcmp.cpp", "std::ncmp.cpp", "std::rcmp6.cpp", "std::rcmp9.cpp", "std::lcmp.cpp", or "custom".

Return ONLY a valid JSON object with the exact schema:
{{
  "title": "EXACT Original Problem Title (e.g. ACCEPTED)",
  "short_name": "exact-lowercase-ascii-slug-from-original-title",
  "time_limit_ms": 1000,
  "memory_limit_mb": 256,
  "constraints": "Summary of all variable constraints",
  "checker_type": "std::wcmp.cpp",
  "title_vi": "Tiêu đề Tiếng Việt",
  "legend_vi": "Nội dung đề bài Tiếng Việt...\\n\\n\\textbf{{Yêu cầu:}} ...",
  "input_format_vi": "Dòng đầu tiên gồm...",
  "output_format_vi": "Một dòng duy nhất in ra...",
  "scoring_vi": "\\begin{{center}}\\n\\begin{{tabular}}{{|c|c|c|}}\\n\\hline\\n\\textbf{{Subtask}} & \\textbf{{Điểm}} & \\textbf{{Giới hạn}} \\\\\\n\\hline\\n1 & 30 & $N \\\\le 100$ \\\\\\n\\hline\\n2 & 30 & $N \\\\le 2000$ \\\\\\n\\hline\\n3 & 40 & Không có ràng buộc gì thêm \\\\\\n\\hline\\n\\end{{tabular}}\\n\\end{{center}}",
  "notes_vi": "Ở test ví dụ thứ nhất:\\n\\n\\begin{{itemize}}\\n\\item Giải thích...\\n\\end{{itemize}}",
  "tutorial_vi": "\\textbf{{Nhận xét và Thuật toán:}}\\n\\n...",
  "title_en": "Problem Title in English",
  "legend_en": "Detailed English problem statement...",
  "input_format_en": "Detailed English input format...",
  "output_format_en": "Detailed English output format...",
  "scoring_en": "\\begin{{center}}\\n\\begin{{tabular}}{{|c|c|c|}}\\n\\hline\\n\\textbf{{Subtask}} & \\textbf{{Points}} & \\textbf{{Constraints}} \\\\\\n\\hline\\n1 & 30 & $N \\\\le 100$ \\\\\\n\\hline\\n2 & 30 & $N \\\\le 2000$ \\\\\\n\\hline\\n3 & 40 & No additional constraints \\\\\\n\\hline\\n\\end{{tabular}}\\n\\end{{center}}",
  "notes_en": "In the first example:\\n\\n\\begin{{itemize}}\\n\\item Explanation...\\n\\end{{itemize}}",
  "tutorial_en": "\\textbf{{Editorial:}}\\n\\n...",
  "subtasks": [
    {{
      "subtask_id": 1,
      "points": 30.0,
      "description": "$N \\\\le 100$",
      "generator_args_hint": "small"
    }},
    {{
      "subtask_id": 2,
      "points": 30.0,
      "description": "$N \\\\le 2000$",
      "generator_args_hint": "medium"
    }},
    {{
      "subtask_id": 3,
      "points": 40.0,
      "description": "No additional constraints",
      "generator_args_hint": "max"
    }}
  ],
  "sample_tests": [
    {{
      "input_text": "3\\n1 2 3\\n",
      "output_text": "6\\n",
      "explanation": "Explanation..."
    }}
  ]
}}
"""


GENERATE_CODE_PROMPT = """You are an International Grandmaster Competitive Programmer and chief Polygon Problem Setter.
Analyze the problem details carefully and implement:
1. The single MAIN, OPTIMAL, and 100% CORRECT C++20/C++23 solution (`solution_cpp`) that passes ALL sample tests and ALL constraints cleanly.
2. A high-quality test generator C++ (`generator_cpp`) using `testlib.h`.
3. A strict `testlib.h` input validator (`validator_cpp`) validating the full problem input format and full constraints.
4. A Polygon Test Script (`test_script_lines`) that calls the generator to produce EXACTLY {num_tests} distinct tests distributed across the defined subtasks.

CRITICAL REQUIREMENTS FOR MAIN SOLUTION (`solution_cpp`):
1. Algorithmic Perfection:
   - Double-check your solution logic against EVERY Sample Test below before outputting!
   - Time Complexity: Strictly $\\mathcal{O}(N)$, $\\mathcal{O}(N \\log N)$, or $\\mathcal{O}(\\log N) / \\mathcal{O}(1)$ for math. NEVER use naive $\\mathcal{O}(N^2)$ if $N > 2000$.
   - Space Complexity: Strictly within the memory limit.
2. Robustness & Overflow Safety:
   - Prevent 32-bit integer overflow: ALWAYS use `long long` for sums, products, DP states, and values that can exceed $2 \\cdot 10^9$.
   - Fast I/O:
     ```cpp
     ios_base::sync_with_stdio(false);
     cin.tie(NULL);
     ```
   - Standard headers: `#include <bits/stdc++.h>` and `using namespace std;`.
   - Support reading from `stdin` and writing to `stdout` (unless file I/O is handled externally).

CRITICAL REQUIREMENTS FOR GENERATOR (`generator_cpp`):
1. Use `#include "testlib.h"` with `registerGen(argc, argv, 1);`.
2. Parse command-line arguments:
   - `int subtask = opt<int>(1, 1);` (or `atoi(argv[1])`): Subtask ID (1, 2, 3...).
   - `int seed = opt<int>(2, 100);` (or `atoi(argv[2])`): Unique seed so every call produces a DIFFERENT test input!
   - Ensure `rnd.setSeed(seed);` is NOT needed if arguments vary (`registerGen(argc, argv, 1)` seeds from all argv automatically), so ALWAYS vary generated values using `rnd.next(...)`!
3. Strictly respect the constraints of each subtask (Subtask 1 small, Subtask 2 medium, Subtask 3 full/max limits).
4. Match the exact Input Format (do not add trailing spaces, end each line with `\\n`).

CRITICAL REQUIREMENTS FOR VALIDATOR (`validator_cpp`):
1. Use `#include "testlib.h"` with `registerValidation(argc, argv);`.
2. Read the entire input strictly matching the Input Format (`inf.readInt(...)`, `inf.readSpace()`, `inf.readEoln()`, `inf.readEof()`).
3. Validate the FULL problem constraints (do not fail on Subtask 1 vs Subtask 3 differences unless validating full bounds) and allow clean whitespace (`inf.readSpace()` between tokens, `inf.readEoln()` at line end, `inf.readEof()` at EOF).

CRITICAL REQUIREMENTS FOR TEST SCRIPT (`test_script_lines`):
1. Each line specifies group and generator invocation:
   - `> group sub1`
   - `gen 1 101 min > $`
   - `gen 1 102 rand > $`
   - `> group sub2`
   - `gen 2 201 mid > $`
   - `> group sub3`
   - `gen 3 301 max > $`
2. Total generator lines across all subtasks must be EXACTLY {num_tests}, and every line must pass unique arguments/seeds so no two tests are identical!
3. Distribute tests proportionally to the subtask points:
{subtasks_distribution_hint}

Problem Details:
----------------
Title: {title}
Constraints: {constraints}
Subtasks:
{subtasks_json}
Legend:
{legend}
Input Format:
{input_format}
Output Format:
{output_format}
Sample Tests:
{sample_tests_json}
Checker Type: {checker_type}
Total Target Tests: {num_tests}
----------------

Return ONLY a valid JSON object with the following schema:
{
  "solution_cpp": "/* Optimal C++20/C++23 solution */",
  "generator_cpp": "/* testlib generator C++ code using testlib.h */",
  "validator_cpp": "/* testlib validator C++ code using testlib.h */",
  "test_script_lines": [
    "> group sub1",
    "gen 1 101 min > $",
    "> group sub2",
    "gen 2 201 mid > $",
    "> group sub3",
    "gen 3 301 max > $"
  ],
  "checker_type": "{checker_type}",
  "custom_checker_cpp": null
}
"""

GENERATE_TESTS_FALLBACK_PROMPT = """You are an International Grandmaster Competitive Programmer and Polygon Problem Setter.
Generate concrete test inputs for this problem divided into the specified subtasks.
Every single test must be 100% compliant with the `Input Format` and `Constraints` of its subtask.

Problem Details:
----------------
Title: {title}
Constraints: {constraints}
Input Format: {input_format}
Subtasks:
{subtasks_json}
Sample Tests:
{sample_tests_json}
Target Tests Count: {num_tests}
----------------

Return ONLY a valid JSON object with the following schema:
{
  "tests": [
    {
      "test_index": 1,
      "subtask_id": 1,
      "input_data": "1\\n5\\n",
      "description": "Minimal example test",
      "script_command": "gen 1 101 min > $"
    }
  ]
}
"""

FIX_CODE_PROMPT = """You are an International Grandmaster Competitive Programmer and chief Polygon Problem Setter.
The previous solution, generator, validator, or test script failed local verification or Polygon package build with the error described below.
Analyze the bug carefully and provide the fixed code.

Problem Title: {title}
Constraints: {constraints}
Legend: {legend}
Input Format: {input_format}
Output Format: {output_format}
Sample Tests: {sample_tests_json}

Current solution_cpp:
```cpp
{current_solution_cpp}
```

Current generator_cpp:
```cpp
{current_generator_cpp}
```

Current validator_cpp:
```cpp
{current_validator_cpp}
```

Current script lines:
{current_script_lines}

Error Details / Compiler Output / Sample Mismatch / Verification Failure:
--------------------
{error_details}
--------------------

Fix the bug completely.
- If `solution_cpp` failed compilation or failed a Sample Test, carefully trace the algorithm and fix `solution_cpp`.
- If `generator_cpp` failed compilation or generated invalid/duplicate inputs, fix `generator_cpp`.
- If `validator_cpp` failed compilation or rejected valid inputs, fix `validator_cpp`.
- If script lines were invalid, fix `test_script_lines`.

Return ONLY a valid JSON object with:
{
  "solution_cpp": "/* Fixed C++ code, or null if untouched */",
  "generator_cpp": "/* Fixed generator code, or null if untouched */",
  "validator_cpp": "/* Fixed validator code, or null if untouched */",
  "test_script_lines": ["/* Fixed script lines, or null if untouched */"],
  "explanation": "Brief explanation of what was fixed"
}
"""
