import sys
import subprocess

PQ_TIMEOUT_SECONDS = 60


def parse_query_input(path: str = "query_input.txt") -> tuple[str, list[tuple[str, str]]]:
    query_name = ""
    data_files: list[tuple[str, str]] = []
    current_file = None
    current_desc: list[str] = []

    with open(path, encoding="utf-8") as f:
        for raw in f:
            line = raw.rstrip("\n")
            if line.strip().startswith("query_name:"):
                query_name = line.split(":", 1)[1].strip()
            elif line.strip().startswith("data_file:"):
                if current_file is not None:
                    data_files.append((current_file, " ".join(current_desc).strip()))
                current_file = line.split(":", 1)[1].strip()
                current_desc = []
            else:
                if current_file is not None:
                    current_desc.append(line.strip())
        if current_file is not None:
            data_files.append((current_file, " ".join(current_desc).strip()))

    return query_name, data_files


def run_pq(program_path: str) -> tuple[str, str, int | None]:
    """Returns (stdout, stderr, returncode). returncode is None on timeout."""
    try:
        result = subprocess.run(
            [sys.executable, program_path],
            capture_output=True,
            text=True,
            timeout=PQ_TIMEOUT_SECONDS,
        )
        return result.stdout, result.stderr, result.returncode
    except subprocess.TimeoutExpired as e:
        return (e.stdout or "", e.stderr or "", None)
