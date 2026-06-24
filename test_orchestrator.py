"""
Test — PharmaIntel BR Orchestrator
Run: python test_orchestrator.py
"""
import sys, io
from pathlib import Path
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, str(Path(__file__).parent))

from src.orchestrator import run_orchestrator, print_result

REQUEST = (
    "Evaluate Brazil opportunity for trastuzumab API/IFA and finished dosage forms. "
    "Identify ANVISA/CMED/import signals, sourcing route, Brazilian partner categories "
    "and recommended commercial action."
)

if __name__ == "__main__":
    print(f"\nREQUEST: {REQUEST}\n")
    result = run_orchestrator(REQUEST)
    print_result(result)
