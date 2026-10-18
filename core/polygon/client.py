import hashlib
import json
import random
import string
import time
from typing import Any, Dict, List, Optional, Union
import requests


class PolygonAPIError(Exception):
    """Exception raised when Polygon API returns an error or request fails."""
    pass


class PolygonClient:
    """Client for interacting with the Polygon Codeforces REST API."""

    def __init__(
        self,
        api_key: str,
        api_secret: str,
        api_url: str = "https://polygon.codeforces.com/api/",
        timeout: int = 60,
    ):
        self.api_key = api_key
        self.api_secret = api_secret
        self.api_url = api_url.rstrip("/") + "/"
        self.timeout = timeout
        self.session = requests.Session()

    def _generate_signature(self, method_name: str, params: Dict[str, Any]) -> str:
        """
        Generate Polygon API signature (apiSig).
        Format: 6_random_chars + SHA512(6_random_chars/methodName?k1=v1&k2=v2...#apiSecret)
        """
        rand_prefix = "".join(random.choices(string.ascii_lowercase + string.digits, k=6))
        
        # Sort parameters alphabetically by key, then value
        sorted_params = sorted(params.items(), key=lambda item: (item[0], str(item[1])))
        param_query = "&".join(f"{k}={v}" for k, v in sorted_params)
        
        to_hash = f"{rand_prefix}/{method_name}?{param_query}#{self.api_secret}"
        sha512_hash = hashlib.sha512(to_hash.encode("utf-8")).hexdigest()
        
        return f"{rand_prefix}{sha512_hash}"

    def request(
        self,
        method_name: str,
        params: Optional[Dict[str, Any]] = None,
        files: Optional[Dict[str, Any]] = None,
        max_retries: int = 5,
    ) -> Any:
        """
        Send a signed request to Polygon API with automatic retry on transient failures and 429 backoff.
        """
        base_params = dict(params or {})
        url = f"{self.api_url}{method_name}"
        
        last_error = None
        for attempt in range(1, max_retries + 1):
            try:
                # Regenerate fresh timestamp and signature for each retry attempt
                req_params = dict(base_params)
                req_params["apiKey"] = self.api_key
                req_params["time"] = int(time.time())
                req_params["apiSig"] = self._generate_signature(method_name, req_params)
                
                if files:
                    response = self.session.post(
                        url,
                        data=req_params,
                        files=files,
                        timeout=self.timeout,
                    )
                else:
                    response = self.session.post(
                        url,
                        data=req_params,
                        timeout=self.timeout,
                    )
                
                if response.status_code == 429:
                    # Polygon / Cloudflare Rate Limit -> sleep longer and retry
                    last_error = PolygonAPIError(f"HTTP 429 Too Many Requests on {method_name}")
                    sleep_time = 4 * attempt
                    time.sleep(sleep_time)
                    continue
                
                if response.status_code != 200:
                    try:
                        err_json = response.json()
                        err_msg = err_json.get("comment", response.text)
                    except Exception:
                        err_msg = response.text
                    raise PolygonAPIError(f"HTTP {response.status_code}: {err_msg}")
                
                try:
                    res_data = response.json()
                except Exception:
                    # Some endpoints (e.g. problem.script) return text/plain directly
                    return response.text

                if res_data.get("status") != "OK":
                    comment = res_data.get("comment", "Unknown Polygon error")
                    raise PolygonAPIError(f"Polygon API error in {method_name}: {comment}")
                
                return res_data.get("result")

            
            except (requests.RequestException, PolygonAPIError) as e:
                last_error = e
                if attempt < max_retries:
                    sleep_time = 2 * attempt
                    time.sleep(sleep_time)
                else:
                    raise PolygonAPIError(f"Failed calling {method_name} after {max_retries} attempts: {last_error}")

    # ==================== Problem Management ====================

    def list_problems(self) -> List[Dict[str, Any]]:
        """Return list of all problems accessible by the user."""
        return self.request("problems.list")

    def create_problem(self, name: str) -> Dict[str, Any]:
        """Create a new problem with specified name."""
        return self.request("problem.create", {"name": name})

    def get_info(self, problem_id: int) -> Dict[str, Any]:
        """Get problem info (time limit, memory limit, IO files)."""
        return self.request("problem.info", {"problemId": problem_id})

    def update_info(
        self,
        problem_id: int,
        time_limit_ms: int = 1000,
        memory_limit_mb: int = 256,
        interactive: bool = False,
        input_file: str = "",
        output_file: str = "",
    ) -> None:
        """Update problem general info."""
        params = {
            "problemId": problem_id,
            "timeLimit": time_limit_ms,
            "memoryLimit": memory_limit_mb,
            "interactive": "true" if interactive else "false",
            "inputFile": input_file,
            "outputFile": output_file,
        }
        self.request("problem.updateInfo", params)

    # ==================== Statements ====================

    def get_statements(self, problem_id: int) -> Dict[str, Any]:
        """Get existing statements for problem."""
        return self.request("problem.statements", {"problemId": problem_id})

    def save_statement(
        self,
        problem_id: int,
        lang: str = "english",
        encoding: str = "UTF-8",
        name: str = "",
        legend: str = "",
        input_format: str = "",
        output_format: str = "",
        notes: str = "",
        tutorial: str = "",
    ) -> None:
        """Save problem statement."""
        params = {
            "problemId": problem_id,
            "lang": lang,
            "encoding": encoding,
            "name": name,
            "legend": legend,
            "input": input_format,
            "output": output_format,
            "notes": notes,
            "tutorial": tutorial,
        }
        self.request("problem.saveStatement", params)

    # ==================== Files & Resources ====================

    def list_files(self, problem_id: int) -> Dict[str, Any]:
        """List files (source files, resource files) attached to problem."""
        return self.request("problem.files", {"problemId": problem_id})

    def save_file(
        self,
        problem_id: int,
        file_type: str,  # "source" or "resource"
        name: str,
        content: Union[str, bytes],
        source_type: Optional[str] = "cpp.g++17",
        check_existing: bool = False,
    ) -> None:
        """Save a source or resource file."""
        if isinstance(content, bytes):
            content_str = content.decode("utf-8", errors="replace")
        else:
            content_str = content

        params = {
            "problemId": problem_id,
            "type": file_type,
            "name": name,
            "file": content_str,
            "checkExisting": "true" if check_existing else "false",
        }
        if file_type == "source" and source_type and name.endswith(".cpp"):
            params["sourceType"] = source_type

        self.request("problem.saveFile", params=params)

    # ==================== Checker & Validator ====================

    def set_validator(self, problem_id: int, validator_name: str) -> None:
        """Set problem validator filename (e.g. validator.cpp)."""
        self.request("problem.setValidator", {
            "problemId": problem_id,
            "validator": validator_name,
        })

    def set_checker(self, problem_id: int, checker_name: str) -> None:
        """
        Set problem checker (standard checker like std::wcmp.cpp or custom checker filename).
        """
        self.request("problem.setChecker", {
            "problemId": problem_id,
            "checker": checker_name,
        })

    # ==================== Solutions ====================

    def list_solutions(self, problem_id: int) -> List[Dict[str, Any]]:
        """List all solutions for problem."""
        return self.request("problem.solutions", {"problemId": problem_id})

    def save_solution(
        self,
        problem_id: int,
        name: str,
        content: str,
        tag: str = "MA",  # MA = Main correct solution, OK = Correct
        source_type: Optional[str] = "cpp.g++17",
        check_existing: bool = False,
    ) -> None:
        """Save solution file with tag (MA, OK, WA, TL, ML, RE, etc.)."""
        params = {
            "problemId": problem_id,
            "name": name,
            "file": content,
            "tag": tag,
            "checkExisting": "true" if check_existing else "false",
        }
        if source_type and name.endswith(".cpp"):
            params["sourceType"] = source_type

        self.request("problem.saveSolution", params=params)

    # ==================== Tests & Script ====================

    def list_tests(self, problem_id: int, testset: str = "tests") -> List[Dict[str, Any]]:
        """List tests in testset."""
        result = self.request("problem.tests", {"problemId": problem_id, "testset": testset})
        return result if result else []

    def clear_all_tests(self, problem_id: int, testset: str = "tests") -> None:
        """Remove all existing tests by overwriting testset script with empty, then removing tests one by one."""
        try:
            existing = self.list_tests(problem_id=problem_id, testset=testset)
            # Delete from last to first to avoid reindexing issues
            for test in reversed(existing):
                idx = test.get("index")
                if idx is not None:
                    try:
                        self.request("problem.removeTest", {
                            "problemId": problem_id,
                            "testset": testset,
                            "testIndex": idx,
                        })
                    except Exception:
                        pass
        except Exception:
            pass

    def save_test(
        self,
        problem_id: int,
        test_index: int,
        test_input: str,
        testset: str = "tests",
        test_group: Optional[str] = None,
        test_points: Optional[float] = None,
        test_description: Optional[str] = None,
        use_in_statements: bool = False,
        check_existing: bool = False,
    ) -> None:
        """Save a single test input."""
        params: Dict[str, Any] = {
            "problemId": problem_id,
            "testset": testset,
            "testIndex": test_index,
            "testInput": test_input,
            "testUseInStatements": "true" if use_in_statements else "false",
            "checkExisting": "true" if check_existing else "false",
        }
        if test_group:
            params["testGroup"] = test_group
        if test_points is not None:
            params["testPoints"] = test_points
        if test_description:
            params["testDescription"] = test_description

        self.request("problem.saveTest", params)

    def get_script(self, problem_id: int, testset: str = "tests") -> Optional[str]:
        """Get test generator script."""
        return self.request("problem.script", {"problemId": problem_id, "testset": testset})

    def save_script(self, problem_id: int, script_content: str, testset: str = "tests") -> None:
        """Save test generation script."""
        self.request("problem.saveScript", {
            "problemId": problem_id,
            "testset": testset,
            "source": script_content,
        })

    # ==================== Commit & Packages ====================

    def commit_changes(self, problem_id: int, message: str = "Auto-commit before packaging") -> Dict[str, Any]:
        """Commit working copy changes before building a package."""
        return self.request("problem.commitChanges", {
            "problemId": problem_id,
            "message": message,
        })

    def list_packages(self, problem_id: int) -> List[Dict[str, Any]]:
        """List packages for problem."""
        return self.request("problem.packages", {"problemId": problem_id})

    def create_package(self, problem_id: int, full: bool = True, verify: bool = True) -> Any:
        """Trigger package building job using problem.buildPackage."""
        return self.request("problem.buildPackage", {
            "problemId": problem_id,
            "full": "true" if full else "false",
            "verify": "true" if verify else "false",
        })
