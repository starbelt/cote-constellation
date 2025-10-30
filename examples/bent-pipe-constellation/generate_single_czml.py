#!/usr/bin/env python3
"""
Generate a single CZML file for testing
"""
import pandas as pd
import json
from pathlib import Path
from datetime import datetime, timedelta
import sys
import zipfile
import shutil
import gzip

def generate_single_czml(size, analysis_dir, spacing, policy):
    """Generate CZML for a single configuration"""
    
    # Extract image size from analysis_dir (e.g., constellation_analysis_20251022_183657_00279_100)
    # Format: constellation_analysis_YYYYMMDD_HHMMSS_IMAGESIZE_CONSTELSIZE
    dir_parts = Path(analysis_dir).name.split('_')
    image_size = dir_parts[4] if len(dir_parts) >= 5 else "unknown"
    
    print(f"\n{'='*80}")
    print(f"Generating: {spacing}, {policy}, {size} satellites, {image_size} MB")
    print(f"Analysis dir: {analysis_dir}")
    print(f"{'='*80}\n")
    
    # Check if we need to unzip simulation_logs.zip
    spacing_dir = Path(analysis_dir) / spacing
    zip_file = spacing_dir / "simulation_logs.zip"
    policy_dir = spacing_dir / policy
    vis_log_path = policy_dir / "visibility_log.csv"
    extracted = False
    
    # If visibility_log doesn't exist but zip does, extract ONLY the needed policy
    if not vis_log_path.exists() and zip_file.exists():
        print(f"📦 Extracting {policy}/ from {zip_file.name}...")
        with zipfile.ZipFile(zip_file, 'r') as zip_ref:
            # Extract only files from the specific policy directory
            policy_members = [m for m in zip_ref.namelist() if m.startswith(f"{policy}/")]
            if policy_members:
                zip_ref.extractall(spacing_dir, members=policy_members)
                extracted = True
                print(f"✅ Extracted {len(policy_members)} files to {spacing_dir}/{policy}")
            else:
                print(f"❌ Policy '{policy}' not found in zip")
                return None
    
    # Load visibility log
    if not vis_log_path.exists():
        print(f"❌ File not found: {vis_log_path}")
        return None
    
    df = pd.read_csv(vis_log_path)
    
    # Limit to 1 hour (3600 seconds) for visualization
    df = df[df['time'] <= 3600].copy()
    
    print(f"  Data points: {len(df)} rows")
    print(f"  Time range: {df['time'].min()} - {df['time'].max()} seconds")
    print(f"  Satellites: {sorted(df['sat_id'].unique())[:5]}...")
    
    # Ground station
    gs_lat = 78.2308
    gs_lon = 15.3906
    gs_alt = 0
    
    # Start time
    start_time = datetime(2025, 1, 1, 0, 0, 0)
    
    # CZML document
    czml = [{
        "id": "document",
        "name": f"Constellation: {spacing} {policy} {size}sats",
        "version": "1.0",
        "clock": {
            "interval": f"{start_time.isoformat()}Z/{(start_time + timedelta(seconds=1200)).isoformat()}Z",
            "currentTime": f"{start_time.isoformat()}Z",
            "multiplier": 1
        }
    }]
    
    # Determine sats per base orbital position (50 positions)
    try:
        size_int = int(size)
    except Exception:
        size_int = 50
    sats_per_position = max(1, size_int // 50)

    # Build ground station color intervals based on whether any satellites are in view
    gs_color_intervals = []
    times = sorted(df['time'].unique())
    current_has_sats = None
    interval_start = None
    
    for time_val in times:
        time_str = (start_time + timedelta(seconds=float(time_val))).isoformat() + "Z"
        sats_in_view = df[(df['time'] == time_val) & (df['in_view'] == 1)]
        has_sats = len(sats_in_view) > 0
        
        if current_has_sats is None:
            current_has_sats = has_sats
            interval_start = time_str
            continue
        
        if has_sats != current_has_sats:
            color = [0, 255, 0, 255] if current_has_sats else [128, 128, 128, 255]
            gs_color_intervals.append({
                "interval": f"{interval_start}/{time_str}",
                "rgba": color
            })
            interval_start = time_str
            current_has_sats = has_sats
    
    # Close final interval
    last_time_val = (start_time + timedelta(seconds=float(times[-1]))).isoformat() + "Z"
    color = [0, 255, 0, 255] if current_has_sats else [128, 128, 128, 255]
    gs_color_intervals.append({
        "interval": f"{interval_start}/{last_time_val}",
        "rgba": color
    })
    
    # Add ground station
    czml.append({
        "id": "GroundStation",
        "name": "Svalbard",
        "position": {
            "cartographicDegrees": [gs_lon, gs_lat, gs_alt]
        },
        "point": {
            "pixelSize": 14,
            "color": gs_color_intervals
        },
        "label": {
            "text": "Svalbard GS",
            "font": "14px sans-serif",
            "fillColor": {"rgba": [255, 255, 255, 255]},
            "outlineColor": {"rgba": [0, 0, 0, 255]},
            "outlineWidth": 2,
            "style": "FILL_AND_OUTLINE",
            "pixelOffset": {"cartesian2": [0, -15]}
        }
    })

    # Lead/cluster palette (distinct colors to follow cluster order visually)
    lead_palette = [
        [255, 99, 71, 255],     # Tomato
        [255, 165, 0, 255],     # Orange
        [255, 215, 0, 255],     # Gold
        [50, 205, 50, 255],     # LimeGreen
        [64, 224, 208, 255],    # Turquoise
        [30, 144, 255, 255],    # DodgerBlue
        [138, 43, 226, 255],    # BlueViolet
        [199, 21, 133, 255],    # MediumVioletRed
        [255, 105, 180, 255],   # HotPink
        [0, 206, 209, 255],     # DarkTurquoise
    ]

    # Process each satellite
    for sat_id in sorted(df['sat_id'].unique()):
        sat_df = df[df['sat_id'] == sat_id].copy()
        
        # Build position data
        positions = []
        for _, row in sat_df.iterrows():
            time_str = (start_time + timedelta(seconds=float(row['time']))).isoformat() + "Z"
            positions.extend([
                time_str,
                row['lon_deg'], row['lat_deg'], 500000  # 500km altitude for visibility
            ])
        
        # Build color intervals (grey=out of view, purple=in view/contention, green=connected)
        color_intervals = []
        pixelsize_intervals = []
        label_bg_intervals = []
        current_state = None  # Track state: 'out', 'in_view', 'connected'
        interval_start = None
        first_time = (start_time + timedelta(seconds=float(sat_df.iloc[0]['time']))).isoformat() + "Z"
        
        for _, row in sat_df.iterrows():
            time_str = (start_time + timedelta(seconds=float(row['time']))).isoformat() + "Z"
            
            # Determine state
            if row['connected'] == 1:
                new_state = 'connected'
                color = [0, 255, 0, 255]  # Green
                pixel_size = 16  # Double size for connected
                label_bg = [0, 128, 0, 200]  # Green background
            elif row['in_view'] == 1:
                new_state = 'in_view'
                color = [200, 0, 255, 255]  # Purple (contention)
                pixel_size = 8  # Normal size
                label_bg = [100, 0, 128, 200]  # Purple background
            else:
                new_state = 'out'
                color = [128, 128, 128, 255]  # Grey
                pixel_size = 8  # Normal size
                label_bg = [80, 80, 80, 200]  # Grey background
            
            # Start first interval
            if current_state is None:
                current_state = new_state
                interval_start = time_str
                current_color = color
                current_pixel_size = pixel_size
                current_label_bg = label_bg
                continue
            
            # State changed - close previous interval
            if new_state != current_state:
                color_intervals.append({
                    "interval": f"{interval_start}/{time_str}",
                    "rgba": current_color
                })
                pixelsize_intervals.append({
                    "interval": f"{interval_start}/{time_str}",
                    "number": current_pixel_size
                })
                label_bg_intervals.append({
                    "interval": f"{interval_start}/{time_str}",
                    "rgba": current_label_bg
                })
                interval_start = time_str
                current_state = new_state
                current_color = color
                current_pixel_size = pixel_size
                current_label_bg = label_bg
        
        # Close final interval
        last_time = (start_time + timedelta(seconds=float(sat_df.iloc[-1]['time']))).isoformat() + "Z"
        color_intervals.append({
            "interval": f"{interval_start}/{last_time}",
            "rgba": current_color
        })
        pixelsize_intervals.append({
            "interval": f"{interval_start}/{last_time}",
            "number": current_pixel_size
        })
        label_bg_intervals.append({
            "interval": f"{interval_start}/{last_time}",
            "rgba": current_label_bg
        })
        
        # Determine satellite number, cluster index and base/lead status
        sat_num = int(sat_id) % 1000
        cluster_idx = sat_num // sats_per_position
        is_lead = (sat_num % sats_per_position == 0)

        # Labels: dynamic label with satellite index + elevation/distance when connected
        label_text_intervals = []
        label_show_intervals = []
        
        current_label_text = None
        interval_start = None
        first_time = (start_time + timedelta(seconds=float(sat_df.iloc[0]['time']))).isoformat() + "Z"
        
        for _, row in sat_df.iterrows():
            time_str = (start_time + timedelta(seconds=float(row['time']))).isoformat() + "Z"
            
            # Build label text based on connection status
            if row['connected'] == 1:
                # Show sat number + elevation + distance when connected
                elev = row['elevation_deg']
                dist = row['distance_km']
                new_label_text = f"{sat_num:03d}\nEl:{elev:.1f}°\n{dist:.0f}km"
            else:
                # Just show sat number when not connected
                new_label_text = f"{sat_num:03d}"
            
            # Start first interval
            if current_label_text is None:
                current_label_text = new_label_text
                interval_start = time_str
                continue
            
            # Label text changed - close previous interval
            if new_label_text != current_label_text:
                label_text_intervals.append({
                    "interval": f"{interval_start}/{time_str}",
                    "string": current_label_text
                })
                interval_start = time_str
                current_label_text = new_label_text
        
        # Close final interval
        label_text_intervals.append({
            "interval": f"{interval_start}/{last_time}",
            "string": current_label_text
        })
        
        # Label always visible (controlled by scale in viewer)
        label_show_intervals.append({
            "interval": f"{first_time}/{last_time}",
            "boolean": True
        })
        
        # Build custom properties for buffer and download data
        # Create continuous 1-second intervals (no gaps) by forward-filling
        buffer_intervals = []
        download_intervals = []
        connected_intervals = []
        in_view_intervals = []
        distance_intervals = []
        elevation_intervals = []
        
        # Get all unique timestamps and sort
        all_times = sorted(sat_df['time'].unique())
        max_time = int(sat_df['time'].max())
        
        # Create mapping of time -> row data
        time_data = {}
        for _, row in sat_df.iterrows():
            time_data[row['time']] = row
        
        # Generate intervals for every second (forward fill)
        last_row = None
        for t in range(0, max_time + 1):
            # Use actual data if available, otherwise forward fill
            if t in time_data:
                last_row = time_data[t]
            
            if last_row is None:
                continue
                
            time_str = (start_time + timedelta(seconds=t)).isoformat() + "Z"
            next_time = (start_time + timedelta(seconds=t + 1, milliseconds=1)).isoformat() + "Z"
            
            buffer = last_row['buffer_mb'] if pd.notna(last_row['buffer_mb']) else 0
            download = last_row['downloaded_mb'] if pd.notna(last_row['downloaded_mb']) else 0
            connected = last_row['connected'] == 1
            in_view = last_row['in_view'] == 1
            distance = last_row['distance_km'] if pd.notna(last_row['distance_km']) else 0
            elevation = last_row['elevation_deg'] if pd.notna(last_row['elevation_deg']) else 0
            
            buffer_intervals.append({
                "interval": f"{time_str}/{next_time}",
                "number": float(buffer)
            })
            download_intervals.append({
                "interval": f"{time_str}/{next_time}",
                "number": float(download)
            })
            connected_intervals.append({
                "interval": f"{time_str}/{next_time}",
                "boolean": connected
            })
            in_view_intervals.append({
                "interval": f"{time_str}/{next_time}",
                "boolean": in_view
            })
            distance_intervals.append({
                "interval": f"{time_str}/{next_time}",
                "number": float(distance)
            })
            elevation_intervals.append({
                "interval": f"{time_str}/{next_time}",
                "number": float(elevation)
            })
        
        # Build polyline show intervals using the same 1-second granularity as connected_intervals
        # This ensures the green connection line matches exactly with the connection state
        polyline_show_intervals = []
        for conn_interval in connected_intervals:
            polyline_show_intervals.append({
                "interval": conn_interval["interval"],
                "boolean": conn_interval["boolean"]
            })
        
        # Add satellite packet
        czml.append({
            "id": f"sat_{sat_id}",
            "name": f"Satellite {int(sat_id) % 1000:03d}",
            "properties": {
                "buffer_mb": buffer_intervals,
                "download_mb": download_intervals,
                "is_connected": connected_intervals,
                "in_view": in_view_intervals,
                "distance_km": distance_intervals,
                "elevation_deg": elevation_intervals
            },
            "position": {
                "epoch": f"{start_time.isoformat()}Z",
                "cartographicDegrees": positions
            },
            "point": {
                "pixelSize": pixelsize_intervals,
                "color": color_intervals,
                "outlineColor": {"rgba": [0, 0, 0, 0]},
                "outlineWidth": 0
            },
            "label": {
                "show": label_show_intervals,
                "text": label_text_intervals,
                "font": "14px sans-serif",
                "fillColor": {"rgba": [255, 255, 255, 255]},  # White text
                "backgroundColor": label_bg_intervals,
                "showBackground": True,
                "backgroundPadding": {"cartesian2": [8, 4]},
                "style": "FILL",
                "pixelOffset": {"cartesian2": [50, -30]}
            },
            "polyline": {
                "show": polyline_show_intervals,
                "positions": {
                    "references": [
                        f"sat_{sat_id}#position",
                        "GroundStation#position"
                    ]
                },
                "material": {
                    "solidColor": {
                        "color": {"rgba": [0, 255, 0, 200]}
                    }
                },
                "width": 2
            }
        })
    
    # Save CZML with image size in filename
    # Always write next to this script in examples/bent-pipe-constellation/cesium_output
    script_dir = Path(__file__).resolve().parent
    output_dir = script_dir / "cesium_output"
    output_dir.mkdir(exist_ok=True)
    
    # Format image size as 5-digit number to match analysis convention
    image_size_padded = image_size.zfill(5)  # e.g., "028" -> "00028", "28000" -> "28000"
    output_file = output_dir / f"{spacing}_{policy}_{size}sats_{image_size_padded}.czml"
    
    with open(output_file, 'w') as f:
        json.dump(czml, f)
    
    file_size = output_file.stat().st_size / (1024 * 1024)
    print(f"\n✅ Generated: {output_file.name}")
    print(f"   File size: {file_size:.2f} MB")
    
    # Compress the CZML file
    print(f"🗜️  Compressing to .gz...")
    output_gz = output_file.with_suffix('.czml.gz')
    with open(output_file, 'rb') as f_in:
        with gzip.open(output_gz, 'wb') as f_out:
            shutil.copyfileobj(f_in, f_out)
    
    # Remove uncompressed file
    output_file.unlink()
    
    compressed_size = output_gz.stat().st_size / (1024 * 1024)
    print(f"   Compressed: {compressed_size:.2f} MB ({compressed_size/file_size*100:.1f}% of original)")
    
    # Cleanup: remove extracted directory if we extracted it
    if extracted and policy_dir.exists():
        print(f"🧹 Cleaning up {policy_dir}...")
        shutil.rmtree(policy_dir)
        print(f"✅ Cleanup complete")
    
    return str(output_gz)


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) >= 5:
        # Command line arguments: analysis_dir spacing policy size
        analysis_dir = sys.argv[1]
        spacing = sys.argv[2]
        policy = sys.argv[3]
        size = sys.argv[4]
    else:
        # Test with orbit-spaced, fifo, 100 sats, 02799 MB image
        size = "100"
        analysis_dir = "constellation_analysis_20251022_201325_02799_100"
        spacing = "orbit-spaced"
        policy = "fifo"
    
    filename = generate_single_czml(size, analysis_dir, spacing, policy)
    if filename:
        print(f"\n✅ Success! File: {filename}")
    else:
        print(f"\n❌ Failed to generate CZML")
        sys.exit(1)
