#!/usr/bin/env python3
"""
setup_next_pass.py
- Reads configuration/{date-time.dat, time-step.dat, planet.tle}
- Finds next pass of the TLE over Svalbard (78.229, 15.407)
- Updates:
    date-time.dat -> AOS - PRE_MARGIN_SEC
    num-steps.dat -> ceil((AOS->LOS + PRE_MARGIN_SEC + POST_MARGIN_SEC) / timestep)
"""

from datetime import datetime, timezone, timedelta
import math
import os
import sys

# ---- You may tweak these margins ----
PRE_MARGIN_SEC  = 60   # start sim this many seconds before AOS
POST_MARGIN_SEC = 60   # keep sim running this many seconds after LOS
HOURS_AHEAD     = 12   # search window for the next pass

# ---- Ground site ----
GS_LAT  = 78.229
GS_LON  = 15.407
GS_HAE_M = 0.0

CFG_DIR = os.path.join(os.getcwd(), "configuration")
DATE_TIME = os.path.join(CFG_DIR, "date-time.dat")
TIME_STEP = os.path.join(CFG_DIR, "time-step.dat")
NUM_STEPS = os.path.join(CFG_DIR, "num-steps.dat")
TLE_PATH  = os.path.join(CFG_DIR, "planet.tle")

def read_date_time(path):
    with open(path, "r") as f:
        header = f.readline().rstrip("\n")
        vals = f.readline().strip()
    y,m,d,H,M,S,NS = vals.split(",")
    start = datetime(int(y), int(m), int(d), int(H), int(M), int(S),
                     int(int(NS)//1000), tzinfo=timezone.utc)
    return header, start

def read_time_step(path):
    # hour,minute,second,nanosecond
    with open(path, "r") as f:
        f.readline()
        line = f.readline().strip()
    hh,mm,ss,ns = [int(x) for x in line.split(",")]
    dt = hh*3600 + mm*60 + ss + ns*1e-9
    return dt

def write_date_time(path, header, start_dt):
    ns = int(start_dt.microsecond) * 1000
    with open(path, "w") as f:
        f.write(header + "\n")
        f.write(f"{start_dt.year:04d},{start_dt.month:02d},{start_dt.day:02d},"
                f"{start_dt.hour:02d},{start_dt.minute:02d},{start_dt.second:02d},"
                f"{ns:09d}\n")

def write_num_steps(path, steps):
    # COTE examples use a zero-padded width (19). Match that style.
    with open(path, "w") as f:
        f.write("steps\n")
        f.write(f"{steps:019d}\n")

def load_tle(path):
    with open(path, "r") as f:
        lines = [line.strip() for line in f.readlines() if line.strip()]
    
    # Handle both 2-line and 3-line TLE formats
    if len(lines) == 2 and lines[0].startswith("1 ") and lines[1].startswith("2 "):
        return lines[0], lines[1]
    elif len(lines) == 3 and lines[1].startswith("1 ") and lines[2].startswith("2 "):
        return lines[1], lines[2]  # Skip name line
    else:
        raise RuntimeError("planet.tle must contain either 2 or 3 lines: [name], line1, line2")
    return l1, l2

def find_next_pass(start_dt, l1, l2):
    # Skyfield imports here so the script can at least print a nice error
    from skyfield.api import load, EarthSatellite, wgs84

    ts = load.timescale()
    sat = EarthSatellite(l1, l2, "SAT", ts)
    gs  = wgs84.latlon(GS_LAT, GS_LON, elevation_m=GS_HAE_M)

    def alt_deg(t_dt):
        tt = ts.from_datetime(t_dt)
        alt, az, dist = (sat - gs).at(tt).altaz()[:3]
        return alt.degrees

    t = start_dt
    end = start_dt + timedelta(hours=HOURS_AHEAD)
    step = timedelta(seconds=10)

    alt_prev = alt_deg(t)
    track = []
    aos = None
    los = None

    # scan forward for up to HOURS_AHEAD with 10s steps; refine with bisection
    while t <= end:
        t_next = t + step
        alt_next = alt_deg(t_next)

        if alt_prev > 0 or alt_next > 0:
            track.append((t, alt_prev))

        # detect AOS
        if alt_prev <= 0 < alt_next and aos is None:
            lo, hi = t, t_next
            for _ in range(24):
                mid = lo + (hi - lo)/2
                if alt_deg(mid) > 0:
                    hi = mid
                else:
                    lo = mid
            aos = hi
            track = [(aos, alt_deg(aos))]

        # detect LOS
        if aos and alt_prev > 0 and alt_next <= 0:
            lo, hi = t, t_next
            for _ in range(24):
                mid = lo + (hi - lo)/2
                if alt_deg(mid) > 0:
                    lo = mid
                else:
                    hi = mid
            los = hi
            track.append((los, 0.0))
            break

        t, alt_prev = t_next, alt_next

    if not aos or not los:
        return None

    t_peak, alt_peak = max(track, key=lambda x: x[1])
    return {
        "aos": aos,
        "los": los,
        "t_peak": t_peak,
        "alt_peak_deg": alt_peak
    }

def main():
    # Read configs
    dt_header, start = read_date_time(DATE_TIME)
    dt_seconds = read_time_step(TIME_STEP)
    l1, l2 = load_tle(TLE_PATH)

    result = find_next_pass(start, l1, l2)
    if not result:
        print(f"No pass found within {HOURS_AHEAD} hours from {start.isoformat()}")
        sys.exit(1)

    aos = result["aos"]
    los = result["los"]
    peak_t = result["t_peak"]
    peak_alt = result["alt_peak_deg"]

    # New start: PRE_MARGIN before AOS
    new_start = aos - timedelta(seconds=PRE_MARGIN_SEC)

    # Duration to cover: pre + pass + post
    cover_sec = PRE_MARGIN_SEC + (los - aos).total_seconds() + POST_MARGIN_SEC
    steps = math.ceil(cover_sec / dt_seconds)

    # Write back
    write_date_time(DATE_TIME, dt_header, new_start)
    write_num_steps(NUM_STEPS, steps)

    # Report
    print("=== Next pass configured ===")
    print("Original start   :", start.isoformat())
    print("AOS (rise)       :", aos.isoformat())
    print("Peak elev        :", f"{peak_alt:.1f} deg at {peak_t.isoformat()}")
    print("LOS (set)        :", los.isoformat())
    print("Time step (s)    :", f"{dt_seconds:.6f}")
    print("New start (UTC)  :", new_start.isoformat(), f"(= AOS - {PRE_MARGIN_SEC}s)")
    print("Sim span (s)     :", f"{cover_sec:.1f}")
    print("Num steps        :", steps)
    print("\nFiles updated:")
    print(" - configuration/date-time.dat")
    print(" - configuration/num-steps.dat")

if __name__ == "__main__":
    try:
        main()
    except ModuleNotFoundError as e:
        print("Missing dependency:", e)
        print("Install with either:")
        print("  python3 -m venv ~/venvs/sky && source ~/venvs/sky/bin/activate && pip install skyfield numpy")
        print("  # or: sudo apt install python3-skyfield python3-numpy")
        sys.exit(2)
