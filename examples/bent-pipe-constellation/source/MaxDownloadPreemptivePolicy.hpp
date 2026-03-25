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

class MaxDownloadPreemptivePolicy : public SchedulingPolicy {
private:
    struct SatDistanceCandidate {
        cote::Satellite* sat;
        double distanceKm;
        uint64_t bufferedBits;
        
        SatDistanceCandidate(cote::Satellite* s, double dist, uint64_t buf) 
            : sat(s), distanceKm(dist), bufferedBits(buf) {}
    };

public:
    std::string getPolicyName() override {
        return "MaxDownloadPreemptive";
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
        
        if(visibleSats.empty()) {
            return nullptr;
        }
        
        std::vector<SatDistanceCandidate> candidates;
        
        for(auto* sat : visibleSats) {
            uint32_t satId = sat->getID();
            
            if(satId2Occupied.count(satId) && satId2Occupied.at(satId)) {
                if(currentSat == nullptr || sat->getID() != currentSat->getID()) {
                    continue;
                }
            }
            
            uint64_t bufferedBits = satId2Sensor.at(satId)->getBitsBuffered();
            
            std::array<double,3> satPosn = sat->getECIPosn();
            std::array<double,3> gndPosn = groundStation->getECIPosn();
            
            double dx = satPosn[0] - gndPosn[0];
            double dy = satPosn[1] - gndPosn[1];
            double dz = satPosn[2] - gndPosn[2];
            double distanceKm = std::sqrt(dx*dx + dy*dy + dz*dz);
            
            candidates.emplace_back(sat, distanceKm, bufferedBits);
        }
        
        if(candidates.empty()) {
            return nullptr;
        }
        
        std::sort(candidates.begin(), candidates.end(),
            [](const SatDistanceCandidate& a, const SatDistanceCandidate& b) {
                return a.distanceKm < b.distanceKm;
            });
        
        if(currentSat != nullptr) {
            auto currentIt = std::find_if(candidates.begin(), candidates.end(),
                [currentSat](const SatDistanceCandidate& c) {
                    return c.sat->getID() == currentSat->getID();
                });
            
            if(currentIt != candidates.end()) {
                size_t currentRank = std::distance(candidates.begin(), currentIt);
                
                if(currentRank == 0) {
                    return currentSat;
                }
                
                if(currentIt->bufferedBits > 0 && currentRank < 3) {
                    return currentSat;
                }
            }
        }
        
        for(const auto& candidate : candidates) {
            if(candidate.bufferedBits > 0) {
                return candidate.sat;
            }
        }
        
        // No data available; stay with closest satellite
        return candidates[0].sat;
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
