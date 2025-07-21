"""
Test the accumulation factor calculation
"""

# Configuration values from test
feed_tds = 5000  # ppm
recycle_ratio = 0.5  # 50% of fresh feed
system_recovery = 0.85  # 85% overall recovery
avg_rejection = 0.95  # 95% average rejection

# Calculate accumulation using the formula
accumulation_factor = (
    recycle_ratio * feed_tds * avg_rejection / (1 - system_recovery) + feed_tds
) / (1 + recycle_ratio)

print(f"Feed TDS: {feed_tds} ppm")
print(f"Recycle ratio: {recycle_ratio} (50%)")
print(f"System recovery: {system_recovery} (85%)")
print(f"Average rejection: {avg_rejection} (95%)")
print(f"\nCalculation breakdown:")
print(f"  Numerator term 1: {recycle_ratio} * {feed_tds} * {avg_rejection} / (1 - {system_recovery}) = {recycle_ratio * feed_tds * avg_rejection / (1 - system_recovery):.0f}")
print(f"  Numerator term 2: {feed_tds}")
print(f"  Total numerator: {recycle_ratio * feed_tds * avg_rejection / (1 - system_recovery) + feed_tds:.0f}")
print(f"  Denominator: 1 + {recycle_ratio} = {1 + recycle_ratio}")
print(f"\nEffective feed TDS: {accumulation_factor:.0f} ppm")
print(f"Accumulation factor: {accumulation_factor/feed_tds:.2f}x")

# Check if this matches what the error reported
if accumulation_factor > 100000:
    print(f"\nWARNING: Calculated TDS ({accumulation_factor:.0f} ppm) seems too high!")
    print("This might be causing the initialization failure.")