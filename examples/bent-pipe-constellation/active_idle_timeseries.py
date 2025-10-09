#!/usr/bin/env python3
"""
Optimized Matrix Charts - 4 Separate Strategy Charts from Archives
Creates 4 separate PNG files (one per strategy) with optimized data processing.
"""

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from pathlib import Path
from datetime import datetime
import seaborn as sns
import zipfile
import tempfile
import shutil
import glob
import argparse
import sys

# Configuration
SCRIPT_DIR = Path(__file__).parent.absolute()
SPACING_STRATEGIES = ["close-spaced", "close-orbit-spaced", "frame-spaced", "orbit-spaced"]
POLICIES = ["sticky", "fifo", "roundrobin", "random"]

# Image size mappings
IMAGE_SIZE_MAP = {
    's': 0.027,   # Small images (corrected from 0.028)
    'm': 0.279,   # Medium images (corrected from 0.28)
    'l': 2.799,   # Large images (corrected from 2.8)
    'xl': 28.0    # Extra large images
}

def parse_image_sizes(image_str):
    """Parse comma-separated image size abbreviations to MB values"""
    if not image_str:
        return list(IMAGE_SIZE_MAP.values())  # Return all if none specified
    
    sizes = []
    for size_abbrev in image_str.split(','):
        size_abbrev = size_abbrev.strip().lower()
        if size_abbrev in IMAGE_SIZE_MAP:
            sizes.append(IMAGE_SIZE_MAP[size_abbrev])
        else:
            valid_sizes = ', '.join(IMAGE_SIZE_MAP.keys())
            raise ValueError(f"Invalid image size '{size_abbrev}'. Valid options: {valid_sizes}")
    
    return sizes

def parse_satellite_counts(sats_str):
    """Parse comma-separated satellite counts"""
    if not sats_str:
        return [1, 50, 100, 200]  # Return all if none specified
    
    try:
        counts = [int(count.strip()) for count in sats_str.split(',')]
        return counts
    except ValueError as e:
        raise ValueError(f"Invalid satellite count: {e}")

def find_matching_folders(base_dir, image_sizes=None, satellite_counts=None):
    """Find constellation analysis folders matching the specified parameters"""
    if image_sizes is None:
        image_sizes = list(IMAGE_SIZE_MAP.values())
    if satellite_counts is None:
        satellite_counts = [1, 50, 100, 200]
    
    # Convert image sizes to the format used in folder names (5 digits with leading zeros)
    size_patterns = []
    for size in image_sizes:
        if size < 1:
            # For small sizes like 0.027, convert to 00027 format
            size_int = int(size * 1000)
            size_patterns.append(f"{size_int:05d}")
        else:
            # For larger sizes like 28.0, convert to 28000 format
            size_int = int(size * 1000)
            size_patterns.append(f"{size_int:05d}")
    
    # Convert satellite counts to match the folder format (no leading zeros for larger numbers)
    sat_patterns = []
    for count in satellite_counts:
        if count < 10:
            sat_patterns.append(f"{count:02d}")  # "01", "02", etc.
        else:
            sat_patterns.append(str(count))      # "50", "100", "200"
    
    matching_folders = []
    
    # Look for folders with pattern: constellation_analysis_YYYYMMDD_HHMMSS_IMAGESIZE_SATCOUNT
    all_folders = [d for d in base_dir.iterdir() 
                   if d.is_dir() and d.name.startswith('constellation_analysis_')]
    
    for folder in all_folders:
        parts = folder.name.split('_')
        if len(parts) >= 6:  # constellation_analysis_DATE_TIME_SIZE_SATS
            try:
                # Extract image size and satellite count from folder name
                size_part = parts[4]  # Should be like "00027" or "28000"
                sat_part = parts[5]   # Should be like "01" or "200"
                
                # Check if this folder matches our criteria
                if size_part in size_patterns and sat_part in sat_patterns:
                    matching_folders.append(folder)
            except (ValueError, IndexError):
                # Skip folders that don't follow the expected naming convention
                continue
    
    return sorted(matching_folders, key=lambda x: x.name)

def extract_constellation_data(folder_path=None, image_sizes=None, satellite_counts=None):
    """Extract data from constellation_analysis folders with filtering"""
    
    if folder_path:
        # User specified a folder
        folder = Path(folder_path)
        
        # Handle relative paths from current directory
        if not folder.is_absolute():
            folder = SCRIPT_DIR / folder
        
        # Validate folder exists and follows naming convention
        if not folder.exists():
            print(f"❌ Error: Specified folder '{folder_path}' does not exist!")
            return None
        
        if not folder.is_dir():
            print(f"❌ Error: '{folder_path}' is not a directory!")
            return None
        
        if not folder.name.startswith('constellation_analysis_'):
            print(f"⚠️  Warning: Folder '{folder.name}' does not follow expected naming convention (constellation_analysis_YYYYMMDD_HHMMSS)")
        
        print(f"📁 Using specified constellation analysis folder: {folder.name}")
        return [folder]  # Return as list for consistency
    else:
        # Find matching folders based on image sizes and satellite counts
        matching_folders = find_matching_folders(SCRIPT_DIR, image_sizes, satellite_counts)
        
        if not matching_folders:
            size_str = ", ".join([f"{s:.3f}MB" for s in image_sizes]) if image_sizes else "all"
            sats_str = ", ".join([str(s) for s in satellite_counts]) if satellite_counts else "all"
            print(f"❌ No constellation_analysis folders found matching:")
            print(f"   Image sizes: {size_str}")
            print(f"   Satellite counts: {sats_str}")
            return None
        
        print(f"📁 Found {len(matching_folders)} matching constellation analysis folders:")
        for folder in matching_folders:
            parts = folder.name.split('_')
            if len(parts) >= 6:
                size_part = parts[4]
                sat_part = parts[5]
                
                # Convert size part back to readable format
                try:
                    size_val = int(size_part) / 1000.0
                    if size_val < 1:
                        size_display = f"{size_val:.3f}MB"
                    else:
                        size_display = f"{size_val:.1f}MB"
                    
                    sat_display = f"{int(sat_part)} satellites"
                    print(f"   - {folder.name} (Image: {size_display}, Sats: {sat_display})")
                except ValueError:
                    print(f"   - {folder.name}")
            else:
                print(f"   - {folder.name}")
        
        return matching_folders

def extract_archive_data(strategy, archive_base_path):
    """Extract simulation data from zip archive for the given strategy."""
    archive_path = archive_base_path / strategy / 'simulation_logs.zip'
    
    if not archive_path.exists():
        print(f"  Warning: Archive not found: {archive_path}")
        return None
    
    temp_dir = Path(tempfile.mkdtemp(prefix=f'{strategy}_extract_'))
    
    try:
        with zipfile.ZipFile(archive_path, 'r') as zip_ref:
            zip_ref.extractall(temp_dir)
        return temp_dir
    except Exception as e:
        print(f"  Error extracting {archive_path}: {e}")
        if temp_dir.exists():
            shutil.rmtree(temp_dir)
        return None

def parse_communication_data_optimized(strategy, policy, temp_dir):
    """Optimized parsing with sampling for faster processing and proper buffer states."""
    policy_dir = temp_dir / policy
    tx_rx_file = policy_dir / "meas-downlink-tx-rx.csv"
    
    if not tx_rx_file.exists():
        print(f"    Warning: No tx-rx file found for {strategy}_{policy}")
        return None, None
        
    # Read with sampling for speed (every 10th row for large files)
    print(f"    Processing {strategy}_{policy}...")
    
    # First, get file size to decide sampling
    file_size = tx_rx_file.stat().st_size
    if file_size > 10_000_000:  # If file > 10MB, sample every 10th row
        sample_rows = list(range(0, 100000, 10))  # Sample first 10k rows, every 10th
        df = pd.read_csv(tx_rx_file, skiprows=lambda x: x not in sample_rows and x != 0)
    else:
        df = pd.read_csv(tx_rx_file)
    
    # Handle the empty third column
    if len(df.columns) == 3:
        df = df.iloc[:, :2]
    
    if len(df) <= 1:
        print(f"    Warning: Empty data file for {strategy}_{policy}")
        return None, None
        
    df.columns = ['timestamp', 'satellite']
    df['timestamp'] = pd.to_datetime(df['timestamp'])
    
    # Convert to relative time (hours from start)
    start_time = df['timestamp'].min()
    df['hours'] = (df['timestamp'] - start_time).dt.total_seconds() / 3600
    
    # Ground station state
    df['ground_station_active'] = df['satellite'].apply(lambda x: 0 if pd.isna(x) or x == 'None' else 1)
    
    # Find most active satellites (show ALL satellites, not just top 5)
    active_data = df[df['satellite'] != 'None']
    if len(active_data) == 0:
        return df[['hours', 'ground_station_active']], {}
        
    satellite_counts = active_data['satellite'].value_counts()
    all_sats = satellite_counts.index.tolist()  # Get ALL satellites instead of limiting
    
    # Read buffer files to get buffer state (with sampling)
    buffer_files = list(policy_dir.glob("meas-MB-buffered-sat-*.csv"))
    buffer_data = {}
    
    for buffer_file in buffer_files:
        # Extract satellite ID from filename: meas-MB-buffered-sat-0060518000.csv
        sat_id_match = buffer_file.stem.split('-')[-1]  # Gets "0060518000"
        if len(sat_id_match) >= 10:
            # Convert to expected format: 60518000-0
            sat_base = sat_id_match[-8:]  # Last 8 digits
            sat_id = f"{sat_base}-0"
            
            if sat_id in all_sats:
                try:
                    # Sample buffer file too for performance
                    buffer_file_size = buffer_file.stat().st_size
                    if buffer_file_size > 10_000_000:  # Sample large buffer files
                        df_buffer = pd.read_csv(buffer_file, skiprows=lambda x: x not in sample_rows and x != 0)
                    else:
                        df_buffer = pd.read_csv(buffer_file)
                        
                    if len(df_buffer.columns) >= 2:
                        df_buffer.columns = ['timestamp', 'buffer_mb'] + list(df_buffer.columns[2:])
                        df_buffer['timestamp'] = pd.to_datetime(df_buffer['timestamp'])
                        df_buffer['hours'] = (df_buffer['timestamp'] - start_time).dt.total_seconds() / 3600
                        buffer_data[sat_id] = df_buffer[['hours', 'buffer_mb']]
                except Exception:
                    # Skip buffer file if it can't be read
                    pass
    
    # Create satellite data with proper connection and buffer states
    satellite_data = {}
    for sat in all_sats:
        # Create connection state: 1 when this satellite is connected, 0 otherwise
        sat_connected = df['satellite'].apply(lambda x: 1 if x == sat else 0)
        
        # Create base data structure
        sat_data = df[['hours']].copy()
        sat_data[f'sat_{sat}_connected'] = sat_connected
        
        # Add buffer information if available
        if sat in buffer_data:
            # Merge buffer data with nearest time matching
            sat_data = pd.merge_asof(
                sat_data.sort_values('hours'),
                buffer_data[sat].sort_values('hours'),
                on='hours', direction='nearest'
            )
            sat_data['buffer_mb'] = sat_data['buffer_mb'].fillna(0)
            
            # Create proper buffer-aware states
            sat_data[f'sat_{sat}_state'] = 0  # disconnected
            connected_mask = sat_data[f'sat_{sat}_connected'] > 0
            
            # For each connected period, check if satellite has buffer to drain
            actively_draining = np.zeros(len(sat_data), dtype=bool)
            
            for i in range(len(sat_data)):
                if connected_mask.iloc[i]:  # If connected at this timestep
                    # Check current buffer
                    current_buffer = sat_data['buffer_mb'].iloc[i]
                    
                    # Also check previous timestep buffer (satellite may connect with existing buffer)
                    prev_buffer = 0
                    if i > 0:
                        prev_buffer = sat_data['buffer_mb'].iloc[i-1]
                    
                    # Actively draining if: has current buffer OR had previous buffer (draining it now)
                    if current_buffer > 0.001 or prev_buffer > 0.001:  # Small threshold for floating point
                        actively_draining[i] = True
            
            # State 1: Connected AND actively draining (has buffer to transmit)
            sat_data.loc[connected_mask & actively_draining, f'sat_{sat}_state'] = 1
            
            # State 2: Connected BUT no buffer to drain (idle)
            sat_data.loc[connected_mask & ~actively_draining, f'sat_{sat}_state'] = 2
        else:
            # No buffer data available, just use connection state
            sat_data['buffer_mb'] = 0
            sat_data[f'sat_{sat}_state'] = sat_connected  # Just use connection state if no buffer data
        
        satellite_data[sat] = sat_data
    
    return df[['hours', 'ground_station_active']], satellite_data

def create_strategy_chart_optimized(strategy, output_dir, archive_base_path=None):
    """Create a single strategy chart with 4 policies (optimized)."""
    
    plt.style.use('default')
    sns.set_palette("husl")
    
    # Extract image size and satellite count from folder name for title
    folder_name = archive_base_path.name if archive_base_path else "unknown"
    image_size_str = "unknown"
    sat_count_str = "unknown"
    
    parts = folder_name.split('_')
    if len(parts) >= 6:
        try:
            # Convert from 5-digit format back to readable
            size_part = parts[4]  # e.g., "00027" or "28000"
            sat_part = parts[5]   # e.g., "01" or "200"
            
            image_size = int(size_part) / 1000.0  # Convert back to MB
            sat_count = int(sat_part)
            
            # Convert image size to readable format
            if image_size < 0.1:
                image_size_str = f"{image_size:.3f}MB"
            elif image_size < 1:
                image_size_str = f"{image_size:.2f}MB"
            else:
                image_size_str = f"{image_size:.1f}MB"
            
            sat_count_str = f"{sat_count} satellites"
        except (ValueError, IndexError):
            pass
    
    # Create 4 vertically stacked subplots - made even larger for better visibility
    fig, axes = plt.subplots(4, 1, figsize=(28, 22))  # Increased from (24, 18)
    fig.suptitle(f'{strategy.replace("-", " ").title()} Strategy - All Policies\n{image_size_str} | {sat_count_str}', 
                 fontsize=20, fontweight='bold')  # Larger title font
    
    # Enhanced color scheme with more distinct, high-contrast colors for satellites
    import matplotlib.colors as mcolors
    
    # Create a diverse set of colors using different color spaces
    base_colors = [
        '#FF0000', '#0000FF', '#00FF00', '#FF8000', '#8000FF',  # Bright primary colors
        '#FF0080', '#0080FF', '#80FF00', '#FF8080', '#8080FF',  # Mixed bright colors
        '#E74C3C', '#3498DB', '#2ECC71', '#F39C12', '#9B59B6',  # Material colors
        '#E67E22', '#8E44AD', '#1ABC9C', '#F1C40F', '#34495E',  # More material colors
        '#FF6B35', '#F7931E', '#FFD23F', '#06FFA5', '#4ECDC4',  # Vibrant set
        '#45B7D1', '#96CEB4', '#FFEAA7', '#DDA0DD', '#98D8C8',  # Pastel but visible
        '#FF7675', '#74B9FF', '#00B894', '#FDCB6E', '#6C5CE7',  # French palette
        '#FD79A8', '#00CEC9', '#55A3FF', '#FF9F43', '#A29BFE',  # More French
        '#FF3838', '#2E86AB', '#A23B72', '#F18F01', '#C73E1D',  # Bold colors
        '#8E2DE2', '#4A00E0', '#FF6B9D', '#C44569', '#F8B500',  # Gradient inspired
    ]
    
    colors = {
        'ground_station': '#2C3E50',
        'satellites': base_colors * 2  # Ensure we have enough colors for 50+ satellites
    }
    
    # Extract archive data once for this strategy - use provided path
    if archive_base_path is None:
        print(f"    Error: No archive base path provided for {strategy}")
        return None
    temp_dir = extract_archive_data(strategy, archive_base_path)
    if temp_dir is None:
        return None
    
    try:
        legend_added = False
        
        for policy_idx, policy in enumerate(POLICIES):
            ax = axes[policy_idx]
            
            # Parse communication data
            ground_data, satellite_data = parse_communication_data_optimized(strategy, policy, temp_dir)
            
            if ground_data is None or not satellite_data:
                ax.text(0.5, 0.5, f'No data for {strategy}/{policy}', 
                       transform=ax.transAxes, ha='center', va='center', fontsize=12, color='red')
                ax.set_title(f'{policy.upper()} Policy - No Communication Data', fontweight='bold')
                continue
            
            # Plot ground station activity
            ax.plot(ground_data['hours'], ground_data['ground_station_active'], 
                   color=colors['ground_station'], linewidth=3, label='Ground Station', 
                   alpha=0.9, drawstyle='steps-post')
            
            # Plot satellites with proper buffer state coloring (ALL satellites) - enhanced colors
            satellite_y = 1.5
            for j, (sat_id, sat_data) in enumerate(satellite_data.items()):
                # Get a unique color for this satellite
                sat_color = colors['satellites'][j % len(colors['satellites'])]
                
                state_col = f'sat_{sat_id}_state'
                if state_col in sat_data.columns:
                    # For connected with buffer (state 1) - Use satellite's unique color (actively draining)
                    active_mask = sat_data[state_col] == 1
                    if active_mask.any():
                        spike_line = sat_data[state_col].copy()
                        spike_line[spike_line != 1] = 0  # Only show spikes for state 1
                        spike_line = spike_line + satellite_y
                        ax.plot(sat_data['hours'], spike_line, 
                               color=sat_color, linewidth=2.5, alpha=0.9, drawstyle='steps-post',
                               label=f'Sat {sat_id[-1] if len(sat_id) > 10 else sat_id} (Draining)' if policy_idx == 0 else "")
                    
                    # For connected without buffer (state 2) - Use grey for idle/hogging state
                    idle_mask = sat_data[state_col] == 2
                    if idle_mask.any():
                        spike_line_grey = sat_data[state_col].copy()
                        spike_line_grey[spike_line_grey != 2] = 0  # Only show spikes for state 2
                        spike_line_grey[spike_line_grey == 2] = 1  # Convert state 2 to spike height 1
                        spike_line_grey = spike_line_grey + satellite_y
                        ax.plot(sat_data['hours'], spike_line_grey, 
                               color='#A0A0A0', linewidth=2.5, alpha=0.7, drawstyle='steps-post',
                               label=f'Sat {sat_id[-1] if len(sat_id) > 10 else sat_id} (Idle)' if policy_idx == 0 else "")
                else:
                    # Fallback: simple connection state with unique satellite color
                    connected_col = f'sat_{sat_id}_connected'
                    if connected_col in sat_data.columns:
                        spike_line = sat_data[connected_col] + satellite_y
                        ax.plot(sat_data['hours'], spike_line, 
                               color=sat_color, 
                               linewidth=2, alpha=0.8, drawstyle='steps-post',
                               label=f'Sat {sat_id[-1] if len(sat_id) > 10 else sat_id}' if policy_idx == 0 else "")
            
            # Formatting
            ax.set_ylabel(f'{policy.upper()}\nPolicy', fontweight='bold', fontsize=16)  # Larger font for bigger chart
            ax.set_title(f'{policy.upper()} Policy', fontweight='bold', fontsize=18)  # Larger font for bigger chart
            ax.grid(True, alpha=0.3)
            ax.set_ylim(-0.1, 2.8)
            
            # Add reference lines
            ax.axhline(y=0, color='gray', linestyle='--', alpha=0.3, linewidth=0.5)
            ax.axhline(y=1, color='gray', linestyle='--', alpha=0.3, linewidth=0.5)
            ax.axhline(y=satellite_y, color='gray', linestyle='--', alpha=0.3, linewidth=0.5)
            
            # Y-tick labels
            ax.set_yticks([0, 1, satellite_y, satellite_y + 1])
            ax.set_yticklabels(['GS Idle', 'GS Active', 'Sat Idle', 'Sat Active'], fontsize=14)  # Larger font for bigger chart
            
            # Shared legend vertically aligned in a single column
            if policy_idx == 0 and not legend_added and len(satellite_data) > 0:
                handles, labels = ax.get_legend_handles_labels()
                if len(handles) > 25:  # Many satellites - use smaller font
                    fig.legend(handles, labels, bbox_to_anchor=(0.98, 0.5), loc='center right', 
                              fontsize=8, ncol=1, frameon=True, fancybox=True, shadow=True)
                elif len(handles) > 15:  # Medium number
                    fig.legend(handles, labels, bbox_to_anchor=(0.98, 0.5), loc='center right', 
                              fontsize=9, ncol=1, frameon=True, fancybox=True, shadow=True)
                else:  # Few satellites - larger font
                    fig.legend(handles, labels, bbox_to_anchor=(0.98, 0.5), loc='center right', 
                              fontsize=10, ncol=1, frameon=True, fancybox=True, shadow=True)
                legend_added = True
            
            # X-axis label only on bottom - larger font for bigger chart
            if policy_idx == 3:
                ax.set_xlabel('Time (hours)', fontweight='bold', fontsize=16)
            else:
                ax.set_xlabel('')
        
        # Layout and save - adjusted for larger chart with vertically centered legend
        plt.tight_layout(pad=2.5)  # Increased padding for larger chart
        plt.subplots_adjust(right=0.82, hspace=0.4)  # More space for larger chart and legend
        
        # Generate filename with image size and satellite count
        parts = archive_base_path.name.split('_')
        if len(parts) >= 6:
            size_part = parts[4]  # e.g., "00027"
            sat_part = parts[5]   # e.g., "01"
            
            # Convert to readable format for filename
            try:
                size_val = int(size_part) / 1000.0
                sat_val = int(sat_part)
                size_str = f"{size_val:.3f}".replace('.', 'p')  # e.g., "0p027"
                output_file = output_dir / f"active_idle_timeseries_{strategy.replace('-', '_')}_strategy_{size_str}MB_{sat_val}sats.png"
            except ValueError:
                output_file = output_dir / f"active_idle_timeseries_{strategy.replace('-', '_')}_strategy.png"
        else:
            output_file = output_dir / f"active_idle_timeseries_{strategy.replace('-', '_')}_strategy.png"
        plt.savefig(output_file, dpi=300, bbox_inches='tight', facecolor='white')
        plt.close()
        
        print(f"✅ {strategy} strategy chart saved: {output_file}")
        return output_file
        
    finally:
        # Clean up temporary directory
        if temp_dir.exists():
            shutil.rmtree(temp_dir)

def main():
    """Generate 4 optimized strategy charts."""
    print("Generating optimized strategy charts from archived data...")
    print("Creating 4 PNG files (one per spacing strategy)...")
    print()
    
    # Parse command line arguments
    parser = argparse.ArgumentParser(description='Generate active/idle timeseries charts')
    parser.add_argument('folder', nargs='?', default=None, 
                       help='Constellation analysis folder to process (optional, defaults to matching folders)')
    parser.add_argument('--image', '--images', type=str, default=None,
                       help='Comma-separated image sizes: s,m,l,xl (s=0.028MB, m=0.28MB, l=2.8MB, xl=28MB)')
    parser.add_argument('--sats', '--satellites', type=str, default=None,
                       help='Comma-separated satellite counts: 1,50,100,200')
    args = parser.parse_args()
    
    # Parse image sizes and satellite counts
    try:
        image_sizes = parse_image_sizes(args.image)
        satellite_counts = parse_satellite_counts(args.sats)
    except ValueError as e:
        print(f"❌ Error: {e}")
        return
    
    # Use existing constellation analysis directories
    folders = extract_constellation_data(args.folder, image_sizes, satellite_counts)
    if not folders:
        return
    
    generated_files = []
    
    for folder in folders:
        print(f"\n📁 Processing folder: {folder.name}")
        
        for strategy in SPACING_STRATEGIES:
            print(f"  Processing {strategy} strategy...")
            output_file = create_strategy_chart_optimized(strategy, folder, folder)
            if output_file:
                generated_files.append(output_file)
        print()
    
    if generated_files:
        print(f"✅ Generated {len(generated_files)} strategy charts:")
        for file in generated_files:
            print(f"  - {file}")
    else:
        print("❌ No charts generated")
    
    return generated_files

if __name__ == "__main__":
    main()
