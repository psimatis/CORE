#include <chrono>
#include <exception>
#include <iostream>
#include <memory>
#include <ostream>
#include <string>
#include <thread>
#include <tracy/Tracy.hpp>
#include <utility>
#include <vector>

#include "core_client/client.hpp"
#include "core_server/library/server.hpp"
#include "core_server/library/server_config.hpp"
#include "shared/datatypes/catalog/stream_info.hpp"
#include "shared/datatypes/event.hpp"

using namespace CORE;

int main(int argc, char** argv) {
  FrameMark;
  try {
    // Manual argument parsing for --options since ServerConfig parsing is broken
    std::string manual_options_path = "";
    for (int i = 0; i < argc - 1; i++) {
      if (std::string(argv[i]) == "--options") {
        manual_options_path = argv[i + 1];
        std::cout << "MANUAL PARSING: Found --options, path=" << manual_options_path << std::endl;
        break;
      }
    }
    std::cout << "MANUAL PARSING: Final options path='" << manual_options_path << "' (empty=" << manual_options_path.empty() << ")" << std::endl;
    
    Library::ServerConfig server_config = Library::ServerConfig::from_args(argc, argv);
    Library::OfflineServer server{std::move(server_config)};
    Client client{"tcp://localhost", server.get_server_config().get_fixed_ports().router};

    std::string query_string = client.read_file(
      server.get_server_config().get_query_path());
    std::string declaration_string = client.read_file(
      server.get_server_config().get_declaration_path());

    Types::StreamInfo stream_info = client.declare_stream(declaration_string);

    // Use manual argument parsing for quarantine options
    if (!manual_options_path.empty()) {
      std::cout << "LOADING QUARANTINE OPTIONS FROM: " << manual_options_path << std::endl;
      std::string option_declaration_string = client.read_file(manual_options_path);
      std::cout << "QUARANTINE OPTIONS CONTENT: " << option_declaration_string << std::endl;
      client.declare_option(option_declaration_string);
      std::cout << "QUARANTINE OPTIONS LOADED SUCCESSFULLY" << std::endl;
    } else {
      std::cout << "NO --options ARGUMENT PROVIDED - USING DEFAULT DIRECT POLICY (NO QUARANTINE)" << std::endl;
    }

    std::cout << "Query: " << query_string << std::endl;

    client.add_query(std::move(query_string));
    std::vector<Types::Event> events = std::move(
      stream_info.get_events_from_csv(server.get_server_config().get_csv_data_path()));
    std::vector<std::shared_ptr<Types::Event>> events_to_send;
    for (Types::Event event : events) {
      events_to_send.push_back(std::make_shared<Types::Event>(event));
    }

    std::cout << "Read events " << events.size() << std::endl;
    FrameMark;

    // Send events one by one with delays to trigger temporal violations
    std::cout << "STREAMING MODE: Sending events with 2-second delays..." << std::endl;
    for (size_t i = 0; i < events_to_send.size(); i++) {
      std::cout << "STREAMING: Sending event " << i << std::endl;
      
      std::vector<std::shared_ptr<Types::Event>> single_event = {events_to_send[i]};
      server.receive_stream({0, std::move(single_event)});
      
      // Wait 2 seconds before sending next event (except for last one)
      if (i < events_to_send.size() - 1) {
        std::this_thread::sleep_for(std::chrono::seconds(2));
      }
    }
    
    std::cout << "STREAMING: All events sent, waiting for final processing..." << std::endl;
    std::this_thread::sleep_for(std::chrono::seconds(3));

    return 0;
  }

  catch (std::exception& e) {
    std::cout << "Exception: " << e.what() << std::endl;
    return 1;
  }
}