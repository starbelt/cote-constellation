#!/usr/bin/env python3
"""
Chart 1: Communication Pattern Time Series - Satellite "Flipping" Visualization

Shows how different link policies cause satellites to switch on/off during communication.
This is the "flipping" chart that visualizes policy-driven satellite switching patterns.
"""

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from pathlib import Path
from datetime import datetime, timedelta
import seaborn as sns

# Configuration
SCRIPT_DIR = Path(__file__).parent.absolute()
LOGS_DIR = SCRIPT_DIR / "logs"
POLICIES = ["sticky", "fifo", "roundrobin", "random"]
TOP_SATELLITES = 5  # Show top 5 most active satellites + ground station

def read_config():
    """Read simulation configuration"""
    config = {}
    
    # Sensor config
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
                            config['frame_spacing'] = float(values[i])
    
    return config

def parse_communication_data(policy):
    """Parse tx-rx logs to extract communication patterns as continuous 0-1 lines"""
    policy_dir = LOGS_DIR / policy
    tx_rx_file = policy_dir / "meas-downlink-tx-rx.csv"
    
    if not tx_rx_file.exists():
        return None, None
        
    # Read tx-rx data
    df = pd.read_csv(tx_rx_file)
    
    # Handle the empty third column
    if len(df.columns) == 3:
        df = df.iloc[:, :2]  # Keep only first two columns
    
    df.columns = ['timestamp', 'satellite']
    df['timestamp'] = pd.to_datetime(df['timestamp'])
    
    # Convert to relative time (hours from start)
    start_time = df['timestamp'].min()
    df['hours'] = (df['timestamp'] - start_time).dt.total_seconds() / 3600
    
    # Ground station state: 1 when communicating, 0 when idle (continuous line)
    df['ground_station_active'] = df['satellite'].apply(lambda x: 0 if pd.isna(x) or x == 'None' else 1)
    
    # Find most active satellites for this policy
    active_data = df[df['satellite'] != 'None']
    if len(active_data) == 0:
        return df[['hours', 'ground_station_active']], {}
        
    satellite_counts = active_data['satellite'].value_counts()
    top_sats = satellite_counts.head(TOP_SATELLITES).index.tolist()
    
    # Create continuous 0-1 lines for each satellite
    satellite_data = {}
    for sat in top_sats:
        # Create binary communication state: 1 when this satellite is active, 0 otherwise
        df[f'sat_{sat}'] = df['satellite'].apply(lambda x: 1 if x == sat else 0)
        satellite_data[sat] = df[['hours', f'sat_{sat}']].copy()
    
    ground_station_data = df[['hours', 'ground_station_active']].copy()
    
    return ground_station_data, satellite_data

def create_communication_pattern_chart(output_dir=None):
    """Create Chart 1: Communication Pattern Time Series"""
    
    # Set up the plot style
    plt.style.use('default')
    sns.set_palette("husl")
    
    fig, axes = plt.subplots(2, 2, figsize=(20, 12))
    fig.suptitle('Communication Pattern Time Series - Satellite "Flipping" Visualization', 
                 fontsize=16, fontweight='bold', y=0.95)
    
    # Color scheme
    colors = {
        'ground_station': '#2C3E50',  # Dark blue-gray
        'satellites': ['#E74C3C', '#3498DB', '#2ECC71', '#F39C12', '#9B59B6']  # Distinct colors
    }
    
    for i, policy in enumerate(POLICIES):
        ax = axes[i // 2, i % 2]
        
        print(f"Processing {policy} policy...")
        
        # Parse communication data
        ground_data, satellite_data = parse_communication_data(policy)
        
        if ground_data is None or not satellite_data:
            ax.text(0.5, 0.5, f'No data for {policy}', 
                   transform=ax.transAxes, ha='center', va='center', fontsize=12)
            ax.set_title(f'{policy.upper()} Policy\nNo Communication Data', fontweight='bold')
            continue
        
        # Plot ground station activity (bottom line - continuous 0-1)
        ax.plot(ground_data['hours'], ground_data['ground_station_active'], 
               color=colors['ground_station'], linewidth=2, label='Ground Station', 
               alpha=0.9, drawstyle='steps-post')
        
        # Plot individual satellite lines (stacked above ground station)
        y_offset = 1.2  # Start above ground station line
        satellite_names = list(satellite_data.keys())
        
        for j, (sat_id, sat_data) in enumerate(satellite_data.items()):
            if j >= TOP_SATELLITES:  # Limit to top satellites
                break
                
            # Offset each satellite line vertically for visual separation
            y_pos = y_offset + (j * 1.2)
            
            # Create continuous 0-1 line shifted to this satellite's y-position
            sat_line = sat_data[f'sat_{sat_id}'] + y_pos
            
            # Plot continuous line showing satellite active (y_pos+1) vs inactive (y_pos)
            ax.plot(sat_data['hours'], sat_line, 
                   color=colors['satellites'][j % len(colors['satellites'])], 
                   linewidth=2, label=f'Sat {sat_id[-1] if len(sat_id) > 10 else sat_id}', 
                   alpha=0.8, drawstyle='steps-post')
        
        # Customize the subplot
        ax.set_xlabel('Time (hours)', fontweight='bold')
        ax.set_ylabel('Communication State (0=Idle, 1=Active)', fontweight='bold')
        ax.set_title(f'{policy.upper()} Policy\nSatellite Line Chart (0-1 States)', fontweight='bold')
        ax.grid(True, alpha=0.3)
        
        # Set y-axis to show clear 0-1 transitions for each line
        max_y = y_offset + len(satellite_data) * 1.2 + 0.5
        ax.set_ylim(-0.1, max_y)
        
        # Add horizontal reference lines at each satellite's baseline
        for j in range(len(satellite_data)):
            y_ref = y_offset + (j * 1.2)
            ax.axhline(y=y_ref, color='gray', linestyle='--', alpha=0.3, linewidth=0.5)
        ax.set_ylabel('Communication State (0=Idle, 1=Active)', fontweight='bold')
        ax.set_title(f'{policy.upper()} Policy\nSatellite Line Chart (0-1 States)', fontweight='bold')
        ax.grid(True, alpha=0.3)
        
        # Set y-axis to show clear 0-1 transitions for each line
        max_y = y_offset + len(satellite_data) * 1.2 + 0.5
        ax.set_ylim(-0.1, max_y)
        
        # Add horizontal reference lines at each satellite's baseline
        for j in range(len(satellite_data)):
            y_ref = y_offset + (j * 1.2)
            ax.axhline(y=y_ref, color='gray', linestyle='--', alpha=0.3, linewidth=0.5)
        
        # Legend with smaller font - positioned to not overlap lines
        if len(satellite_data) <= 3:
            ax.legend(bbox_to_anchor=(1.05, 1), loc='upper left', fontsize=8)
        else:
            ax.legend(bbox_to_anchor=(1.05, 0.5), loc='center left', fontsize=8)
    
    # Adjust layout
    plt.tight_layout()
    
    # Save plot
    if output_dir is None:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_dir = SCRIPT_DIR / f"communication_pattern_analysis_{timestamp}"
        output_dir.mkdir(exist_ok=True)
    
    output_file = output_dir / "communication_pattern_flipping.png"
    plt.savefig(output_file, dpi=300, bbox_inches='tight', facecolor='white')
    plt.close()
    
    print(f"✅ Communication pattern chart saved: {output_file}")
    return output_file

def main():
    """Generate Chart 1: Communication Pattern Time Series"""
    print("=" * 60)
    print("CHART 1: COMMUNICATION PATTERN TIME SERIES")
    print("=" * 60)
    print("Generating satellite 'flipping' visualization...")
    
    config = read_config()
    print(f"Configuration: {config}")
    
    # Create the communication pattern chart
    output_file = create_communication_pattern_chart()
    
    print("\n🎯 Chart 1 Analysis Complete!")
    print(f"📊 Generated: {output_file.name}")
    print("\n💡 This chart shows:")
    print("  • Ground station idle/active periods (bottom continuous line: 0=idle, 1=active)")
    print("  • Individual satellite communication lines (each satellite gets own line)")
    print("  • Continuous 0-1 state transitions showing exact 'flipping' moments")
    print("  • Policy-driven line switching patterns:")
    print("    - Round Robin: Regular ~30s line transitions between satellites")
    print("    - Sticky: One satellite line stays at 1, others remain at 0")
    print("    - FIFO: Queue-based line switching")
    print("    - Random: Irregular line state changes")
    print("  • Precise timing of state changes for detailed examination")
    print("  • Smooth line transitions ideal for zooming and analysis")

if __name__ == "__main__":
    main()
