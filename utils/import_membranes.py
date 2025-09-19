"""
Import membrane specifications from CSV and generate catalog with ion-specific B values.

This script:
1. Parses membrane_properties.csv from FilmTec
2. Filters out obsolete models and 4" diameter elements
3. Calculates A_w and B_s permeability coefficients
4. Generates ion-specific B values using diffusivity ratios
5. Creates a comprehensive membrane catalog
"""

import csv
import re
import yaml
import logging
import numpy as np
from pathlib import Path
from datetime import datetime
from typing import Dict, Optional, Tuple, List
import sys

# Add parent directory to path for imports
sys.path.append(str(Path(__file__).parent.parent))

from utils.membrane_parameter_fitting import calculate_membrane_permeability_from_spec

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Reference diffusivities at 25°C (m²/s) from literature
DIFFUSIVITIES = {
    'Na_+': 1.33e-9,
    'Cl_-': 2.03e-9,
    'Ca_2+': 0.79e-9,
    'Mg_2+': 0.71e-9,
    'K_+': 1.96e-9,
    'Sr_2+': 0.70e-9,
    'SO4_2-': 1.06e-9,
    'HCO3_-': 1.18e-9,
    'SiO3_2-': 0.95e-9,
    'Br_-': 2.01e-9,
    'F_-': 1.46e-9,
}

# Ion charges for Donnan exclusion calculation
ION_CHARGES = {
    'Na_+': 1, 'Cl_-': -1, 'Ca_2+': 2, 'Mg_2+': 2,
    'K_+': 1, 'Sr_2+': 2, 'SO4_2-': -2, 'HCO3_-': -1,
    'SiO3_2-': -2, 'Br_-': -1, 'F_-': -1,
}

# Hydrated radii (m) for steric effects
HYDRATED_RADII = {
    'Na_+': 1.84e-10,
    'Cl_-': 1.21e-10,
    'Ca_2+': 3.09e-10,
    'Mg_2+': 3.47e-10,
    'K_+': 1.25e-10,
    'Sr_2+': 3.09e-10,
    'SO4_2-': 2.30e-10,
    'HCO3_-': 1.56e-10,
    'SiO3_2-': 2.50e-10,
    'Br_-': 1.18e-10,
    'F_-': 1.66e-10,
}

# Activation energies by membrane family (J/mol)
ACTIVATION_ENERGIES = {
    'seawater': {'A_w': 23000, 'B_s': 15000},
    'brackish': {'A_w': 20000, 'B_s': 13000},
    'ultra_low_energy': {'A_w': 18000, 'B_s': 12000},
    'high_rejection': {'A_w': 21000, 'B_s': 14000},
    'nanofiltration': {'A_w': 17000, 'B_s': 11000},
    'fouling_resistant': {'A_w': 20000, 'B_s': 13000},
}

# Element dimensions (m)
ELEMENT_DIMENSIONS = {
    '8040': {'diameter': 0.2032, 'length': 1.016},  # 8" x 40"
    '8020': {'diameter': 0.2032, 'length': 0.508},  # 8" x 20"
    '4040': {'diameter': 0.1016, 'length': 1.016},  # 4" x 40"
    '4021': {'diameter': 0.1016, 'length': 0.533},  # 4" x 21"
}


def parse_csv_value(value: str) -> Tuple[float, float]:
    """
    Parse values like '11,500 (43.5)' or '400 (37.2)'
    Returns: (imperial_value, metric_value)
    """
    # Remove commas and clean up
    value = value.replace(',', '').strip()

    # Extract main number
    main_match = re.match(r'([\d.]+)', value)
    main_val = float(main_match.group(1)) if main_match else 0.0

    # Extract parenthetical value
    paren_match = re.search(r'\(([\d.]+)\)', value)
    paren_val = float(paren_match.group(1)) if paren_match else 0.0

    return main_val, paren_val


def parse_membrane_model(model_name: str) -> Dict:
    """Extract structured data from membrane model name."""

    # Clean up name
    clean_name = re.sub(r'\s+', '_', model_name.strip())
    clean_name = re.sub(r'[^\w\-/]', '', clean_name)

    # Extract spacer thickness from /XX suffix
    spacer_match = re.search(r'/(\d+)', model_name)
    spacer_mil = int(spacer_match.group(1)) if spacer_match else None

    # If no explicit spacer, infer from model patterns
    if not spacer_mil:
        if 'XFR' in model_name or 'FR' in model_name:
            spacer_mil = 34  # Fouling resistant typically 34 mil
        elif 'LD' in model_name:
            spacer_mil = 46  # Low differential typically 46 mil
        elif 'NF' in model_name:
            spacer_mil = 20  # NF typically thinner
        else:
            spacer_mil = 31  # Standard default

    # Extract nominal area from model number
    area_match = re.search(r'-(\d{3})', model_name)
    nominal_area = int(area_match.group(1)) if area_match else 400

    # Determine element size
    if nominal_area < 100:
        element_type = '4040'  # 4" diameter - SKIP THESE
    elif nominal_area < 300:
        element_type = '4021'  # 4" x 21" - SKIP THESE
    elif nominal_area < 400:
        element_type = '8020'  # 8" x 20"
    else:
        element_type = '8040'  # 8" x 40" standard

    # Determine membrane family
    if any(x in model_name for x in ['SW30', 'Seamaxx']):
        family = 'seawater'
    elif 'NF' in model_name:
        family = 'nanofiltration'
    elif any(x in model_name for x in ['XLE', 'ULE']):
        family = 'ultra_low_energy'
    elif any(x in model_name for x in ['HR', 'XHR']):
        family = 'high_rejection'
    elif any(x in model_name for x in ['FR', 'XFR', 'CR', 'Fortilife']):
        family = 'fouling_resistant'
    elif any(x in model_name for x in ['ECO', 'LE', 'PRO']):
        family = 'brackish'
    else:
        family = 'brackish'  # Default

    # Determine spacer profile key
    spacer_profile = f'filmtec_{spacer_mil}mil'

    # Special cases
    if spacer_mil == 20:
        spacer_profile = 'nf_20mil'
    elif spacer_mil not in [28, 31, 34, 46, 65]:
        spacer_profile = 'default'  # Fallback for unusual spacers

    return {
        'clean_name': clean_name,
        'spacer_mil': spacer_mil,
        'element_type': element_type,
        'family': family,
        'spacer_profile': spacer_profile,
        'nominal_area': nominal_area
    }


def calculate_ion_specific_B_values(
    base_B_NaCl: float,
    membrane_family: str,
    test_solute: str = 'NaCl'
) -> Dict[str, float]:
    """
    Calculate ion-specific B values using diffusivity ratios and charge effects.
    Based on Solution-Diffusion model: B_i ∝ D_i * exp(-z_i * ΔΨ)
    """

    # Base case: NaCl average diffusivity
    D_NaCl_avg = (DIFFUSIVITIES['Na_+'] + DIFFUSIVITIES['Cl_-']) / 2

    # Membrane charge density factor (empirical, family-dependent)
    charge_factors = {
        'seawater': 0.8,          # Tightest, strongest Donnan exclusion
        'high_rejection': 0.7,    # High rejection, strong exclusion
        'brackish': 0.5,          # Standard brackish
        'ultra_low_energy': 0.4,  # Looser, weaker exclusion
        'fouling_resistant': 0.5, # Similar to brackish
        'nanofiltration': 0.3,    # Weakest charge exclusion
    }
    charge_factor = charge_factors.get(membrane_family, 0.5)

    B_comp = {}

    for ion in DIFFUSIVITIES.keys():
        # Diffusivity ratio (primary transport mechanism)
        D_ratio = DIFFUSIVITIES[ion] / D_NaCl_avg

        # Charge effect (Donnan exclusion)
        charge = abs(ION_CHARGES[ion])
        if charge > 1:
            # Stronger exclusion for multivalent ions
            charge_penalty = np.exp(-charge_factor * charge * 1.5)
        else:
            # Weaker effect for monovalent
            charge_penalty = np.exp(-charge_factor * charge)

        # Steric hindrance based on hydrated radius
        r_ion = HYDRATED_RADII.get(ion, 2e-10)
        r_NaCl_avg = (HYDRATED_RADII['Na_+'] + HYDRATED_RADII['Cl_-']) / 2

        if r_ion > r_NaCl_avg:
            # Larger ions face more hindrance
            steric_factor = (r_NaCl_avg / r_ion) ** 2
        else:
            # Smaller ions pass more easily
            steric_factor = 1.0 + 0.2 * (1 - r_ion / r_NaCl_avg)

        # Combined B value
        B_comp[ion] = base_B_NaCl * D_ratio * charge_penalty * steric_factor

    # Adjust if test was with MgSO4 instead of NaCl
    if test_solute == 'MgSO4':
        # Base B represents divalent rejection, scale up monovalent
        scaling_factors = {
            'seawater': 2.5,
            'high_rejection': 2.8,
            'brackish': 3.0,
            'ultra_low_energy': 3.5,
            'nanofiltration': 4.0,
        }
        scale = scaling_factors.get(membrane_family, 3.0)

        for ion in ['Na_+', 'Cl_-', 'K_+', 'Br_-', 'F_-']:
            if ion in B_comp:
                B_comp[ion] *= scale

    return B_comp


def import_membrane_row(row: List[str], row_num: int) -> Optional[Dict]:
    """Import a single membrane from CSV row."""

    try:
        # Parse CSV columns
        model_name = row[0].strip()

        # Skip if obsolete or discontinued
        if any(x in model_name.lower() for x in ['obsolete', 'discontinued', 'to be discontinued']):
            logger.info(f"Skipping obsolete model: {model_name}")
            return None

        # Parse values
        area_ft2, area_m2 = parse_csv_value(row[1])
        pressure_psi, pressure_bar = parse_csv_value(row[2])
        flow_gpd, flow_m3_day = parse_csv_value(row[3])
        rejection = float(row[4]) / 100  # Convert percentage to fraction
        feed_ppm = float(row[5])
        test_solute = row[6].strip()
        recovery = float(row[7]) / 100 if row[7] else 0.15

        # Skip 4" diameter elements
        if area_ft2 < 100:
            logger.info(f"Skipping 4-inch element: {model_name}")
            return None

        # Parse model details
        parsed = parse_membrane_model(model_name)

        # Skip 4" elements based on parsed type
        if parsed['element_type'] in ['4040', '4021']:
            logger.info(f"Skipping 4-inch element: {model_name}")
            return None

        # Determine if seawater or brackish based on test salinity
        if feed_ppm >= 30000:
            membrane_class = 'seawater'
        elif feed_ppm >= 10000:
            membrane_class = 'seawater'  # High brackish, use SW parameters
        else:
            membrane_class = 'brackish'

        # Override with parsed family if more specific
        if parsed['family'] in ['seawater', 'nanofiltration']:
            membrane_class = parsed['family']

        logger.info(f"Processing {model_name} (Row {row_num})")

        # Calculate A_w and B_s using existing function
        try:
            params = calculate_membrane_permeability_from_spec(
                permeate_flow_m3_day=flow_m3_day,
                salt_rejection=rejection,
                active_area_m2=area_m2,
                test_pressure_bar=pressure_bar,
                test_temperature_c=25.0,
                feed_concentration_ppm=feed_ppm,
                recovery=recovery
            )
        except Exception as e:
            logger.warning(f"Failed to fit parameters for {model_name}: {e}")
            # Use fallback values based on family
            if membrane_class == 'seawater':
                params = {'A_w': 3.0e-12, 'B_s': 1.5e-8}
            else:
                params = {'A_w': 9.0e-12, 'B_s': 5.0e-8}

        # Generate ion-specific B values
        B_comp = calculate_ion_specific_B_values(
            base_B_NaCl=params['B_s'],
            membrane_family=parsed['family'],
            test_solute=test_solute
        )

        # Determine operating limits based on type
        if membrane_class == 'seawater':
            max_pressure = 8270000  # 1200 psi
            max_temp = 45
            pH_range = [3, 11]
        elif parsed['family'] == 'fouling_resistant':
            max_pressure = 4137000  # 600 psi
            max_temp = 45
            pH_range = [1, 13]  # Wider pH tolerance
        else:
            max_pressure = 4137000  # 600 psi
            max_temp = 45
            pH_range = [2, 11]

        # Create catalog entry
        entry = {
            'family': parsed['family'],
            'A_w': float(params['A_w']),
            'B_comp': {k: float(v) for k, v in B_comp.items()},
            'spacer_profile': parsed['spacer_profile'],
            'temperature_corrections': {
                'A_w_activation_energy': ACTIVATION_ENERGIES[parsed['family']]['A_w'],
                'B_activation_energy': ACTIVATION_ENERGIES[parsed['family']]['B_s'],
                'reference_temperature': 298.15  # K (25°C)
            },
            'physical': {
                'active_area_m2': float(area_m2),
                'element_type': parsed['element_type'],
                'elements_per_vessel': 7 if parsed['element_type'] == '8040' else 6
            },
            'limits': {
                'max_pressure_pa': int(max_pressure),
                'max_temperature_c': int(max_temp),
                'pH_range': pH_range
            },
            'test_conditions': {
                'pressure_bar': float(pressure_bar),
                'temperature_c': 25.0,
                'feed_ppm': float(feed_ppm),
                'recovery': float(recovery),
                'rejection': float(rejection),
                'test_solute': test_solute,
                'permeate_flow_m3_day': float(flow_m3_day)
            },
            'metadata': {
                'raw_name': model_name,
                'import_date': datetime.now().isoformat(),
                'row_number': row_num,
                'assumptions': [
                    'Diffusivity-based ion B ratios',
                    f'Spacer profile: {parsed["spacer_profile"]}',
                    f'Family: {parsed["family"]}'
                ]
            }
        }

        return parsed['clean_name'], entry

    except Exception as e:
        logger.error(f"Error processing row {row_num} ({row[0]}): {e}")
        return None


def main():
    """Main import function."""

    # Paths
    csv_path = Path(__file__).parent.parent / 'membrane_properties.csv'
    catalog_path = Path(__file__).parent.parent / 'config' / 'membrane_catalog.yaml'

    if not csv_path.exists():
        logger.error(f"CSV file not found: {csv_path}")
        return

    # Create catalog directory if needed
    catalog_path.parent.mkdir(exist_ok=True)

    # Load existing catalog if present
    if catalog_path.exists():
        with open(catalog_path, 'r') as f:
            catalog = yaml.safe_load(f) or {}
    else:
        catalog = {}

    if 'membrane_catalog' not in catalog:
        catalog['membrane_catalog'] = {}

    # Process CSV
    imported_count = 0
    skipped_count = 0
    error_count = 0

    with open(csv_path, 'r', encoding='utf-8-sig') as f:
        reader = csv.reader(f)

        for row_num, row in enumerate(reader, start=1):
            # Skip empty rows or header-like rows
            if not row or not row[0] or 'model' in row[0].lower():
                continue

            # Skip if not enough columns
            if len(row) < 8:
                logger.warning(f"Skipping row {row_num}: insufficient columns")
                continue

            result = import_membrane_row(row, row_num)

            if result:
                model_key, entry = result
                catalog['membrane_catalog'][model_key] = entry
                imported_count += 1
                logger.info(f"Imported: {model_key}")
            else:
                skipped_count += 1

    # Add header comment
    catalog_with_header = f"""# RO Membrane Catalog
# Generated from FilmTec membrane specifications
# Last updated: {datetime.now().isoformat()}
# Total membranes: {len(catalog['membrane_catalog'])}

""" + yaml.dump(catalog, sort_keys=False, default_flow_style=False)

    # Save catalog
    with open(catalog_path, 'w') as f:
        f.write(catalog_with_header)

    logger.info(f"\nImport complete:")
    logger.info(f"  Imported: {imported_count} membranes")
    logger.info(f"  Skipped: {skipped_count} (obsolete or 4-inch)")
    logger.info(f"  Errors: {error_count}")
    logger.info(f"  Catalog saved to: {catalog_path}")

    # Print sample entries
    if catalog['membrane_catalog']:
        print("\nSample catalog entries:")
        for i, (key, val) in enumerate(list(catalog['membrane_catalog'].items())[:3]):
            print(f"\n{key}:")
            print(f"  Family: {val['family']}")
            print(f"  A_w: {val['A_w']:.2e} m/s/Pa")
            print(f"  B_Na+: {val['B_comp']['Na_+']:.2e} m/s")
            print(f"  B_Ca2+: {val['B_comp']['Ca_2+']:.2e} m/s")
            print(f"  Area: {val['physical']['active_area_m2']} m²")
            print(f"  Spacer: {val['spacer_profile']}")


if __name__ == '__main__':
    main()