"""Logger - Centralized logging"""
import logging
import os
from datetime import datetime

class Logger:
    def __init__(self, name: str, log_file: str = "logs/dcomet.log", level: str = "INFO"):
        self.logger = logging.getLogger(name)
        self.logger.setLevel(getattr(logging, level))
        
        # Create logs directory if not exists
        os.makedirs(os.path.dirname(log_file), exist_ok=True)
        
        # File handler
        fh = logging.FileHandler(log_file)
        fh.setLevel(getattr(logging, level))
        
        # Console handler
        ch = logging.StreamHandler()
        ch.setLevel(getattr(logging, level))
        
        # Formatter
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        fh.setFormatter(formatter)
        ch.setFormatter(formatter)
        
        self.logger.addHandler(fh)
        self.logger.addHandler(ch)
    
    def info(self, msg: str, **kwargs):
        self.logger.info(msg, **kwargs)
    
    def warning(self, msg: str, **kwargs):
        self.logger.warning(msg, **kwargs)
    
    def error(self, msg: str, **kwargs):
        self.logger.error(msg, **kwargs)
    
    def debug(self, msg: str, **kwargs):
        self.logger.debug(msg, **kwargs)

# Global logger instance
_logger = None

def get_logger(name: str, log_file: str = "logs/dcomet.log", level: str = "INFO") -> Logger:
    """Get or create logger instance"""
    global _logger
    if _logger is None:
        _logger = Logger(name, log_file, level)
    return _logger
