# GCP VM Manager API Test Suite

This is a comprehensive test suite for the GCP VM Manager API. It tests all available endpoints and operations, providing detailed reports on API functionality.

## Features

- Tests health endpoint
- Tests VM status operations
- Tests VM start operations (requires a VM in TERMINATED state)
- Tests VM resume operations (requires a VM in SUSPENDED state)
- Interactive mode to help prepare VMs in the right state
- Generates detailed reports in both text and CSV formats
- Colorized console output for clear visibility
- Configurable through environment variables or command line arguments

## Requirements

Install required dependencies:

```bash
pip install requests python-dotenv rich
```

## Configuration

You can configure the test suite in two ways:

1. Using a `.env` file in the same directory:

```
API_URL=http://127.0.0.1:8000
START_TEST_VM=your-terminated-vm
RESUME_TEST_VM=your-suspended-vm
TEST_ZONE=us-east4-a # Optional
```

```bash
pip install requests python-dotenv rich
```

1. Using command line arguments:

```bash
python test_api.py --url http://127.0.0.1:8000 --start-vm your-terminated-vm --resume-vm your-suspended-vm
```

## VM State Requirements

- **Start Test VM:** Must be in TERMINATED state. In interactive mode, the test will offer to stop the VM if it's running.
- **Resume Test VM:** Must be in SUSPENDED state. In interactive mode, the test will offer to suspend the VM if it's not already suspended.

## Running Tests

Basic usage:

```bash
python test_api.py
```

This will run the full test suite against the configured API endpoint and VMs.

Non-interactive mode (for automation):

```bash
python test_api.py --non-interactive
```

In non-interactive mode, tests will be skipped if VMs are not in the required state.

## Test Reports

The test suite generates two report formats:

1. A human-readable text report: `vm_api_test_report_YYYYMMDD_HHMMSS.txt`
2. A CSV file for data analysis: `vm_api_test_report_YYYYMMDD_HHMMSS.csv`

Both contain detailed information about each test, including success/failure status, messages, and details.

## Notes

- You can provide either one or both test VMs depending on what you want to test.
- Stop and suspend operations may fail if the test VMs are not in the API's whitelist - this is expected behavior.
- The interactive mode will guide you through preparing VMs in the right state.

