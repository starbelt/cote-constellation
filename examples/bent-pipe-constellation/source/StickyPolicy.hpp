#pragma once

#include <vector>
#include <map>
#include "SchedulingPolicy.hpp"
#include <Satellite.hpp>
#include <Sensor.hpp>
#include <DateTime.hpp>

class StickyPolicy : public SchedulingPolicy {
public:
    virtual std::string getPolicyName() override {
        return "Sticky";
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
            for(const auto* sat : visibleSats) {
                if(sat == currentSat) {
                    return currentSat;
                }
            }
        }
        
        cote::Satellite* bestSat = nullptr;
        uint64_t bestSatBuffer = 0;
        
        for(const auto* sat : visibleSats) {
            const uint32_t SAT_ID = sat->getID();
            const uint64_t BUF = satId2Sensor.at(SAT_ID)->getBitsBuffered();
            
            if(!satId2Occupied.at(SAT_ID) && BUF > bestSatBuffer) {
                bestSat = const_cast<cote::Satellite*>(sat);
                bestSatBuffer = BUF;
            }
        }
        
        return bestSat;
    }
};
