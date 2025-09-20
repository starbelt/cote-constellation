#ifndef BENTPIPESTRATEGY_HPP
#define BENTPIPESTRATEGY_HPP

#include "SpacingStrategy.hpp"
#include <utilities.hpp>

class BentPipeStrategy : public SpacingStrategy {
public:
    BentPipeStrategy() = default;
    ~BentPipeStrategy() = default;

    bool shouldTriggerObservation(
        const std::array<double,3>& currPosn,
        const std::array<double,3>& prevSensePosn,
        const cote::DateTime& prevSenseDateTime,
        const cote::DateTime& currentDateTime,
        double distanceKm,
        double thresholdKm,
        uint32_t leadSatId,
        const std::vector<cote::Satellite>& satellites
    ) override {
        // Original bent-pipe logic: trigger when distance exceeds threshold
        return distanceKm >= thresholdKm;
    }

    void executeObservation(
        const std::vector<cote::Satellite>& satellites,
        std::map<uint32_t, cote::Sensor*>& satId2Sensor,
        std::map<uint32_t, double>& satId2ThresholdKm,
        double threshCoeff,
        const cote::DateTime& dateTime,
        cote::Log& log
    ) override {
        // Original bent-pipe logic: all satellites trigger sense simultaneously
        log.evnt(cote::LogLevel::INFO, dateTime.toString(), "trigger-time");
        for(size_t i = 0; i < satellites.size(); i++) {
            satId2Sensor[satellites.at(i).getID()]->triggerSense();
            satId2ThresholdKm[satellites.at(i).getID()] =
                threshCoeff * cote::util::calcAltitudeKm(satellites.at(i).getECIPosn());
        }
    }

    void updateFrameState(
        uint32_t leadSatId,
        const std::array<double,3>& currPosn,
        const cote::DateTime& dateTime,
        std::map<uint32_t, cote::Sensor*>& satId2Sensor
    ) override {
        // Bent-pipe strategy doesn't need frame state updates
        // All satellites always trigger together
    }

    std::string getStrategyName() const override {
        return "bent-pipe";
    }
};

#endif
