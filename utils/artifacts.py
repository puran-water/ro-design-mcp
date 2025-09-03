"""
Artifact management utilities for RO Design MCP Server.

Handles deterministic run ID generation, artifact writing, and context capture.
"""

import hashlib
import json
import os
import platform
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import logging

try:
    from importlib import metadata as importlib_metadata
except ImportError:
    import importlib_metadata  # Python < 3.8

from .schemas import (
    ArtifactFile,
    ArtifactManifest,
    ROSimulationInput,
    ROSimulationResults,
    RunContext,
    SCHEMA_VERSION_CONTEXT,
    SCHEMA_VERSION_INPUT,
    SCHEMA_VERSION_MANIFEST,
    SCHEMA_VERSION_RESULTS,
)
from .logging_config import get_configured_logger

logger = get_configured_logger(__name__)


def _canonicalize_floats(obj: Any, precision: int = 12) -> Any:
    """
    Canonicalize floating point numbers for stable hashing.
    
    Args:
        obj: Object to canonicalize
        precision: Decimal precision for rounding
        
    Returns:
        Canonicalized object
    """
    if isinstance(obj, float):
        # Round to specified precision for stability
        return float(f"{obj:.{precision}g}")
    if isinstance(obj, dict):
        return {k: _canonicalize_floats(v, precision) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_canonicalize_floats(v, precision) for v in obj]
    if isinstance(obj, tuple):
        return tuple(_canonicalize_floats(v, precision) for v in obj)
    return obj


def canonical_dumps(data: Dict[str, Any]) -> str:
    """
    Create canonical JSON string for deterministic hashing.
    
    Args:
        data: Dictionary to serialize
        
    Returns:
        Canonical JSON string with sorted keys
    """
    canonical = _canonicalize_floats(data)
    return json.dumps(
        canonical, 
        sort_keys=True, 
        separators=(",", ":"), 
        ensure_ascii=False
    )


def sha256_hexdigest(text: str) -> str:
    """
    Calculate SHA-256 hash of text.
    
    Args:
        text: Text to hash
        
    Returns:
        Hexadecimal hash string
    """
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def deterministic_run_id(
    tool_name: str,
    input_payload: Dict[str, Any],
    schema_version: str = SCHEMA_VERSION_INPUT,
    code_version: Optional[str] = None,
) -> str:
    """
    Generate deterministic run ID from inputs.
    
    Args:
        tool_name: Name of the tool being executed
        input_payload: Input parameters
        schema_version: Schema version of inputs
        code_version: Optional code version/git SHA
        
    Returns:
        Deterministic run ID (SHA-256 hex string)
    """
    # Build hashable content
    content = {
        "tool": tool_name,
        "schema_version": schema_version,
        "input": input_payload,
    }
    
    if code_version:
        content["code_version"] = code_version
    
    # Generate hash
    canonical_json = canonical_dumps(content)
    run_id = sha256_hexdigest(canonical_json)[:16]  # Use first 16 chars for brevity
    
    logger.debug(f"Generated run_id: {run_id} for tool: {tool_name}")
    return run_id


def ensure_dir(path: Path) -> None:
    """
    Ensure directory exists, creating if necessary.
    
    Args:
        path: Directory path
    """
    path.mkdir(parents=True, exist_ok=True)


def write_json_atomic(path: Path, data: Dict[str, Any]) -> None:
    """
    Write JSON atomically to avoid partial writes.
    
    Args:
        path: File path
        data: Data to write
    """
    tmp_path = path.with_suffix('.tmp')
    
    with open(tmp_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, sort_keys=True, ensure_ascii=False)
        f.write('\n')  # Add newline at end
    
    # Atomic move
    tmp_path.replace(path)
    logger.debug(f"Wrote JSON to {path}")


def read_json(path: Path) -> Dict[str, Any]:
    """
    Read JSON file.
    
    Args:
        path: File path
        
    Returns:
        Parsed JSON data
    """
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)


def _get_package_version(package: str) -> Optional[str]:
    """
    Get version of installed package.
    
    Args:
        package: Package name
        
    Returns:
        Version string or None if not found
    """
    try:
        return importlib_metadata.version(package)
    except Exception:
        return None


def _get_git_info(cwd: Optional[Path] = None) -> Dict[str, Optional[str]]:
    """
    Get git repository information.
    
    DISABLED: Git commands cause significant delays on WSL/NTFS filesystems
    and are not essential for RO simulations. Returns empty placeholders.
    
    Args:
        cwd: Working directory (default: current)
        
    Returns:
        Dictionary with git info (all None values to avoid delays)
    """
    # Git commands disabled to avoid 90+ second delays on WSL
    return {
        'commit': None,
        'commit_short': None,
        'branch': None,
        'dirty': None,
        'root': None,
    }


def capture_context(
    tool_name: str,
    run_id: str,
    input_schema_version: str = SCHEMA_VERSION_INPUT,
    results_schema_version: str = SCHEMA_VERSION_RESULTS,
) -> RunContext:
    """
    Capture execution context for reproducibility.
    
    Args:
        tool_name: Name of the tool
        run_id: Run identifier
        input_schema_version: Input schema version
        results_schema_version: Results schema version
        
    Returns:
        RunContext object with full environment info
    """
    # Get key environment variables
    env_vars = {}
    for key in ['PYTHONPATH', 'PATH', 'LOCALAPPDATA', 'PROJECT_ROOT']:
        if key in os.environ:
            env_vars[key] = os.environ[key]
    
    context = RunContext(
        schema_version=SCHEMA_VERSION_CONTEXT,
        created_at=datetime.now(timezone.utc),
        run_id=run_id,
        tool_name=tool_name,
        python_version=sys.version.split()[0],
        platform=platform.platform(),
        os=platform.system(),
        git=_get_git_info(),
        packages={
            'pyomo': _get_package_version('pyomo'),
            'watertap': _get_package_version('watertap'),
            'idaes-pse': _get_package_version('idaes-pse'),
            'pydantic': _get_package_version('pydantic'),
            'numpy': _get_package_version('numpy'),
            'pandas': _get_package_version('pandas'),
        },
        environment_variables=env_vars,
    )
    
    return context


def checksum_file(path: Path) -> Tuple[str, int]:
    """
    Calculate SHA-256 checksum and size of file.
    
    Args:
        path: File path
        
    Returns:
        Tuple of (sha256_hex, size_in_bytes)
    """
    sha256 = hashlib.sha256()
    size = 0
    
    with open(path, 'rb') as f:
        while chunk := f.read(8192):
            sha256.update(chunk)
            size += len(chunk)
    
    return sha256.hexdigest(), size


def build_manifest(
    run_id: str,
    tool_name: str,
    artifact_dir: Path,
) -> ArtifactManifest:
    """
    Build manifest of all artifact files.
    
    Args:
        run_id: Run identifier
        tool_name: Tool name
        artifact_dir: Directory containing artifacts
        
    Returns:
        ArtifactManifest object
    """
    files = []
    total_size = 0
    
    # List all files in artifact directory
    for file_path in sorted(artifact_dir.glob('*')):
        if file_path.is_file() and file_path.name != 'index.json':
            sha256, size = checksum_file(file_path)
            files.append(ArtifactFile(
                filename=file_path.name,
                path=str(file_path.relative_to(artifact_dir.parent)),
                sha256=sha256,
                size_bytes=size,
                created_at=datetime.fromtimestamp(
                    file_path.stat().st_mtime, 
                    tz=timezone.utc
                )
            ))
            total_size += size
    
    manifest = ArtifactManifest(
        schema_version=SCHEMA_VERSION_MANIFEST,
        run_id=run_id,
        tool_name=tool_name,
        created_at=datetime.now(timezone.utc),
        input_schema_version=SCHEMA_VERSION_INPUT,
        results_schema_version=SCHEMA_VERSION_RESULTS,
        context_schema_version=SCHEMA_VERSION_CONTEXT,
        files=files,
        total_size_bytes=total_size,
    )
    
    return manifest


def artifacts_root() -> Path:
    """
    Get root directory for artifacts.
    
    Returns:
        Path to artifacts directory
    """
    # Use environment variable or default to ./artifacts
    root = os.environ.get('RO_ARTIFACTS_ROOT', 'artifacts')
    return Path(root)


def prepare_run_dir(run_id: str) -> Path:
    """
    Prepare directory for run artifacts.
    
    Args:
        run_id: Run identifier
        
    Returns:
        Path to run directory
    """
    run_dir = artifacts_root() / run_id
    ensure_dir(run_dir)
    logger.info(f"Prepared artifact directory: {run_dir}")
    return run_dir


def write_artifacts(
    run_id: str,
    tool_name: str,
    input_data: Dict[str, Any],
    results_data: Dict[str, Any],
    context: RunContext,
    logs: Optional[str] = None,
    warnings: Optional[List[str]] = None,
) -> Path:
    """
    Write all artifacts for a run.
    
    Args:
        run_id: Run identifier
        tool_name: Tool name
        input_data: Input parameters
        results_data: Results data
        context: Execution context
        logs: Optional log text
        warnings: Optional warnings list
        
    Returns:
        Path to artifact directory
    """
    # Prepare directory
    artifact_dir = prepare_run_dir(run_id)
    
    # Write input.json
    input_path = artifact_dir / 'input.json'
    write_json_atomic(input_path, input_data)
    
    # Write results.json
    results_path = artifact_dir / 'results.json'
    write_json_atomic(results_path, results_data)
    
    # Write context.json
    context_path = artifact_dir / 'context.json'
    write_json_atomic(context_path, context.model_dump(mode='json'))
    
    # Write logs if provided
    if logs:
        logs_path = artifact_dir / 'logs.txt'
        with open(logs_path, 'w', encoding='utf-8') as f:
            f.write(logs)
        logger.debug(f"Wrote logs to {logs_path}")
    
    # Write warnings if provided
    if warnings:
        warnings_path = artifact_dir / 'warnings.json'
        write_json_atomic(warnings_path, warnings)
    
    # Build and write manifest
    manifest = build_manifest(run_id, tool_name, artifact_dir)
    manifest_path = artifact_dir / 'index.json'
    write_json_atomic(manifest_path, manifest.model_dump(mode='json'))
    
    logger.info(f"Wrote {len(manifest.files)} artifacts to {artifact_dir}")
    return artifact_dir


def check_existing_results(run_id: str) -> Optional[Dict[str, Any]]:
    """
    Check if results already exist for a run ID.
    
    Args:
        run_id: Run identifier
        
    Returns:
        Results data if exists, None otherwise
    """
    results_path = artifacts_root() / run_id / 'results.json'
    
    if results_path.exists():
        logger.info(f"Found existing results for run_id: {run_id}")
        return read_json(results_path)
    
    return None


def cleanup_old_artifacts(days: int = 30) -> int:
    """
    Clean up artifact directories older than specified days.
    
    Args:
        days: Number of days to keep artifacts
        
    Returns:
        Number of directories deleted
    """
    import time
    
    root = artifacts_root()
    if not root.exists():
        return 0
    
    cutoff_time = time.time() - (days * 24 * 60 * 60)
    deleted = 0
    
    for run_dir in root.iterdir():
        if run_dir.is_dir():
            # Check modification time of directory
            if run_dir.stat().st_mtime < cutoff_time:
                logger.info(f"Deleting old artifacts: {run_dir}")
                shutil.rmtree(run_dir)
                deleted += 1
    
    logger.info(f"Cleaned up {deleted} old artifact directories")
    return deleted
