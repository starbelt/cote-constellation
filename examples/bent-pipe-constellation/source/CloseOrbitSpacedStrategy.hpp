#ifndef CLOSEORBITSPACEDSTRATEGY_HPP
#define CLOSEORBITSPACEDSTRATEGY_HPP

#include "SpacingStrategy.hpp"
#include <utilities.hpp>
#include <algorithm>  // for std::sort
#include <iomanip>    // for std::setfill, std::setw

class CloseOrbitSpacedStrategy : public SpacingStrategy {
public:
    CloseOrbitSpacedStrategy() = default;
    ~CloseOrbitSpacedStrategy() = default;

    // Strategy: Constant 25 orbital positions with variable cluster density
    // constellation.dat provides base spacing for 25 orbital positions
    // initialize() propagates additional satellites at each position:
    // - 25 sats:  25 positions × 1 sat  (identical to orbit-spaced, no re-phasing)
    // - 50 sats:  25 positions × 2 sats (propagate 1 extra at 6km)
    // - 100 sats: 25 positions × 4 sats (propagate 3 extras at 3km)
    // - 200 sats: 25 positions × 8 sats (propagate 7 extras at 1.5km)

    void initialize(std::vector<cote::Satellite>& satellites) {
        const size_t satCount = satellites.size();
        std::cout << "close-orbit-spaced: " << satCount << " satellites" << std::endl;
        
        // For satellite counts < 25: No clustering, use constellation.dat spacing
        // This means close-orbit-spaced behaves identically to orbit-spaced for small constellations
        if (satCount < 25) {
            std::cout << "  → " << satCount << " sats: no clustering (uses constellation.dat)" << std::endl;
            return;
        }
        
        // 25 sats: No clustering (baseline complete)
        if (satCount == 25) {
            std::cout << "  → 25 sats: baseline (no clustering)" << std::endl;
            return;
        }
        
        // Cluster all satellites
        // 50 sats:  25 clusters of 2 (base sats: 000, 002, 004, 006, ...)
        // 100 sats: 25 clusters of 4 (base sats: 000, 004, 008, 012, ...)
        // 200 sats: 25 clusters of 8 (base sats: 000, 008, 016, 024, ...)
        const double orbitalVelocity = 7.5;  // km/s (approximate LEO velocity)
        size_t clusterSize;
        double targetSeparationKm;
        
        if (satCount == 50) {
            clusterSize = 2;
            targetSeparationKm = 6.0;   // 6km spacing within cluster
        } else if (satCount == 100) {
            clusterSize = 4;
            targetSeparationKm = 3.0;   // 3km spacing within cluster
        } else {  // 200 sats
            clusterSize = 8;
            targetSeparationKm = 1.5;   // 1.5km spacing within cluster
        }
        
        const double timeOffsetSec = targetSeparationKm / orbitalVelocity;
        size_t clustersPositioned = 0;
        
        // Process each cluster
        for (size_t i = 0; i < satCount; i += clusterSize) {
            // Satellite i is the base/lead of this cluster
            cote::DateTime baseTime = satellites[i].getLocalTime();
            
            // Position the remaining satellites in this cluster behind the base
            for (size_t j = 1; j < clusterSize && (i + j) < satCount; j++) {
                cote::DateTime followerTime = baseTime;
                // Each follower is offset by j * timeOffsetSec behind the base
                advanceBySeconds(followerTime, j * timeOffsetSec);
                satellites[i + j].setLocalTime(followerTime);
            }
            clustersPositioned++;
        }
        
        std::cout << "  → Positioned " << clustersPositioned << " clusters of " << clusterSize 
                  << " satellites (" << targetSeparationKm << " km spacing)" << std::endl;
    }

private:
    // Helper function to advance a DateTime by a given number of seconds (in-place)
    static inline void advanceBySeconds(cote::DateTime& t, double dt) {
        long whole = static_cast<long>(std::floor(dt));
        long ns = static_cast<long>(std::llround((dt - whole) * 1e9));
        t.update(static_cast<uint8_t>(whole), static_cast<uint32_t>(ns));
    }

public:
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
        // Close-orbit-spaced logic: trigger when distance exceeds threshold
        // This combines the orbital distribution approach with cluster-based sensing
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
        // Close-orbit-spaced logic: all satellites in constellation trigger simultaneously
        // The orbital clusters are defined by the constellation configuration file
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
        // Close-orbit-spaced strategy uses simultaneous triggering
        // No special frame state management needed
    }

    std::string getStrategyName() const override {
        return "close-orbit-spaced";
    }
};

#endif
