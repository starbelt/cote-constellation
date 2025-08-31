#pragma once

#include <vector>
#include <map>
#include <random>
#include <algorithm>
#include "SchedulingPolicy.hpp"
#include <Satellite.hpp>
#include <Sensor.hpp>
#include <DateTime.hpp>

class RandomPolicy : public SchedulingPolicy {
private:
    mutable std::mt19937 rng{42};
    mutable std::map<uint32_t, uint64_t> gndId2ConnectionStartStep;
    uint64_t minConnectionSteps = 30;
    
public:
    std::string getPolicyName() override {
        return "Random";
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
        
        if(currentSat != NULL) {
            bool currentSatVisible = false;
            for(const auto* sat : visibleSats) {
                if(sat == currentSat) {
                    currentSatVisible = true;
                    break;
                }
            }
            
            uint64_t connectionSteps = stepCount - gndId2ConnectionStartStep[groundStationId];
            if(currentSatVisible && connectionSteps < minConnectionSteps) {
                return currentSat;
            }
        }
        
        std::vector<cote::Satellite*> eligibleSats;
        
        for(const auto* sat : visibleSats) {
            const uint32_t SAT_ID = sat->getID();
            const uint64_t BUF = satId2Sensor.at(SAT_ID)->getBitsBuffered();
            
            if(BUF > 0) {
                eligibleSats.push_back(const_cast<cote::Satellite*>(sat));
            }
        }
        
        if(eligibleSats.empty()) {
            return nullptr;
        }
        
        std::uniform_int_distribution<size_t> dist(0, eligibleSats.size() - 1);
        cote::Satellite* selected = eligibleSats[dist(rng)];
        gndId2ConnectionStartStep[groundStationId] = stepCount;
        return selected;
    }
};
