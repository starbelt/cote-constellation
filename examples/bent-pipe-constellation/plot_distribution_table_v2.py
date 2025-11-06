#!/usr/bin/env python3
"""Plot the distribution table comparing orbit-spaced vs close-orbit-spaced (100 satellites)"""

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import zipfile
from pathlib import Path

def plot_distribution_table_v2():
    """Create bar chart visualization comparing orbit-spaced vs close-orbit-spaced"""
    
    zip_orbit = 'constellation_analysis_20251022_214230_28000_100/orbit-spaced/simulation_logs.zip'
    zip_close = 'constellation_analysis_20251022_214230_28000_100/close-orbit-spaced/simulation_logs.zip'
    
    print("Loading data...")
    with zipfile.ZipFile(zip_orbit, 'r') as zipf:
        with zipf.open('fifo/visibility_log.csv') as f:
            df_orbit = pd.read_csv(f)
    
    with zipfile.ZipFile(zip_close, 'r') as zipf:
        with zipf.open('fifo/visibility_log.csv') as f:
            df_close = pd.read_csv(f)
    
    rates_orbit = df_orbit[df_orbit['connected'] == 1]['downloaded_mb'].values
    rates_close = df_close[df_close['connected'] == 1]['downloaded_mb'].values
    
    # Create bins - extend to 18 MB to capture all close-orbit-spaced data
    bins = np.arange(0, 18, 0.5)
    hist_orbit, _ = np.histogram(rates_orbit, bins=bins)
    hist_close, _ = np.histogram(rates_close, bins=bins)
    
    # Create labels for each bin
    labels = [f'{bins[i]:.1f}-{bins[i+1]:.1f}' for i in range(len(bins)-1)]
    
    # Focus on the interesting range (11.5-18.0) - extended to show full picture
    interesting_start = int(11.5 / 0.5)
    interesting_end = len(bins) - 1  # Show all bins up to 18.0
    
    interesting_labels = labels[interesting_start:interesting_end]
    interesting_orbit = hist_orbit[interesting_start:interesting_end]
    interesting_close = hist_close[interesting_start:interesting_end]
    
    # Calculate data volume (GB) for each bin - CORRECTED METHOD
    # Sum ACTUAL downloaded values in each bin, not bin_midpoint × count
    data_gb_orbit = []
    data_gb_close = []
    for i in range(len(interesting_orbit)):
        bin_idx = interesting_start + i
        bin_start = bins[bin_idx]
        bin_end = bins[bin_idx + 1]
        
        # Get actual values in this bin and sum them
        mask_orbit = (rates_orbit >= bin_start) & (rates_orbit < bin_end)
        mask_close = (rates_close >= bin_start) & (rates_close < bin_end)
        
        actual_sum_orbit_mb = np.sum(rates_orbit[mask_orbit])
        actual_sum_close_mb = np.sum(rates_close[mask_close])
        
        data_gb_orbit.append(actual_sum_orbit_mb / 1024)  # MB to GB
        data_gb_close.append(actual_sum_close_mb / 1024)  # MB to GB
    
    # Create figure
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(20, 8))
    
    color_orbit = '#2E86AB'
    color_close = '#A23B72'
    
    # 1. Side-by-side bars (interesting range only)
    x = np.arange(len(interesting_labels))
    width = 0.35
    
    bars1 = ax1.bar(x - width/2, interesting_orbit, width, label='orbit-spaced', 
                    color=color_orbit, alpha=0.8, edgecolor='black', linewidth=1)
    bars2 = ax1.bar(x + width/2, interesting_close, width, label='close-orbit-spaced',
                    color=color_close, alpha=0.8, edgecolor='black', linewidth=1)
    
    # Add value labels on bars (count + data in GB)
    for i, bar in enumerate(bars1):
        height = bar.get_height()
        if height > 0:
            ax1.text(bar.get_x() + bar.get_width()/2., height,
                    f'{int(height):,}\n({data_gb_orbit[i]:.1f} GB)',
                    ha='center', va='bottom', fontsize=8, fontweight='bold')
    
    for i, bar in enumerate(bars2):
        height = bar.get_height()
        if height > 0:
            ax1.text(bar.get_x() + bar.get_width()/2., height,
                    f'{int(height):,}\n({data_gb_close[i]:.1f} GB)',
                    ha='center', va='bottom', fontsize=8, fontweight='bold')
    
    # Add total data labels in legend
    total_data_orbit = sum(data_gb_orbit)
    total_data_close = sum(data_gb_close)
    
    ax1.set_xlabel('Download Rate Range (MB/timestep)', fontsize=13, fontweight='bold')
    ax1.set_ylabel('Count (number of downloads)', fontsize=13, fontweight='bold')
    ax1.set_title(f'Download Rate Distribution: orbit-spaced vs close-orbit-spaced (100 satellites)\n' + 
                  f'orbit-spaced: {total_data_orbit:.1f} GB total  |  close-orbit-spaced: {total_data_close:.1f} GB total  |  Δ = {total_data_close - total_data_orbit:+.1f} GB', 
                  fontsize=13, fontweight='bold')
    ax1.set_xticks(x)
    ax1.set_xticklabels(interesting_labels, rotation=45, ha='right')
    ax1.legend(fontsize=12, loc='upper left')
    ax1.grid(True, axis='y', alpha=0.3)
    
    # Add threshold line at 14.0 MB - where close-orbit-spaced starts dominating
    try:
        threshold_idx = list(interesting_labels).index('14.0-14.5')
        ax1.axvline(threshold_idx - 0.5, color='red', linestyle='--', linewidth=2.5, 
                    alpha=0.7, label='14.0 MB threshold')
    except ValueError:
        pass  # Threshold not in visible range
    
    
    # 2. Difference bars (in GB of data)
    data_diff_gb = [data_gb_orbit[i] - data_gb_close[i] for i in range(len(data_gb_orbit))]
    colors = [color_orbit if d > 0 else color_close for d in data_diff_gb]
    
    bars3 = ax2.bar(x, data_diff_gb, color=colors, alpha=0.8, edgecolor='black', linewidth=1)
    
    # Add value labels (GB difference) - only show if significant
    for i, (bar, diff_gb) in enumerate(zip(bars3, data_diff_gb)):
        height = bar.get_height()
        count_diff = interesting_orbit[i] - interesting_close[i]
        if abs(diff_gb) >= 1.0:  # Only label if >= 1 GB difference
            ax2.text(bar.get_x() + bar.get_width()/2., height,
                    f'{diff_gb:+.1f} GB\n({count_diff:+,} DL)',
                    ha='center', va='bottom' if diff_gb > 0 else 'top', 
                    fontsize=8, fontweight='bold')
    
    ax2.axhline(0, color='black', linewidth=1)
    try:
        threshold_idx_2 = list(interesting_labels).index('14.0-14.5')
        ax2.axvline(threshold_idx_2 - 0.5, color='red', linestyle='--', linewidth=2.5, alpha=0.7)
    except ValueError:
        pass
    
    ax2.set_xlabel('Download Rate Range (MB/timestep)', fontsize=13, fontweight='bold')
    ax2.set_ylabel('Data Difference (GB): orbit-spaced minus close-orbit-spaced', fontsize=13, fontweight='bold')
    ax2.set_title(f'Data Volume Impact by Rate Range\n' +
                  f'(Positive = orbit-spaced wins, Negative = close-orbit-spaced wins)', 
                  fontsize=13, fontweight='bold')
    ax2.set_xticks(x)
    ax2.set_xticklabels(interesting_labels, rotation=45, ha='right')
    ax2.grid(True, axis='y', alpha=0.3)
    
    plt.tight_layout()
    
    # Save
    output_dir = Path('constellation_analysis') / 'comparison_charts'
    output_dir.mkdir(parents=True, exist_ok=True)
    output_file = output_dir / 'distribution_table_orbit_vs_close_100sat.png'
    plt.savefig(output_file, dpi=300, bbox_inches='tight')
    print(f"\n✅ Saved: {output_file}")
    plt.close()
    
    # Print the actual table
    print("\n" + "="*110)
    print("DISTRIBUTION TABLE (11.5-13.5 MB range): orbit-spaced vs close-orbit-spaced (100 satellites)")
    print("="*110)
    print()
    print(f'{"Range (MB)":>15} | {"orbit-spaced":>13} {"close-orbit":>13} | {"Difference":>12} {"orbit wins?":>15}')
    print('-'*110)
    
    for i, label in enumerate(interesting_labels):
        c_orbit = interesting_orbit[i]
        c_close = interesting_close[i]
        diff = c_orbit - c_close
        winner = "✓ YES" if diff > 0 else "NO"
        marker = " ⚠️ KEY!" if abs(diff) > 1000 else ""
        print(f'{label:>15} | {c_orbit:>13,} {c_close:>13,} | {diff:>+12,} {winner:>15}{marker}')
    
    print()
    print("="*110)
    print()
    print("SUMMARY:")
    print(f"  • orbit-spaced total in this range: {interesting_orbit.sum():,}")
    print(f"  • close-orbit-spaced total in this range: {interesting_close.sum():,}")
    print(f"  • Net difference: {interesting_orbit.sum() - interesting_close.sum():+,}")
    
    # Calculate total data downloaded in this range
    total_data_orbit = sum((bins[interesting_start + i] + bins[interesting_start + i + 1]) / 2 * interesting_orbit[i] 
                           for i in range(len(interesting_orbit)))
    total_data_close = sum((bins[interesting_start + i] + bins[interesting_start + i + 1]) / 2 * interesting_close[i] 
                           for i in range(len(interesting_close)))
    
    print()
    print("DATA VOLUME IN THIS RANGE:")
    print(f"  • orbit-spaced: {total_data_orbit:,.1f} MB")
    print(f"  • close-orbit-spaced: {total_data_close:,.1f} MB")
    print(f"  • Difference: {total_data_orbit - total_data_close:+,.1f} MB")
    
    # Analyze the pattern
    print()
    if interesting_orbit.sum() > interesting_close.sum():
        print("ORBIT-SPACED ADVANTAGE:")
    else:
        print("CLOSE-ORBIT-SPACED ADVANTAGE:")
    
    # Find where each wins (count differences)
    count_differences = interesting_orbit - interesting_close
    orbit_wins_bins = [i for i, diff in enumerate(count_differences) if diff > 0]
    close_wins_bins = [i for i, diff in enumerate(count_differences) if diff < 0]
    
    if orbit_wins_bins:
        print(f"  • orbit-spaced wins in bins: {', '.join(interesting_labels[i] for i in orbit_wins_bins)}")
        print(f"    Download count advantage: +{sum(count_differences[i] for i in orbit_wins_bins):,} downloads")
        print(f"    Data volume advantage: +{sum(data_diff_gb[i] for i in orbit_wins_bins):.1f} GB")
    
    if close_wins_bins:
        print(f"  • close-orbit-spaced wins in bins: {', '.join(interesting_labels[i] for i in close_wins_bins)}")
        print(f"    Download count advantage: +{abs(sum(count_differences[i] for i in close_wins_bins)):,} downloads")
        print(f"    Data volume advantage: +{abs(sum(data_diff_gb[i] for i in close_wins_bins)):.1f} GB")

if __name__ == '__main__':
    plot_distribution_table_v2()
