# RO FBBT Diagnostic Test Guide

This guide explains how to use the diagnostic test scripts to identify and resolve FBBT initialization failures.

## Quick Start

For immediate diagnosis of a specific failure:

```bash
# Test with your failing configuration
python quick_diagnostic_test.py --A_w 1.6e-11 --pressure 30 --tds 1000

# Test with different parameters
python quick_diagnostic_test.py --A_w 2e-11 --pressure 40 --tds 5000 --recovery 0.7
```

## Test Scripts

### 1. Quick Diagnostic Test (`quick_diagnostic_test.py`)

**Purpose**: Quickly diagnose a specific configuration that's failing.

**Features**:
- Calculates expected flux before building model
- Runs pre-FBBT checks
- Provides detailed diagnostics
- Generates specific recommendations
- Creates both log and JSON output

**Usage**:
```bash
python quick_diagnostic_test.py [options]

Options:
  --A_w        Water permeability (m/s/Pa) [default: 1.6e-11]
  --B_s        Salt permeability (m/s) [default: 1e-8]
  --pressure   Feed pressure (bar) [default: 25]
  --tds        Feed TDS (ppm) [default: 1000]
  --recovery   Target recovery [default: 0.5]
  --output     Output file name [optional]
```

**Example Output**:
```
RO INITIALIZATION DIAGNOSTIC TEST
================================================================================
Configuration:
  Membrane A_w: 1.60e-11 m/s/Pa
  Feed pressure: 30 bar
  Expected flux: 0.0450 kg/m²/s
  WaterTAP flux bounds: [0.0001, 0.03] kg/m²/s
  Flux within bounds: NO
  WARNING: Expected flux exceeds bounds!
  Maximum safe pressure: 16.4 bar

RECOMMENDATIONS:
1. Flux exceeds upper bound - pressure too high for membrane permeability
2. Reduce pressure to max 16.4 bar
3. Or use a lower permeability membrane
```

### 2. Comprehensive Test Suite (`test_fbbt_diagnostics.py`)

**Purpose**: Systematically test multiple scenarios to identify failure patterns.

**Features**:
- Tests multiple parameter combinations
- Identifies failure boundaries
- Generates comprehensive reports
- Creates visualizations
- Supports parallel execution

**Usage**:
```bash
# Run basic test suite (quick)
python test_fbbt_diagnostics.py --test-suite basic

# Run full test suite
python test_fbbt_diagnostics.py --test-suite full --parallel

# Run custom scenarios
python test_fbbt_diagnostics.py --scenarios my_tests.json
```

**Test Suites**:
- `basic`: Tests different membrane permeabilities (quick)
- `full`: Complete parameter sweeps (comprehensive)
- `custom`: User-defined scenarios from JSON file

**Output Files**:
- `test_summary.csv`: Summary table of all tests
- `test_report.md`: Detailed analysis and recommendations
- `test_results.json`: Complete test data
- `test_results_visualization.png`: Failure boundary plots

## Interpreting Results

### Common Failure Types

1. **FBBT Infeasibility**
   - **Symptom**: `Detected an infeasible constraint during FBBT`
   - **Cause**: Flux exceeds bounds during interval arithmetic
   - **Fix**: Reduce pressure or use staged initialization

2. **High Flux Violation**
   - **Symptom**: Expected flux > 0.03 kg/m²/s
   - **Cause**: High permeability + high pressure
   - **Fix**: Cap pressure based on flux limit

3. **Initialization Failure**
   - **Symptom**: Various solver errors
   - **Cause**: Poor initial guesses or scaling
   - **Fix**: Use staged initialization

### Reading the Diagnostic Output

1. **Pre-FBBT Check**:
   ```
   PRE-FBBT FLUX BOUNDS CHECK
   Worst-case flux: 0.0350 kg/m²/s
   Max allowed: 0.0250 kg/m²/s
   PASS: False
   ```
   This shows flux will exceed bounds before FBBT runs.

2. **Flux State Logging**:
   ```
   FLUX STATE: Pre-initialization
   Flux value: 0.0280 kg/m²/s
   Bounds: [0.0001, 0.0300] kg/m²/s
   Upper margin: 6.7%
   ```
   Shows how close flux is to bounds.

3. **Recommendations**:
   - Specific pressure limits
   - Alternative membranes
   - Initialization strategies

## Workflow for Debugging

1. **Start with Quick Diagnostic**:
   ```bash
   python quick_diagnostic_test.py --A_w 1.6e-11 --pressure 25
   ```
   
2. **If it fails, check the log**:
   - Look for "FLUX BOUNDS WILL BE VIOLATED"
   - Note the recommended maximum pressure
   - Check the initialization error type

3. **Test the recommended fix**:
   ```bash
   # Test with reduced pressure
   python quick_diagnostic_test.py --A_w 1.6e-11 --pressure 16
   ```

4. **If still failing, run comprehensive tests**:
   ```bash
   python test_fbbt_diagnostics.py --test-suite basic
   ```

5. **Review the test report**:
   - Check `test_report.md` for patterns
   - Look at visualization for failure boundaries
   - Apply recommended strategies

## Custom Test Scenarios

Create a JSON file with custom scenarios:

```json
[
  {
    "name": "my_membrane_test",
    "A_w": 1.5e-11,
    "B_s": 1e-8,
    "feed_pressure": 28,
    "feed_tds": 2000,
    "recovery": 0.6,
    "test_type": "custom"
  }
]
```

Run with:
```bash
python test_fbbt_diagnostics.py --scenarios my_tests.json
```

## Troubleshooting

### Issue: All tests pass but actual simulation fails
- Check if using same property package
- Verify multi-stage vs single-stage configuration
- Ensure membrane properties match

### Issue: Diagnostic suggests pressure but still fails
- Try even lower pressure (use 80% of recommended)
- Enable staged initialization
- Check for other constraints (e.g., high recovery)

### Issue: Tests hang or crash
- Reduce parallel workers: `--workers 2`
- Run sequentially: remove `--parallel`
- Check system memory

## Best Practices

1. **Always start with quick diagnostic** for immediate feedback
2. **Use recommended pressure** as maximum, not target
3. **Run comprehensive tests** when changing membrane types
4. **Save test results** for future reference
5. **Share logs** when reporting issues

## Next Steps

After identifying the issue:

1. Update your configuration with recommended values
2. Use appropriate initialization strategy (elegant vs staged)
3. Consider membrane alternatives if needed
4. Implement flux validation in your workflow