#!/usr/bin/env python3
"""
Generate CZML files for all combinations of configurations
"""
import os
import subprocess
from pathlib import Path
import zipfile

# Configuration matrix
IMAGE_SIZES = {
    "00027": "constellation_analysis_20251022_170000_00027",
    "00279": "constellation_analysis_20251022_182439_00279",
    "02799": "constellation_analysis_20251022_195835_02799",
    "28000": "constellation_analysis_20251022_212850_28000"
}

CONSTELLATION_SIZES = ["01", "50", "100", "200"]
SPACING_STRATEGIES = ["orbit-spaced", "close-orbit-spaced", "close-spaced", "frame-spaced"]
POLICIES = ["fifo", "sticky", "random", "roundrobin"]

def find_analysis_dir(image_size, constellation_size):
    """Find the analysis directory for a given image size and constellation size"""
    pattern = f"constellation_analysis_*_{image_size}_{constellation_size}"
    matches = list(Path(".").glob(pattern))
    if matches:
        return matches[0].name
    return None

def extract_visibility_log(analysis_dir, spacing, policy):
    """Extract visibility_log.csv from simulation_logs.zip if needed"""
    zip_path = Path(analysis_dir) / spacing / "simulation_logs.zip"
    vis_log = Path(analysis_dir) / spacing / policy / "visibility_log.csv"
    
    if vis_log.exists():
        return True
    
    if not zip_path.exists():
        return False
    
    try:
        print(f"  📦 Extracting {policy}/visibility_log.csv from {zip_path}")
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            zip_ref.extract(f"{policy}/visibility_log.csv", Path(analysis_dir) / spacing)
        return True
    except Exception as e:
        print(f"  ❌ Failed to extract: {e}")
        return False

def cleanup_extracted_log(analysis_dir, spacing, policy):
    """Remove extracted visibility_log.csv after processing to save disk space"""
    vis_log = Path(analysis_dir) / spacing / policy / "visibility_log.csv"
    try:
        if vis_log.exists():
            vis_log.unlink()
            # Also remove the policy directory if empty
            policy_dir = vis_log.parent
            if policy_dir.exists() and not any(policy_dir.iterdir()):
                policy_dir.rmdir()
    except Exception as e:
        print(f"  ⚠️  Failed to cleanup {vis_log}: {e}")

def main():
    generated = []
    skipped = []
    failed = []
    
    total = len(IMAGE_SIZES) * len(CONSTELLATION_SIZES) * len(SPACING_STRATEGIES) * len(POLICIES)
    current = 0
    
    print(f"\n{'='*80}")
    print(f"Generating CZML files for ALL configurations")
    print(f"Total combinations: {total}")
    print(f"{'='*80}\n")
    
    for image_size in IMAGE_SIZES.keys():
        for constellation_size in CONSTELLATION_SIZES:
            # Find the correct analysis directory
            analysis_dir = find_analysis_dir(image_size, constellation_size)
            
            if not analysis_dir:
                print(f"⚠️  No analysis dir for {image_size}_{constellation_size}")
                skipped.extend([f"{image_size}_{constellation_size}_{s}_{p}" 
                               for s in SPACING_STRATEGIES for p in POLICIES])
                current += len(SPACING_STRATEGIES) * len(POLICIES)
                continue
            
            for spacing in SPACING_STRATEGIES:
                spacing_dir = Path(analysis_dir) / spacing
                
                if not spacing_dir.exists():
                    print(f"⚠️  {spacing} not found in {analysis_dir}")
                    skipped.extend([f"{spacing}_{p}_{constellation_size}" for p in POLICIES])
                    current += len(POLICIES)
                    continue
                
                for policy in POLICIES:
                    current += 1
                    config_key = f"{spacing}_{policy}_{constellation_size}"
                    
                    print(f"\n[{current}/{total}] {spacing} | {policy} | {constellation_size} sats | {image_size}")
                    
                    # Extract visibility log if needed
                    if not extract_visibility_log(analysis_dir, spacing, policy):
                        print(f"  ⚠️  Skipping - no visibility log")
                        skipped.append(config_key)
                        continue
                    
                    # Generate CZML
                    try:
                        result = subprocess.run(
                            ["python3", "generate_single_czml.py", 
                             analysis_dir, spacing, policy, constellation_size],
                            capture_output=True,
                            text=True,
                            timeout=300
                        )
                        
                        if result.returncode == 0:
                            print(f"  ✅ Generated")
                            generated.append(config_key)
                        else:
                            print(f"  ❌ Failed: {result.stderr[:200]}")
                            failed.append(config_key)
                    except subprocess.TimeoutExpired:
                        print(f"  ⏱️  Timeout (>5min)")
                        failed.append(config_key)
                    except Exception as e:
                        print(f"  ❌ Error: {e}")
                        failed.append(config_key)
                    finally:
                        # Clean up extracted log file to save disk space
                        cleanup_extracted_log(analysis_dir, spacing, policy)
    
    # Summary
    print(f"\n{'='*80}")
    print(f"SUMMARY")
    print(f"{'='*80}")
    print(f"✅ Generated: {len(generated)}")
    print(f"⚠️  Skipped:   {len(skipped)}")
    print(f"❌ Failed:    {len(failed)}")
    print(f"{'='*80}\n")
    
    if failed:
        print("Failed configurations:")
        for f in failed[:10]:
            print(f"  - {f}")
        if len(failed) > 10:
            print(f"  ... and {len(failed) - 10} more")

if __name__ == "__main__":
    main()
