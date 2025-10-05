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

class WaitFixedTimePolicy : public BasePolicy {
  std::mutex events_lock;
  std::list<Types::EventWrapper> events;
  std::chrono::duration<int64_t, std::nano> time_to_wait;

  // Corresponds to the last time an event was sent
  Types::IntValue last_time_sent = Types::IntValue::create_lower_bound();

 public:
  WaitFixedTimePolicy(Catalog& catalog, std::atomic<Types::PortNumber>& next_available_inproc_port, std::chrono::duration<int64_t, std::nano> time_to_wait)
      : BasePolicy(catalog, next_available_inproc_port), time_to_wait(time_to_wait) {
    this->start();
  }

  ~WaitFixedTimePolicy() { this->handle_destruction(); }

  void receive_event(Types::EventWrapper&& event) override {
    std::cout << "QUARANTINE RECEIVE: event time=" << event.get_primary_time().val << std::endl;
    LOG_L3_BACKTRACE(
      "Received event with id {} and time {} in "
      "WaitFixedTimePolicy::receive_event",
      event.get_unique_event_type_id(),
      event.get_primary_time().val);

    std::lock_guard<std::mutex> lock(events_lock);

    if (event.get_primary_time().val < last_time_sent.val) {
      std::cout << "QUARANTINE DROP: event time=" << event.get_primary_time().val << " < last_sent=" << last_time_sent.val << std::endl;
      LOG_L3_BACKTRACE(
        "Dropping event with id {} and time {} in "
        "WaitFixedTimePolicy::receive_event due to time being before last time sent",
        event.get_unique_event_type_id(),
        event.get_primary_time().val);
      return;
    }

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
      "WaitFixedTimePolicy::try_add_tuples_to_send");

    std::lock_guard<std::mutex> lock(events_lock);
    auto now = std::chrono::system_clock::now();

    for (auto iter = events.begin(); iter != events.end();) {
      const Types::EventWrapper& event = *iter;
      auto duration = now - event.get_received_time();
      if (duration > time_to_wait) {
        std::cout << "QUARANTINE SEND: event time=" << event.get_primary_time().val << std::endl;
        LOG_L3_BACKTRACE(
          "Adding event with id {} and time {} to send queue in "
          "WaitFixedTimePolicy::try_add_tuples_to_send",
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
      this->send_event_queue.enqueue(std::move(*iter));
      iter = events.erase(iter);
    }
  }

 private:
  bool static is_nanoseconds_after_existing_event(const Types::EventWrapper& event_in_list, int64_t event_to_insert_time_nanoseconds) {
    return event_to_insert_time_nanoseconds >= event_in_list.get_primary_time().val;
  }
};
}  // namespace CORE::Internal::Interface::Module::Quarantine
