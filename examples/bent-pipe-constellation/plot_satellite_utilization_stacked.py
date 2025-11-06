#!/usr/bin/env python3
"""
Plot Satellite Utilization with Stacked Bars: Each satellite as a segment

Shows satellite utilization with each individual satellite as a colored segment
in a stacked bar chart. This makes it easy to see:
- Which specific satellites are being used
- How many satellites are contributing
- The distribution of satellite usage across the constellation

Chart Structure:
----------------
X-axis: Strategy-Policy combinations for each constellation size
Y-axis: Percentage (0-100%)
Bars: Stacked segments, each representing one contacted satellite
Colors: Each satellite gets a unique color (or color from palette)
"""

import pandas as pd
import matplotlib.pyplot as plt
import numpy as np
import zipfile
from pathlib import Path
from typing import Dict, List, Tuple, Set
import sys
import re
import matplotlib.cm as cm

# Configuration directories
BASE_DIR = Path(".")
OUTPUT_DIR = BASE_DIR / "constellation_analysis" / "stacked_satellite_charts"

# Constants
STRATEGIES_MAP = {
    "close-spaced": "Close",
    "orbit-spaced": "Orbit",
    "frame-spaced": "Frame",
    "close-orbit-spaced": "Close-Orbit"
}
CONSTELLATION_SIZES = [1, 25, 50, 100, 200]  # Sizes in base results 2
IMAGE_SIZES_TO_PROCESS = [27, 279, 2799, 28000, 280000, 1024000]  # All image sizes in base results 2
POLICIES = ["sticky", "fifo", "roundrobin", "random"]
POLICY_COLORS = {
    "sticky": "#d62728",      # red
    "fifo": "#1f77b4",        # blue
    "roundrobin": "#2ca02c",  # green
    "random": "#ff7f0e"       # orange
}

def find_constellation_dirs() -> Dict[str, List[Path]]:
    """Find all constellation_analysis directories organized by image size."""
    results_dir = BASE_DIR / "results" / "base results 2"
    
    if not results_dir.exists():
        print(f"❌ Results directory not found: {results_dir}")
        return {}
    
    # Pattern: constellation_analysis_YYYYMMDD_HHMMSS_IMAGESIZE_CONSTSIZE
    pattern = r"constellation_analysis_\d{8}_\d{6}_(\d+)_(\d+)"
    
    dirs_by_size = {}
    for dir_path in results_dir.iterdir():
        if dir_path.is_dir():
            match = re.match(pattern, dir_path.name)
            if match:
                image_size_kb = int(match.group(1))
                const_size = int(match.group(2))
                
                if image_size_kb not in dirs_by_size:
                    dirs_by_size[image_size_kb] = []
                dirs_by_size[image_size_kb].append((const_size, dir_path))
    
    # Sort by constellation size
    for size_kb in dirs_by_size:
        dirs_by_size[size_kb].sort(key=lambda x: x[0])
    
    return dirs_by_size


def get_contacted_satellites(zip_path: Path, policy: str) -> Set[str]:
    """
    Get the set of satellite IDs that were contacted at least once.
    
    Returns:
        Set of satellite IDs (as strings) that received at least one connection
    """
    csv_file = f"{policy}/meas-downlink-tx-rx.csv"
    contacted_sats = set()
    
    try:
        with zipfile.ZipFile(zip_path, 'r') as zf:
            if csv_file not in zf.namelist():
                return contacted_sats
            
            with zf.open(csv_file) as f:
                df = pd.read_csv(f)
                
                for link in df['downlink-tx-rx']:
                    if link == 'None' or pd.isna(link):
                        continue
                    if isinstance(link, str) and '-' in link:
                        sat_id = link.split('-')[0]
                        contacted_sats.add(sat_id)
    except Exception as e:
        print(f"  ⚠️  Error reading {zip_path}/{csv_file}: {e}")
    
    return contacted_sats


def plot_stacked_utilization(data_by_size: Dict, image_size_kb: int):
    """
    Create stacked bar chart showing individual satellites as segments.
    
    data_by_size: {const_size: {strategy: {policy: set(contacted_sat_ids)}}}
    """
    
    fig, ax = plt.subplots(figsize=(24, 12))
    
    # Prepare data structure for plotting
    bar_positions = []
    bar_labels = []
    all_bars_data = []  # List of (contacted_sats, total_sats, strategy) for each bar
    x_positions_for_labels = []
    
    x_pos = 0
    bar_width = 0.6
    constellation_spacing = 0.3
    strategy_spacing = 2.0
    
    # Organize: For each strategy -> each constellation size -> each policy
    # Order: Close, Frame, Orbit, Close-Orbit
    for strategy in ["close-spaced", "frame-spaced", "orbit-spaced", "close-orbit-spaced"]:
        strategy_start_pos = x_pos
        
        for const_size in CONSTELLATION_SIZES:
            if const_size not in data_by_size:
                continue
            
            if strategy not in data_by_size[const_size]:
                continue
            
            policy_data = data_by_size[const_size][strategy]
            const_start_pos = x_pos
            
            for policy in POLICIES:
                if policy not in policy_data:
                    contacted_sats = set()
                else:
                    contacted_sats = policy_data[policy]
                
                # Store data for this bar
                bar_positions.append(x_pos)
                bar_labels.append(f"{const_size}")
                all_bars_data.append((contacted_sats, const_size, strategy))
                
                x_pos += bar_width + 0.15
            
            # Mark center of this constellation group for labeling
            const_center = (const_start_pos + x_pos - (bar_width + 0.15)) / 2
            x_positions_for_labels.append((const_center, f"{const_size}"))
            
            # Add spacing between constellation sizes
            x_pos += constellation_spacing
        
        # Add spacing between strategies
        x_pos += strategy_spacing
    
    # Now plot the stacked bars
    # For each bar, create stacked segments for each contacted satellite
    for idx, (bar_x, (contacted_sats, total_sats, strategy)) in enumerate(zip(bar_positions, all_bars_data)):
        num_contacted = len(contacted_sats)
        
        if num_contacted == 0:
            # No satellites contacted - show empty bar in gray
            ax.bar(bar_x, 100, bar_width, color='#cccccc', alpha=0.3, 
                   edgecolor='black', linewidth=0.5)
            continue
        
        # Calculate height per satellite (to stack to 100%)
        segment_height = 100.0 / total_sats
        
        # Get colormap for satellite colors
        if num_contacted <= 10:
            colors = plt.cm.tab10(np.linspace(0, 1, 10))
        elif num_contacted <= 20:
            colors = plt.cm.tab20(np.linspace(0, 1, 20))
        else:
            colors = plt.cm.rainbow(np.linspace(0, 1, num_contacted))
        
        # Stack contacted satellites
        bottom = 0
        sorted_sats = sorted(contacted_sats, key=lambda x: int(x))
        
        for sat_idx, sat_id in enumerate(sorted_sats):
            color = colors[sat_idx % len(colors)]
            ax.bar(bar_x, segment_height, bar_width, 
                   bottom=bottom, color=color, 
                   edgecolor='black', linewidth=0.1, alpha=0.8)
            
            bottom += segment_height
        
        # Fill remaining with gray (not contacted)
        remaining_height = 100 - bottom
        if remaining_height > 0.1:
            ax.bar(bar_x, remaining_height, bar_width, 
                   bottom=bottom, color='#cccccc', alpha=0.3,
                   edgecolor='black', linewidth=0.1)
        
        # Add text label showing percentage only (cleaner)
        utilization_pct = (num_contacted / total_sats) * 100
        ax.text(bar_x, 102, f"{utilization_pct:.0f}%",
                ha='center', va='bottom', fontsize=7, fontweight='bold', color='#333')
    
    # Formatting
    ax.set_ylabel('Percentage of Satellites', fontsize=14, fontweight='bold')
    ax.set_xlabel('')  # Remove x-axis label for cleaner look
    ax.set_title(f'Satellite Utilization: Individual Satellites as Stacked Segments\n'
                 f'Image Size: {image_size_kb} KB | Each colored segment = one contacted satellite',
                 fontsize=16, fontweight='bold', pad=20)
    
    # Add constellation size labels on x-axis
    ax.set_xticks([pos for pos, label in x_positions_for_labels])
    ax.set_xticklabels([label for pos, label in x_positions_for_labels], 
                      rotation=0, ha='center', fontsize=9)
    
    ax.set_ylim(0, 115)
    ax.set_yticks(range(0, 101, 10))
    
    # Add grid
    ax.grid(axis='y', alpha=0.3, linestyle='--')
    
    # Add strategy labels below constellation sizes
    x_pos = 0
    for strategy in ["close-spaced", "frame-spaced", "orbit-spaced", "close-orbit-spaced"]:
        # Find all bars for this strategy
        strategy_bars = []
        for i, (_, _, bar_strategy) in enumerate(all_bars_data):
            if bar_strategy == strategy:
                strategy_bars.append(bar_positions[i])
        
        if strategy_bars:
            mid_x = (strategy_bars[0] + strategy_bars[-1]) / 2
            ax.text(mid_x, -12, STRATEGIES_MAP[strategy], 
                   ha='center', va='top', fontsize=14, fontweight='bold')
    
    # Add legend
    from matplotlib.patches import Patch
    legend_elements = [
        Patch(facecolor='tab:blue', alpha=0.8, label='Contacted Satellites'),
        Patch(facecolor='#cccccc', alpha=0.3, label='Not Contacted')
    ]
    ax.legend(handles=legend_elements, loc='upper left', fontsize=11, framealpha=0.9)
    
    plt.tight_layout()
    
    output_path = OUTPUT_DIR / f"satellite_utilization_stacked_{image_size_kb}kb.png"
    plt.savefig(output_path, dpi=150, bbox_inches='tight')
    plt.close()
    
    print(f"✅ Saved: {output_path}")


def main():
    """Main analysis function."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    
    print("\n" + "="*80)
    print("STACKED SATELLITE UTILIZATION ANALYSIS")
    print("="*80 + "\n")
    
    dirs_by_size = find_constellation_dirs()
    
    if not dirs_by_size:
        print("❌ No constellation directories found!")
        return
    
    # Process each image size
    for image_size_kb in sorted(dirs_by_size.keys()):
        # Only process specified image sizes
        if image_size_kb not in IMAGE_SIZES_TO_PROCESS:
            continue
            
        print(f"\n📊 Processing Image Size: {image_size_kb} KB")
        print("-" * 80)
        
        # Collect data: {const_size: {strategy: {policy: set(contacted_sat_ids)}}}
        data_by_size = {}
        
        constellation_dirs = dirs_by_size[image_size_kb]
        
        for const_size, dir_path in constellation_dirs:
            if const_size not in CONSTELLATION_SIZES:
                continue
            
            print(f"\n  Constellation Size: {const_size} satellites")
            
            if const_size not in data_by_size:
                data_by_size[const_size] = {}
            
            # Check each strategy
            for strategy in ["close-spaced", "orbit-spaced", "frame-spaced", "close-orbit-spaced"]:
                strategy_dir = dir_path / strategy
                if not strategy_dir.exists():
                    continue
                
                zip_path = strategy_dir / "simulation_logs.zip"
                if not zip_path.exists():
                    continue
                
                if strategy not in data_by_size[const_size]:
                    data_by_size[const_size][strategy] = {}
                
                # Process each policy
                for policy in POLICIES:
                    contacted_sats = get_contacted_satellites(zip_path, policy)
                    data_by_size[const_size][strategy][policy] = contacted_sats
                    
                    utilization_pct = len(contacted_sats) / const_size * 100
                    print(f"    {STRATEGIES_MAP[strategy]:12} | {policy:10} | "
                          f"{len(contacted_sats):3}/{const_size:3} sats ({utilization_pct:5.1f}%)")
        
        # Create stacked chart for this image size
        if data_by_size:
            plot_stacked_utilization(data_by_size, image_size_kb)
    
    print("\n" + "="*80)
    print("✅ ANALYSIS COMPLETE!")
    print("="*80)
    print(f"\n📁 All charts saved to: {OUTPUT_DIR}/")
    print("\nEach colored segment in the bars represents one contacted satellite!")
    print("Gray areas show satellites that were never contacted (starved).")


if __name__ == "__main__":
    main()
