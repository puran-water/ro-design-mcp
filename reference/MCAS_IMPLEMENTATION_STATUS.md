# MCAS Implementation Status

## Date: 2025-07-17

## Summary
Added MCAS (Multi-Component Aqueous Solution) support to `direct_simulate_ro.py` but encountered fundamental structural issues that prevent successful simulation using the current approach.

## Implementation Details

### Completed
1. **Added MCAS imports and dependencies**:
   - Imported MCASParameterBlock from WaterTAP
   - Imported mcas_builder utilities
   - Added ion composition parameter support

2. **Created `build_ro_model_mcas()` function**:
   - Builds RO model with MCAS property package
   - Handles ion composition parameter
   - Sets appropriate B_comp values for different ions
   - Handles flexible A_comp indexing for MCAS

3. **Created `initialize_and_solve_mcas()` function**:
   - Follows successful simple package initialization pattern
   - Applies flux/recovery/permeability-aware pressure calculations
   - Handles sequential initialization with reduced recovery
   - Implements two-phase solving for low permeability membranes

4. **Updated `run_direct_simulation()` to route to MCAS**:
   - Detects when ion composition is provided
   - Routes to MCAS model building and solving
   - Handles flexible component indexing

### Issues Encountered

1. **Degrees of Freedom Problem**:
   - Model has -10 DOF after adding recovery constraints (over-constrained)
   - Initial model has only 2 DOF compared to ~10-12 for seawater package
   - MCAS creates many internal equality constraints

2. **Component Indexing**:
   - A_comp indexing differs between MCAS and seawater packages
   - Fixed with flexible try/except blocks for different index structures
   - B_comp requires fixing for each individual ion species

3. **Property Package Complexity**:
   - MCAS creates many more variables and constraints than seawater package
   - Activity coefficients, ion speciation, interface properties all add constraints
   - Concentration polarization modeled differently with interface state blocks

## Root Causes

1. **Structural Differences**: The RO0D model behaves fundamentally differently with MCAS vs seawater property packages
2. **Over-specification**: Fixing B_comp for each ion species plus recovery constraints over-constrains the model
3. **Missing DOF**: MCAS may require additional specifications (e.g., pH, activity coefficients) not needed for seawater

## Technical Details

- MCAS A_comp indexing: `ro.A_comp[time]` (single index)
- Seawater A_comp indexing: `ro.A_comp[time, component]`
- MCAS B_comp: Individual values for each solute species
- Initial DOF with MCAS: 2 (vs 10-12 for seawater)
- DOF after recovery constraints: -10 (highly over-constrained)

## Recommendation

Given the fundamental structural differences, recommend:

1. **Prioritize simple property package** for MCP server functionality
2. **Use notebook-based MCAS simulations** for ion-specific analysis when needed
3. **Future work**: Study WaterTAP MCAS examples to understand proper DOF management
4. **Consider alternative approaches**:
   - Use fewer fixed variables (e.g., don't fix all B_comp values)
   - Implement pH and activity coefficient specifications
   - Use MCAS-specific initialization procedures

## Testing Results

```
Test Date: 2025-07-17
Feed: 150 m³/h, 2000 ppm TDS (Na+: 786 mg/L, Cl-: 1214 mg/L)

Brackish (BW30-400): FAILED - Solver: other (Too few degrees of freedom)
ECO PRO-400: FAILED - Solver: other (Too few degrees of freedom)
```

## Next Steps

1. **Immediate**: Focus on MCP server with simple property package
2. **Remove print statements** that contaminate STDIO
3. **Configure logging** to use stderr exclusively  
4. **Force MCP** to use direct simulation route
5. **Test MCP** with simple property package workflow
6. **Future**: Research proper MCAS initialization from WaterTAP examples