"""
Zone Manager Module
Handles discovering and managing GCP zones
"""
import subprocess
import json
import logging
from typing import List

# Setup logger for this module
logger = logging.getLogger(__name__)

class ZoneManager:
    """Handles discovery and management of GCP zones"""
    
    def __init__(self, target_regions=None):
        """
        Initialize the zone manager
        
        Args:
            target_regions: List of region prefixes to filter zones (e.g. ["us-", "asia-"])
        """
        self.target_regions = target_regions or ["us-", "asia-"]
        self.fallback_zones = [
            "us-central1-a", "us-central1-b", "us-east1-b", 
            "asia-east1-a", "asia-southeast1-a"
        ]
    
    def get_all_zones(self) -> List[str]:
        """
        Dynamically discover all available zones in the target regions.
        Returns a list of zone names.
        """
        zones = []
        try:
            # Get all zones from gcloud
            result = subprocess.run(
                ["gcloud", "compute", "zones", "list", "--format=json"],
                capture_output=True, text=True
            )
            
            if result.returncode == 0 and result.stdout.strip():
                all_zones = json.loads(result.stdout)
                
                # Filter zones that match our target regions
                for zone_info in all_zones:
                    zone_name = zone_info.get("name", "")
                    if any(zone_name.startswith(region) for region in self.target_regions):
                        zones.append(zone_name)
                
                logger.info(f"Discovered {len(zones)} zones in {', '.join(self.target_regions)} regions")
            else:
                logger.error(f"Failed to get zones list: {result.stderr}")
                zones = self.fallback_zones
                logger.warning(f"Using fallback zone list: {zones}")
        
        except Exception as e:
            logger.exception(f"Error getting zones list: {str(e)}")
            zones = self.fallback_zones
            logger.warning(f"Using fallback zone list due to error: {zones}")
        
        return zones
    
    def get_current_project(self) -> str:
        """Get the current GCP project"""
        try:
            result = subprocess.run(
                ["gcloud", "config", "get-value", "project"],
                capture_output=True, text=True
            )
            if result.returncode != 0:
                logger.error(f"Failed to get current project: {result.stderr}")
                return ""
            
            project = result.stdout.strip()
            return project
            
        except Exception as e:
            logger.exception(f"Error getting current project: {str(e)}")
            return "" 