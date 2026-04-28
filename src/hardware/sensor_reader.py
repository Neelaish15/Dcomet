"""Sensor Reader - Reads from Arduino or simulator"""
import math
import time
from typing import Dict

class SensorReader:
    """
    Abstracts Arduino/Simulator inputs.
    Reads real sensors OR simulated data - same interface.
    """
    
    def __init__(self, config, der_id: int = 1):
        self.config = config
        self.der_id = der_id
        self.arduino_enabled = config.get('hardware.arduino.enabled', False)
        self.simulation_enabled = config.get('hardware.simulation.enabled', True)
        self.start_time = time.time()
        
        if self.arduino_enabled:
            try:
                import serial
                port = config.get('hardware.arduino.port', 'COM3')
                baudrate = config.get('hardware.arduino.baudrate', 9600)
                self.serial = serial.Serial(port, baudrate)
            except Exception as e:
                print(f"Failed to connect to Arduino: {e}")
                self.arduino_enabled = False
                self.simulation_enabled = True
    
    def read_der_data(self) -> Dict[str, float]:
        """
        Read DER data (current, voltage, power)
        Returns: {current_a, voltage_v, power_w}
        """
        if self.arduino_enabled:
            try:
                line = self.serial.readline().decode('utf-8').strip()
                if line:
                    parts = line.split(',')
                    if len(parts) >= 2:
                        current_raw = int(parts[0])
                        voltage_raw = int(parts[1])
                        
                        # Convert from 0-1024 analog to actual values
                        # Assuming: 0-1024 maps to 0-20A and 0-25V
                        current_a = (current_raw / 1024) * 20
                        voltage_v = (voltage_raw / 1024) * 25
                        power_w = current_a * voltage_v
                        
                        return {
                            'current_a': current_a,
                            'voltage_v': voltage_v,
                            'power_w': max(0, power_w)
                        }
            except Exception as e:
                print(f"Arduino read error: {e}")
                self.arduino_enabled = False
                self.simulation_enabled = True
        
        # Fallback to simulation
        if self.simulation_enabled:
            return self._simulate_der_power()
        
        return {'current_a': 0, 'voltage_v': 12, 'power_w': 0}
    
    def _simulate_der_power(self) -> Dict[str, float]:
        """Generate realistic simulated power output"""
        profile_key = f'hardware.simulation.der_{self.der_id}_power_profile'
        profile = self.config.get(profile_key, 'variable')
        
        elapsed = time.time() - self.start_time
        
        if profile == "sunny":
            # Sunny day: 0-10W (sine wave over ~1 hour cycle)
            power_w = 10 * max(0, math.sin(elapsed / 3600))
            
        elif profile == "variable":
            # Variable: sine + random variation
            power_w = 8 * max(0, math.sin(elapsed / 3600) + 0.2 * math.sin(elapsed / 120))
            
        elif profile == "steady":
            # Steady: constant 70% of capacity
            capacity = self.config.get(f'der_config.der_{self.der_id}.rated_capacity_w', 10)
            power_w = capacity * 0.7
            
        else:
            power_w = 0
        
        # Add some noise
        import random
        power_w += random.uniform(-0.5, 0.5)
        power_w = max(0, power_w)
        
        # Calculate current and voltage (assuming 12V system)
        voltage_v = 12.0
        current_a = power_w / voltage_v if voltage_v > 0 else 0
        
        return {
            'current_a': current_a,
            'voltage_v': voltage_v,
            'power_w': power_w
        }
    
    def close(self):
        """Close serial connection if open"""
        if self.arduino_enabled and hasattr(self, 'serial'):
            self.serial.close()
