"""
Tests for artifact management utilities.
"""

import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import pytest

from utils.artifacts import (
    _canonicalize_floats,
    build_manifest,
    canonical_dumps,
    capture_context,
    check_existing_results,
    checksum_file,
    deterministic_run_id,
    ensure_dir,
    prepare_run_dir,
    read_json,
    sha256_hexdigest,
    write_artifacts,
    write_json_atomic,
)


class TestCanonicalization:
    """Test canonicalization of data for deterministic hashing."""
    
    def test_canonicalize_floats(self):
        """Test float canonicalization."""
        # Test single float
        assert _canonicalize_floats(3.14159265359) == 3.14159265359
        
        # Test dict with floats
        data = {"a": 1.23456789012345, "b": 9.87654321098765}
        result = _canonicalize_floats(data, precision=6)
        assert isinstance(result["a"], float)
        assert isinstance(result["b"], float)
        
        # Test nested structures
        nested = {"outer": {"inner": [1.111, 2.222, 3.333]}}
        result = _canonicalize_floats(nested)
        assert isinstance(result["outer"]["inner"][0], float)
    
    def test_canonical_dumps(self):
        """Test canonical JSON serialization."""
        data1 = {"b": 2, "a": 1, "c": 3.14159}
        data2 = {"a": 1, "b": 2, "c": 3.14159}
        
        # Should produce identical JSON strings
        assert canonical_dumps(data1) == canonical_dumps(data2)
        
        # Should be sorted
        json_str = canonical_dumps(data1)
        assert json_str.startswith('{"a":1')


class TestHashing:
    """Test hashing functions."""
    
    def test_sha256_hexdigest(self):
        """Test SHA-256 hash calculation."""
        # Known hash for "hello world"
        text = "hello world"
        expected = "b94d27b9934d3e08a52e52d7da7dabfac484efe37a5380ee9088f7ace2efcde9"
        assert sha256_hexdigest(text) == expected
    
    def test_deterministic_run_id(self):
        """Test deterministic run ID generation."""
        # Same inputs should produce same ID
        input1 = {"feed_flow": 100, "recovery": 0.75}
        id1 = deterministic_run_id("test_tool", input1)
        id2 = deterministic_run_id("test_tool", input1)
        assert id1 == id2
        
        # Different inputs should produce different IDs
        input2 = {"feed_flow": 200, "recovery": 0.75}
        id3 = deterministic_run_id("test_tool", input2)
        assert id1 != id3
        
        # Different tool names should produce different IDs
        id4 = deterministic_run_id("other_tool", input1)
        assert id1 != id4
        
        # ID should be 16 characters (truncated SHA-256)
        assert len(id1) == 16


class TestFileOperations:
    """Test file operation utilities."""
    
    def test_ensure_dir(self):
        """Test directory creation."""
        with tempfile.TemporaryDirectory() as tmpdir:
            test_path = Path(tmpdir) / "nested" / "dirs" / "test"
            
            # Directory should not exist initially
            assert not test_path.exists()
            
            # Create it
            ensure_dir(test_path)
            assert test_path.exists()
            assert test_path.is_dir()
            
            # Should be idempotent
            ensure_dir(test_path)
            assert test_path.exists()
    
    def test_write_read_json(self):
        """Test JSON write and read operations."""
        with tempfile.TemporaryDirectory() as tmpdir:
            test_file = Path(tmpdir) / "test.json"
            data = {"key": "value", "number": 42, "nested": {"a": 1}}
            
            # Write JSON
            write_json_atomic(test_file, data)
            assert test_file.exists()
            
            # Read it back
            loaded = read_json(test_file)
            assert loaded == data
            
            # Check atomic write (no .tmp file should remain)
            assert not test_file.with_suffix('.tmp').exists()
    
    def test_checksum_file(self):
        """Test file checksum calculation."""
        with tempfile.NamedTemporaryFile(mode='w', delete=False) as f:
            f.write("test content")
            f.flush()
            
            try:
                sha256, size = checksum_file(Path(f.name))
                
                # Should return valid SHA-256 (64 hex chars)
                assert len(sha256) == 64
                assert all(c in '0123456789abcdef' for c in sha256)
                
                # Should return correct size
                assert size == 12  # "test content" is 12 bytes
            finally:
                os.unlink(f.name)


class TestContext:
    """Test context capture functionality."""
    
    def test_capture_context(self):
        """Test execution context capture."""
        context = capture_context("test_tool", "test_run_123")
        
        # Check required fields
        assert context.schema_version
        assert context.created_at
        assert isinstance(context.created_at, datetime)
        assert context.run_id == "test_run_123"
        assert context.tool_name == "test_tool"
        assert context.python_version
        assert context.platform
        assert context.os
        
        # Check git info structure
        assert isinstance(context.git, dict)
        assert 'commit' in context.git
        assert 'branch' in context.git
        assert 'dirty' in context.git
        
        # Check packages structure
        assert isinstance(context.packages, dict)
        assert 'pyomo' in context.packages
        assert 'watertap' in context.packages


class TestArtifactManagement:
    """Test artifact management functions."""
    
    def test_prepare_run_dir(self):
        """Test run directory preparation."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Temporarily override artifacts root
            original_root = os.environ.get('RO_ARTIFACTS_ROOT')
            os.environ['RO_ARTIFACTS_ROOT'] = tmpdir
            
            try:
                run_dir = prepare_run_dir("test_run_456")
                assert run_dir.exists()
                assert run_dir.is_dir()
                assert run_dir.name == "test_run_456"
                assert str(tmpdir) in str(run_dir)
            finally:
                if original_root:
                    os.environ['RO_ARTIFACTS_ROOT'] = original_root
                else:
                    del os.environ['RO_ARTIFACTS_ROOT']
    
    def test_build_manifest(self):
        """Test manifest building."""
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_dir = Path(tmpdir) / "test_run"
            artifact_dir.mkdir()
            
            # Create some test files
            (artifact_dir / "input.json").write_text('{"test": 1}')
            (artifact_dir / "results.json").write_text('{"status": "success"}')
            
            # Build manifest
            manifest = build_manifest("test_run", "test_tool", artifact_dir)
            
            # Check manifest structure
            assert manifest.schema_version
            assert manifest.run_id == "test_run"
            assert manifest.tool_name == "test_tool"
            assert isinstance(manifest.created_at, datetime)
            assert len(manifest.files) == 2
            assert manifest.total_size_bytes > 0
            
            # Check file entries
            filenames = [f.filename for f in manifest.files]
            assert "input.json" in filenames
            assert "results.json" in filenames
    
    def test_check_existing_results(self):
        """Test checking for existing results."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Override artifacts root
            original_root = os.environ.get('RO_ARTIFACTS_ROOT')
            os.environ['RO_ARTIFACTS_ROOT'] = tmpdir
            
            try:
                # Initially no results
                assert check_existing_results("nonexistent") is None
                
                # Create a result file
                run_dir = Path(tmpdir) / "existing_run"
                run_dir.mkdir()
                results = {"status": "success", "data": [1, 2, 3]}
                (run_dir / "results.json").write_text(json.dumps(results))
                
                # Should find results
                found = check_existing_results("existing_run")
                assert found == results
            finally:
                if original_root:
                    os.environ['RO_ARTIFACTS_ROOT'] = original_root
                else:
                    del os.environ['RO_ARTIFACTS_ROOT']
    
    def test_write_artifacts(self):
        """Test complete artifact writing workflow."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Override artifacts root
            original_root = os.environ.get('RO_ARTIFACTS_ROOT')
            os.environ['RO_ARTIFACTS_ROOT'] = tmpdir
            
            try:
                # Prepare test data
                input_data = {"param1": "value1", "param2": 42}
                results_data = {"status": "success", "result": 123}
                context = capture_context("test_tool", "test_run_789")
                logs = "This is a test log\nWith multiple lines"
                warnings = ["Warning 1", "Warning 2"]
                
                # Write artifacts
                artifact_dir = write_artifacts(
                    run_id="test_run_789",
                    tool_name="test_tool",
                    input_data=input_data,
                    results_data=results_data,
                    context=context,
                    logs=logs,
                    warnings=warnings
                )
                
                # Check that all expected files exist
                assert (artifact_dir / "input.json").exists()
                assert (artifact_dir / "results.json").exists()
                assert (artifact_dir / "context.json").exists()
                assert (artifact_dir / "logs.txt").exists()
                assert (artifact_dir / "warnings.json").exists()
                assert (artifact_dir / "index.json").exists()
                
                # Verify content
                assert read_json(artifact_dir / "input.json") == input_data
                assert read_json(artifact_dir / "results.json") == results_data
                assert (artifact_dir / "logs.txt").read_text() == logs
                assert read_json(artifact_dir / "warnings.json") == warnings
                
                # Check manifest
                manifest = read_json(artifact_dir / "index.json")
                assert manifest["run_id"] == "test_run_789"
                assert manifest["tool_name"] == "test_tool"
                assert len(manifest["files"]) == 5  # All files except index.json
                
            finally:
                if original_root:
                    os.environ['RO_ARTIFACTS_ROOT'] = original_root
                else:
                    del os.environ['RO_ARTIFACTS_ROOT']


if __name__ == "__main__":
    pytest.main([__file__, "-v"])