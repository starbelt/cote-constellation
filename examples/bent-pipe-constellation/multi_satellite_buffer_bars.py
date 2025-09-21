#!/usr/bin/env python3
"""
Multi-Satellite Data Distribution Bar Chart Analysis

Shows total data downloaded per satellite per orbital pass with stacked bars
and summary statistics for satellites served per policy.

Updated to use constellation analysis folders like other analysis scripts.
"""

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from pathlib import Path
from datetime import datetime
import zipfile
import glob
import os
import tempfile
import shutil

# Configuration - use absolute paths
SCRIPT_DIR = Path(__file__).parent.absolute()
SPACING_STRATEGIES = ["close-spaced", "close-orbit-spaced", "frame-spaced", "orbit-spaced"]
POLICIES = ["sticky", "fifo", "roundrobin", "random"]

def find_latest_constellation_analysis_folder():
    """Find the most recent constellation_analysis_* folder"""
    # Look in the current directory first (bent-pipe-constellation folder)
    constellation_folders = [d for d in SCRIPT_DIR.iterdir() 
                           if d.is_dir() and d.name.startswith('constellation_analysis_')]
    
    if not constellation_folders:
        print("No constellation_analysis_* folders found!")
        print(f"Searched in: {SCRIPT_DIR}")
        return None
    
    # Sort by folder name (which includes timestamp) to get the latest
    latest_folder = sorted(constellation_folders, key=lambda x: x.name)[-1]
    print(f"Using latest analysis folder: {latest_folder.name}")
    return latest_folder

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
                            config['frame_spacing'] = float(values[i])
    
    return config

def get_buffer_data_for_strategy(strategy, constellation_folder):
    """Get total data downloaded per satellite per policy for a specific strategy"""
    strategy_path = constellation_folder / strategy
    archive_path = strategy_path / 'simulation_logs.zip'
    
    if not archive_path.exists():
        print(f"  Warning: Archive not found: {archive_path}")
        return {}
    
    # Create temporary directory for extraction
    temp_dir = Path(tempfile.mkdtemp(prefix=f'{strategy}_extract_'))
    
    try:
        # Extract the zip file
        with zipfile.ZipFile(archive_path, 'r') as zip_ref:
            zip_ref.extractall(temp_dir)
        
        results = {}
        
        # Process each policy
        for policy in POLICIES:
            policy_dir = temp_dir / policy
            
            if not policy_dir.exists():
                continue
                
            results[policy] = {}
            
            # Look for buffer files
            buffer_files = list(policy_dir.glob("meas-MB-buffered-sat-*.csv"))
            
            for buffer_file in buffer_files:
                # Extract satellite ID from filename
                sat_id = buffer_file.stem.split('meas-MB-buffered-sat-')[1]
                
                try:
                    buffer_df = pd.read_csv(buffer_file)
                    
                    if len(buffer_df) > 1:
                        buffer_col = f"MB-buffered-sat-{sat_id}"
                        
                        if buffer_col in buffer_df.columns:
                            # Calculate total data downloaded by looking at buffer decrease
                            buffer_df['prev_value'] = buffer_df[buffer_col].shift(1)
                            buffer_df['decrease'] = buffer_df['prev_value'] - buffer_df[buffer_col]
                            
                            # Sum all buffer decreases (data flowing out)
                            total_downloaded = buffer_df[buffer_df['decrease'] > 0]['decrease'].sum()
                            
                            if total_downloaded > 0:
                                results[policy][sat_id] = total_downloaded
                except Exception as e:
                    continue
        
        return results
        
    except Exception as e:
        print(f"  Error extracting {archive_path}: {e}")
        return {}
    finally:
        # Clean up temporary directory
        if temp_dir.exists():
            shutil.rmtree(temp_dir)

def create_bar_chart_for_strategy(strategy, buffer_results, config, output_dir):
    """Create bar chart for a specific strategy showing policy performance"""
    if not buffer_results:
        print(f"  No data for strategy: {strategy}")
        return
    
    # Set consistent font family
    plt.rcParams['font.family'] = 'DejaVu Sans'
    plt.rcParams['font.sans-serif'] = ['DejaVu Sans', 'Arial', 'Helvetica', 'sans-serif']
    
    # Create figure
    fig, ax = plt.subplots(1, 1, figsize=(12, 8))
    
    # Calculate totals for each policy
    policy_totals = {}
    policy_satellites_served = {}
    
    for policy in POLICIES:
        if policy not in buffer_results:
            policy_totals[policy] = 0
            policy_satellites_served[policy] = 0
            continue
            
        policy_data = buffer_results[policy]
        total_data = sum(policy_data.values())
        satellites_served = len([sat for sat, data in policy_data.items() if data > 0])
        
        policy_totals[policy] = total_data
        policy_satellites_served[policy] = satellites_served
    
    # Prepare data for plotting
    policies = POLICIES
    totals = [policy_totals[p] for p in policies]
    satellites_counts = [policy_satellites_served[p] for p in policies]
    
    # Create colors - use policy-specific colors for consistency
    colors = {'sticky': '#2E8B57', 'fifo': '#4682B4', 'roundrobin': '#DAA520', 'random': '#CD5C5C'}
    bar_colors = [colors.get(policy.lower(), '#888888') for policy in policies]
    
    # Create the bar chart
    bars = ax.bar(policies, totals, color=bar_colors, alpha=0.8, edgecolor='black', linewidth=1)
    
    # Customize the plot
    strategy_display = strategy.replace('-', ' ').title()
    ax.set_ylabel('Total Data Downloaded (MB)', fontweight='bold', fontsize=12)
    ax.set_xlabel('Scheduling Policy', fontweight='bold', fontsize=12)
    ax.set_title(f'Total Data Downloaded by Policy - {strategy_display} Strategy\n(Constellation Performance Comparison)', 
                fontweight='bold', fontsize=14, pad=20)
    
    # Add value labels on bars
    if totals and max(totals) > 0:
        for i, (bar, total, sat_count) in enumerate(zip(bars, totals, satellites_counts)):
            height = bar.get_height()
            # Show total MB and satellite count
            ax.text(bar.get_x() + bar.get_width()/2., height + max(totals)*0.01,
                    f'{total:.0f} MB\n({sat_count} sats)',
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
    output_path = output_dir / f"buffer_bars_{strategy}_strategy.png"
    plt.savefig(output_path, dpi=300, bbox_inches='tight', facecolor='white')
    plt.close()
    
    print(f"  Generated buffer bar chart for {strategy} -> {output_path.name}")
    
    # Print ranking for this strategy
    if any(totals):
        sorted_policies = sorted([(p, policy_totals[p]) for p in POLICIES], key=lambda x: x[1], reverse=True)
        ranking = " > ".join([policy.upper() for policy, total in sorted_policies if total > 0])
        if ranking:
            print(f"  {strategy_display} strategy ranking: {ranking}")

def create_bar_charts():
    """Create bar charts for all strategies"""
    print("Multi-Satellite Buffer Distribution Bar Chart Analysis")
    
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
        
        # Get buffer data for this strategy
        buffer_results = get_buffer_data_for_strategy(strategy, constellation_folder)
        
        # Create bar chart for this strategy
        create_bar_chart_for_strategy(strategy, buffer_results, config, output_dir)
    
    print(f"\nAll charts generated in: {output_dir}")
    print("Charts show total data downloaded per policy for each spacing strategy.")

def main():
    """Main function to run analysis"""
    create_bar_charts()

if __name__ == "__main__":
    main()
