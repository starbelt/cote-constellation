#ifndef FRAMESPACEDSTRATEGY_HPP
#define FRAMESPACEDSTRATEGY_HPP

#include "SpacingStrategy.hpp"
#include <utilities.hpp>

class FrameSpacedStrategy : public SpacingStrategy {
private:
    size_t frameCount = 0;  // Track which satellite should observe

public:
    FrameSpacedStrategy() = default;
    ~FrameSpacedStrategy() = default;

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
        // Frame-spaced logic: trigger when distance exceeds threshold
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
        // Frame-spaced logic: only trigger ONE satellite per observation event
        size_t satIndex = frameCount % satellites.size();
        
        log.evnt(cote::LogLevel::INFO, dateTime.toString(), "trigger-time");
        
        // Trigger only the current satellite in the rotation
        satId2Sensor[satellites.at(satIndex).getID()]->triggerSense();
        satId2ThresholdKm[satellites.at(satIndex).getID()] =
            threshCoeff * cote::util::calcAltitudeKm(satellites.at(satIndex).getECIPosn());
        
        frameCount++;  // Move to next satellite for next trigger
    }

    void updateFrameState(
        uint32_t leadSatId,
        const std::array<double,3>& currPosn,
        const cote::DateTime& dateTime,
        std::map<uint32_t, cote::Sensor*>& satId2Sensor
    ) override {
        // Frame-spaced strategy: no special state updates needed
        // Rotation is handled directly in executeObservation
    }

    std::string getStrategyName() const override {
        return "frame-spaced";
    }
};

#endif