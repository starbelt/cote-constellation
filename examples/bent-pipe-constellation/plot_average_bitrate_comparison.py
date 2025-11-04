#!/usr/bin/env python3
"""
Plot AVERAGE BIT RATE (without activity time factor) vs image size for ALL constellation sizes.
This shows the quality of the downlink when data is actually being transmitted.
"""

import pandas as pd
import matplotlib.pyplot as plt
import numpy as np
from pathlib import Path
import zipfile
import re

# Configuration
BASE_DIR = Path("results/base results 2")
CONSTELLATION_SIZES = [1, 25, 50, 100, 200]
IMAGE_SIZES_KB = [27, 279, 2799, 28000, 280000, 1024000]
STRATEGIES = ["close-spaced", "frame-spaced", "orbit-spaced", "close-orbit-spaced"]
POLICIES = ["sticky", "fifo", "roundrobin", "random"]

# Strategy display names and colors
STRATEGY_DISPLAY = {
    "close-spaced": "Close-Spaced",
    "frame-spaced": "Frame-Spaced",
    "orbit-spaced": "Orbit-Spaced",
    "close-orbit-spaced": "Close-Orbit-Spaced"
}

STRATEGY_COLORS = {
    "close-spaced": '#d62728',      # red
    "frame-spaced": '#ff7f0e',      # orange
    "orbit-spaced": '#2ca02c',      # green
    "close-orbit-spaced": '#1f77b4' # blue
}

# Line styles for constellation sizes
CONSTELLATION_STYLES = {
    1: ':',      # dotted
    25: '--',    # dashed
    50: '-.',    # dash-dot
    100: '-',    # solid
    200: '-'     # solid (thicker)
}

CONSTELLATION_WIDTHS = {
    1: 1.5,
    25: 1.5,
    50: 1.5,
    100: 2.0,
    200: 2.5
}

def find_matching_directory(base_dir, const_size, img_size):
    """Find the directory matching constellation and image size."""
    img_size_str = f"{img_size:05d}"
    const_size_str = f"{const_size:02d}" if const_size < 100 else str(const_size)
    pattern = f"constellation_analysis_*_{img_size_str}_{const_size_str}"
    matching = list(base_dir.glob(pattern))
    if matching:
        return matching[0]
    return None

def calculate_average_bitrate(strategy, policy, const_size, img_size):
    """Calculate average bitrate during active transmission (non-zero seconds only)."""
    analysis_dir = find_matching_directory(BASE_DIR, const_size, img_size)
    if not analysis_dir:
        return None
    
    strategy_dir = analysis_dir / strategy
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
output_dir = Path("bitrate_charts")
output_dir.mkdir(exist_ok=True)

# Create the comprehensive comparison chart
fig, ax = plt.subplots(figsize=(20, 12))

print("\n" + "="*80)
print("AVERAGE BIT RATE COMPARISON (During Active Transmission)")
print("="*80)

# Collect and plot data for each strategy and constellation size
for strategy in STRATEGIES:
    print(f"\n{STRATEGY_DISPLAY[strategy]}:")
    print("-" * 60)
    
    for const_size in CONSTELLATION_SIZES:
        bitrates = []
        
        for img_size in IMAGE_SIZES_KB:
            # Average across all policies for this configuration
            policy_bitrates = []
            for policy in POLICIES:
                result = calculate_average_bitrate(strategy, policy, const_size, img_size)
                if result:
                    policy_bitrates.append(result)
            
            if policy_bitrates:
                avg_bitrate = np.mean(policy_bitrates)
                bitrates.append(avg_bitrate)
            else:
                bitrates.append(None)
        
        # Plot line for this strategy+constellation combination
        valid_indices = [i for i, b in enumerate(bitrates) if b is not None]
        valid_image_sizes = [IMAGE_SIZES_KB[i] for i in valid_indices]
        valid_bitrates = [bitrates[i] for i in valid_indices]
        
        if valid_bitrates:
            label = f'{STRATEGY_DISPLAY[strategy]} ({const_size} sats)'
            ax.plot(valid_image_sizes, valid_bitrates, 
                   marker='o', markersize=6, 
                   linewidth=CONSTELLATION_WIDTHS[const_size],
                   color=STRATEGY_COLORS[strategy],
                   linestyle=CONSTELLATION_STYLES[const_size],
                   label=label,
                   alpha=0.8)
            
            print(f"  {const_size:3d} sats: {' → '.join([f'{b:6.2f}' for b in valid_bitrates])} Mbps")

# Formatting
ax.set_xscale('log')
ax.set_xlabel('Image Size', fontsize=16, fontweight='bold')
ax.set_ylabel('Average Downlink Bit Rate (Mbps)\nDuring Active Transmission', fontsize=16, fontweight='bold')
ax.set_title('Average Downlink Bit Rate Comparison\nAll Strategies × All Constellation Sizes\n(Measured only when actively transmitting data)',
            fontsize=18, fontweight='bold', pad=20)
ax.grid(True, alpha=0.3, linestyle='--')

# Create custom legend
legend_handles = []
legend_labels = []

for strategy in STRATEGIES:
    for const_size in CONSTELLATION_SIZES:
        label = f'{STRATEGY_DISPLAY[strategy]} ({const_size} sats)'
        line = plt.Line2D([0], [0], 
                         color=STRATEGY_COLORS[strategy],
                         linestyle=CONSTELLATION_STYLES[const_size],
                         linewidth=CONSTELLATION_WIDTHS[const_size],
                         marker='o', markersize=6)
        legend_handles.append(line)
        legend_labels.append(label)

ax.legend(legend_handles, legend_labels, 
         fontsize=10, loc='lower right', ncol=2, framealpha=0.95)

# Format x-axis labels
ax.set_xticks(IMAGE_SIZES_KB)
ax.set_xticklabels([f'{size//1000}MB' if size >= 1000 else f'{size}KB' 
                    for size in IMAGE_SIZES_KB], rotation=45, ha='right')

plt.tight_layout()

# Save figure
output_path = output_dir / 'average_bitrate_comprehensive_comparison.png'
plt.savefig(output_path, dpi=150, bbox_inches='tight')
print("\n" + "="*80)
print(f"Chart saved: {output_path}")
print("="*80)
plt.close()
