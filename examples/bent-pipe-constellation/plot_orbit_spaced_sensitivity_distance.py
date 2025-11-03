#!/usr/bin/env python3
"""
Create stacked bar charts showing TOTAL DISTANCE by constellation size and policy.
ORBIT-SPACED STRATEGY ONLY - SENSITIVITY STUDY (10, 15, 17, 18, 19, 20, 25 satellites)

This shows cumulative link distance to understand geometry effects.
Better geometry (18-19 sats) should show LOWER total distance.

X-axis: Constellation sizes (10, 15, 17, 18, 19, 20, 25)
Y-axis: Total distance (km)
Stacks: Each bar divided by 4 link policies (sticky, fifo, roundrobin, random)

One chart per image size.
"""

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import zipfile
from pathlib import Path
import re

def scan_spacing_sensitivity_configurations(search_dirs=['results/orbit space best constellation size', 'results/base results'], strategies=['orbit-spaced', 'close-orbit-spaced']):
    """Scan for orbit-spaced and close-orbit-spaced configurations in sensitivity study and base results directories"""
    configs = []
    
    # Scan multiple directories
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
                
                # Check for both orbit-spaced and close-orbit-spaced strategies
                for strategy in strategies:
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

def get_total_distance(zip_path, policy='fifo'):
    """Calculate total distance (km) from visibility log"""
    try:
        with zipfile.ZipFile(zip_path, 'r') as zipf:
            with zipf.open(f'{policy}/visibility_log.csv') as f:
                df = pd.read_csv(f)
        
        # Filter to connected timesteps only
        connected_df = df[df['connected'] == 1].copy()
        
        if len(connected_df) == 0:
            return 0.0
        
        # Sum all distances when connected
        total_distance_km = connected_df['distance_km'].sum()
        
        return total_distance_km
        
    except Exception as e:
        print(f"  ⚠️  Error reading {zip_path}/{policy}: {e}")
        return 0.0

def create_sensitivity_distance_charts():
    """Create side-by-side stacked bar charts - one per image size, comparing orbit-spaced vs close-orbit-spaced"""
    
    print("="*110)
    print("=" * 20 + " SPACING STRATEGY COMPARISON: TOTAL DISTANCE STACKED BAR CHARTS")
    print("Orbit-Spaced vs Close-Orbit-Spaced | Stacked by Policy")
    print("="*110)
    print()
    
    print("Scanning for orbit-spaced and close-orbit-spaced configurations (including base results)...")
    configs_df = scan_spacing_sensitivity_configurations()
    
    if len(configs_df) == 0:
        print("❌ No orbit-spaced sensitivity configurations found!")
        return
    
    print(f"Found {len(configs_df)} orbit-spaced sensitivity configurations")
    print()
    
    # Collect all data
    results = []
    
    # Group by image_size, strategy, and num_sats
    grouped = configs_df.groupby(['image_size_kb', 'strategy', 'num_sats'])
    
    policies = ['sticky', 'fifo', 'roundrobin', 'random']
    
    print("Calculating total distances...")
    for (image_size_kb, strategy, num_sats), group in grouped:
        image_size_mb = image_size_kb / 1000.0
        
        for policy in policies:
            row = group.iloc[0]
            total_distance = get_total_distance(row['zip_path'], policy)
            
            results.append({
                'image_size_mb': image_size_mb,
                'strategy': strategy,
                'policy': policy,
                'num_sats': num_sats,
                'orbital_spacing_deg': 360.0 / num_sats,
                'total_distance_km': total_distance
            })
    
    results_df = pd.DataFrame(results)
    
    # Save raw data
    output_dir = Path('comparison_charts')
    output_dir.mkdir(exist_ok=True)
    results_df.to_csv(output_dir / 'spacing_comparison_sensitivity_distance.csv', index=False)
    print(f"✅ Saved: {output_dir / 'spacing_comparison_sensitivity_distance.csv'}")
    print()
    
    # Create charts
    create_charts(results_df, output_dir)
    
    return results_df

def create_charts(results_df, output_dir):
    """Create side-by-side stacked bar charts per image size (orbit-spaced vs close-orbit-spaced)"""
    
    # Get unique values
    image_sizes = sorted(results_df['image_size_mb'].unique())
    strategies = ['orbit-spaced', 'close-orbit-spaced']
    policies = ['sticky', 'fifo', 'roundrobin', 'random']
    
    # Color scheme by policy (4 distinct colors for stacks)
    policy_colors = {
        'sticky': '#E63946',      # Red
        'fifo': '#2E86AB',        # Blue
        'roundrobin': '#06A77D',  # Green
        'random': '#F77F00'       # Orange
    }
    
    # Create one chart per image size
    for image_size in image_sizes:
        print(f"Creating spacing comparison distance chart for {image_size} MB...")
        
        subset = results_df[results_df['image_size_mb'] == image_size]
        
        if len(subset) == 0:
            continue
        
        # Create figure with 2 subplots side by side
        fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(28, 10))
        axes = [ax1, ax2]
        
        # Process each strategy
        for strategy_idx, strategy in enumerate(strategies):
            ax = axes[strategy_idx]
            strategy_subset = subset[subset['strategy'] == strategy]
            
            if len(strategy_subset) == 0:
                ax.text(0.5, 0.5, f'No data for {strategy}', 
                       ha='center', va='center', fontsize=16, transform=ax.transAxes)
                continue
            
            # Get satellite counts for this strategy
            sat_counts = sorted(strategy_subset['num_sats'].unique())
            
            # Prepare data structure for stacked bars
            bar_width = 0.7
            x_positions = np.arange(len(sat_counts))
            
            # Build stacked bars
            for x_idx, sat_count in enumerate(sat_counts):
                orbital_spacing = 360.0 / sat_count
                
                # Get data for all policies for this sat_count
                bottom = 0
                for policy in policies:
                    data = strategy_subset[
                        (strategy_subset['policy'] == policy) & 
                        (strategy_subset['num_sats'] == sat_count)
                    ]
                    
                    if len(data) > 0:
                        value = data['total_distance_km'].values[0]
                    else:
                        value = 0
                    
                    # Draw this segment of the stack
                    ax.bar(x_positions[x_idx], value, bar_width, bottom=bottom, 
                          color=policy_colors[policy], 
                          edgecolor='white', linewidth=2,
                          label=policy.upper() if x_idx == 0 and strategy_idx == 0 else "")
                    
                    # Add text label in the center of this stack segment
                    if value > 0:
                        text_y = bottom + value / 2
                        if value >= 1000:
                            text = f'{value/1000:.0f}k'
                        else:
                            text = f'{value:.0f}'
                        
                        ax.text(x_positions[x_idx], text_y, text, 
                               ha='center', va='center',
                               fontsize=8, fontweight='bold',
                               color='white',
                               bbox=dict(boxstyle='round,pad=0.3', 
                                        facecolor='black', 
                                        edgecolor='none',
                                        alpha=0.7))
                    
                    bottom += value
                
                # Add total on top of bar
                if bottom > 0:
                    if bottom >= 1000:
                        total_text = f'{bottom/1000:.1f}k km'
                    else:
                        total_text = f'{bottom:.0f} km'
                    ax.text(x_positions[x_idx], bottom * 1.03, total_text, 
                           ha='center', va='bottom',
                           fontsize=10, fontweight='bold',
                           color='black')
                
                # Add orbital spacing annotation below bar
                max_y_for_strategy = strategy_subset.groupby('num_sats')['total_distance_km'].sum().max()
                spacing_offset = -max(1000, max_y_for_strategy * 0.05)
                ax.text(x_positions[x_idx], spacing_offset, f'{orbital_spacing:.2f}°', 
                       ha='center', va='top',
                       fontsize=9, fontweight='bold',
                       color='#555')
            
            # Set x-axis labels
            ax.set_xticks(x_positions)
            ax.set_xticklabels([f'{sat}' for sat in sat_counts], fontsize=11, fontweight='bold')
            ax.set_xlabel('Number of Satellites', fontsize=13, fontweight='bold')
            
            # Y-axis
            ax.set_ylabel('Total Distance (km)', fontsize=13, fontweight='bold')
            
            # Set y limits with padding
            max_y_for_strategy = strategy_subset.groupby('num_sats')['total_distance_km'].sum().max()
            min_offset = max(2000, max_y_for_strategy * 0.08)
            ax.set_ylim(-min_offset, max_y_for_strategy * 1.18)
            
            # Subplot title
            strategy_name = 'Orbit-Spaced' if strategy == 'orbit-spaced' else 'Close-Orbit-Spaced'
            ax.set_title(f'{strategy_name}',
                        fontsize=15, fontweight='bold', pad=10)
            
            # Grid
            ax.grid(True, alpha=0.3, linestyle='--', axis='y')
            ax.set_axisbelow(True)
        
        # Overall title
        fig.suptitle(f'Spacing Strategy Comparison: Total Link Distance by Satellite Count\n{image_size} MB Images',
                    fontsize=17, fontweight='bold', y=0.98)
        
        # Legend (only on left subplot)
        ax1.legend(title='Link Policy', fontsize=11, title_fontsize=12, 
                  loc='upper left', framealpha=0.95, edgecolor='black')
        
        plt.tight_layout(rect=[0, 0, 1, 0.96])
        
        # Save
        filename = f'spacing_comparison_sensitivity_distance_{image_size}mb.png'
        output_file = output_dir / filename
        plt.savefig(output_file, dpi=300, bbox_inches='tight')
        print(f"✅ Saved: {output_file}")
        plt.close()
    
    print()
    print("="*110)
    print("✅ SPACING COMPARISON SENSITIVITY DISTANCE STACKED BAR CHARTS COMPLETE!")
    print("="*110)
    print()
    print("Chart Structure:")
    print("  LAYOUT: Side-by-side comparison (Orbit-Spaced | Close-Orbit-Spaced)")
    print("  X-AXIS: Constellation sizes (varies by strategy availability)")
    print("          Orbital spacing shown below each bar")
    print()
    print("  Y-AXIS: Total distance (km) - cumulative link distance when connected")
    print()
    print("  STACKS: Each bar divided by 4 policies:")
    print("    🔴 Red    = STICKY")
    print("    🔵 Blue   = FIFO")
    print("    🟢 Green  = ROUNDROBIN")
    print("    🟠 Orange = RANDOM")
    print()
    print(f"  RESULT: {len(image_sizes)} chart(s) (one per image size)")
    print("          2 strategies per chart (side-by-side)")

if __name__ == '__main__':
    import os
    
    # Change to script directory
    script_dir = Path(__file__).parent
    os.chdir(script_dir)
    
    results_df = create_sensitivity_distance_charts()
    
    if results_df is not None:
        print()
        print("✨ Orbit-spaced sensitivity distance stacked bar charts complete!")
