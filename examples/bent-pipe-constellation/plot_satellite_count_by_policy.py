#!/usr/bin/env python3
"""
Plot Satellite Count Contacted: How many unique satellites get contacted?

FLIPPED VERSION: Policies on X-axis, Strategies in legend

Shows the COUNT of unique satellites that receive at least one ground station
connection during the entire simulation period. This reveals "satellite starvation"
by showing the absolute number of satellites used vs total available.

Chart Structure:
----------------
X-axis: Policy groups (STICKY, FIFO, ROUNDROBIN, RANDOM, MAXDOWNLOAD)
        Each group shows results for different constellation sizes (1, 25, 50, 100, 200)
Y-axis: Number of unique satellites contacted (0 to constellation size)
Colors: Different strategies (Close=red, Orbit=blue, Frame=green, Close-Orbit=orange)
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
OUTPUT_DIR = BASE_DIR / "constellation_analysis" / "satellite_count_charts"

# Constants
STRATEGIES_MAP = {
    "close-spaced": "Close",
    "frame-spaced": "Frame",
    "orbit-spaced": "Orbit",
    "close-orbit-spaced": "Close-Orbit"
}
CONSTELLATION_SIZES = [1, 25, 50, 100, 200]
POLICIES = ["sticky", "fifo", "roundrobin", "random", "maxdownload"]
POLICY_COLORS = {
    "sticky": "#E63946",      # red
    "fifo": "#2E86AB",        # blue
    "roundrobin": "#06A77D",  # green
    "random": "#F77F00",      # orange
    "maxdownload": "#9D4EDD"  # purple
}
STRATEGY_COLORS = {
    "close-spaced": "#E63946",       # red
    "orbit-spaced": "#2E86AB",       # blue
    "frame-spaced": "#06A77D",       # green
    "close-orbit-spaced": "#F77F00"  # orange
}

def scan_all_configurations(search_dir='results/maxdownload_20251118_162637'):
    """Scan for all constellation_analysis folders and their strategy/policy subfolders"""
    configs = []
    
    search_path = Path(search_dir)
    # Search in specified directory
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

def plot_satellite_count_by_policy(results: Dict):
    """
    Create grouped bar charts with policies on X-axis and strategies as different colored bars.
    This is the FLIPPED version.
    """
    
    OUTPUT_DIR.mkdir(exist_ok=True)
    
    # Create one chart per image size
    for image_size in sorted(results.keys()):
        fig, ax = plt.subplots(figsize=(22, 10))
        
        strategies = list(STRATEGIES_MAP.keys())
        num_strategies = len(strategies)
        
        # Bar positioning - each policy/constellation combo gets 4 bars (one per strategy)
        bar_width = 0.15
        strategy_group_width = num_strategies * bar_width
        policy_spacing = 0.5
        
        x_offset = 0
        x_positions_for_labels = []
        max_y = 0
        
        # For each policy
        for policy_idx, policy in enumerate(POLICIES):
            # For each constellation size
            for sat_count in CONSTELLATION_SIZES:
                # Draw 4 bars (one per strategy) for this policy/constellation combo
                for strategy_idx, strategy in enumerate(strategies):
                    if strategy not in results[image_size]:
                        count = 0
                        total = sat_count
                    elif sat_count not in results[image_size][strategy]:
                        count = 0
                        total = sat_count
                    elif policy not in results[image_size][strategy][sat_count]:
                        count = 0
                        total = sat_count
                    else:
                        count, total = results[image_size][strategy][sat_count][policy]
                    
                    max_y = max(max_y, total)
                    
                    x_pos = x_offset + strategy_idx * bar_width
                    
                    ax.bar(x_pos, count, bar_width,
                          color=STRATEGY_COLORS[strategy],
                          edgecolor='black',
                          linewidth=0.5,
                          label=STRATEGIES_MAP[strategy] if policy_idx == 0 and sat_count == CONSTELLATION_SIZES[0] else "")
                    
                    # Add count label on top of bar
                    if count > 0 and count < total * 0.95:  # Only show if not at max
                        ax.text(x_pos, count + max_y * 0.01, f"{count}",
                               ha='center', va='bottom', fontsize=6, fontweight='bold')
                
                # Mark the center of this group for labeling
                x_positions_for_labels.append((x_offset + strategy_group_width/2, f"{sat_count}"))
                x_offset += strategy_group_width + 0.08
            
            # Add extra spacing between policies
            x_offset += policy_spacing
        
        # Set x-axis labels (constellation sizes)
        ax.set_xticks([pos for pos, label in x_positions_for_labels])
        ax.set_xticklabels([label for pos, label in x_positions_for_labels], 
                          rotation=0, ha='center', fontsize=9)
        ax.set_xlabel('Number of Satellites', fontsize=14, fontweight='bold')
        
        # Add policy group labels on secondary x-axis
        policy_centers = []
        x_offset = 0
        for policy in POLICIES:
            num_bars = len(CONSTELLATION_SIZES)
            center = x_offset + (num_bars * (strategy_group_width + 0.08) - 0.08) / 2
            policy_centers.append(center)
            x_offset += num_bars * (strategy_group_width + 0.08) + policy_spacing
        
        ax2 = ax.secondary_xaxis('bottom')
        ax2.set_xticks(policy_centers)
        ax2.set_xticklabels([p.upper() for p in POLICIES], 
                            fontsize=15, fontweight='bold')
        ax2.tick_params(axis='x', which='major', pad=35)
        
        # Add vertical separators between policy groups
        x_offset = 0
        for policy_idx in range(1, len(POLICIES)):
            separator_x = x_offset + len(CONSTELLATION_SIZES) * (strategy_group_width + 0.08) + policy_spacing / 2
            ax.axvline(x=separator_x, color='black', linestyle='-', linewidth=2, alpha=0.3)
            x_offset += len(CONSTELLATION_SIZES) * (strategy_group_width + 0.08) + policy_spacing
        
        # Y-axis
        ax.set_ylabel('Number of Unique Satellites Contacted', fontsize=14, fontweight='bold')
        ax.set_title(f'Satellite Contact Count by Policy, Constellation Size, and Strategy\n{image_size} KB Images',
                    fontsize=16, fontweight='bold', pad=20)
        
        ax.set_ylim(0, max_y * 1.15)
        ax.grid(axis='y', alpha=0.3, linestyle='--')
        ax.set_axisbelow(True)
        
        # Add reference lines for constellation sizes
        for const_size in CONSTELLATION_SIZES:
            if const_size <= max_y:
                ax.axhline(y=const_size, color='gray', linestyle=':', linewidth=1, alpha=0.4)
                ax.text(ax.get_xlim()[1] * 0.99, const_size + max_y * 0.01, f'{const_size}', 
                       ha='right', va='bottom', fontsize=8, color='gray', fontweight='bold')
        
        # Legend
        handles, labels = ax.get_legend_handles_labels()
        by_label = dict(zip(labels, handles))
        ax.legend(by_label.values(), by_label.keys(), 
                 loc='upper left', ncol=4, framealpha=0.95, fontsize=12, 
                 title='Spacing Strategy', title_fontsize=13, frameon=True, edgecolor='black')
        
        plt.tight_layout()
        
        # Save
        output_file = OUTPUT_DIR / f'satellite_count_by_policy_{image_size}kb.png'
        plt.savefig(output_file, dpi=300, bbox_inches='tight')
        print(f"\n✅ Saved: {output_file}")
        plt.close()

def main():
    print("=" * 100)
    print(" " * 30 + "SATELLITE COUNT ANALYSIS")
    print(" " * 25 + "(Policies on X-axis, Strategies as Colors)")
    print("=" * 100)
    
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
    print("\nGenerating charts (policies on X-axis)...")
    plot_satellite_count_by_policy(results)
    
    print("\n" + "=" * 100)
    print("✅ ANALYSIS COMPLETE!")
    print("=" * 100)
    
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
