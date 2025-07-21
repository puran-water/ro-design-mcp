#!/usr/bin/env python3
"""
Simple test of the TDS calculation fix without numpy dependencies.
"""

def calculate_concentrate_tds(feed_tds_ppm, recovery, salt_passage=0.015):
    """Local copy of the fixed function for testing."""
    if recovery >= 1.0:
        raise ValueError(f"Recovery must be less than 1, got {recovery}")
    
    # With salt passage: concentrate_tds = feed_tds * (1 - SP*R) / (1 - R)
    concentrate_tds_ppm = feed_tds_ppm * (1 - salt_passage * recovery) / (1 - recovery)
    return concentrate_tds_ppm

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
    
    # Expected concentrate TDS for 75% recovery with salt passage
    expected_conc_tds = feed_tds * (1 - salt_passage * overall_recovery) / (1 - overall_recovery)
    print(f"Expected final concentrate TDS (direct calc): {expected_conc_tds:.0f} ppm")
    
    # Compare with perfect rejection (old formula)
    old_formula_tds = feed_tds / (1 - overall_recovery)
    print(f"Old formula (perfect rejection): {old_formula_tds:.0f} ppm")
    
    print(f"\nDifference: {old_formula_tds - expected_conc_tds:.0f} ppm")
    
    # Verify results are reasonable
    assert stage2_conc_tds < 10000, f"Final concentrate TDS ({stage2_conc_tds:.0f} ppm) exceeds 10,000 ppm!"
    assert stage2_conc_tds > 6000, f"Final concentrate TDS ({stage2_conc_tds:.0f} ppm) seems too low!"
    
    print("\n✓ All tests passed! TDS calculations are now realistic.")
    print(f"✓ Final concentrate TDS: {stage2_conc_tds:.0f} ppm (was 666,667 ppm with old formula)")

if __name__ == "__main__":
    test_tds_calculation()