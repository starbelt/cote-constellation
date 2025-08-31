#pragma once

#include <vector>
#include <map>
#include "SchedulingPolicy.hpp"
#include <Satellite.hpp>
#include <Sensor.hpp>
#include <DateTime.hpp>

class ShortestJobFirstPolicy : public SchedulingPolicy {
public:
    std::string getPolicyName() override {
        return "ShortestJobFirst";
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
        // TODO: SJF policy implementation to be completed
        
        for(const auto* sat : visibleSats) {
            const uint32_t SAT_ID = sat->getID();
            const uint64_t BUF = satId2Sensor.at(SAT_ID)->getBitsBuffered();
            
            if(BUF > 0) {
                return const_cast<cote::Satellite*>(sat);
            }
        }
        
        return nullptr;
    }
};
