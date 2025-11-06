#!/usr/bin/env python3
"""
Plot Satellite Utilization Percentage: How many satellites get contacted?

Shows the percentage of satellites that receive at least one ground station
connection during the entire simulation period. This reveals "satellite starvation"
where certain link policies prevent some satellites from ever being used.

KEY FINDINGS:
-------------
This visualization dramatically shows the "satellite starvation" problem:

1. ORBIT-SPACED: Near 100% utilization across all policies
   - All satellites get used effectively
   - Good resource distribution

2. CLOSE-SPACED + STICKY: Severe starvation!
   - 50 sats: Only 22% utilized (39 satellites NEVER contacted)
   - 200 sats: Only 5.5% utilized (189 satellites NEVER contacted!)
   - Ground stations "stick" to the same satellites, ignoring others

3. CLOSE-SPACED + FIFO/ROUNDROBIN/RANDOM: Better distribution
   - 50 sats: 42-100% utilization
   - 200 sats: 92-100% utilization
   - Fair policies ensure broader satellite usage

4. FRAME-SPACED: Moderate utilization (52-100%)
   - Generally good, but RANDOM policy can miss some satellites

5. CLOSE-ORBIT: Mixed results
   - Generally high utilization, but STICKY can reduce to 63-93%

INTERPRETATION:
--------------
The chart answers: "What proportion of our satellite constellation actually 
gets used during the simulation?" 

Low percentages indicate high contention from the satellite's perspective - 
many satellites are "starved" and never get to communicate with ground stations.
This is wasteful and suggests the link policy or constellation design needs 
improvement.

Chart Structure:
----------------
X-axis: Strategy groups (Close, Orbit, Frame, Close-Orbit)
        Each group shows results for different constellation sizes (1, 50, 100, 200)
Y-axis: Percentage of satellites contacted (0-100%)
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
SCRIPT_DIR = Path(__file__).parent.absolute()
OUTPUT_DIR = SCRIPT_DIR / "constellation_analysis" / "satellite_utilization"

# Constants
STRATEGIES_MAP = {
    "close-spaced": "Close",
    "orbit-spaced": "Orbit",
    "frame-spaced": "Frame",
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

def calculate_utilization_percentage(configs: List[Dict]) -> Dict:
    """
    Calculate the percentage of satellites contacted for each configuration.
    Returns nested dict: {image_size: {strategy: {constellation_size: {policy: percentage}}}}
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
        
        # Calculate utilization
        contacted_sats, total_sats = get_contacted_satellites(strategy_folder, policy)
        
        if total_sats > 0:
            utilization_pct = (len(contacted_sats) / total_sats) * 100.0
        else:
            utilization_pct = 0.0
        
        results[image_size][strategy][num_sats][policy] = utilization_pct
        
        print(f"  {STRATEGIES_MAP.get(strategy, strategy):12s} | "
              f"Size {num_sats:3d} | {policy:10s} | "
              f"{len(contacted_sats):3d}/{total_sats:3d} sats contacted ({utilization_pct:5.1f}%)")
    
    return results

def plot_utilization_charts(results: Dict):
    """Create grouped bar charts showing satellite utilization percentage"""
    
    OUTPUT_DIR.mkdir(exist_ok=True)
    
    # Create one chart per image size
    for image_size in sorted(results.keys()):
        fig, ax = plt.subplots(figsize=(20, 10))
        
        strategies = list(STRATEGIES_MAP.keys())
        num_policies = len(POLICIES)
        
        # Bar positioning - each strategy/constellation combo gets 4 bars (one per policy)
        bar_width = 0.18
        policy_group_width = num_policies * bar_width
        strategy_spacing = 0.3
        
        x_offset = 0
        x_positions_for_labels = []
        
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
                        utilization = 0
                    else:
                        utilization = strategy_data[sat_count][policy]
                    
                    x_pos = x_offset + policy_idx * bar_width
                    
                    ax.bar(x_pos, utilization, bar_width,
                          color=POLICY_COLORS[policy],
                          edgecolor='black',
                          linewidth=0.5,
                          label=policy.upper() if strategy_idx == 0 and sat_count == CONSTELLATION_SIZES[0] else "")
                
                # Mark the center of this group for labeling
                x_positions_for_labels.append((x_offset + policy_group_width/2, f"{sat_count}"))
                x_offset += policy_group_width + 0.1  # small gap between constellation sizes
            
            # Add extra spacing between strategies
            x_offset += strategy_spacing
        
        # Remove x-axis tick labels for cleaner look
        ax.set_xticks([])
        
        # Add only strategy group labels at the bottom
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
            
            ax.text(x_center, -5, STRATEGIES_MAP[strategy], 
                   ha='center', va='top', fontsize=14, fontweight='bold')
            
            x_offset += strategy_width + strategy_spacing
        
        # Styling
        ax.set_ylabel('Satellite Utilization (%)', fontsize=14, fontweight='bold')
        ax.set_title(f'Satellite Utilization by Strategy & Policy\n'
                    f'Image Size: {image_size} KB | Each strategy shows 5 constellation sizes (1, 25, 50, 100, 200 sats)',
                    fontsize=16, fontweight='bold', pad=20)
        
        ax.set_ylim(0, 108)
        ax.grid(axis='y', alpha=0.3, linestyle='--')
        ax.set_axisbelow(True)
        
        # Add 100% reference line
        ax.axhline(y=100, color='gray', linestyle='--', linewidth=1.5, alpha=0.6)
        ax.text(ax.get_xlim()[1] * 0.98, 101, '100% (Full Utilization)', ha='right', va='bottom', 
               fontsize=10, color='gray', fontweight='bold')
        
        # Add annotation highlighting satellite starvation in close-spaced configurations
        if 'close-spaced' in results[image_size]:
            close_data = results[image_size]['close-spaced']
            if 200 in close_data and 'sticky' in close_data[200]:
                sticky_util = close_data[200]['sticky']
                if sticky_util < 30:  # Significant starvation
                    ax.text(0.02, 0.98, 
                           f'⚠️ Satellite Starvation Alert:\n'
                           f'Close-spaced + STICKY policy shows only {sticky_util:.1f}% utilization\n'
                           f'for 200-satellite constellation',
                           transform=ax.transAxes,
                           fontsize=11, 
                           verticalalignment='top',
                           bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.8),
                           fontweight='bold')
        
        # Legend - compact horizontal layout
        handles, labels = ax.get_legend_handles_labels()
        # Remove duplicate labels
        by_label = dict(zip(labels, handles))
        ax.legend(by_label.values(), by_label.keys(), 
                 loc='upper right', ncol=4, framealpha=0.9, fontsize=11, 
                 title='Policy', title_fontsize=11, frameon=True, shadow=False)
        
        plt.tight_layout()
        
        output_file = OUTPUT_DIR / f'satellite_utilization_comparison_{image_size}kb.png'
        plt.savefig(output_file, dpi=150, bbox_inches='tight')
        print(f"\n✅ Saved: {output_file}")
        plt.close()

def plot_utilization_by_policy(results: Dict):
    """
    Create separate subplots for each policy, showing utilization across strategies.
    This makes it easier to compare policies directly.
    """
    
    OUTPUT_DIR.mkdir(exist_ok=True)
    
    for image_size in sorted(results.keys()):
        fig, axes = plt.subplots(2, 2, figsize=(18, 14))
        axes = axes.flatten()
        
        strategies = list(STRATEGIES_MAP.keys())
        
        for policy_idx, policy in enumerate(POLICIES):
            ax = axes[policy_idx]
            
            # Prepare data for this policy
            x_labels = []
            utilizations = []
            colors = []
            
            for strategy in strategies:
                if strategy not in results[image_size]:
                    continue
                
                strategy_data = results[image_size][strategy]
                
                for sat_count in CONSTELLATION_SIZES:
                    if sat_count not in strategy_data:
                        continue
                    
                    if policy in strategy_data[sat_count]:
                        label = f"{STRATEGIES_MAP[strategy]}-{sat_count}"
                        x_labels.append(label)
                        utilizations.append(strategy_data[sat_count][policy])
                        colors.append(POLICY_COLORS[policy])
            
            # Plot bars
            x_pos = np.arange(len(x_labels))
            ax.bar(x_pos, utilizations, color=colors, edgecolor='black', linewidth=0.5, alpha=0.8)
            
            ax.set_xticks(x_pos)
            ax.set_xticklabels(x_labels, rotation=45, ha='right', fontsize=9)
            ax.set_ylabel('Utilization (%)', fontsize=12, fontweight='bold')
            ax.set_title(f'{policy.upper()} Policy', fontsize=14, fontweight='bold')
            ax.set_ylim(0, 105)
            ax.grid(axis='y', alpha=0.3, linestyle='--')
            ax.set_axisbelow(True)
            ax.axhline(y=100, color='red', linestyle='--', linewidth=1, alpha=0.5)
        
        fig.suptitle(f'Satellite Utilization Comparison by Policy\n'
                    f'Image Size: {image_size} KB',
                    fontsize=18, fontweight='bold')
        
        plt.tight_layout(rect=[0, 0, 1, 0.97])
        
        output_file = OUTPUT_DIR / f'satellite_utilization_by_policy_{image_size}kb.png'
        plt.savefig(output_file, dpi=150, bbox_inches='tight')
        print(f"✅ Saved: {output_file}")
        plt.close()

def main():
    print("=" * 80)
    print("SATELLITE UTILIZATION ANALYSIS")
    print("Calculating percentage of satellites contacted during simulation")
    print("=" * 80)
    
    # Scan for all configurations
    configs = scan_all_configurations()
    
    if not configs:
        print("❌ No constellation_analysis folders found!")
        return
    
    print(f"\n✅ Found {len(configs)} configurations\n")
    
    # Calculate utilization percentages
    print("Calculating satellite utilization...\n")
    results = calculate_utilization_percentage(configs)
    
    # Create visualizations
    print("\nGenerating charts...")
    plot_utilization_charts(results)
    plot_utilization_by_policy(results)
    
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
                        avg_util = np.mean(list(results[image_size][strategy][sat_count].values()))
                        print(f"      Size {sat_count:3d}: {avg_util:5.1f}% average utilization")

if __name__ == '__main__':
    main()
