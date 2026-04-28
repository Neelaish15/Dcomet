"""Power Calculator - Normalized power calculations for any scale"""

class PowerCalculator:
    """
    Normalizes power calculations to work at any scale.
    Same logic for 10W prototype and 1MW industrial system.
    """
    
    def __init__(self, config):
        self.config = config
        self.normalization = config.get('power_system.normalization_factor', 1.0)
        self.base_power_mva = config.get('power_system.base_power_mva', 0.00001)
        self.base_voltage_kv = config.get('power_system.base_voltage_kv', 12)
    
    def normalize_power(self, power_watts: float) -> float:
        """Convert actual watts to normalized PU (per-unit) values"""
        if self.base_power_mva == 0:
            return 0
        return (power_watts * self.normalization) / (self.base_power_mva * 1_000_000)
    
    def denormalize_power(self, power_pu: float) -> float:
        """Convert normalized PU back to actual watts"""
        if self.normalization == 0:
            return 0
        return (power_pu * self.base_power_mva * 1_000_000) / self.normalization
    
    def calculate_available_power(self, der_output_w: float) -> float:
        """Calculate how much power DER can provide to market"""
        return max(0, der_output_w)
    
    def calculate_excess_power(self, der_output_w: float, der_load_w: float) -> float:
        """Calculate how much excess power DER has"""
        excess = max(0, der_output_w - der_load_w)
        return excess
    
    def check_line_loading(self, injected_power_w: float, line_capacity_w: float) -> tuple:
        """
        Check if line can handle injected power.
        Returns (is_safe, loading_percent)
        """
        if line_capacity_w == 0:
            return False, 0
        
        loading_percent = (injected_power_w / line_capacity_w) * 100
        max_allowed = self.config.get('trading.constraints.max_line_loading_percent', 85)
        
        is_safe = loading_percent <= max_allowed
        return is_safe, loading_percent
    
    def check_voltage_within_tolerance(self, voltage_pu: float) -> tuple:
        """
        Check if voltage is within acceptable range.
        Returns (is_valid, voltage_deviation_percent)
        """
        nominal = 1.0
        deviation = abs(voltage_pu - nominal) / nominal * 100
        tolerance = self.config.get('power_system.voltage_tolerance_percent', 10)
        
        is_valid = deviation <= tolerance
        return is_valid, deviation
    
    def calculate_trade_price(self, quantity_wh: float) -> float:
        """Calculate price for energy trade"""
        price_per_wh = self.config.get('trading.price_per_unit_usd_per_wh', 0.50)
        return quantity_wh * price_per_wh
