#!/usr/bin/env python3
"""
Plot Individual Satellite Utilization: Which specific satellites get contacted?

Shows exactly which satellite IDs receive connections, revealing whether
the load is concentrated on just one satellite or distributed across multiple.

This answers questions like:
- Is it the SAME satellite getting all connections (sticky behavior)?
- Or are multiple satellites sharing the load?
- Which specific satellite IDs are the "favorites"?

Chart Structure:
----------------
- One chart per strategy-policy-size combination
- X-axis: Satellite ID
- Y-axis: Binary (1 = contacted, 0 = not contacted)
- Shows the exact satellites that received at least one connection
- Color-coded by whether satellite was contacted or not
"""

import pandas as pd
import matplotlib.pyplot as plt
import numpy as np
import zipfile
from pathlib import Path
from typing import Dict, List, Tuple, Set
import sys
import re

# Configuration directories
BASE_DIR = Path(".")
OUTPUT_DIR = BASE_DIR / "individual_satellite_charts"

# Constants
STRATEGIES_MAP = {
    "close-spaced": "Close",
    "orbit-spaced": "Orbit",
    "frame-spaced": "Frame",
    "close-orbit-spaced": "Close-Orbit"
}
CONSTELLATION_SIZES = [1, 50, 100, 200]
POLICIES = ["sticky", "fifo", "roundrobin", "random"]

def find_constellation_dirs() -> Dict[str, List[Path]]:
    """Find all constellation_analysis directories organized by image size."""
    results_dir = BASE_DIR / "results" / "base results"
    
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


def get_contacted_satellites(zip_path: Path, policy: str, total_sats: int) -> Set[str]:
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


def plot_individual_utilization(strategy: str, policy: str, const_size: int, 
                                contacted_sats: Set[str], output_path: Path):
    """
    Create a chart showing which individual satellites were contacted.
    """
    # Get all satellite IDs in order
    all_sat_ids = sorted(contacted_sats, key=lambda x: int(x) if x.isdigit() else 0)
    
    # Create binary array: 1 if contacted, 0 if not
    fig, ax = plt.subplots(figsize=(16, 6))
    
    # Create bar chart
    colors = ['#2ca02c' if sat_id in contacted_sats else '#d62728' 
              for sat_id in all_sat_ids]
    
    x_pos = np.arange(len(all_sat_ids))
    ax.bar(x_pos, [1] * len(all_sat_ids), color=colors, alpha=0.7, edgecolor='black', linewidth=0.5)
    
    # Formatting
    ax.set_xlabel('Satellite ID', fontsize=12, fontweight='bold')
    ax.set_ylabel('Contacted', fontsize=12, fontweight='bold')
    ax.set_title(f'{STRATEGIES_MAP[strategy]} | {policy.upper()} | {const_size} Satellites\n'
                 f'{len(contacted_sats)}/{const_size} satellites contacted ({len(contacted_sats)/const_size*100:.1f}%)',
                 fontsize=14, fontweight='bold', pad=20)
    
    # Set x-axis ticks
    if len(all_sat_ids) <= 50:
        ax.set_xticks(x_pos)
        ax.set_xticklabels(all_sat_ids, rotation=90, fontsize=8)
    else:
        # For large constellations, show every Nth label
        step = max(1, len(all_sat_ids) // 20)
        ax.set_xticks(x_pos[::step])
        ax.set_xticklabels([all_sat_ids[i] for i in range(0, len(all_sat_ids), step)], 
                          rotation=90, fontsize=8)
    
    ax.set_yticks([0, 1])
    ax.set_yticklabels(['Not Contacted', 'Contacted'])
    ax.set_ylim(-0.1, 1.3)
    
    # Add grid
    ax.grid(axis='y', alpha=0.3, linestyle='--')
    
    # Add legend
    from matplotlib.patches import Patch
    legend_elements = [
        Patch(facecolor='#2ca02c', alpha=0.7, label='Contacted'),
        Patch(facecolor='#d62728', alpha=0.7, label='Not Contacted')
    ]
    ax.legend(handles=legend_elements, loc='upper right', fontsize=10)
    
    plt.tight_layout()
    plt.savefig(output_path, dpi=150, bbox_inches='tight')
    plt.close()


def main():
    """Main analysis function."""
    OUTPUT_DIR.mkdir(exist_ok=True)
    
    print("\n" + "="*80)
    print("INDIVIDUAL SATELLITE UTILIZATION ANALYSIS")
    print("="*80 + "\n")
    
    dirs_by_size = find_constellation_dirs()
    
    if not dirs_by_size:
        print("❌ No constellation directories found!")
        return
    
    # Process each image size
    for image_size_kb in sorted(dirs_by_size.keys()):
        print(f"\n📊 Processing Image Size: {image_size_kb} KB")
        print("-" * 80)
        
        size_output_dir = OUTPUT_DIR / f"{image_size_kb}kb"
        size_output_dir.mkdir(exist_ok=True)
        
        constellation_dirs = dirs_by_size[image_size_kb]
        
        for const_size, dir_path in constellation_dirs:
            print(f"\n  Constellation Size: {const_size} satellites")
            
            # Check each strategy
            for strategy in ["close-spaced", "orbit-spaced", "frame-spaced", "close-orbit-spaced"]:
                strategy_dir = dir_path / strategy
                if not strategy_dir.exists():
                    continue
                
                zip_path = strategy_dir / "simulation_logs.zip"
                if not zip_path.exists():
                    continue
                
                # Process each policy
                for policy in POLICIES:
                    contacted_sats = get_contacted_satellites(zip_path, policy, const_size)
                    
                    if len(contacted_sats) == 0:
                        print(f"    {STRATEGIES_MAP[strategy]:12} | {policy:10} | No satellites contacted")
                        continue
                    
                    utilization_pct = len(contacted_sats) / const_size * 100
                    print(f"    {STRATEGIES_MAP[strategy]:12} | {policy:10} | "
                          f"{len(contacted_sats):3}/{const_size:3} sats contacted ({utilization_pct:5.1f}%) | "
                          f"Sat IDs: {', '.join(sorted(list(contacted_sats)[:5]))}{'...' if len(contacted_sats) > 5 else ''}")
                    
                    # Create individual chart
                    output_path = size_output_dir / f"individual_sats_{strategy}_{policy}_{const_size}.png"
                    plot_individual_utilization(strategy, policy, const_size, contacted_sats, output_path)
        
        print(f"\n✅ Saved charts to: {size_output_dir}/")
    
    print("\n" + "="*80)
    print("✅ ANALYSIS COMPLETE!")
    print("="*80)
    print(f"\n📁 All charts saved to: {OUTPUT_DIR}/")
    print("\nYou can now see exactly which satellites are being used vs. ignored!")
    print("Look for patterns like:")
    print("  - Single satellite doing all the work (sticky behavior)")
    print("  - Small cluster of satellites (limited coverage)")
    print("  - All satellites used evenly (good distribution)")


if __name__ == "__main__":
    main()
