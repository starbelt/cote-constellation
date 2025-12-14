#!/usr/bin/env python3
"""
Create stacked bar charts showing bitrate efficiency by policy and strategy.

X-axis: Link policies (sticky, fifo, roundrobin, random, mindistance, maxdownload) grouped by constellation size
Y-axis: Bitrate Efficiency (%) - how close to optimal bitrate each policy achieved
Stacks: Each bar divided by 4 spacing strategies (close, frame, orbit, close-orbit)

One chart per image size.

Metrics shown:
- bitrate_efficiency_pct: (avg_connected_bitrate / avg_best_available_bitrate) * 100
- This measures: "How good was the link I chose vs the best link I could have chosen?"
"""

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import zipfile
from pathlib import Path
import re
import tempfile
import shutil

def analyze_optimality(log_zip_path, policy):
    """
    Analyze a single simulation's optimality for a specific policy.
    Returns: dict with optimality metrics
    """
    temp_dir = tempfile.mkdtemp()
    
    try:
        with zipfile.ZipFile(log_zip_path, 'r') as zip_ref:
            visibility_file = f"{policy}/visibility_log.csv"
            try:
                zip_ref.extract(visibility_file, temp_dir)
            except KeyError:
                return None
        
        log_file = Path(temp_dir) / visibility_file
        df = pd.read_csv(log_file)
        
        # Reconstruct pre-download buffer state
        df['pre_download_buffer_mb'] = df['buffer_mb'] + df['downloaded_mb']
        
        results = []
        for timestep, group in df.groupby('time'):
            # Skip image capture timesteps
            if (group['image_taken'] == 1).any():
                continue
            
            # Check if any satellite is connected
            connected = group[group['connected'] == 1]
            if len(connected) == 0:
                continue
            
            # Find satellites with in_view=1 AND pre-download buffer > 0
            inview_with_data = group[(group['in_view'] == 1) & (group['pre_download_buffer_mb'] > 0)]
            
            if len(inview_with_data) == 0:
                continue
            
            # Find the best bitrate among in-view satellites WITH DATA
            best_bitrate = inview_with_data['bitrate_mbps'].max()
            best_sat_id = inview_with_data.loc[inview_with_data['bitrate_mbps'] == best_bitrate, 'sat_id'].iloc[0]
            
            # Check if connected to the best satellite
            connected_sat_id = connected['sat_id'].iloc[0]
            connected_bitrate = connected['bitrate_mbps'].iloc[0]
            is_optimal = (connected_sat_id == best_sat_id)
            
            # Calculate actual data downloaded
            connected_downloaded_mb = connected['downloaded_mb'].iloc[0]
            
            # What WOULD have been downloaded from best satellite
            best_sat_data = inview_with_data.loc[inview_with_data['sat_id'] == best_sat_id].iloc[0]
            best_potential_mb = best_sat_data['pre_download_buffer_mb']
            best_capacity_mb = best_sat_data['bitrate_mbps'] / 8.0
            best_would_download_mb = min(best_capacity_mb, best_potential_mb)
            
            results.append({
                'timestep': timestep,
                'best_sat_id': best_sat_id,
                'best_bitrate': best_bitrate,
                'best_would_download_mb': best_would_download_mb,
                'connected_sat_id': connected_sat_id,
                'connected_bitrate': connected_bitrate,
                'connected_downloaded_mb': connected_downloaded_mb,
                'optimal': is_optimal
            })
        
        if not results:
            return None
        
        results_df = pd.DataFrame(results)
        
        total_connections = len(results_df)
        optimal_count = results_df['optimal'].sum()
        optimality_pct = (optimal_count / total_connections) * 100
        
        # Bitrate efficiency
        avg_connected_bitrate = results_df['connected_bitrate'].mean()
        avg_best_bitrate = results_df['best_bitrate'].mean()
        bitrate_efficiency_pct = (avg_connected_bitrate / avg_best_bitrate) * 100 if avg_best_bitrate > 0 else 0
        
        # Data efficiency
        total_data_downloaded_mb = results_df['connected_downloaded_mb'].sum()
        total_optimal_data_mb = results_df['best_would_download_mb'].sum()
        data_efficiency_pct = (total_data_downloaded_mb / total_optimal_data_mb * 100) if total_optimal_data_mb > 0 else 0
        
        return {
            'policy': policy,
            'active_downlink_timesteps': total_connections,
            'optimal_connections': optimal_count,
            'optimality_pct': optimality_pct,
            'avg_connected_bitrate_Mbps': avg_connected_bitrate,
            'avg_best_available_bitrate_Mbps': avg_best_bitrate,
            'bitrate_efficiency_pct': bitrate_efficiency_pct,
            'total_data_downloaded_mb': total_data_downloaded_mb,
            'total_optimal_data_mb': total_optimal_data_mb,
            'data_efficiency_pct': data_efficiency_pct
        }
    
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)

def scan_all_configurations(search_dir='results/base results 2'):
    """Scan for all constellation_analysis folders"""
    configs = []
    
    search_path = Path(search_dir)
    for folder in search_path.glob('constellation_analysis_*'):
        if not folder.is_dir():
            continue
        
        match = re.match(r'constellation_analysis_\d{8}_\d{6}_(\d+)_(\d+)', folder.name)
        if match:
            image_size_kb = int(match.group(1))
            num_sats = int(match.group(2))
            
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

def create_stacked_efficiency_charts(results_dir='results/base results 2', metric='bitrate_efficiency'):
    """
    Create stacked bar charts showing efficiency metrics.
    
    Args:
        results_dir: Directory containing simulation results
        metric: One of 'bitrate_efficiency', 'optimality', or 'data_efficiency'
    """
    
    metric_labels = {
        'bitrate_efficiency': ('Bitrate Efficiency (%)', 'bitrate_efficiency_pct', 
                               'How close to optimal bitrate?\n(connected_bitrate / best_available_bitrate)'),
        'optimality': ('Optimal Selection (%)', 'optimality_pct',
                       'How often was the optimal satellite selected?'),
        'data_efficiency': ('Data Efficiency (%)', 'data_efficiency_pct',
                            'How much data vs optimal download?\n(actual_downloaded / optimal_downloadable)')
    }
    
    y_label, metric_col, subtitle = metric_labels[metric]
    
    print("="*110)
    print("=" * 30 + f" {y_label.upper()} STACKED BAR CHARTS")
    print(f"Metric: {subtitle}")
    print("X-axis: Link Policies | Stacks: Spacing Strategies")
    print("="*110)
    print()
    
    # Check for existing CSV
    output_dir = Path('constellation_analysis') / 'efficiency_charts'
    output_dir.mkdir(parents=True, exist_ok=True)
    existing_csv = output_dir / 'efficiency_data.csv'
    
    if existing_csv.exists():
        print(f"📊 Loading existing data from: {existing_csv}")
        results_df = pd.read_csv(existing_csv)
        print(f"✅ Loaded {len(results_df)} rows")
    else:
        print(f"Scanning for constellation configurations in: {results_dir}")
        configs_df = scan_all_configurations(results_dir)
        
        if len(configs_df) == 0:
            print("❌ No configurations found!")
            return None
        
        print(f"Found {len(configs_df)} configurations")
        print()
        
        results = []
        policies = ['sticky', 'fifo', 'roundrobin', 'random', 'mindistance', 'maxdownload']
        
        total_analyses = len(configs_df) * len(policies)
        current = 0
        
        for _, config in configs_df.iterrows():
            image_size_mb = config['image_size_kb'] / 1000.0
            
            for policy in policies:
                current += 1
                print(f"\r  Analyzing {current}/{total_analyses}: {config['strategy']}, {config['num_sats']} sats, {policy}...", end='')
                
                metrics = analyze_optimality(config['zip_path'], policy)
                
                if metrics:
                    results.append({
                        'image_size_mb': image_size_mb,
                        'strategy': config['strategy'],
                        'policy': policy,
                        'num_sats': config['num_sats'],
                        'optimality_pct': metrics['optimality_pct'],
                        'bitrate_efficiency_pct': metrics['bitrate_efficiency_pct'],
                        'data_efficiency_pct': metrics['data_efficiency_pct'],
                        'optimal_connections': metrics['optimal_connections'],
                        'total_connections': metrics['active_downlink_timesteps'],
                        'avg_connected_bitrate': metrics['avg_connected_bitrate_Mbps'],
                        'avg_best_bitrate': metrics['avg_best_available_bitrate_Mbps'],
                        'total_data_downloaded_mb': metrics['total_data_downloaded_mb'],
                        'total_optimal_data_mb': metrics['total_optimal_data_mb']
                    })
        
        print()  # Newline after progress
        
        if not results:
            print("❌ No valid results found!")
            return None
        
        results_df = pd.DataFrame(results)
        
        # Save raw data
        results_df.to_csv(existing_csv, index=False)
        print(f"✅ Saved: {existing_csv}")
    
    print()
    
    # Create charts
    create_charts(results_df, output_dir, metric_col, y_label, subtitle)
    
    return results_df

def create_charts(results_df, output_dir, metric_col, y_label, subtitle):
    """Create one stacked bar chart per image size"""
    
    image_sizes = sorted(results_df['image_size_mb'].unique())
    strategies = ['close-spaced', 'frame-spaced', 'orbit-spaced', 'close-orbit-spaced']
    policies = ['sticky', 'fifo', 'roundrobin', 'random', 'mindistance', 'maxdownload']
    sat_counts = sorted(results_df['num_sats'].unique())
    
    # Color scheme by STRATEGY
    strategy_colors = {
        'close-spaced': '#E63946',        # Red
        'frame-spaced': '#06A77D',        # Green
        'orbit-spaced': '#2E86AB',        # Blue
        'close-orbit-spaced': '#F77F00'   # Orange
    }
    
    policy_labels = {
        'sticky': 'STICKY',
        'fifo': 'FIFO',
        'roundrobin': 'ROUNDROBIN',
        'random': 'RANDOM',
        'mindistance': 'MINDISTANCE',
        'maxdownload': 'MAXDOWNLOAD'
    }
    
    strategy_labels = {
        'close-spaced': 'Close',
        'frame-spaced': 'Frame',
        'orbit-spaced': 'Orbit',
        'close-orbit-spaced': 'Close-Orbit'
    }
    
    for image_size in image_sizes:
        print(f"Creating {metric_col} chart for {image_size} MB...")
        
        subset = results_df[results_df['image_size_mb'] == image_size]
        
        if len(subset) == 0:
            continue
        
        fig, ax = plt.subplots(figsize=(20, 10))
        
        num_bars_per_group = len(policies)
        bar_width = 0.7
        group_width = num_bars_per_group * bar_width + 1.5
        
        x_positions = []
        x_labels = []
        
        # Build stacked bars - but for percentages we show AVERAGE not SUM
        for sat_idx, sat_count in enumerate(sat_counts):
            for policy_idx, policy in enumerate(policies):
                x_pos = sat_idx * group_width + policy_idx * bar_width
                x_positions.append(x_pos)
                x_labels.append(policy_labels[policy])
                
                # For efficiency percentages, we show individual strategy values stacked
                # Each strategy contributes (value / 4) to a normalized 100% scale
                # OR we show them side by side as grouped bars within the stack
                
                # Actually for this viz, let's show the WEIGHTED AVERAGE across strategies
                # and use bar height to show the efficiency, with color segments showing
                # contribution from each strategy
                
                bottom = 0
                total_value = 0
                strategy_values = []
                
                for strategy in strategies:
                    data = subset[
                        (subset['strategy'] == strategy) & 
                        (subset['policy'] == policy) & 
                        (subset['num_sats'] == sat_count)
                    ]
                    
                    if len(data) > 0:
                        value = data[metric_col].values[0]
                    else:
                        value = 0
                    
                    strategy_values.append(value)
                    total_value += value
                
                # Normalize: each strategy contributes proportionally
                # Stack shows the efficiency percentage contribution from each strategy
                avg_value = total_value / len(strategies) if strategies else 0
                
                for i, (strategy, value) in enumerate(zip(strategies, strategy_values)):
                    # Each segment height = value / 4 (so total stack = average)
                    segment_height = value / len(strategies)
                    
                    ax.bar(x_pos, segment_height, bar_width, bottom=bottom,
                          color=strategy_colors[strategy],
                          edgecolor='white', linewidth=1.5,
                          label=strategy_labels[strategy] if sat_idx == 0 and policy_idx == 0 else "")
                    
                    # Add value label if segment is large enough
                    if segment_height > 3:
                        text_y = bottom + segment_height / 2
                        ax.text(x_pos, text_y, f'{value:.0f}%',
                               ha='center', va='center',
                               fontsize=7, fontweight='bold',
                               color='white',
                               bbox=dict(boxstyle='round,pad=0.2',
                                        facecolor='black',
                                        edgecolor='none',
                                        alpha=0.6))
                    
                    bottom += segment_height
                
                # Add average at top
                if bottom > 0:
                    ax.text(x_pos, bottom + 1, f'{avg_value:.1f}%',
                           ha='center', va='bottom',
                           fontsize=10, fontweight='bold',
                           color='black')
        
        # Set x-axis
        ax.set_xticks(x_positions)
        ax.set_xticklabels(x_labels, fontsize=9, rotation=45, ha='right')
        ax.set_xlabel('Link Selection Policy', fontsize=14, fontweight='bold')
        
        # Satellite count labels
        sat_centers = []
        for sat_idx in range(len(sat_counts)):
            center = sat_idx * group_width + (num_bars_per_group * bar_width - bar_width) / 2
            sat_centers.append(center)
        
        ax2 = ax.secondary_xaxis('bottom')
        ax2.set_xticks(sat_centers)
        ax2.set_xticklabels([f'{s} Satellites' for s in sat_counts],
                            fontsize=13, fontweight='bold')
        ax2.tick_params(axis='x', which='major', pad=45)
        
        # Vertical separators
        for sat_idx in range(1, len(sat_counts)):
            separator_x = sat_idx * group_width - 0.75
            ax.axvline(x=separator_x, color='black', linestyle='-', linewidth=2.5, alpha=0.4)
        
        # Y-axis
        ax.set_ylabel(y_label, fontsize=14, fontweight='bold')
        ax.set_ylim(0, 105)  # Percentage scale
        
        # Add 100% reference line
        ax.axhline(y=100, color='green', linestyle='--', linewidth=2, alpha=0.5, label='100% (Perfect)')
        
        # Title
        ax.set_title(f'{y_label} by Policy\n{image_size} MB Images - {subtitle}',
                    fontsize=16, fontweight='bold', pad=20)
        
        # Legend
        ax.legend(title='Spacing Strategy', fontsize=11, title_fontsize=12,
                 loc='lower right', framealpha=0.95, edgecolor='black')
        
        # Grid
        ax.grid(True, alpha=0.3, linestyle='--', axis='y')
        ax.set_axisbelow(True)
        
        plt.tight_layout()
        
        # Save
        filename = f'{metric_col}_{image_size}mb.png'
        output_file = output_dir / filename
        plt.savefig(output_file, dpi=300, bbox_inches='tight')
        print(f"✅ Saved: {output_file}")
        plt.close()
    
    print()
    print("="*110)
    print("✅ EFFICIENCY CHARTS COMPLETE!")
    print("="*110)
    print()
    print("Chart Structure:")
    print(f"  X-AXIS: {len(sat_counts)} satellite count groups ({', '.join(map(str, sat_counts))} sats)")
    print(f"          Each group has {len(policies)} bars (one per policy)")
    print()
    print(f"  Y-AXIS: {y_label}")
    print()
    print("  STACKS: Each bar shows average efficiency across 4 strategies:")
    print("    🔴 Red    = Close-spaced")
    print("    🟢 Green  = Frame-spaced")
    print("    🔵 Blue   = Orbit-spaced")
    print("    🟠 Orange = Close-Orbit-spaced")
    print()
    print("  VALUES: Number in each segment = that strategy's efficiency %")
    print("          Number above bar = average across all strategies")

if __name__ == '__main__':
    import os
    import sys
    
    script_dir = Path(__file__).parent
    os.chdir(script_dir)
    
    # Parse arguments
    results_dir = 'results/base results 2'
    metric = 'bitrate_efficiency'
    
    for arg in sys.argv[1:]:
        if arg in ['bitrate_efficiency', 'optimality', 'data_efficiency']:
            metric = arg
        elif not arg.startswith('-'):
            results_dir = arg
    
    print(f"Using results directory: {results_dir}")
    print(f"Metric: {metric}")
    print()
    
    results_df = create_stacked_efficiency_charts(results_dir, metric=metric)
    
    if results_df is not None:
        print()
        print("✨ Efficiency analysis complete!")
        print()
        print("Available metrics (pass as argument):")
        print("  bitrate_efficiency - How close to optimal bitrate?")
        print("  optimality         - How often was optimal satellite selected?")
        print("  data_efficiency    - How much data vs optimal?")
