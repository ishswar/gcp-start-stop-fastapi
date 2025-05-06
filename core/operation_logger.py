"""
Operation Logger Module
Handles logging of VM operations to CSV files organized by month
"""
import csv
import os
from datetime import datetime
from typing import Optional
import logging
import inspect

class OperationLogger:
    def __init__(self, base_dir=None):
        # If not specified, place logs in the same directory as this file
        if base_dir is None:
            # Get the directory where this file is located
            current_file_dir = os.path.dirname(os.path.abspath(inspect.getfile(inspect.currentframe())))
            self.base_dir = os.path.join(current_file_dir, "logs", "operations")
        else:
            self.base_dir = base_dir
            
        self.logger = logging.getLogger(__name__)
        self._ensure_log_directory()
        self.logger.info(f"Operation logs will be stored in: {self.base_dir}")

    def _ensure_log_directory(self):
        """Ensure log directories exist"""
        if not os.path.exists(self.base_dir):
            os.makedirs(self.base_dir, exist_ok=True)
            self.logger.info(f"Created operations log directory: {self.base_dir}")

    def _get_log_path(self, timestamp: datetime) -> str:
        """Get path for the current month's log file"""
        year_dir = os.path.join(self.base_dir, str(timestamp.year))
        if not os.path.exists(year_dir):
            os.makedirs(year_dir, exist_ok=True)
        
        return os.path.join(year_dir, f"operations_{timestamp.strftime('%Y_%m')}.csv")

    def _ensure_csv_headers(self, filepath: str):
        """Ensure CSV file exists with headers"""
        headers = ['timestamp', 'vm_name', 'operation', 'client_ip', 'zone', 'status', 'vanity_name']
        
        if not os.path.exists(filepath):
            self.logger.info(f"Creating new operations log file: {filepath}")
            with open(filepath, 'w', newline='') as f:
                writer = csv.writer(f)
                writer.writerow(headers)

    def log_operation(self, timestamp: datetime, vm_name: str, operation: str, 
                     client_ip: str, zone: Optional[str], status: str, vanity_name: str = None):
        """Log an operation to the appropriate CSV file"""
        try:
            log_path = self._get_log_path(timestamp)
            self._ensure_csv_headers(log_path)

            with open(log_path, 'a', newline='') as f:
                writer = csv.writer(f)
                writer.writerow([
                    timestamp.isoformat(),
                    vm_name,
                    operation,
                    client_ip,
                    zone or 'unknown',
                    status,
                    vanity_name or vm_name
                ])
            
            self.logger.info(f"Operation logged to CSV: {operation} on {vm_name} - {status}")
            return log_path
        except Exception as e:
            self.logger.error(f"Error logging operation to CSV: {e}")
            return None
            
    def get_recent_operations(self, limit=10):
        """Get most recent operations from log files"""
        try:
            # Find the most recent log file
            all_years = [d for d in os.listdir(self.base_dir) if os.path.isdir(os.path.join(self.base_dir, d))]
            if not all_years:
                return []
                
            most_recent_year = max(all_years)
            year_dir = os.path.join(self.base_dir, most_recent_year)
            
            # Find most recent month file
            log_files = [f for f in os.listdir(year_dir) if f.startswith("operations_") and f.endswith(".csv")]
            if not log_files:
                return []
                
            most_recent_file = max(log_files)
            log_path = os.path.join(year_dir, most_recent_file)
            
            # Read entries from file
            entries = []
            with open(log_path, 'r', newline='') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    entries.append(row)
            
            # Return most recent entries
            return sorted(entries, key=lambda x: x['timestamp'], reverse=True)[:limit]
            
        except Exception as e:
            self.logger.error(f"Error retrieving recent operations: {e}")
            return [] 