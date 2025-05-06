"""
VM Operations Handler with SSE Support
Handles execution of VM operations and provides real-time updates via SSE
"""
from fastapi import HTTPException
from sse_starlette.sse import EventSourceResponse
import asyncio
import subprocess
from datetime import datetime
from typing import AsyncGenerator, Optional, Dict, List
import logging
import re
import json
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Get allowed VMs from environment, fallback to defaults if not set
default_allowed_vms = ["guedfocnlq03", "guedfocdsml01", "guedfocwqa82"]
ALLOWED_VMS = os.getenv("ALLOWED_VMS", "").split(",") if os.getenv("ALLOWED_VMS") else default_allowed_vms

# Clean up any empty strings from the list
ALLOWED_VMS = [vm.strip() for vm in ALLOWED_VMS if vm.strip()]

# List of restricted operations that require VM to be in the allowed list
RESTRICTED_OPERATIONS = os.getenv("RESTRICTED_OPERATIONS", "stop,suspend").split(",")
RESTRICTED_OPERATIONS = [op.strip() for op in RESTRICTED_OPERATIONS if op.strip()]

# Mapping vanity names to actual hostnames
VANITY_TO_HOSTNAME = {
    "nlq": "guedfocnlq03",
    "py-server": "guedfocdsml01",
}

class VMOperationsHandler:
    def __init__(self, vm_cache, operation_logger):
        self.vm_cache = vm_cache
        self.operation_logger = operation_logger
        self.logger = logging.getLogger(__name__)

    def map_vanity_to_hostname(self, vmname: str) -> str:
        """Map vanity name to actual hostname if needed"""
        # First, remove domain suffix if present
        base_vmname = vmname.split('.')[0]
        
        # Check if the vmname matches any of our vanity names
        for vanity_name, real_hostname in VANITY_TO_HOSTNAME.items():
            if base_vmname.startswith(vanity_name):
                self.logger.info(f"Mapped vanity name {vmname} to {real_hostname}")
                return real_hostname
                
        return base_vmname  # Return the base VM name if no mapping is found

    def get_vanity_name(self, vmname: str) -> str:
        """Get the vanity name for a VM if available"""
        base_vmname = vmname.split('.')[0]
        
        for vanity_name, real_hostname in VANITY_TO_HOSTNAME.items():
            if base_vmname == real_hostname or base_vmname.startswith(vanity_name):
                return f"{vanity_name}.ibi.systems"
                
        return vmname  # Return the original vmname if no mapping is found

    def is_vm_allowed_for_operation(self, vmname: str, operation: str) -> bool:
        """Check if VM is allowed for the specified operation"""
        if operation.lower() not in RESTRICTED_OPERATIONS:
            # Allow all VMs for non-restricted operations (status, start, resume)
            return True
        
        # For restricted operations (stop, suspend), check against allowed VMs
        real_vmname = self.map_vanity_to_hostname(vmname)
        return real_vmname in ALLOWED_VMS

    async def execute_vm_operation(self, vmname: str, operation: str, zone: Optional[str], client_ip: str) -> AsyncGenerator:
        """
        Execute VM operation with SSE updates
        """
        # Map vanity name to real hostname
        real_vmname = self.map_vanity_to_hostname(vmname)
        vanity_vmname = self.get_vanity_name(vmname)
        start_time = datetime.now()
        
        # Check if operation is allowed for this VM
        if not self.is_vm_allowed_for_operation(real_vmname, operation):
            allowed_vms_display = [f"{vm} ({self.get_vanity_name(vm)})" for vm in ALLOWED_VMS]
            error_msg = f"Operation '{operation}' is not allowed for VM '{vmname}'. Only allowed for: {', '.join(allowed_vms_display)}"
            self.logger.warning(error_msg)
            yield self._format_sse_message("error", error_msg)
            
            self.operation_logger.log_operation(
                timestamp=datetime.now(),
                vm_name=real_vmname,
                operation=operation,
                client_ip=client_ip,
                zone=zone,
                status="denied",
                vanity_name=vanity_vmname
            )
            return
        
        try:
            # Get zone from cache if not provided
            if not zone:
                self.logger.info(f"Looking up zone for VM {real_vmname} in cache")
                zone = self.vm_cache.get_vm_zone(real_vmname)
                if not zone:
                    error_msg = f"VM {real_vmname} not found in any zone. Please specify a zone parameter."
                    self.logger.warning(f"VM {real_vmname} not found in cache")
                    yield self._format_sse_message("error", error_msg)
                    
                    # Log the error
                    self.operation_logger.log_operation(
                        timestamp=datetime.now(),
                        vm_name=real_vmname,
                        operation=operation,
                        client_ip=client_ip,
                        zone="unknown",
                        status="failed-no-zone",
                        vanity_name=vanity_vmname
                    )
                    return  # Return immediately instead of proceeding

            # Log operation start
            self.logger.info(f"Starting {operation} operation on {real_vmname} ({vanity_vmname}) in zone {zone}")
            self.operation_logger.log_operation(
                timestamp=start_time,
                vm_name=real_vmname,
                operation=operation,
                client_ip=client_ip,
                zone=zone,
                status="started",
                vanity_name=vanity_vmname
            )

            # Special handling for status operation
            if operation == "status":
                yield self._format_sse_message("info", f"Checking status of VM {real_vmname} in zone {zone}")
                
                # Execute command to get just the status in CSV format for reliable parsing
                cmd = ["gcloud", "compute", "instances", "describe", real_vmname, 
                      "--zone", zone, "--format=csv[no-heading](status,machineType.basename(),networkInterfaces[0].networkIP)"]
                
                process = await asyncio.create_subprocess_exec(
                    *cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE
                )
                
                output, error = await process.communicate()
                
                if process.returncode == 0:
                    # Parse the CSV output
                    output_text = output.decode().strip()
                    self.logger.debug(f"Raw status output: '{output_text}'")
                    
                    # Split by comma (CSV format)
                    vm_info = output_text.split(',')
                    
                    if len(vm_info) >= 1:
                        status = vm_info[0].strip()
                        
                        # Extract machine type
                        machine_type = "unknown"
                        if len(vm_info) >= 2:
                            machine_type = vm_info[1].strip()
                        
                        # Extract IP address
                        ip_address = "unknown"
                        if len(vm_info) >= 3:
                            ip_address = vm_info[2].strip()
                        
                        # Format a clean status message
                        status_info = {
                            "name": real_vmname,
                            "vanity_name": vanity_vmname if vanity_vmname != real_vmname else None,
                            "status": status,
                            "machine_type": machine_type,
                            "ip_address": ip_address,
                            "zone": zone
                        }
                        
                        # Log status to CSV
                        self.operation_logger.log_operation(
                            timestamp=datetime.now(),
                            vm_name=real_vmname,
                            operation=operation,
                            client_ip=client_ip,
                            zone=zone,
                            status="completed",
                            vanity_name=vanity_vmname
                        )
                        
                        # Send a single, formatted status message
                        yield self._format_sse_message("status", json.dumps(status_info))
                        yield self._format_sse_message("success", f"VM {real_vmname} is {status} ({machine_type}, IP: {ip_address})")
                    else:
                        yield self._format_sse_message("error", "Unable to parse VM status information")
                else:
                    error_msg = error.decode()
                    sanitized_error = self._sanitize_error(error_msg)
                    self.logger.error(f"Error getting VM status: {error_msg}")
                    yield self._format_sse_message("error", sanitized_error)
                    
                    self.operation_logger.log_operation(
                        timestamp=datetime.now(),
                        vm_name=real_vmname,
                        operation=operation,
                        client_ip=client_ip,
                        zone=zone,
                        status="failed",
                        vanity_name=vanity_vmname
                    )
                
                return
                
            # For other operations (start/stop), continue with existing code
            # Prepare command based on operation
            cmd = self._get_gcloud_command(operation, real_vmname, zone)
            if not cmd:
                yield self._format_sse_message("error", f"Invalid operation: {operation}")
                return

            yield self._format_sse_message("info", f"Executing {operation} on VM {real_vmname} in zone {zone}")

            # Execute command
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )

            # Stream output
            while True:
                line = await process.stdout.readline()
                if not line:
                    break
                yield self._format_sse_message("progress", line.decode().strip())

            # Wait for completion
            await process.wait()

            if process.returncode == 0:
                success_msg = f"Successfully completed {operation} operation on VM {real_vmname} ({vanity_vmname})"
                self.logger.info(success_msg)
                yield self._format_sse_message("success", success_msg)
                
                self.operation_logger.log_operation(
                    timestamp=datetime.now(),
                    vm_name=real_vmname,
                    operation=operation,
                    client_ip=client_ip,
                    zone=zone,
                    status="completed",
                    vanity_name=vanity_vmname
                )
            else:
                error = await process.stderr.read()
                error_message = error.decode()
                
                # Sanitize the error message
                sanitized_error = self._sanitize_error(error_message)
                
                self.logger.error(f"Operation failed with original error: {error_message}")
                self.logger.info(f"Sending sanitized error to client: {sanitized_error}")
                
                yield self._format_sse_message("error", sanitized_error)
                
                self.operation_logger.log_operation(
                    timestamp=datetime.now(),
                    vm_name=real_vmname,
                    operation=operation,
                    client_ip=client_ip,
                    zone=zone,
                    status="failed",
                    vanity_name=vanity_vmname
                )

        except Exception as e:
            error_msg = str(e)
            sanitized_error = self._sanitize_error(error_msg)
            
            self.logger.error(f"Error during {operation} operation: {error_msg}")
            self.logger.info(f"Sending sanitized error to client: {sanitized_error}")
            
            yield self._format_sse_message("error", sanitized_error)
            
            self.operation_logger.log_operation(
                timestamp=datetime.now(),
                vm_name=real_vmname,
                operation=operation,
                client_ip=client_ip,
                zone=zone,
                status="error",
                vanity_name=vanity_vmname
            )

    def _get_gcloud_command(self, operation: str, vmname: str, zone: str) -> Optional[list]:
        """Get gcloud command based on operation"""
        commands = {
            "status": ["gcloud", "compute", "instances", "describe", vmname, "--zone", zone],
            "start": ["gcloud", "compute", "instances", "start", vmname, "--zone", zone],
            "stop": ["gcloud", "compute", "instances", "stop", vmname, "--zone", zone],
            "suspend": ["gcloud", "compute", "instances", "suspend", vmname, "--zone", zone],
            "resume": ["gcloud", "compute", "instances", "resume", vmname, "--zone", zone]
        }
        return commands.get(operation)

    def _format_sse_message(self, event_type: str, data: str) -> dict:
        """Format message for SSE"""
        return {
            "event": event_type,
            "data": data,
            "retry": 1000  # Retry timeout in milliseconds
        }

    async def stream_operation(self, vmname: str, operation: str, zone: Optional[str], client_ip: str) -> EventSourceResponse:
        """
        Create SSE response for VM operation
        """
        return EventSourceResponse(
            self.execute_vm_operation(vmname, operation, zone, client_ip),
            media_type="text/event-stream"
        )

    def _sanitize_error(self, error_message: str) -> str:
        """
        Sanitize error messages to remove sensitive information
        """
        # Check if it's a 404 not found error
        if "HTTPError 404" in error_message and "was not found" in error_message:
            # Extract just the VM name from the error
            vm_match = re.search(r'instances/([^\'"\s]+)', error_message)
            vm_name = vm_match.group(1) if vm_match else "the specified VM"
            
            return f"Error: VM '{vm_name}' not found. Please verify the VM name and try again."
        
        # For permission errors
        if "permission" in error_message.lower() or "authorized" in error_message.lower():
            return "Error: Insufficient permissions to perform this operation."
        
        # For other errors, provide a generic message
        return "An error occurred while performing the operation. Please check VM name and try again."

    async def execute_operation_json(self, vmname: str, operation: str, zone: Optional[str], client_ip: str):
        """
        Execute VM operation and return JSON response (no streaming)
        """
        # Map vanity name to real hostname
        real_vmname = self.map_vanity_to_hostname(vmname)
        vanity_vmname = self.get_vanity_name(vmname)
        start_time = datetime.now()
        
        # Check if operation is allowed for this VM
        if not self.is_vm_allowed_for_operation(real_vmname, operation):
            allowed_vms_display = [f"{vm} ({self.get_vanity_name(vm)})" for vm in ALLOWED_VMS]
            error_msg = f"Operation '{operation}' is not allowed for VM '{vmname}'. Only allowed for: {', '.join(allowed_vms_display)}"
            self.logger.warning(error_msg)
            
            self.operation_logger.log_operation(
                timestamp=datetime.now(),
                vm_name=real_vmname,
                operation=operation,
                client_ip=client_ip,
                zone=zone,
                status="denied",
                vanity_name=vanity_vmname
            )
            
            raise HTTPException(status_code=403, detail=error_msg)
        
        try:
            # Get zone from cache if not provided
            if not zone:
                self.logger.info(f"Looking up zone for VM {real_vmname} in cache")
                zone = self.vm_cache.get_vm_zone(real_vmname)
                if not zone:
                    error_msg = f"VM {real_vmname} not found in any zone. Please specify a zone parameter."
                    self.logger.warning(f"VM {real_vmname} not found in cache")
                    
                    # Log the error
                    self.operation_logger.log_operation(
                        timestamp=datetime.now(),
                        vm_name=real_vmname,
                        operation=operation,
                        client_ip=client_ip,
                        zone="unknown",
                        status="failed-no-zone",
                        vanity_name=vanity_vmname
                    )
                    
                    # Return meaningful error rather than hanging
                    raise HTTPException(status_code=404, detail=error_msg)

            # Log operation start
            self.logger.info(f"Starting {operation} operation on {real_vmname} ({vanity_vmname}) in zone {zone}")
            self.operation_logger.log_operation(
                timestamp=start_time,
                vm_name=real_vmname,
                operation=operation,
                client_ip=client_ip,
                zone=zone,
                status="started",
                vanity_name=vanity_vmname
            )

            # Execute based on operation type
            if operation == "status":
                # Use CSV format to ensure reliable parsing for specific fields
                cmd = ["gcloud", "compute", "instances", "describe", real_vmname, 
                       "--zone", zone, "--format=json"]
                
                process = await asyncio.create_subprocess_exec(
                    *cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE
                )
                
                output, error = await process.communicate()
                
                if process.returncode == 0:
                    # Parse the full JSON response
                    full_vm_info = json.loads(output)
                    
                    # Extract machine type basename (just the last part)
                    machine_type = "unknown"
                    if "machineType" in full_vm_info:
                        machine_type_parts = full_vm_info["machineType"].split("/")
                        machine_type = machine_type_parts[-1] if machine_type_parts else "unknown"
                    
                    # Extract network IP if available
                    network_ip = "unknown"
                    if "networkInterfaces" in full_vm_info and full_vm_info["networkInterfaces"]:
                        network_ip = full_vm_info["networkInterfaces"][0].get("networkIP", "unknown")
                        
                    # Build a clean response
                    instance_info = {
                        "name": full_vm_info.get("name", "unknown"),
                        "status": full_vm_info.get("status", "unknown"),
                        "zone": zone,
                        "machineType": machine_type,
                        "networkIP": network_ip
                    }
                    
                    # Log status to CSV
                    self.operation_logger.log_operation(
                        timestamp=datetime.now(),
                        vm_name=real_vmname,
                        operation=operation,
                        client_ip=client_ip,
                        zone=zone,
                        status="completed",
                        vanity_name=vanity_vmname
                    )
                    
                    # Return similar response format to your original code
                    return {
                        "status": "success", 
                        "data": instance_info,
                        "vanity_name": vanity_vmname if vanity_vmname != real_vmname else None
                    }
                else:
                    error_msg = error.decode()
                    sanitized_error = self._sanitize_error(error_msg)
                    self.logger.error(f"Error getting VM status: {error_msg}")
                    
                    self.operation_logger.log_operation(
                        timestamp=datetime.now(),
                        vm_name=real_vmname,
                        operation=operation,
                        client_ip=client_ip,
                        zone=zone,
                        status="failed",
                        vanity_name=vanity_vmname
                    )
                    
                    # Use regex to extract project and instance name if available
                    match = re.search(r"The resource 'projects/([^/]+)/.*?instances/([^'\"]+)", error_msg)
                    if match:
                        instance = match.group(2)
                        error_message = f"Error: The resource '{instance}' was not found in zone '{zone}'."
                        raise HTTPException(status_code=404, detail=error_message)
                    else:
                        raise HTTPException(status_code=500, detail=sanitized_error)
            
            elif operation in ["start", "stop", "suspend", "resume"]:
                # Map operation to past tense for message
                operation_past = {
                    "start": "started",
                    "stop": "stopped",
                    "suspend": "suspended",
                    "resume": "resumed"
                }.get(operation, operation + "ed")  # Default fallback
                
                # Start or stop the VM
                cmd = self._get_gcloud_command(operation, real_vmname, zone)
                
                process = await asyncio.create_subprocess_exec(
                    *cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE
                )
                
                output, error = await process.communicate()
                
                if process.returncode == 0:
                    success_msg = f"VM {real_vmname} ({vanity_vmname}) {operation_past} successfully."
                    self.logger.info(success_msg)
                    
                    self.operation_logger.log_operation(
                        timestamp=datetime.now(),
                        vm_name=real_vmname,
                        operation=operation,
                        client_ip=client_ip,
                        zone=zone,
                        status="completed",
                        vanity_name=vanity_vmname
                    )
                    
                    return {"status": "success", "message": success_msg}
                else:
                    error_msg = error.decode()
                    sanitized_error = self._sanitize_error(error_msg)
                    self.logger.error(f"Operation failed with original error: {error_msg}")
                    
                    self.operation_logger.log_operation(
                        timestamp=datetime.now(),
                        vm_name=real_vmname,
                        operation=operation,
                        client_ip=client_ip,
                        zone=zone,
                        status="failed",
                        vanity_name=vanity_vmname
                    )
                    
                    raise HTTPException(status_code=500, detail=sanitized_error)
            
            else:
                raise HTTPException(status_code=400, detail=f"Invalid operation: {operation}")

        except HTTPException:
            # Re-raise HTTP exceptions
            raise
        except Exception as e:
            error_msg = str(e)
            sanitized_error = self._sanitize_error(error_msg)
            
            self.logger.error(f"Error during {operation} operation: {error_msg}")
            
            self.operation_logger.log_operation(
                timestamp=datetime.now(),
                vm_name=real_vmname,
                operation=operation,
                client_ip=client_ip,
                zone=zone,
                status="error",
                vanity_name=vanity_vmname
            )
            
            raise HTTPException(status_code=500, detail=sanitized_error) 