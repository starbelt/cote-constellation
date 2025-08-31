# Satellite Downlink Scheduling Policies

This directory contains various scheduling policies for satellite-to-ground downlink operations. Each policy implements a different strategy for deciding which satellite a ground station should connect to at any given time.

## Policy Overview

### GreedyPolicy (Sticky)
A simple greedy policy that maintains the current satellite connection as long as possible. Once connected to a satellite, it will not switch unless the satellite goes out of view. When no satellite is connected, it selects the visible satellite with the highest buffered data volume. This represents the original "bent-pipe" behavior where ground stations stick to their chosen satellite.

### FIFOPolicy (First-In-First-Out)
Implements a realistic First-In-First-Out queue-based scheduling system. Satellites are queued in the order they first become visible to each ground station. The policy maintains a minimum 30-second connection time before allowing switches, then moves to the next satellite in the FIFO queue. This ensures fair access based on arrival order while maintaining realistic connection durations.

### ShortestJobFirstPolicy (SJF)
A non-preemptive shortest job first scheduler that selects satellites with the least amount of buffered data to download. After maintaining a minimum 30-second connection, it switches to the satellite with the smallest data buffer among visible options. This policy aims to minimize average completion time by handling smaller data transfers first.

### ShortestRemainingTimePolicy (SRTF)
Similar to SJF but uses a preemptive approach where the scheduler continuously evaluates which satellite has the least remaining data to download. After the minimum connection time, it always switches to the satellite with the smallest buffer, making it more responsive to changing conditions than SJF.

### RoundRobinPolicy
Implements a round-robin scheduling approach that cycles through visible satellites in a predetermined order. Each satellite gets a fair time slice (minimum 30 seconds) before the scheduler moves to the next satellite in the rotation. This ensures all satellites receive equal access regardless of their data buffer sizes.

### RandomPolicy
A randomized scheduler that selects satellites pseudo-randomly from the available options. It maintains the minimum 30-second connection time for realistic operations, then randomly chooses among visible satellites with data to download. Uses a fixed seed (42) for reproducible results across simulation runs.

## Common Features

All policies (except Greedy) implement:
- **Minimum Connection Time**: 30-second minimum connection duration for realistic satellite operations
- **Data-Aware Selection**: Only select satellites that have buffered data to download
- **Visibility Tracking**: Automatically handle satellites going in and out of view
- **Fair Resource Usage**: Respect satellite occupation status to prevent conflicts

## Usage

Policies are selected via command line argument when running the simulation:
```bash
./bent-pipe /path/to/config/ /path/to/logs/ [policy_name]
```

Supported policy names: `greedy`, `fifo`, `sjf`, `srtf`, `roundrobin`, `random`
