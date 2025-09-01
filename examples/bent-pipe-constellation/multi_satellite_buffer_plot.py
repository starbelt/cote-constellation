#!/usr/bin/env python3
"""
Multi-Satellite Buffer Analysis

Plot buffer levels over time for the top 10 satellites for each policy,
with orbital passes shaded in green.
"""

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from pathlib import Path

# Configuration
LOGS_DIR = Path("logs")
POLICIES = ["greedy", "fifo", "roundrobin", "random"]
TOP_N_SATELLITES = 10

def get_top_satellites_by_policy(policy, top_n=10):
    """Get the top N satellites by total data downloaded for a policy"""
    policy_dir = LOGS_DIR / policy
    tx_rx_file = policy_dir / "meas-downlink-tx-rx.csv"
    mbps_file = policy_dir / "meas-downlink-Mbps.csv"
    
    if not tx_rx_file.exists() or not mbps_file.exists():
        print(f"Warning: Log files not found for {policy} policy")
        return []
    
    # Load connection and throughput data
    tx_rx_df = pd.read_csv(tx_rx_file)
    mbps_df = pd.read_csv(mbps_file)
    
    # Handle CSV structure
    if 'time' in tx_rx_df.columns:
        tx_rx_df = tx_rx_df[['time', 'downlink-tx-rx']]
        tx_rx_df.columns = ["timestamp", "satellite"]
        mbps_df = mbps_df[['time', 'downlink-Mbps']]
        mbps_df.columns = ["timestamp", "mbps"]
    else:
        tx_rx_df.columns = ["timestamp", "satellite"]
        mbps_df.columns = ["timestamp", "mbps"]
    
    # Convert timestamps
    tx_rx_df["timestamp"] = pd.to_datetime(tx_rx_df["timestamp"])
    mbps_df["timestamp"] = pd.to_datetime(mbps_df["timestamp"])
    mbps_df["mbps"] = pd.to_numeric(mbps_df["mbps"], errors='coerce')
    
    # Calculate total data per satellite
    satellite_totals = {}
    
    for i, row in tx_rx_df.iterrows():
        sat = row["satellite"]
        if sat != "None":
            # Find corresponding throughput
            mbps_row = mbps_df[mbps_df["timestamp"] == row["timestamp"]]
            if not mbps_row.empty:
                mbps = mbps_row.iloc[0]["mbps"]
                data_mb = mbps * 100 / 8  # Convert to MB (100s time step, 8 bits/byte)
                
                if sat not in satellite_totals:
                    satellite_totals[sat] = 0
                satellite_totals[sat] += data_mb
    
    # Get top N satellites
    sorted_sats = sorted(satellite_totals.items(), key=lambda x: x[1], reverse=True)
    top_satellites = [sat_id for sat_id, _ in sorted_sats[:top_n]]
    
    print(f"{policy}: Top {top_n} satellites by data downloaded:")
    for i, (sat_id, total_mb) in enumerate(sorted_sats[:top_n]):
        print(f"  {i+1:2d}. {sat_id:15s}: {total_mb:6.0f} MB")
    
    return top_satellites

def load_satellite_buffer_data(policy, satellite_id):
    """Load buffer data for a specific satellite"""
    # Extract numeric satellite ID from string like "60518000-0"
    if isinstance(satellite_id, str) and "-" in satellite_id:
        sat_num = satellite_id.split("-")[0]
    else:
        sat_num = str(satellite_id)
    
    policy_dir = LOGS_DIR / policy
    buffer_file = policy_dir / f"meas-MB-buffered-sat-{int(sat_num):010d}.csv"
    
    if not buffer_file.exists():
        print(f"Warning: Buffer file not found for satellite {sat_num} in {policy} policy")
        return None
    
    # Load buffer data
    buffer_df = pd.read_csv(buffer_file)
    
    if 'time' in buffer_df.columns:
        buffer_col = [col for col in buffer_df.columns if 'MB-buffered' in col][0]
        buffer_df = buffer_df[['time', buffer_col]]
        buffer_df.columns = ["timestamp", "buffer_mb"]
    else:
        buffer_df.columns = ["timestamp", "buffer_mb"]
    
    # Convert timestamp to datetime, then to numeric hours since start
    buffer_df["timestamp"] = pd.to_datetime(buffer_df["timestamp"])
    start_time = buffer_df["timestamp"].min()
    buffer_df["hours"] = (buffer_df["timestamp"] - start_time).dt.total_seconds() / 3600
    buffer_df["buffer_mb"] = pd.to_numeric(buffer_df["buffer_mb"], errors='coerce')
    
    return buffer_df

def get_all_satellites_across_policies():
    """Get all satellites that appear in any policy's connection logs"""
    all_satellites = set()
    
    for policy in POLICIES:
        policy_dir = LOGS_DIR / policy
        tx_rx_file = policy_dir / "meas-downlink-tx-rx.csv"
        
        if not tx_rx_file.exists():
            continue
            
        tx_rx_df = pd.read_csv(tx_rx_file)
        
        if 'time' in tx_rx_df.columns:
            tx_rx_df = tx_rx_df[['time', 'downlink-tx-rx']]
            tx_rx_df.columns = ["timestamp", "satellite"]
        else:
            tx_rx_df.columns = ["timestamp", "satellite"]
        
        # Get unique satellites (excluding None)
        policy_satellites = set(tx_rx_df[tx_rx_df["satellite"] != "None"]["satellite"].unique())
        all_satellites.update(policy_satellites)
    
    return sorted(list(all_satellites))

def get_satellite_orbital_passes_all_policies(satellite_id):
    """Get orbital pass times for a satellite across all policies (should be the same)"""
    # Use the first available policy to determine orbital passes
    # (they should be the same across all policies since orbital mechanics don't change)
    
    for policy in POLICIES:
        policy_dir = LOGS_DIR / policy
        tx_rx_file = policy_dir / "meas-downlink-tx-rx.csv"
        
        if not tx_rx_file.exists():
            continue
        
        tx_rx_df = pd.read_csv(tx_rx_file)
        
        if 'time' in tx_rx_df.columns:
            tx_rx_df = tx_rx_df[['time', 'downlink-tx-rx']]
            tx_rx_df.columns = ["timestamp", "satellite"]
        else:
            tx_rx_df.columns = ["timestamp", "satellite"]
        
        tx_rx_df["timestamp"] = pd.to_datetime(tx_rx_df["timestamp"])
        start_time = tx_rx_df["timestamp"].min()
        tx_rx_df["hours"] = (tx_rx_df["timestamp"] - start_time).dt.total_seconds() / 3600
        
        # Check if this satellite appears in this policy
        sat_connections = tx_rx_df[tx_rx_df["satellite"] == satellite_id].copy()
        
        if not sat_connections.empty:
            # Found the satellite in this policy, determine its orbital passes
            passes = []
            current_pass_start = None
            last_time = None
            
            for _, row in sat_connections.iterrows():
                current_time = row["hours"]
                
                if last_time is None or (current_time - last_time) > 0.5:  # Gap of more than 0.5 hours indicates new orbital pass
                    # Start new pass
                    if current_pass_start is not None:
                        passes.append((current_pass_start, last_time))
                    current_pass_start = current_time
                
                last_time = current_time
            
            # Close final pass
            if current_pass_start is not None:
                passes.append((current_pass_start, last_time))
            
            return passes
    
    return []  # Satellite not found in any policy

def plot_multi_satellite_buffer_comparison(output_dir):
    """Create buffer comparison plot for top satellites across all policies"""
    
    # Get all satellites that appear across all policies
    all_satellites = get_all_satellites_across_policies()
    print(f"Found {len(all_satellites)} total satellites across all policies")
    print(f"Satellites: {all_satellites}")
    
    # Use the first 10 satellites (or all if fewer than 10)
    selected_satellites = all_satellites[:TOP_N_SATELLITES]
    print(f"Selected {len(selected_satellites)} satellites for comparison: {selected_satellites}")
    
    fig, axes = plt.subplots(2, 2, figsize=(20, 16))
    fig.suptitle(f'Buffer Levels Over Time - Same {len(selected_satellites)} Satellites Across All Policies\n(Green = Orbital Passes)', 
                 fontsize=16, fontweight='bold')
    
    colors = plt.cm.tab10(np.linspace(0, 1, len(selected_satellites)))
    
    for i, policy in enumerate(POLICIES):
        row = i // 2
        col = i % 2
        ax = axes[row, col]
        
        print(f"\n=== Processing {policy.upper()} policy ===")
        
        # Plot buffer levels for the selected satellites
        satellites_plotted = 0
        for j, satellite_id in enumerate(selected_satellites):
            color = colors[j]
            
            # Load buffer data
            buffer_df = load_satellite_buffer_data(policy, satellite_id)
            if buffer_df is None:
                print(f"  No buffer data for satellite {satellite_id} in {policy}")
                continue
            
            # Extract satellite number for display
            if isinstance(satellite_id, str) and "-" in satellite_id:
                sat_display = satellite_id.split("-")[0]
            else:
                sat_display = str(satellite_id)
            
            # Plot buffer level
            ax.plot(buffer_df['hours'], buffer_df['buffer_mb'], 
                   color=color, linewidth=1.5, alpha=0.8, 
                   label=f'Sat {sat_display}')
            
            satellites_plotted += 1
        
        # Add orbital passes for all selected satellites (should be the same regardless of policy)
        print(f"  Adding orbital passes...")
        pass_times_added = set()  # To avoid duplicate shading
        for satellite_id in selected_satellites:
            passes = get_satellite_orbital_passes_all_policies(satellite_id)
            for pass_start, pass_end in passes:
                pass_key = (round(pass_start, 2), round(pass_end, 2))
                if pass_key not in pass_times_added:
                    ax.axvspan(pass_start, pass_end, alpha=0.1, color='green')
                    pass_times_added.add(pass_key)
        
        # Add a single label for orbital passes
        if pass_times_added:
            ax.axvspan(0, 0, alpha=0.0, color='green', label=f'Orbital Passes ({len(pass_times_added)})')
        
        ax.set_xlabel('Time (hours)')
        ax.set_ylabel('Buffer (MB)')
        ax.set_title(f'{policy.upper()} Policy ({satellites_plotted} satellites)')
        ax.grid(True, alpha=0.3)
        ax.legend(bbox_to_anchor=(1.05, 1), loc='upper left', fontsize=8)
    
    plt.tight_layout()
    plt.savefig(output_dir / "multi_satellite_buffer_comparison_fixed.png", dpi=300, bbox_inches='tight')
    plt.close()
    
    print(f"\nFixed multi-satellite buffer comparison plot saved!")

def main():
    print("MULTI-SATELLITE BUFFER COMPARISON")
    print("==================================")
    
    if not LOGS_DIR.exists():
        print(f"Error: Logs directory {LOGS_DIR} does not exist!")
        return
    
    # Create output directory
    output_dir = Path("orbital_analysis_output")
    output_dir.mkdir(exist_ok=True)
    
    # Create the comparison plot
    plot_multi_satellite_buffer_comparison(output_dir)
    
    print(f"\nAnalysis complete! Check {output_dir}/multi_satellite_buffer_comparison.png")

if __name__ == "__main__":
    main()
