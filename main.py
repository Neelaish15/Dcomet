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
    def __init__(self, config_path: str = "config/scenarios/demo_10w_prototype.yaml"):
        print(f"\n{'='*60}\nDCOMET - Beckn P2P Energy Trading System\nDemo: 10W Solar\n{'='*60}\n")
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
        self.logger.info("[2] DERs announcing on Beckn...")
        print("\n[Beckn Marketplace - DER Announcements]")
        beckn_offers = {}
        for der_id, available_w in available_power.items():
            if available_w > 0:
                bpp = self.beckn_bpps[der_id]
                offer = bpp.create_search_response({}, available_w)
                beckn_offers[der_id] = offer
                print(f"  {der_id}: {available_w:.2f}W @ $0.50/Wh")
        self.logger.info("[3] AI agents deciding...")
        system_state = {
            'der_outputs': {k: v['power_w'] for k, v in der_data.items()},
            'available_offers': list(beckn_offers.values()),
            'grid_voltage_pu': 1.0,
            'line_loading_percent': 10.0,
            'proposed_injection_w': total_available,
            'total_load_w': 5.0,
            'active_trades': len(self.trading_engine.active_trades),
            'load_demands': {f'consumer_{i}': 2.0 for i in range(1, self.config.get('loads_config.num_loads', 1) + 1)}
        }
        decisions = self.agent_manager.orchestrate_trading_cycle(system_state)
        print("\n[Agent Decisions]")
        print("  DER Decisions:")
        for i, dec in enumerate(decisions['der_decisions'], 1):
            print(f"    DER {i}: Sell={dec.get('sell', False)}, Offer={dec.get('offer_percentage', 0)}%")
        print("  Consumer Decisions:")
        for i, dec in enumerate(decisions['consumer_decisions'], 1):
            print(f"    Consumer {i}: Buy={dec.get('buy', False)}, Qty={dec.get('quantity_w', 0):.1f}W")
        if decisions['dso_decision']:
            print(f"  DSO: Approve={decisions['dso_decision'].get('approve', False)}")
        self.logger.info("[4] Matching...")
        available_ders = []
        for i, dec in enumerate(decisions['der_decisions'], 1):
            if dec.get('sell', False):
                available_ders.append({
                    'id': f'der_{i}',
                    'name': self.config.get(f'der_config.der_{i}.name', f'DER {i}'),
                    'available_power_w': (available_power[f'der_{i}'] * dec.get('offer_percentage', 80) / 100)
                })
        active_loads = []
        for i, dec in enumerate(decisions['consumer_decisions'], 1):
            if dec.get('buy', False):
                active_loads.append({
                    'id': f'consumer_{i}',
                    'name': self.config.get(f'loads_config.load_{i}.name', f'Consumer {i}'),
                    'need_power_w': dec.get('quantity_w', 0)
                })
        trades = self.trading_engine.match_buyers_sellers(available_ders, active_loads)
        print("\n[Grid Stability Check]")
        approved_trades = []
        for trade in trades:
            dso_approval = decisions['dso_decision'].get('approve', True)
            if dso_approval:
                trade_result = self.trading_engine.execute_trade(trade)
                approved_trades.append(trade_result)
                print(f"  [OK] Trade APPROVED: {trade['quantity_w']:.2f}W")
            else:
                print(f"  [XX] Trade REJECTED")
        self.logger.info("[5] Power flow...")
        pf_results = self.grid_engine.run_power_flow()
        print("\n[Power Flow Results]")
        if pf_results['converged']:
            print("  [OK] Power flow converged")
        else:
            print("  [XX] Power flow did not converge!")
        print("\n[Trading Summary]")
        summary = self.trading_engine.get_trade_summary()
        print(f"  Active: {summary['active_trades']}, Energy: {summary['total_energy_traded_wh']:.3f}Wh, Revenue: ${summary['total_revenue_usd']:.2f}")
        return approved_trades
    
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
    system = DcometSystem("config/scenarios/demo_10w_prototype.yaml")
    system.run_demo(num_cycles=5)

if __name__ == "__main__":
    main()
