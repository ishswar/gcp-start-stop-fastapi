#!/usr/bin/env python3
"""
GCP VM Manager API Test Suite
Comprehensive tests for the VM management API with detailed reporting
"""
import os
import sys
import json
import logging
import requests
import time
import argparse
import csv
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Tuple, Any, Optional
from dotenv import load_dotenv
from rich.console import Console
from rich.table import Table
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskID
from rich.panel import Panel
from rich.prompt import Confirm

# Create logs directory if it doesn't exist
logs_dir = Path("test_logs")
logs_dir.mkdir(exist_ok=True)

# Configure logging to write to test_logs directory
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler(logs_dir / "api_tests.log"),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger("api_tests")

# Initialize rich console for pretty output
console = Console()

# Load environment variables
load_dotenv()

class VMState:
    """VM states from GCP"""
    RUNNING = "RUNNING"
    TERMINATED = "TERMINATED"
    SUSPENDED = "SUSPENDED"
    STOPPING = "STOPPING"
    SUSPENDING = "SUSPENDING"
    PROVISIONING = "PROVISIONING"
    STAGING = "STAGING"
    UNKNOWN = "UNKNOWN"

class APITest:
    """Test harness for GCP VM Manager API"""
    
    def __init__(self, api_url: str = None, start_vm: str = None, resume_vm: str = None, 
                 test_zone: str = None, silent: bool = False, interactive: bool = True):
        """Initialize test harness"""
        self.api_url = api_url or os.getenv("API_URL", "http://127.0.0.1:8000")
        self.start_vm = start_vm or os.getenv("START_TEST_VM", "")
        self.resume_vm = resume_vm or os.getenv("RESUME_TEST_VM", "")
        self.test_zone = test_zone or os.getenv("TEST_ZONE", "")
        self.silent = silent
        self.interactive = interactive and not silent
        self.results = []
        self.skipped_tests = []  # Track skipped tests separately
        self.start_time = datetime.now()
        timestamp = self.start_time.strftime('%Y%m%d_%H%M%S')
        self.report_file = logs_dir / f"vm_api_test_report_{timestamp}.txt"
        
        # Track VM states
        self.vm_states = {
            self.start_vm: VMState.UNKNOWN,
            self.resume_vm: VMState.UNKNOWN
        }
        
        # Track which tests to run
        self.run_start_tests = bool(self.start_vm)
        self.run_resume_tests = bool(self.resume_vm)
        
        # Test progress tracking
        self.progress = None
        self.task_id = None
        
    def log(self, message: str, level: str = "info"):
        """Log a message and print to console if not in silent mode"""
        getattr(logger, level)(message)
        if not self.silent:
            console.print(message)
            
    def start_test_suite(self):
        """Initialize and begin the test suite"""
        console.print(Panel.fit(
            f"[bold blue]GCP VM Manager API Test Suite[/bold blue]", 
            subtitle=f"Target: {self.api_url}"
        ))
        
        if not self.start_vm and not self.resume_vm:
            console.print("[bold red]ERROR: No test VMs specified. Please provide at least one VM for testing.[/bold red]")
            console.print("Use START_TEST_VM in .env for start/stop tests.")
            console.print("Use RESUME_TEST_VM in .env for suspend/resume tests.")
            return
            
        # Check VM states before proceeding
        self.check_vm_states()
        
        # Calculate total test count
        total_tests = 1  # Health endpoint
        if self.run_start_tests:
            total_tests += 3  # Status, start, status after start
        if self.run_resume_tests:
            total_tests += 3  # Status, resume, status after resume
            
        # Start progress tracker
        self.progress = Progress(
            SpinnerColumn(),
            TextColumn("[bold blue]{task.description}[/bold blue]"),
            BarColumn(),
            TextColumn("[bold]{task.completed}/{task.total}[/bold]"),
        )
        
        with self.progress:
            # Add task for test suite
            self.task_id = self.progress.add_task("Running API tests...", total=total_tests)
            
            # Run common tests
            self.test_health_endpoint()
            
            # Run start/stop tests if VM is available
            if self.run_start_tests:
                self.test_vm_status(self.start_vm, "start_vm_initial_status")
                self.test_start_operation()
                self.test_vm_status(self.start_vm, "start_vm_final_status")
            
            # Run suspend/resume tests if VM is available
            if self.run_resume_tests:
                self.test_vm_status(self.resume_vm, "resume_vm_initial_status")
                self.test_resume_operation()
                self.test_vm_status(self.resume_vm, "resume_vm_final_status")
            
        # Generate detailed report
        self.generate_report()
        
    def check_vm_states(self):
        """Check VM states and determine which tests can be run"""
        if self.start_vm:
            console.print(f"\n[bold]Checking state for start/stop test VM: {self.start_vm}[/bold]")
            vm_state = self.get_vm_state(self.start_vm)
            
            if vm_state == VMState.UNKNOWN:
                console.print(f"[red]Cannot determine state of VM {self.start_vm}. Start/stop tests will be skipped.[/red]")
                self.run_start_tests = False
                # Record skipped tests
                self._record_skipped_test("start_vm_initial_status", f"Cannot determine state of VM {self.start_vm}")
                self._record_skipped_test("vm_start", f"Cannot determine state of VM {self.start_vm}")
                self._record_skipped_test("start_vm_final_status", f"Cannot determine state of VM {self.start_vm}")
            elif vm_state != VMState.TERMINATED:
                if self.interactive:
                    console.print(f"[yellow]Warning: VM {self.start_vm} is not in TERMINATED state (current: {vm_state}).[/yellow]")
                    console.print("[yellow]Start test requires VM to be in TERMINATED state.[/yellow]")
                    
                    if Confirm.ask("Would you like to stop this VM now to continue with start testing?"):
                        if self.stop_vm(self.start_vm):
                            console.print(f"[green]VM {self.start_vm} stopped successfully.[/green]")
                            vm_state = self.get_vm_state(self.start_vm)
                            if vm_state == VMState.TERMINATED:
                                console.print(f"[green]VM is now in TERMINATED state. Start tests will proceed.[/green]")
                            else:
                                console.print(f"[yellow]VM is in {vm_state} state, not TERMINATED. Waiting might be required.[/yellow]")
                        else:
                            console.print(f"[red]Failed to stop VM {self.start_vm}. Start tests will be skipped.[/red]")
                            self.run_start_tests = False
                    else:
                        console.print("[yellow]Start tests will be skipped.[/yellow]")
                        self.run_start_tests = False
                else:
                    console.print(f"[yellow]VM {self.start_vm} is not in TERMINATED state (current: {vm_state}). Start tests will be skipped.[/yellow]")
                    self.run_start_tests = False
        
        if self.resume_vm:
            console.print(f"\n[bold]Checking state for suspend/resume test VM: {self.resume_vm}[/bold]")
            vm_state = self.get_vm_state(self.resume_vm)
            
            if vm_state == VMState.UNKNOWN:
                console.print(f"[red]Cannot determine state of VM {self.resume_vm}. Suspend/resume tests will be skipped.[/red]")
                self.run_resume_tests = False
            elif vm_state != VMState.SUSPENDED:
                if self.interactive:
                    console.print(f"[yellow]Warning: VM {self.resume_vm} is not in SUSPENDED state (current: {vm_state}).[/yellow]")
                    console.print("[yellow]Resume test requires VM to be in SUSPENDED state.[/yellow]")
                    
                    if Confirm.ask("Would you like to suspend this VM now to continue with resume testing?"):
                        if self.suspend_vm(self.resume_vm):
                            console.print(f"[green]VM {self.resume_vm} suspend request sent successfully.[/green]")
                            console.print(f"[yellow]Note: VM suspension may take some time to complete.[/yellow]")
                            
                            # Wait for suspension to complete
                            console.print("[yellow]Waiting for VM to enter SUSPENDED state (up to 2 minutes)...[/yellow]")
                            for _ in range(12):  # Wait up to 2 minutes
                                time.sleep(10)
                                vm_state = self.get_vm_state(self.resume_vm)
                                if vm_state == VMState.SUSPENDED:
                                    console.print(f"[green]VM is now in SUSPENDED state. Resume tests will proceed.[/green]")
                                    break
                                console.print(f"Current state: {vm_state}")
                                
                            if vm_state != VMState.SUSPENDED:
                                console.print(f"[red]VM did not enter SUSPENDED state within timeout. Resume tests will be skipped.[/red]")
                                self.run_resume_tests = False
                        else:
                            console.print(f"[red]Failed to suspend VM {self.resume_vm}. Resume tests will be skipped.[/red]")
                            self.run_resume_tests = False
                    else:
                        console.print("[yellow]Resume tests will be skipped.[/yellow]")
                        self.run_resume_tests = False
                else:
                    console.print(f"[yellow]VM {self.resume_vm} is not in SUSPENDED state (current: {vm_state}). Resume tests will be skipped.[/yellow]")
                    self.run_resume_tests = False
                    
        console.print("\n[bold]Test Configuration:[/bold]")
        console.print(f"API URL: {self.api_url}")
        console.print(f"Start/Stop Tests: {'Enabled' if self.run_start_tests else 'Disabled'}")
        if self.run_start_tests:
            console.print(f"  - Start Test VM: {self.start_vm} (State: {self.vm_states.get(self.start_vm, 'Unknown')})")
        console.print(f"Suspend/Resume Tests: {'Enabled' if self.run_resume_tests else 'Disabled'}")
        if self.run_resume_tests:
            console.print(f"  - Resume Test VM: {self.resume_vm} (State: {self.vm_states.get(self.resume_vm, 'Unknown')})")
        console.print(f"Zone: {self.test_zone or 'Auto-detect'}")
        console.print("")
                
    def get_vm_state(self, vm_name: str) -> str:
        """Get current VM state"""
        if not vm_name:
            return VMState.UNKNOWN
            
        try:
            # Use JSON format for reliable parsing
            params = {
                "vmname": vm_name,
                "operation": "status",
                "format": "json"
            }
            
            if self.test_zone:
                params["zone"] = self.test_zone
                
            response = requests.get(f"{self.api_url}/gcp-action/", params=params)
            response.raise_for_status()
            data = response.json()
            
            if data.get("status") == "success":
                vm_info = data.get("data", {})
                vm_state = vm_info.get("status", VMState.UNKNOWN)
                self.vm_states[vm_name] = vm_state
                return vm_state
            else:
                logger.warning(f"Failed to get VM state: {data}")
                return VMState.UNKNOWN
        except Exception as e:
            logger.error(f"Error getting VM state: {str(e)}")
            return VMState.UNKNOWN
            
    def stop_vm(self, vm_name: str) -> bool:
        """Attempt to stop a VM"""
        try:
            params = {
                "vmname": vm_name,
                "operation": "stop",
                "format": "json"
            }
            
            if self.test_zone:
                params["zone"] = self.test_zone
                
            response = requests.get(f"{self.api_url}/gcp-action/", params=params)
            
            # Handle 403 if VM is not in whitelist
            if response.status_code == 403:
                console.print("[yellow]Stop operation not authorized. This VM may not be in the whitelist.[/yellow]")
                console.print("[yellow]Please stop the VM manually through GCP console.[/yellow]")
                
                if self.interactive:
                    if Confirm.ask("Have you manually stopped the VM?"):
                        return True
                return False
                
            response.raise_for_status()
            data = response.json()
            
            return data.get("status") == "success"
        except Exception as e:
            logger.error(f"Error stopping VM: {str(e)}")
            return False
            
    def suspend_vm(self, vm_name: str) -> bool:
        """Attempt to suspend a VM"""
        try:
            params = {
                "vmname": vm_name,
                "operation": "suspend",
                "format": "json"
            }
            
            if self.test_zone:
                params["zone"] = self.test_zone
                
            response = requests.get(f"{self.api_url}/gcp-action/", params=params)
            
            # Handle 403 if VM is not in whitelist
            if response.status_code == 403:
                console.print("[yellow]Suspend operation not authorized. This VM may not be in the whitelist.[/yellow]")
                console.print("[yellow]Please suspend the VM manually through GCP console.[/yellow]")
                
                if self.interactive:
                    if Confirm.ask("Have you manually suspended the VM?"):
                        return True
                return False
                
            response.raise_for_status()
            data = response.json()
            
            return data.get("status") == "success"
        except Exception as e:
            logger.error(f"Error suspending VM: {str(e)}")
            return False
        
    def test_health_endpoint(self):
        """Test the health endpoint"""
        self.log("Testing health endpoint...")
        test_name = "health_check"
        
        try:
            response = requests.get(f"{self.api_url}/health")
            response.raise_for_status()
            data = response.json()
            
            if data.get("status") == "healthy":
                success = True
                message = "Health check succeeded"
                details = f"Server version: {data.get('server_version', 'unknown')}"
            else:
                success = False
                message = f"Health check returned non-healthy status: {data.get('status')}"
                details = json.dumps(data)
        except Exception as e:
            success = False
            message = f"Health check failed with error: {str(e)}"
            details = str(e)
            
        self.record_result(test_name, success, message, details)
        self.progress.update(self.task_id, advance=1)
        
    def test_vm_status(self, vm_name: str, test_name: str):
        """Test getting VM status"""
        self.log(f"Testing status operation on VM {vm_name}...")
        
        try:
            # Use JSON format for reliable parsing
            params = {
                "vmname": vm_name,
                "operation": "status",
                "format": "json"
            }
            
            if self.test_zone:
                params["zone"] = self.test_zone
                
            response = requests.get(f"{self.api_url}/gcp-action/", params=params)
            response.raise_for_status()
            data = response.json()
            
            if data.get("status") == "success":
                vm_info = data.get("data", {})
                vm_state = vm_info.get("status", VMState.UNKNOWN)
                self.vm_states[vm_name] = vm_state
                
                success = True
                message = f"VM status check succeeded: {vm_state}"
                details = f"Machine type: {vm_info.get('machineType', 'unknown')}, IP: {vm_info.get('networkIP', 'unknown')}"
            else:
                success = False
                message = "VM status check failed"
                details = json.dumps(data)
        except Exception as e:
            success = False
            message = f"VM status check failed with error: {str(e)}"
            details = str(e)
            
        self.record_result(test_name, success, message, details)
        self.progress.update(self.task_id, advance=1)
        
    def test_start_operation(self):
        """Test starting the VM"""
        vm_name = self.start_vm
        self.log(f"Testing start operation on VM {vm_name}...")
        test_name = "vm_start"
        
        try:
            # Use JSON format for reliable parsing
            params = {
                "vmname": vm_name,
                "operation": "start",
                "format": "json"
            }
            
            if self.test_zone:
                params["zone"] = self.test_zone
                
            response = requests.get(f"{self.api_url}/gcp-action/", params=params)
            response.raise_for_status()
            data = response.json()
            
            if data.get("status") == "success":
                success = True
                message = f"VM start operation succeeded"
                details = data.get("message", "")
            else:
                success = False
                message = "VM start operation failed"
                details = json.dumps(data)
        except Exception as e:
            success = False
            message = f"VM start operation failed with error: {str(e)}"
            details = str(e)
            
        self.record_result(test_name, success, message, details)
        self.progress.update(self.task_id, advance=1)
        
    def test_resume_operation(self):
        """Test resuming the VM from suspended state"""
        vm_name = self.resume_vm
        self.log(f"Testing resume operation on VM {vm_name}...")
        test_name = "vm_resume"
        
        try:
            # Use JSON format for reliable parsing
            params = {
                "vmname": vm_name,
                "operation": "resume",
                "format": "json"
            }
            
            if self.test_zone:
                params["zone"] = self.test_zone
                
            response = requests.get(f"{self.api_url}/gcp-action/", params=params)
            response.raise_for_status()
            data = response.json()
            
            if data.get("status") == "success":
                success = True
                message = f"VM resume operation succeeded"
                details = data.get("message", "")
            else:
                success = False
                message = "VM resume operation failed"
                details = json.dumps(data)
        except Exception as e:
            success = False
            message = f"VM resume operation failed with error: {str(e)}"
            details = str(e)
            
        self.record_result(test_name, success, message, details)
        self.progress.update(self.task_id, advance=1)
        
    def record_result(self, test_name: str, success: bool, message: str, details: str):
        """Record a test result"""
        result = {
            "test_name": test_name,
            "success": success,
            "message": message,
            "details": details,
            "timestamp": datetime.now().isoformat()
        }
        self.results.append(result)
        
        status = "[green]PASSED[/green]" if success else "[red]FAILED[/red]"
        self.log(f"{test_name}: {status} - {message}")
        
    def generate_report(self):
        """Generate a detailed test report"""
        # Calculate summary
        total_tests = len(self.results) + len(self.skipped_tests)
        passed_tests = sum(1 for r in self.results if r["success"])
        failed_tests = sum(1 for r in self.results if not r["success"])
        skipped_tests = len(self.skipped_tests)
        
        # Create report table
        table = Table(title="GCP VM Manager API Test Results")
        table.add_column("Test", style="blue")
        table.add_column("Result", style="green")
        table.add_column("Message")
        table.add_column("Details", overflow="fold")
        
        for result in self.results:
            status = "✅ PASSED" if result["success"] else "❌ FAILED"
            status_style = "green" if result["success"] else "red"
            table.add_row(
                result["test_name"],
                f"[{status_style}]{status}[/{status_style}]",
                result["message"],
                result["details"]
            )
        
        for skipped in self.skipped_tests:
            table.add_row(
                skipped["test_name"],
                "[yellow]⏭️ SKIPPED[/yellow]",
                skipped["reason"],
                "Test was skipped"
            )
        
        # Print summary
        console.print("\n")
        console.print(Panel.fit(
            f"[bold]Test Summary[/bold]\n"
            f"Total Tests: {total_tests}\n"
            f"Passed: [green]{passed_tests}[/green]\n"
            f"Failed: [red]{failed_tests}[/red]\n"
            f"Skipped: [yellow]{skipped_tests}[/yellow]\n"
            f"Success Rate: [{'green' if passed_tests == total_tests - skipped_tests else 'yellow'}]{passed_tests/(total_tests-skipped_tests)*100 if total_tests > skipped_tests else 0:.1f}%[/]",
            title="Summary"
        ))
        
        console.print(table)
        
        # Save report to file
        self.save_report_to_file()
        console.print(f"\nDetailed report saved to: [bold]{self.report_file}[/bold]")
        
        # Also save as CSV for data analysis
        csv_file = self.report_file.with_suffix('.csv')
        self.save_report_to_csv(csv_file)
        console.print(f"CSV report saved to: [bold]{csv_file}[/bold]")
        
    def save_report_to_file(self):
        """Save the test report to a text file"""
        with open(self.report_file, "w") as f:
            f.write("GCP VM Manager API Test Report\n")
            f.write("================================\n\n")
            f.write(f"Test Run: {self.start_time.strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"API URL: {self.api_url}\n")
            f.write(f"Start/Stop VM: {self.start_vm or 'Not tested'}\n")
            f.write(f"Resume/Suspend VM: {self.resume_vm or 'Not tested'}\n")
            f.write(f"Test Zone: {self.test_zone or 'Auto-detected'}\n\n")
            
            f.write("Test Results\n")
            f.write("-----------\n\n")
            
            for result in self.results:
                status = "PASSED" if result["success"] else "FAILED"
                f.write(f"Test: {result['test_name']}\n")
                f.write(f"Result: {status}\n")
                f.write(f"Message: {result['message']}\n")
                f.write(f"Details: {result['details']}\n")
                f.write(f"Timestamp: {result['timestamp']}\n")
                f.write("\n")
            
            if self.skipped_tests:
                f.write("Skipped Tests\n")
                f.write("-------------\n\n")
                
                for skipped in self.skipped_tests:
                    f.write(f"Test: {skipped['test_name']}\n")
                    f.write(f"Result: SKIPPED\n")
                    f.write(f"Reason: {skipped['reason']}\n")
                    f.write(f"Timestamp: {skipped['timestamp']}\n")
                    f.write("\n")
            
            # Summary
            total_tests = len(self.results) + len(self.skipped_tests)
            passed_tests = sum(1 for r in self.results if r["success"])
            failed_tests = sum(1 for r in self.results if not r["success"])
            skipped_tests = len(self.skipped_tests)
            
            f.write("Summary\n")
            f.write("-------\n")
            f.write(f"Total Tests: {total_tests}\n")
            f.write(f"Passed: {passed_tests}\n")
            f.write(f"Failed: {failed_tests}\n")
            f.write(f"Skipped: {skipped_tests}\n")
            success_rate = passed_tests/(total_tests-skipped_tests)*100 if total_tests > skipped_tests else 0
            f.write(f"Success Rate: {success_rate:.1f}%\n")
            
    def save_report_to_csv(self, csv_file: str):
        """Save the test report to a CSV file for data analysis"""
        with open(csv_file, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["test_name", "result", "message", "details", "timestamp"])
            
            for result in self.results:
                writer.writerow([
                    result["test_name"],
                    "PASSED" if result["success"] else "FAILED",
                    result["message"],
                    result["details"],
                    result["timestamp"]
                ])
            
            for skipped in self.skipped_tests:
                writer.writerow([
                    skipped["test_name"],
                    "SKIPPED",
                    skipped["reason"],
                    "Test was skipped",
                    skipped["timestamp"]
                ])

    def _record_skipped_test(self, test_name: str, reason: str):
        """Record a skipped test"""
        skipped = {
            "test_name": test_name,
            "reason": reason,
            "timestamp": datetime.now().isoformat()
        }
        self.skipped_tests.append(skipped)
        self.log(f"{test_name}: [yellow]SKIPPED[/yellow] - {reason}", level="warning")


def parse_arguments():
    """Parse command line arguments"""
    parser = argparse.ArgumentParser(description="GCP VM Manager API Test Suite")
    parser.add_argument("--url", help="API URL (default: from .env or http://127.0.0.1:8000)")
    parser.add_argument("--start-vm", help="VM to test start operations (should be in TERMINATED state)")
    parser.add_argument("--resume-vm", help="VM to test resume operations (should be in SUSPENDED state)")
    parser.add_argument("--zone", help="VM zone (default: auto-detect)")
    parser.add_argument("--silent", action="store_true", help="Minimize console output")
    parser.add_argument("--non-interactive", action="store_true", help="Run without interactive prompts")
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_arguments()
    
    # Set up environment variables from arguments if provided
    if args.url:
        os.environ["API_URL"] = args.url
    if args.start_vm:
        os.environ["START_TEST_VM"] = args.start_vm
    if args.resume_vm:
        os.environ["RESUME_TEST_VM"] = args.resume_vm
    if args.zone:
        os.environ["TEST_ZONE"] = args.zone
        
    # Run the test suite
    test_suite = APITest(
        api_url=args.url, 
        start_vm=args.start_vm, 
        resume_vm=args.resume_vm,
        test_zone=args.zone,
        silent=args.silent,
        interactive=not args.non_interactive
    )
    test_suite.start_test_suite() 