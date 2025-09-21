#!/usr/bin/env python3
"""
Multi-Satellite Data Loss Bar Chart Analysis

Shows total data lost per policy with clean bar chart visualization
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
SPACING_STRATEGIES = ["close-spaced", "frame-spaced", "orbit-spaced"]

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

def get_loss_data_for_strategy(strategy, constellation_folder):
    """Extract loss data for a specific strategy from constellation analysis folder"""
    strategy_folder = constellation_folder / strategy
    if not strategy_folder.exists():
        print(f"  Strategy folder not found: {strategy}")
        return {}
    
    simulation_logs_zip = strategy_folder / "simulation_logs.zip"
    if not simulation_logs_zip.exists():
        print(f"  No simulation_logs.zip found for {strategy}")
        return {}
    
    loss_results = {}
    
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
            
            # Calculate loss data for this policy using real overflow logs
            policy_loss_data = calculate_loss_for_policy(policy_dir)
            if policy_loss_data is not None:
                loss_results[policy] = policy_loss_data
    
    return loss_results

def calculate_loss_for_policy(policy_dir):
    """Calculate total data loss for a specific policy directory using real overflow logs"""
    # Find all buffer overflow files
    overflow_files = list(policy_dir.glob("meas-buffer-overflow-sat-*.csv"))
    
    if not overflow_files:
        # No overflow files means no loss
        return 0.0
    
    total_loss_mb = 0.0
    
    for overflow_file in overflow_files:
        try:
            # Read overflow data
            df = pd.read_csv(overflow_file)
            
            if df.empty:
                continue
            
            # The overflow data is CUMULATIVE - take the maximum value (final cumulative loss)
            # Following the logic from generate_spacing_comparison.py
            
            # Handle 3-column format by taking first 2 columns
            if len(df.columns) == 3:
                df = df.iloc[:, :2]
            
            # Rename columns for clarity
            df.columns = ['timestamp', 'cumulative_loss_mb']
            
            # Get the final cumulative loss value for this satellite
            cumulative_loss_values = pd.to_numeric(df['cumulative_loss_mb'], errors='coerce').dropna()
            
            if len(cumulative_loss_values) > 0:
                # Use the maximum cumulative loss (final value) - this is the total loss for this satellite
                satellite_total_loss = cumulative_loss_values.max()
                total_loss_mb += satellite_total_loss
                
        except Exception as e:
            print(f"    Error processing {overflow_file.name}: {e}")
            continue
    
    return total_loss_mb

def get_policy_dirs():
    """Get policy directories (legacy function for backward compatibility)"""
    dirs = {}
    for policy in POLICIES:
        policy_dir = LOGS_DIR / policy
        if policy_dir.exists():
            dirs[policy] = policy_dir
    return dirs

def analyze_satellite_data_loss():
    """Analyze total data loss per policy from buffer overflow files"""
    policy_dirs = get_policy_dirs()
    config = read_config()
    mb_per_sense = config.get('mb_per_sense', 50.0)  # Default fallback
    
    results = {}
    total_overflow_files_found = 0
    
    for policy, policy_dir in policy_dirs.items():
        total_loss_mb = 0
        satellites_with_loss = set()
        
        # Find all buffer overflow files for this policy
        overflow_files = list(policy_dir.glob("meas-buffer-overflow-sat-*.csv"))
        total_overflow_files_found += len(overflow_files)
        
        for overflow_file in overflow_files:
            # Extract satellite ID from filename
            sat_id = overflow_file.stem.split('-')[-1]
            
            try:
                df = pd.read_csv(overflow_file)
                if not df.empty:
                    # Handle different possible column structures
                    if len(df.columns) >= 2:
                        df = df.iloc[:, :2]  # Keep only first 2 columns
                        df.columns = ["timestamp", "overflow_count"]
                        
                        # Convert overflow count to numeric
                        df["overflow_count"] = pd.to_numeric(df["overflow_count"], errors='coerce')
                        
                        # Sum all overflow events for this satellite
                        satellite_overflow_events = df["overflow_count"].sum()
                        if pd.notna(satellite_overflow_events) and satellite_overflow_events > 0:
                            satellite_loss_mb = satellite_overflow_events * mb_per_sense
                            total_loss_mb += satellite_loss_mb
                            satellites_with_loss.add(sat_id)
                            
            except Exception as e:
                print(f"Warning: Could not process {overflow_file}: {e}")
                continue
        
        results[policy] = {
            'total_loss_mb': total_loss_mb,
            'satellites_with_loss': len(satellites_with_loss),
            'satellites_affected': satellites_with_loss
        }
    
    return results

def create_loss_bar_chart(output_dir=None):
    """Create clean bar chart showing total data loss per policy"""
    config = read_config()
    loss_results = analyze_satellite_data_loss()
    
    # Always create the chart regardless of whether there are losses
    
    # Save plot - use provided output directory or create timestamped one
    if output_dir is None:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_dir = SCRIPT_DIR / f"analysis_{timestamp}"
        output_dir.mkdir(exist_ok=True)
    
    # Set consistent font family for the entire plot
    plt.rcParams['font.family'] = 'DejaVu Sans'
    plt.rcParams['font.sans-serif'] = ['DejaVu Sans', 'Arial', 'Helvetica', 'sans-serif']
    
    # Create figure - cleaner layout for simple bar chart
    fig, ax = plt.subplots(1, 1, figsize=(12, 8))
    
    # Extract data for plotting
    policy_totals = {}
    policy_satellites_affected = {}
    
    for policy in POLICIES:
        if policy in loss_results and policy != '_metadata':
            policy_totals[policy] = loss_results[policy]['total_loss_mb']
            policy_satellites_affected[policy] = loss_results[policy]['satellites_with_loss']
        else:
            policy_totals[policy] = 0
            policy_satellites_affected[policy] = 0
    
    # Sort policies by total data loss (least loss first - best performance first)
    sorted_policies = sorted([p for p in POLICIES if p in policy_totals], 
                           key=lambda p: policy_totals[p])
    
    # Create data for plotting
    policy_labels = [policy.upper() for policy in sorted_policies]
    loss_values = [policy_totals[policy] for policy in sorted_policies]
    satellite_counts = [policy_satellites_affected[policy] for policy in sorted_policies]
    
    # Check if all values are zero
    all_zero = all(val == 0 for val in loss_values)
    total_loss = sum(loss_values)
    
    if all_zero:
        # Special handling for zero loss case - use green colors to indicate good performance
        bar_colors = ['#d4edda'] * len(sorted_policies)  # Light green for all
        title_suffix = "No Data Loss Detected!"
    else:
        # Use red gradient for losses (lighter red = better performance = less loss)
        red_colors = ['#fee5d9', '#fcbba1', '#fc9272', '#de2d26'][:len(sorted_policies)]
        bar_colors = red_colors
        title_suffix = "Total Data Lost Due to Buffer Overflow"
    
    # Handle case where all values are 0 or very close
    max_loss = max(loss_values) if loss_values else 1
    min_loss = min(loss_values) if loss_values else 0
    
    # Create the bar chart
    x_positions = np.arange(len(policy_labels))
    bars = ax.bar(x_positions, loss_values, color=bar_colors, alpha=0.8, width=0.6)
    
    # Adjust y-axis for better visibility
    if all_zero:
        # For zero loss, show a small range to make the chart look proper
        ax.set_ylim(0, 10)
    elif max_loss > 0:
        if max_loss - min_loss < max_loss * 0.1:  # Values are very close
            # Set y-axis to show differences better
            y_range = max_loss * 0.2 if max_loss > 0 else 10
            y_min = max(0, min_loss - y_range * 0.1)
            y_max = max_loss + y_range * 0.1
            ax.set_ylim(y_min, y_max)
        else:
            ax.set_ylim(0, max_loss * 1.1)
    else:
        ax.set_ylim(0, 10)  # Default range if no losses
    
    # Add value labels on top of each bar
    for i, (bar, policy, satellites) in enumerate(zip(bars, sorted_policies, satellite_counts)):
        height = bar.get_height()
        
        # Main data label
        label_y = height + (ax.get_ylim()[1] - ax.get_ylim()[0]) * 0.02
        label_color = '#28a745' if all_zero else '#8b0000'  # Green for zero, red for losses
        ax.text(bar.get_x() + bar.get_width()/2, label_y,
               f'{height:.1f} MB',
               ha='center', va='bottom', fontweight='bold', fontsize=14,
               family='DejaVu Sans', color=label_color)
        
        # Satellite count label inside the bar (if bar is tall enough) or below for zero case
        if all_zero:
            # For zero loss, put text in the middle of the chart area
            middle_y = ax.get_ylim()[1] * 0.5
            ax.text(bar.get_x() + bar.get_width()/2, middle_y,
                   'No Buffer\nOverflows',
                   ha='center', va='center', fontweight='bold', fontsize=12,
                   family='DejaVu Sans', color='#155724',
                   bbox=dict(boxstyle='round,pad=0.4', facecolor='#d4edda', alpha=0.9, edgecolor='#28a745'))
        elif height > (ax.get_ylim()[1] - ax.get_ylim()[0]) * 0.1:
            middle_y = (height + ax.get_ylim()[0]) * 0.5
            ax.text(bar.get_x() + bar.get_width()/2, middle_y,
                   f'{satellites} satellites' if satellites > 0 else 'No losses',
                   ha='center', va='center', fontweight='bold', fontsize=12,
                   family='DejaVu Sans', color='white',
                   bbox=dict(boxstyle='round,pad=0.3', facecolor='black', alpha=0.7))
    
    # Create enhanced title
    title_lines = ["Satellite Constellation Data Loss Analysis"]
    
    # Add constellation parameters
    sat_count = config.get('satellite_count', 'Unknown')
    frame_spacing = config.get('frame_spacing')
    mb_per_sense = config.get('mb_per_sense')
    
    if sat_count != 'Unknown' and frame_spacing and mb_per_sense:
        title_lines.append(f"{sat_count} Satellites | Frame Rate: 1 image/{frame_spacing:.1f}s | Image Size: {mb_per_sense:.2f} MB")
    elif mb_per_sense:
        title_lines.append(f"Image Size: {mb_per_sense:.2f} MB")
    
    title_lines.append(title_suffix)
    
    title = '\n'.join(title_lines)
    fig.suptitle(title, fontsize=16, fontweight='bold', family='DejaVu Sans')
    
    # Customize the chart
    ax.set_xlabel('Scheduling Policy (Ordered by Performance - Best First)', fontweight='bold', fontsize=14, family='DejaVu Sans')
    ax.set_ylabel('Total Data Lost (MB)', fontweight='bold', fontsize=14, family='DejaVu Sans')
    ax.set_xticks(x_positions)
    ax.set_xticklabels(policy_labels, fontsize=12, fontweight='bold', family='DejaVu Sans')
    
    # Add horizontal grid for easier reading
    ax.grid(True, alpha=0.3, axis='y', linestyle='--')
    ax.set_axisbelow(True)
    
    # Style the axes
    ax.tick_params(axis='y', labelsize=11)
    for label in ax.get_yticklabels():
        label.set_family('DejaVu Sans')
    
    plt.tight_layout()
    plt.savefig(output_dir / "satellite_loss_bars.png", dpi=300, bbox_inches='tight')
    plt.close()
def create_bar_chart_for_strategy(strategy, loss_results, config, output_dir):
    """Create bar chart for a specific strategy showing policy performance"""
    if loss_results is None:
        print(f"  No data for strategy: {strategy}")
        return
    
    # Set consistent font family
    plt.rcParams['font.family'] = 'DejaVu Sans'
    plt.rcParams['font.sans-serif'] = ['DejaVu Sans', 'Arial', 'Helvetica', 'sans-serif']
    
    # Create figure
    fig, ax = plt.subplots(1, 1, figsize=(12, 8))
    
    # Prepare data for plotting
    policies = POLICIES
    totals = [loss_results.get(p, 0) for p in policies]
    
    # Create colors - use red tones for loss (darker = worse)
    colors = {'sticky': '#FF6B6B', 'fifo': '#FF4757', 'roundrobin': '#FF3838', 'random': '#FF1E1E'}
    bar_colors = [colors.get(policy.lower(), '#888888') for policy in policies]
    
    # Create the bar chart
    bars = ax.bar(policies, totals, color=bar_colors, alpha=0.8, edgecolor='black', linewidth=1)
    
    # Customize the plot
    strategy_display = strategy.replace('-', ' ').title()
    ax.set_ylabel('Total Data Loss (MB)', fontweight='bold', fontsize=12)
    ax.set_xlabel('Scheduling Policy', fontweight='bold', fontsize=12)
    ax.set_title(f'Total Data Loss by Policy - {strategy_display} Strategy\n(Constellation Performance Comparison)', 
                fontweight='bold', fontsize=14, pad=20)
    
    # Add value labels on bars
    if totals and max(totals) > 0:
        for i, (bar, total) in enumerate(zip(bars, totals)):
            height = bar.get_height()
            # Show total MB lost
            ax.text(bar.get_x() + bar.get_width()/2., height + max(totals)*0.01,
                    f'{total:.1f} MB',
                    ha='center', va='bottom', fontweight='bold', fontsize=10, color='black')
    elif all(t == 0 for t in totals):
        # Special case when no loss occurred
        ax.text(0.5, 0.5, 'No Data Loss Detected\n(Excellent Buffer Management!)', 
                transform=ax.transAxes, ha='center', va='center',
                fontsize=16, fontweight='bold', color='green',
                bbox=dict(boxstyle="round,pad=0.3", facecolor='lightgreen', alpha=0.7))
    
    # Improve styling
    ax.grid(True, alpha=0.3, axis='y')
    ax.set_axisbelow(True)
    
    # Smart y-axis scaling
    if totals and max(totals) > 0:
        max_value = max(totals)
        ax.set_ylim(0, max_value * 1.15)
    else:
        ax.set_ylim(0, 1)  # Show a small range when no loss
    
    # Style the plot
    for label in ax.get_xticklabels():
        label.set_fontweight('bold')
        label.set_family('DejaVu Sans')
    
    for label in ax.get_yticklabels():
        label.set_family('DejaVu Sans')
    
    plt.tight_layout()
    
    # Save the plot
    output_path = output_dir / f"loss_bars_{strategy}_strategy.png"
    plt.savefig(output_path, dpi=300, bbox_inches='tight', facecolor='white')
    plt.close()
    
    print(f"  Generated loss bar chart for {strategy} -> {output_path.name}")
    
    # Print ranking for this strategy (lower loss is better)
    if any(totals):
        sorted_policies = sorted([(p, loss_results.get(p, 0)) for p in POLICIES], key=lambda x: x[1])
        ranking = " > ".join([policy.upper() for policy, total in sorted_policies if total >= 0])
        if ranking:
            print(f"  {strategy_display} strategy ranking (best to worst): {ranking}")
            total_strategy_loss = sum(totals)
            if total_strategy_loss > 0:
                print(f"  Total loss for {strategy}: {total_strategy_loss:.1f} MB")
            else:
                print(f"  {strategy_display}: No data loss detected!")
    else:
        print(f"  {strategy_display}: No data loss detected!")

def create_bar_charts():
    """Create bar charts for all strategies"""
    print("Multi-Satellite Data Loss Bar Chart Analysis")
    
    constellation_folder = find_latest_constellation_analysis_folder()
    if not constellation_folder:
        return
    
    config = read_config()
    
    # Create output directory
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir = SCRIPT_DIR / f"loss_bar_analysis_{timestamp}"
    output_dir.mkdir(exist_ok=True)
    
    print(f"Output directory: {output_dir.name}")
    
    # Process each strategy
    for strategy in SPACING_STRATEGIES:
        print(f"\nProcessing {strategy} strategy...")
        
        # Get loss data for this strategy
        loss_results = get_loss_data_for_strategy(strategy, constellation_folder)
        
        # Create bar chart for this strategy
        create_bar_chart_for_strategy(strategy, loss_results, config, output_dir)
    
    print(f"\nAll charts generated in: {output_dir}")
    print("Charts show total data loss per policy for each spacing strategy.")

def main():
    """Main function to run analysis"""
    create_bar_charts()

if __name__ == "__main__":
    main()
