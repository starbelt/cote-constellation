#!/usr/bin/env python3
"""
Cross-Spacing Comparison Analysis

Generates comparison charts analyzing policy performance across different spacing strategies.
Creates summary visualizations for the multi-spacing research matrix using REAL data.
"""

import pandas as pd
import matplotlib.pyplot as plt
import numpy as np
import argparse
import json
import glob
import zipfile
import os
from pathlib import Path
from datetime import datetime

def extract_metrics_from_logs(spacing_dir):
    """Extract real metrics from simulation logs"""
    logs_zip = spacing_dir / "simulation_logs.zip"
    if not logs_zip.exists():
        return None
    
    metrics = {}
    policies = ['sticky', 'fifo', 'roundrobin', 'random']
    
    # Extract zip temporarily
    temp_dir = spacing_dir / "temp_logs"
    temp_dir.mkdir(exist_ok=True)
    
    with zipfile.ZipFile(logs_zip, 'r') as zip_ref:
        zip_ref.extractall(temp_dir)
    
    for policy in policies:
        policy_dir = temp_dir / policy
        if not policy_dir.exists():
            continue
            
        # Count total trigger events
        trigger_file = policy_dir / "evnt-trigger-time.csv"
        total_triggers = 0
        if trigger_file.exists():
            with open(trigger_file, 'r') as f:
                total_triggers = len(f.readlines()) - 1  # Subtract header
        
        # Calculate total data RETRIEVED FROM SATELLITE using buffer drain analysis
        total_downloaded_mb = 0
        
        # Look for individual satellite buffer files
        buffer_files = [f for f in os.listdir(policy_dir) if f.startswith('meas-MB-buffered-sat-') and f.endswith('.csv')]
        
        if buffer_files:
            try:
                # Process satellite buffer files efficiently
                processed_count = 0
                for buffer_file in buffer_files:
                    buffer_path = policy_dir / buffer_file
                    if buffer_path.exists():
                        try:
                            buffer_df = pd.read_csv(buffer_path)
                            if len(buffer_df.columns) >= 2:
                                # Get buffer values
                                buffer_values = pd.to_numeric(buffer_df.iloc[:, 1], errors='coerce').dropna()
                                
                                # Find significant buffer drops (data leaving satellite)
                                for i in range(1, len(buffer_values)):
                                    drop = buffer_values.iloc[i-1] - buffer_values.iloc[i]
                                    if drop > 1.0:  # Count meaningful drops > 1MB
                                        total_downloaded_mb += drop
                                
                                processed_count += 1
                        except Exception as e:
                            continue  # Skip problematic files
                        
            except Exception as e:
                total_downloaded_mb = 0
        
        metrics[policy] = {
            'total_triggers': total_triggers,
            'total_downloaded_mb': total_downloaded_mb,
            'buffer_files_found': len(buffer_files) if buffer_files else 0
        }
    
    # Clean up temp directory
    import shutil
    shutil.rmtree(temp_dir)
    
    return metrics

def generate_spacing_strategy_comparison(master_dir, output_dir):
    """Generate 2x2 grid: each quadrant shows one policy with 4 spacing strategy bars"""
    
    spacings = ['bent-pipe', 'close-spaced', 'frame-spaced', 'orbit-spaced']
    policies = ['sticky', 'fifo', 'roundrobin', 'random']
    spacing_labels = ['Bent\nPipe', 'Close\nSpaced', 'Frame\nSpaced', 'Orbit\nSpaced']
    
    # Extract real data from all spacing strategies
    all_data = {}
    for spacing in spacings:
        spacing_dir = master_dir / spacing
        if spacing_dir.exists():
            metrics = extract_metrics_from_logs(spacing_dir)
            if metrics:
                all_data[spacing] = metrics
    
    if not all_data:
        return None
    
    # Create 2x2 subplot grid
    fig, ((ax1, ax2), (ax3, ax4)) = plt.subplots(2, 2, figsize=(16, 12))
    axes = [ax1, ax2, ax3, ax4]
    colors = ['#e74c3c', '#f39c12', '#27ae60', '#3498db']  # Red, Orange, Green, Blue
    
    for i, policy in enumerate(policies):
        ax = axes[i]
        
        # Extract total downloaded data for this policy across all spacing strategies
        data_values = []
        for spacing in spacings:
            if spacing in all_data and policy in all_data[spacing]:
                data_values.append(all_data[spacing][policy]['total_downloaded_mb'])
            else:
                data_values.append(0)
        
        # Create bar chart
        bars = ax.bar(spacing_labels, data_values, color=colors, alpha=0.8, 
                      edgecolor='black', linewidth=1)
        
        # Add value labels on bars
        for bar, value in zip(bars, data_values):
            height = bar.get_height()
            ax.text(bar.get_x() + bar.get_width()/2., height + max(data_values) * 0.01,
                   f'{value:.0f} MB', ha='center', va='bottom', fontweight='bold', fontsize=10)
        
        # Customize subplot
        ax.set_title(f'{policy.upper()} Policy\nData Retrieved by Spacing Strategy', 
                    fontsize=12, fontweight='bold', pad=15)
        ax.set_ylabel('Data Retrieved (MB)', fontsize=10, fontweight='bold')
        ax.set_ylim(0, max(data_values) * 1.15 if data_values else 100)
        ax.grid(True, alpha=0.3, axis='y')
        ax.tick_params(axis='x', rotation=0)
    
    plt.suptitle('Spacing Strategy Performance Comparison\n' +
                'Data Retrieved: Higher Values = More Data Downloaded', 
                fontsize=16, fontweight='bold', y=0.98)
    plt.tight_layout()
    
    # Save chart
    output_path = output_dir / "spacing_strategy_comparison.png"
    plt.savefig(output_path, dpi=300, bbox_inches='tight')
    plt.close()
    
    return output_path

def generate_policy_performance_matrix(master_dir, output_dir):
    """Generate heatmap matrix: rows=policies, cols=spacing strategies"""
    
    spacings = ['bent-pipe', 'close-spaced', 'frame-spaced', 'orbit-spaced']
    policies = ['sticky', 'fifo', 'roundrobin', 'random']
    spacing_labels = ['Bent Pipe', 'Close Spaced', 'Frame Spaced', 'Orbit Spaced']
    policy_labels = ['STICKY', 'FIFO', 'ROUNDROBIN', 'RANDOM']
    
    # Extract real data from all spacing strategies
    all_data = {}
    for spacing in spacings:
        spacing_dir = master_dir / spacing
        if spacing_dir.exists():
            metrics = extract_metrics_from_logs(spacing_dir)
            if metrics:
                all_data[spacing] = metrics
    
    if not all_data:
        return None
    
    # Create performance matrix (policies x spacings)
    performance_matrix = np.zeros((len(policies), len(spacings)))
    
    for i, policy in enumerate(policies):
        for j, spacing in enumerate(spacings):
            if spacing in all_data and policy in all_data[spacing]:
                performance_matrix[i, j] = all_data[spacing][policy]['total_downloaded_mb']
    
    # Create heatmap
    fig, ax = plt.subplots(figsize=(14, 10))
    
    # Use Blues colormap (darker = more data downloaded)
    max_value = np.max(performance_matrix) if np.max(performance_matrix) > 0 else 1000
    im = ax.imshow(performance_matrix, cmap='Blues', aspect='auto', vmin=0, vmax=max_value)
    
    # Set ticks and labels
    ax.set_xticks(np.arange(len(spacings)))
    ax.set_yticks(np.arange(len(policies)))
    ax.set_xticklabels(spacing_labels, fontsize=12, fontweight='bold')
    ax.set_yticklabels(policy_labels, fontsize=12, fontweight='bold')
    
    # Add colorbar
    cbar = plt.colorbar(im, ax=ax, shrink=0.8)
    cbar.set_label('Data Retrieved (MB)', rotation=270, labelpad=20, 
                   fontsize=12, fontweight='bold')
    cbar.ax.tick_params(labelsize=10)
    
    # Add text annotations with real values
    for i in range(len(policies)):
        for j in range(len(spacings)):
            value = performance_matrix[i, j]
            # Use white text on dark areas, black on light areas
            color = 'white' if value > (max_value * 0.6) else 'black'
            text = ax.text(j, i, f'{value:.0f} MB', ha="center", va="center", 
                         color=color, fontweight='bold', fontsize=11)
    
    # Titles and labels
    ax.set_title('Policy-Spacing Performance Matrix\n' +
                'Data Retrieved: Higher Values = More Data Downloaded', 
                fontsize=16, fontweight='bold', pad=25)
    ax.set_xlabel('Spacing Strategy', fontsize=14, fontweight='bold')
    ax.set_ylabel('Scheduling Policy', fontsize=14, fontweight='bold')
    
    # Add grid for better readability
    ax.set_xticks(np.arange(len(spacings)+1)-.5, minor=True)
    ax.set_yticks(np.arange(len(policies)+1)-.5, minor=True)
    ax.grid(which="minor", color="black", linestyle='-', linewidth=2)
    ax.tick_params(which="minor", size=0)
    
    plt.tight_layout()
    
    # Save chart
    output_path = output_dir / "policy_spacing_performance_matrix.png"
    plt.savefig(output_path, dpi=300, bbox_inches='tight')
    plt.close()
    
    return output_path

def main():
    parser = argparse.ArgumentParser(description='Cross-Spacing Comparison Analysis')
    parser.add_argument('--input-dir', required=True, help='Master analysis directory containing spacing subdirectories')
    args = parser.parse_args()
    
    master_dir = Path(args.input_dir)
    if not master_dir.exists():
        return 1
    
    # Generate comparison charts with REAL data
    matrix_chart = generate_policy_performance_matrix(master_dir, master_dir)
    comparison_chart = generate_spacing_strategy_comparison(master_dir, master_dir)
    
    return 0

if __name__ == "__main__":
    exit(main())
