"""
Agent Manager - Orchestrates logic-based agents without LLMs.
Uses deterministic rules + lightweight ML for edge deployment.
"""
from typing import Dict, Any
from .logic_agents import DERAgent, ConsumerAgent, DSOAgent, ManagerAgent
from .ml_models import ContinuousLearningManager


class AgentManager:
    """
    Manages all agents in the DCOMET system.
    Uses physics-based logic + lightweight ML for continuous learning.
    """
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.ml_manager = ContinuousLearningManager()
        
        # Initialize agents
        self.manager_agent = ManagerAgent(ml_manager=self.ml_manager)
        
        # Create DER agents
        num_ders = config.get('der_config.num_ders', 3)
        for i in range(1, num_ders + 1):
            der_id = f'der_{i}'
            capacity_w = config.get(f'der_config.der_{i}.rated_capacity_w', 10.0)
            der_agent = DERAgent(der_id, capacity_w, self.ml_manager)
            self.manager_agent.register_der(der_agent)
        
        # Create Consumer agents
        num_consumers = config.get('loads_config.num_loads', 1)
        for i in range(1, num_consumers + 1):
            consumer_id = f'consumer_{i}'
            max_budget = config.get(f'loads_config.load_{i}.max_budget_usd', 10.0)
            consumer_agent = ConsumerAgent(consumer_id, max_budget, self.ml_manager)
            self.manager_agent.register_consumer(consumer_agent)
        
        # Create DSO agent
        dso_agent = DSOAgent(
            'dso_1',
            max_line_loading_pct=config.get('grid.max_line_loading_pct', 80.0),
            ml_manager=self.ml_manager
        )
        self.manager_agent.set_dso(dso_agent)
        
        print("[AgentManager] Initialized with logic-based agents (no LLMs)")
        print(f"  - {num_ders} DER agents")
        print(f"  - {num_consumers} Consumer agents")
        print(f"  - 1 DSO agent")
        print(f"  - ML-backed continuous learning enabled")
    
    def update_system_measurements(self, der_data: Dict[str, Dict], system_state: Dict[str, Any]):
        """
        Update all agents with current system measurements.
        Called at start of each cycle.
        """
        # Update DER agents
        for der_id, measurements in der_data.items():
            if der_id in self.manager_agent.der_agents:
                der_agent = self.manager_agent.der_agents[der_id]
                der_agent.update_measurements(
                    generation_w=measurements.get('power_w', 0),
                    voltage_pu=measurements.get('voltage_pu', 1.0),
                    frequency_hz=measurements.get('frequency_hz', 50.0)
                )
        
        # Update Consumer agents
        total_budget_spent = system_state.get('total_budget_spent', 0)
        for consumer_id, consumer_agent in self.manager_agent.consumer_agents.items():
            demand_w = system_state.get('consumer_demand_w', {}).get(consumer_id, 2.5)
            frequency_hz = system_state.get('frequency_hz', 50.0)
            consumer_agent.update_measurements(
                demand_w=demand_w,
                frequency_hz=frequency_hz,
                budget_spent=total_budget_spent
            )
        
        # Update DSO agent
        self.manager_agent.dso_agent.update_grid_state(
            voltage_pu=system_state.get('voltage_pu', 1.0),
            frequency_hz=system_state.get('frequency_hz', 50.0),
            line_loading_pct=system_state.get('line_loading_pct', 0.0)
        )
    
    def orchestrate_trading_cycle(self, system_state: Dict[str, Any]) -> Dict[str, Any]:
        """
        Run a complete trading cycle with all agents.
        Returns: trading decisions and executed trades.
        """
        result = self.manager_agent.orchestrate_trading_cycle(system_state)
        
        # Format result for API
        return {
            'der_decisions': [
                {
                    'der_id': offer['agent_id'],
                    'sell': True,
                    'offer_percentage': 70,  # 70% available
                    'quantity_w': offer['quantity_w'],
                    'price_usd': offer['price_usd']
                }
                for offer in result['der_offers']
            ],
            'consumer_decisions': [
                {
                    'consumer_id': req['consumer_id'],
                    'buy': True,
                    'quantity_w': req['quantity_w'],
                    'max_price': req['max_price']
                }
                for req in result['consumer_requests']
            ],
            'executed_trades': result['executed_trades'],
            'rejected_trades': result['rejected_trades'],
            'ml_insights': self.get_ml_insights(),
            'explainability': result.get('explainability', []),
        }
    
    def get_ml_insights(self) -> Dict[str, Any]:
        """
        Get current insights from ML models for monitoring/debugging.
        """
        return {
            **self.ml_manager.get_runtime_insights(),
            'grid_health_score': self.ml_manager.grid_analyzer.get_grid_health_score(
                self.manager_agent.dso_agent.state['current_voltage_pu'],
                self.manager_agent.dso_agent.state['current_frequency_hz'],
                self.manager_agent.dso_agent.state['current_line_loading_pct'],
            )
        }
    
    def get_agent_status(self) -> Dict[str, Any]:
        """
        Get status of all agents for debugging/monitoring.
        """
        der_status = {}
        for der_id, agent in self.manager_agent.der_agents.items():
            der_status[der_id] = {
                'status': agent.state['status'],
                'generation_w': agent.state['current_generation_w'],
                'available_w': agent.state['available_for_trading_w'],
                'voltage_pu': agent.state['voltage_pu']
            }
        
        consumer_status = {}
        for consumer_id, agent in self.manager_agent.consumer_agents.items():
            consumer_status[consumer_id] = {
                'status': agent.state['status'],
                'demand_w': agent.state['current_demand_w'],
                'budget_remaining_usd': agent.state['budget_remaining_usd'],
                'frequency_hz': agent.state['frequency_hz']
            }
        
        return {
            'der_agents': der_status,
            'consumer_agents': consumer_status,
            'dso_agent': {
                'voltage_pu': self.manager_agent.dso_agent.state['current_voltage_pu'],
                'frequency_hz': self.manager_agent.dso_agent.state['current_frequency_hz'],
                'line_loading_pct': self.manager_agent.dso_agent.state['current_line_loading_pct']
            },
            'ml_manager': {
                'cycle_count': self.ml_manager.cycle_count,
                'solar_confidence': self.ml_manager.solar_predictor.get_confidence(),
                'demand_model_trained': self.ml_manager.demand_predictor.is_trained
            }
        }
