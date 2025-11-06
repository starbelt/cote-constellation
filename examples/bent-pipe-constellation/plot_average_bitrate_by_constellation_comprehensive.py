#!/usr/bin/env python3
"""
Plot AVERAGE BIT RATE vs CONSTELLATION SIZE - COMPREHENSIVE VIEW
All strategies and all image sizes on ONE chart.
X-axis: Constellation Size (1, 25, 50, 100, 200)
Lines: Strategy × Image Size combinations (color = strategy, line style = image size)
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

# Line styles for image sizes
IMAGE_SIZE_STYLES = {
    27: ':',         # dotted
    279: '--',       # dashed
    2799: '-.',      # dash-dot
    28000: '-',      # solid
    280000: '-',     # solid (thicker)
    1024000: '-'     # solid (thickest)
}

IMAGE_SIZE_WIDTHS = {
    27: 1.5,
    279: 1.5,
    2799: 1.8,
    28000: 2.0,
    280000: 2.3,
    1024000: 2.6
}

IMAGE_SIZE_LABELS = {
    27: '27 KB',
    279: '279 KB',
    2799: '2.8 MB',
    28000: '28 MB',
    280000: '280 MB',
    1024000: '1 GB'
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
output_dir = Path("constellation_analysis") / "bitrate_charts"
output_dir.mkdir(parents=True, exist_ok=True)

# Create the comprehensive comparison chart
fig, ax = plt.subplots(figsize=(20, 12))

print("\n" + "="*80)
print("AVERAGE BIT RATE vs CONSTELLATION SIZE - COMPREHENSIVE")
print("="*80)

# Collect and plot data for each strategy and image size
for strategy in STRATEGIES:
    print(f"\n{STRATEGY_DISPLAY[strategy]}:")
    print("-" * 80)
    
    for img_size in IMAGE_SIZES_KB:
        bitrates = []
        
        for const_size in CONSTELLATION_SIZES:
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
        
        # Plot line for this strategy+image size combination
        valid_indices = [i for i, b in enumerate(bitrates) if b is not None]
        valid_const_sizes = [CONSTELLATION_SIZES[i] for i in valid_indices]
        valid_bitrates = [bitrates[i] for i in valid_indices]
        
        if valid_bitrates:
            label = f'{STRATEGY_DISPLAY[strategy]} ({IMAGE_SIZE_LABELS[img_size]})'
            ax.plot(valid_const_sizes, valid_bitrates, 
                   marker='o', markersize=6, 
                   linewidth=IMAGE_SIZE_WIDTHS[img_size],
                   color=STRATEGY_COLORS[strategy],
                   linestyle=IMAGE_SIZE_STYLES[img_size],
                   label=label,
                   alpha=0.8)
            
            print(f"  {IMAGE_SIZE_LABELS[img_size]:10s}: {' → '.join([f'{b:6.2f}' for b in valid_bitrates])} Mbps")

# Formatting
ax.set_xlabel('Constellation Size (Number of Satellites)', fontsize=16, fontweight='bold')
ax.set_ylabel('Average Downlink Bit Rate (Mbps)\nDuring Active Transmission', fontsize=16, fontweight='bold')
ax.set_title('Average Downlink Bit Rate vs Constellation Size\nAll Strategies × All Image Sizes\n(Measured only when actively transmitting data)',
            fontsize=18, fontweight='bold', pad=20)
ax.grid(True, alpha=0.3, linestyle='--')

# Set x-axis to show all constellation sizes
ax.set_xticks(CONSTELLATION_SIZES)
ax.set_xticklabels([f'{size}' for size in CONSTELLATION_SIZES])

# Create custom legend outside plot area
legend_handles = []
legend_labels = []

for strategy in STRATEGIES:
    for img_size in IMAGE_SIZES_KB:
        label = f'{STRATEGY_DISPLAY[strategy]} ({IMAGE_SIZE_LABELS[img_size]})'
        line = plt.Line2D([0], [0], 
                         color=STRATEGY_COLORS[strategy],
                         linestyle=IMAGE_SIZE_STYLES[img_size],
                         linewidth=IMAGE_SIZE_WIDTHS[img_size],
                         marker='o', markersize=6)
        legend_handles.append(line)
        legend_labels.append(label)

ax.legend(legend_handles, legend_labels, 
         fontsize=9, loc='upper left', bbox_to_anchor=(1.02, 1), 
         ncol=1, framealpha=0.95)

plt.tight_layout()

# Save figure
output_path = output_dir / 'average_bitrate_by_constellation_comprehensive.png'
plt.savefig(output_path, dpi=150, bbox_inches='tight')
print("\n" + "="*80)
print(f"✅ Chart saved: {output_path}")
print("="*80)
plt.close()
