#!/usr/bin/env python3
"""
Plot AVERAGE BIT RATE vs CONSTELLATION SIZE - SENSITIVITY STUDY with OPTIMAL CROSSOVER
Shows the sensitivity study data (10, 15, 17, 18, 19, 20, 25 satellites) with a red dashed
vertical line marking the optimal crossover point at 18 satellites.

X-axis: Constellation Size (10, 15, 17, 18, 19, 20, 25)
Lines: Image sizes
Red Dashed Line: Optimal crossover at 18 satellites
"""

import pandas as pd
import matplotlib.pyplot as plt
import numpy as np
from pathlib import Path
import zipfile
import re

# Configuration - Sensitivity Study
SENSITIVITY_DIRS = [
    'results/orbit space best constellation size',
    'results/orbit space sensitivity 2'
]
CONSTELLATION_SIZES = [10, 15, 17, 18, 19, 20, 25]
IMAGE_SIZES_KB = [2799, 28000, 280000, 1024000]  # 4 main image sizes
STRATEGY = "orbit-spaced"  # Sensitivity study focuses on orbit-spaced
POLICIES = ["sticky", "fifo", "roundrobin", "random"]

# Image size display
IMAGE_SIZE_LABELS = {
    2799: '2.8 MB',
    28000: '28 MB',
    280000: '280 MB',
    1024000: '1 GB'
}

# Policy display names
POLICY_LABELS = {
    'sticky': 'Sticky',
    'fifo': 'FIFO',
    'roundrobin': 'Round Robin',
    'random': 'Random'
}

# Image size colors (4 colors, policies will use line styles)
IMAGE_SIZE_COLORS = {
    2799: '#e6194b',    # red
    28000: '#3cb44b',   # green
    280000: '#4363d8',  # blue
    1024000: '#911eb4'  # purple
}

# Policy line styles
POLICY_STYLES = {
    'sticky': '-',      # solid
    'fifo': '--',       # dashed
    'roundrobin': '-.',  # dash-dot
    'random': ':'       # dotted
}

def find_matching_directory(const_size, img_size):
    """Find the directory matching constellation and image size in sensitivity directories."""
    img_size_str = f"{img_size:05d}"
    const_size_str = f"{const_size:02d}" if const_size < 100 else str(const_size)
    pattern = f"constellation_analysis_*_{img_size_str}_{const_size_str}"
    
    for search_dir in SENSITIVITY_DIRS:
        base_dir = Path(search_dir)
        if not base_dir.exists():
            continue
        matching = list(base_dir.glob(pattern))
        if matching:
            return matching[0]
    return None

def calculate_average_bitrate(policy, const_size, img_size):
    """Calculate average bitrate during active transmission (non-zero seconds only)."""
    analysis_dir = find_matching_directory(const_size, img_size)
    if not analysis_dir:
        return None
    
    strategy_dir = analysis_dir / STRATEGY
    if not strategy_dir.exists():
        return None
        
    zip_path = strategy_dir / "simulation_logs.zip"
    if not zip_path.exists():
        return None
    
    try:
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            csv_path = f"{policy}/meas-downlink-Mbps.csv"
            if csv_path not in zip_ref.namelist():
                return None
                
            with zip_ref.open(csv_path) as f:
                bitrate_df = pd.read_csv(f)
            
            # Calculate average bitrate during non-zero seconds ONLY
            nonzero_bitrates = bitrate_df['downlink-Mbps'][bitrate_df['downlink-Mbps'] > 0]
            if len(nonzero_bitrates) == 0:
                return None
            avg_bitrate_mbps = np.mean(nonzero_bitrates)
            
            return avg_bitrate_mbps
    
    except Exception as e:
        return None

# Create output directory
output_dir = Path("constellation_analysis") / "sensitivity_bitrate_charts"
output_dir.mkdir(parents=True, exist_ok=True)

# Create the sensitivity study chart with optimal crossover line
fig, ax = plt.subplots(figsize=(16, 10))

print("\n" + "="*80)
print("AVERAGE BIT RATE vs CONSTELLATION SIZE - SENSITIVITY STUDY")
print("Orbit-Spaced Strategy - Finding Optimal Crossover")
print("All 16 combinations: 4 policies × 4 image sizes")
print("="*80)

# Collect all data to find the true optimal point
all_constellation_averages = {size: [] for size in CONSTELLATION_SIZES}

# Collect and plot data for each image size and policy combination (16 lines total)
for img_size in IMAGE_SIZES_KB:
    print(f"\n{IMAGE_SIZE_LABELS[img_size]}:")
    print("-" * 60)
    
    for policy in POLICIES:
        bitrates = []
        
        for const_size in CONSTELLATION_SIZES:
            result = calculate_average_bitrate(policy, const_size, img_size)
            if result:
                bitrates.append(result)
                all_constellation_averages[const_size].append(result)
            else:
                bitrates.append(None)
        
        # Plot line for this image size + policy combination
        valid_indices = [i for i, b in enumerate(bitrates) if b is not None]
        valid_const_sizes = [CONSTELLATION_SIZES[i] for i in valid_indices]
        valid_bitrates = [bitrates[i] for i in valid_indices]
        
        if valid_bitrates:
            label = f'{IMAGE_SIZE_LABELS[img_size]} - {POLICY_LABELS[policy]}'
            ax.plot(valid_const_sizes, valid_bitrates, 
                    marker='o', markersize=6,
                    linewidth=2,
                    linestyle=POLICY_STYLES[policy],
                    color=IMAGE_SIZE_COLORS[img_size],
                    label=label)
            
            print(f"  {POLICY_LABELS[policy]:12s}: {', '.join([f'{b:.2f}' if b else 'N/A' for b in bitrates])} Mbps")

# Calculate global average and find optimal
constellation_avg_bitrates = {size: np.mean(rates) for size, rates in all_constellation_averages.items() if rates}
optimal_constellation_size = max(constellation_avg_bitrates.items(), key=lambda x: x[1])[0]
optimal_avg_bitrate = constellation_avg_bitrates[optimal_constellation_size]

print("\n" + "="*80)
print("OPTIMAL CONSTELLATION SIZE ANALYSIS")
print("="*80)
print("\nGLOBAL AVERAGE (All 16 combinations):")
for size in CONSTELLATION_SIZES:
    if size in constellation_avg_bitrates:
        avg = constellation_avg_bitrates[size]
        marker = " ← OPTIMAL" if size == optimal_constellation_size else ""
        print(f"{size:3d} satellites: {avg:.2f} Mbps{marker}")
print("="*80)

# Add RED DASHED VERTICAL LINE at the global optimal crossover point
ax.axvline(x=optimal_constellation_size, color='red', linestyle='--', linewidth=3, 
           label=f'Optimal ({optimal_constellation_size} sats, {optimal_avg_bitrate:.2f} Mbps)', zorder=10)

# Add annotation for the optimal point (position for zoomed view)
ax.annotate(f'Optimal\n{optimal_constellation_size} Satellites\n{optimal_avg_bitrate:.2f} Mbps', 
            xy=(optimal_constellation_size, 119),
            xytext=(optimal_constellation_size, 119),
            ha='center', va='top',
            fontsize=11, fontweight='bold',
            color='red',
            bbox=dict(boxstyle='round,pad=0.5', facecolor='white', edgecolor='red', linewidth=2))

# Formatting
ax.set_xlabel('Constellation Size (Number of Satellites)', fontsize=14, fontweight='bold')
ax.set_ylabel('Average Bit Rate (Mbps)', fontsize=14, fontweight='bold')
ax.set_title(f'Average Bit Rate vs Constellation Size - Orbit-Spaced Sensitivity Study\nOptimal Crossover at {optimal_constellation_size} Satellites', 
             fontsize=16, fontweight='bold', pad=20)
ax.grid(True, alpha=0.3, linestyle='--')
ax.legend(loc='center left', bbox_to_anchor=(1.02, 0.5), fontsize=8.5, framealpha=0.9, ncol=1)

# Set x-axis to show all constellation sizes
ax.set_xticks(CONSTELLATION_SIZES)
ax.set_xticklabels(CONSTELLATION_SIZES)

# Zoom in around 100 Mbps to see differences clearly
ax.set_ylim(100, 120)

plt.tight_layout()

# Save
output_file = output_dir / 'average_bitrate_sensitivity_optimal_18sats.png'
plt.savefig(output_file, dpi=150, bbox_inches='tight')
print(f"\n✅ Saved: {output_file}")

plt.close()

print("\n" + "="*80)
print("COMPLETE")
print("="*80)
