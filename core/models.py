from dataclasses import dataclass, field, asdict
from typing import List, Optional, Dict, Any


@dataclass
class SampleTestCase:
    input_text: str
    output_text: str
    explanation: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class SubtaskData:
    subtask_id: int            # 1, 2, 3...
    points: float              # e.g. 30.0, 40.0
    description: str           # e.g. "n <= 100, a_i <= 1000"
    generator_args_hint: str = ""   # e.g. "small"
    test_count: int = 0        # number of tests allocated for this subtask

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ProblemData:
    source_url: str
    title: str
    short_name: str = ""
    legend: str = ""  # Problem statement story/description in LaTeX/Markdown
    input_format: str = ""
    output_format: str = ""
    constraints: str = ""
    notes: Optional[str] = None
    tutorial: str = ""  # Detailed editorial/tutorial in LaTeX
    time_limit_ms: int = 1000
    memory_limit_mb: int = 256
    checker_type: str = "std::lcmp.cpp"
    sample_tests: List[SampleTestCase] = field(default_factory=list)
    subtasks: List[SubtaskData] = field(default_factory=list)
    raw_html: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class TestCase:
    test_index: int
    input_data: str
    expected_output: Optional[str] = None  # Generated directly from solution.cpp execution
    description: str = ""
    is_sample: bool = False
    subtask_id: Optional[int] = None
    group: Optional[str] = None
    points: Optional[float] = None
    script_command: Optional[str] = None  # Command in Polygon script (e.g. "gen 1 101 min > $")

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class GeneratedCode:
    solution_cpp: str
    validator_cpp: str = ""
    generator_cpp: str = ""
    brute_force_cpp: str = ""  # Optional reference solution
    solution_tl_cpp: str = ""
    solution_wa_cpp: str = ""
    solution_py: str = ""
    checker_type: str = "std::lcmp.cpp"  # std::wcmp.cpp, std::ncmp.cpp, std::rcmp6.cpp, std::yesno.cpp, or custom
    custom_checker_cpp: Optional[str] = None
    tests: List[TestCase] = field(default_factory=list)
    test_script_lines: List[str] = field(default_factory=list)
    subtasks: List[SubtaskData] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class PolygonProblemRecord:
    id: int
    name: str
    owner: Optional[str] = None
    access_type: Optional[str] = None
    url: str = ""
    cf_import_url: str = ""  # Direct link used to import to Codeforces (e.g. https://polygon.codeforces.com/p577274/luatgay/three-numbers-on-the-blackboar)
    package_id: Optional[int] = None
    package_state: Optional[str] = None
    access_granted_to_cf: bool = False
    source_url: str = ""
    created_at: str = ""
    status: str = "PENDING"  # PENDING, SUCCESS, FAILED
    error_message: Optional[str] = None
    total_tests: int = 0
    subtasks_summary: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
