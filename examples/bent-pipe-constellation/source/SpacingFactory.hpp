#ifndef SPACINGFACTORY_HPP
#define SPACINGFACTORY_HPP

#include "SpacingStrategy.hpp"
#include "CloseSpacedStrategy.hpp"
#include "FrameSpacedStrategy.hpp"
#include "OrbitSpacedStrategy.hpp"

#include <memory>
#include <string>
#include <stdexcept>

class SpacingFactory {
public:
    static std::unique_ptr<SpacingStrategy> createStrategy(const std::string& strategyName) {
        if (strategyName == "bent-pipe" || strategyName == "bentpipe" || 
            strategyName == "close-spaced" || strategyName == "close" || strategyName == "closed") {
            return std::make_unique<CloseSpacedStrategy>();
        } else if (strategyName == "frame-spaced" || strategyName == "frame") {
            return std::make_unique<FrameSpacedStrategy>();
        } else if (strategyName == "orbit-spaced" || strategyName == "orbit") {
            return std::make_unique<OrbitSpacedStrategy>();
        } else {
            throw std::invalid_argument("Unknown spacing strategy: " + strategyName + 
                ". Valid options: bent-pipe, close-spaced, frame-spaced, orbit-spaced");
        }
    }

    static std::string getAvailableStrategies() {
        return "bent-pipe, close-spaced, frame-spaced, orbit-spaced";
    }
};

#endif
