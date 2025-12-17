# RO Design MCP Server - Feature Roadmap

**Version**: 1.0
**Date**: 2025-09-26
**Author**: Claude Code + User + Codex Review

---

## Executive Summary

This roadmap outlines the implementation of four major enhancements to the RO Design MCP Server:

1. **4-Inch Element Support** - Enable small system designs (1-2 weeks)
2. **Second Pass RO** - Ultra-pure water production (4-6 weeks)
3. **Permeate Backpressure Optimization** - Cost-optimized multi-stage hydraulics (1-2 weeks)
4. **Brine Concentration RO** - Zero-liquid discharge capability (6-8 weeks)

**Total Timeline**: 12-18 weeks
**Key Benefits**: Expand addressable applications, reduce system costs, enable ZLD designs

---

## Configuration Targets Summary

| RO Train Type | Element Size | Flux Targets (LMH) | Min Conc Flow (m³/h) | Max Stages | Notes |
|---------------|--------------|---------------------|----------------------|------------|-------|
| **Primary (Current)** | 8-inch | [18, 15, 12] | [3.5, 3.8, 4.0] | 3 | Existing baseline |
| **Primary** | 4-inch | [18, 15, 12] | [1.0, 1.1, 1.2] | 3 | Phase 1 |
| **Second Pass** | 8-inch | [26, 24, 22] | [2.8, 3.0, 3.2] | 3 | Phase 2 |
| **Second Pass** | 4-inch | [26, 24, 22] | [0.8, 0.9, 1.0] | 3 | Phase 2 |
| **Brine Concentration** | 8-inch | [9, 6] | [4.2, 4.4] | 2 | Phase 3 |

**Key Observations**:
- Second pass flux is **44% higher** than primary (26 vs 18 LMH Stage 1) due to low osmotic pressure
- Brine concentration flux is **50% lower** than primary (9 vs 18 LMH Stage 1) due to extreme TDS
- 4-inch concentrate flows are ~71% lower than 8-inch equivalents
- Brine concentration limited to 2 stages (use reject recycle for high recovery)

---

## Phase 1: 4-Inch Element Support

**Timeline**: 1-2 weeks
**Complexity**: LOW
**Prerequisites**: None

### Objectives

Enable design of small RO systems (<50 m³/h) using 4-inch membrane elements without power-intensive reject recycle.

### Configuration Targets

- **Flux targets**: [18, 15, 12] LMH (same as 8-inch)
- **Min concentrate flow per vessel**: [1.0, 1.1, 1.2] m³/h (71% reduction vs 8-inch)
- **Elements per vessel**: 4-6 (vs 7 for 8-inch)
- **Element types**: 4040 (~7.6-7.9 m² active area), 4021 (~2.6 m² active area)

### Implementation Tasks

#### 1.1 Membrane Catalog Extensions
**File**: `config/membrane_catalog.yaml`

Add 4-inch membrane entries with complete metadata:
```yaml
physical:
  element_type: '4040'  # or '4021'
  active_area_m2: 7.6
  diameter_mm: 100
  length_mm: 1016
  pressure_class: 'standard'
  flux_band:
    min_lmh: 12
    max_lmh: 20
    recommended_lmh: 16
  spacer_geometry:
    channel_height_mm: 0.79
    pressure_drop_coefficient: 1.2e10
```

**User Action**: Populate FilmTec 4-inch membrane data from manufacturer specifications.

#### 1.2 Configuration Constants
**File**: `utils/constants.py`

Add element-size-specific defaults:
```python
# 4-inch element defaults
FLUX_TARGETS_4INCH_LMH = [18, 15, 12]
MIN_CONCENTRATE_FLOW_4INCH_M3H = [1.0, 1.1, 1.2]
ELEMENTS_PER_VESSEL_4INCH = 4  # Can be 4-6 depending on vessel length
```

#### 1.3 Vessel Sizing Logic
**File**: `utils/optimize_ro.py`

Modify `optimize_vessel_array_configuration()`:
- Detect element size from membrane catalog (`element_type` field)
- Adjust `elements_per_vessel` based on element type:
  - 8040: 7 elements
  - 4040: 4-6 elements (typically 6 for 40-inch vessels)
  - 4021: 3-4 elements
- Select appropriate flux targets and concentrate flow constraints
- Update vessel area calculation: `vessel_area = element_area_m2 * elements_per_vessel`

#### 1.4 Membrane Properties Handler
**File**: `utils/membrane_properties_handler.py`

Add element size detection:
```python
def get_element_size_from_catalog(membrane_model):
    """
    Determine element size (4-inch vs 8-inch) from catalog.
    Returns: '4040', '4021', '8040', etc.
    """
    catalog_entry = get_membrane_from_catalog(membrane_model)
    return catalog_entry.get('physical', {}).get('element_type', '8040')
```

### Testing & Validation

**Test Cases**:
1. Small brackish system: 15 m³/h feed, 75% recovery, 1-stage with 6×4040 vessels
2. Pilot seawater: 5 m³/h feed, 40% recovery, 2-stage with 3×4040 + 2×4040
3. Compare against FilmTec WAVE projections for known 4-inch designs

**Success Criteria**:
- [ ] All 4-inch FilmTec membranes added to catalog with complete metadata
- [ ] Configuration tool auto-detects element size from catalog
- [ ] Vessel sizing correctly allocates 4-6 elements for 4-inch
- [ ] Concentrate flow constraints properly applied (1.0-1.2 m³/h range)
- [ ] Regression test passes for known 4-inch pilot system

### Files Modified
- `config/membrane_catalog.yaml` - Add 4-inch membranes
- `utils/constants.py` - Add 4-inch defaults
- `utils/optimize_ro.py` - Element-size-aware vessel sizing
- `utils/membrane_properties_handler.py` - Element size detection

---

## Phase 2: Second Pass RO

**Timeline**: 4-6 weeks
**Complexity**: MEDIUM-HIGH
**Prerequisites**: Phase 1 complete (recommended but not required)

### Objectives

Enable design of two-pass RO systems for ultra-pure water production (boilers, semiconductors, pharmaceuticals). Primary RO permeate is fed to a second RO train, with second pass concentrate recycled to primary feed.

### Configuration Targets

#### 8-inch elements:
- **Flux targets**: [26, 24, 22] LMH (44% higher than primary)
- **Min concentrate flow**: [2.8, 3.0, 3.2] m³/h (20% lower than primary)

#### 4-inch elements:
- **Flux targets**: [26, 24, 22] LMH (same as 8-inch)
- **Min concentrate flow**: [0.8, 0.9, 1.0] m³/h (71% reduction vs 8-inch)

### Operating Conditions

- **Feed TDS**: 200-500 ppm (from primary permeate)
- **Recovery**: 85-95% (higher than primary due to low fouling potential)
- **Pressure**: 8-15 bar (much lower than primary)
- **Product TDS target**: <30 ppm (ultra-pure water)
- **Membrane selection**: BW30_PRO_400, BW30XFRLE_400 (high flux, low fouling)
- **Chemical addition**: NaOH for inter-pass boron removal (optional)

### Architecture Overview

**Multi-Train System**:
```
Primary RO:  Feed → [Stage 1 → Stage 2 → Stage 3] → Permeate (to Second Pass)
                                                   → Concentrate (disposal)

Second Pass: Permeate from Primary → [Stage 1 → Stage 2] → Final Product
                                                         → Reject (to Primary Feed)

Recycle Loop: Second Pass Reject → Primary Feed (iterative mass balance)
```

**Key Challenge**: Iterative mass balance convergence
- Second pass reject blends with primary feed, changing primary feed composition
- Primary permeate quality changes, affecting second pass performance
- Requires fixed-point iteration with relaxation

### Implementation Tasks

#### 2.1 Multi-Train Coordinator
**New File**: `utils/multi_train_coordinator.py`

Create DAG-based orchestrator inspired by WaterTAP's `oaro_multi.py`:

```python
class StreamPort:
    """
    Stream properties: flow, TDS, ion composition, temperature, pressure.
    Represents a connection point between trains.
    """
    def __init__(self):
        self.flow_m3h = 0.0
        self.tds_ppm = 0.0
        self.ion_composition = {}
        self.temperature_c = 25.0
        self.feed_pressure_bar = 0.0
        self.permeate_pressure_bar = 0.0  # For backpressure optimization

class ROTrain:
    """
    Represents a single RO train with typed ports.
    Mirrors WaterTAP's staged-flow patterns.
    """
    def __init__(self, train_id, train_type, configuration):
        self.train_id = train_id
        self.train_type = train_type  # 'primary', 'second_pass', 'brine_concentration'
        self.configuration = configuration  # From optimize_ro_configuration()
        self.ports = {
            'feed': StreamPort(),
            'permeate': StreamPort(),
            'brine': StreamPort()
        }

class MultiTrainSystem:
    """
    Lightweight DAG for train connectivity and mass balance.
    Uses state-propagation order like WaterTAP's flowsheets.
    """
    def __init__(self):
        self.trains = {}  # {train_id: ROTrain}
        self.connections = []  # List of (source_port, dest_port) tuples

    def add_train(self, train: ROTrain):
        """Add a train to the system."""
        self.trains[train.train_id] = train

    def connect(self, source_train_id, source_port_name, dest_train_id, dest_port_name):
        """
        Add typed connection between trains.

        Example:
            connect('second_pass', 'brine', 'primary', 'feed')
        """
        self.connections.append({
            'source': (source_train_id, source_port_name),
            'dest': (dest_train_id, dest_port_name)
        })

    def solve_mass_balance(self, max_iterations=20, relaxation_factor=0.5):
        """
        Two-tier solver (Codex recommendation):
        - Inner loop: Train hydraulics/PHREEQC equilibrium
        - Outer loop: System mass balance with under-relaxation

        Relaxation: x_new = α·x_calc + (1-α)·x_old
        Uses Anderson acceleration if residuals stagnate.
        """
        pass
```

#### 2.2 Enhanced Iteration Strategy

Implement relaxed fixed-point iteration to handle sharp osmotic pressure gradients:

```python
def solve_with_relaxation(self, under_relax=0.5, convergence_tol=0.01):
    """
    Fixed-point iteration with under-relaxation to avoid divergence.

    Algorithm:
    1. Initialize: Guess second pass reject composition (assume ~300 ppm TDS)
    2. Solve primary train with mixed feed
    3. Solve second pass train with primary permeate
    4. Update primary feed with relaxation: feed_new = α·feed_calc + (1-α)·feed_old
    5. Check convergence: |flow_new - flow_old| / flow_old < tol
    6. If not converged and residuals stagnate, switch to Anderson acceleration

    Typical convergence: 5-10 iterations for second pass systems
    """
    pass
```

#### 2.3 New MCP Tool
**File**: `server.py`

Add new tool endpoint:

```python
@mcp.tool()
async def design_second_pass_ro_system(
    primary_config: Dict[str, Any],
    second_pass_recovery_target: float = 0.90,
    membrane_model_second_pass: str = "BW30_PRO_400",
    element_size: str = "8-inch",  # or "4-inch"
    feed_temperature_c: float = 25.0,
    enable_boron_removal: bool = False,
    economic_params: Optional[Dict] = None
) -> Dict[str, Any]:
    """
    Design a complete two-pass RO system.

    Args:
        primary_config: Configuration from optimize_ro_configuration()
        second_pass_recovery_target: Target recovery for second pass (0.85-0.95)
        membrane_model_second_pass: Membrane for second pass (typically high flux BW)
        element_size: "8-inch" or "4-inch"
        enable_boron_removal: Add inter-pass NaOH dosing for boron rejection
        economic_params: Economic parameters (merged for both trains)

    Returns:
        Complete two-train system design with:
        - Both train configurations
        - Iterative mass balance results
        - Combined economics (CAPEX, OPEX, LCOW)
        - Final product quality (<30 ppm TDS target)
    """
    pass
```

#### 2.4 Hybrid Simulator Updates
**File**: `utils/hybrid_ro_simulator.py`

Add multi-train simulation capability:

```python
def simulate_multi_train_system(
    multi_train_system: MultiTrainSystem,
    feed_salinity_ppm: float,
    feed_ion_composition: str,
    membrane_models: Dict[str, str],  # {train_id: membrane_model}
    economic_params: Dict,
    chemical_dosing: Dict
) -> Dict[str, Any]:
    """
    Simulate multi-train RO system with iterative mass balance.

    Steps:
    1. Initialize all trains with guess compositions
    2. Solve trains in dependency order (primary first, then second pass)
    3. Update connected streams
    4. Check convergence
    5. Aggregate economics across trains

    Returns combined results for entire system.
    """
    pass
```

#### 2.5 Pressure Tracking
**Update**: `StreamPort` class to track pressures per train

Each train operates at independent pressure:
- Primary: 18-30 bar typical
- Second pass: 8-15 bar typical

**Important**: Pressure must NOT be inherited between trains. Second pass pump operates independently.

#### 2.6 Chemical Dosing
**File**: `utils/chemical_dosing_calculator.py`

Add second pass specific dosing:

```python
CHEMICAL_DOSING_DEFAULTS = {
    'primary_brackish': {
        'antiscalant_mg_L': 3.0,
    },
    'second_pass': {
        'antiscalant_mg_L': 1.0,  # Lower due to low TDS
        'naoh_for_boron_mg_L': 0.0,  # Optional, if enable_boron_removal=True
        'naoh_target_ph': 10.5,  # Inter-pass pH for boron rejection
    }
}
```

**Boron Removal Note**: Boron is a neutral species (B(OH)₃) that requires pH >10 to convert to borate (B(OH)₄⁻) for effective rejection. Inter-pass NaOH injection is common practice.

#### 2.7 Instrumentation Costs
**File**: `utils/economic_defaults.py`

Multi-train systems require additional instrumentation:
- Conductivity analyzers (per-train permeate and final blend)
- pH control for inter-pass chemical addition
- Pressure instrumentation (per-train)
- Flow meters (inter-train connections)

Add to CAPEX breakdown:
```python
INSTRUMENTATION_COSTS = {
    'conductivity_analyzer_usd': 5000,
    'ph_controller_usd': 3000,
    'pressure_transmitter_usd': 500,
    'flow_meter_usd': 2000
}
```

### Testing & Validation

**Test Cases**:
1. **Two-pass polish**: 100 m³/h primary (75% recovery, 300 ppm permeate) + second pass (90% recovery, <30 ppm product)
2. **Pharmaceutical water**: Ultra-low TDS target (<10 ppm) with boron removal
3. **4-inch pilot**: 20 m³/h primary + 15 m³/h second pass with 4-inch elements

**Validation Against Commercial Designs**:
- Compare flux, pressure, recovery vs vendor design reports (FilmTec WAVE, Hydranautics IMS)
- Validate LCOW calculations against literature values
- Verify iterative convergence (<10 iterations typical)

**Success Criteria**:
- [ ] Multi-train orchestrator functional with DAG-based connectivity
- [ ] Two-pass system converges in <10 iterations with relaxation
- [ ] Second pass produces <30 ppm TDS product
- [ ] Pressure tracking decoupled (primary vs second pass)
- [ ] Inter-pass NaOH dosing calculated for boron removal
- [ ] Instrumentation costs included in WaterTAP economic analysis
- [ ] Regression test validates against 3×5:3 commercial design (100 m³/h primary → 75 m³/h permeate → 67.5 m³/h final product)

### Files Modified/Created
- `utils/multi_train_coordinator.py` (NEW) - DAG orchestrator, ROTrain, MultiTrainSystem
- `utils/hybrid_ro_simulator.py` - Add `simulate_multi_train_system()`
- `server.py` - New tool `design_second_pass_ro_system()`
- `utils/chemical_dosing_calculator.py` - Second pass specific dosing
- `utils/economic_defaults.py` - Instrumentation costs
- `utils/constants.py` - Second pass flux targets and concentrate flow

---

## Phase 2.5: Permeate Backpressure Optimization ⭐

**Timeline**: 1-2 weeks
**Complexity**: LOW-MEDIUM
**Prerequisites**: Phase 2 complete (REQUIRED)

### Objectives

Eliminate interstage booster pumps when pressure differential between stages is small (<2 bar). This is industry-standard practice documented in FilmTec Design Manual for second pass systems and low-pressure brackish multi-stage designs.

### Technical Background

**Fundamental Equation**:
```
TMP = P_feed - P_permeate - π_osmotic
Flux = A_w × TMP
```

**Traditional Approach** (separate pumps per stage):
- Stage N: P_feed_N = 20 bar, P_permeate_N = 0 bar → TMP_N = 20 - π_N
- Stage N+1: P_feed_N+1 = 21 bar, P_permeate_N+1 = 0 bar → TMP_N+1 = 21 - π_N+1
- **Cost**: Interstage booster pump required ($5k-50k CAPEX + maintenance)

**Backpressure Approach** (when Δ P ≤ 2 bar):
- Stage N: P_feed_N = 21 bar (same as N+1), P_permeate_N = 1 bar → TMP_N = 21 - 1 - π_N = 20 - π_N ✓
- Stage N+1: P_feed_N+1 = 21 bar, P_permeate_N+1 = 0 bar → TMP_N+1 = 21 - π_N+1 ✓
- **Savings**: Eliminate interstage booster pump, add backpressure control valve (~$500-2k)

**Net Savings**: 2-5% of total system CAPEX for multi-stage systems

### Decision Logic

```python
def should_use_backpressure_control(P_stage_n, P_stage_n_plus_1):
    """
    Determine if backpressure control is economical vs booster pump.

    Threshold: 2 bar pressure difference (industry standard)

    Returns:
        True: Use backpressure control (eliminate booster pump)
        False: Use traditional interstage booster pump
    """
    delta_P = P_stage_n_plus_1 - P_stage_n

    if delta_P < 0:
        # Stage N+1 needs LESS pressure - no booster anyway
        return False
    elif delta_P <= 2.0:  # bar
        # Small difference - backpressure is economical
        return True
    else:
        # Large difference (>2 bar) - booster pump is more efficient
        # Energy waste from running Stage N at high pressure exceeds pump cost
        return False
```

### Implementation Tasks

#### 2.5.1 Pressure Optimization Module
**New File**: `utils/pressure_optimization.py`

```python
def calculate_optimal_backpressure(
    target_flux_lmh: float,
    feed_pressure_bar: float,
    osmotic_pressure_bar: float,
    A_w: float,
    temperature_c: float = 25.0
) -> float:
    """
    Calculate required permeate backpressure to achieve target flux.

    Equation: Flux = A_w × (P_feed - P_permeate - π)
    Rearrange: P_permeate = P_feed - π - (Flux / A_w)

    Returns permeate backpressure in bar.
    """
    # Convert flux to SI units (m³/m²/s)
    flux_si = target_flux_lmh / 3600000  # LMH to m/s

    # Calculate required TMP
    tmp_required = flux_si / A_w  # Pa
    tmp_required_bar = tmp_required / 1e5

    # Calculate backpressure
    backpressure = feed_pressure_bar - osmotic_pressure_bar - tmp_required_bar

    return max(0.0, backpressure)  # Cannot be negative

def validate_backpressure_safety(
    feed_pressure_bar: float,
    permeate_pressure_bar: float,
    membrane_max_pressure_bar: float
) -> Tuple[bool, str]:
    """
    Validate backpressure operation against membrane safety limits.

    Constraints:
    1. P_permeate < P_feed - 0.3 bar (5 psi safety margin)
    2. P_feed ≤ membrane max pressure
    3. P_permeate ≥ 0 (cannot be vacuum)

    Returns: (is_safe, message)
    """
    if permeate_pressure_bar >= feed_pressure_bar - 0.3:
        return False, f"Permeate pressure ({permeate_pressure_bar:.1f} bar) too close to feed pressure ({feed_pressure_bar:.1f} bar) - risk of flow reversal"

    if feed_pressure_bar > membrane_max_pressure_bar:
        return False, f"Feed pressure ({feed_pressure_bar:.1f} bar) exceeds membrane limit ({membrane_max_pressure_bar:.1f} bar)"

    if permeate_pressure_bar < 0:
        return False, "Cannot apply negative (vacuum) permeate pressure"

    return True, "Backpressure operation is safe"
```

#### 2.5.2 Hybrid Simulator Updates
**File**: `utils/hybrid_ro_simulator.py`

Modify TMP calculation to include permeate pressure:

```python
def calculate_stage_performance_with_backpressure(
    stage_config: Dict,
    feed_pressure_bar: float,
    permeate_pressure_bar: float,  # NEW parameter
    osmotic_pressure_bar: float,
    A_w: float,
    target_flux_lmh: float
) -> Dict:
    """
    Calculate stage performance with permeate backpressure.

    Modified TMP equation:
        TMP = P_feed - P_permeate - π_osmotic

    This replaces the traditional TMP = P_feed - π_osmotic assumption.
    """
    # Calculate actual TMP with backpressure
    tmp_bar = feed_pressure_bar - permeate_pressure_bar - osmotic_pressure_bar

    # Calculate actual flux achieved
    tmp_pa = tmp_bar * 1e5
    flux_achieved_lmh = (A_w * tmp_pa) * 3600000  # Convert to LMH

    # Check if flux target is met
    flux_deviation = abs(flux_achieved_lmh - target_flux_lmh) / target_flux_lmh

    return {
        'tmp_bar': tmp_bar,
        'flux_achieved_lmh': flux_achieved_lmh,
        'flux_deviation': flux_deviation,
        'permeate_pressure_bar': permeate_pressure_bar,
        'feed_pressure_bar': feed_pressure_bar
    }
```

#### 2.5.3 Multi-Stage Optimization
**File**: `utils/multi_train_coordinator.py`

Add backpressure optimization to multi-stage solver:

```python
def optimize_multi_stage_pressures(self, train: ROTrain):
    """
    Optimize pressures across all stages in a train.

    Algorithm:
    1. Calculate required feed pressure for each stage (traditional approach)
    2. Identify stages where Δ P ≤ 2 bar
    3. For consecutive stages with small Δ P, use highest pressure for all
    4. Apply backpressure to earlier stages to maintain flux targets
    5. Update economic model: remove booster pumps, add control valves

    Returns optimized pressure profile and equipment list.
    """
    stage_pressures = []

    # Phase 1: Calculate traditional pressures
    for stage in train.configuration['stages']:
        required_pressure = calculate_required_feed_pressure(stage)
        stage_pressures.append(required_pressure)

    # Phase 2: Identify backpressure opportunities
    optimized_pressures = []
    uses_backpressure = []

    for i, P_current in enumerate(stage_pressures):
        if i == len(stage_pressures) - 1:
            # Last stage - no backpressure needed
            optimized_pressures.append(P_current)
            uses_backpressure.append(False)
        else:
            P_next = stage_pressures[i + 1]
            delta_P = P_next - P_current

            if delta_P <= 2.0 and delta_P > 0:
                # Use next stage pressure and apply backpressure
                optimized_pressures.append(P_next)
                uses_backpressure.append(True)
            else:
                # Use traditional approach
                optimized_pressures.append(P_current)
                uses_backpressure.append(False)

    # Phase 3: Calculate backpressures and validate
    stage_results = []
    for i, (P_feed, use_bp) in enumerate(zip(optimized_pressures, uses_backpressure)):
        if use_bp:
            backpressure = calculate_optimal_backpressure(
                train.configuration['stages'][i]['target_flux'],
                P_feed,
                train.configuration['stages'][i]['osmotic_pressure'],
                train.configuration['stages'][i]['A_w']
            )
            is_safe, msg = validate_backpressure_safety(P_feed, backpressure, train.membrane_max_pressure)
            if not is_safe:
                # Fallback to booster pump
                use_bp = False
                backpressure = 0.0
        else:
            backpressure = 0.0

        stage_results.append({
            'stage': i + 1,
            'feed_pressure_bar': P_feed,
            'permeate_pressure_bar': backpressure,
            'uses_backpressure': use_bp,
            'tmp_bar': P_feed - backpressure - train.configuration['stages'][i]['osmotic_pressure']
        })

    return stage_results
```

#### 2.5.4 Economic Model Updates
**File**: `utils/economic_defaults.py`

Update equipment costing:

```python
# Interstage booster pump costs (only if NOT using backpressure)
BOOSTER_PUMP_COST_USD = {
    'small': 5000,   # <50 m³/h
    'medium': 15000, # 50-200 m³/h
    'large': 50000   # >200 m³/h
}

# Backpressure control equipment (if using backpressure)
BACKPRESSURE_CONTROL_VALVE_USD = {
    'small': 500,
    'medium': 1000,
    'large': 2000
}

def calculate_interstage_equipment_cost(
    flow_m3h: float,
    uses_backpressure: bool
) -> float:
    """
    Calculate interstage equipment cost (booster pump OR control valve).
    """
    if flow_m3h < 50:
        size_class = 'small'
    elif flow_m3h < 200:
        size_class = 'medium'
    else:
        size_class = 'large'

    if uses_backpressure:
        return BACKPRESSURE_CONTROL_VALVE_USD[size_class]
    else:
        return BOOSTER_PUMP_COST_USD[size_class]
```

### Validation Cases

**Case 1: Classic Second Pass**
- Primary RO: 75 m³/h @ 22 bar → 56 m³/h permeate @ 1.5 bar residual
- Second pass requirement: 14 bar
- **Decision**: Δ = 14 - 1.5 = 12.5 bar > 2 bar → **Use booster pump**

**Case 2: Three-Stage Brackish (Ideal for Backpressure)**
- Stage 1 needs: 18 bar
- Stage 2 needs: 19 bar (Δ = 1 bar)
- Stage 3 needs: 20 bar (Δ = 1 bar)
- **Decision**: All Δ ≤ 2 bar → **Run all stages at 20 bar, apply backpressure to Stages 1 and 2**
- **Savings**: Eliminate 2 interstage booster pumps (~$10k-30k CAPEX)

**Case 3: Low-Pressure Second Pass (Edge Case)**
- Primary RO: 100 m³/h @ 18 bar → 75 m³/h permeate @ 2 bar residual
- Second pass requirement: 12 bar
- **Traditional decision**: Δ = 12 - 2 = 10 bar > 2 bar → Use booster pump
- **Optimized approach**:
  - Can we design primary to output 12 bar permeate pressure (via backpressure)?
  - If yes and primary flux targets still met → Eliminate second pass booster pump entirely!
  - This requires primary stages to tolerate 12 bar permeate pressure

**Case 4: Seawater RO (Not Suitable)**
- Stage 1 needs: 60 bar
- Stage 2 needs: 64 bar (Δ = 4 bar)
- Stage 3 needs: 68 bar (Δ = 4 bar)
- **Decision**: All Δ > 2 bar → **Use traditional booster pumps**
- **Reason**: Energy waste from running Stage 1 at 68 bar exceeds booster pump cost

### Benefits

1. **Cost Savings**: 2-5% of total system CAPEX
   - Eliminate booster pumps ($5k-50k each)
   - Reduced maintenance (fewer pumps)
   - Simpler hydraulics

2. **Second Pass Optimization**: Natural fit
   - Second pass often operates at lower pressure than primary
   - Backpressure control is industry standard practice
   - FilmTec Design Manual explicitly documents this approach

3. **Low-Pressure Primary Systems**: Unexpected benefit
   - Three-stage brackish with small Δ P between stages
   - Can eliminate multiple booster pumps

4. **Industry Alignment**: Mirrors best practices
   - FilmTec, Hydranautics, Toray all use this approach
   - Increases competitiveness of tool's designs

### Risks and Mitigations

| Risk | Mitigation |
|------|-----------|
| Permeate pressure exceeds feed pressure | Hard constraint check, 0.3 bar safety margin |
| Membrane delamination | Validate against manufacturer max permeate pressure specs |
| Salt passage increase at high pressure | Include in rejection calculations, monitor in validation |
| Energy waste if Δ P calculation wrong | Conservative threshold (2 bar), allow user override |
| Control complexity | Document clearly, provide worked examples |

### Success Criteria

- [ ] Pressure optimization module functional with decision logic
- [ ] TMP calculations include permeate pressure
- [ ] Multi-stage optimizer identifies backpressure opportunities
- [ ] Economic model conditionally removes booster pumps
- [ ] Safety constraints validated (P_permeate < P_feed - 0.3 bar)
- [ ] Validation cases pass (3-stage brackish eliminates 2 booster pumps)
- [ ] Integration with Phase 2 second pass systems

### Files Modified/Created
- `utils/pressure_optimization.py` (NEW) - Backpressure decision logic and calculations
- `utils/hybrid_ro_simulator.py` - TMP with permeate pressure
- `utils/multi_train_coordinator.py` - Multi-stage pressure optimizer
- `utils/economic_defaults.py` - Conditional booster pump costing
- `V2_API_DOCUMENTATION.md` - Document backpressure optimization feature

---

## Phase 3: Brine Concentration RO

**Timeline**: 6-8 weeks
**Complexity**: HIGH
**Prerequisites**: Phase 2.5 complete (REQUIRED)

### Objectives

Enable design of brine concentration RO systems for zero-liquid discharge (ZLD) applications. Primary RO concentrate is fed to a high-pressure BC-RO train to further concentrate the brine, reducing thermal evaporator load by ~40%.

### Configuration Targets

- **Flux targets**: [9, 6] LMH (2 stages only, 50% and 33% of primary)
- **Min concentrate flow per vessel**: [4.2, 4.4] m³/h (20% higher than primary)
- **Max stages**: 2 (no 3rd stage - use reject recycle for high recovery)
- **Element size**: 8-inch only (4-inch not rated for 70-85 bar operation)

### Operating Conditions

- **Feed TDS**: 40,000-150,000 ppm (from primary concentrate)
- **Recovery**: 30-50% (conservative due to extreme scaling risk)
- **Pressure**: 70-85 bar (extreme pressure application)
- **Product TDS**: 5,000-20,000 ppm (BC-RO permeate)
- **Concentrate TDS**: 100,000-250,000 ppm (to thermal evaporator)
- **Membrane selection**: SW30XHR-440i (extra-high pressure rating, 85 bar max)
- **Antiscalant**: 8-15 mg/L (vs 3-5 mg/L for primary)
- **Energy recovery device**: REQUIRED - Isobaric PX or turbine (95% efficiency)

### Architecture Overview

**Two Permeate Routing Options**:

**Option A: BC Permeate → Primary Permeate (Simple Blending)**
```
Primary RO:  Feed (100 m³/h, 35k ppm) → [Stages] → Permeate (45 m³/h, 300 ppm)
                                                  → Concentrate (55 m³/h, 60k ppm) → BC-RO

BC-RO:       Concentrate (55 m³/h, 60k ppm) → [Stage 1 → Stage 2] → Permeate (22 m³/h, 5k ppm)
                                                                    → Concentrate (33 m³/h, 100k ppm)

Final:       Primary Permeate + BC Permeate = 45 + 22 = 67 m³/h mixed product (~1,800 ppm)
             To Thermal: 33 m³/h (vs 55 m³/h without BC-RO) = 40% load reduction
```

**Option B: BC Permeate → Primary Feed (Iterative Mass Balance)**
```
Primary RO:  Mixed Feed (100 m³/h, 32k ppm) → [Stages] → Permeate (45 m³/h, 250 ppm)
                                                        → Concentrate (55 m³/h, 58k ppm) → BC-RO

BC-RO:       Concentrate (55 m³/h, 58k ppm) → [Stage 1 → Stage 2] → Permeate (22 m³/h, 5k ppm) → Primary Feed
                                                                    → Concentrate (33 m³/h, 98k ppm)

Recycle Loop: BC Permeate blends with raw feed (iterative convergence)
              Effective feed: 100 m³/h raw + 22 m³/h BC permeate = 122 m³/h at 32k ppm

Final:       Primary Permeate only = 45 m³/h (~250 ppm) - cleaner than Option A!
             To Thermal: 33 m³/h (40% load reduction)
```

### Implementation Tasks

#### 3.1 Extend Multi-Train Coordinator
**File**: `utils/multi_train_coordinator.py`

Add `brine_concentration` train type with routing mode:

```python
class MultiTrainSystem:
    def add_bc_ro_train(
        self,
        train_id: str,
        configuration: Dict,
        permeate_routing: str = 'to_primary_feed'  # or 'to_primary_permeate'
    ):
        """
        Add brine concentration RO train to system.

        Permeate Routing:
        - 'to_primary_feed': BC permeate → Primary feed (iterative mass balance)
        - 'to_primary_permeate': BC permeate → Primary permeate (simple blending)

        The routing mode determines connection topology and solver strategy.
        """
        bc_train = ROTrain(train_id, 'brine_concentration', configuration)
        self.add_train(bc_train)

        # Connect BC-RO feed to primary concentrate
        self.connect('primary', 'brine', train_id, 'feed')

        # Connect BC-RO permeate based on routing mode
        if permeate_routing == 'to_primary_feed':
            self.connect(train_id, 'permeate', 'primary', 'feed')
            self.requires_iteration = True  # Flag for iterative solver
        elif permeate_routing == 'to_primary_permeate':
            self.connect(train_id, 'permeate', 'primary', 'permeate')
            self.requires_iteration = False  # Simple blending, no iteration
        else:
            raise ValueError(f"Invalid permeate routing: {permeate_routing}")
```

#### 3.2 Energy Recovery Device Design
**New File**: `utils/erd_design.py`

BC-RO at 70-85 bar REQUIRES energy recovery:

```python
def select_erd_for_bc_ro(
    concentrate_flow_m3h: float,
    concentrate_pressure_bar: float,
    feed_pressure_bar: float,
    application: str = 'brine_concentration'
) -> Dict[str, Any]:
    """
    Select energy recovery device for high-pressure brine concentration.

    BC-RO at 70-85 bar uses:
    - Isobaric pressure exchangers (PX) for medium-large systems (>20 m³/h)
    - Turbochargers/Pelton turbines for smaller systems (<20 m³/h)

    Even pilot BC-RO rigs use pressure exchangers due to extreme energy costs.

    Returns:
        {
            'type': 'isobaric_PX' or 'turbine',
            'efficiency': 0.90-0.95,
            'capital_cost_usd': calculated,
            'power_recovery_kw': calculated,
            'annual_opex_savings_usd': calculated
        }
    """
    # Calculate recoverable energy
    pressure_drop_bar = concentrate_pressure_bar - 5  # Assume 5 bar losses
    pressure_drop_pa = pressure_drop_bar * 1e5
    flow_m3s = concentrate_flow_m3h / 3600
    power_recoverable_kw = (pressure_drop_pa * flow_m3s) / 1000

    # Select device type and efficiency
    if concentrate_flow_m3h > 20:
        erd_type = 'isobaric_PX'
        efficiency = 0.95  # Modern PX units
        # Capital cost scales with flow
        capital_cost_usd = 50000 + (concentrate_flow_m3h * 1000)
    else:
        erd_type = 'turbine'
        efficiency = 0.90  # Pelton turbine
        capital_cost_usd = 20000 + (concentrate_flow_m3h * 500)

    # Calculate actual recovery and savings
    power_recovered_kw = power_recoverable_kw * efficiency
    annual_runtime_hours = 8760 * 0.9  # 90% uptime
    electricity_cost_usd_kwh = 0.07
    annual_savings_usd = power_recovered_kw * annual_runtime_hours * electricity_cost_usd_kwh

    return {
        'type': erd_type,
        'efficiency': efficiency,
        'capital_cost_usd': capital_cost_usd,
        'power_recovery_kw': power_recovered_kw,
        'annual_opex_savings_usd': annual_savings_usd,
        'simple_payback_years': capital_cost_usd / annual_savings_usd
    }
```

#### 3.3 High-Pressure Membrane Catalog
**File**: `config/membrane_catalog.yaml`

Add BC-RO specific membranes (user will populate FilmTec data):

**Target Membranes**:
- **SW30XHR-440i**: Extra-high rejection for BC-RO, 85 bar max pressure
- **SW30HRLE-440**: High rejection low energy, 83 bar max pressure
- **SW30ULE-400i**: Ultra-low energy (if appropriate for lower pressure BC)

**Required Metadata**:
```yaml
SW30XHR-440i:
  family: seawater_high_pressure
  physical:
    element_type: '8040'
    active_area_m2: 40.9
  limits:
    max_pressure_pa: 8500000  # 85 bar - critical for BC-RO!
    max_temperature_c: 45
  test_conditions:
    pressure_bar: 55.0
    temperature_c: 25.0
    feed_ppm: 32000.0
    recovery: 0.08  # Very low test recovery for SWRO
```

#### 3.4 Enhanced PHREEQC Integration
**File**: `utils/phreeqc_client.py`

BC-RO operates at extreme supersaturation. PHREEQC is CRITICAL:

```python
def validate_bc_ro_chemistry(
    feed_composition: Dict[str, float],
    feed_tds_ppm: float,
    recovery: float,
    temperature_c: float,
    ph: float,
    antiscalant_dose_mg_L: float
) -> Dict[str, Any]:
    """
    Validate brine concentration RO chemistry with PHREEQC.

    BC-RO Specific Challenges:
    1. Feed TDS: 40,000-150,000 ppm (exceeds most databases)
    2. Concentrate TDS: 100,000-250,000 ppm (extreme supersaturation)
    3. PHREEQC validity: Most databases valid only to ~200 g/L NaCl

    Fallback Strategy:
    - If feed TDS > 200 g/L: Use empirical scaling correlations
    - If PHREEQC fails to converge: Provide truncated warnings
    - Always calculate: CaSO4, CaCO3, SiO2, BaSO4, SrSO4, CaF2
    """
    # Check database validity
    if feed_tds_ppm > 200000:
        logger.warning(
            f"Feed TDS ({feed_tds_ppm} ppm) exceeds PHREEQC database validity (>200 g/L). "
            "Using empirical scaling correlations."
        )
        return use_empirical_scaling_model(feed_composition, recovery, temperature_c, ph)

    # Attempt PHREEQC simulation
    try:
        result = run_phreeqc_concentration_simulation(
            feed_composition, recovery, temperature_c, ph
        )

        # Adjust SI thresholds for antiscalant
        si_thresholds = get_antiscalant_si_thresholds(
            antiscalant_dose_mg_L,
            antiscalant_type='high_performance_BC'
        )

        # Evaluate scaling risk with BC-specific thresholds
        scaling_risk = evaluate_scaling_risk_bc_ro(result, si_thresholds)

        return {
            'status': 'phreeqc_success',
            'saturation_indices': result['SI'],
            'scaling_risk': scaling_risk,
            'max_sustainable_recovery': calculate_max_recovery(result, si_thresholds)
        }

    except Exception as e:
        logger.error(f"PHREEQC failed for BC-RO conditions: {e}")
        logger.info("Falling back to empirical scaling model")
        return use_empirical_scaling_model(feed_composition, recovery, temperature_c, ph)

def use_empirical_scaling_model(
    feed_composition: Dict[str, float],
    recovery: float,
    temperature_c: float,
    ph: float
) -> Dict[str, Any]:
    """
    Empirical scaling correlations for extreme TDS (>200 g/L).

    Based on literature correlations from:
    - Jiang et al. (2012) - Calcium sulfate scaling in SWRO
    - Lattemann & Höpner (2008) - High-salinity RO
    """
    # Simplified solubility products at high ionic strength
    # (Activity coefficients approach limiting values)
    pass
```

#### 3.5 BC-RO Chemical Dosing
**File**: `utils/chemical_dosing_calculator.py`

```python
CHEMICAL_DOSING_DEFAULTS = {
    'brine_concentration': {
        'antiscalant_mg_L': 10.0,  # Higher dose for extreme conditions
        'antiscalant_type': 'high_performance_BC',  # Specialized formulations
        'mg_oh2_precipitation': False,  # Optional pre-treatment for Mg removal
        'acid_for_pH_adjustment_mg_L': 0.0,  # If needed to prevent CaCO3
    }
}

# Antiscalant SI thresholds for BC-RO
ANTISCALANT_SI_THRESHOLDS_BC = {
    'CaSO4': 1.8,   # vs 1.2 for primary (more aggressive)
    'CaCO3': 1.5,   # vs 1.0 for primary
    'SiO2': 1.3,    # vs 1.0 for primary
    'BaSO4': 2.5,   # vs 2.0 for primary
    'SrSO4': 1.8,   # vs 1.5 for primary
    'CaF2': 1.5     # vs 1.2 for primary
}
```

**Note**: BC-RO often requires specialized high-performance antiscalants (SUEZ Vitec 7000, Nalco PC-191) designed for extreme salinity and temperature.

#### 3.6 New MCP Tool
**File**: `server.py`

```python
@mcp.tool()
async def design_brine_concentration_system(
    primary_config: Dict[str, Any],
    bc_recovery_target: float = 0.40,
    permeate_routing: str = 'to_primary_feed',  # or 'to_primary_permeate'
    membrane_model_bc: str = "SW30XHR-440i",
    feed_ion_composition: str,
    feed_temperature_c: float = 25.0,
    feed_ph: float = 7.5,
    antiscalant_dose_mg_L: float = 10.0,
    economic_params: Optional[Dict] = None
) -> Dict[str, Any]:
    """
    Design a complete primary + brine concentration RO system for ZLD.

    Args:
        primary_config: Configuration from optimize_ro_configuration()
        bc_recovery_target: Target recovery for BC-RO (0.30-0.50 typical)
        permeate_routing: 'to_primary_feed' (iterative) or 'to_primary_permeate' (simple)
        membrane_model_bc: High-pressure membrane (SW30XHR-440i recommended)
        feed_ion_composition: Required for scaling predictions
        antiscalant_dose_mg_L: 8-15 mg/L typical for BC-RO
        economic_params: Must include ERD costs

    Returns:
        Complete ZLD system design with:
        - Primary + BC-RO configurations
        - ERD specification and energy savings
        - Thermal evaporator load reduction (%)
        - Total system LCOW
        - Scaling risk analysis at extreme concentrations
    """
    pass
```

#### 3.7 Iterative Convergence for BC-RO
**File**: `utils/multi_train_coordinator.py`

BC-RO with `permeate_routing='to_primary_feed'` requires enhanced iteration:

```python
def solve_bc_ro_system_with_feed_recycle(
    self,
    max_iterations: int = 30,  # BC-RO may need more iterations
    relaxation_factor: float = 0.3,  # More aggressive relaxation
    convergence_tolerance: float = 0.01
) -> Dict[str, Any]:
    """
    Solve BC-RO system with permeate recycle to primary feed.

    Challenges vs Second Pass:
    1. Larger composition swings (5k ppm BC permeate mixing with raw feed)
    2. Sharp osmotic pressure gradients at high TDS
    3. PHREEQC may fail to converge at extreme concentrations

    Strategy:
    - Use lower relaxation factor (0.3 vs 0.5 for second pass)
    - Allow more iterations (30 vs 20)
    - Switch to Anderson acceleration sooner if residuals stagnate
    """
    iteration = 0
    converged = False

    # Initial guess: Assume BC permeate is 5000 ppm, 40% of primary concentrate flow
    primary_feed_composition_old = self.raw_feed_composition

    while iteration < max_iterations and not converged:
        # Solve primary with current feed composition
        primary_result = simulate_train(
            self.trains['primary'],
            primary_feed_composition_old
        )

        # Solve BC-RO with primary concentrate
        bc_feed = primary_result['concentrate']
        bc_result = simulate_train(
            self.trains['brine_concentration'],
            bc_feed
        )

        # Mix BC permeate with raw feed
        bc_permeate = bc_result['permeate']
        primary_feed_composition_new = mix_streams(
            self.raw_feed_composition,
            bc_permeate
        )

        # Check convergence
        residual = calculate_composition_residual(
            primary_feed_composition_old,
            primary_feed_composition_new
        )

        if residual < convergence_tolerance:
            converged = True
        else:
            # Apply relaxation
            primary_feed_composition_old = apply_relaxation(
                primary_feed_composition_old,
                primary_feed_composition_new,
                relaxation_factor
            )

        iteration += 1

    if not converged:
        logger.warning(f"BC-RO iteration did not converge after {max_iterations} iterations")

    return aggregate_bc_ro_results(primary_result, bc_result)
```

### Testing & Validation

**Test Cases**:

1. **ZLD Seawater System**:
   - Primary: 100 m³/h feed (35k ppm), 45% recovery → 45 m³/h permeate, 55 m³/h concentrate (60k ppm)
   - BC-RO: 55 m³/h feed (60k ppm), 40% recovery → 22 m³/h permeate (5k ppm), 33 m³/h concentrate (100k ppm)
   - Routing: BC permeate to primary feed
   - Validate: Thermal load reduced from 55 to 33 m³/h (40% reduction)

2. **High-Silica Mining Wastewater**:
   - Primary: 50 m³/h feed (8k ppm, 120 mg/L SiO₂), 75% recovery
   - BC-RO: 12.5 m³/h feed (32k ppm, 480 mg/L SiO₂), 35% recovery
   - Challenge: Silica scaling at high pH
   - Validate: PHREEQC predicts amorphous silica SI correctly

3. **High-Sulfate Industrial Brine**:
   - Primary: 200 m³/h feed (12k ppm, high SO₄²⁻), 80% recovery
   - BC-RO: 40 m³/h feed (60k ppm), 45% recovery
   - Challenge: CaSO₄ scaling (gypsum → anhydrite transition)
   - Validate: Antiscalant-adjusted SI thresholds

**Success Criteria**:
- [ ] BC-RO handles feed up to 150,000 ppm TDS
- [ ] Flux targets 9 and 6 LMH achieved without violations
- [ ] ERD design integrated (PX or turbine, 95% efficiency)
- [ ] ERD economic analysis shows 1-3 year payback
- [ ] PHREEQC fallbacks for >200 g/L conditions functional
- [ ] Antiscalant dosing increased to 8-15 mg/L for BC-RO
- [ ] Two permeate routing modes both functional
- [ ] Iterative convergence with feed recycle (<30 iterations)
- [ ] Stress test passes with high-silica feed (>150 mg/L SiO₂)
- [ ] ZLD workflow validated: 40% thermal load reduction confirmed

### Files Modified/Created
- `utils/multi_train_coordinator.py` - Extend for BC-RO train type and routing modes
- `utils/erd_design.py` (NEW) - Energy recovery device selection and economics
- `utils/phreeqc_client.py` - Enhanced for extreme TDS, fallback for >200 g/L
- `utils/chemical_dosing_calculator.py` - BC-RO specific dosing and SI thresholds
- `config/membrane_catalog.yaml` - Add high-pressure membranes (SW30XHR-440i)
- `server.py` - New tool `design_brine_concentration_system()`
- `utils/constants.py` - BC-RO flux targets and concentrate flow
- `V2_API_DOCUMENTATION.md` - Document BC-RO capabilities and ZLD workflow

---

## Cross-Cutting Updates

### Configuration File Structure

**File**: `utils/constants.py`

Add all new configuration targets:

```python
# 8-inch defaults (current)
FLUX_TARGETS_8INCH_PRIMARY_LMH = [18, 15, 12]
MIN_CONCENTRATE_FLOW_8INCH_PRIMARY_M3H = [3.5, 3.8, 4.0]

# 4-inch defaults (Phase 1)
FLUX_TARGETS_4INCH_PRIMARY_LMH = [18, 15, 12]
MIN_CONCENTRATE_FLOW_4INCH_PRIMARY_M3H = [1.0, 1.1, 1.2]

# Second pass - 8-inch (Phase 2)
FLUX_TARGETS_8INCH_SECOND_PASS_LMH = [26, 24, 22]
MIN_CONCENTRATE_FLOW_8INCH_SECOND_PASS_M3H = [2.8, 3.0, 3.2]

# Second pass - 4-inch (Phase 2)
FLUX_TARGETS_4INCH_SECOND_PASS_LMH = [26, 24, 22]
MIN_CONCENTRATE_FLOW_4INCH_SECOND_PASS_M3H = [0.8, 0.9, 1.0]

# Brine concentration - 8-inch only (Phase 3)
FLUX_TARGETS_8INCH_BC_RO_LMH = [9, 6]  # 2 stages only
MIN_CONCENTRATE_FLOW_8INCH_BC_RO_M3H = [4.2, 4.4]

def get_flux_targets(train_type: str, element_size: str) -> List[float]:
    """
    Get flux targets based on train type and element size.

    Args:
        train_type: 'primary', 'second_pass', 'brine_concentration'
        element_size: '4-inch', '8-inch'

    Returns:
        List of flux targets in LMH per stage
    """
    key = f"FLUX_TARGETS_{element_size.upper().replace('-', '')}_{train_type.upper()}_LMH"
    return globals().get(key, FLUX_TARGETS_8INCH_PRIMARY_LMH)

def get_min_concentrate_flow(train_type: str, element_size: str) -> List[float]:
    """
    Get minimum concentrate flow per vessel based on train type and element size.

    Args:
        train_type: 'primary', 'second_pass', 'brine_concentration'
        element_size: '4-inch', '8-inch'

    Returns:
        List of min concentrate flow in m³/h per vessel per stage
    """
    key = f"MIN_CONCENTRATE_FLOW_{element_size.upper().replace('-', '')}_{train_type.upper()}_M3H"
    return globals().get(key, MIN_CONCENTRATE_FLOW_8INCH_PRIMARY_M3H)
```

### Documentation Updates

**Files to Update**:
1. `README.md` - Add new capabilities overview
2. `V2_API_DOCUMENTATION.md` - Document all new tools and parameters
3. `CHANGELOG.md` - Add entries for each phase as completed

**New Documentation Files**:
1. `docs/4_INCH_DESIGN_GUIDE.md` - Design guidelines for small systems
2. `docs/SECOND_PASS_DESIGN_GUIDE.md` - Two-pass system design patterns
3. `docs/BACKPRESSURE_OPTIMIZATION.md` - When and how to use backpressure
4. `docs/ZLD_DESIGN_GUIDE.md` - Complete ZLD workflow with BC-RO

### Testing Strategy

**Regression Test Suite**:

Create `tests/test_multi_configuration.py`:

```python
def test_4inch_small_system():
    """Test 4-inch configuration for 15 m³/h brackish water"""
    pass

def test_second_pass_polish():
    """Test two-pass system for <30 ppm product"""
    pass

def test_backpressure_3stage():
    """Test backpressure optimization eliminates 2 booster pumps"""
    pass

def test_bc_ro_zld():
    """Test BC-RO reduces thermal load by 40%"""
    pass

def test_bc_ro_feed_recycle_convergence():
    """Test BC-RO with feed recycle converges in <30 iterations"""
    pass
```

---

## Implementation Timeline

| Phase | Duration | Dependency | Cumulative Weeks |
|-------|----------|------------|------------------|
| **Phase 1: 4-inch** | 1-2 weeks | None | 1-2 |
| **Phase 2: Second Pass** | 4-6 weeks | Phase 1 complete (recommended) | 5-8 |
| **Phase 2.5: Backpressure** | 1-2 weeks | Phase 2 complete (REQUIRED) | 6-10 |
| **Phase 3: Brine Conc** | 6-8 weeks | Phase 2.5 complete (REQUIRED) | 12-18 |
| **TOTAL** | **12-18 weeks** | | |

---

## Success Metrics

### Phase 1 Success:
- [ ] All 4-inch FilmTec membranes added to catalog
- [ ] Configuration tool auto-selects 4-inch for flows <20 m³/h
- [ ] Concentrate flow constraints correct (1.0-1.2 m³/h range)
- [ ] Regression test passes for 15 m³/h pilot system

### Phase 2 Success:
- [ ] Multi-train orchestrator functional with DAG
- [ ] Two-pass converges in <10 iterations
- [ ] Product <30 ppm TDS achieved
- [ ] Boron removal with inter-pass NaOH
- [ ] Independent pressure tracking per train
- [ ] Instrumentation costs in economic model

### Phase 2.5 Success:
- [ ] Backpressure optimizer functional
- [ ] 3-stage brackish eliminates 2 booster pumps
- [ ] Safety constraints validated
- [ ] 2-5% CAPEX savings demonstrated
- [ ] Integration with second pass systems

### Phase 3 Success:
- [ ] BC-RO handles up to 150,000 ppm feed
- [ ] Flux targets 9 and 6 LMH achieved
- [ ] ERD integration (95% efficiency)
- [ ] PHREEQC fallbacks for extreme TDS
- [ ] 40% thermal load reduction validated
- [ ] Two routing modes functional

---

## Key Architectural Decisions

### ✓ Continue Hybrid Simulator Approach
- Literature-based performance + WaterTAP costing
- Avoid full WaterTAP flowsheet convergence issues
- Validated by Codex and v2.4.0 experience

### ✓ Multi-Train Orchestrator Pattern
- Inspired by WaterTAP's `oaro_multi.py`
- Lightweight DAG (not full NetworkX)
- Typed ports (feed, permeate, brine)
- Two-tier solver: inner (train), outer (system)

### ✓ Relaxation for Stability
- Under-relaxation factor: 0.5 for second pass, 0.3 for BC-RO
- Anderson acceleration if residuals stagnate
- Avoid Newton-Raphson due to sharp osmotic pressure slopes

### ✓ Phase Ordering
- 4-inch first: Quick win, no conflicts
- Second pass before BC-RO: Validate orchestrator in benign conditions
- Backpressure after second pass: Natural integration point
- BC-RO last: Extends proven framework with extreme condition safeguards

---

## Risk Mitigation

| Risk | Mitigation |
|------|-----------|
| **Phase 1**: 4-inch pressure drop data incomplete | Fallback to scaling from 8-inch with diameter correction |
| **Phase 2**: Iterative convergence fails | Implement Anderson acceleration, adjustable relaxation |
| **Phase 2.5**: Backpressure causes membrane damage | Hard constraint: P_permeate < P_feed - 0.3 bar, validate vs max specs |
| **Phase 3**: PHREEQC fails at extreme TDS | Fallback to empirical scaling correlations (Jiang et al. 2012) |
| **Phase 3**: BC-RO never converges | Timeout after 30 iterations, recommend lower recovery target |
| **All phases**: Economic model inaccurate | Validate against vendor quotes and literature LCOW values |

---

## Codex Review Validation

This roadmap incorporates feedback from Codex review on 2025-09-26:

✅ **Flux targets validated**: Adjusted to 12-20 LMH (brackish), 18-26 LMH (second pass), 5-8 LMH (BC-RO)
✅ **Architecture mirrors WaterTAP patterns**: Multi-train orchestrator based on `oaro_multi.py`
✅ **Relaxation strategy confirmed**: 0.5 under-relax default, Anderson acceleration for stagnation
✅ **ERD integration emphasized**: Critical for BC-RO, isobaric PX at 70-85 bar
✅ **Chemical dosing enhanced**: BC-RO requires 8-15 mg/L antiscalant, second pass needs NaOH
✅ **Temperature correction noted**: 4-inch elements often 20-30% below nameplate in cold feeds
✅ **PHREEQC safeguards**: Fallback for >200 g/L TDS, empirical correlations
✅ **Phase ordering validated**: 4-inch → Second Pass → Backpressure → BC-RO is correct sequence

---

## Appendix A: Key Literature References

1. **FilmTec Design Manual** (Form No. 45-D01504-en, Rev. 18, September 2025)
   - Section 3.7: Permeate-staged (double-pass) systems
   - Section 3.9: Membrane system design guidelines
   - Flux targets and concentrate flow recommendations

2. **"Reverse Osmosis: Industrial Processes and Applications"** (Jane Kucera, 2nd Edition)
   - Chapter 5: Basic flow patterns (double pass, concentrate recycle)
   - Chapter 15: Zero-liquid discharge systems with brine concentrators
   - Chapter 16.5: High efficiency reverse osmosis (HERO) for ZLD

3. **WaterTAP Documentation** (watertap-org/watertap)
   - `watertap/flowsheets/oaro/oaro_multi.py` - Multi-stage orchestration patterns
   - `watertap/flowsheets/lsrro` - Large-scale reverse osmosis examples

4. **Jiang et al. (2012)** - "Calcium sulfate scaling in reverse osmosis: Role of ionic strength"
   - Empirical scaling correlations at high ionic strength

5. **Lattemann & Höpner (2008)** - "Environmental impact and impact assessment of seawater desalination"
   - High-salinity RO design considerations

---

## Appendix B: Glossary

- **BC-RO**: Brine Concentration Reverse Osmosis
- **DAG**: Directed Acyclic Graph (for train connectivity)
- **ERD**: Energy Recovery Device (pressure exchanger or turbine)
- **LMH**: Liters per square meter per hour (flux units)
- **PX**: Pressure Exchanger (isobaric ERD)
- **SI**: Saturation Index (PHREEQC scaling prediction)
- **TMP**: Transmembrane Pressure (driving force for flux)
- **ZLD**: Zero Liquid Discharge (no wastewater disposal)

---

**End of Roadmap**