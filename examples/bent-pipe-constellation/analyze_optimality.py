#!/usr/bin/env python3
"""
Analyze the optimality of satellite scheduling policies.

For each timestep, determines:
1. Which satellite had the best bitrate among all in-view satellites
2. Whether the policy actually connected to that best satellite (connected=1)
3. Calculate optimality percentage: (optimal_connections / total_connections) * 100

This shows how well each policy performs compared to the theoretical optimum.
"""

import sys
import os
import zipfile
import pandas as pd
import numpy as np
from pathlib import Path
import shutil
import tempfile

def analyze_optimality(log_zip_path, policy):
    """
    Analyze a single simulation's optimality for a specific policy.
    
    Returns: dict with optimality metrics
    """
    # Create temporary directory for extraction
    temp_dir = tempfile.mkdtemp()
    
    try:
        # Extract only the visibility_log.csv for the specific policy
        with zipfile.ZipFile(log_zip_path, 'r') as zip_ref:
            visibility_file = f"{policy}/visibility_log.csv"
            try:
                zip_ref.extract(visibility_file, temp_dir)
            except KeyError:
                print(f"❌ No visibility_log.csv found for policy '{policy}' in {log_zip_path}")
                return None
        
        log_file = Path(temp_dir) / visibility_file
        
        # Read the log file
        df = pd.read_csv(log_file)
        
        # CRITICAL: Reconstruct pre-download buffer state
        # buffer_mb is POST-download, downloaded_mb is what was downloaded THIS timestep
        # Pre-download buffer = buffer_mb + downloaded_mb
        df['pre_download_buffer_mb'] = df['buffer_mb'] + df['downloaded_mb']
        
        # Group by timestep (time column)
        results = []
        for timestep, group in df.groupby('time'):
            # FILTER 1: Skip timesteps where any satellite took an image (image_taken=1)
            # These are image capture timesteps, not downlink timesteps
            if (group['image_taken'] == 1).any():
                continue
            
            # FILTER 2: Check if any satellite is connected (connected=1)
            # If no connection, this is an idle timestep - skip it
            connected = group[group['connected'] == 1]
            if len(connected) == 0:
                continue  # Idle timestep - no connection made
            
            # Find satellites with in_view=1 AND pre-download buffer > 0 (satellites with data)
            # This is the CORRECT set to evaluate optimality against
            inview_with_data = group[(group['in_view'] == 1) & (group['pre_download_buffer_mb'] > 0)]
            
            if len(inview_with_data) == 0:
                continue  # No satellites with data available (shouldn't happen if connected exists)
            
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
            best_capacity_mb = best_sat_data['bitrate_mbps'] / 8.0  # MB per second
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
        
        # Calculate optimality metrics
        if not results:
            return None
        
        results_df = pd.DataFrame(results)
        
        # All results now have connections (we filtered out idle timesteps)
        total_connections = len(results_df)
        optimal_count = results_df['optimal'].sum()
        optimality_pct = (optimal_count / total_connections) * 100
        
        # Calculate bitrate efficiency (actual vs best possible)
        avg_connected_bitrate = results_df['connected_bitrate'].mean()
        avg_best_bitrate = results_df['best_bitrate'].mean()
        bitrate_efficiency_pct = (avg_connected_bitrate / avg_best_bitrate) * 100 if avg_best_bitrate > 0 else 0
        
        # Calculate data efficiency (actual data downloaded vs optimal)
        total_data_downloaded_mb = results_df['connected_downloaded_mb'].sum()
        total_optimal_data_mb = results_df['best_would_download_mb'].sum()
        data_efficiency_pct = (total_data_downloaded_mb / total_optimal_data_mb * 100) if total_optimal_data_mb > 0 else 0
        
        return {
            'policy': policy,
            'active_downlink_timesteps': total_connections,
            'optimal_connections': optimal_count,
            'suboptimal_connections': total_connections - optimal_count,
            'optimality_pct': optimality_pct,
            'avg_connected_bitrate_Mbps': avg_connected_bitrate,
            'avg_best_available_bitrate_Mbps': avg_best_bitrate,
            'bitrate_efficiency_pct': bitrate_efficiency_pct,
            'total_data_downloaded_mb': total_data_downloaded_mb,
            'total_optimal_data_mb': total_optimal_data_mb,
            'data_efficiency_pct': data_efficiency_pct
        }
    
    finally:
        # Cleanup: remove temporary directory and all extracted files
        shutil.rmtree(temp_dir, ignore_errors=True)

def analyze_results_directory(results_dir, policy_filter=None, spacing_filter=None, sat_count_filter=None):
    """
    Analyze all simulations in a results directory.
    """
    results_path = Path(results_dir)
    
    if not results_path.exists():
        print(f"❌ Results directory not found: {results_dir}")
        return
    
    print(f"🔍 Analyzing optimality in: {results_dir}")
    print()
    
    # Define all policies to analyze
    all_policies = ["sticky", "fifo", "roundrobin", "random", "mindistance", "maxdownload"]
    policies_to_analyze = [policy_filter] if policy_filter else all_policies
    
    all_results = []
    
    # Find all simulation_logs.zip files
    zip_files = list(results_path.glob('**/simulation_logs.zip'))
    
    if not zip_files:
        print("❌ No simulation_logs.zip files found")
        return
    
    print(f"Found {len(zip_files)} simulation log files")
    print(f"Analyzing policies: {', '.join(policies_to_analyze)}")
    print()
    
    for zip_file in sorted(zip_files):
        # Parse directory structure to extract metadata
        # Format: constellation_analysis_TIMESTAMP_IMAGESIZE_SATCOUNT/SPACING/simulation_logs.zip
        parts = zip_file.parts
        spacing = parts[-2]
        constellation_dir = parts[-3]
        
        # Extract image size and sat count from directory name
        dir_parts = constellation_dir.split('_')
        if len(dir_parts) >= 5:
            image_size = dir_parts[-2]
            sat_count = dir_parts[-1]
        else:
            continue
        
        # Apply filters
        if spacing_filter and spacing != spacing_filter:
            continue
        if sat_count_filter and sat_count != str(sat_count_filter).zfill(2):
            continue
        
        print(f"📊 Analyzing: {sat_count} sats, {spacing}, {image_size}KB...")
        
        # Analyze each policy in this configuration
        for policy in policies_to_analyze:
            metrics = analyze_optimality(zip_file, policy)
            
            if metrics:
                metrics['sat_count'] = int(sat_count)
                metrics['spacing'] = spacing
                metrics['image_size_KB'] = int(image_size)
                metrics['log_file'] = str(zip_file)
                all_results.append(metrics)
                
                print(f"   {policy:12s}: {metrics['optimality_pct']:5.1f}% optimal ({metrics['optimal_connections']}/{metrics['active_downlink_timesteps']}), "
                      f"bitrate eff: {metrics['bitrate_efficiency_pct']:5.1f}%, data eff: {metrics['data_efficiency_pct']:5.1f}%")
            else:
                print(f"   {policy:12s}: ⚠️  No data")
        print()
    
    if not all_results:
        print("❌ No results to analyze")
        return
    
    # Create summary DataFrame
    summary_df = pd.DataFrame(all_results)
    
    # Group by configuration and show summary
    print()
    print("=" * 120)
    print("OPTIMALITY SUMMARY BY POLICY AND CONFIGURATION")
    print("=" * 120)
    print()
    
    for policy in sorted(summary_df['policy'].unique()):
        policy_data = summary_df[summary_df['policy'] == policy]
        print(f"📡 Policy: {policy.upper()}")
        print(f"   Overall Optimality: {policy_data['optimality_pct'].mean():5.1f}% (avg across all configs)")
        print(f"   Bitrate Efficiency: {policy_data['bitrate_efficiency_pct'].mean():5.1f}%")
        print()
        
        for sat_count in sorted(policy_data['sat_count'].unique()):
            sat_data = policy_data[policy_data['sat_count'] == sat_count]
            print(f"      {sat_count} Satellites:")
            for spacing in sorted(sat_data['spacing'].unique()):
                spacing_data = sat_data[sat_data['spacing'] == spacing]
                avg_optimality = spacing_data['optimality_pct'].mean()
                avg_bitrate_eff = spacing_data['bitrate_efficiency_pct'].mean()
                print(f"         {spacing:20s}: {avg_optimality:5.1f}% optimal, {avg_bitrate_eff:5.1f}% bitrate efficiency")
        print()
    
    return summary_df

if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("Usage: python analyze_optimality.py <results_directory> [policy] [spacing] [sat_count]")
        print()
        print("Examples:")
        print("  python analyze_optimality.py results/maxdownload_20251124_195052")
        print("  python analyze_optimality.py results/maxdownload_20251124_195052 maxdownload")
        print("  python analyze_optimality.py results/maxdownload_20251124_195052 maxdownload orbit-spaced")
        print("  python analyze_optimality.py results/maxdownload_20251124_195052 maxdownload orbit-spaced 50")
        print()
        print("Valid policies: sticky, fifo, roundrobin, random, mindistance, maxdownload")
        sys.exit(1)
    
    results_dir = sys.argv[1]
    policy_filter = sys.argv[2] if len(sys.argv) > 2 else None
    spacing_filter = sys.argv[3] if len(sys.argv) > 3 else None
    sat_count_filter = sys.argv[4] if len(sys.argv) > 4 else None
    
    summary = analyze_results_directory(results_dir, policy_filter=policy_filter, 
                                       spacing_filter=spacing_filter, sat_count_filter=sat_count_filter)
    
    if summary is not None:
        # Save summary to CSV
        output_file = Path(results_dir) / 'optimality_summary.csv'
        summary.to_csv(output_file, index=False)
        print(f"💾 Saved summary to: {output_file}")
