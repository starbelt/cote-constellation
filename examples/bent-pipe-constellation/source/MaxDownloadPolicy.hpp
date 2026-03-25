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

class MaxDownloadPolicy : public SchedulingPolicy {
private:
    struct SatDownloadCandidate {
        cote::Satellite* sat;
        double potentialDownloadMB;
        double bitrateMbps;
        uint64_t bufferedBits;
        
        SatDownloadCandidate(cote::Satellite* s, double potential, double bitrate, uint64_t buf) 
            : sat(s), potentialDownloadMB(potential), bitrateMbps(bitrate), bufferedBits(buf) {}
    };

public:
    std::string getPolicyName() override {
        return "MaxDownload";
    }
    
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
        
        if(visibleSats.empty()) {
            return nullptr;
        }
        
        std::vector<SatDownloadCandidate> candidates;
        
        for(auto* sat : visibleSats) {
            uint32_t satId = sat->getID();
            
            if(satId2Occupied.count(satId) && satId2Occupied.at(satId)) {
                if(currentSat == nullptr || sat->getID() != currentSat->getID()) {
                    continue;
                }
            }
            
            uint64_t bufferedBits = satId2Sensor.at(satId)->getBitsBuffered();
            
            if(bufferedBits == 0) {
                continue;
            }
            
            double bitrateMbps = satId2BitrateMbps.at(satId);
            
            // potential_download = min(link_capacity, buffer)
            double bufferMB = (static_cast<double>(bufferedBits) / 8.0) / 1.0e6;
            double downloadCapacityMB = bitrateMbps / 8.0;
            double potentialDownloadMB = std::min(downloadCapacityMB, bufferMB);
            
            candidates.emplace_back(sat, potentialDownloadMB, bitrateMbps, bufferedBits);
        }
        
        if(candidates.empty()) {
            return nullptr;
        }
        
        // Check if all candidates are buffer-limited
        bool allBufferLimited = true;
        for(const auto& c : candidates) {
            double downloadCapacityMB = c.bitrateMbps / 8.0;  // MB per second
            double bufferMB = (static_cast<double>(c.bufferedBits) / 8.0) / 1.0e6;
            if(bufferMB >= downloadCapacityMB) {
                allBufferLimited = false;
                break;
            }
        }
        
        if(allBufferLimited) {
            // Buffer-limited: pick satellite with most data
            std::sort(candidates.begin(), candidates.end(),
                [](const SatDownloadCandidate& a, const SatDownloadCandidate& b) {
                    if(std::abs(a.potentialDownloadMB - b.potentialDownloadMB) < 0.001) {
                        return a.bitrateMbps > b.bitrateMbps;
                    }
                    return a.potentialDownloadMB > b.potentialDownloadMB;
                });
        } else {
            // Capacity-limited: balance bitrate and buffer
            std::sort(candidates.begin(), candidates.end(),
                [](const SatDownloadCandidate& a, const SatDownloadCandidate& b) {
                    if(std::abs(a.potentialDownloadMB - b.potentialDownloadMB) < 0.001) {
                        return a.bitrateMbps > b.bitrateMbps;
                    }
                    return a.potentialDownloadMB > b.potentialDownloadMB;
                });
        }
        
        return candidates[0].sat;
    }
    
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
        std::map<uint32_t,double> emptyBitrates;
        return makeSchedulingDecision(visibleSats, satId2Sensor, satId2Occupied,
                                     currentTime, groundStationId, currentSat, stepCount,
                                     groundStation, emptyBitrates);
    }
    
    cote::Satellite* makeSchedulingDecision(
        const std::vector<cote::Satellite*>& visibleSats,
        const std::map<uint32_t,cote::Sensor*>& satId2Sensor,
        const std::map<uint32_t,bool>& satId2Occupied,
        const cote::DateTime& currentTime,
        uint32_t groundStationId,
        cote::Satellite* currentSat,
        uint64_t stepCount
    ) override {
        return nullptr;
    }
};


