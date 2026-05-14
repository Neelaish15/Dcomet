#!/usr/bin/env python3
import sys, time, json
from typing import Dict, List
from datetime import datetime

sys.path.insert(0, 'src')

from core.config_loader import get_config
from core.power_calculator import PowerCalculator
from core.grid_engine import GridEngine
from hardware.sensor_reader import SensorReader
from beckn.trading_engine import TradingEngine, BecknBPP, BecknBAP
from agents.agent_manager import AgentManager
from utils.logger import get_logger

class DcometSystem:
    def __init__(self, config_path: str = "config/scenarios/demo_realistic_3kw_plus.yaml"):
        print(f"\n{'='*60}\nDCOMET - Beckn P2P Energy Trading System\nDemo: Realistic Solar (3kW+)\n{'='*60}\n")
        self.config = get_config(config_path)
        self.logger = get_logger("dcomet", level=self.config.get('logging.level', 'INFO'))
        self.logger.info("Initializing System...")
        self.power_calc = PowerCalculator(self.config)
        self.grid_engine = GridEngine(self.config.get('grid.file', 'config/grid_profiles/simple_4bus.yaml'))
        self.trading_engine = TradingEngine(self.config)
        self.agent_manager = AgentManager(self.config)
        self.sensor_readers = {}
        num_ders = self.config.get('der_config.num_ders', 3)
        for i in range(1, num_ders + 1):
            self.sensor_readers[f'der_{i}'] = SensorReader(self.config, i)
        self.beckn_bpps = {}
        self.beckn_baps = {}
        for i in range(1, num_ders + 1):
            der_name = self.config.get(f'der_config.der_{i}.name', f'DER {i}')
            capacity = self.config.get(f'der_config.der_{i}.rated_capacity_w', 10)
            self.beckn_bpps[f'der_{i}'] = BecknBPP(f'der_{i}', der_name, capacity)
        num_consumers = self.config.get('loads_config.num_loads', 1)
        for i in range(1, num_consumers + 1):
            consumer_name = self.config.get(f'loads_config.load_{i}.name', f'Consumer {i}')
            self.beckn_baps[f'consumer_{i}'] = BecknBAP(f'consumer_{i}', consumer_name)
        self.cycle = 0
        self.logger.info("System Ready!")
    
    def read_der_data(self) -> Dict[str, Dict]:
        der_data = {}
        for der_id, reader in self.sensor_readers.items():
            data = reader.read_der_data()
            der_data[der_id] = data
        return der_data
    
    def calculate_available_power(self, der_data: Dict) -> Dict[str, float]:
        available = {}
        for der_id, data in der_data.items():
            power_w = data['power_w']
            available_for_trading = power_w * 0.7
            available[der_id] = max(0, available_for_trading)
        return available
    
    def run_trading_cycle(self, cycle_num: int = 0):
        print(f"\n{'-'*60}\nTRADING CYCLE #{cycle_num + 1}\nTime: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n{'-'*60}")
        self.cycle = cycle_num
        self.logger.info("[1] Reading DER sensor data...")
        der_data = self.read_der_data()
        print("\n[DER Power Generation]")
        for der_id, data in der_data.items():
            print(f"  {der_id}: {data['power_w']:.2f}W @ {data['voltage_v']:.1f}V")
        available_power = self.calculate_available_power(der_data)
        print("\n[Available for Trading]")
        total_available = 0
        for der_id, power_w in available_power.items():
            print(f"  {der_id}: {power_w:.2f}W")
            total_available += power_w
        print(f"  TOTAL: {total_available:.2f}W")
        
        self.logger.info("[2] AI agents deciding (logic-based + ML)...")
        print("\n[Agent Decision Making]")
        
        # Prepare system state for agents
        num_consumers = self.config.get('loads_config.num_loads', 1)
        consumer_demand = {f'consumer_{i}': 2.5 + i * 0.5 for i in range(1, num_consumers + 1)}
        total_demand = sum(consumer_demand.values())
        
        system_state = {
            'voltage_pu': 1.0,
            'frequency_hz': 50.0,
            'line_loading_pct': 15.0,
            'consumer_demand_w': consumer_demand,
            'total_budget_spent': 0,
            'timestamp': datetime.now().isoformat()
        }
        
        # Update agents with measurements
        self.agent_manager.update_system_measurements(der_data, system_state)
        
        # Run orchestration with logic-based agents
        decisions = self.agent_manager.orchestrate_trading_cycle(system_state)
        
        print("\n[DER Offers]")
        for offer in decisions['der_decisions']:
            print(f"  {offer['der_id']}: {offer['quantity_w']:.2f}W @ ${offer['price_usd']:.3f}/W")
        
        print("\n[Consumer Requests]")
        for req in decisions['consumer_decisions']:
            print(f"  {req['consumer_id']}: {req['quantity_w']:.2f}W (max ${req['max_price']:.3f})")
        
        print("\n[Executed Trades]")
        for trade in decisions['executed_trades']:
            print(f"  [{trade['trade_id']}] {trade['seller_id']} -> {trade['buyer_id']}: {trade['quantity_kwh']:.5f} kWh @ ${trade['price_usd']:.3f}")
        
        print("\n[ML Insights]")
        ml_insights = decisions['ml_insights']
        print(f"  Solar Prediction Confidence: {ml_insights['solar_prediction_confidence']:.1%}")
        print(f"  Demand Model Trained: {ml_insights['demand_model_trained']}")
        total_cycles_trained = ml_insights.get('cycle_count', ml_insights.get('cycles_trained', 0))
        print(f"  Total Cycles Trained: {total_cycles_trained}")
        
        # Store trades for API and summary
        for trade in decisions['executed_trades']:
            self.trading_engine.active_trades[trade['trade_id']] = trade
        
        self.logger.info("[3] Power flow simulation...")
        pf_results = self.grid_engine.run_power_flow()
        print("\n[Power Flow Results]")
        if pf_results['converged']:
            print("  [OK] Power flow converged")
        else:
            print("  [XX] Power flow did not converge!")
        
        return decisions['executed_trades']
    
    def run_demo(self, num_cycles: int = 10):
        print(f"\n{'='*60}\nDCOMET DEMO: Running {num_cycles} cycles\n{'='*60}")
        all_trades = []
        try:
            for cycle in range(num_cycles):
                trades = self.run_trading_cycle(cycle)
                all_trades.extend(trades)
                time.sleep(self.config.get('trading.trading_interval_seconds', 2))
        except KeyboardInterrupt:
            print(f"\n\nDemo interrupted")
        except Exception as e:
            self.logger.error(f"Error: {e}", exc_info=True)
            raise
        self._print_final_summary(all_trades)
    
    def _print_final_summary(self, all_trades: List):
        print(f"\n{'='*60}\nDEMO SUMMARY\n{'='*60}")
        print(f"Cycles: {self.cycle + 1}, Trades: {len(all_trades)}")
        if all_trades:
            total_energy = sum(t.get('quantity_wh', 0) for t in all_trades)
            total_revenue = sum(t.get('price_usd', 0) for t in all_trades)
            print(f"Energy: {total_energy:.3f}Wh, Revenue: ${total_revenue:.2f}")
            if total_energy > 0:
                print(f"Avg: ${total_revenue/total_energy:.2f}/Wh")
        print(f"Done!\n{'='*60}\n")

def main():
    system = DcometSystem("config/scenarios/demo_realistic_3kw_plus.yaml")
    system.run_demo(num_cycles=5)

if __name__ == "__main__":
    main()
