// Sensor.cpp
// Sensor class implementation file
//
// Written by Bradley Denby
// Other contributors: None
//
// See the top-level LICENSE file for the license.

// Standard library
#include <array>         // array
#include <cstdint>       // uint32_t, uint64_t
#include <utility>       // move

// comsim
#include <DateTime.hpp>  // DateTime
#include <Log.hpp>       // Log
#include <LogLevel.hpp>  // LogLevel
#include <Sensor.hpp>    // Sensor

namespace cote {
  Sensor::Sensor(
   const std::array<double,3>& eciPosn, const DateTime* const globalTime,
   const uint32_t& id, Log* const log
  ) : senseTrigger(false), bitsBuffered(0), bitsPerSense(0),
      maxBufferCapacity(UINT64_MAX), totalBitsLost(0), // Default to unlimited buffer
      prevSensePosn(eciPosn), prevSenseDateTime(*globalTime), eciPosn(eciPosn),
      globalTime(globalTime), id(id), log(log) {}

  Sensor::Sensor(const Sensor& sensor) :
   senseTrigger(sensor.getSenseTrigger()),
   bitsBuffered(sensor.getBitsBuffered()),
   bitsPerSense(sensor.getBitsPerSense()),
   maxBufferCapacity(sensor.getMaxBufferCapacity()),
   totalBitsLost(sensor.totalBitsLost),
   prevSensePosn(sensor.getPrevSensePosn()),
   prevSenseDateTime(sensor.getPrevSenseDateTime()),
   eciPosn(sensor.getECIPosn()), globalTime(sensor.getGlobalTime()),
   id(sensor.getID()), log(sensor.getLog()) {}

  Sensor::Sensor(Sensor&& sensor) :
   senseTrigger(sensor.senseTrigger), bitsBuffered(sensor.bitsBuffered),
   bitsPerSense(sensor.bitsPerSense), maxBufferCapacity(sensor.maxBufferCapacity),
   totalBitsLost(sensor.totalBitsLost), prevSensePosn(sensor.prevSensePosn),
   prevSenseDateTime(sensor.prevSenseDateTime), eciPosn(sensor.eciPosn),
   globalTime(sensor.globalTime), id(sensor.id), log(sensor.log) {
    sensor.globalTime = NULL;
    sensor.log = NULL;
  }

  Sensor::~Sensor() {
    this->globalTime = NULL;
    this->log = NULL;
  }

  Sensor& Sensor::operator=(const Sensor& sensor) {
    Sensor temp(sensor);
    *this = std::move(temp);
    return *this;
  }

  Sensor& Sensor::operator=(Sensor&& sensor) {
    this->senseTrigger      = sensor.senseTrigger;
    this->bitsBuffered      = sensor.bitsBuffered;
    this->bitsPerSense      = sensor.bitsPerSense;
    this->maxBufferCapacity = sensor.maxBufferCapacity;
    this->totalBitsLost     = sensor.totalBitsLost;
    this->prevSensePosn     = sensor.prevSensePosn;
    this->prevSenseDateTime = sensor.prevSenseDateTime;
    this->eciPosn           = sensor.eciPosn;
    this->globalTime        = sensor.globalTime;
    this->id                = sensor.id;
    this->log               = sensor.log;
    sensor.globalTime       = NULL;
    sensor.log              = NULL;
    return *this;
  }

  Sensor* Sensor::clone() const {
    return new Sensor(*this);
  }

  bool Sensor::getSenseTrigger() const {
    return this->senseTrigger;
  }

  uint64_t Sensor::getBitsBuffered() const {
    return this->bitsBuffered;
  }

  uint64_t Sensor::getBitsPerSense() const {
    return this->bitsPerSense;
  }

  uint64_t Sensor::getMaxBufferCapacity() const {
    return this->maxBufferCapacity;
  }

  uint64_t Sensor::getTotalBitsLost() const {
    return this->totalBitsLost;
  }

  std::array<double,3> Sensor::getPrevSensePosn() const {
    return this->prevSensePosn;
  }

  DateTime Sensor::getPrevSenseDateTime() const {
    return this->prevSenseDateTime;
  }

  std::array<double,3> Sensor::getECIPosn() const {
    return this->eciPosn;
  }

  const DateTime* Sensor::getGlobalTime() const {
    return this->globalTime;
  }

  uint32_t Sensor::getID() const {
    return this->id;
  }

  Log* Sensor::getLog() const {
    return this->log;
  }

  void Sensor::triggerSense() {
    this->senseTrigger = true;
  }

  uint64_t Sensor::drainBuffer(const uint64_t& bits) {
    if(this->bitsBuffered>=bits) {
      this->bitsBuffered -= bits;
      return bits;
    } else {
      uint64_t drainedBits = this->bitsBuffered;
      this->bitsBuffered = 0;
      return drainedBits;
    }
  }

  void Sensor::setBitsPerSense(const uint64_t& bits) {
    this->bitsPerSense = bits;
  }

  void Sensor::setMaxBufferCapacity(const uint64_t& capacityBits) {
    this->maxBufferCapacity = capacityBits;
  }

  void Sensor::setECIPosn(const std::array<double,3>& eciPosn) {
    this->eciPosn = eciPosn;
  }

  void Sensor::update(const uint32_t& nanosecond) {
    // **It is expected that this->globalTime has already been updated**
    // **It is expected that this->eciPosn has already been updated**
    if(this->senseTrigger) {
      // Add new data, but cap at maximum buffer capacity
      uint64_t newTotal = this->bitsBuffered + this->bitsPerSense;
      if(newTotal > this->maxBufferCapacity) {
        // Buffer overflow - data is lost!
        this->bitsBuffered = this->maxBufferCapacity;
        this->totalBitsLost += this->bitsPerSense; // Track cumulative loss
        // Log cumulative overflow
        if(this->log != NULL) {
          this->log->meas(
            cote::LogLevel::INFO,
            DateTime(*(this->globalTime)).toString(),
            std::string("buffer-overflow-sat-") + std::to_string(this->id),
            std::to_string(static_cast<double>(this->totalBitsLost) / (8.0 * 1024.0 * 1024.0)) // Cumulative lost data in MB
          );
        }
      } else {
        this->bitsBuffered = newTotal;
      }
      this->setPrevSensePosnDateTime(
       this->eciPosn, DateTime(*(this->globalTime))
      );
      this->senseTrigger      = false;
    }
  }

  void Sensor::update(const uint8_t& second, const uint32_t& nanosecond) {
    // **It is expected that this->globalTime has already been updated**
    // **It is expected that this->eciPosn has already been updated**
    this->update(nanosecond);
  }

  void Sensor::update(
   const uint8_t& minute, const uint8_t& second, const uint32_t& nanosecond
  ) {
    // **It is expected that this->globalTime has already been updated**
    // **It is expected that this->eciPosn has already been updated**
    this->update(nanosecond);
  }

  void Sensor::update(
   const uint8_t& hour, const uint8_t& minute, const uint8_t& second,
   const uint32_t& nanosecond
  ) {
    // **It is expected that this->globalTime has already been updated**
    // **It is expected that this->eciPosn has already been updated**
    this->update(nanosecond);
  }

  void Sensor::setPrevSensePosnDateTime(
   const std::array<double,3>& eciPosn, const DateTime& dateTime
  ) {
    this->prevSensePosn = eciPosn;
    this->prevSenseDateTime = dateTime;
  }
}
