#ifndef SCHEDULING_POLICY_HPP
#define SCHEDULING_POLICY_HPP

#include <vector>
#include <map>
#include <string>
#include <Satellite.hpp>
#include <Sensor.hpp>
#include <DateTime.hpp>

class SchedulingPolicy {
public:
    virtual cote::Satellite* makeSchedulingDecision(
        const std::vector<cote::Satellite*>& visibleSats,
        const std::map<uint32_t,cote::Sensor*>& satId2Sensor,
        const std::map<uint32_t,bool>& satId2Occupied,
        const cote::DateTime& currentTime,
        uint32_t groundStationId,
        cote::Satellite* currentSat,
        uint64_t stepCount
    ) = 0;
    
    virtual std::string getPolicyName() = 0;
    virtual ~SchedulingPolicy() = default;
};

#endif
