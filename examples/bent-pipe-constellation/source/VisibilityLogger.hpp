// VisibilityLogger.hpp
//
// Minimal utility for visibility logging
//
// Written by GitHub Copilot
// Other contributors: None
//
// See the top-level LICENSE file for the license.

#ifndef VISIBILITY_LOGGER_HPP
#define VISIBILITY_LOGGER_HPP

#include <filesystem>
#include <fstream>
#include <string>
#include <map>
#include <cstdint>

class VisibilityLogger {
public:
  // Constructor - opens the log file
  VisibilityLogger(const std::filesystem::path& logDirectory);
  
  // Destructor - closes the log file
  ~VisibilityLogger();
  
  // Write a log entry
  void writeEntry(
    double simTimeSeconds,
    uint32_t SAT_ID,
    int inView,
    int connected,
    double bufferMB,
    double downloadedMB,
    int imageTaken,
    double latDeg,
    double lonDeg,
    const std::string& timestamp,
    double distanceKm,
    double elevationDeg
  );
  
  // Close the log file
  void close();

private:
  std::ofstream visibilityLog;
};

#endif // VISIBILITY_LOGGER_HPP
