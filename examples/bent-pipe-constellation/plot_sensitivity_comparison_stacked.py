#!/usr/bin/env python3
"""
Generate side-by-side comparison charts of orbit-spaced vs close-orbit-spaced (25-cluster)
showing stacked data downloaded by policy for sensitivity study satellite counts: 1, 25, 50, 100, 200

Left panel: Orbit-Spaced (1, 25, 50, 100, 200 satellites)
Right panel: Close-Orbit-Spaced 25-Cluster (1, 25, 50, 100, 200 satellites)

One chart per image size.
"""

import pandas as pd
import matplotlib.pyplot as plt
import numpy as np
from pathlib import Path
import re
import zipfile

# Directories to scan (in priority order)
ORBIT_SPACED_DIRS = [
    Path("results/orbit space best constellation size"),
    Path("results/base results")
]

CLOSE_ORBIT_SPACED_DIRS = [
    Path("results/close orbit space 25 clusters"),
    Path("results/base results")
]

# Satellite counts for sensitivity study
SAT_COUNTS = [1, 25, 50, 100, 200]

# Image sizes (in MB and their directory codes)
IMAGE_SIZES = {
    '00027': 0.027,
    '00279': 0.279,
    '02799': 2.799,
    '28000': 28.0,
    '280000': 280.0,
    '1024000': 1024.0
}

# Policies
POLICIES = ['sticky', 'fifo', 'roundrobin', 'random']

# Colors for policies (stacking)
POLICY_COLORS = {
    'sticky': '#FF6B6B',      # Red
    'fifo': '#4ECDC4',        # Teal
    'roundrobin': '#45B7D1',  # Blue
    'random': '#FFA07A'       # Orange
}

def extract_info_from_dirname(dirname):
    """Extract image size and constellation size from directory name."""
    # Format: constellation_analysis_YYYYMMDD_HHMMSS_IMAGESIZE_CONSTELSIZE
    parts = dirname.split('_')
    if len(parts) >= 6:
        image_size_code = parts[4]
        try:
            constel_size = int(parts[5])
            return image_size_code, constel_size
        except ValueError:
            return None, None
    return None, None

def find_analysis_dir(base_dirs, image_size_code, sat_count, spacing):
    """Find analysis directory for given configuration, checking multiple base directories."""
    for base_dir in base_dirs:
        if not base_dir.exists():
            continue
            
        # Try both formats: with leading zero (01, 02, etc.) and without (1, 25, etc.)
        patterns = [
            f"constellation_analysis_*_{image_size_code}_{sat_count:02d}",  # e.g., _01, _25
            f"constellation_analysis_*_{image_size_code}_{sat_count}"       # e.g., _1, _25
        ]
        
        for pattern in patterns:
            matching = list(base_dir.glob(pattern))
            
            if matching:
                analysis_dir = matching[0]
                # Check if the spacing strategy directory exists
                spacing_dir = analysis_dir / spacing
                if spacing_dir.exists():
                    return analysis_dir
    
    return None

def load_data_for_configuration(base_dirs, image_size_code, sat_count, spacing):
    """Load downloaded data for all policies for a given configuration."""
    analysis_dir = find_analysis_dir(base_dirs, image_size_code, sat_count, spacing)
    
    if not analysis_dir:
        return None
    
    spacing_dir = analysis_dir / spacing
    zip_path = spacing_dir / "simulation_logs.zip"
    results = {}
    
    # Read from zip file
    if zip_path.exists():
        try:
            with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                for policy in POLICIES:
                    vis_log_file = f"{policy}/visibility_log.csv"
                    
                    try:
                        with zip_ref.open(vis_log_file) as f:
                            df = pd.read_csv(f)
                            if 'downloaded_mb' in df.columns:
                                # Sum all downloaded data in MB
                                total_downloaded_mb = df['downloaded_mb'].sum()
                                results[policy] = total_downloaded_mb
                    except KeyError:
                        # File not in zip
                        pass
                    except Exception as e:
                        print(f"    ⚠️  Error reading {vis_log_file} from zip: {e}")
        except Exception as e:
            print(f"    ⚠️  Error opening zip file {zip_path}: {e}")
    
    return results if results else None

def create_comparison_chart(image_size_code, image_size_mb):
    """Create side-by-side comparison chart for one image size."""
    
    print(f"\n{'='*80}")
    print(f"Processing Image Size: {image_size_mb} MB (code: {image_size_code})")
    print(f"{'='*80}")
    
    # Collect data for both strategies
    orbit_spaced_data = {}
    close_orbit_spaced_data = {}
    
    for sat_count in SAT_COUNTS:
        print(f"\n  Satellite count: {sat_count}")
        
        # Orbit-spaced
        print(f"    Searching orbit-spaced...")
        orbit_data = load_data_for_configuration(
            ORBIT_SPACED_DIRS, 
            image_size_code, 
            sat_count, 
            'orbit-spaced'
        )
        if orbit_data:
            orbit_spaced_data[sat_count] = orbit_data
            total = sum(orbit_data.values())
            print(f"    ✅ Found orbit-spaced: {total:.2f} MB total")
        else:
            print(f"    ❌ No orbit-spaced data found")
        
        # Close-orbit-spaced
        print(f"    Searching close-orbit-spaced...")
        close_data = load_data_for_configuration(
            CLOSE_ORBIT_SPACED_DIRS,
            image_size_code,
            sat_count,
            'close-orbit-spaced'
        )
        if close_data:
            close_orbit_spaced_data[sat_count] = close_data
            total = sum(close_data.values())
            print(f"    ✅ Found close-orbit-spaced: {total:.2f} MB total")
        else:
            print(f"    ❌ No close-orbit-spaced data found")
    
    # Check if we have any data
    if not orbit_spaced_data and not close_orbit_spaced_data:
        print(f"\n  ⚠️  No data found for image size {image_size_mb} MB - skipping chart")
        return None
    
    # Create figure with two subplots (side by side)
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(16, 6))
    fig.suptitle(f'Data Downloaded Comparison - Image Size: {image_size_mb} MB', 
                 fontsize=16, fontweight='bold', y=0.98)
    
    # Common settings
    bar_width = 0.6
    x_positions = np.arange(len(SAT_COUNTS))
    x_labels = [str(sc) for sc in SAT_COUNTS]
    
    # Plot orbit-spaced (left panel)
    if orbit_spaced_data:
        bottoms = np.zeros(len(SAT_COUNTS))
        
        for policy in POLICIES:
            heights = []
            for sat_count in SAT_COUNTS:
                if sat_count in orbit_spaced_data and policy in orbit_spaced_data[sat_count]:
                    heights.append(orbit_spaced_data[sat_count][policy])
                else:
                    heights.append(0)
            
            ax1.bar(x_positions, heights, bar_width, bottom=bottoms,
                   label=policy.upper(), color=POLICY_COLORS[policy],
                   edgecolor='black', linewidth=0.5)
            bottoms += heights
        
        # Add total labels on top of bars
        for i, sat_count in enumerate(SAT_COUNTS):
            if sat_count in orbit_spaced_data:
                total = sum(orbit_spaced_data[sat_count].values())
                ax1.text(i, bottoms[i], f'{total:.1f}',
                        ha='center', va='bottom', fontsize=9, fontweight='bold')
    else:
        ax1.text(0.5, 0.5, 'No Data Available', 
                transform=ax1.transAxes, ha='center', va='center',
                fontsize=14, color='gray')
    
    ax1.set_xlabel('Number of Satellites', fontsize=12, fontweight='bold')
    ax1.set_ylabel('Total Data Downloaded (MB)', fontsize=12, fontweight='bold')
    ax1.set_title('Orbit-Spaced Strategy', fontsize=14, fontweight='bold', pad=10)
    ax1.set_xticks(x_positions)
    ax1.set_xticklabels(x_labels)
    ax1.grid(True, alpha=0.3, axis='y')
    ax1.legend(loc='upper left', framealpha=0.9)
    
    # Plot close-orbit-spaced (right panel)
    if close_orbit_spaced_data:
        bottoms = np.zeros(len(SAT_COUNTS))
        
        for policy in POLICIES:
            heights = []
            for sat_count in SAT_COUNTS:
                if sat_count in close_orbit_spaced_data and policy in close_orbit_spaced_data[sat_count]:
                    heights.append(close_orbit_spaced_data[sat_count][policy])
                else:
                    heights.append(0)
            
            ax2.bar(x_positions, heights, bar_width, bottom=bottoms,
                   label=policy.upper(), color=POLICY_COLORS[policy],
                   edgecolor='black', linewidth=0.5)
            bottoms += heights
        
        # Add total labels on top of bars
        for i, sat_count in enumerate(SAT_COUNTS):
            if sat_count in close_orbit_spaced_data:
                total = sum(close_orbit_spaced_data[sat_count].values())
                ax2.text(i, bottoms[i], f'{total:.1f}',
                        ha='center', va='bottom', fontsize=9, fontweight='bold')
        
        # Add cluster info below bars
        for i, sat_count in enumerate(SAT_COUNTS):
            if sat_count == 1:
                cluster_text = '1 sat'
            elif sat_count == 25:
                cluster_text = '25×1'
            elif sat_count == 50:
                cluster_text = '25×2\n6km'
            elif sat_count == 100:
                cluster_text = '25×4\n3km'
            elif sat_count == 200:
                cluster_text = '25×8\n1.5km'
            else:
                cluster_text = ''
            
            if cluster_text:
                ax2.text(i, -0.05, cluster_text,
                        transform=ax2.get_xaxis_transform(),
                        ha='center', va='top', fontsize=8, style='italic', color='gray')
    else:
        ax2.text(0.5, 0.5, 'No Data Available',
                transform=ax2.transAxes, ha='center', va='center',
                fontsize=14, color='gray')
    
    ax2.set_xlabel('Number of Satellites', fontsize=12, fontweight='bold')
    ax2.set_ylabel('Total Data Downloaded (MB)', fontsize=12, fontweight='bold')
    ax2.set_title('Close-Orbit-Spaced (25 Clusters)', fontsize=14, fontweight='bold', pad=10)
    ax2.set_xticks(x_positions)
    ax2.set_xticklabels(x_labels)
    ax2.grid(True, alpha=0.3, axis='y')
    ax2.legend(loc='upper left', framealpha=0.9)
    
    # Match y-axis scales
    if orbit_spaced_data or close_orbit_spaced_data:
        max_y = max(
            max([sum(orbit_spaced_data.get(sc, {}).values()) for sc in SAT_COUNTS] + [0]),
            max([sum(close_orbit_spaced_data.get(sc, {}).values()) for sc in SAT_COUNTS] + [0])
        )
        ax1.set_ylim(0, max_y * 1.15)
        ax2.set_ylim(0, max_y * 1.15)
    
    plt.tight_layout()
    
    # Save figure
    output_dir = Path("sensitivity_comparison_charts")
    output_dir.mkdir(exist_ok=True)
    
    output_file = output_dir / f"comparison_stacked_{image_size_code}mb.png"
    plt.savefig(output_file, dpi=150, bbox_inches='tight')
    print(f"\n  ✅ Saved: {output_file}")
    plt.close()
    
    return output_file

def main():
    """Generate all comparison charts."""
    print("="*80)
    print("SENSITIVITY STUDY COMPARISON - ORBIT-SPACED VS CLOSE-ORBIT-SPACED")
    print("="*80)
    print(f"\nSatellite counts: {SAT_COUNTS}")
    print(f"Policies: {POLICIES}")
    print(f"\nOrbit-spaced search paths:")
    for dir_path in ORBIT_SPACED_DIRS:
        print(f"  - {dir_path}")
    print(f"\nClose-orbit-spaced search paths:")
    for dir_path in CLOSE_ORBIT_SPACED_DIRS:
        print(f"  - {dir_path}")
    
    generated_charts = []
    
    # Generate chart for each image size
    for image_size_code, image_size_mb in IMAGE_SIZES.items():
        output_file = create_comparison_chart(image_size_code, image_size_mb)
        if output_file:
            generated_charts.append(output_file)
    
    # Summary
    print(f"\n{'='*80}")
    print("GENERATION COMPLETE")
    print(f"{'='*80}")
    print(f"Generated {len(generated_charts)} charts:")
    for chart in generated_charts:
        print(f"  ✅ {chart}")
    print(f"\nOutput directory: sensitivity_comparison_charts/")
    print(f"{'='*80}")

if __name__ == "__main__":
    main()
