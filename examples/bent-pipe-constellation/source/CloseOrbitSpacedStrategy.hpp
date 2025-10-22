#ifndef CLOSEORBITSPACEDSTRATEGY_HPP
#define CLOSEORBITSPACEDSTRATEGY_HPP

#include "SpacingStrategy.hpp"
#include <utilities.hpp>

class CloseOrbitSpacedStrategy : public SpacingStrategy {
public:
    CloseOrbitSpacedStrategy() = default;
    ~CloseOrbitSpacedStrategy() = default;

    // Strategy: Constant 50 orbital positions with variable cluster density
    // constellation.dat provides base spacing for 50 orbital positions (108 seconds)
    // initialize() propagates additional satellites at each position:
    // - 1 sat:    No clustering (copy of orbit_01.dat)
    // - 50 sats:  50 positions × 1 sat  (identical to orbit-spaced, no re-phasing)
    // - 100 sats: 50 positions × 2 sats (propagate 1 extra at 6km = 12km/2)
    // - 200 sats: 50 positions × 4 sats (propagate 3 extras at 3km = 12km/4)

    void initialize(std::vector<cote::Satellite>& satellites) {
        const size_t totalSats = satellites.size();
        
        // Special case: 1 satellite - no clustering needed
        if (totalSats == 1) {
            std::cout << "close-orbit-spaced: 1 satellite, no clustering" << std::endl;
            return;
        }
        
        // Calculate satellites per orbital position
        const size_t ORBITAL_POSITIONS = 50;
        const size_t satsPerPosition = totalSats / ORBITAL_POSITIONS;
        
        // Special case: 50 satellites - already correctly positioned, no re-phasing needed
        if (totalSats == 50) {
            std::cout << "close-orbit-spaced: 50 satellites = 50 positions × 1 sat (matches orbit-spaced)" << std::endl;
            return;
        }
        
        // Calculate spacing within clusters
        // Cluster footprint: 12 km constant
        // Spacing within cluster = 12km / satsPerPosition
        const double CLUSTER_FOOTPRINT_KM = 12.0;
        const double spacingWithinCluster_km = CLUSTER_FOOTPRINT_KM / static_cast<double>(satsPerPosition);
        
        // Orbital velocity: approximately 7.8 km/s at 550 km altitude
        const double ORBITAL_VELOCITY_KM_S = 7.8;
        const double spacingWithinCluster_sec = spacingWithinCluster_km / ORBITAL_VELOCITY_KM_S;
        
        std::cout << "close-orbit-spaced: " << totalSats << " satellites = " 
                  << ORBITAL_POSITIONS << " positions × " << satsPerPosition 
                  << " sats, spacing within cluster: " << spacingWithinCluster_km << " km ("
                  << spacingWithinCluster_sec << " sec)" << std::endl;
        
        // Re-phase satellites to create clusters
        // Satellites 0-(satsPerPosition-1) are at position 0
        // Satellites satsPerPosition-(2*satsPerPosition-1) are at position 1, etc.
        for (size_t pos = 0; pos < ORBITAL_POSITIONS; pos++) {
            for (size_t satInCluster = 1; satInCluster < satsPerPosition; satInCluster++) {
                size_t satIndex = pos * satsPerPosition + satInCluster;
                if (satIndex >= totalSats) break;
                
                // Get the lead satellite for this position (first in cluster)
                size_t leadSatIndex = pos * satsPerPosition;
                cote::DateTime leadTime = satellites.at(leadSatIndex).getLocalTime();
                
                // Advance by (satInCluster * spacingWithinCluster_sec) seconds
                double advanceSeconds = static_cast<double>(satInCluster) * spacingWithinCluster_sec;
                advanceBySeconds(leadTime, advanceSeconds);
                
                // Update satellite position and time
                satellites.at(satIndex).setLocalTime(leadTime);
            }
        }
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
