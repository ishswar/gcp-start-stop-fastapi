"""
VM Cache Management Module
Handles caching and persistence of GCP VM data
"""
import os
import pickle
import threading
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple
import asyncio
import subprocess
import time

# Default values
CACHE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "vm_cache.pickle")
CACHE_MAX_AGE_HOURS = 1  # Maximum age of cache file to be considered valid

# Setup logger for this module
logger = logging.getLogger(__name__)

class VMCache:
    """Manages the VM cache with thread-safe persistence"""
    
    def __init__(self, cache_file=CACHE_FILE, max_age_hours=CACHE_MAX_AGE_HOURS):
        """Initialize the VM cache manager"""
        self.cache_file = cache_file
        self.max_age_hours = max_age_hours
        self.vm_cache: Dict[str, Dict[str, Any]] = {}
        self.vm_zone_map: Dict[str, str] = {}
        self.last_update = datetime.min
        self.lock = threading.Lock()
        self.refresh_task = None
        self.refresh_interval_seconds = max_age_hours * 3600  # Convert hours to seconds
    
    async def initialize(self):
        """Initialize the VM cache on startup"""
        logger.info("Initializing VM cache...")
        
        # Try to load from pickle file if it exists and is recent
        if self._load_from_pickle():
            logger.info("Loaded VM cache from pickle file")
        else:
            # If pickle loading failed or cache is old, update cache
            await self.update_cache()
            
        # Start the periodic refresh task
        self.start_refresh_task()
    
    def start_refresh_task(self):
        """Start a background task to periodically refresh the cache"""
        if self.refresh_task is not None:
            # Task already running
            return
            
        # Create and start the background refresh task
        self.refresh_task = asyncio.create_task(self._periodic_refresh())
        logger.info(f"Started periodic cache refresh task (interval: {self.max_age_hours} hours)")
        
    async def _periodic_refresh(self):
        """Background task to periodically refresh the cache"""
        try:
            while True:
                # Calculate time until next refresh
                with self.lock:
                    time_since_update = datetime.now() - self.last_update
                    seconds_until_refresh = max(
                        0, 
                        self.refresh_interval_seconds - time_since_update.total_seconds()
                    )
                
                # If it's been at least 75% of the refresh interval, schedule refresh soon
                if seconds_until_refresh < (self.refresh_interval_seconds * 0.25):
                    seconds_until_refresh = 60  # Refresh in 1 minute
                    
                logger.info(f"Next cache refresh in {seconds_until_refresh/60:.1f} minutes")
                
                # Wait until next refresh time
                await asyncio.sleep(seconds_until_refresh)
                
                # Perform the refresh
                logger.info(f"Periodic refresh triggered after {seconds_until_refresh/60:.1f} minute wait")
                try:
                    await self.update_cache()
                except Exception as e:
                    logger.error(f"Error during scheduled cache refresh: {e}", exc_info=True)
                    
                # Wait at least 30 seconds between refresh attempts (avoid too frequent updates on errors)
                await asyncio.sleep(30)
                
        except asyncio.CancelledError:
            logger.info("Cache refresh task was cancelled")
        except Exception as e:
            logger.error(f"Cache refresh task failed with error: {e}", exc_info=True)
            # Restart the task if it fails
            asyncio.create_task(self._restart_refresh_task())
            
    async def _restart_refresh_task(self):
        """Restart the refresh task after a delay if it fails"""
        await asyncio.sleep(60)  # Wait a minute before restarting
        logger.info("Restarting failed cache refresh task")
        self.refresh_task = None
        self.start_refresh_task()
            
    def stop_refresh_task(self):
        """Stop the periodic refresh task"""
        if self.refresh_task is not None:
            self.refresh_task.cancel()
            self.refresh_task = None
            logger.info("Stopped periodic cache refresh task")
    
    def _load_from_pickle(self) -> bool:
        """Load cache from pickle file if it exists and is recent"""
        try:
            if not os.path.exists(self.cache_file):
                return False

            with open(self.cache_file, 'rb') as f:
                cached_data = pickle.load(f)
                cache_time = cached_data.get('timestamp')
                
                # Check if cache is less than 1 hour old
                if cache_time and (datetime.now() - cache_time).total_seconds() < 3600:
                    self.vm_zone_map = cached_data.get('vm_zone_map', {})
                    self.last_update = cache_time
                    return True
                return False
        except Exception as e:
            logger.error(f"Error loading pickle cache: {e}")
            return False
    
    def _save_to_pickle(self):
        """Save current cache to pickle file"""
        try:
            cache_data = {
                'vm_zone_map': self.vm_zone_map,
                'timestamp': datetime.now()
            }
            with open(self.cache_file, 'wb') as f:
                pickle.dump(cache_data, f)
        except Exception as e:
            logger.error(f"Error saving pickle cache: {e}")
    
    async def update_cache(self):
        """Update the VM zone cache"""
        logger.info("Updating VM zone cache...")
        self.vm_zone_map.clear()
        
        zones_found = 0
        vm_count_by_zone = {}

        try:
            # Get list of all zones in us-* and asia-* regions
            zones_cmd = ["gcloud", "compute", "zones", "list", "--filter=name~'^(us-|asia-)'", "--format=value(name)"]
            logger.debug(f"Executing command: {' '.join(zones_cmd)}")
            
            zones_process = await asyncio.create_subprocess_exec(
                *zones_cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )
            zones_output, zones_error = await zones_process.communicate()
            
            if zones_process.returncode != 0:
                logger.error(f"Error getting zones: {zones_error.decode() if zones_error else 'Unknown error'}")
                return
            
            zones = [z for z in zones_output.decode().strip().split('\n') if z]
            zones_found = len(zones)
            
            if not zones:
                logger.error("No zones found! Check GCP authentication and permissions")
                return
            
            logger.info(f"Found {zones_found} zones matching filter criteria")

            # For each zone, get VM instances
            for zone in zones:
                logger.info(f"Scanning zone: {zone}")
                cmd = ["gcloud", "compute", "instances", "list", f"--zones={zone}", "--format=value(name)"]
                logger.debug(f"Executing command: {' '.join(cmd)}")
                
                process = await asyncio.create_subprocess_exec(
                    *cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE
                )
                output, error = await process.communicate()
                
                if process.returncode != 0:
                    logger.error(f"Error scanning zone {zone}: {error.decode() if error else 'Unknown error'}")
                    continue
                
                zone_vms = []
                if output:
                    vms = [vm for vm in output.decode().strip().split('\n') if vm]
                    for vm in vms:
                        # Store both the original VM name and lowercase version for case-insensitive lookup
                        self.vm_zone_map[vm] = zone
                        self.vm_zone_map[vm.lower()] = zone  # Add lowercase version for case-insensitive lookup
                        zone_vms.append(vm)
                
                # Log VMs found in this zone
                vm_count_by_zone[zone] = len(zone_vms)
                if zone_vms:
                    logger.info(f"Zone {zone}: Found {len(zone_vms)} VMs: {', '.join(zone_vms)}")
                else:
                    logger.info(f"Zone {zone}: No VMs found")

            self.last_update = datetime.now()
            
            # If we found any VMs, save the cache
            if self.vm_zone_map:
                self._save_to_pickle()
                logger.info(f"Cache updated and saved to {self.cache_file}")
            else:
                logger.warning("No VMs found across any zone! Cache not saved.")
                return
            
            # Log summary information
            total_vms = len(set(vm.lower() for vm in self.vm_zone_map.keys())) // 2  # Divide by 2 because we store both original and lowercase
            non_empty_zones = sum(1 for count in vm_count_by_zone.values() if count > 0)
            logger.info(f"Cache update complete - Total: {total_vms} VMs across {non_empty_zones}/{zones_found} zones")
            
            # Log distribution of VMs by zone
            for zone, count in sorted(vm_count_by_zone.items(), key=lambda x: x[1], reverse=True):
                if count > 0:
                    logger.info(f"  - {zone}: {count} VMs")

        except Exception as e:
            logger.error(f"Error updating VM cache: {e}", exc_info=True)
            # Don't raise the exception - just log it to prevent app crash
    
    def save_to_disk(self) -> bool:
        """
        Save the VM cache to disk using pickle
        Returns True if successful
        """
        try:
            with self.lock:
                if not self.vm_cache:
                    logger.warning("Not saving empty VM cache to disk")
                    return False
                
                cache_data = {
                    "timestamp": self.last_update,
                    "vm_cache": self.vm_cache
                }
                
                with open(self.cache_file, 'wb') as f:
                    pickle.dump(cache_data, f)
                    
                logger.info(f"VM cache saved to disk: {self.cache_file} ({len(self.vm_cache)} VMs)")
                return True
                
        except Exception as e:
            logger.error(f"Failed to save VM cache to disk: {str(e)}")
            return False
    
    def load_from_disk(self) -> bool:
        """
        Load VM cache from disk if available and not too old
        Returns True if cache was loaded successfully
        """
        if not os.path.exists(self.cache_file):
            logger.info(f"No VM cache file found at {self.cache_file}")
            return False
            
        try:
            # Check file modification time as a quick check
            file_mod_time = datetime.fromtimestamp(os.path.getmtime(self.cache_file))
            file_age = datetime.now() - file_mod_time
            
            if file_age > timedelta(hours=self.max_age_hours):
                logger.info(f"VM cache file is too old ({file_age.total_seconds()/3600:.1f} hours), will refresh")
                return False
                
            with open(self.cache_file, 'rb') as f:
                cache_data = pickle.load(f)
                
            # Verify timestamp in the file
            cached_timestamp = cache_data.get("timestamp")
            if not cached_timestamp:
                logger.warning("Invalid cache file format (missing timestamp)")
                return False
                
            cache_age = datetime.now() - cached_timestamp
            if cache_age > timedelta(hours=self.max_age_hours):
                logger.info(f"VM cache data is too old ({cache_age.total_seconds()/3600:.1f} hours), will refresh")
                return False
                
            # Load the cache data
            cached_vms = cache_data.get("vm_cache", {})
            if not cached_vms:
                logger.warning("Empty VM cache in file")
                return False
                
            with self.lock:
                self.vm_cache = cached_vms
                self.last_update = cached_timestamp
                
            logger.info(f"Loaded VM cache from disk: {len(self.vm_cache)} VMs, age: {cache_age.total_seconds()/60:.1f} minutes")
            return True
            
        except Exception as e:
            logger.error(f"Failed to load VM cache from disk: {str(e)}")
            return False
    
    def update(self, new_cache: Dict[str, Dict[str, Any]]) -> None:
        """Update the cache with new data"""
        with self.lock:
            self.vm_cache = new_cache
            self.last_update = datetime.now()
    
    async def update_if_needed(self):
        """Check if cache needs updating and update if necessary"""
        with self.lock:
            cache_age = datetime.now() - self.last_update
            if cache_age > timedelta(hours=self.max_age_hours):
                logger.info(f"Cache is {cache_age.total_seconds() / 3600:.1f} hours old. Auto-refreshing...")
                
        # Release lock before potentially long update operation
        await self.update_cache()
        return True

    def get_vm_zone(self, vm_name: str) -> Optional[str]:
        """Get a VM's zone from the cache, case-insensitive"""
        if not vm_name:
            logger.error("Attempted to get zone for empty VM name")
            return None
        
        # Remove domain if present
        clean_vm_name = vm_name.split('.')[0]
        logger.info(f"Looking up zone for VM {clean_vm_name} (original: {vm_name})")
        
        with self.lock:
            # Check if cache needs refresh
            cache_age = datetime.now() - self.last_update
            if cache_age > timedelta(hours=self.max_age_hours):
                logger.warning(f"Cache is stale ({cache_age.total_seconds() / 3600:.1f} hours old). Will schedule refresh after this request.")
                # Don't refresh now - that would block the request
                # Instead, schedule refresh to run in background
                asyncio.create_task(self.update_cache())
            
            # Try exact match first
            if clean_vm_name in self.vm_zone_map:
                zone = self.vm_zone_map[clean_vm_name]
                logger.info(f"Found VM {clean_vm_name} in zone {zone}")
                return zone
            
            # Try case-insensitive match
            lower_vm_name = clean_vm_name.lower()
            if lower_vm_name in self.vm_zone_map:
                zone = self.vm_zone_map[lower_vm_name]
                logger.info(f"Found VM {clean_vm_name} (case-insensitive) in zone {zone}")
                return zone
            
            # Try partial match (in case VM name has a prefix or suffix)
            for vm, zone in self.vm_zone_map.items():
                if clean_vm_name in vm or vm in clean_vm_name:
                    logger.info(f"Found VM {clean_vm_name} by partial match with {vm} in zone {zone}")
                    return zone
                
            # VM not found
            cached_vms = len(set(k.lower() for k in self.vm_zone_map.keys())) // 2 if self.vm_zone_map else 0
            logger.warning(f"VM {clean_vm_name} not found in cache. Cache contains {cached_vms} VMs.")
            
            # Log when the cache was last updated
            logger.info(f"Cache was last updated {cache_age.total_seconds() / 60:.1f} minutes ago")
            
            # Schedule a refresh for next time
            if cached_vms == 0 or cache_age > timedelta(minutes=30):
                logger.info("Scheduling cache refresh in background due to cache miss")
                asyncio.create_task(self.update_cache())
            
            return None
    
    def get_vm_info(self, vm_name: str) -> Optional[Dict[str, Any]]:
        """Get all VM info from the cache"""
        with self.lock:
            return self.vm_cache.get(vm_name)
        
    def get_all_vms(self) -> Dict[str, Dict[str, Any]]:
        """Get all VMs in the cache"""
        with self.lock:
            return self.vm_cache.copy()
    
    def is_cache_stale(self, max_age_minutes: int = None) -> bool:
        """Check if cache is older than specified minutes"""
        if max_age_minutes is None:
            max_age_minutes = self.max_age_hours * 60
            
        with self.lock:
            cache_age = datetime.now() - self.last_update
            return cache_age > timedelta(minutes=max_age_minutes)
    
    def get_cache_age(self) -> timedelta:
        """Get the age of the cache"""
        with self.lock:
            return datetime.now() - self.last_update
            
    def update_vm_status(self, vm_name: str, status: str) -> bool:
        """Update a VM's status in the cache"""
        with self.lock:
            if vm_name in self.vm_cache:
                self.vm_cache[vm_name]["status"] = status
                return True
        return False

    def get_status(self) -> dict:
        """Get cache status"""
        return {
            "last_update": self.last_update.isoformat() if self.last_update else None,
            "cached_vms": len(self.vm_zone_map)
        } 