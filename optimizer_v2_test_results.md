# Optimizer Configuration Testing with V2 Simulator

## Test Parameters
- **Feed Flow**: 150 m³/h
- **Target Recovery**: 75%
- **Feed Salinity**: 4,000 ppm (brackish water)
- **Feed Temperature**: 25°C
- **Membrane Type**: Brackish (BW30-400)

## Ion Composition
| Ion | Concentration (mg/L) |
|-----|---------------------|
| Na+ | 1,572 |
| Cl- | 2,428 |

---

## Configuration 1: Two-Stage (17:8) without Recycle

### Array Configuration
- **Stage 1**: 17 vessels, 4,422 m² membrane area
- **Stage 2**: 8 vessels, 2,081 m² membrane area
- **Total Vessels**: 25
- **Recycle**: None

### Performance Results
| Metric | Value |
|--------|--------|
| **LCOW** | $0.187/m³ |
| **Specific Energy** | 0.83 kWh/m³ |
| **System Recovery** | 74.6% |
| **Permeate Flow** | 111.9 m³/h |
| **Permeate TDS** | 17.7 mg/L |
| **Feed Pressure** | 18.8 bar |
| **Stage 2 Pressure** | 17.5 bar |
| **Total Pump Power** | 93.1 kW |

### Economic Summary
| Component | Value |
|-----------|--------|
| **Total Capital Cost** | $470,638 |
| **Annual Operating Cost** | $88,636/year |
| **Pump Capital** | $19,485 |
| **Membrane Capital** | $390,000 |
| **Electricity Cost** | $57,316/year |
| **Membrane Replacement** | $39,000/year |
| **Antiscalant Cost** | $5,914/year |

---

## Configuration 2: Single-Stage (23) with Recycle

### Array Configuration
- **Stage 1**: 23 vessels, 5,980 m² membrane area
- **Total Vessels**: 23
- **Recycle Ratio**: 0.90 (high recycle)

### Performance Results
| Metric | Value |
|--------|--------|
| **LCOW** | $0.219/m³ |
| **Specific Energy** | 1.20 kWh/m³ |
| **System Recovery** | 66.3% |
| **Permeate Flow** | 99.5 m³/h |
| **Permeate TDS** | 18.4 mg/L |
| **Feed Pressure** | 18.8 bar |
| **Total Pump Power** | 119.7 kW |

### Economic Summary
| Component | Value |
|-----------|--------|
| **Total Capital Cost** | $461,223 |
| **Annual Operating Cost** | $90,882/year |
| **Pump Capital** | $10,070 |
| **Membrane Capital** | $390,000 |
| **Electricity Cost** | $73,683/year |
| **Membrane Replacement** | $39,000/year |
| **Antiscalant Cost** | $11,827/year |

### Note on Performance
Despite 90% recycle, this configuration achieved lower recovery (66.3%) than the target due to single-stage limitations and high concentrate recirculation.

---

## Configuration 3: Two-Stage (18:8) with Small Recycle

### Array Configuration
- **Stage 1**: 18 vessels, 4,680 m² membrane area
- **Stage 2**: 8 vessels, 2,081 m² membrane area
- **Total Vessels**: 26
- **Recycle Ratio**: 0.14 (small recycle)

### Performance Results
| Metric | Value |
|--------|--------|
| **LCOW** | $0.209/m³ |
| **Specific Energy** | 1.29 kWh/m³ |
| **System Recovery** | 85.3% |
| **Permeate Flow** | 127.9 m³/h |
| **Permeate TDS** | 18.0 mg/L |
| **Feed Pressure** | 20.7 bar |
| **Stage 2 Pressure** | 19.8 bar |
| **Total Pump Power** | 164.4 kW |

### Economic Summary
| Component | Value |
|-----------|--------|
| **Total Capital Cost** | $593,327 |
| **Annual Operating Cost** | $120,618/year |
| **Pump Capital** | $32,174 |
| **Membrane Capital** | $500,000 |
| **Electricity Cost** | $101,201/year |
| **Membrane Replacement** | $50,000/year |
| **Antiscalant Cost** | $6,755/year |

### Note on Performance
This configuration exceeded the 75% target recovery, achieving 85.3% with only 14% recycle.

---

## Comparative Analysis

| Metric | Config 1 (17:8) | Config 2 (23+R) | Config 3 (18:8+R) |
|--------|-----------------|-----------------|-------------------|
| **LCOW ($/m³)** | **0.187** (best) | 0.219 | 0.209 |
| **Specific Energy (kWh/m³)** | **0.83** (best) | 1.20 | 1.29 |
| **Recovery (%)** | 74.6 | 66.3 | **85.3** (best) |
| **Permeate Flow (m³/h)** | 111.9 | 99.5 | **127.9** (best) |
| **Capital Cost ($)** | 470,638 | **461,223** (best) | 593,327 |
| **Operating Cost ($/yr)** | **88,636** (best) | 90,882 | 120,618 |
| **Vessels** | 25 | **23** (fewest) | 26 |
| **Recycle** | None | 90% | 14% |

## Key Findings

1. **Configuration 1** (two-stage without recycle) provides the best economics:
   - Lowest LCOW at $0.187/m³
   - Lowest specific energy at 0.83 kWh/m³
   - Meets target recovery (74.6% vs 75% target)

2. **Configuration 2** (single-stage with high recycle) underperforms:
   - Despite 90% recycle, only achieves 66.3% recovery
   - Higher energy consumption due to recirculation
   - Single-stage limitation prevents reaching target recovery

3. **Configuration 3** (two-stage with small recycle) exceeds recovery target:
   - Achieves highest recovery at 85.3%
   - Higher capital and operating costs
   - Small recycle (14%) helps boost recovery beyond target

## Recommendation

**Use Configuration 1** (17 stage-1 vessels, 8 stage-2 vessels, no recycle) for this application:
- Best economic performance (LCOW = $0.187/m³)
- Lowest energy consumption (0.83 kWh/m³)
- Meets recovery target without complexity of recycle
- Simplest operation and maintenance

## Technical Notes

1. All configurations used proper membrane areas from optimizer:
   - Critical for solver convergence
   - Areas calculated based on flux and recovery targets

2. V2 simulator advantages demonstrated:
   - WaterTAPCostingDetailed framework
   - Chemical consumption tracking
   - Robust solver initialization
   - Comprehensive economic breakdown

3. Energy values are realistic for brackish water RO:
   - 0.83-1.29 kWh/m³ range is industry-typical
   - No ERD needed for brackish water applications