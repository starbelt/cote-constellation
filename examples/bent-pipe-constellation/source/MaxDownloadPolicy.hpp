#pragma once

#include <vector>
#include <map>
#include <algorithm>
#include <cmath>
#include "SchedulingPolicy.hpp"
#include <Satellite.hpp>
#include <Sensor.hpp>
#include <DateTime.hpp>
#include <utilities.hpp>
#include <Channel.hpp>
#include <Transmitter.hpp>
#include <Receiver.hpp>

/**
 * MaxDownloadPolicy - Smart Maximum Download Link Scheduling Policy
 * 
 * An intelligent link scheduling policy that maximizes actual data downloaded
 * by considering both link quality (bitrate) AND available buffer data.
 * 
 * Algorithm:
 * 1. Every timestep, evaluate all visible satellites
 * 2. For each satellite, calculate potential download in next timestep:
 *    potential_download_MB = min(bitrate_Mbps * 1.0 second, buffer_MB)
 * 3. Detect operating regime:
 *    a) Buffer-limited: ALL satellites have buffer < 1 second of capacity
 *       → Prioritize BITRATE (all buffers drain instantly anyway)
 *    b) Capacity-limited: Some satellites have sustained buffer
 *       → Prioritize POTENTIAL DOWNLOAD (balance bitrate vs buffer)
 * 4. Select best satellite for current regime
 * 5. Switch immediately if a better download opportunity becomes available
 * 
 * Key Insight - Two Operating Regimes:
 * 1. Buffer-Limited (small images, < ~1MB):
 *    All satellites have tiny buffers that drain in << 1 second.
 *    Strategy: Pick satellite with MOST BUFFER to maximize data downloaded.
 *    Example: Sat A has 0.06 MB, Sat B has 0.03 MB, both at 120 Mbps
 *    → Choose Sat A to download 0.06 MB instead of 0.03 MB (2x more data!)
 * 
 * 2. Capacity-Limited (large images, > ~1MB):
 *    A satellite with high bitrate but low buffer may download less than
 *    a satellite with moderate bitrate but full buffer.
 *    Example:
 *      Sat A: 100 Mbps, 2 MB buffer  → potential = min(12.5, 2) = 2 MB
 *      Sat B: 80 Mbps, 300 MB buffer → potential = min(10, 300) = 10 MB
 *      Decision: Choose Sat B (more actual data downloaded)
 * 
 * Note: Timestep is 1 second, so bitrate_Mbps directly equals MB/sec download rate.
 */
class MaxDownloadPolicy : public SchedulingPolicy {
private:
    // Helper struct to pair satellite with its download potential
    struct SatDownloadCandidate {
        cote::Satellite* sat;
        double potentialDownloadMB;  // Higher is better (actual data we can download)
        double bitrateMbps;          // For tie-breaking
        uint64_t bufferedBits;
        
        SatDownloadCandidate(cote::Satellite* s, double potential, double bitrate, uint64_t buf) 
            : sat(s), potentialDownloadMB(potential), bitrateMbps(bitrate), bufferedBits(buf) {}
    };

public:
    std::string getPolicyName() override {
        return "MaxDownload";
    }
    
    // Override the 9-parameter version with bitrate information
    cote::Satellite* makeSchedulingDecision(
        const std::vector<cote::Satellite*>& visibleSats,
        const std::map<uint32_t,cote::Sensor*>& satId2Sensor,
        const std::map<uint32_t,bool>& satId2Occupied,
        const cote::DateTime& currentTime,
        uint32_t groundStationId,
        cote::Satellite* currentSat,
        uint64_t stepCount,
        cote::GroundStation* groundStation,
        const std::map<uint32_t,double>& satId2BitrateMbps
    ) override {
        
        // If no satellites visible, disconnect
        if(visibleSats.empty()) {
            return nullptr;
        }
        
        // Build list of candidate satellites with potential download calculations
        std::vector<SatDownloadCandidate> candidates;
        
        for(auto* sat : visibleSats) {
            uint32_t satId = sat->getID();
            
            // Skip if occupied by another ground station
            if(satId2Occupied.count(satId) && satId2Occupied.at(satId)) {
                // Exception: if we're the ones occupying it (currentSat), include it
                if(currentSat == nullptr || sat->getID() != currentSat->getID()) {
                    continue;
                }
            }
            
            // Get buffer status
            uint64_t bufferedBits = satId2Sensor.at(satId)->getBitsBuffered();
            
            // Skip satellites with empty buffers
            if(bufferedBits == 0) {
                continue;
            }
            
            // Get bitrate for this satellite
            double bitrateMbps = satId2BitrateMbps.at(satId);
            
            // Calculate potential download in next timestep (1 second)
            // Bitrate is in Mbps (megabits per second)
            // Buffer is in bits, convert to MB
            double bufferMB = (static_cast<double>(bufferedBits) / 8.0) / 1.0e6;
            
            // Download limited by min(bitrate capacity, available buffer)
            // bitrateMbps * 1.0 second = megabits per second
            // Convert to MB: megabits / 8 = megabytes
            double downloadCapacityMB = bitrateMbps / 8.0;  // MB we could download in 1 second
            double potentialDownloadMB = std::min(downloadCapacityMB, bufferMB);
            
            candidates.emplace_back(sat, potentialDownloadMB, bitrateMbps, bufferedBits);
        }
        
        // If no valid candidates, disconnect
        if(candidates.empty()) {
            return nullptr;
        }
        
        // Check if ALL candidates are buffer-limited (will drain to zero in < 1 second)
        // In this regime, maximize data downloaded by picking satellite with most buffer
        bool allBufferLimited = true;
        for(const auto& c : candidates) {
            double downloadCapacityMB = c.bitrateMbps / 8.0;  // MB per second
            double bufferMB = (static_cast<double>(c.bufferedBits) / 8.0) / 1.0e6;
            if(bufferMB >= downloadCapacityMB) {
                allBufferLimited = false;
                break;
            }
        }
        
        // Sort by appropriate metric
        if(allBufferLimited) {
            // Buffer-limited regime: ALL satellites will drain completely
            // Strategy: Pick satellite with MOST data to maximize total downloaded
            // (since they all drain instantly, get the biggest chunk possible)
            std::sort(candidates.begin(), candidates.end(),
                [](const SatDownloadCandidate& a, const SatDownloadCandidate& b) {
                    // Primary: potential download (more buffer = more data)
                    if(std::abs(a.potentialDownloadMB - b.potentialDownloadMB) < 0.001) {
                        // Tie-breaker: prefer higher bitrate (faster drain if buffers equal)
                        return a.bitrateMbps > b.bitrateMbps;
                    }
                    return a.potentialDownloadMB > b.potentialDownloadMB;
                });
        } else {
            // Capacity-limited regime: Some satellites have sustained buffers
            // Strategy: Balance bitrate and buffer size for sustained throughput
            std::sort(candidates.begin(), candidates.end(),
                [](const SatDownloadCandidate& a, const SatDownloadCandidate& b) {
                    if(std::abs(a.potentialDownloadMB - b.potentialDownloadMB) < 0.001) {
                        // Tie-breaker: prefer higher bitrate
                        return a.bitrateMbps > b.bitrateMbps;
                    }
                    return a.potentialDownloadMB > b.potentialDownloadMB;  // Higher potential = better
                });
        }
        
        // Return the best candidate (highest potential download)
        return candidates[0].sat;
    }
    
    // Stub for 8-parameter interface (calls 9-param with empty bitrate map)
    cote::Satellite* makeSchedulingDecision(
        const std::vector<cote::Satellite*>& visibleSats,
        const std::map<uint32_t,cote::Sensor*>& satId2Sensor,
        const std::map<uint32_t,bool>& satId2Occupied,
        const cote::DateTime& currentTime,
        uint32_t groundStationId,
        cote::Satellite* currentSat,
        uint64_t stepCount,
        cote::GroundStation* groundStation
    ) override {
        // This should never be called - MaxDownload requires bitrate information
        std::map<uint32_t,double> emptyBitrates;
        return makeSchedulingDecision(visibleSats, satId2Sensor, satId2Occupied,
                                     currentTime, groundStationId, currentSat, stepCount,
                                     groundStation, emptyBitrates);
    }
    
    // Stub for legacy 7-parameter interface
    cote::Satellite* makeSchedulingDecision(
        const std::vector<cote::Satellite*>& visibleSats,
        const std::map<uint32_t,cote::Sensor*>& satId2Sensor,
        const std::map<uint32_t,bool>& satId2Occupied,
        const cote::DateTime& currentTime,
        uint32_t groundStationId,
        cote::Satellite* currentSat,
        uint64_t stepCount
    ) override {
        // This should never be called - MaxDownload requires ground station and bitrate
        return nullptr;
    }
};


