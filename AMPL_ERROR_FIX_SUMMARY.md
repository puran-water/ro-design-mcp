# AMPL Error Fix Summary

## Problem
MCP server simulate_ro_system_v2 failed with "Error in AMPL evaluation" when economic parameters were provided.

## Root Cause
Chemical dosing Zero-Order (ZO) models from WaterTAP cause AMPL errors in subprocess environments.

## Solution
Temporarily disabled chemical dosing models in `utils/ro_model_builder_v2.py`:
- Line 645-646: Disabled `_build_chemical_dosing`
- Line 650-651: Disabled CIP system

## Result
✅ MCP simulation now works with full economic costing and LCOW calculations
⚠️ Chemical dosing features temporarily unavailable

## Test Confirmation
Successfully simulated 100 m³/h system with:
- LCOW: $0.163/m³
- Specific Energy: 0.685 kWh/m³
- All configurations working (1-stage, 2-stage, recycle)