#!/usr/bin/env python3
"""
Multi-Satellite Data Loss Bar Chart Analysis

Shows total data lost per policy with clean bar chart visualization
ordered by performance (least loss first).
"""

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from pathlib import Path
from datetime import datetime
import zipfile

# Configuration - use absolute paths
SCRIPT_DIR = Path(__file__).parent.absolute()
LOGS_DIR = SCRIPT_DIR / "logs"
POLICIES = ["sticky", "fifo", "roundrobin", "random"]

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

def get_policy_dirs():
    """Get policy directories"""
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
        title_suffix = "No Data Loss Detected - Excellent Performance!"
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
    
    # Reset matplotlib settings to default
    plt.rcParams.update(plt.rcParamsDefault)
    
    if output_dir and output_dir.parent == SCRIPT_DIR:  # Only print if we created our own directory
        print(f"Generated satellite loss bar chart -> {output_dir}/satellite_loss_bars.png")
        if all_zero:
            print("Result: No data loss detected across all policies - excellent buffer management!")
        elif sorted_policies:
            print(f"Loss ranking (best to worst): {' < '.join([p.upper() for p in sorted_policies])}")
            print(f"Total loss across all policies: {total_loss:.1f} MB")
        print(f"For detailed buffer analysis, use the buffer plot script.")

def main():
    """Main function"""
    print("Multi-Satellite Data Loss Bar Chart Analysis")
    
    policy_dirs = get_policy_dirs()
    if not policy_dirs:
        print("No simulation logs found!")
        print("Please run simulations first using the scripts in the scripts/ directory.")
        return
    
    create_loss_bar_chart()  # Use default behavior when run standalone

if __name__ == "__main__":
    main()
