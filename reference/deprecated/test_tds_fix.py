#!/usr/bin/env python3
"""
Test script to verify the TDS calculation fix.
"""

import sys
sys.path.insert(0, '.')

from utils.ro_initialization import calculate_concentrate_tds, calculate_required_pressure

def test_tds_calculation():
    """Test that TDS calculation produces realistic values."""
    print("Testing TDS calculation with corrected formula...")
    
    # Test case from user: 2000 ppm feed, 75% system recovery in 2 stages
    feed_tds = 2000  # ppm
    stage1_recovery = 0.5518
    stage2_recovery = 0.4128
    salt_passage = 0.015  # 1.5%
    
    # Stage 1 calculation
    stage1_conc_tds = calculate_concentrate_tds(feed_tds, stage1_recovery, salt_passage)
    print(f"\nStage 1:")
    print(f"  Feed TDS: {feed_tds:.0f} ppm")
    print(f"  Recovery: {stage1_recovery:.1%}")
    print(f"  Salt passage: {salt_passage:.1%}")
    print(f"  Concentrate TDS: {stage1_conc_tds:.0f} ppm")
    
    # Stage 2 calculation (using stage 1 concentrate as feed)
    stage2_conc_tds = calculate_concentrate_tds(stage1_conc_tds, stage2_recovery, salt_passage)
    print(f"\nStage 2:")
    print(f"  Feed TDS: {stage1_conc_tds:.0f} ppm")
    print(f"  Recovery: {stage2_recovery:.1%}")
    print(f"  Salt passage: {salt_passage:.1%}")
    print(f"  Concentrate TDS: {stage2_conc_tds:.0f} ppm")
    
    # Calculate overall system recovery
    overall_recovery = 1 - (1 - stage1_recovery) * (1 - stage2_recovery)
    print(f"\nOverall system recovery: {overall_recovery:.1%}")
    
    # Expected concentrate TDS for 75% recovery
    expected_conc_tds = feed_tds * (1 - salt_passage * overall_recovery) / (1 - overall_recovery)
    print(f"Expected final concentrate TDS: {expected_conc_tds:.0f} ppm")
    
    # Test pressure calculation
    print("\n" + "="*50)
    print("Testing pressure calculation...")
    
    for i, (tds, recovery) in enumerate([(feed_tds, stage1_recovery), 
                                         (stage1_conc_tds, stage2_recovery)], 1):
        pressure = calculate_required_pressure(
            tds, 
            recovery,
            salt_passage=salt_passage
        )
        print(f"\nStage {i} required pressure: {pressure/1e5:.1f} bar")
    
    # Verify results are reasonable
    assert stage2_conc_tds < 10000, f"Final concentrate TDS ({stage2_conc_tds:.0f} ppm) exceeds 10,000 ppm!"
    assert stage2_conc_tds > 6000, f"Final concentrate TDS ({stage2_conc_tds:.0f} ppm) seems too low!"
    
    print("\n✓ All tests passed! TDS calculations are now realistic.")

if __name__ == "__main__":
    test_tds_calculation()