# GCP VM Manager API

A FastAPI-based service for managing Google Cloud Platform (GCP) virtual machines through a REST API. This service allows you to start, stop, suspend, and resume VMs via HTTP requests, with real-time status updates using Server-Sent Events (SSE).

## Features

- 🚀 Start, stop, suspend, and resume GCP VMs via HTTP requests
- 🔍 Get real-time VM status information
- 📊 Real-time operation progress using Server-Sent Events (SSE)
- 📝 Detailed operation logging with year/month organization
- 🔄 VM zone auto-detection with intelligent caching
- 🔒 Restricted operations (stop/suspend) for selected VMs only
- 🧪 Comprehensive test suite

## Architecture Overview

This application consists of several modules that work together:

- **API Layer**: FastAPI-based HTTP endpoints 
- **Operations Layer**: Handlers for VM operations
- **Caching Layer**: Intelligent VM zone caching to minimize GCP API calls
- **Logging Layer**: Detailed operation logging with CSV export
- **Utility Layer**: Helper functions for various tasks

The server leverages the `gcloud` command-line tool to perform operations, meaning it requires minimal IAM permissions and works with standard Google Cloud authentication.

## Prerequisites

- Python 3.8+
- Google Cloud SDK (`gcloud`) installed and configured
- GCP project with Compute Engine VMs
- Appropriate permissions to manage VMs

## Quick Start

1. Clone this repository
2. Install dependencies: `pip install -r requirements.txt`
3. Configure `.env` file (see Configuration section)
4. Start the server: `uvicorn fastserver:app --reload`
5. Access API at http://127.0.0.1:8000

## API Endpoints

### Main Endpoint: `/gcp-action/`

Manages VM operations with the following parameters:

- `vmname` (required): Name of the VM to operate on
- `operation`: Operation to perform (default: "status")
  - `status`: Get VM state
  - `start`: Power on VM
  - `stop`: Power off VM (restricted)
  - `suspend`: Suspend VM (restricted)
  - `resume`: Resume suspended VM
- `zone`: GCP zone (optional - will be auto-detected if not provided)
- `format`: Response format (default: "sse")
  - `sse`: Real-time updates via Server-Sent Events
  - `json`: Single JSON response

#### Examples:
Get VM status with real-time updates
GET /gcp-action/?vmname=my-instance-name
Start a VM with JSON response
GET /gcp-action/?vmname=my-instance-name&operation=start&format=json
Stop a VM in a specific zone
GET /gcp-action/?vmname=my-instance-name&operation=stop&zone=us-east4-a


### Health Check: `/health`

Returns service health status and configuration information.

### API Documentation: `/api-docs`

Returns detailed API documentation in JSON format.

## Installation

### 1. Clone the repository

```bash
git clone https://github.com/username/gcp-vm-manager.git
cd gcp-vm-manager
```

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

Required packages:
- fastapi
- uvicorn
- python-dotenv
- sse-starlette
- rich (for test runner)

### 3. Configure Google Cloud SDK

This application requires the `gcloud` command-line tool to be installed and authenticated.

#### For local development:

```bash
# Install Google Cloud SDK (if not already installed)
# For macOS:
brew install --cask google-cloud-sdk

# For Linux:
# See: https://cloud.google.com/sdk/docs/install

# Initialize and authenticate
gcloud init
# Follow prompts to select your project and authenticate
```

#### For production environments:

In production environments like GCP Compute Engine or GKE, the service can use the default service account credentials. Make sure the service account has the required permissions to manage VMs.

## Configuration

### Environment Variables

Create a `.env` file in the root directory with the following variables:

VMs allowed for restricted operations (stop, suspend)
ALLOWED_VMS=vm1,vm2,vm3
Operations that are restricted to allowed VMs list
RESTRICTED_OPERATIONS=stop,suspend
Default zone (optional - will be used if no zone is provided and VM not found in cache)
DEFAULT_ZONE=us-central1-a
Cache settings
CACHE_MAX_AGE_HOURS=1

### Example .env file:

Allow these VMs to be stopped or suspended
ALLOWED_VMS=guedfocnlq03,guedfocdsml01,guedfocwqa82
Restrict these operations to the whitelist
RESTRICTED_OPERATIONS=stop,suspend
Default zone if none specified
DEFAULT_ZONE=us-east4-a
Cache refresh interval
CACHE_MAX_AGE_HOURS=1


### VM Name Aliases

The system supports vanity names/aliases for VMs. You can configure these in `vm_name_utils.py`:

```python
# Mapping vanity names to actual hostnames
VANITY_TO_HOSTNAME = {
    "nlq": "guedfocnlq03",
    "py-server": "guedfocdsml01",
}
```

## Running the Server

### Development Mode

```bash
uvicorn fastserver:app --reload
```

This starts the server in development mode with auto-reload on port 8000.

### Production Mode

```bash
uvicorn fastserver:app --host 0.0.0.0 --port 8000
```

For production deployments, consider using Gunicorn with Uvicorn workers:

```bash
gunicorn -w 4 -k uvicorn.workers.UvicornWorker fastserver:app
```

### Docker (optional)

```bash
docker build -t gcp-vm-manager .
docker run -p 8000:8000 --env-file .env gcp-vm-manager
```


# README Part 3: Module Breakdown


## Core Modules

### `fastserver.py` - Main Application Entry Point

This is the main FastAPI application that defines the endpoints and orchestrates the components.

Key components:
- FastAPI application setup with CORS middleware
- Lifespan context manager for startup/shutdown events
- API endpoints definition
- Error handling

Important functions:
- `lifespan(app)`: Manages application startup/shutdown events
- `handle_vm_operation()`: Main endpoint handler for VM operations
- `health_check()`: Health check endpoint

### `vm_operations_handler.py` - VM Operations Logic

Handles the execution of VM operations and streaming of results.

Key functions:
- `execute_vm_operation()`: Executes operations with SSE streaming
- `execute_operation_json()`: Executes operations with JSON response
- `is_vm_allowed_for_operation()`: Checks if a VM is allowed for restricted operations
- `map_vanity_to_hostname()`: Maps vanity names to actual hostnames

### `vm_cache.py` - VM Zone Caching

Implements intelligent caching of VM zone information to minimize GCP API calls.

Key features:
- Thread-safe caching with periodic refresh
- Persistent storage with pickle
- Background refresh task

Important functions:
- `initialize()`: Initializes the cache on startup
- `update_cache()`: Refreshes the VM zone cache
- `get_vm_zone()`: Gets a VM's zone from the cache
- `_periodic_refresh()`: Background task for cache refresh

### `operation_logger.py` - Operation Logging

Handles logging VM operations to CSV files organized by year/month.

Key features:
- Organized logging structure by year/month
- CSV format for easy analysis
- Detailed operation logging

Important functions:
- `log_operation()`: Logs an operation to the appropriate CSV file
- `get_recent_operations()`: Retrieves most recent operations

### `gcp_commands.py` - GCP Command Execution

Handles building and executing gcloud commands.

Key function:
- `build_gcloud_command()`: Constructs appropriate gcloud command
- `execute_command()`: Executes the command with output handling

### `sse_utils.py` - Server-Sent Events Utilities

Provides utilities for streaming updates to clients using Server-Sent Events.

Key components:
- `SSEEvent` class: Formats events according to SSE protocol
- `get_sse_response()`: Creates streaming response for SSE

### `vm_name_utils.py` - VM Name Utilities

Handles VM name mapping and processing.

Key functions:
- `map_vanity_to_hostname()`: Maps vanity names to actual hostnames
- `get_vanity_name()`: Gets the vanity name for a VM if available

### `vm_scanner.py` - VM Discovery

Handles scanning GCP zones for VMs.

Key function:
- `scan_zones_for_vms()`: Discovers VMs across multiple zones

### `zone_manager.py` - Zone Management

Handles GCP zone discovery and management.

Key function:
- `get_all_zones()`: Retrieves all available zones
- `filter_zones()`: Filters zones by region pattern

### `logger_config.py` - Logging Configuration

Configures application logging with year/month directory structure.

Key function:
- `setup_logging()`: Sets up loggers with appropriate handlers


# README Part 4: Testing

```markdown
## Testing

The project includes a comprehensive test suite for API testing.

### Test Suite Features

- Health endpoint testing
- VM status operations testing
- VM start operations testing (requires VM in TERMINATED state)
- VM resume operations testing (requires VM in SUSPENDED state)
- Interactive mode to prepare VMs in the right state
- Detailed test reports

### Test Configuration

Create a `.env` file in the `tests` directory:

```
# API Test Configuration
API_URL=http://127.0.0.1:8000

# VM for testing start/stop operations (should be in TERMINATED state)
START_TEST_VM=your-vm-name

# VM for testing resume/suspend operations (should be in SUSPENDED state)
RESUME_TEST_VM=your-suspended-vm

# Optional zone - will be auto-detected if not specified
# TEST_ZONE=us-east4-a

## Core Modules

### `fastserver.py` - Main Application Entry Point

This is the main FastAPI application that defines the endpoints and orchestrates the components.

Key components:
- FastAPI application setup with CORS middleware
- Lifespan context manager for startup/shutdown events
- API endpoints definition
- Error handling

Important functions:
- `lifespan(app)`: Manages application startup/shutdown events
- `handle_vm_operation()`: Main endpoint handler for VM operations
- `health_check()`: Health check endpoint

### `vm_operations_handler.py` - VM Operations Logic

Handles the execution of VM operations and streaming of results.

Key functions:
- `execute_vm_operation()`: Executes operations with SSE streaming
- `execute_operation_json()`: Executes operations with JSON response
- `is_vm_allowed_for_operation()`: Checks if a VM is allowed for restricted operations
- `map_vanity_to_hostname()`: Maps vanity names to actual hostnames

### `vm_cache.py` - VM Zone Caching

Implements intelligent caching of VM zone information to minimize GCP API calls.

Key features:
- Thread-safe caching with periodic refresh
- Persistent storage with pickle
- Background refresh task

Important functions:
- `initialize()`: Initializes the cache on startup
- `update_cache()`: Refreshes the VM zone cache
- `get_vm_zone()`: Gets a VM's zone from the cache
- `_periodic_refresh()`: Background task for cache refresh

### `operation_logger.py` - Operation Logging

Handles logging VM operations to CSV files organized by year/month.

Key features:
- Organized logging structure by year/month
- CSV format for easy analysis
- Detailed operation logging

Important functions:
- `log_operation()`: Logs an operation to the appropriate CSV file
- `get_recent_operations()`: Retrieves most recent operations

### `gcp_commands.py` - GCP Command Execution

Handles building and executing gcloud commands.

Key function:
- `build_gcloud_command()`: Constructs appropriate gcloud command
- `execute_command()`: Executes the command with output handling

### `sse_utils.py` - Server-Sent Events Utilities

Provides utilities for streaming updates to clients using Server-Sent Events.

Key components:
- `SSEEvent` class: Formats events according to SSE protocol
- `get_sse_response()`: Creates streaming response for SSE

### `vm_name_utils.py` - VM Name Utilities

Handles VM name mapping and processing.

Key functions:
- `map_vanity_to_hostname()`: Maps vanity names to actual hostnames
- `get_vanity_name()`: Gets the vanity name for a VM if available

### `vm_scanner.py` - VM Discovery

Handles scanning GCP zones for VMs.

Key function:
- `scan_zones_for_vms()`: Discovers VMs across multiple zones

### `zone_manager.py` - Zone Management

Handles GCP zone discovery and management.

Key function:
- `get_all_zones()`: Retrieves all available zones
- `filter_zones()`: Filters zones by region pattern

### `logger_config.py` - Logging Configuration

Configures application logging with year/month directory structure.

Key function:
- `setup_logging()`: Sets up loggers with appropriate handlers

## Testing

The project includes a comprehensive test suite for API testing.

### Test Suite Features

- Health endpoint testing
- VM status operations testing
- VM start operations testing (requires VM in TERMINATED state)
- VM resume operations testing (requires VM in SUSPENDED state)
- Interactive mode to prepare VMs in the right state
- Detailed test reports

### Test Configuration

Create a `.env` file in the `tests` directory:

API Test Configuration
API_URL=http://127.0.0.1:8000
VM for testing start/stop operations (should be in TERMINATED state)
START_TEST_VM=your-vm-name
VM for testing resume/suspend operations (should be in SUSPENDED state)
RESUME_TEST_VM=your-suspended-vm
Optional zone - will be auto-detected if not specified
TEST_ZONE=us-east4-a


### Running Tests

Basic usage:

```bash
cd tests
python test_api.py
```

Command-line options:

```bash
# Specify API URL
python test_api.py --url http://your-server:8000

# Specify test VMs
python test_api.py --start-vm your-vm --resume-vm your-suspended-vm

# Specify zone
python test_api.py --zone us-east4-a

# Silent mode (minimal output)
python test_api.py --silent

# Non-interactive mode (for CI/CD)
python test_api.py --non-interactive
```

### Test Reports

The test suite generates two report formats:

1. Text report: `test_logs/vm_api_test_report_YYYYMMDD_HHMMSS.txt`
2. CSV file: `test_logs/vm_api_test_report_YYYYMMDD_HHMMSS.csv`

These reports include detailed information about each test's success/failure status, messages, and details.

### Important Test Module Functions

In `test_api.py`:

- `start_test_suite()`: Main entry point for test execution
- `check_vm_states()`: Verifies VMs are in the correct state before testing
- `test_health_endpoint()`: Tests the health endpoint
- `test_vm_status()`: Tests getting VM status
- `test_start_operation()`: Tests starting a VM
- `test_resume_operation()`: Tests resuming a VM
- `generate_report()`: Generates detailed test reports/127.0.0.1:8000/health" | jq .
```

Response:
```json
{
  "status": "healthy",
  "server_version": "2.0.0",
  "cache_status": {
    "last_update": "2025-05-06T09:31:28.909005",
    "cached_vms": 276,
    "age_minutes": 15.2,
    "refresh_scheduled_in_minutes": 44.8,
    "refresh_active": true
  },
  "supported_operations": {
    "status": "Available for all VMs",
    "start": "Available for all VMs",
    "stop": "Restricted to whitelisted VMs",
    "suspend": "Restricted to whitelisted VMs",
    "resume": "Available for all VMs"
  },
  "timestamp": "2025-05-06T09:46:46.549473"
}
```

## Troubleshooting

### Common Issues

#### VM Not Found in Cache

If you see an error like "VM not found in any zone":

1. Check if the VM exists in the GCP project
2. Try providing the zone explicitly in the request
3. Wait for the cache to refresh (happens every hour by default)
4. Manually trigger a cache refresh by restarting the service

#### Authentication Errors

If you see authentication errors:

1. Verify `gcloud` is properly authenticated
2. Run `gcloud auth login` to refresh credentials
3. Check that the service account has the required permissions

#### Restricted Operation Errors

If you see "Operation not allowed" errors:

1. Verify the VM is in the `ALLOWED_VMS` list in the .env file
2. Restart the service after updating the .env file

### Logging and Debugging

Logs are stored in the following locations:

- Application logs: `logs/YYYY/MM-Month/gcp_vm_operations.log`
- Operation logs: `logs/operations/YYYY/operations_YYYY_MM.csv`
- Test logs: `tests/test_logs/`

To increase logging verbosity, modify `logger_config.py` to set the log level to DEBUG.

## Security Considerations

- This service does not implement authentication/authorization - use API Gateway or reverse proxy for this
- Restricted operations (stop/suspend) are limited to whitelisted VMs
- Consider running in a private network or with firewall rules in production
- Use HTTPS in production to protect data in transit
```

## Usage Examples

### Get VM Status

Using cURL:

```bash
# SSE format (streaming)
curl "http://127.0.0.1:8000/gcp-action/?vmname=my-instance"

# JSON format
curl "http://127.0.0.1:8000/gcp-action/?vmname=my-instance&format=json" | jq .
```

Response (JSON format):
```json
{
  "status": "success",
  "data": {
    "name": "my-instance",
    "status": "RUNNING",
    "zone": "us-central1-a",
    "machineType": "e2-standard-4",
    "networkIP": "10.128.0.2"
  }
}
```

### Start a VM

```bash
curl "http://127.0.0.1:8000/gcp-action/?vmname=my-instance&operation=start&format=json"
```

Response:
```json
{
  "status": "success",
  "message": "VM my-instance started successfully."
}
```

### Stop a VM (Restricted Operation)

```bash
curl "http://127.0.0.1:8000/gcp-action/?vmname=allowed-vm&operation=stop&format=json"
```

Response for an allowed VM:
```json
{
  "status": "success",
  "message": "VM allowed-vm stopped successfully."
}
```

Response for a non-allowed VM:
```json
{
  "detail": "Operation 'stop' is not allowed for VM 'non-allowed-vm'. Only allowed for: vm1, vm2, vm3"
}
```

### Health Check

```bash
curl "http://127.0.0.1:8000/health" | jq .
```

Response:
```json
{
  "status": "healthy",
  "server_version": "2.0.0",
  "cache_status": {
    "last_update": "2025-05-06T09:31:28.909005",
    "cached_vms": 276,
    "age_minutes": 15.2,
    "refresh_scheduled_in_minutes": 44.8,
    "refresh_active": true
  },
  "supported_operations": {
    "status": "Available for all VMs",
    "start": "Available for all VMs",
    "stop": "Restricted to whitelisted VMs",
    "suspend": "Restricted to whitelisted VMs",
    "resume": "Available for all VMs"
  },
  "timestamp": "2025-05-06T09:46:46.549473"
}
```

## Troubleshooting

### Common Issues

#### VM Not Found in Cache

If you see an error like "VM not found in any zone":

1. Check if the VM exists in the GCP project
2. Try providing the zone explicitly in the request
3. Wait for the cache to refresh (happens every hour by default)
4. Manually trigger a cache refresh by restarting the service

#### Authentication Errors

If you see authentication errors:

1. Verify `gcloud` is properly authenticated
2. Run `gcloud auth login` to refresh credentials
3. Check that the service account has the required permissions

#### Restricted Operation Errors

If you see "Operation not allowed" errors:

1. Verify the VM is in the `ALLOWED_VMS` list in the .env file
2. Restart the service after updating the .env file

### Logging and Debugging

Logs are stored in the following locations:

- Application logs: `logs/YYYY/MM-Month/gcp_vm_operations.log`
- Operation logs: `logs/operations/YYYY/operations_YYYY_MM.csv`
- Test logs: `tests/test_logs/`

To increase logging verbosity, modify `logger_config.py` to set the log level to DEBUG.

## Security Considerations

- This service does not implement authentication/authorization - use API Gateway or reverse proxy for this
- Restricted operations (stop/suspend) are limited to whitelisted VMs
- Consider running in a private network or with firewall rules in production
- Use HTTPS in production to protect data in transit