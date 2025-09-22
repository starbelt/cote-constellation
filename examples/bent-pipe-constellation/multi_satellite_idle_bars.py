#!/usr/bin/env python3
"""
Multi-Satellite Idle Time Bar Charts

Creates detailed bar charts showing idle time distribution across satellites
for each spacing strategy with policies as bars within each chart.
"""

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from pathlib import Path
from datetime import datetime
import zipfile
import tempfile
import shutil

# Configuration - use absolute paths
SCRIPT_DIR = Path(__file__).parent.absolute()
LOGS_DIR = SCRIPT_DIR / "logs"
POLICIES = ["sticky", "fifo", "roundrobin", "random"]
SPACING_STRATEGIES = ["close-spaced", "close-orbit-spaced", "frame-spaced", "orbit-spaced"]

def read_config():
    """Read simulation configuration"""
    config = {}
    
    # Sensor config - use absolute path
    sensor_file = SCRIPT_DIR / "configuration/sensor.dat"
    if sensor_file.exists():
        with open(sensor_file, 'r') as f:
            lines = f.readlines()
            if len(lines) >= 2:
                header = lines[0].strip().split(',')
                values = lines[1].strip().split(',')
                for i, key in enumerate(header):
                    if i < len(values) and key == 'bits-per-sense':
                        config['mb_per_sense'] = int(values[i]) / (8 * 1024 * 1024)
    
    # Constellation config
    constellation_file = SCRIPT_DIR / "configuration/constellation.dat"
    if constellation_file.exists():
        with open(constellation_file, 'r') as f:
            lines = f.readlines()
            if len(lines) >= 2:
                header = lines[0].strip().split(',')
                values = lines[1].strip().split(',')
                for i, key in enumerate(header):
                    if i < len(values):
                        if key == 'count':
                            config['satellite_count'] = int(values[i])
                        elif key == 'second':
                            # Frame spacing in seconds
                            config['frame_spacing'] = float(values[i]) + float(values[i+1]) / 1e9 if i+1 < len(values) else float(values[i])
    
    return config

def find_latest_constellation_analysis_folder():
    """Find the most recent constellation_analysis_* folder"""
    # Look for constellation_analysis_* folders in parent directories
    current_dir = SCRIPT_DIR
    
    while current_dir != current_dir.parent:
        constellation_folders = [f for f in current_dir.iterdir() 
                               if f.is_dir() and f.name.startswith('constellation_analysis_')]
        
        if constellation_folders:
            # Sort by modification time (newest first)
            latest_folder = max(constellation_folders, key=lambda x: x.stat().st_mtime)
            print(f"Using latest analysis folder: {latest_folder.name}")
            return latest_folder
        
        current_dir = current_dir.parent
    
    print("No constellation_analysis_* folder found!")
    return None

def get_idle_data_for_strategy(strategy, constellation_folder):
    """Extract idle time data for a specific strategy from constellation analysis folder"""
    strategy_folder = constellation_folder / strategy
    if not strategy_folder.exists():
        print(f"  Strategy folder not found: {strategy}")
        return {}
    
    simulation_logs_zip = strategy_folder / "simulation_logs.zip"
    if not simulation_logs_zip.exists():
        print(f"  No simulation_logs.zip found for {strategy}")
        return {}
    
    idle_results = {}
    
    # Extract and process each policy
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        
        # Extract the ZIP file
        with zipfile.ZipFile(simulation_logs_zip, 'r') as zip_file:
            zip_file.extractall(temp_path)
        
        # Process each policy subdirectory
        for policy in POLICIES:
            policy_dir = temp_path / policy
            if not policy_dir.exists():
                print(f"    Policy {policy} not found for {strategy}")
                continue
            
            # Calculate idle time for this policy
            policy_idle_data = calculate_idle_time_for_policy(policy_dir)
            if policy_idle_data:
                idle_results[policy] = policy_idle_data
    
    return idle_results

def calculate_idle_time_for_policy(policy_dir):
    """Calculate idle time data for a specific policy directory
    
    Simplified approach: Count time periods where buffer <= 0.001 MB
    This approximates 'idle' periods where satellites have no data to transmit.
    The reference logic includes connection state, but for aggregate analysis
    this buffer-based approach provides a good proxy for idle behavior.
    """
    # Find all buffer measurement files
    buffer_files = list(policy_dir.glob("meas-MB-buffered-sat-*.csv"))
    
    if not buffer_files:
        return {}
    
    idle_data = {}
    
    for buffer_file in buffer_files:
        try:
            # Extract satellite ID from filename
            sat_id_str = buffer_file.name.split('-')[-1].replace('.csv', '')
            sat_id = int(sat_id_str)
            
            # Read buffer data
            df = pd.read_csv(buffer_file)
            
            if df.empty:
                idle_data[sat_id] = 0
                continue
            
            # Parse buffer data
            df.columns = ['timestamp', 'buffer_mb'] + list(df.columns[2:])
            df['buffer_mb'] = pd.to_numeric(df['buffer_mb'], errors='coerce')
            
            # Count periods where buffer <= 0.001 (essentially empty)
            idle_mask = df['buffer_mb'] <= 0.001
            
            # For more accuracy, also check previous buffer state like reference
            # Idle when current AND previous buffer are both low
            prev_buffer_low = df['buffer_mb'].shift(1) <= 0.001
            
            # True idle: both current and previous buffer are low
            true_idle_mask = idle_mask & prev_buffer_low.fillna(True)  # First record defaults to True
            
            idle_count = true_idle_mask.sum()
            idle_data[sat_id] = idle_count
                
        except Exception as e:
            print(f"    Error processing {buffer_file.name}: {e}")
            idle_data[sat_id] = 0
            continue
    
    return idle_data

def get_policy_dirs():
    """Get policy directories (legacy function for backward compatibility)"""
    dirs = {}
    for policy in POLICIES:
        policy_dir = LOGS_DIR / policy
        if policy_dir.exists():
            dirs[policy] = policy_dir
    return dirs

def get_active_satellites():
    """Get satellites that have any downlink activity (legacy function)"""
    policy_dirs = get_policy_dirs()
    all_satellites = set()
    
    for policy, policy_dir in policy_dirs.items():
        tx_rx_file = policy_dir / "meas-downlink-tx-rx.csv"
        if tx_rx_file.exists():
            tx_rx_df = pd.read_csv(tx_rx_file)
            tx_rx_df = tx_rx_df.iloc[:, :2]
            tx_rx_df.columns = ["timestamp", "satellite"]
            
            # Get unique satellites (excluding None/NaN)
            satellites = tx_rx_df["satellite"].dropna()
            satellites = satellites[satellites != "None"]
            all_satellites.update(satellites.unique())
    
    return sorted(list(all_satellites))

def create_bar_chart_for_strategy(strategy, idle_results, config, output_dir):
    """Create bar chart for a specific strategy showing policy performance"""
    if not idle_results:
        print(f"  No data for strategy: {strategy}")
        return
    
    # Set consistent font family
    plt.rcParams['font.family'] = 'DejaVu Sans'
    plt.rcParams['font.sans-serif'] = ['DejaVu Sans', 'Arial', 'Helvetica', 'sans-serif']
    
    # Create figure
    fig, ax = plt.subplots(1, 1, figsize=(12, 8))
    
    # Calculate totals for each policy
    policy_totals = {}
    policy_satellites_affected = {}
    
    for policy in POLICIES:
        if policy not in idle_results:
            policy_totals[policy] = 0
            policy_satellites_affected[policy] = 0
            continue
            
        policy_data = idle_results[policy]
        total_idle_time = sum(policy_data.values())
        satellites_with_idle = len([sat for sat, idle_time in policy_data.items() if idle_time > 0])
        
        policy_totals[policy] = total_idle_time
        policy_satellites_affected[policy] = satellites_with_idle
    
    # Prepare data for plotting
    policies = POLICIES
    totals = [policy_totals[p] for p in policies]
    satellites_counts = [policy_satellites_affected[p] for p in policies]
    
    # Create colors - use policy-specific colors for consistency
    colors = {'sticky': '#CD5C5C', 'fifo': '#FF6347', 'roundrobin': '#FF8C00', 'random': '#FF4500'}
    bar_colors = [colors.get(policy.lower(), '#888888') for policy in policies]
    
    # Create the bar chart
    bars = ax.bar(policies, totals, color=bar_colors, alpha=0.8, edgecolor='black', linewidth=1)
    
    # Customize the plot
    strategy_display = strategy.replace('-', ' ').title()
    ax.set_ylabel('Total Idle Time (seconds)', fontweight='bold', fontsize=12)
    ax.set_xlabel('Scheduling Policy', fontweight='bold', fontsize=12)
    ax.set_title(f'Total Idle Time by Policy - {strategy_display} Strategy\n(Constellation Performance Comparison)', 
                fontweight='bold', fontsize=14, pad=20)
    
    # Add value labels on bars
    if totals and max(totals) > 0:
        for i, (bar, total, sat_count) in enumerate(zip(bars, totals, satellites_counts)):
            height = bar.get_height()
            # Show total seconds and satellite count
            ax.text(bar.get_x() + bar.get_width()/2., height + max(totals)*0.01,
                    f'{total:.1f}s\n({sat_count} sats)',
                    ha='center', va='bottom', fontweight='bold', fontsize=10)
    
    # Improve styling
    ax.grid(True, alpha=0.3, axis='y')
    ax.set_axisbelow(True)
    
    # Smart y-axis scaling
    if totals and max(totals) > 0:
        max_value = max(totals)
        ax.set_ylim(0, max_value * 1.15)
    
    # Style the plot
    for label in ax.get_xticklabels():
        label.set_fontweight('bold')
        label.set_family('DejaVu Sans')
    
    for label in ax.get_yticklabels():
        label.set_family('DejaVu Sans')
    
    plt.tight_layout()
    
    # Save the plot
    output_path = output_dir / f"idle_bars_{strategy}_strategy.png"
    plt.savefig(output_path, dpi=300, bbox_inches='tight', facecolor='white')
    plt.close()
    
    print(f"  Generated idle bar chart for {strategy} -> {output_path.name}")
    
    # Print ranking for this strategy (lower idle time is better)
    if any(totals):
        sorted_policies = sorted([(p, policy_totals[p]) for p in POLICIES], key=lambda x: x[1])
        ranking = " > ".join([policy.upper() for policy, total in sorted_policies if total >= 0])
        if ranking:
            print(f"  {strategy_display} strategy ranking (best to worst): {ranking}")

def create_bar_charts():
    """Create bar charts for all strategies"""
    print("Multi-Satellite Idle Time Bar Chart Analysis")
    
    constellation_folder = find_latest_constellation_analysis_folder()
    if not constellation_folder:
        return
    
    config = read_config()
    
    # Use the latest constellation analysis folder (same as generate_spacing_comparison.py)
    output_dir = find_latest_constellation_analysis_folder()
    
    print(f"Output directory: {output_dir.name}")
    
    # Process each strategy
    for strategy in SPACING_STRATEGIES:
        print(f"\nProcessing {strategy} strategy...")
        
        # Get idle data for this strategy
        idle_results = get_idle_data_for_strategy(strategy, constellation_folder)
        
        # Create bar chart for this strategy
        create_bar_chart_for_strategy(strategy, idle_results, config, output_dir)
    
    print(f"\nAll charts generated in: {output_dir}")
    print("Charts show total idle time per policy for each spacing strategy.")

def main():
    """Main function to run analysis"""
    create_bar_charts()

if __name__ == "__main__":
    main()
