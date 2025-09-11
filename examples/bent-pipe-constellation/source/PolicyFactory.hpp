#ifndef POLICY_FACTORY_HPP
#define POLICY_FACTORY_HPP

#include <memory>
#include <string>
#include "SchedulingPolicy.hpp"
#include "RandomPolicy.hpp"
#include "FIFOPolicy.hpp"
#include "RoundRobinPolicy.hpp"
#include "ShortestJobFirstPolicy.hpp"
#include "ShortestRemainingTimePolicy.hpp"
#include "StickyPolicy.hpp"

class PolicyFactory {
public:
    static std::unique_ptr<SchedulingPolicy> createPolicy(const std::string& policyName) {
        if(policyName == "random") {
            return std::make_unique<RandomPolicy>();
        } else if(policyName == "fifo") {
            return std::make_unique<FIFOPolicy>();
        } else if(policyName == "roundrobin") {
            return std::make_unique<RoundRobinPolicy>();
        } else if(policyName == "sjf" || policyName == "shortestjobfirst") {
            return std::make_unique<ShortestJobFirstPolicy>();
        } else if(policyName == "srtf" || policyName == "shortestremainingtime") {
            return std::make_unique<ShortestRemainingTimePolicy>();
        } else if(policyName == "sticky" || policyName == "greedy") {
            return std::make_unique<StickyPolicy>();
        }
        // Default to sticky (original bent-pipe behavior)
        return std::make_unique<StickyPolicy>();
    }
};

#endif
