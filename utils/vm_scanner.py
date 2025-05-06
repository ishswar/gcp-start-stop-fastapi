"""
VM Scanner Module
Scans GCP for VMs and updates the cache
"""
import logging
from datetime import datetime
import time
import threading
from typing import Dict, Any

from vm_cache import VMCache
from zone_manager import ZoneManager
from gcp_commands import GCPCommandExecutor

# Setup logger for this module
logger = logging.getLogger(__name__)

class VMScanner:
    """
    Scans GCP for VMs and updates the cache
    """
    
    def __init__(self, vm_cache: VMCache, zone_manager: ZoneManager):
        """
        Initialize the VM scanner
        
        Args:
            vm_cache: The VM cache manager to update
            zone_manager: The zone manager to use for zone discovery
        """
        self.vm_cache = vm_cache
        self.zone_manager = zone_manager
        self.gcp = GCPCommandExecutor()
        self.scanner_thread = None
    
    def update_vm_cache(self) -> int:
        """
        Scans all zones and builds a cache of VM names to zones
        
        Returns:
            Number of VMs found
        """
        logger.info(f"Starting VM cache update for regions: {', '.join(self.zone_manager.target_regions)}...")
        new_cache = {}
        zones_scanned = 0
        vms_found = 0
        
        # Get current project
        project = self.zone_manager.get_current_project()
        if not project:
            logger.error("Failed to get current project, cache update aborted")
            return 0
            
        logger.info(f"Current project: {project}")
        
        # Get all zones dynamically
        zones = self.zone_manager.get_all_zones()
        
        # For each zone, list VMs
        for zone in zones:
            zones_scanned += 1
            
            success, instances, error = self.gcp.list_vms_in_zone(zone)
            if success:
                for instance in instances:
                    vm_name = instance.get("name")
                    vm_zone = instance.get("zone", "").split("/")[-1]
                    vm_status = instance.get("status")
                    
                    if vm_name:
                        vms_found += 1
                        new_cache[vm_name] = {
                            "zone": vm_zone,
                            "status": vm_status,
                            "project": project
                        }
                        logger.info(f"Found VM: {vm_name} in zone {vm_zone} (status: {vm_status})")
            else:
                logger.error(f"Error scanning zone {zone}: {error}")
        
        # Update the cache
        self.vm_cache.update(new_cache)
        
        # Save to disk
        self.vm_cache.save_to_disk()
        
        logger.info(f"VM cache update completed. Scanned {zones_scanned} zones, found {vms_found} VMs.")
        return vms_found
    
    def start_background_updates(self, interval_seconds: int = 3600):
        """
        Start a background thread for periodic cache updates
        
        Args:
            interval_seconds: How often to update the cache (in seconds)
        """
        def periodic_update():
            while True:
                # Sleep first to avoid duplicate scan at startup
                time.sleep(interval_seconds)
                try:
                    self.update_vm_cache()
                except Exception as e:
                    logger.exception(f"Error in background VM cache update: {str(e)}")
        
        self.scanner_thread = threading.Thread(
            target=periodic_update,
            daemon=True
        )
        self.scanner_thread.start()
        
        logger.info(f"Background VM cache update thread started (refresh interval: {interval_seconds//60} minutes)") 