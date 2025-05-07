import os
import logging
import threading
from datetime import datetime
from logging.handlers import RotatingFileHandler

# Thread safety lock for logger setup
_logger_lock = threading.Lock()

def setup_logging(logger_name):
    """
    Setup logging with year/month directory structure.
    Thread-safe implementation.
    
    Args:
        logger_name: The name of the logger to configure
        
    Returns:
        Configured logger instance
    """
    with _logger_lock:
        # Create base logs directory
        logs_base_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs")
        if not os.path.exists(logs_base_dir):
            os.makedirs(logs_base_dir)
        
        # Get current year and month
        now = datetime.now()
        year_dir = os.path.join(logs_base_dir, str(now.year))
        if not os.path.exists(year_dir):
            os.makedirs(year_dir)
        
        # Month directory (01-January, 02-February, etc.)
        month_name = now.strftime("%m-%B")
        month_dir = os.path.join(year_dir, month_name)
        if not os.path.exists(month_dir):
            os.makedirs(month_dir)
        
        # Log file paths
        log_file = os.path.join(month_dir, "gcp_vm_operations.log")
        stdout_log = os.path.join(month_dir, "stdout.log")
        stderr_log = os.path.join(month_dir, "stderr.log")
        
        # Configure logger
        logger = logging.getLogger(logger_name)
        logger.setLevel(logging.INFO)
        
        # Clear existing handlers if any
        if logger.handlers:
            logger.handlers.clear()
        
        # File handler with rotation (10 MB max size, keep 5 backup files)
        file_handler = RotatingFileHandler(log_file, maxBytes=10*1024*1024, backupCount=5)
        file_handler.setLevel(logging.INFO)
        
        # Console handler
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.INFO)
        
        # Stdout handler
        stdout_handler = RotatingFileHandler(stdout_log, maxBytes=10*1024*1024, backupCount=5)
        stdout_handler.setLevel(logging.INFO)
        
        # Stderr handler
        stderr_handler = RotatingFileHandler(stderr_log, maxBytes=10*1024*1024, backupCount=5)
        stderr_handler.setLevel(logging.ERROR)
        
        # Create formatter
        formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        file_handler.setFormatter(formatter)
        console_handler.setFormatter(formatter)
        stdout_handler.setFormatter(formatter)
        stderr_handler.setFormatter(formatter)
        
        # Add handlers to the logger
        logger.addHandler(file_handler)
        logger.addHandler(console_handler)
        logger.addHandler(stdout_handler)
        logger.addHandler(stderr_handler)
        
        return logger
    
    
    """
    Setup logging with year/month directory structure.
    Thread-safe implementation.
    
    Args:
        logger_name: The name of the logger to configure
        
    Returns:
        Configured logger instance
    """
    with _logger_lock:
        # Create base logs directory
        logs_base_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs")
        if not os.path.exists(logs_base_dir):
            os.makedirs(logs_base_dir)
        
        # Get current year and month
        now = datetime.now()
        year_dir = os.path.join(logs_base_dir, str(now.year))
        if not os.path.exists(year_dir):
            os.makedirs(year_dir)
        
        # Month directory (01-January, 02-February, etc.)
        month_name = now.strftime("%m-%B")
        month_dir = os.path.join(year_dir, month_name)
        if not os.path.exists(month_dir):
            os.makedirs(month_dir)
        
        # Log file path
        log_file = os.path.join(month_dir, "gcp_vm_operations.log")
        
        # Configure logger
        logger = logging.getLogger(logger_name)
        logger.setLevel(logging.INFO)
        
        # Clear existing handlers if any
        if logger.handlers:
            logger.handlers.clear()
        
        # File handler with rotation (10 MB max size, keep 5 backup files)
        file_handler = RotatingFileHandler(log_file, maxBytes=10*1024*1024, backupCount=5)
        file_handler.setLevel(logging.INFO)
        
        # Console handler
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.INFO)
        
        # Create formatter
        formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        file_handler.setFormatter(formatter)
        console_handler.setFormatter(formatter)
        
        # Add handlers to the logger
        logger.addHandler(file_handler)
        logger.addHandler(console_handler)
        
        return logger

def get_logger():
    """
    Get or create a logger instance with the current date structure.
    """
    return setup_logging(__name__) 