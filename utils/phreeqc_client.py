"""
PHREEQC Client for RO Scaling Calculations

This module provides a simplified PHREEQC interface specifically designed
for RO system scaling predictions and water chemistry calculations.
Includes caching for performance and focuses on key RO scales.
"""

import os
import sys
import logging
import hashlib
import json
from typing import Dict, Optional, List, Tuple, Any
from functools import lru_cache
from pathlib import Path
import numpy as np

try:
    from periodictable import formula as chemform  # Used for molar mass lookups
except ImportError:  # pragma: no cover - periodictable is a phreeqpython dependency
    chemform = None

logger = logging.getLogger(__name__)

# Cache for saturation index calculations
_SI_CACHE = {}
_MAX_CACHE_SIZE = 1000

# Try to import PhreeqPython
try:
    import phreeqpython
    PHREEQPYTHON_AVAILABLE = True
except ImportError:
    PHREEQPYTHON_AVAILABLE = False
    logger.warning("PhreeqPython not available. PHREEQC calculations will be disabled.")


class PhreeqcROClient:
    """
    PHREEQC client optimized for RO scaling calculations.
    """

    # Key minerals for RO scaling
    RO_SCALING_MINERALS = [
        'Calcite',       # CaCO3
        'Aragonite',     # CaCO3 (alternative form)
        'Gypsum',        # CaSO4·2H2O
        'Anhydrite',     # CaSO4
        'Barite',        # BaSO4
        'Celestite',     # SrSO4
        'Fluorite',      # CaF2
        'SiO2(a)',       # Amorphous silica
        'Brucite',       # Mg(OH)2
    ]

    # Database recommendations for RO calculations
    DATABASE_RECOMMENDATIONS = {
        'default': 'phreeqc.dat',      # General purpose
        'seawater': 'pitzer.dat',      # High ionic strength
        'brackish': 'phreeqc.dat',     # Moderate ionic strength
        'industrial': 'minteq.v4.dat', # Industrial waters
    }

    def __init__(self, database_path: Optional[str] = None, cache_enabled: bool = True):
        """
        Initialize PHREEQC client for RO calculations.

        Args:
            database_path: Path to PHREEQC database file. If None, uses default.
            cache_enabled: Enable caching for repeated calculations
        """
        if not PHREEQPYTHON_AVAILABLE:
            raise ImportError("PhreeqPython is required for PHREEQC calculations")

        self.cache_enabled = cache_enabled
        self.pp = None

        # Optional mapping for display purposes only
        # PhreeqPython handles the chemistry internally
        self.element_to_ion_display = {
            'Na': 'Na+',
            'Ca': 'Ca2+',
            'Mg': 'Mg2+',
            'K': 'K+',
            'Ba': 'Ba2+',
            'Sr': 'Sr2+',
            'Cl': 'Cl-',
            'S(6)': 'SO4-2',
            'C(4)': 'HCO3-',
            'N(5)': 'NO3-',
            'F': 'F-',
            'Si': 'SiO2'
        }

        self._initialize_phreeqc(database_path)

    def _initialize_phreeqc(self, database_path: Optional[str] = None):
        """Initialize PhreeqPython instance with appropriate database."""
        try:
            if database_path and os.path.exists(database_path):
                # Use specified database
                self.pp = phreeqpython.PhreeqPython(database=database_path)
                self.database_path = database_path
                logger.info(f"Initialized PHREEQC with database: {os.path.basename(database_path)}")
            else:
                # Let PhreeqPython use its default database
                # PhreeqPython will find its bundled database automatically
                self.pp = phreeqpython.PhreeqPython()
                self.database_path = "default"
                logger.info("Initialized PHREEQC with default database")

        except Exception as e:
            logger.error(f"Failed to initialize PHREEQC: {e}")
            raise

    def _find_default_database(self) -> str:
        """Find default PHREEQC database."""
        potential_paths = [
            # Windows paths
            r"C:\Program Files\USGS\phreeqc-3.8.6-17100-x64\database\phreeqc.dat",
            r"C:\phreeqc\database\phreeqc.dat",
            # Linux/WSL paths
            "/mnt/c/Program Files/USGS/phreeqc-3.8.6-17100-x64/database/phreeqc.dat",
            "/usr/local/share/phreeqc/database/phreeqc.dat",
            "/usr/share/phreeqc/database/phreeqc.dat",
            # Local installation
            Path(__file__).parent.parent / "databases" / "phreeqc.dat",
        ]

        for path in potential_paths:
            if isinstance(path, Path):
                path = str(path)
            if os.path.exists(path):
                logger.info(f"Found PHREEQC database at: {path}")
                return path

        # Check environment variable
        if 'PHREEQC_DATABASE' in os.environ:
            db_dir = os.environ['PHREEQC_DATABASE']
            db_path = os.path.join(db_dir, 'phreeqc.dat')
            if os.path.exists(db_path):
                return db_path

        raise FileNotFoundError("Could not find PHREEQC database. Please specify path.")

    def calculate_saturation_indices(
        self,
        ion_composition: Dict[str, float],
        temperature_c: float = 25.0,
        ph: float = 7.5,
        pe: float = 4.0,
        use_cache: bool = True
    ) -> Dict[str, float]:
        """
        Calculate saturation indices for RO-relevant minerals.

        Args:
            ion_composition: Ion concentrations in mg/L
            temperature_c: Temperature in Celsius
            ph: pH value
            pe: Redox potential (pe)
            use_cache: Use cached results if available

        Returns:
            Dictionary of mineral names to saturation indices
        """
        # Create cache key if caching is enabled
        if use_cache and self.cache_enabled:
            cache_key = self._create_cache_key(ion_composition, temperature_c, ph, pe)
            if cache_key in _SI_CACHE:
                logger.debug("Using cached saturation indices")
                return _SI_CACHE[cache_key]

        try:
            # Build PHREEQC solution
            solution_dict = self._build_solution(ion_composition, temperature_c, ph, pe)

            # Add solution to PHREEQC - returns a solution object
            solution = self.pp.add_solution(solution_dict)

            # Get saturation indices for RO minerals
            si_results = {}
            for mineral in self.RO_SCALING_MINERALS:
                try:
                    # Get SI using the solution object's si() method
                    si = solution.si(mineral)
                    if si is not None and not np.isnan(si) and si != -999.0:
                        si_results[mineral] = float(si)
                except Exception as e:
                    # Mineral might not exist in this database
                    logger.debug(f"Could not calculate SI for {mineral}: {e}")
                    continue

            # Cache results
            if use_cache and self.cache_enabled and len(_SI_CACHE) < _MAX_CACHE_SIZE:
                _SI_CACHE[cache_key] = si_results

            return si_results

        except Exception as e:
            logger.error(f"Error calculating saturation indices: {e}")
            raise

    def calculate_lsi(
        self,
        calcium_mg_l: float,
        alkalinity_mg_l_caco3: float,
        tds_mg_l: float,
        temperature_c: float = 25.0,
        ph: float = 7.5
    ) -> float:
        """
        Calculate Langelier Saturation Index (LSI) for calcium carbonate.

        Args:
            calcium_mg_l: Calcium concentration in mg/L as Ca
            alkalinity_mg_l_caco3: Alkalinity in mg/L as CaCO3
            tds_mg_l: Total dissolved solids in mg/L
            temperature_c: Temperature in Celsius
            ph: pH value

        Returns:
            LSI value
        """
        # Build simplified solution for LSI calculation
        ion_composition = {
            'Ca': calcium_mg_l,
            'Alkalinity': alkalinity_mg_l_caco3,
        }

        # Add background ions based on TDS
        # Approximate Na and Cl from TDS (simplified)
        remaining_tds = max(0, tds_mg_l - calcium_mg_l - alkalinity_mg_l_caco3)
        ion_composition['Na'] = remaining_tds * 0.3  # Rough approximation
        ion_composition['Cl'] = remaining_tds * 0.5  # Rough approximation

        # Calculate SI for calcite
        si_results = self.calculate_saturation_indices(
            ion_composition, temperature_c, ph
        )

        # LSI is the saturation index of calcite
        if 'Calcite' in si_results:
            return si_results['Calcite']
        elif 'Aragonite' in si_results:
            return si_results['Aragonite']
        else:
            raise ValueError("Could not calculate LSI - Calcite not found in results")

    def calculate_scaling_potential(
        self,
        feed_composition: Dict[str, float],
        recovery: float,
        temperature_c: float = 25.0,
        ph: float = 7.5,
        rejection: float = 0.985,
        maintain_ph: bool = False
    ) -> Dict[str, Any]:
        """
        Calculate scaling potential for RO concentrate at given recovery using PHREEQC.

        This method now properly uses PHREEQC's REACTION capability to model
        water removal and concentration effects, including CO2 degassing,
        speciation changes, and pH shifts.

        Args:
            feed_composition: Feed water ion concentrations in mg/L
            recovery: System recovery (0-1)
            temperature_c: Temperature in Celsius
            ph: pH value
            rejection: Salt rejection (default 0.985)
            maintain_ph: If True, use Fix_pH to maintain pH; if False, let pH drift naturally

        Returns:
            Dictionary with concentrate composition and saturation indices
        """
        # Calculate concentration factor
        cf = 1 / (1 - recovery)

        # Build PHREEQC solution with proper ion mapping
        solution_dict = self._build_solution(feed_composition, temperature_c, ph, pe=4.0)

        # Create feed solution in PHREEQC
        feed_solution = self.pp.add_solution(solution_dict)

        # Create a copy for concentration
        concentrate_solution = feed_solution.copy()

        # Calculate water removal (recovery * initial water moles)
        water_to_remove = recovery * 55.51  # moles

        try:
            # Remove water using PhreeqPython's native change method
            # This automatically creates the proper REACTION block
            concentrate_solution.change({'H2O': -water_to_remove}, units='mol')

            # If maintaining pH, use PhreeqPython's change_ph method
            # This automatically uses Fix_pH equilibrium phase
            if maintain_ph:
                concentrate_solution.change_ph(ph)

        except Exception as e:
            # NO FALLBACK - fail loudly
            logger.error(f"PHREEQC concentration failed: {e}")
            raise RuntimeError(f"Cannot calculate concentrate chemistry without PHREEQC: {e}")

        # Extract concentrate composition directly from solution object
        try:
            if chemform is None:
                raise RuntimeError("periodictable dependency not available for molar mass conversion")

            concentrate_composition = {}
            solution_volume = concentrate_solution.volume or 1.0

            # Get all elements present in the solution along with their molar totals
            for element, moles in concentrate_solution.elements.items():
                base_element = self._get_base_element_symbol(element)
                if base_element is None:
                    continue

                if moles is None:
                    continue

                try:
                    molar_mass = chemform(base_element).mass
                except Exception:
                    # Skip species without defined molar mass (e.g., electrons)
                    logger.debug(f"Skipping element {element}: cannot resolve molar mass")
                    continue

                mg_total = float(moles) * molar_mass * 1e3
                mg_per_L = mg_total / solution_volume  # volume is in L

                # Map to our ion notation if needed (optional for display)
                ion_name = self._get_ion_name(element)
                concentrate_composition[ion_name] = mg_per_L

            # Get actual pH of concentrate
            actual_ph = concentrate_solution.pH

            # Calculate saturation indices directly from concentrate solution
            si_results = {}
            for mineral in self.RO_SCALING_MINERALS:
                try:
                    si = concentrate_solution.si(mineral)
                    if si is not None and not np.isnan(si) and si != -999.0:
                        si_results[mineral] = float(si)
                except:
                    # Mineral not in database
                    continue

            # Get total silica if present
            if 'Si' in concentrate_solution.elements:
                si_mg = concentrate_solution.total_element('Si', 'mg')
                # Convert Si to SiO2 equivalent
                silica_mg_l = (si_mg * 60.08 / 28.09) / concentrate_solution.volume
                concentrate_composition['SiO2_total'] = silica_mg_l

            # Determine scaling risks
            scaling_risks = self._assess_scaling_risks(si_results)

            return {
                'recovery': recovery,
                'concentration_factor': cf,
                'concentrate_composition': concentrate_composition,
                'saturation_indices': si_results,
                'actual_ph': actual_ph,
                'ph_shift': actual_ph - ph,
                'scaling_risks': scaling_risks,
                'limiting_scales': [s for s in scaling_risks if scaling_risks[s] == 'high'],
                'method': 'PHREEQC_native'
            }

        except Exception as e:
            logger.error(f"Failed to extract concentrate data: {e}")
            raise RuntimeError(f"Cannot extract concentrate chemistry from PHREEQC: {e}")


    def _get_ion_name(self, element: str) -> str:
        """Convert PHREEQC element name to ion notation for display."""
        return self.element_to_ion_display.get(element, element)

    @staticmethod
    def _get_base_element_symbol(element: str) -> Optional[str]:
        """Normalize PHREEQC element labels like 'S(6)' to plain element symbols."""
        if not element:
            return None

        base = element.split('(')[0].strip()
        if not base or base.lower() in {'charge', 'e'}:
            return None

        return base

    def find_maximum_recovery(
        self,
        feed_composition: Dict[str, float],
        temperature_c: float = 25.0,
        ph: float = 7.5,
        use_antiscalant: bool = True,
        tolerance: float = 0.001
    ) -> Dict[str, Any]:
        """
        Find maximum sustainable recovery based on scaling limits.

        Uses binary search to find the highest recovery that meets all
        scaling constraints.

        Args:
            feed_composition: Feed water ion concentrations in mg/L
            temperature_c: Temperature in Celsius
            ph: pH value
            use_antiscalant: Apply antiscalant limits
            tolerance: Recovery search tolerance

        Returns:
            Maximum recovery and limiting factors
        """
        # Define scaling limits based on literature
        if use_antiscalant:
            si_limits = {
                'Calcite': 1.8,      # LSI < 1.8 per warranty (PHREEQC SI = LSI for CaCO3)
                'Aragonite': 1.8,    # Alternative CaCO3
                'Gypsum': np.log10(2.3),  # 230% supersaturation
                'Anhydrite': np.log10(2.3),
                'Barite': 0.0,       # 100% saturation (antiscalants ineffective for BaSO4)
                'Celestite': np.log10(1.15), # 115% saturation with antiscalant
                'Fluorite': 0.0,     # At saturation
                'SiO2(a)': 0.0,      # Amorphous silica at saturation
                'Chalcedony': -0.2,  # More conservative for crystalline forms
                'Quartz': -0.5,      # Most conservative for crystalline silica
                'Brucite': 0.5,      # Some supersaturation allowed
            }
        else:
            # More conservative limits without antiscalant
            si_limits = {
                'Calcite': 0.5,
                'Aragonite': 0.5,
                'Gypsum': 0.0,
                'Anhydrite': 0.0,
                'Barite': -0.3,
                'Celestite': -0.3,
                'Fluorite': -0.3,
                'SiO2(a)': -0.3,     # Below saturation without antiscalant
                'Chalcedony': -0.5,  # Conservative for crystalline forms
                'Quartz': -0.7,      # Very conservative for quartz
                'Brucite': 0.0,
            }

        # Binary search for maximum recovery
        min_recovery = 0.1
        max_recovery = 0.95  # Practical upper limit

        limiting_factor = None
        best_recovery = min_recovery
        best_results = None

        while max_recovery - min_recovery > tolerance:
            test_recovery = (min_recovery + max_recovery) / 2

            # Calculate scaling potential at this recovery
            results = self.calculate_scaling_potential(
                feed_composition, test_recovery, temperature_c, ph
            )

            # Check if any limits are exceeded
            exceeded = False
            for mineral, si in results['saturation_indices'].items():
                if mineral in si_limits:
                    if si > si_limits[mineral]:
                        exceeded = True
                        limiting_factor = f"{mineral} (SI: {si:.2f} > {si_limits[mineral]:.2f})"
                        break

            if exceeded:
                # Recovery too high, search lower
                max_recovery = test_recovery
            else:
                # Recovery acceptable, try higher
                min_recovery = test_recovery
                best_recovery = test_recovery
                best_results = results

        # Return results
        return {
            'maximum_recovery': best_recovery,
            'limiting_factor': limiting_factor,
            'final_saturation_indices': best_results['saturation_indices'] if best_results else {},
            'concentrate_composition': best_results['concentrate_composition'] if best_results else {},
            'antiscalant_used': use_antiscalant
        }

    def _build_solution(
        self,
        ion_composition: Dict[str, float],
        temperature_c: float,
        ph: float,
        pe: float
    ) -> Dict[str, Any]:
        """Build PHREEQC solution dictionary."""
        solution = {
            'temp': temperature_c,
            'pH': ph,
            'pe': pe,
            'units': 'mg/l'
        }

        # Map charge-tagged ion names to PHREEQC format with unit conversions
        ion_mapping = {
            # Cations
            'Na+': ('Na', 1.0),
            'Ca2+': ('Ca', 1.0),
            'Ca+2': ('Ca', 1.0),
            'Mg2+': ('Mg', 1.0),
            'Mg+2': ('Mg', 1.0),
            'K+': ('K', 1.0),
            'Fe2+': ('Fe(2)', 1.0),
            'Fe3+': ('Fe(3)', 1.0),
            'Mn2+': ('Mn', 1.0),
            'Ba2+': ('Ba', 1.0),
            'Sr2+': ('Sr', 1.0),
            'NH4+': ('N(-3)', 18.04/14.01),  # Convert NH4 to N basis

            # Anions
            'Cl-': ('Cl', 1.0),
            'SO4-2': ('S(6)', 96.06/32.07),  # Convert SO4 to S basis
            'SO4^2-': ('S(6)', 96.06/32.07),
            'HCO3-': ('Alkalinity', 1.0),
            'CO3-2': ('C(4)', 60.01/12.01),  # Convert CO3 to C basis
            'CO3^2-': ('C(4)', 60.01/12.01),
            'NO3-': ('N(5)', 62.00/14.01),  # Convert NO3 to N basis
            'F-': ('F', 1.0),
            'PO4-3': ('P', 94.97/30.97),  # Convert PO4 to P basis
            'Br-': ('Br', 1.0),
            'B(OH)4-': ('B', 78.84/10.81),  # Convert borate to B basis

            # Silica (special handling)
            'SiO2': ('Si', 60.08/28.09),  # Convert SiO2 to Si basis
            'SiO3-2': ('Si', 76.08/28.09),  # Convert SiO3 to Si basis
            'H4SiO4': ('Si', 96.11/28.09),  # Convert H4SiO4 to Si basis

            # Legacy non-charged names (for backward compatibility)
            'Na': ('Na', 1.0),
            'Ca': ('Ca', 1.0),
            'Mg': ('Mg', 1.0),
            'K': ('K', 1.0),
            'Cl': ('Cl', 1.0),
            'SO4': ('S(6)', 96.06/32.07),
            'HCO3': ('Alkalinity', 1.0),
            'F': ('F', 1.0),
        }

        for ion, conc in ion_composition.items():
            if ion in ion_mapping:
                phreeqc_ion, conversion = ion_mapping[ion]
                # Apply unit conversion
                converted_conc = conc / conversion  # Division because we defined it as MW_compound/MW_element
                solution[phreeqc_ion] = converted_conc
            else:
                # Log warning for unmapped ions
                logger.warning(f"Unknown ion '{ion}' - attempting direct use")
                solution[ion] = conc

        return solution

    def _create_cache_key(
        self,
        ion_composition: Dict[str, float],
        temperature_c: float,
        ph: float,
        pe: float
    ) -> str:
        """Create cache key for saturation index calculations."""
        # Create deterministic string representation
        key_parts = [
            f"T:{temperature_c:.1f}",
            f"pH:{ph:.2f}",
            f"pe:{pe:.1f}"
        ]

        # Sort ions for consistency
        for ion in sorted(ion_composition.keys()):
            key_parts.append(f"{ion}:{ion_composition[ion]:.3f}")

        key_string = "|".join(key_parts)

        # Return hash for compact storage
        return hashlib.md5(key_string.encode()).hexdigest()

    def _assess_scaling_risks(self, si_results: Dict[str, float]) -> Dict[str, str]:
        """Assess scaling risk levels based on saturation indices."""
        risks = {}

        for mineral, si in si_results.items():
            if mineral in ['Calcite', 'Aragonite']:
                # Calcium carbonate
                if si > 1.8:
                    risks[mineral] = 'high'
                elif si > 1.0:
                    risks[mineral] = 'medium'
                elif si > 0.5:
                    risks[mineral] = 'low'
                else:
                    risks[mineral] = 'none'

            elif mineral in ['Gypsum', 'Anhydrite']:
                # Calcium sulfate
                if si > np.log10(2.0):  # 200% supersaturation
                    risks[mineral] = 'high'
                elif si > 0:
                    risks[mineral] = 'medium'
                elif si > -0.3:
                    risks[mineral] = 'low'
                else:
                    risks[mineral] = 'none'

            elif mineral in ['Barite', 'Celestite']:
                # Barium/Strontium sulfate
                if si > np.log10(0.8):  # 80% saturation
                    risks[mineral] = 'high'
                elif si > np.log10(0.5):
                    risks[mineral] = 'medium'
                elif si > np.log10(0.3):
                    risks[mineral] = 'low'
                else:
                    risks[mineral] = 'none'

            else:
                # General assessment
                if si > 0.5:
                    risks[mineral] = 'high'
                elif si > 0:
                    risks[mineral] = 'medium'
                elif si > -0.5:
                    risks[mineral] = 'low'
                else:
                    risks[mineral] = 'none'

        return risks


def get_phreeqc_client(
    water_type: str = 'brackish',
    database_path: Optional[str] = None
) -> PhreeqcROClient:
    """
    Factory function to get configured PHREEQC client.

    Args:
        water_type: Type of water ('brackish', 'seawater', 'industrial')
        database_path: Override database path

    Returns:
        Configured PhreeqcROClient instance
    """
    if not database_path:
        # Use recommended database for water type
        db_name = PhreeqcROClient.DATABASE_RECOMMENDATIONS.get(
            water_type,
            PhreeqcROClient.DATABASE_RECOMMENDATIONS['default']
        )
        # This will need to find the actual path
        database_path = None  # Let client find it

    return PhreeqcROClient(database_path)
