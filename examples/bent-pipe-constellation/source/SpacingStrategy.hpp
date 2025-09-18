#ifndef SPACINGSTRATEGY_HPP
#define SPACINGSTRATEGY_HPP

// Standard library
#include <array>
#include <cstdint>
#include <map>
#include <vector>

// cote
#include <DateTime.hpp>
#include <Log.hpp>
#include <Satellite.hpp>
#include <Sensor.hpp>

class SpacingStrategy {
public:
    virtual ~SpacingStrategy() = default;

    // Check if satellites should trigger observation based on distance threshold
    virtual bool shouldTriggerObservation(
        const std::array<double,3>& currPosn,
        const std::array<double,3>& prevSensePosn,
        const cote::DateTime& prevSenseDateTime,
        const cote::DateTime& currentDateTime,
        double distanceKm,
        double thresholdKm,
        uint32_t leadSatId,
        const std::vector<cote::Satellite>& satellites
    ) = 0;

    // Execute observation trigger for satellites based on strategy
    virtual void executeObservation(
        const std::vector<cote::Satellite>& satellites,
        std::map<uint32_t, cote::Sensor*>& satId2Sensor,
        std::map<uint32_t, double>& satId2ThresholdKm,
        double threshCoeff,
        const cote::DateTime& dateTime,
        cote::Log& log
    ) = 0;

    // Update any internal state (frame counters, etc.)
    virtual void updateFrameState(
        uint32_t leadSatId,
        const std::array<double,3>& currPosn,
        const cote::DateTime& dateTime,
        std::map<uint32_t, cote::Sensor*>& satId2Sensor
    ) = 0;

    // Get strategy name for logging
    virtual std::string getStrategyName() const = 0;

protected:
    // Helper function for calculating threshold
    double calculateThreshold(double threshCoeff, const std::array<double,3>& eciPosn) const;
};

#endif
