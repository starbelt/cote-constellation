#!/usr/bin/env python3
"""
Generate a single CZML file for testing
"""
import pandas as pd
import json
from pathlib import Path
from datetime import datetime, timedelta
import sys

def generate_single_czml(size, analysis_dir, spacing, policy):
    """Generate CZML for a single configuration"""
    
    # Extract image size from analysis_dir (e.g., constellation_analysis_20251022_183657_00279_100)
    # Format: constellation_analysis_YYYYMMDD_HHMMSS_IMAGESIZE_CONSTELSIZE
    dir_parts = Path(analysis_dir).name.split('_')
    image_size = dir_parts[3] if len(dir_parts) >= 4 else "unknown"
    
    print(f"\n{'='*80}")
    print(f"Generating: {spacing}, {policy}, {size} satellites, {image_size} MB")
    print(f"Analysis dir: {analysis_dir}")
    print(f"{'='*80}\n")
    
    # Load visibility log
    vis_log_path = Path(analysis_dir) / spacing / policy / "visibility_log.csv"
    
    if not vis_log_path.exists():
        print(f"❌ File not found: {vis_log_path}")
        return None
    
    df = pd.read_csv(vis_log_path)
    
    # Limit to 5 seconds for fast baseline iteration
    df = df[df['time'] <= 5].copy()
    
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
    
    # Add ground station
    czml.append({
        "id": "GroundStation",
        "name": "Svalbard",
        "position": {
            "cartographicDegrees": [gs_lon, gs_lat, gs_alt]
        },
        "point": {
            "pixelSize": 10,
            "color": {"rgba": [255, 0, 0, 255]}
        },
        "label": {
            "text": "Svalbard GS",
            "font": "14px sans-serif",
            "fillColor": {"rgba": [255, 255, 255, 255]},
            "outlineColor": {"rgba": [0, 0, 0, 255]},
            "outlineWidth": 2,
            "style": "FILL_AND_OUTLINE",
            "pixelOffset": {"cartesian2": [15, 0]}
        }
    })
    
    # Determine sats per base orbital position (50 positions)
    try:
        size_int = int(size)
    except Exception:
        size_int = 50
    sats_per_position = max(1, size_int // 50)

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
        
        # Build color intervals (grey=out of view, white=in view, green=connected)
        color_intervals = []
        current_state = None  # Track state: 'out', 'in_view', 'connected'
        interval_start = None
        first_time = (start_time + timedelta(seconds=float(sat_df.iloc[0]['time']))).isoformat() + "Z"
        
        for _, row in sat_df.iterrows():
            time_str = (start_time + timedelta(seconds=float(row['time']))).isoformat() + "Z"
            
            # Determine state
            if row['connected'] == 1:
                new_state = 'connected'
                color = [0, 255, 0, 255]  # Green
            elif row['in_view'] == 1:
                new_state = 'in_view'
                color = [255, 255, 255, 255]  # White
            else:
                new_state = 'out'
                color = [128, 128, 128, 255]  # Grey
            
            # Start first interval
            if current_state is None:
                current_state = new_state
                interval_start = time_str
                current_color = color
                continue
            
            # State changed - close previous interval
            if new_state != current_state:
                color_intervals.append({
                    "interval": f"{interval_start}/{time_str}",
                    "rgba": current_color
                })
                interval_start = time_str
                current_state = new_state
                current_color = color
        
        # Close final interval
        last_time = (start_time + timedelta(seconds=float(sat_df.iloc[-1]['time']))).isoformat() + "Z"
        color_intervals.append({
            "interval": f"{interval_start}/{last_time}",
            "rgba": current_color
        })
        
        # Determine satellite number, cluster index and base/lead status
        sat_num = int(sat_id) % 1000
        cluster_idx = sat_num // sats_per_position
        is_lead = (sat_num % sats_per_position == 0)

        # Labels: always show simple static label with satellite index
        label_text_intervals = []
        label_show_intervals = []
        first_time = (start_time + timedelta(seconds=float(sat_df.iloc[0]['time']))).isoformat() + "Z"
        label_text_intervals.append({
            "interval": f"{first_time}/{last_time}",
            "string": f"Sat {sat_num:03d}{' (LEAD)' if is_lead else ''}"
        })
        label_show_intervals.append({
            "interval": f"{first_time}/{last_time}",
            "boolean": True
        })
        
        # Build connection line show intervals (MUST have explicit false intervals)
        # Start by checking if satellite is connected at first timestamp
        polyline_show_intervals = []
        first_time = (start_time + timedelta(seconds=float(sat_df.iloc[0]['time']))).isoformat() + "Z"
        first_connected = bool(sat_df.iloc[0]['connected'] == 1)
        
        current_connected = first_connected
        interval_start = first_time
        
        for _, row in sat_df.iterrows():
            time_str = (start_time + timedelta(seconds=float(row['time']))).isoformat() + "Z"
            is_connected = bool(row['connected'] == 1)
            
            if is_connected != current_connected:
                # Close previous interval
                polyline_show_intervals.append({
                    "interval": f"{interval_start}/{time_str}",
                    "boolean": current_connected
                })
                interval_start = time_str
                current_connected = is_connected
        
        # Close final interval
        polyline_show_intervals.append({
            "interval": f"{interval_start}/{last_time}",
            "boolean": current_connected
        })
        
        # Build custom properties for buffer and download data
        # Create continuous 1-second intervals (no gaps) by forward-filling
        buffer_intervals = []
        download_intervals = []
        connected_intervals = []
        in_view_intervals = []
        
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
        
        # Add satellite packet
        czml.append({
            "id": f"sat_{sat_id}",
            "name": f"Satellite {int(sat_id) % 1000:03d}",
            "properties": {
                "buffer_mb": buffer_intervals,
                "download_mb": download_intervals,
                "is_connected": connected_intervals,
                "in_view": in_view_intervals
            },
            "position": {
                "epoch": f"{start_time.isoformat()}Z",
                "cartographicDegrees": positions
            },
            "point": {
                "pixelSize": 8,
                "color": color_intervals,
                "outlineColor": {"rgba": lead_palette[cluster_idx % len(lead_palette)]} if is_lead else {"rgba": [0, 0, 0, 0]},
                "outlineWidth": 3 if is_lead else 0
            },
            "label": {
                "show": label_show_intervals,
                "text": label_text_intervals,
                "font": "14px sans-serif",
                "fillColor": {"rgba": [255, 255, 255, 255]},  # White text
                "backgroundColor": {"rgba": lead_palette[cluster_idx % len(lead_palette)]} if is_lead else {"rgba": [0, 128, 0, 200]},
                "showBackground": True,
                "backgroundPadding": {"cartesian2": [8, 4]},
                "style": "FILL",
                "pixelOffset": {"cartesian2": [20, -10]}
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
    output_file = output_dir / f"{spacing}_{policy}_{size}sats_{image_size}mb.czml"
    
    with open(output_file, 'w') as f:
        json.dump(czml, f)
    
    file_size = output_file.stat().st_size / (1024 * 1024)
    print(f"\n✅ Generated: {output_file.name}")
    print(f"   File size: {file_size:.2f} MB")
    
    return str(output_file)


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
