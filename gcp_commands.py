"""
GCP Command Executor
Handles executing GCP commands and processing results
"""
import subprocess
import re
import json
import logging
from typing import Dict, Any, Tuple, Optional

# Setup logger for this module
logger = logging.getLogger(__name__)

class GCPCommandExecutor:
    """
    Executes GCP commands and processes the results
    """
    
    @staticmethod
    def describe_vm(vm_name: str, zone: str) -> Tuple[bool, Dict[str, Any], str]:
        """
        Execute gcloud command to describe a VM
        
        Returns:
            Tuple of (success, instance_info, error_message)
        """
        logger.info(f"Checking status for VM {vm_name} in zone {zone}")
        # Describe the VM instance
        result = subprocess.run(
            ["gcloud", "compute", "instances", "describe", vm_name, "--zone", zone],
            capture_output=True, text=True
        )
        
        if result.returncode == 0:
            # Parse the output to return only the relevant details
            output = result.stdout.split("\n")
            instance_info = {}
            
            for line in output:
                if "name" in line:
                    instance_info["name"] = line.split(":")[1].strip()
                if "status" in line:
                    instance_info["status"] = line.split(":")[1].strip()
                if "zone" in line:
                    instance_info["zone"] = line.split(":")[1].strip()

            return True, instance_info, ""
        else:
            # Extract error message
            error_message = result.stderr.split("\n")[0]
            return False, {}, error_message
    
    @staticmethod
    def start_vm(vm_name: str, zone: str) -> Tuple[bool, str]:
        """
        Execute gcloud command to start a VM
        
        Returns:
            Tuple of (success, error_message)
        """
        logger.info(f"Starting VM {vm_name} in zone {zone}")
        # Start the VM instance
        result = subprocess.run(
            ["gcloud", "compute", "instances", "start", vm_name, "--zone", zone],
            capture_output=True, text=True
        )
        
        if result.returncode == 0:
            return True, ""
        else:
            # Extract error message
            error_message = result.stderr.split("\n")[0]
            return False, error_message
    
    @staticmethod
    def stop_vm(vm_name: str, zone: str) -> Tuple[bool, str]:
        """
        Execute gcloud command to stop a VM
        
        Returns:
            Tuple of (success, error_message)
        """
        logger.info(f"Stopping VM {vm_name} in zone {zone}")
        # Stop the VM instance
        result = subprocess.run(
            ["gcloud", "compute", "instances", "stop", vm_name, "--zone", zone],
            capture_output=True, text=True
        )
        
        if result.returncode == 0:
            return True, ""
        else:
            # Extract error message
            error_message = result.stderr.split("\n")[0]
            return False, error_message
    
    @staticmethod
    def list_vms_in_zone(zone: str) -> Tuple[bool, list, str]:
        """
        List all VMs in a specific zone
        
        Returns:
            Tuple of (success, instances_list, error_message)
        """
        logger.info(f"Scanning zone {zone} for VMs...")
        
        result = subprocess.run(
            ["gcloud", "compute", "instances", "list", "--filter=zone:" + zone, "--format=json"],
            capture_output=True, text=True
        )
        
        if result.returncode == 0 and result.stdout.strip():
            instances = json.loads(result.stdout)
            return True, instances, ""
        else:
            error_message = result.stderr.split("\n")[0] if result.stderr else "Empty response"
            return False, [], error_message
            
    @staticmethod
    def extract_project_from_error(error_message: str) -> Optional[str]:
        """Extract project name from a GCP error message"""
        match = re.search(r"The resource 'projects/([^/]+)/.*?instances/([^']+)", error_message)
        if match:
            return match.group(1)
        return None
        
    @staticmethod
    def extract_instance_from_error(error_message: str) -> Optional[str]:
        """Extract instance name from a GCP error message"""
        match = re.search(r"The resource 'projects/([^/]+)/.*?instances/([^']+)", error_message)
        if match:
            return match.group(2)
        return None 