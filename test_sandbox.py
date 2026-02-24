import sys
from pathlib import Path

# Add project root to path
sys.path.append(str(Path(__file__).parent))

from src.utils.cpp_execution import sanitize_cpp, compile_cpp, run_program, ExecutionLimits

def test_sanitizer():
    bad_code = """
#include <iostream>
#include <unistd.h>
int main() { system("rm -rf /"); }
"""
    try:
        sanitize_cpp(bad_code)
        print("FAIL: Sanitizer missed bad code")
    except ValueError as e:
        print(f"PASS: Sanitizer caught it: {e}")

def test_timeout():
    # Write a quick infinite loop
    srcpath = Path("temp_loop.cpp")
    exepath = Path("temp_loop.exe" if sys.platform == "win32" else "temp_loop")
    srcpath.write_text("int main() { while(true) {} return 0; }")
    
    ok, msg = compile_cpp(srcpath, exepath)
    if not ok:
        print(f"FAIL: Compile failed: {msg}")
        return
        
    limits = ExecutionLimits(wall_seconds=1)
    print("Running infinite loop with 1s timeout...")
    ret, out, err = run_program(exepath, limits=limits)
    
    if ret == 124 and "Time Limit Exceeded" in err:
        print("PASS: Timeout correctly handled yielding 124.")
    else:
        print(f"FAIL: Expected 124 timeout, got {ret}, err: {err}")
        
    srcpath.unlink(missing_ok=True)
    exepath.unlink(missing_ok=True)

if __name__ == "__main__":
    print("--- Running Sandbox Security & Timeout Tests (T1.1, T1.2) ---")
    test_sanitizer()
    test_timeout()
    print("--- Tests Finished ---\n")
