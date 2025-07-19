#!/usr/bin/env python3
"""
Run all tests for the RO Design MCP Server.

This script runs all test suites and provides a summary of results.
"""

import subprocess
import sys
from pathlib import Path


def run_test_suite(test_file, description):
    """Run a single test suite and report results."""
    print(f"\n{'='*60}")
    print(f"Running {description}")
    print(f"{'='*60}")
    
    try:
        result = subprocess.run(
            [sys.executable, test_file],
            capture_output=True,
            text=True
        )
        
        if result.returncode == 0:
            print(f"[PASS] {description}")
            return True
        else:
            print(f"[FAIL] {description}")
            print("\nOutput:")
            print(result.stdout)
            if result.stderr:
                print("\nErrors:")
                print(result.stderr)
            return False
    except Exception as e:
        print(f"[ERROR] {description}: {str(e)}")
        return False


def main():
    """Run all test suites."""
    tests_dir = Path(__file__).parent / "tests"
    
    # Define test suites
    test_suites = [
        ("test_no_duplicates.py", "No Duplicate Functions Test"),
        ("test_salt_passage_required.py", "Salt Passage Parameter Test"),
        ("test_tds_fix.py", "TDS Calculation Fix Test"),
        ("test_api.py", "API Endpoints Test"),
        ("test_notebook_execution.py", "Notebook Execution Test"),
    ]
    
    # Run each test suite
    results = []
    for test_file, description in test_suites:
        test_path = tests_dir / test_file
        if test_path.exists():
            passed = run_test_suite(str(test_path), description)
            results.append((description, passed))
        else:
            print(f"\n[SKIP] {description} - file not found: {test_file}")
            results.append((description, None))
    
    # Summary
    print(f"\n{'='*60}")
    print("TEST SUMMARY")
    print(f"{'='*60}")
    
    passed = sum(1 for _, result in results if result is True)
    failed = sum(1 for _, result in results if result is False)
    skipped = sum(1 for _, result in results if result is None)
    
    for description, result in results:
        if result is True:
            print(f"[PASS] {description}")
        elif result is False:
            print(f"[FAIL] {description}")
        else:
            print(f"[SKIP] {description}")
    
    print(f"\nTotal: {len(results)} tests")
    print(f"Passed: {passed}")
    print(f"Failed: {failed}")
    print(f"Skipped: {skipped}")
    
    # Return non-zero exit code if any tests failed
    sys.exit(1 if failed > 0 else 0)


if __name__ == "__main__":
    main()