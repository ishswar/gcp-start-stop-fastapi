"""
VM Name Utilities
Handles cleaning and mapping VM names
"""
import logging

# Setup logger for this module
logger = logging.getLogger(__name__)

class VMNameManager:
    """
    Handles VM name transformations and mappings
    """
    
    def __init__(self, vanity_mappings=None, domain_suffixes=None):
        """
        Initialize the VM name manager
        
        Args:
            vanity_mappings: Dict mapping vanity names to actual hostnames
            domain_suffixes: List of domain suffixes to strip from VM names
        """
        self.vanity_to_hostname = vanity_mappings or {
            "nlq": "guedfocnlq03",
            "py-server": "guedfocdsml01",
        }
        
        self.domain_suffixes = domain_suffixes or [
            ".dev.tibco.com", ".ibi.systems", ".tibco.com"
        ]
    
    def clean_vm_name(self, vmname: str) -> str:
        """
        Clean VM name by removing known domain suffixes
        """
        if not vmname:
            return vmname
            
        # Remove any known domain suffixes
        original_name = vmname
        for suffix in self.domain_suffixes:
            if vmname.endswith(suffix):
                vmname = vmname[:-(len(suffix))]
                logger.info(f"Stripped domain suffix from VM name: {original_name} -> {vmname}")
                break
                
        return vmname

    def map_vanity_to_hostname(self, vmname: str) -> str:
        """
        Map vanity hostname to real VM name
        First clean the VM name by removing domain suffixes
        """
        # First clean the name
        vmname = self.clean_vm_name(vmname)
        
        # Check if the vmname contains a vanity prefix (like "nlq" or "py-server")
        for vanity_name, real_hostname in self.vanity_to_hostname.items():
            if vmname.startswith(vanity_name):
                logger.info(f"Mapped vanity name to real hostname: {vmname} -> {real_hostname}")
                return real_hostname
                
        return vmname  # Return the cleaned vmname if no mapping is found

    def get_vanity_name(self, vmname: str) -> str:
        """
        Get vanity name for display purposes
        """
        # First clean the name
        vmname = self.clean_vm_name(vmname)
        
        # Check if the vmname starts with a known vanity prefix
        for vanity_name in self.vanity_to_hostname.keys():
            if vmname.startswith(vanity_name):
                return f"{vanity_name}.ibi.systems"
                
        return vmname  # Return the cleaned vmname if no mapping is found 