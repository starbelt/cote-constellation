#!/usr/bin/env python3
"""
Create stacked bar charts showing total data downloaded by constellation size and policy.
ORBIT-SPACED STRATEGY ONLY

X-axis: Constellation sizes (25, 50, 100, 200)
Y-axis: Total data downloaded (GB)
Stacks: Each bar divided by 4 link policies (sticky, fifo, roundrobin, random)

One chart per image size.
"""

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import zipfile
from pathlib import Path
import re

def scan_orbit_spaced_configurations(search_dir='results/base results'):
    """Scan for all constellation_analysis folders with orbit-spaced strategy"""
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
            
            # Check for orbit-spaced strategy only
            strategy_path = folder / 'orbit-spaced' / 'simulation_logs.zip'
            if strategy_path.exists():
                configs.append({
                    'folder': folder,
                    'strategy': 'orbit-spaced',
                    'image_size_kb': image_size_kb,
                    'num_sats': num_sats,
                    'zip_path': strategy_path
                })
    
    return pd.DataFrame(configs)

def get_data_downloaded(zip_path, policy='fifo'):
    """Get total data downloaded from visibility log"""
    try:
        with zipfile.ZipFile(zip_path, 'r') as zipf:
            with zipf.open(f'{policy}/visibility_log.csv') as f:
                df = pd.read_csv(f)
        
        # Sum all downloaded data in MB, convert to GB
        total_downloaded_mb = df['downloaded_mb'].sum()
        total_downloaded_gb = total_downloaded_mb / 1024.0
        
        return total_downloaded_gb
        
    except Exception as e:
        print(f"  ⚠️  Error reading {zip_path}/{policy}: {e}")
        return 0.0

def create_orbit_spaced_charts():
    """Create stacked bar charts - one per image size, orbit-spaced only"""
    
    print("="*110)
    print("=" * 30 + " ORBIT-SPACED STRATEGY: DATA DOWNLOADED STACKED BAR CHARTS")
    print("Stacked by Policy, Grouped by Satellite Count")
    print("="*110)
    print()
    
    print("Scanning for orbit-spaced configurations...")
    configs_df = scan_orbit_spaced_configurations()
    
    if len(configs_df) == 0:
        print("❌ No orbit-spaced configurations found!")
        return
    
    print(f"Found {len(configs_df)} orbit-spaced configurations")
    print()
    
    # Collect all data
    results = []
    
    # Group by image_size and num_sats
    grouped = configs_df.groupby(['image_size_kb', 'num_sats'])
    
    policies = ['sticky', 'fifo', 'roundrobin', 'random']
    
    for (image_size_kb, num_sats), group in grouped:
        image_size_mb = image_size_kb / 1000.0
        
        for policy in policies:
            row = group.iloc[0]
            data_gb = get_data_downloaded(row['zip_path'], policy)
            
            results.append({
                'image_size_mb': image_size_mb,
                'policy': policy,
                'num_sats': num_sats,
                'orbital_spacing_deg': 360.0 / num_sats,
                'data_downloaded_gb': data_gb
            })
    
    results_df = pd.DataFrame(results)
    
    # Save raw data
    output_dir = Path('constellation_analysis') / 'orbit_spaced_charts'
    output_dir.mkdir(parents=True, exist_ok=True)
    results_df.to_csv(output_dir / 'orbit_spaced_data_downloaded.csv', index=False)
    print(f"✅ Saved: {output_dir / 'orbit_spaced_data_downloaded.csv'}")
    print()
    
    # Create charts
    create_charts(results_df, output_dir)
    
    return results_df

def create_charts(results_df, output_dir):
    """Create one stacked bar chart per image size"""
    
    # Get unique values
    image_sizes = sorted(results_df['image_size_mb'].unique())
    policies = ['sticky', 'fifo', 'roundrobin', 'random']
    sat_counts = sorted(results_df['num_sats'].unique())
    
    # Color scheme by policy (4 distinct colors for stacks)
    policy_colors = {
        'sticky': '#E63946',      # Red
        'fifo': '#2E86AB',        # Blue
        'roundrobin': '#06A77D',  # Green
        'random': '#F77F00'       # Orange
    }
    
    # Create one chart per image size
    for image_size in image_sizes:
        print(f"Creating orbit-spaced stacked bar chart for {image_size} MB...")
        
        subset = results_df[results_df['image_size_mb'] == image_size]
        
        if len(subset) == 0:
            continue
        
        # Create figure
        fig, ax = plt.subplots(figsize=(14, 10))
        
        # Prepare data structure for stacked bars
        bar_width = 0.6
        x_positions = np.arange(len(sat_counts))
        
        # Build stacked bars
        for x_idx, sat_count in enumerate(sat_counts):
            orbital_spacing = 360.0 / sat_count
            
            # Get data for all policies for this sat_count
            bottom = 0
            for policy in policies:
                data = subset[
                    (subset['policy'] == policy) & 
                    (subset['num_sats'] == sat_count)
                ]
                
                if len(data) > 0:
                    value = data['data_downloaded_gb'].values[0]
                else:
                    value = 0
                
                # Draw this segment of the stack
                ax.bar(x_positions[x_idx], value, bar_width, bottom=bottom, 
                      color=policy_colors[policy], 
                      edgecolor='white', linewidth=2,
                      label=policy.upper() if x_idx == 0 else "")
                
                # Add text label in the center of this stack segment
                if value > 0:
                    # Position text in the middle of this segment
                    text_y = bottom + value / 2
                    # Format value: show 1 decimal for values < 10, otherwise round to integer
                    if value < 10:
                        text = f'{value:.1f}'
                    else:
                        text = f'{value:.0f}'
                    
                    ax.text(x_positions[x_idx], text_y, text, 
                           ha='center', va='center',
                           fontsize=10, fontweight='bold',
                           color='white',
                           bbox=dict(boxstyle='round,pad=0.4', 
                                    facecolor='black', 
                                    edgecolor='none',
                                    alpha=0.7))
                
                bottom += value
            
            # Add total on top of bar
            if bottom > 0:
                ax.text(x_positions[x_idx], bottom + 5, f'{bottom:.1f} GB', 
                       ha='center', va='bottom',
                       fontsize=11, fontweight='bold',
                       color='black')
            
            # Add orbital spacing annotation below bar
            ax.text(x_positions[x_idx], -15, f'{orbital_spacing:.1f}°', 
                   ha='center', va='top',
                   fontsize=10, fontweight='bold',
                   color='#555')
        
        # Set x-axis labels
        ax.set_xticks(x_positions)
        ax.set_xticklabels([f'{sat} sats' for sat in sat_counts], fontsize=13, fontweight='bold')
        ax.set_xlabel('Number of Satellites (Orbital Spacing)', fontsize=14, fontweight='bold')
        
        # Y-axis
        ax.set_ylabel('Total Data Downloaded (GB)', fontsize=14, fontweight='bold')
        
        # Set y limits with padding
        max_y = results_df[results_df['image_size_mb'] == image_size].groupby('num_sats')['data_downloaded_gb'].sum().max()
        ax.set_ylim(-20, max_y * 1.15)
        
        # Title
        ax.set_title(f'Orbit-Spaced Strategy: Data Downloaded by Satellite Count and Policy\n{image_size} MB Images',
                    fontsize=16, fontweight='bold', pad=20)
        
        # Add subtitle with orbital spacing info
        ax.text(0.5, 0.98, 'Wider Spacing → Better Geometric Diversity', 
               transform=ax.transAxes,
               ha='center', va='top',
               fontsize=11, style='italic', color='#555',
               bbox=dict(boxstyle='round,pad=0.5', facecolor='yellow', alpha=0.2))
        
        # Legend
        ax.legend(title='Link Policy', fontsize=12, title_fontsize=13, 
                 loc='upper left', framealpha=0.95, edgecolor='black')
        
        # Grid
        ax.grid(True, alpha=0.3, linestyle='--', axis='y')
        ax.set_axisbelow(True)
        
        plt.tight_layout()
        
        # Save
        filename = f'orbit_spaced_only_{image_size}mb.png'
        output_file = output_dir / filename
        plt.savefig(output_file, dpi=300, bbox_inches='tight')
        print(f"✅ Saved: {output_file}")
        plt.close()
    
    print()
    print("="*110)
    print("✅ ORBIT-SPACED STACKED BAR CHARTS COMPLETE!")
    print("="*110)
    print()
    print("Chart Structure:")
    print("  X-AXIS: Constellation sizes (25, 50, 100, 200 satellites)")
    print("          Orbital spacing shown below each bar")
    print()
    print("  Y-AXIS: Total data downloaded (GB)")
    print()
    print("  STACKS: Each bar divided by 4 policies:")
    print("    🔴 Red    = STICKY")
    print("    🔵 Blue   = FIFO")
    print("    🟢 Green  = ROUNDROBIN")
    print("    🟠 Orange = RANDOM")
    print()
    print(f"  RESULT: {len(image_sizes)} chart(s) (one per image size)")
    print(f"          {len(sat_counts)} stacked bars per chart (one per satellite count)")
    print()
    
    # Print summary table
    print("📊 SUMMARY TABLE:")
    print("-" * 110)
    for image_size in image_sizes:
        print(f"\n{image_size} MB Images:")
        print(f"{'Satellites':<12} {'Spacing':<12} {'Sticky':<12} {'FIFO':<12} {'RoundRobin':<12} {'Random':<12} {'TOTAL':<12}")
        print("-" * 110)
        
        subset = results_df[results_df['image_size_mb'] == image_size]
        for sat_count in sat_counts:
            sat_data = subset[subset['num_sats'] == sat_count]
            if len(sat_data) == 0:
                continue
            
            spacing = 360.0 / sat_count
            totals = {}
            for policy in policies:
                policy_data = sat_data[sat_data['policy'] == policy]
                totals[policy] = policy_data['data_downloaded_gb'].values[0] if len(policy_data) > 0 else 0
            
            total = sum(totals.values())
            
            print(f"{sat_count:<12} {spacing:>6.1f}°      {totals['sticky']:>8.2f} GB  {totals['fifo']:>8.2f} GB  {totals['roundrobin']:>8.2f} GB  {totals['random']:>8.2f} GB  {total:>8.2f} GB")

if __name__ == '__main__':
    import os
    
    # Change to script directory
    script_dir = Path(__file__).parent
    os.chdir(script_dir)
    
    results_df = create_orbit_spaced_charts()
    
    if results_df is not None:
        print()
        print("✨ Orbit-spaced stacked bar charts complete!")
