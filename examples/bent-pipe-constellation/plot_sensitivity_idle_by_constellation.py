#!/usr/bin/env python3
"""
Create stacked bar charts showing total idle time for SENSITIVITY STUDY.
Constellation sizes: 1, 10, 15, 17, 18, 19, 20, 25, 50, 100, 200
Strategy: orbit-spaced only (from orbit space best constellation size)

X-axis: Constellation sizes (11 bars)
Y-axis: Total idle time (hours)
Stacks: Each bar divided by 4 link policies (sticky, fifo, roundrobin, random)

One chart per image size.
"""

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import zipfile
from pathlib import Path
import re

def scan_sensitivity_configurations(search_dirs=['results/orbit space best constellation size', 'results/base results 2']):
    """Scan for orbit-spaced configurations in sensitivity study directories"""
    configs = []
    
    for search_dir in search_dirs:
        search_path = Path(search_dir)
        if not search_path.exists():
            print(f"⚠️  Directory not found: {search_dir}")
            continue
            
        for folder in search_path.glob('constellation_analysis_*'):
            if not folder.is_dir():
                continue
            
            # Parse folder name: constellation_analysis_YYYYMMDD_HHMMSS_IMAGESIZE_NUMSATS
            match = re.match(r'constellation_analysis_\d{8}_\d{6}_(\d+)_(\d+)', folder.name)
            if match:
                image_size_kb = int(match.group(1))
                num_sats = int(match.group(2))
                
                # Only orbit-spaced strategy
                strategy = 'orbit-spaced'
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
    Extract total idle time from visibility_log.csv for a given policy.
    
    Idle Definition: simulation_time - productive_time
                     Productive = connected AND buffer > 0.001 MB
    
    This matches the definition used in generate_combined_total_idle_matrix.py
    
    Returns: Total idle time in hours
    """
    try:
        with zipfile.ZipFile(zip_path, 'r') as zipf:
            with zipf.open(f'{policy}/visibility_log.csv') as f:
                df = pd.read_csv(f)
        
        # Simulation duration is 6 hours = 21600 seconds
        sim_duration_seconds = 21600
        
        # Productive condition: connected AND has meaningful data in buffer
        productive_entries = df[(df['connected'] == 1) & (df['buffer_mb'] > 0.001)]
        
        # Each entry represents 1 second (visibility_log is per-second data)
        productive_seconds = len(productive_entries) * 1
        
        # Idle time = Total simulation time - productive time
        idle_seconds = sim_duration_seconds - productive_seconds
        idle_hours = idle_seconds / 3600.0
        
        return idle_hours
        
    except Exception as e:
        print(f"  ⚠️  Error reading {zip_path}/{policy}: {e}")
        return 0.0

def collect_all_data(search_dirs):
    """Collect idle time data from all configurations"""
    
    configs_df = scan_sensitivity_configurations(search_dirs)
    
    if len(configs_df) == 0:
        print("❌ No configurations found!")
        return pd.DataFrame()
    
    print(f"Found {len(configs_df)} orbit-spaced configurations")
    
    results = []
    policies = ['sticky', 'fifo', 'roundrobin', 'random']
    
    for _, config in configs_df.iterrows():
        for policy in policies:
            idle_hours = get_idle_time(config['zip_path'], policy)
            
            results.append({
                'image_size_kb': config['image_size_kb'],
                'num_sats': config['num_sats'],
                'strategy': config['strategy'],
                'policy': policy,
                'idle_hours': idle_hours
            })
    
    results_df = pd.DataFrame(results)
    
    # Deduplicate: Keep only one entry per (image_size_kb, num_sats, policy) combination
    # This handles cases where the same constellation size appears in multiple source directories
    if len(results_df) > 0:
        results_df = results_df.drop_duplicates(subset=['image_size_kb', 'num_sats', 'policy'], keep='first')
    
    return results_df

def create_stacked_bar_chart(df, image_size_kb, output_dir):
    """Create stacked bar chart for one image size"""
    
    # Filter for this image size
    df_img = df[df['image_size_kb'] == image_size_kb].copy()
    
    if len(df_img) == 0:
        print(f"  ⚠️  No data for {image_size_kb} KB")
        return
    
    # Define constellation sizes in order
    const_sizes = [1, 10, 15, 17, 18, 19, 20, 25, 50, 100, 200]
    
    # Filter to only include constellation sizes that exist in data
    available_sizes = sorted(df_img['num_sats'].unique())
    const_sizes = [s for s in const_sizes if s in available_sizes]
    
    if len(const_sizes) == 0:
        print(f"  ⚠️  No matching constellation sizes for {image_size_kb} KB")
        return
    
    # Pivot data for stacking
    policies = ['sticky', 'fifo', 'roundrobin', 'random']
    
    # Create matrix: rows=constellation sizes, columns=policies
    idle_matrix = np.zeros((len(const_sizes), len(policies)))
    
    for i, size in enumerate(const_sizes):
        for j, policy in enumerate(policies):
            mask = (df_img['num_sats'] == size) & (df_img['policy'] == policy)
            if mask.any():
                idle_matrix[i, j] = df_img[mask]['idle_hours'].iloc[0]
    
    # Create stacked bar chart
    fig, ax = plt.subplots(figsize=(16, 10))
    
    # X positions for bars
    x = np.arange(len(const_sizes))
    width = 0.8
    
    # Colors for policies
    colors = {
        'sticky': '#d62728',      # red
        'fifo': '#1f77b4',        # blue
        'roundrobin': '#2ca02c',  # green
        'random': '#ff7f0e'       # orange
    }
    
    # Create stacked bars
    bottom = np.zeros(len(const_sizes))
    
    for j, policy in enumerate(policies):
        values = idle_matrix[:, j]
        ax.bar(x, values, width, label=policy.upper(), 
               bottom=bottom, color=colors[policy], alpha=0.9)
        bottom += values
    
    # Formatting
    image_size_mb = image_size_kb / 1024.0
    ax.set_xlabel('Constellation Size (Number of Satellites)', fontsize=14, fontweight='bold')
    ax.set_ylabel('Total Idle Time (hours)', fontsize=14, fontweight='bold')
    ax.set_title(f'Total Idle Time by Constellation Size - Orbit-Spaced Sensitivity Study\nImage Size: {image_size_mb:.3f} MB', 
                 fontsize=16, fontweight='bold', pad=20)
    
    # X-axis labels
    ax.set_xticks(x)
    ax.set_xticklabels([str(s) for s in const_sizes])
    
    # Legend
    ax.legend(title='Policy', loc='upper left', fontsize=12, title_fontsize=12)
    
    # Grid
    ax.grid(True, alpha=0.3, axis='y', linestyle='--')
    ax.set_axisbelow(True)
    
    # Add value labels on top of each bar
    for i, size in enumerate(const_sizes):
        total = bottom[i]
        ax.text(i, total, f'{total:.1f}h', 
                ha='center', va='bottom', fontsize=9, fontweight='bold')
    
    plt.tight_layout()
    
    # Save
    output_file = output_dir / f"sensitivity_idle_time_{image_size_mb:.3f}mb.png"
    plt.savefig(output_file, dpi=150, bbox_inches='tight')
    print(f"✅ Saved: {output_file}")
    plt.close()

def create_sensitivity_charts(search_dirs=['results/orbit space best constellation size', 'results/base results 2']):
    """Main function to create all charts"""
    
    print("="*100)
    print("=" * 18 + " " * 45 + "SENSITIVITY STUDY - IDLE TIME CHARTS")
    print("=" * 18 + "Orbit-Spaced Only, Stacked by Policy" + " " * 25 + "=" * 18)
    print("="*100)
    
    # Create output directory
    output_dir = Path("constellation_analysis") / "sensitivity_idle_charts"
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Scan for configurations
    print(f"\nScanning for orbit-spaced configurations in sensitivity study...")
    
    # Collect all data
    df = collect_all_data(search_dirs)
    
    if df.empty:
        print("❌ No configuration data found!")
        return
    
    # Save raw data
    csv_output = output_dir / "sensitivity_idle_time.csv"
    df.to_csv(csv_output, index=False)
    print(f"\n✅ Saved: {csv_output}")
    
    # Get unique image sizes
    image_sizes = sorted(df['image_size_kb'].unique())
    
    print(f"\nCreating charts for {len(image_sizes)} image size(s)...\n")
    
    # Create chart for each image size
    for image_size_kb in image_sizes:
        image_size_mb = image_size_kb / 1024.0
        print(f"Creating chart for {image_size_mb:.3f} MB...")
        create_stacked_bar_chart(df, image_size_kb, output_dir)
    
    print("\n" + "="*100)
    print("✅ SENSITIVITY IDLE TIME CHARTS COMPLETE!")
    print("="*100)
    print("\nChart Structure:")
    print("  X-AXIS: Constellation sizes (1, 10, 15, 17, 18, 19, 20, 25, 50, 100, 200)")
    print("  Y-AXIS: Total idle time (hours)")
    print("  STACKS: Each bar divided by 4 policies:")
    print("    🔴 Red    = STICKY")
    print("    🔵 Blue   = FIFO")
    print("    🟢 Green  = ROUNDROBIN")
    print("    🟠 Orange = RANDOM")
    print(f"\n  RESULT: {len(image_sizes)} chart(s) (one per image size)")
    print("\n✨ Charts complete!")

if __name__ == "__main__":
    create_sensitivity_charts()
