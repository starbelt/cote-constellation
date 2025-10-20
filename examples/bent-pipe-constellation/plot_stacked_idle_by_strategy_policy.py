#!/usr/bin/env python3
"""
Plot Stacked Bar Charts: IDLE TIME by Strategy & Policy

Grouped by Strategy, Stacked by Policy
X-axis: Strategy groups (Close, Orbit, Frame, Close-Orbit)
        Each group has 4 bars (one per constellation size: 1, 50, 100, 200)
Y-axis: Total idle time (hours)
Stacks: Each bar divided by 4 policies (STICKY, FIFO, ROUNDROBIN, RANDOM)
Result: 4 charts (one per image size)
        16 stacked bars per chart (4 strategies × 4 constellation sizes)

Idle Definition: buffer_mb > 0 AND connected = 0
                 (satellite has data but is not downloading)
"""

import pandas as pd
import matplotlib.pyplot as plt
import numpy as np
import zipfile
from pathlib import Path
from typing import Dict, List, Tuple
import sys
import re

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
    "sticky": "red",
    "fifo": "blue",
    "roundrobin": "green",
    "random": "orange"
}

def scan_all_configurations(search_dir='.'):
    """Scan for all constellation_analysis folders"""
    configs = []
    
    search_path = Path(search_dir)
    for folder in search_path.glob('constellation_analysis_*'):
        if not folder.is_dir():
            continue
        
        # Parse folder name: constellation_analysis_YYYYMMDD_HHMMSS_IMAGESIZE_NUMSATS
        match = re.match(r'constellation_analysis_\d{8}_\d{6}_(\d+)_(\d+)', folder.name)
        if match:
            image_size_kb = int(match.group(1))
            num_sats = int(match.group(2))
            
            # Check which strategies exist
            for strategy in ['close-spaced', 'orbit-spaced', 'frame-spaced', 'close-orbit-spaced']:
                strategy_path = folder / strategy / 'simulation_logs.zip'
                if strategy_path.exists():
                    configs.append({
                        'folder': folder,
                        'strategy': strategy,
                        'image_size_kb': image_size_kb,
                        'num_sats': num_sats,
                        'zip_path': strategy_path
                    })
    
    return pd.DataFrame(configs)

def get_idle_time(zip_path, policy='fifo'):
    """
    Calculate total idle time from visibility_log.csv in zip file
    
    Idle Definition: buffer_mb > 0 AND connected = 0
                     (satellite has data but is not downloading)
    
    Returns: Total idle time in hours
    """
    try:
        with zipfile.ZipFile(zip_path, 'r') as zipf:
            with zipf.open(f'{policy}/visibility_log.csv') as f:
                df = pd.read_csv(f)
        
        # Idle condition: has data in buffer but not connected
        idle_entries = df[(df['buffer_mb'] > 0) & (df['connected'] == 0)]
        
        # Each entry represents 10 seconds
        idle_seconds = len(idle_entries) * 10
        idle_hours = idle_seconds / 3600
        
        return idle_hours
        
    except Exception as e:
        return 0.0

def collect_all_data() -> pd.DataFrame:
    """
    Collect idle time data for all configurations.
    
    Returns DataFrame with columns:
    - strategy
    - policy
    - num_sats
    - image_size_kb
    - idle_hours
    """
    # Scan for all configurations
    configs_df = scan_all_configurations()
    
    if configs_df.empty:
        print("❌ No constellation_analysis folders found!")
        return pd.DataFrame()
    
    data = []
    
    for _, config in configs_df.iterrows():
        strategy = STRATEGIES_MAP[config['strategy']]
        
        for policy in POLICIES:
            idle_hours = get_idle_time(config['zip_path'], policy)
            
            data.append({
                'strategy': strategy,
                'policy': policy,
                'num_sats': config['num_sats'],
                'image_size_kb': config['image_size_kb'],
                'idle_hours': idle_hours
            })
    
    return pd.DataFrame(data)

def create_stacked_bar_chart(df: pd.DataFrame, image_size_kb: int) -> None:
    """
    Create stacked bar chart for a single image size.
    
    Chart Structure:
    - 4 strategy groups on x-axis
    - Each group has 4 bars (one per constellation size)
    - Each bar is stacked with 4 policies
    """
    # Filter data for this image size
    df_img = df[df['image_size_kb'] == image_size_kb].copy()
    
    if df_img.empty:
        print(f"⚠️  No data for image size {image_size_kb} KB")
        return
    
    # Create figure
    fig, ax = plt.subplots(figsize=(24, 10))
    
    # Strategy display order
    STRATEGIES = ["Close", "Orbit", "Frame", "Close-Orbit"]
    
    # X-axis positions
    group_width = 5  # Space for each strategy group
    bar_width = 0.8
    group_gap = 1.5
    
    x_positions = []
    x_labels = []
    
    for i, strategy in enumerate(STRATEGIES):
        group_start = i * (group_width + group_gap)
        
        for j, num_sats in enumerate(CONSTELLATION_SIZES):
            x_pos = group_start + j
            x_positions.append(x_pos)
            x_labels.append(f"{num_sats}")
    
    # Plot stacked bars
    for x_pos, label in zip(x_positions, x_labels):
        # Determine strategy and num_sats for this position
        group_idx = x_pos // (group_width + group_gap)
        bar_idx = int(x_pos % (group_width + group_gap))
        
        strategy = STRATEGIES[group_idx]
        num_sats = CONSTELLATION_SIZES[bar_idx]
        
        # Get data for all policies for this configuration
        config_data = df_img[
            (df_img['strategy'] == strategy) & 
            (df_img['num_sats'] == num_sats)
        ]
        
        # Stack the bars
        bottom = 0
        for policy in POLICIES:
            policy_data = config_data[config_data['policy'] == policy]
            
            if not policy_data.empty:
                value = policy_data['idle_hours'].values[0]
                
                # Plot this policy's segment
                ax.bar(x_pos, value, bar_width, 
                      bottom=bottom,
                      color=POLICY_COLORS[policy],
                      label=policy.upper() if x_pos == x_positions[0] else "",
                      edgecolor='black',
                      linewidth=0.5)
                
                # Add text label in the center of this stack segment
                if value > 0.1:  # Only show label if > 0.1 hours (6 minutes)
                    text_y = bottom + value / 2
                    
                    # Format text based on value
                    if value < 1:
                        text = f'{value:.2f}'  # 2 decimals for small values
                    elif value < 10:
                        text = f'{value:.1f}'  # 1 decimal
                    else:
                        text = f'{value:.0f}'  # Integer for large values
                    
                    ax.text(x_pos, text_y, text, 
                           ha='center', va='center',
                           fontsize=8, fontweight='bold',
                           color='white',
                           bbox=dict(boxstyle='round,pad=0.3', 
                                   facecolor='black', 
                                   edgecolor='none',
                                   alpha=0.6))
                
                bottom += value
    
    # Add strategy group labels
    for i, strategy in enumerate(STRATEGIES):
        group_center = i * (group_width + group_gap) + (group_width - 1) / 2
        ax.text(group_center, -0.15, strategy, 
               ha='center', va='top',
               fontsize=14, fontweight='bold',
               transform=ax.get_xaxis_transform())
    
    # Customize plot
    image_size_mb = image_size_kb / 1024.0
    ax.set_xlabel('Constellation Size (Number of Satellites)', fontsize=14, fontweight='bold')
    ax.set_ylabel('Total Idle Time (hours)', fontsize=14, fontweight='bold')
    ax.set_title(f'Idle Time by Strategy & Policy\nImage Size: {image_size_mb:.3f} MB', 
                fontsize=16, fontweight='bold', pad=20)
    
    ax.set_xticks(x_positions)
    ax.set_xticklabels(x_labels, fontsize=10)
    
    ax.legend(title='Link Policy', loc='upper left', fontsize=12, title_fontsize=12)
    ax.grid(axis='y', alpha=0.3, linestyle='--')
    
    # Tight layout
    plt.tight_layout()
    
    # Save
    output_file = OUTPUT_DIR / f"stacked_idle_time_{image_size_mb:.3f}mb.png"
    plt.savefig(output_file, dpi=150, bbox_inches='tight')
    plt.close()
    
    print(f"✅ Saved: {output_file}")

def main():
    print("=" * 100)
    print("=" * 18 + " " * 64 + "=" * 18)
    print("=" * 18 + " " * 64 + "IDLE TIME STACKED BAR CHARTS")
    print("=" * 18 + "Grouped by Strategy, Stacked by Policy" + " " * 25 + "=" * 18)
    print("=" * 100)
    
    # Create output directory
    OUTPUT_DIR.mkdir(exist_ok=True)
    
    # Scan for configurations
    print("\nScanning for constellation configurations...")
    
    # Collect all data
    df = collect_all_data()
    
    if df.empty:
        print("❌ No configuration data found!")
        sys.exit(1)
    
    # Get unique image sizes
    image_sizes_kb = sorted(df['image_size_kb'].unique())
    
    print(f"Found {len(df)} configuration entries")
    
    # Save raw data
    csv_output = OUTPUT_DIR / "stacked_idle_time.csv"
    df.to_csv(csv_output, index=False)
    print(f"\n✅ Saved: {csv_output}")
    
    # Create stacked bar chart for each image size
    for image_size_kb in image_sizes_kb:
        image_size_mb = image_size_kb / 1024.0
        print(f"\nCreating stacked bar chart for {image_size_mb:.3f} MB...")
        create_stacked_bar_chart(df, image_size_kb)
    
    # Summary
    print("\n" + "=" * 100)
    print("=" * 18 + " " * 64 + "=" * 18)
    print("=" * 18 + " " * 64 + "✅ STACKED BAR CHARTS COMPLETE!")
    print("=" * 100)
    print("\nChart Structure:")
    print("  X-AXIS: 4 strategy groups (Close, Orbit, Frame, Close-Orbit)")
    print("          Each group has 4 bars (one per constellation size: 1, 50, 100, 200)")
    print("\n  Y-AXIS: Total idle time (hours)")
    print("\n  STACKS: Each bar divided by 4 policies:")
    print("    🔴 Red    = STICKY")
    print("    🔵 Blue   = FIFO")
    print("    🟢 Green  = ROUNDROBIN")
    print("    🟠 Orange = RANDOM")
    print(f"\n  RESULT: {len(image_sizes_kb)} chart(s) (one per image size)")
    print("          16 stacked bars per chart (4 strategies × 4 constellation sizes)")
    print("\n✨ Stacked bar charts complete!")

if __name__ == "__main__":
    main()
