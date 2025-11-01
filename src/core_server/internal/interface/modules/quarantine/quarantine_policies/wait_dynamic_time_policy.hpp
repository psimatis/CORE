#pragma once

#include <algorithm>
#include <atomic>
#include <cassert>
#include <chrono>
#include <cstdint>
#include <list>
#include <mutex>
#include <ratio>
#include <utility>

#define QUILL_ROOT_LOGGER_ONLY
#include <quill/Quill.h>             // NOLINT
#include <quill/detail/LogMacros.h>  // NOLINT

#include "base_policy.hpp"
#include "core_server/internal/coordination/catalog.hpp"
#include "shared/datatypes/aliases/port_number.hpp"
#include "shared/datatypes/eventWrapper.hpp"
#include "shared/datatypes/value.hpp"
#include "shared/logging/setup.hpp"

namespace CORE::Internal::Interface::Module::Quarantine {

class WaitDynamicTimePolicy : public BasePolicy {
  std::mutex events_lock;
  std::list<Types::EventWrapper> events;

  std::chrono::duration<float> quarantine_time = std::chrono::duration<float>(0.0f);
  float avg_lateness = 0.0;
  float max_real_time_seen = 0.0;
  float alpha = 0.1;  // Smoothing factor for exponential moving average
  float SAFETY_MARGIN = 1.0;

  int drops = 0;
  int received_events = 0;
  int sent_events = 0;
  std::chrono::duration<float> time_to_wait;

  // Corresponds to the last time an event was sent
  Types::IntValue last_time_sent = Types::IntValue::create_lower_bound();

 public:
  WaitDynamicTimePolicy(Catalog& catalog, std::atomic<Types::PortNumber>& next_available_inproc_port, std::chrono::duration<float> time_to_wait)
      : BasePolicy(catalog, next_available_inproc_port), 
        quarantine_time(time_to_wait),
        time_to_wait(time_to_wait) {
    this->start();
  }

  ~WaitDynamicTimePolicy() { this->handle_destruction(); }

  void receive_event(Types::EventWrapper&& event) override {
    float lateness = 0.0;
    std::cout << "QUARANTINE RECEIVE: event time=" << event.get_primary_time().val << std::endl;
    received_events++;
    LOG_L3_BACKTRACE(
      "Received event with id {} and time {} in "
      "WaitDynamicTimePolicy::receive_event",
      event.get_unique_event_type_id(),
      event.get_primary_time().val);

    std::lock_guard<std::mutex> lock(events_lock);

    if (event.get_primary_time().val < last_time_sent.val) {
      std::cout << "QUARANTINE DROP: event time=" << event.get_primary_time().val << " < last_sent=" << last_time_sent.val << std::endl;
      drops++;
      LOG_L3_BACKTRACE(
        "Dropping event with id {} and time {} in "
        "WaitDynamicTimePolicy::receive_event due to time being before last time sent",
        event.get_unique_event_type_id(),
        event.get_primary_time().val);
      return;
    }
    if (static_cast<float>(event.get_primary_time().val) < max_real_time_seen) {
      lateness = max_real_time_seen - static_cast<float>(event.get_primary_time().val);
    }else {
      lateness = 0.0;
    }
    max_real_time_seen = std::max(max_real_time_seen, static_cast<float>(event.get_primary_time().val));

  avg_lateness = alpha * lateness + (1 - alpha) * avg_lateness;
  // Update quarantine_time as a chrono duration (seconds)
  quarantine_time = std::chrono::duration<float>(avg_lateness + SAFETY_MARGIN);
  quarantine_time = std::clamp(quarantine_time, std::chrono::duration<float>(1.0f), std::chrono::duration<float>(5.0f));  // Clamp between 1 and 5 seconds
  std::cout << "QUARANTINE TIME UPDATED: avg_lateness=" << avg_lateness << " quarantine_time=" << quarantine_time.count() << std::endl;

    events.insert(std::lower_bound(events.begin(), events.end(), event.get_primary_time().val, is_nanoseconds_after_existing_event), std::move(event));
    std::cout << "QUARANTINE SORTED: buffer size=" << events.size() << std::endl;
  }

 protected:
  /**
   * Tries to add received tuples to send queue according to specific policy
   */
  void try_add_tuples_to_send_queue() override {
    // std::cout << "QUARANTINE TRY SEND: buffer size=" << events.size() << std::endl;
    LOG_L3_BACKTRACE(
      "Trying to add tuples to send queue in "
      "WaitDynamicTimePolicy::try_add_tuples_to_send");

    std::lock_guard<std::mutex> lock(events_lock);
    auto now = std::chrono::system_clock::now();

    for (auto iter = events.begin(); iter != events.end();) {
      const Types::EventWrapper& event = *iter;
      auto duration = now - event.get_received_time();
      // compare duration (system_clock::duration) with quarantine_time (chrono::duration<float>) by casting quarantine_time
      if (duration > std::chrono::duration_cast<decltype(duration)>(quarantine_time)) {
        std::cout << "QUARANTINE SEND: event time=" << event.get_primary_time().val << std::endl;
        sent_events++;
        LOG_L3_BACKTRACE(
          "Adding event with id {} and time {} to send queue in "
          "WaitDynamicTimePolicy::try_add_tuples_to_send",
          event.get_unique_event_type_id(),
          event.get_primary_time().val);
        assert(event.get_primary_time().val >= last_time_sent.val && "Event time is not after last time sent");
        last_time_sent = event.get_primary_time();
        this->send_event_queue.enqueue(std::move(*iter));
        iter = events.erase(iter);
      } else {
        // If we couldn't remove the first event, stop trying
        return;
      }
    }
  }

  void force_add_tuples_to_send_queue() override {
    std::lock_guard<std::mutex> lock(events_lock);
    std::cout << "QUARANTINE FORCE SEND: flushing " << events.size() << " remaining events" << std::endl;
    for (auto iter = events.begin(); iter != events.end();) {
      std::cout << "QUARANTINE FORCE SEND EVENT: time=" << iter->get_primary_time().val << std::endl;
      sent_events++;
      this->send_event_queue.enqueue(std::move(*iter));
      iter = events.erase(iter);
    }
    std::cout << "Number of events RECEIVED by quarantine: " << received_events << std::endl;
    std::cout << "Number of events SENT by quarantine: " << sent_events << std::endl;
    std::cout << "Number of events DROPPED by quarantine: " << drops << std::endl;
  }

 private:
  bool static is_nanoseconds_after_existing_event(const Types::EventWrapper& event_in_list, int64_t event_to_insert_time_nanoseconds) {
    return event_to_insert_time_nanoseconds >= event_in_list.get_primary_time().val;
  }
};
}  // namespace CORE::Internal::Interface::Module::Quarantine
