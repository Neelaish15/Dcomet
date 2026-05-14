"""
Physics-based and logic-driven agents for DCOMET.
Replaces LLM-based agents with deterministic decision rules and lightweight ML.
Suitable for edge deployment on low-cost hardware.
"""
from datetime import datetime
from typing import Dict, Any, List, Optional
from .ml_models import ContinuousLearningManager


class DERAgent:
    """
    Distributed Energy Resource Agent.
    Physics: Monitors solar generation, calculates excess, decides to offer based on:
    - Current generation > demand threshold
    - Price > minimum acceptable price
    - Grid voltage within limits
    """
    
    def __init__(self, agent_id: str, capacity_w: float, ml_manager: ContinuousLearningManager):
        self.agent_id = agent_id
        self.capacity_w = capacity_w
        self.ml = ml_manager
        self.min_price = 0.08  # Won't sell below this price
        self.price_multiplier = 1.0  # Adjust based on market conditions
        self.generation_threshold_w = 2.0  # Only offer if generation > threshold
        self.state = {
            'current_generation_w': 0,
            'available_for_trading_w': 0,
            'voltage_pu': 1.0,
            'status': 'idle'
        }
    
    def update_measurements(self, generation_w: float, voltage_pu: float, frequency_hz: float):
        """Update agent with real sensor data."""
        self.state['current_generation_w'] = generation_w
        self.state['voltage_pu'] = voltage_pu
        # Assume 70% can be traded, 30% reserved for local use
        self.state['available_for_trading_w'] = generation_w * 0.7
    
    def decide_to_offer(self, system_demand_w: float, total_supply_w: float) -> Dict[str, Any]:
        """
        Physics-based decision logic:
        1. Check if generation > threshold (excess power exists)
        2. Check if voltage is within limits (safe to inject)
        3. Calculate supply-demand ratio to determine price
        4. Generate offer if conditions met
        """
        decision = {
            'should_offer': False,
            'reason': '',
            'offer': None,
            'explainability': {},
        }
        
        # Rule 1: Check if we have excess generation
        if self.state['current_generation_w'] < self.generation_threshold_w:
            decision['reason'] = 'Insufficient generation'
            decision['should_offer'] = False
            decision['explainability'] = {
                'generation_w': self.state['current_generation_w'],
                'threshold_w': self.generation_threshold_w,
                'rule': 'generation_threshold',
            }
            return decision
        
        # Rule 2: Check voltage safety (must be within ±5% of nominal)
        if not (0.95 <= self.state['voltage_pu'] <= 1.05):
            decision['reason'] = f"Voltage out of range: {self.state['voltage_pu']:.3f} pu"
            decision['should_offer'] = False
            decision['explainability'] = {
                'voltage_pu': self.state['voltage_pu'],
                'limits': [0.95, 1.05],
                'rule': 'voltage_safety',
            }
            return decision
        
        # Rule 3: Calculate optimal price based on supply-demand
        supply_demand_ratio = total_supply_w / system_demand_w if system_demand_w > 0 else 2.0
        
        if supply_demand_ratio > 1.5:  # Oversupply: lower price
            price_multiplier = 0.90
            self.state['status'] = 'oversupply_mode'
        elif supply_demand_ratio < 0.5:  # Undersupply: higher price
            price_multiplier = 1.20
            self.state['status'] = 'undersupply_mode'
        else:
            price_multiplier = 1.0
            self.state['status'] = 'normal_mode'
        
        # Use ML for optimal pricing
        optimal_price = self.ml.price_optimizer.calculate_optimal_price(
            self.state['current_generation_w'],
            system_demand_w
        )
        
        # Rule 4: Respect minimum price threshold
        final_price = max(self.min_price, optimal_price * price_multiplier)

        if self.ml.conservative_mode:
            # Reduce offered power during drift or low confidence windows.
            self.state['available_for_trading_w'] *= 0.8
        
        # Generate offer
        available_kwh = (self.state['available_for_trading_w'] * 0.25) / 1000  # 15-min block to kWh
        
        decision['should_offer'] = True
        decision['reason'] = f"Generation healthy, {self.state['status']}"
        decision['explainability'] = {
            'supply_demand_ratio': round(float(supply_demand_ratio), 6),
            'optimal_price': round(float(optimal_price), 6),
            'price_multiplier': round(float(price_multiplier), 6),
            'conservative_mode': self.ml.conservative_mode,
        }
        decision['offer'] = {
            'agent_id': self.agent_id,
            'type': 'energy_offer',
            'quantity_w': self.state['available_for_trading_w'],
            'quantity_kwh': available_kwh,
            'price_usd': round(final_price, 3),
            'voltage_pu': self.state['voltage_pu'],
            'timestamp': datetime.now().isoformat()
        }
        
        return decision


class ConsumerAgent:
    """
    Consumer/Load Agent.
    Physics: Monitors demand, decides to buy based on:
    - Current demand > safety threshold
    - Price < maximum acceptable price
    - Budget remaining > cost of purchase
    - Grid frequency within limits
    """
    
    def __init__(self, agent_id: str, max_budget_usd: float, ml_manager: ContinuousLearningManager):
        self.agent_id = agent_id
        self.max_budget_usd = max_budget_usd
        self.ml = ml_manager
        self.max_price = 0.20  # Won't buy above this price
        self.demand_threshold_w = 1.0  # Buy if demand > threshold
        self.state = {
            'current_demand_w': 0,
            'budget_remaining_usd': max_budget_usd,
            'frequency_hz': 50.0,
            'status': 'idle'
        }
    
    def update_measurements(self, demand_w: float, frequency_hz: float, budget_spent: float):
        """Update agent with real measurements and budget tracking."""
        self.state['current_demand_w'] = demand_w
        self.state['frequency_hz'] = frequency_hz
        self.state['budget_remaining_usd'] = self.max_budget_usd - budget_spent
    
    def decide_to_buy(self, available_offers: List[Dict]) -> Dict[str, Any]:
        """
        Physics-based decision logic:
        1. Check if demand exists (load active)
        2. Check if frequency is within limits (safe to consume)
        3. Filter offers by price threshold
        4. Select best offer within budget
        5. Calculate optimal quantity to buy
        """
        decision = {
            'should_buy': False,
            'reason': '',
            'selected_offer': None,
            'quantity_to_buy_w': 0,
            'explainability': {},
        }
        
        # Rule 1: Check if we have demand
        if self.state['current_demand_w'] < self.demand_threshold_w:
            decision['reason'] = 'No active demand'
            decision['should_buy'] = False
            decision['explainability'] = {'rule': 'demand_threshold'}
            return decision
        
        # Rule 2: Check frequency safety (must be within ±0.5 Hz of nominal)
        if not (49.5 <= self.state['frequency_hz'] <= 50.5):
            decision['reason'] = f"Frequency out of range: {self.state['frequency_hz']:.2f} Hz"
            decision['should_buy'] = False
            decision['explainability'] = {'rule': 'frequency_safety', 'frequency_hz': self.state['frequency_hz']}
            return decision
        
        # Rule 3: Check budget
        if self.state['budget_remaining_usd'] <= 0:
            decision['reason'] = 'Budget exhausted'
            decision['should_buy'] = False
            decision['explainability'] = {'rule': 'budget_guard'}
            return decision
        
        # Rule 4: Filter affordable offers
        affordable_offers = [
            offer for offer in available_offers
            if offer.get('price_usd', 0) <= self.max_price
        ]
        
        if not affordable_offers:
            decision['reason'] = f'No offers below max price ${self.max_price}'
            decision['should_buy'] = False
            decision['explainability'] = {'rule': 'price_filter', 'max_price': self.max_price}
            return decision
        
        # Rule 5: Select best offer (lowest price)
        best_offer = min(affordable_offers, key=lambda x: x.get('price_usd', 999))
        
        # Rule 6: Calculate quantity to buy
        # Buy amount: min(demand, available, budget_allows, quantity_offered)
        max_affordable_w = (self.state['budget_remaining_usd'] / best_offer['price_usd']) * 1000 \
            if best_offer['price_usd'] > 0 else 0
        
        quantity_to_buy = min(
            self.state['current_demand_w'],
            best_offer.get('quantity_w', 10),
            max_affordable_w,
            self.state['current_demand_w'] * 1.2  # Buy up to 120% of demand for buffer
        )
        
        if quantity_to_buy > 0:
            decision['should_buy'] = True
            decision['reason'] = 'Demand met, affordable offer found'
            decision['selected_offer'] = best_offer
            decision['quantity_to_buy_w'] = round(quantity_to_buy, 3)
            decision['explainability'] = {
                'rule': 'optimal_affordable_offer',
                'offer_price_usd': best_offer.get('price_usd', 0),
                'max_affordable_w': round(float(max_affordable_w), 6),
            }
        else:
            decision['reason'] = 'Budget insufficient for available offers'
            decision['should_buy'] = False
            decision['explainability'] = {'rule': 'budget_limited_quantity'}
        
        return decision


class DSOAgent:
    """
    Distribution System Operator Agent.
    Validates grid constraints and approves/rejects trades based on:
    - Voltage remains within limits
    - Line loading stays below safety threshold
    - Frequency remains within acceptable range
    - Total injection/consumption doesn't exceed grid capacity
    """
    
    def __init__(self, agent_id: str, max_line_loading_pct: float = 80.0, ml_manager: Optional[ContinuousLearningManager] = None):
        self.agent_id = agent_id
        self.max_line_loading_pct = max_line_loading_pct
        self.ml = ml_manager
        self.voltage_limits = (0.95, 1.05)  # ±5% nominal
        self.frequency_limits = (49.5, 50.5)  # ±0.5 Hz
        self.state = {
            'current_voltage_pu': 1.0,
            'current_frequency_hz': 50.0,
            'current_line_loading_pct': 0.0,
            'approved_injections_w': 0,
            'approved_consumptions_w': 0
        }
    
    def update_grid_state(self, voltage_pu: float, frequency_hz: float, line_loading_pct: float):
        """Update DSO with grid measurements."""
        self.state['current_voltage_pu'] = voltage_pu
        self.state['current_frequency_hz'] = frequency_hz
        self.state['current_line_loading_pct'] = line_loading_pct
    
    def validate_trade(self, trade_type: str, quantity_w: float, der_id: str = '', consumer_id: str = '') -> Dict[str, Any]:
        """
        Validate if a proposed trade is safe for the grid.
        trade_type: 'injection' (DER -> Grid) or 'consumption' (Grid -> Consumer)
        """
        validation = {
            'approved': False,
            'reason': '',
            'constraints_violated': [],
            'projected_loading_pct': self.state['current_line_loading_pct'],
        }
        
        # Rule 1: Check voltage limits
        if not (self.voltage_limits[0] <= self.state['current_voltage_pu'] <= self.voltage_limits[1]):
            validation['approved'] = False
            validation['constraints_violated'].append('voltage_out_of_range')
            validation['reason'] = f"Voltage {self.state['current_voltage_pu']:.3f} pu outside limits"
            return validation
        
        # Rule 2: Check frequency limits
        if not (self.frequency_limits[0] <= self.state['current_frequency_hz'] <= self.frequency_limits[1]):
            validation['approved'] = False
            validation['constraints_violated'].append('frequency_out_of_range')
            validation['reason'] = f"Frequency {self.state['current_frequency_hz']:.2f} Hz outside limits"
            return validation
        
        # Rule 3: Check line loading safety
        if self.state['current_line_loading_pct'] > self.max_line_loading_pct:
            validation['approved'] = False
            validation['constraints_violated'].append('line_overloaded')
            validation['reason'] = f"Line loading {self.state['current_line_loading_pct']:.1f}% exceeds {self.max_line_loading_pct}%"
            return validation
        
        # Rule 4: Check if trade would exceed loading limits
        projected_loading = self.state['current_line_loading_pct'] + (quantity_w / 100.0) * 10  # Rough estimate
        validation['projected_loading_pct'] = projected_loading
        if projected_loading > self.max_line_loading_pct:
            validation['approved'] = False
            validation['constraints_violated'].append('would_exceed_loading')
            validation['reason'] = f"Trade would push loading to {projected_loading:.1f}%, exceeds limit"
            return validation
        
        # All constraints satisfied
        validation['approved'] = True
        validation['reason'] = 'Grid constraints satisfied'
        return validation


class ManagerAgent:
    """
    Manager/Orchestrator Agent.
    Coordinates between DER, Consumer, and DSO agents.
    Manages trade lifecycle: search -> select -> confirm -> complete
    """
    
    def __init__(self, agent_id: str = 'manager_1', ml_manager: Optional[ContinuousLearningManager] = None):
        self.agent_id = agent_id
        self.ml = ml_manager or ContinuousLearningManager()
        self.der_agents: Dict[str, DERAgent] = {}
        self.consumer_agents: Dict[str, ConsumerAgent] = {}
        self.dso_agent: Optional[DSOAgent] = None
        self.active_trades = {}
        self.trade_counter = 0
    
    def register_der(self, agent: DERAgent):
        """Register a DER agent."""
        self.der_agents[agent.agent_id] = agent
    
    def register_consumer(self, agent: ConsumerAgent):
        """Register a consumer agent."""
        self.consumer_agents[agent.agent_id] = agent
    
    def set_dso(self, agent: DSOAgent):
        """Set the DSO agent."""
        self.dso_agent = agent
    
    def orchestrate_trading_cycle(self, system_state: Dict[str, Any]) -> Dict[str, Any]:
        """
        Main orchestration logic for a trading cycle.
        Flow: DER Offers -> Consumer Browse -> DSO Validate -> Execute Trade
        """
        cycle_result = {
            'timestamp': datetime.now().isoformat(),
            'der_offers': [],
            'consumer_requests': [],
            'executed_trades': [],
            'rejected_trades': [],
            'grid_status': system_state.get('grid_status', {}),
            'explainability': [],
        }
        
        # Step 1: DERs generate offers
        for der_id, der_agent in self.der_agents.items():
            total_supply = sum(der.state['current_generation_w'] for der in self.der_agents.values())
            total_demand = sum(cons.state['current_demand_w'] for cons in self.consumer_agents.values())
            
            der_decision = der_agent.decide_to_offer(total_demand, total_supply)
            if der_decision['should_offer']:
                cycle_result['der_offers'].append(der_decision['offer'])
            cycle_result['explainability'].append({
                'agent_id': der_id,
                'type': 'der_decision',
                'decision': der_decision['reason'],
                'details': der_decision.get('explainability', {}),
            })
        
        # Step 2: Consumers decide to buy
        for consumer_id, consumer_agent in self.consumer_agents.items():
            consumer_decision = consumer_agent.decide_to_buy(cycle_result['der_offers'])
            if consumer_decision['should_buy']:
                cycle_result['consumer_requests'].append({
                    'consumer_id': consumer_id,
                    'quantity_w': consumer_decision['quantity_to_buy_w'],
                    'selected_offer': consumer_decision['selected_offer'],
                    'max_price': consumer_agent.max_price,
                    'explainability': consumer_decision.get('explainability', {}),
                })
            cycle_result['explainability'].append({
                'agent_id': consumer_id,
                'type': 'consumer_decision',
                'decision': consumer_decision['reason'],
                'details': consumer_decision.get('explainability', {}),
            })
        
        # Step 3: DSO validates trades
        if self.dso_agent:
            seller_trade_count: Dict[str, int] = {}
            for trade_req in cycle_result['consumer_requests']:
                trade_type = 'consumption'
                validation = self.dso_agent.validate_trade(
                    trade_type,
                    trade_req['quantity_w'],
                    consumer_id=trade_req['consumer_id']
                )
                
                if validation['approved']:
                    # Welfare-inspired score: lower price, shorter path penalty, fairness bonus.
                    seller_id = trade_req['selected_offer']['agent_id']
                    seller_seen = seller_trade_count.get(seller_id, 0)
                    fairness_bonus = max(0.0, 0.08 - 0.02 * seller_seen)
                    network_loss_penalty = float(system_state.get('line_loading_pct', 0.0)) / 1000.0
                    utility_score = max(0.0, 0.25 - float(trade_req['selected_offer']['price_usd']))
                    welfare_score = utility_score + fairness_bonus - network_loss_penalty

                    # Execute trade
                    trade = {
                        'trade_id': f"trade_{self.trade_counter}",
                        'timestamp': datetime.now().isoformat(),
                        'seller_id': seller_id,
                        'buyer_id': trade_req['consumer_id'],
                        'quantity_w': trade_req['quantity_w'],
                        'quantity_kwh': (trade_req['quantity_w'] * 0.25) / 1000,
                        'price_usd': trade_req['selected_offer']['price_usd'],
                        'status': 'completed',
                        'explainability': {
                            'dso_validation': validation,
                            'consumer_reason': trade_req.get('explainability', {}),
                            'objective': {
                                'utility_score': round(float(utility_score), 6),
                                'fairness_bonus': round(float(fairness_bonus), 6),
                                'network_loss_penalty': round(float(network_loss_penalty), 6),
                                'welfare_score': round(float(welfare_score), 6),
                            },
                        },
                    }
                    cycle_result['executed_trades'].append(trade)
                    self.trade_counter += 1
                    seller_trade_count[seller_id] = seller_seen + 1
                else:
                    cycle_result['rejected_trades'].append({
                        'reason': validation['reason'],
                        'trade_request': trade_req,
                        'validation': validation,
                    })
        
        # Step 4: Update ML models with cycle outcomes
        if self.ml:
            cycle_data = {
                'der_generation_w': sum(der.state['current_generation_w'] for der in self.der_agents.values()),
                'consumer_demand_w': sum(cons.state['current_demand_w'] for cons in self.consumer_agents.values()),
                'voltage_pu': self.dso_agent.state['current_voltage_pu'] if self.dso_agent else 1.0,
                'frequency_hz': self.dso_agent.state['current_frequency_hz'] if self.dso_agent else 50.0,
                'loading_pct': self.dso_agent.state['current_line_loading_pct'] if self.dso_agent else 0.0,
                'trade_count': len(cycle_result['executed_trades']),
                'trade_price': cycle_result['executed_trades'][0]['price_usd'] if cycle_result['executed_trades'] else 0.12,
                'trade_quantity': cycle_result['executed_trades'][0]['quantity_w'] if cycle_result['executed_trades'] else 0,
                'trade_accepted': len(cycle_result['executed_trades']) > 0
            }
            self.ml.update_from_cycle(cycle_data)
            cycle_result['ml_insights'] = self.ml.get_runtime_insights()
        
        return cycle_result
