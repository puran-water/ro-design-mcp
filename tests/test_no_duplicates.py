#!/usr/bin/env python3
"""
Test to ensure no duplicate function definitions across the codebase.

This test scans all Python files and Jupyter notebooks to detect any
duplicate function or constant definitions that should be imported
from utils instead.
"""

import ast
import json
from pathlib import Path
import pytest
import nbformat


# Functions and constants that should only be defined in utils
UTILS_ONLY_FUNCTIONS = {
    # RO model building
    "build_ro_model_mcas_with_recycle",
    "build_ro_model_mcas",
    
    # RO solving
    "initialize_and_solve_mcas",
    "initialize_model_sequential",
    "initialize_with_block_triangularization",
    "initialize_with_custom_guess",
    "initialize_with_relaxation",
    "initialize_model_advanced",
    
    # RO results extraction
    "extract_results_mcas",
    "predict_scaling_potential",
    
    # Other commonly duplicated functions
    "calculate_concentrate_tds",
    "calculate_required_pressure",
    "initialize_pump_with_pressure",
    "initialize_ro_unit_elegant",
    "initialize_multistage_ro_elegant",
}

UTILS_ONLY_CONSTANTS = {
    "TYPICAL_COMPOSITIONS",
    "MW_DATA",
    "CHARGE_MAP",
    "STOKES_RADIUS_DATA",
    "DEFAULT_SALT_PASSAGE",
}


def get_python_functions(file_path):
    """Extract function names from a Python file."""
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    try:
        tree = ast.parse(content)
        functions = set()
        constants = set()
        
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                functions.add(node.name)
            elif isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name) and target.id.isupper():
                        constants.add(target.id)
        
        return functions, constants
    except SyntaxError:
        return set(), set()


def get_notebook_functions(notebook_path):
    """Extract function names from a Jupyter notebook."""
    with open(notebook_path, 'r', encoding='utf-8') as f:
        nb = nbformat.read(f, as_version=4)
    
    functions = set()
    constants = set()
    
    for cell in nb.cells:
        if cell.cell_type == 'code':
            try:
                tree = ast.parse(cell.source)
                for node in ast.walk(tree):
                    if isinstance(node, ast.FunctionDef):
                        functions.add(node.name)
                    elif isinstance(node, ast.Assign):
                        for target in node.targets:
                            if isinstance(target, ast.Name) and target.id.isupper():
                                constants.add(target.id)
            except SyntaxError:
                pass
    
    return functions, constants


def find_violations():
    """Find all files that define functions/constants that should be in utils."""
    project_root = Path(__file__).parent.parent
    violations = []
    
    # Paths that are allowed to define these functions
    allowed_paths = {
        project_root / "utils" / "ro_model_builder.py",
        project_root / "utils" / "ro_solver.py",
        project_root / "utils" / "ro_results_extractor.py",
        project_root / "utils" / "ro_initialization.py",
        project_root / "utils" / "constants.py",
        project_root / "utils" / "mcas_builder.py",
    }
    
    # Check Python files
    for py_file in project_root.rglob("*.py"):
        # Skip test files and allowed utils files
        if py_file.parent.name == "tests" or py_file in allowed_paths:
            continue
        
        # Skip test files in root directory
        if py_file.name.startswith("test_"):
            continue
        
        # Skip __pycache__ directories
        if "__pycache__" in str(py_file):
            continue
        
        functions, constants = get_python_functions(py_file)
        
        # Check for violations
        func_violations = functions & UTILS_ONLY_FUNCTIONS
        const_violations = constants & UTILS_ONLY_CONSTANTS
        
        if func_violations or const_violations:
            violations.append({
                "file": str(py_file.relative_to(project_root)),
                "functions": list(func_violations),
                "constants": list(const_violations)
            })
    
    # Check notebooks
    notebooks_dir = project_root / "notebooks"
    if notebooks_dir.exists():
        for nb_file in notebooks_dir.glob("*.ipynb"):
            # Skip checkpoint files
            if ".ipynb_checkpoints" in str(nb_file):
                continue
            
            functions, constants = get_notebook_functions(nb_file)
            
            # Check for violations
            func_violations = functions & UTILS_ONLY_FUNCTIONS
            const_violations = constants & UTILS_ONLY_CONSTANTS
            
            if func_violations or const_violations:
                violations.append({
                    "file": str(nb_file.relative_to(project_root)),
                    "functions": list(func_violations),
                    "constants": list(const_violations)
                })
    
    return violations


class TestNoDuplicates:
    """Test class for duplicate detection."""
    
    def test_no_duplicate_functions(self):
        """Test that no duplicate functions exist outside utils."""
        violations = find_violations()
        
        if violations:
            msg = "Found duplicate function/constant definitions:\n"
            for v in violations:
                msg += f"\n{v['file']}:\n"
                if v['functions']:
                    msg += f"  Functions: {', '.join(v['functions'])}\n"
                if v['constants']:
                    msg += f"  Constants: {', '.join(v['constants'])}\n"
            
            pytest.fail(msg)
    
    def test_utils_imports_present(self):
        """Test that files using RO functions import from utils."""
        project_root = Path(__file__).parent.parent
        missing_imports = []
        
        # Files that should import from utils if they use RO functions
        files_to_check = [
            project_root / "server.py",
        ]
        
        # Check notebooks that should have imports
        notebooks_dir = project_root / "notebooks"
        if notebooks_dir.exists():
            files_to_check.extend([
                notebooks_dir / "ro_simulation_mcas_template.ipynb",
                notebooks_dir / "ro_simulation_mcas_recycle_template.ipynb"
            ])
        
        for file_path in files_to_check:
            if not file_path.exists():
                continue
            
            if file_path.suffix == '.py':
                with open(file_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                
                # Check if file uses RO functions but doesn't import from utils
                if any(func in content for func in ["build_ro_model", "initialize_and_solve", "extract_results"]):
                    if "from utils" not in content and "import utils" not in content:
                        missing_imports.append(str(file_path.relative_to(project_root)))
            
            elif file_path.suffix == '.ipynb':
                with open(file_path, 'r', encoding='utf-8') as f:
                    nb = nbformat.read(f, as_version=4)
                
                # Check if notebook has proper imports
                has_utils_import = False
                uses_ro_functions = False
                
                for cell in nb.cells:
                    if cell.cell_type == 'code':
                        if "from utils" in cell.source or "import utils" in cell.source:
                            has_utils_import = True
                        if any(func in cell.source for func in ["build_ro_model", "initialize_and_solve", "extract_results"]):
                            uses_ro_functions = True
                
                if uses_ro_functions and not has_utils_import:
                    missing_imports.append(str(file_path.relative_to(project_root)))
        
        if missing_imports:
            msg = "Files using RO functions but not importing from utils:\n"
            msg += "\n".join(f"  - {f}" for f in missing_imports)
            pytest.fail(msg)


if __name__ == "__main__":
    # Run as script for quick check
    violations = find_violations()
    if violations:
        print("Duplicate definitions found:")
        for v in violations:
            print(f"\n{v['file']}:")
            if v['functions']:
                print(f"  Functions: {', '.join(v['functions'])}")
            if v['constants']:
                print(f"  Constants: {', '.join(v['constants'])}")
    else:
        print("No duplicate definitions found!")