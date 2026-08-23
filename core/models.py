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
    checker_type: str = "std::wcmp.cpp"
    sample_tests: List[SampleTestCase] = field(default_factory=list)
    raw_html: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class TestCase:
    test_index: int
    input_data: str
    description: str = ""
    is_sample: bool = False
    group: Optional[str] = None
    points: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class GeneratedCode:
    solution_cpp: str
    validator_cpp: str
    generator_cpp: str
    brute_force_cpp: str = ""  # Correct naive O(N^2) or O(2^N) solution for double stress-testing
    solution_tl_cpp: str = ""  # Intentionally slow O(N^2) solution tagged TL on Polygon
    solution_wa_cpp: str = ""  # Intentionally flawed greedy/overflow solution tagged WA on Polygon
    solution_py: str = ""      # Python 3 solution for cross-language compatibility
    checker_type: str = "std::wcmp.cpp"  # std::wcmp.cpp, std::ncmp.cpp, std::rcmp6.cpp, std::yesno.cpp, or custom
    custom_checker_cpp: Optional[str] = None
    tests: List[TestCase] = field(default_factory=list)
    test_script_lines: List[str] = field(default_factory=list)

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

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
