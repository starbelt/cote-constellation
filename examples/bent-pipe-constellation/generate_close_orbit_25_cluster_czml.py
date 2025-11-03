#!/usr/bin/env python3
"""
Generate CZML files for close-orbit-spaced 25-cluster constellation results
Produces visualization files for dedicated Cesium viewer

Satellite counts: 1, 25, 50, 100, 200
Policies: sticky, fifo, roundrobin, random
Image sizes: 00027, 00279, 02799, 28000, 280000, 1024000 MB
"""

import subprocess
from pathlib import Path

# Configuration
base_results_dir = Path("results/close orbit space 25 clusters")
output_dir = base_results_dir / "cesium_output"
spacing = "close-orbit-spaced"

# Satellite counts (only the clean divisions for 25 clusters)
sat_counts = ["01", "25", "50", "100", "200"]

# Policies
policies = ["sticky", "fifo", "roundrobin", "random"]

# Image sizes (all 6 available)
image_sizes = ["00027", "00279", "02799", "28000", "280000", "1024000"]

print("=" * 80)
print("CLOSE-ORBIT-SPACED 25-CLUSTER CZML GENERATION")
print("=" * 80)
print(f"Output directory: {output_dir}")
print(f"Satellite counts: {', '.join(sat_counts)}")
print(f"Policies: {', '.join(policies)}")
print(f"Image sizes: {', '.join(image_sizes)}")
print(f"Total files to generate: {len(sat_counts) * len(policies) * len(image_sizes)}")
print("=" * 80)

# Ensure output directory exists
output_dir.mkdir(parents=True, exist_ok=True)

# Generate CZML files
successful = 0
failed = 0
skipped = 0
failed_configs = []

for sat_count in sat_counts:
    for image_size in image_sizes:
        # Find matching analysis directory
        # Format: constellation_analysis_YYYYMMDD_HHMMSS_IMAGESIZE_CONSTELSIZE
        pattern = f"constellation_analysis_*_{image_size}_{int(sat_count):02d}"
        matching_dirs = list(base_results_dir.glob(pattern))
        
        if not matching_dirs:
            print(f"\n⚠️  No analysis directory found for {sat_count} sats, {image_size} MB")
            failed += len(policies)
            for policy in policies:
                failed_configs.append((sat_count, policy, image_size))
            continue
        
        analysis_dir = matching_dirs[0]
        
        for policy in policies:
            config_str = f"{spacing}_{policy}_{sat_count}sats_{image_size}"
            
            # Skip if file already exists
            target_file = output_dir / f"{spacing}_{policy}_{sat_count}sats_{image_size}.czml.gz"
            if target_file.exists():
                print(f"⏭️  Skipping (exists): {config_str}")
                skipped += 1
                continue
                
            print(f"\n📊 Generating: {config_str}")
            
            # Run generate_single_czml.py
            # CLI args: analysis_dir spacing policy size
            cmd = [
                "python3",
                "generate_single_czml.py",
                str(analysis_dir),
                spacing,
                policy,
                sat_count
            ]
            
            try:
                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=300  # 5 minute timeout
                )
                
                if result.returncode == 0:
                    # Move the generated file from cesium_output to our output directory
                    source_file = Path("cesium_output") / f"{spacing}_{policy}_{sat_count}sats_{image_size}.czml.gz"
                    if source_file.exists():
                        target_file = output_dir / source_file.name
                        source_file.rename(target_file)
                        print(f"✅ Success: {target_file.name}")
                        successful += 1
                    else:
                        print(f"❌ File not created: {source_file}")
                        if result.stdout:
                            print(f"   stdout: {result.stdout[:500]}")
                        if result.stderr:
                            print(f"   stderr: {result.stderr[:500]}")
                        failed += 1
                        failed_configs.append((sat_count, policy, image_size))
                else:
                    print(f"❌ Generation failed (code {result.returncode}):")
                    if result.stdout:
                        print(f"   stdout: {result.stdout[:500]}")
                    if result.stderr:
                        print(f"   stderr: {result.stderr[:500]}")
                    failed += 1
                    failed_configs.append((sat_count, policy, image_size))
                    
            except subprocess.TimeoutExpired:
                print(f"❌ Timeout after 5 minutes")
                failed += 1
                failed_configs.append((sat_count, policy, image_size))
            except Exception as e:
                print(f"❌ Error: {e}")
                failed += 1
                failed_configs.append((sat_count, policy, image_size))

print("\n" + "=" * 80)
print("GENERATION COMPLETE")
print("=" * 80)
print(f"✅ Successful: {successful}")
print(f"⏭️  Skipped: {skipped}")
print(f"❌ Failed: {failed}")

if failed_configs:
    print(f"\n⚠️  Failed configurations:")
    for sat_count, policy, image_size in failed_configs:
        print(f"  - {sat_count} sats, {policy}, {image_size} MB")

print("=" * 80)
