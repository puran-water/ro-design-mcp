"""
Pydantic schemas for RO Design MCP Server.

Defines data contracts for inputs, outputs, and artifacts.
"""

from typing import Any, Dict, List, Optional
from datetime import datetime
from pydantic import BaseModel, Field, ConfigDict

# Schema versions
SCHEMA_VERSION_INPUT = "1.0.0"
SCHEMA_VERSION_RESULTS = "1.0.0"
SCHEMA_VERSION_CONTEXT = "1.0.0"
SCHEMA_VERSION_MANIFEST = "1.0.0"


# ============================================================================
# Input Schemas
# ============================================================================

class FeedComposition(BaseModel):
    """Feed water composition and conditions."""
    
    salinity_ppm: float = Field(..., description="Total dissolved solids in ppm")
    ion_composition_mg_l: Dict[str, float] = Field(
        ..., 
        description="Ion concentrations in mg/L (e.g., {'Na+': 1500, 'Cl-': 2400})"
    )
    temperature_c: float = Field(25.0, description="Feed temperature in Celsius")


class StageConfiguration(BaseModel):
    """Configuration for a single RO stage."""
    
    stage_number: int = Field(..., ge=1, le=3)
    feed_flow_m3h: float = Field(..., gt=0)
    n_vessels: int = Field(..., ge=1)
    vessel_count: int = Field(..., ge=1)
    elements_per_vessel: int = Field(7, ge=1, le=8)
    membrane_area_m2: float = Field(..., gt=0)
    stage_recovery: float = Field(..., ge=0, le=1)
    feed_pressure_bar: Optional[float] = Field(None, gt=0)


class RecycleInfo(BaseModel):
    """Concentrate recycle configuration."""
    
    uses_recycle: bool = Field(False)
    recycle_ratio: Optional[float] = Field(None, ge=0, le=1)
    recycle_flow_m3h: Optional[float] = Field(None, ge=0)
    recycle_split_ratio: Optional[float] = Field(None, ge=0, le=1)


class ROConfiguration(BaseModel):
    """Complete RO system configuration."""
    
    n_stages: int = Field(..., ge=1, le=3)
    stage_count: int = Field(None)  # Alias for n_stages
    stages: List[StageConfiguration]
    recycle_info: RecycleInfo
    total_vessels: Optional[int] = None
    total_elements: Optional[int] = None
    total_membrane_area_m2: Optional[float] = None
    
    model_config = ConfigDict(validate_assignment=True)


class MembraneProperties(BaseModel):
    """Custom membrane properties (optional override)."""
    
    water_permeability_m_s_pa: Optional[float] = Field(None, gt=0)
    salt_permeability_m_s: Optional[float] = Field(None, gt=0)
    structural_parameter_m: Optional[float] = Field(None, gt=0)


class SimulationOptions(BaseModel):
    """Simulation control options."""
    
    optimize_pumps: bool = Field(True)
    timeout_seconds: int = Field(120, gt=0, le=600)
    solver: str = Field("ipopt")
    tolerance: float = Field(1e-6, gt=0)


class ROSimulationInput(BaseModel):
    """Complete input specification for RO simulation."""
    
    schema_version: str = Field(SCHEMA_VERSION_INPUT)
    configuration: ROConfiguration
    feed: FeedComposition
    membrane_type: str = Field("brackish", pattern="^(brackish|seawater)$")
    membrane_properties_override: Optional[MembraneProperties] = None
    options: SimulationOptions = Field(default_factory=SimulationOptions)
    
    model_config = ConfigDict(validate_assignment=True)


# ============================================================================
# Output Schemas
# ============================================================================

class SolveStatus(BaseModel):
    """Solver status information."""
    
    success: bool = Field(..., description="True if solve succeeded")
    termination_condition: str = Field(...)
    solver_message: Optional[str] = None
    iterations: Optional[int] = Field(None, ge=0)
    solve_time_seconds: Optional[float] = Field(None, ge=0)


class PerformanceMetrics(BaseModel):
    """System performance metrics."""
    
    system_recovery: float = Field(..., ge=0, le=1)
    total_permeate_flow_m3h: float = Field(..., ge=0)
    total_permeate_tds_mg_l: float = Field(..., ge=0)
    total_power_consumption_kw: float = Field(..., ge=0)
    specific_energy_kwh_m3: float = Field(..., ge=0)


class IonRejection(BaseModel):
    """Ion-specific rejection data."""
    
    feed_mg_l: float = Field(..., ge=0)
    permeate_mg_l: float = Field(..., ge=0)
    concentrate_mg_l: float = Field(..., ge=0)
    rejection: float = Field(..., ge=0, le=1)


class StageResult(BaseModel):
    """Results for a single RO stage."""
    
    stage: int = Field(..., ge=1, le=3)
    recovery: float = Field(..., ge=0, le=1)
    feed_flow_kg_s: float = Field(..., ge=0)
    permeate_flow_kg_s: float = Field(..., ge=0)
    concentrate_flow_kg_s: float = Field(..., ge=0)
    feed_pressure_bar: float = Field(..., ge=0)
    concentrate_pressure_bar: float = Field(..., ge=0)
    permeate_pressure_bar: float = Field(..., ge=0)
    pump_power_kw: float = Field(..., ge=0)
    ion_data: Dict[str, IonRejection]


class EconomicResults(BaseModel):
    """Economic analysis results."""
    
    capital_cost_usd: float = Field(..., ge=0)
    operating_cost_usd_year: float = Field(..., ge=0)
    lcow_usd_m3: float = Field(..., ge=0, description="Levelized cost of water")
    specific_energy_consumption_kwh_m3: float = Field(..., ge=0)
    electricity_cost_usd_year: float = Field(..., ge=0)
    maintenance_cost_usd_year: float = Field(..., ge=0)
    membrane_replacement_cost_usd_year: float = Field(..., ge=0)
    individual_unit_costs: Dict[str, float]
    annual_production_m3: float = Field(..., ge=0)


class MassBalance(BaseModel):
    """Mass balance verification."""
    
    mass_balance_error: float = Field(...)
    mass_balance_ok: bool = Field(...)


class ROSimulationResults(BaseModel):
    """Complete simulation results."""
    
    schema_version: str = Field(SCHEMA_VERSION_RESULTS)
    status: str = Field(..., description="success or error")
    solve_info: SolveStatus
    performance: PerformanceMetrics
    stage_results: List[StageResult]
    economics: EconomicResults
    mass_balance: MassBalance
    ion_analysis: Dict[str, Dict[str, float]]
    warnings: List[str] = Field(default_factory=list)
    artifact_dir: str = Field(..., description="Path to artifact directory")
    
    model_config = ConfigDict(validate_assignment=True)


# ============================================================================
# Artifact Schemas
# ============================================================================

class RunContext(BaseModel):
    """Execution context for reproducibility."""
    
    schema_version: str = Field(SCHEMA_VERSION_CONTEXT)
    created_at: datetime
    run_id: str
    tool_name: str
    python_version: str
    platform: str
    os: str
    git: Dict[str, Optional[str]]
    packages: Dict[str, Optional[str]]
    environment_variables: Dict[str, str] = Field(default_factory=dict)
    
    model_config = ConfigDict(validate_assignment=True)


class ArtifactFile(BaseModel):
    """Metadata for a single artifact file."""
    
    filename: str
    path: str
    sha256: str
    size_bytes: int
    created_at: datetime


class ArtifactManifest(BaseModel):
    """Manifest of all artifacts for a run."""
    
    schema_version: str = Field(SCHEMA_VERSION_MANIFEST)
    run_id: str
    tool_name: str
    created_at: datetime
    input_schema_version: str
    results_schema_version: str
    context_schema_version: str
    files: List[ArtifactFile]
    total_size_bytes: int
    
    model_config = ConfigDict(validate_assignment=True)


# ============================================================================
# Optimization Tool Schemas
# ============================================================================

class OptimizationInput(BaseModel):
    """Input for RO configuration optimization."""
    
    feed_flow_m3h: float = Field(..., gt=0)
    water_recovery_fraction: float = Field(..., gt=0, le=1)
    membrane_type: str = Field("brackish", pattern="^(brackish|seawater)$")
    allow_recycle: bool = Field(True)
    max_recycle_ratio: Optional[float] = Field(0.9, ge=0, le=1)
    flux_targets_lmh: Optional[List[float]] = None
    flux_tolerance: Optional[float] = Field(0.1, ge=0, le=1)
    
    model_config = ConfigDict(validate_assignment=True)


class OptimizationResult(BaseModel):
    """Result from RO configuration optimization."""
    
    status: str = Field(..., pattern="^(success|error)$")
    configurations: List[Dict[str, Any]]
    summary: Dict[str, Any]
    message: Optional[str] = None
    
    model_config = ConfigDict(validate_assignment=True)