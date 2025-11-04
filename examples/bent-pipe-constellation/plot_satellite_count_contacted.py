#!/usr/bin/env python3
"""
Plot Satellite Count Contacted: How many unique satellites get contacted?

Shows the COUNT of unique satellites that receive at least one ground station
connection during the entire simulation period. This reveals "satellite starvation"
by showing the absolute number of satellites used vs total available.

KEY DIFFERENCES FROM PERCENTAGE VERSION:
-----------------------------------------
- Shows RAW COUNTS (e.g., "11 out of 200") instead of percentages
- Makes it easier to see the absolute scale of satellite starvation
- Y-axis scales to match constellation size for each group

Examples:
- If only sat0 connects repeatedly: count = 1
- If all 25 sats in constellation connect at least once: count = 25
- If 11 out of 200 sats connect: count = 11 (189 satellites starved!)

Chart Structure:
----------------
X-axis: Strategy groups (Close, Orbit, Frame, Close-Orbit)
Y-axis: Number of unique satellites contacted (0 to constellation size)
Colors: Different policies (STICKY=red, FIFO=blue, ROUNDROBIN=green, RANDOM=orange)
Output: Multiple charts - one per image size tested
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
OUTPUT_DIR = BASE_DIR / "satellite_count_charts"

# Constants
STRATEGIES_MAP = {
    "close-spaced": "Close",
    "frame-spaced": "Frame",
    "orbit-spaced": "Orbit",
    "close-orbit-spaced": "Close-Orbit"
}
CONSTELLATION_SIZES = [1, 25, 50, 100, 200]
POLICIES = ["sticky", "fifo", "roundrobin", "random"]
POLICY_COLORS = {
    "sticky": "#d62728",      # red
    "fifo": "#1f77b4",        # blue
    "roundrobin": "#2ca02c",  # green
    "random": "#ff7f0e"       # orange
}

def scan_all_configurations(search_dir='results/base results 2'):
    """Scan for all constellation_analysis folders and their strategy/policy subfolders"""
    configs = []
    
    search_path = Path(search_dir)
    # Search in specified directory (base results 2)
    for constellation_folder in search_path.glob('constellation_analysis_*'):
        if not constellation_folder.is_dir():
            continue
            
        # Parse folder name: constellation_analysis_YYYYMMDD_HHMMSS_IMAGESIZE_NUMSATS
        match = re.match(r'constellation_analysis_\d{8}_\d{6}_(\d+)_(\d+)', constellation_folder.name)
        if not match:
            continue
            
        image_size = int(match.group(1))
        num_sats = int(match.group(2))
        
        # Look for strategy folders inside this constellation folder
        for strategy_folder in constellation_folder.iterdir():
            if not strategy_folder.is_dir():
                continue
            
            strategy_name = strategy_folder.name
            if strategy_name not in STRATEGIES_MAP:
                continue
            
            # Check if simulation_logs.zip exists
            zip_path = strategy_folder / 'simulation_logs.zip'
            if not zip_path.exists():
                continue
            
            # Detect available policies in the zip file
            try:
                with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                    # Find unique policy folders in the zip
                    policy_folders = set()
                    for filename in zip_ref.namelist():
                        parts = filename.split('/')
                        if len(parts) > 1 and parts[0] in POLICIES:
                            policy_folders.add(parts[0])
                    
                    # Add a config entry for each policy found
                    for policy in policy_folders:
                        configs.append({
                            'folder': constellation_folder,
                            'strategy_folder': strategy_folder,
                            'image_size': image_size,
                            'num_sats': num_sats,
                            'strategy': strategy_name,
                            'policy': policy
                        })
            except Exception as e:
                print(f"⚠️  Error scanning {zip_path}: {e}")
                continue
    
    return configs


def get_contacted_satellites(strategy_folder: Path, policy: str) -> Tuple[Set[int], int]:
    """
    Get the set of unique satellite IDs that were contacted during the simulation.
    Returns: (set of contacted sat_ids, total constellation size)
    """
    zip_path = strategy_folder / 'simulation_logs.zip'
    
    if not zip_path.exists():
        return set(), 0
    
    contacted_sats = set()
    total_sats = 0
    
    try:
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            # Look for the downlink tx-rx file for this policy
            downlink_file = f'{policy}/meas-downlink-tx-rx.csv'
            
            if downlink_file not in zip_ref.namelist():
                return set(), 0
            
            with zip_ref.open(downlink_file) as f:
                df = pd.read_csv(f)
                
                # Check for required column
                if 'downlink-tx-rx' not in df.columns:
                    print(f"    ⚠️  Missing 'downlink-tx-rx' column in {policy}")
                    return set(), 0
                
                # Filter out None connections
                connected_df = df[df['downlink-tx-rx'] != 'None'].dropna(subset=['downlink-tx-rx'])
                
                # Extract satellite IDs from the format "satid-groundstation"
                for link in connected_df['downlink-tx-rx']:
                    if isinstance(link, str) and '-' in link:
                        sat_id = link.split('-')[0]
                        contacted_sats.add(sat_id)
            
            # Get total constellation size by checking all satellites across all policies
            # Count unique satellites that exist in the buffer files
            buffer_files = [f for f in zip_ref.namelist() if 'meas-MB-buffered-sat-' in f]
            
            # Extract satellite IDs from filenames like "sticky/meas-MB-buffered-sat-0060518040.csv"
            all_sat_ids = set()
            for filename in buffer_files:
                parts = filename.split('sat-')
                if len(parts) > 1:
                    sat_id = parts[1].replace('.csv', '')
                    all_sat_ids.add(sat_id)
            
            total_sats = len(all_sat_ids)
                
    except Exception as e:
        print(f"    ⚠️  Error processing {zip_path}: {e}")
        return set(), 0
    
    return contacted_sats, total_sats

def calculate_satellite_counts(configs: List[Dict]) -> Dict:
    """
    Calculate the COUNT of unique satellites contacted for each configuration.
    Returns nested dict: {image_size: {strategy: {constellation_size: {policy: (count, total)}}}}
    """
    results = {}
    
    # Group by image size, strategy, constellation size, and policy
    for config in configs:
        image_size = config['image_size']
        strategy = config['strategy']
        num_sats = config['num_sats']
        policy = config['policy']
        strategy_folder = config['strategy_folder']
        
        # Initialize nested structure
        if image_size not in results:
            results[image_size] = {}
        if strategy not in results[image_size]:
            results[image_size][strategy] = {}
        if num_sats not in results[image_size][strategy]:
            results[image_size][strategy][num_sats] = {}
        
        # Calculate count
        contacted_sats, total_sats = get_contacted_satellites(strategy_folder, policy)
        
        count = len(contacted_sats)
        
        results[image_size][strategy][num_sats][policy] = (count, total_sats)
        
        starved = total_sats - count
        print(f"  {STRATEGIES_MAP.get(strategy, strategy):12s} | "
              f"Size {num_sats:3d} | {policy:10s} | "
              f"{count:3d}/{total_sats:3d} contacted | {starved:3d} starved")
    
    return results

def plot_satellite_count_charts(results: Dict):
    """Create grouped bar charts showing satellite count contacted"""
    
    OUTPUT_DIR.mkdir(exist_ok=True)
    
    # Create one chart per image size
    for image_size in sorted(results.keys()):
        fig, ax = plt.subplots(figsize=(20, 10))
        
        strategies = list(STRATEGIES_MAP.keys())
        num_policies = len(POLICIES)
        
        # Bar positioning - each strategy/constellation combo gets 4 bars (one per policy)
        bar_width = 0.18
        policy_group_width = num_policies * bar_width
        strategy_spacing = 0.5  # Increased spacing between strategies
        
        x_offset = 0
        x_positions_for_labels = []
        max_y = 0
        
        # For each strategy
        for strategy_idx, strategy in enumerate(strategies):
            if strategy not in results[image_size]:
                continue
            
            strategy_data = results[image_size][strategy]
            
            # For each constellation size within the strategy
            for sat_count in CONSTELLATION_SIZES:
                if sat_count not in strategy_data:
                    continue
                
                # Draw 4 bars (one per policy) for this strategy/constellation combo
                for policy_idx, policy in enumerate(POLICIES):
                    if policy not in strategy_data[sat_count]:
                        count = 0
                        total = sat_count
                    else:
                        count, total = strategy_data[sat_count][policy]
                    
                    max_y = max(max_y, total)
                    
                    x_pos = x_offset + policy_idx * bar_width
                    
                    ax.bar(x_pos, count, bar_width,
                          color=POLICY_COLORS[policy],
                          edgecolor='black',
                          linewidth=0.5,
                          label=policy.upper() if strategy_idx == 0 and sat_count == CONSTELLATION_SIZES[0] else "")
                    
                    # Add count label on top of bar
                    if count > 0:
                        ax.text(x_pos, count + max_y * 0.01, f"{count}",
                               ha='center', va='bottom', fontsize=7, fontweight='bold')
                
                # Mark the center of this group for labeling
                x_positions_for_labels.append((x_offset + policy_group_width/2, f"{sat_count}"))
                x_offset += policy_group_width + 0.1  # small gap between constellation sizes
            
            # Add extra spacing between strategies
            x_offset += strategy_spacing
        
        # Add constellation size labels on x-axis and strategy labels below
        ax.set_xticks([pos for pos, label in x_positions_for_labels])
        ax.set_xticklabels([label for pos, label in x_positions_for_labels], 
                          rotation=0, ha='center', fontsize=9)
        
        # Add strategy group labels below the constellation sizes
        x_offset = 0
        for strategy_idx, strategy in enumerate(strategies):
            if strategy not in results[image_size]:
                continue
            
            # Count how many constellation sizes this strategy has
            strategy_data = results[image_size][strategy]
            num_constellations = len([sc for sc in CONSTELLATION_SIZES if sc in strategy_data])
            
            # Calculate center position for strategy label
            strategy_width = num_constellations * (policy_group_width + 0.1) - 0.1
            x_center = x_offset + strategy_width / 2
            
            ax.text(x_center, -max_y * 0.12, STRATEGIES_MAP[strategy], 
                   ha='center', va='top', fontsize=14, fontweight='bold')
            
            x_offset += strategy_width + strategy_spacing
        
        # Styling
        ax.set_ylabel('Number of Unique Satellites Contacted', fontsize=14, fontweight='bold')
        ax.set_title(f'Satellite Contact Count by Strategy & Policy\n'
                    f'Image Size: {image_size} KB | Shows how many unique satellites were contacted at least once',
                    fontsize=16, fontweight='bold', pad=20)
        
        ax.set_ylim(0, max_y * 1.15)
        ax.grid(axis='y', alpha=0.3, linestyle='--')
        ax.set_axisbelow(True)
        
        # Add reference lines for constellation sizes
        for const_size in CONSTELLATION_SIZES:
            if const_size <= max_y:
                ax.axhline(y=const_size, color='gray', linestyle=':', linewidth=1, alpha=0.4)
                ax.text(ax.get_xlim()[1] * 0.98, const_size, f'{const_size} sats', 
                       ha='right', va='bottom', fontsize=8, color='gray')
        
        # Legend - compact horizontal layout
        handles, labels = ax.get_legend_handles_labels()
        # Remove duplicate labels
        by_label = dict(zip(labels, handles))
        ax.legend(by_label.values(), by_label.keys(), 
                 loc='upper right', ncol=4, framealpha=0.9, fontsize=11, 
                 title='Policy', title_fontsize=11, frameon=True, shadow=False)
        
        plt.tight_layout()
        
        output_file = OUTPUT_DIR / f'satellite_count_comparison_{image_size}kb.png'
        plt.savefig(output_file, dpi=150, bbox_inches='tight')
        print(f"\n✅ Saved: {output_file}")
        plt.close()

def main():
    print("=" * 80)
    print("SATELLITE COUNT ANALYSIS")
    print("Counting unique satellites contacted during simulation")
    print("=" * 80)
    
    # Scan for all configurations
    configs = scan_all_configurations()
    
    if not configs:
        print("❌ No constellation_analysis folders found!")
        return
    
    print(f"\n✅ Found {len(configs)} configurations\n")
    
    # Calculate satellite counts
    print("Counting contacted satellites...\n")
    results = calculate_satellite_counts(configs)
    
    # Create visualizations
    print("\nGenerating charts...")
    plot_satellite_count_charts(results)
    
    print("\n" + "=" * 80)
    print("✅ ANALYSIS COMPLETE!")
    print("=" * 80)
    
    # Print summary statistics
    print("\n📊 Summary Statistics:")
    for image_size in sorted(results.keys()):
        print(f"\n  Image Size: {image_size} KB")
        for strategy in STRATEGIES_MAP.keys():
            if strategy in results[image_size]:
                print(f"    {STRATEGIES_MAP[strategy]:12s}:")
                for sat_count in CONSTELLATION_SIZES:
                    if sat_count in results[image_size][strategy]:
                        counts = [results[image_size][strategy][sat_count][p][0] 
                                 for p in POLICIES if p in results[image_size][strategy][sat_count]]
                        if counts:
                            avg_count = np.mean(counts)
                            total = results[image_size][strategy][sat_count][POLICIES[0]][1]
                            avg_starved = total - avg_count
                            print(f"      Size {sat_count:3d}: {avg_count:5.1f} avg contacted | {avg_starved:5.1f} avg starved")

if __name__ == '__main__':
    main()
