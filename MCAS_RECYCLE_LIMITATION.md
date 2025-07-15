# MCAS Template Recycle Limitation

## Issue Summary
The MCAS (Multi-Component Aqueous Solution) simulation template does not currently support recycle streams. When a configuration includes recycle and MCAS ion composition is specified, the simulation will:

1. Use the MCAS template (for ion-specific modeling)
2. Ignore the recycle configuration
3. Produce incorrect recovery results

## Root Cause
- The configuration tool calculates recoveries based on the effective feed flow (including recycle)
- The MCAS template uses the effective feed flow but doesn't implement the recycle loop
- This causes the simulation to have higher feed flow without the corresponding recycle stream

## Example
Configuration with recycle:
- Raw feed: 150 m³/h
- Recycle: 2.68 m³/h (1.76% ratio)
- Effective feed: 152.68 m³/h
- Target recovery: 75% (based on raw feed)

MCAS simulation result:
- Uses 152.68 m³/h as feed (correct)
- No recycle loop implemented (incorrect)
- Achieves 77.5% recovery instead of 75%

## Impact on Stage Recoveries
The stage-wise recovery constraints are correctly applied, but they're applied to the wrong feed flows:
- Stage 1 should see 152.68 m³/h (with recycle)
- Stage 2 should see the Stage 1 concentrate
- Without the recycle loop, the mass balance is incorrect

## Temporary Solution
When using MCAS with recycle configurations:
1. The system will warn about this limitation
2. Results will show higher-than-expected recovery
3. Stage recoveries won't match configuration targets

## Permanent Solution Options
1. **Create MCAS Recycle Template**: Develop `ro_simulation_mcas_recycle_template.ipynb` that combines MCAS property package with proper recycle modeling using Mixer/Separator units
2. **Enhance Existing Template**: Add recycle support to the current MCAS template with conditional logic
3. **Force Non-MCAS**: When recycle is present, always use the recycle template even if ion composition is specified

## Recommendation
For accurate simulation of systems with recycle, either:
- Use the standard recycle template (without ion-specific modeling)
- Wait for MCAS recycle template development
- Manually adjust the configuration to account for the missing recycle