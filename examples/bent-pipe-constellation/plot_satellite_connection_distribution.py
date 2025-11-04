#!/usr/bin/env python3
"""
Plot Satellite Connection Distribution: Which satellites get how many connections?

Shows the distribution of connections across satellites to reveal whether high 
utilization comes from many satellites being used fairly, or just a few satellites 
being used repeatedly.

KEY INSIGHT:
-----------
This visualization goes beyond "how many satellites get contacted" to show
"how are the connections distributed across satellites?"

Two scenarios can have similar utilization percentages but very different distributions:
1. 100% utilization with even distribution: All satellites get ~equal connections
2. 100% utilization with skewed distribution: A few satellites get most connections

Expected patterns:
- STICKY policy: Very skewed - a few satellites dominate all connections
- FIFO/ROUNDROBIN: More even distribution across satellites
- Close-spaced + any policy: Likely skewed towards nearest satellites
- Orbit-spaced: More even distribution as satellites pass over

Chart Structure:
----------------
Stacked bar chart where each bar represents a configuration:
- Bar height = total number of connections
- Each color segment = connections from a specific satellite
- More colors/segments = better distribution across satellites
- Few dominant colors = concentration on few satellites
"""

import pandas as pd
import matplotlib.pyplot as plt
import numpy as np
import zipfile
from pathlib import Path
from typing import Dict, List, Tuple
import sys
import re
from collections import Counter

# Configuration directories
BASE_DIR = Path(".")
OUTPUT_DIR = BASE_DIR / "comparison_charts"

# Constants
STRATEGIES_MAP = {
    "close-spaced": "Close",
    "orbit-spaced": "Orbit",
    "frame-spaced": "Frame",
    "close-orbit-spaced": "Close-Orbit"
}
CONSTELLATION_SIZES = [1, 50, 100, 200]
POLICIES = ["sticky", "fifo", "roundrobin", "random"]
POLICY_COLORS = {
    "sticky": "#d62728",
    "fifo": "#1f77b4",
    "roundrobin": "#2ca02c",
    "random": "#ff7f0e"
}

def scan_all_configurations(search_dir='.'):
    """Scan for all constellation_analysis folders and their strategy/policy subfolders"""
    configs = []
    
    search_path = Path(search_dir)
    # Search in current directory and subdirectories (especially results/)
    for constellation_folder in search_path.glob('**/constellation_analysis_*'):
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

def get_satellite_connection_counts(strategy_folder: Path, policy: str) -> Tuple[Dict[str, int], int]:
    """
    Get the number of connection SESSIONS each satellite had during the simulation.
    A session = continuous period connected to a satellite until it switches.
    Returns: (dict of {sat_id: session_count}, total_satellites)
    """
    zip_path = strategy_folder / 'simulation_logs.zip'
    
    if not zip_path.exists():
        return {}, 0
    
    sat_connection_sessions = Counter()
    total_sats = 0
    
    try:
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            # Look for the downlink tx-rx file for this policy
            downlink_file = f'{policy}/meas-downlink-tx-rx.csv'
            
            if downlink_file not in zip_ref.namelist():
                return {}, 0
            
            with zip_ref.open(downlink_file) as f:
                df = pd.read_csv(f)
                
                # Check for required column
                if 'downlink-tx-rx' not in df.columns:
                    return {}, 0
                
                # Count connection SESSIONS (each time we switch to a satellite)
                # Track when satellite ID changes
                prev_sat_id = None
                
                for link in df['downlink-tx-rx']:
                    if link == 'None' or pd.isna(link):
                        # No connection, reset tracking
                        prev_sat_id = None
                        continue
                    
                    if isinstance(link, str) and '-' in link:
                        sat_id = link.split('-')[0]
                        
                        # Count this as a new session if satellite changed
                        if sat_id != prev_sat_id:
                            sat_connection_sessions[sat_id] += 1
                            prev_sat_id = sat_id
            
            # Get total constellation size
            buffer_files = [f for f in zip_ref.namelist() if 'meas-MB-buffered-sat-' in f]
            all_sat_ids = set()
            for filename in buffer_files:
                parts = filename.split('sat-')
                if len(parts) > 1:
                    sat_id = parts[1].replace('.csv', '')
                    all_sat_ids.add(sat_id)
            
            total_sats = len(all_sat_ids)
                
    except Exception as e:
        print(f"    ⚠️  Error processing {zip_path}: {e}")
        return {}, 0
    
    return dict(sat_connection_sessions), total_sats

def calculate_connection_distribution(configs: List[Dict]) -> Dict:
    """
    Calculate connection distribution for each configuration.
    Returns nested dict: {image_size: {strategy: {constellation_size: {policy: connection_data}}}}
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
        
        # Get connection counts per satellite
        sat_connections, total_sats = get_satellite_connection_counts(strategy_folder, policy)
        
        total_connections = sum(sat_connections.values())
        num_contacted = len(sat_connections)
        
        results[image_size][strategy][num_sats][policy] = {
            'sat_connections': sat_connections,
            'total_connections': total_connections,
            'total_sats': total_sats,
            'contacted_sats': num_contacted
        }
        
        # Calculate distribution stats
        if sat_connections:
            connection_values = list(sat_connections.values())
            max_conn = max(connection_values)
            min_conn = min(connection_values)
            avg_conn = np.mean(connection_values)
            std_conn = np.std(connection_values)
            
            print(f"  {STRATEGIES_MAP.get(strategy, strategy):12s} | "
                  f"Size {num_sats:3d} | {policy:10s} | "
                  f"{num_contacted:3d}/{total_sats:3d} sats | "
                  f"Total: {total_connections:6d} sessions | "
                  f"Avg: {avg_conn:6.1f} | "
                  f"Max: {max_conn:5d} | "
                  f"Std: {std_conn:6.1f}")
        else:
            print(f"  {STRATEGIES_MAP.get(strategy, strategy):12s} | "
                  f"Size {num_sats:3d} | {policy:10s} | "
                  f"  0/{total_sats:3d} sats | No connections")
    
    return results

def plot_connection_distribution_stacked(results: Dict):
    """
    Create stacked bar charts showing how connections are distributed across satellites.
    Each segment represents a different satellite's contribution with satellite ID labeled.
    """
    
    OUTPUT_DIR.mkdir(exist_ok=True)
    
    # Focus on specific configurations that show the problem clearly
    # Start with 25 satellites for easier inspection
    target_sizes = [25]
    
    for image_size in sorted(results.keys()):
        for target_size in target_sizes:
            # Make figure much larger to accommodate all satellite labels
            fig, axes = plt.subplots(2, 2, figsize=(24, 18))
            axes = axes.flatten()
            
            strategies = list(STRATEGIES_MAP.keys())
            
            for policy_idx, policy in enumerate(POLICIES):
                ax = axes[policy_idx]
                
                # Collect data for this policy across strategies
                bar_labels = []
                bar_data_list = []
                
                for strategy in strategies:
                    if strategy not in results[image_size]:
                        continue
                    
                    strategy_data = results[image_size][strategy]
                    
                    if target_size not in strategy_data:
                        continue
                    
                    if policy not in strategy_data[target_size]:
                        continue
                    
                    data = strategy_data[target_size][policy]
                    sat_connections = data['sat_connections']
                    
                    bar_labels.append(STRATEGIES_MAP[strategy])
                    bar_data_list.append(sat_connections)
                
                # Create stacked bars
                x_pos = np.arange(len(bar_labels))
                bar_width = 0.7
                
                # For stacking, we need to sort satellites by connection count and assign colors
                # Use a colormap to show different satellites
                for idx, (label, sat_connections) in enumerate(zip(bar_labels, bar_data_list)):
                    if not sat_connections:
                        continue
                    
                    # Sort satellites by connection count (descending)
                    sorted_sats = sorted(sat_connections.items(), key=lambda x: x[1], reverse=True)
                    
                    # Create stacked segments - USE ALL SATELLITES
                    bottom = 0
                    
                    # Generate colors for ALL satellites
                    num_sats = len(sorted_sats)
                    if num_sats > 0:
                        # Use different colormaps for different amounts
                        if num_sats <= 20:
                            cmap = plt.cm.get_cmap('tab20')
                        else:
                            cmap = plt.cm.get_cmap('turbo')
                        colors = [cmap(i / max(num_sats - 1, 1)) for i in range(num_sats)]
                    else:
                        colors = []
                    
                    # Plot ALL satellites individually with labels
                    for sat_idx, (sat_id, count) in enumerate(sorted_sats):
                        # Draw the bar segment
                        bar = ax.bar(idx, count, bar_width, bottom=bottom, 
                                    color=colors[sat_idx], 
                                    edgecolor='white', linewidth=0.5)
                        
                        # Add satellite ID label on the bar segment if it's large enough
                        segment_center = bottom + count / 2
                        # Only label if segment is tall enough (>2% of total or >50 connections)
                        total_height = sum(c for _, c in sorted_sats)
                        if count / total_height > 0.02 or count > 50:
                            # Extract last 4 digits of satellite ID for cleaner labels
                            sat_label = sat_id[-4:]
                            ax.text(idx, segment_center, sat_label,
                                   ha='center', va='center', 
                                   fontsize=7, fontweight='bold',
                                   color='white' if sat_idx < num_sats/2 else 'black',
                                   bbox=dict(boxstyle='round,pad=0.2', 
                                           facecolor=colors[sat_idx], 
                                           edgecolor='none', alpha=0.7))
                        
                        bottom += count
                
                ax.set_xticks(x_pos)
                ax.set_xticklabels(bar_labels, fontsize=12, fontweight='bold')
                ax.set_ylabel('Connection Sessions', fontsize=13, fontweight='bold')
                ax.set_title(f'{policy.upper()} Policy', fontsize=15, fontweight='bold')
                ax.grid(axis='y', alpha=0.3, linestyle='--')
                ax.set_axisbelow(True)
            
            fig.suptitle(f'Satellite Connection Session Distribution by Strategy & Policy\n'
                        f'Image Size: {image_size} KB | Constellation Size: {target_size} satellites\n'
                        f'Each colored segment = one satellite (labeled with sat ID)\n'
                        f'Height = Number of times ground station connected to that satellite',
                        fontsize=17, fontweight='bold')
            
            plt.tight_layout(rect=[0, 0, 1, 0.96])
            
            output_file = OUTPUT_DIR / f'connection_distribution_stacked_{image_size}kb_{target_size}sats.png'
            plt.savefig(output_file, dpi=150, bbox_inches='tight')
            print(f"\n✅ Saved: {output_file}")
            plt.close()

def plot_connection_concentration_analysis(results: Dict):
    """
    Show concentration metrics: What % of connections come from top N satellites?
    This reveals whether connections are concentrated in few satellites or distributed.
    """
    
    OUTPUT_DIR.mkdir(exist_ok=True)
    
    target_sizes = [50, 200]
    
    for image_size in sorted(results.keys()):
        for target_size in target_sizes:
            fig, axes = plt.subplots(2, 2, figsize=(18, 14))
            axes = axes.flatten()
            
            strategies = list(STRATEGIES_MAP.keys())
            
            for policy_idx, policy in enumerate(POLICIES):
                ax = axes[policy_idx]
                
                # For each strategy, calculate what % of connections come from top satellites
                top_n_values = [1, 5, 10, 20]  # Top N satellites
                
                for strategy in strategies:
                    if strategy not in results[image_size]:
                        continue
                    
                    strategy_data = results[image_size][strategy]
                    
                    if target_size not in strategy_data:
                        continue
                    
                    if policy not in strategy_data[target_size]:
                        continue
                    
                    data = strategy_data[target_size][policy]
                    sat_connections = data['sat_connections']
                    total_connections = data['total_connections']
                    
                    if total_connections == 0:
                        continue
                    
                    # Sort satellites by connection count
                    sorted_sats = sorted(sat_connections.items(), key=lambda x: x[1], reverse=True)
                    
                    # Calculate cumulative percentage for top N
                    percentages = []
                    for n in top_n_values:
                        top_n_connections = sum(count for _, count in sorted_sats[:n])
                        pct = (top_n_connections / total_connections) * 100
                        percentages.append(pct)
                    
                    # Plot line
                    ax.plot(top_n_values, percentages, 'o-', 
                           linewidth=2, markersize=8,
                           label=STRATEGIES_MAP[strategy])
                
                ax.set_xlabel('Top N Satellites', fontsize=11, fontweight='bold')
                ax.set_ylabel('% of Total Connection Sessions', fontsize=11, fontweight='bold')
                ax.set_title(f'{policy.upper()} Policy', fontsize=13, fontweight='bold')
                ax.grid(True, alpha=0.3)
                ax.set_ylim(0, 105)
                ax.set_xticks(top_n_values)
                ax.legend(loc='lower right', fontsize=10)
                
                # Add reference line at 100%
                ax.axhline(y=100, color='gray', linestyle='--', linewidth=1, alpha=0.5)
            
            fig.suptitle(f'Connection Session Concentration Analysis\n'
                        f'Image Size: {image_size} KB | Constellation Size: {target_size} satellites\n'
                        f'Higher curves = More concentration (fewer satellites selected)',
                        fontsize=15, fontweight='bold')
            
            plt.tight_layout(rect=[0, 0, 1, 0.96])
            
            output_file = OUTPUT_DIR / f'connection_concentration_{image_size}kb_{target_size}sats.png'
            plt.savefig(output_file, dpi=150, bbox_inches='tight')
            print(f"✅ Saved: {output_file}")
            plt.close()

def main():
    print("=" * 80)
    print("SATELLITE CONNECTION DISTRIBUTION ANALYSIS")
    print("Analyzing how connections are distributed across satellites")
    print("=" * 80)
    
    # Scan for all configurations
    configs = scan_all_configurations()
    
    if not configs:
        print("❌ No constellation_analysis folders found!")
        return
    
    print(f"\n✅ Found {len(configs)} configurations\n")
    
    # Calculate connection distribution
    print("Calculating connection distribution per satellite...\n")
    results = calculate_connection_distribution(configs)
    
    # Create visualizations
    print("\nGenerating stacked bar charts...")
    plot_connection_distribution_stacked(results)
    
    print("\nGenerating concentration analysis charts...")
    plot_connection_concentration_analysis(results)
    
    print("\n" + "=" * 80)
    print("✅ ANALYSIS COMPLETE!")
    print("=" * 80)

if __name__ == '__main__':
    main()
