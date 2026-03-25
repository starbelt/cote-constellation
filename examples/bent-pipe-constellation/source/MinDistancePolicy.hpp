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

class MinDistancePolicy : public SchedulingPolicy {
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
        return "MinDistance";
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
            
            if(bufferedBits == 0) {
                continue;
            }
            
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
        
        if(!candidates.empty()) {
            return candidates[0].sat;
        }
        
        return nullptr;
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

