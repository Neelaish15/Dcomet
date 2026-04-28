"""AI Agents - DER, Consumer, DSO using local Ollama"""
import requests
import json
from typing import Dict, Any, Optional
from datetime import datetime

class OllamaAgent:
    """Base agent using Ollama local LLM"""
    
    def __init__(self, agent_id: str, agent_name: str, config, role: str = "advisor"):
        self.agent_id = agent_id
        self.agent_name = agent_name
        self.config = config
        self.role = role
        self.ollama_endpoint = config.get('agents.der_agents.llm_endpoint', 'http://localhost:11434')
        self.model = config.get('agents.der_agents.llm_model', 'mistral')
        self.timeout = config.get('agents.der_agents.timeout_seconds', 30)
    
    def query_llm(self, prompt: str) -> str:
        """Query Ollama local LLM - skip if in demo mode"""
        # Check if demo mode (skip Ollama for faster execution)
        system_mode = self.config.get('system.mode', 'simulation')
        print(f"[DEBUG] Agent query_llm: mode={system_mode}")
        if system_mode == 'demo':
            print(f"[DEBUG] Demo mode detected - skipping Ollama")
            return "[Demo mode - using fallback logic]"
        
        try:
            print(f"[DEBUG] Attempting to connect to Ollama...")
            response = requests.post(
                f"{self.ollama_endpoint}/api/generate",
                json={
                    "model": self.model,
                    "prompt": prompt,
                    "stream": False,
                    "temperature": 0.7,
                },
                timeout=self.timeout
            )
            
            if response.status_code == 200:
                result = response.json()
                return result.get('response', '').strip()
            else:
                return f"Error: {response.status_code}"
        except requests.exceptions.ConnectionError:
            return "[Ollama not running - using fallback logic]"
        except requests.exceptions.Timeout:
            return "[Ollama timeout - using fallback logic]"
        except Exception as e:
            return f"[LLM Error: {str(e)}]"
    
    def make_decision(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """Make decision based on context"""
        raise NotImplementedError

class DERAgent(OllamaAgent):
    """DER (Distributed Energy Resource) Agent"""
    
    def __init__(self, der_id: str, der_name: str, config):
        super().__init__(der_id, der_name, config, role="der_provider")
        self.current_output_w = 0
        self.history = []
    
    def make_decision(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """Decide how much power to offer"""
        self.current_output_w = context.get('current_power_w', 0)
        available_for_sale = context.get('available_for_sale_w', self.current_output_w)
        grid_voltage_pu = context.get('grid_voltage_pu', 1.0)
        active_trades = context.get('active_trades', 0)
        
        # Create prompt for LLM
        prompt = f"""
You are a smart DER (Solar Panel) agent named {self.agent_name}.

Current Status:
- Current Power Generation: {self.current_output_w:.2f}W
- Available for Sale: {available_for_sale:.2f}W
- Grid Voltage: {grid_voltage_pu:.2f}PU
- Active Trades: {active_trades}

Decision:
1. Should I sell energy? (YES/NO)
2. How much to offer? (Suggest percentage of available power)
3. Minimum acceptable price? ($/Wh)

Respond ONLY with JSON format:
{{"sell": true/false, "offer_percentage": 0-100, "min_price_usd": 0.40-0.80}}
"""
        
        # Query LLM or use fallback
        response_text = self.query_llm(prompt)
        
        # Parse response
        try:
            if "{" in response_text:
                json_str = response_text[response_text.find('{'):response_text.rfind('}')+1]
                decision = json.loads(json_str)
            else:
                # Fallback logic
                decision = {
                    "sell": available_for_sale > 1.0,
                    "offer_percentage": 80 if available_for_sale > 1.0 else 0,
                    "min_price_usd": 0.50
                }
        except:
            decision = {
                "sell": available_for_sale > 1.0,
                "offer_percentage": 80 if available_for_sale > 1.0 else 0,
                "min_price_usd": 0.50
            }
        
        decision['agent_id'] = self.agent_id
        decision['timestamp'] = datetime.utcnow().isoformat()
        
        self.history.append(decision)
        return decision

class ConsumerAgent(OllamaAgent):
    """Consumer/Buyer Agent"""
    
    def __init__(self, consumer_id: str, consumer_name: str, config):
        super().__init__(consumer_id, consumer_name, config, role="consumer")
        self.current_demand_w = 0
        self.budget_usd = 10.0  # Daily budget
        self.history = []
    
    def make_decision(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """Decide how much energy to purchase"""
        self.current_demand_w = context.get('current_demand_w', 0)
        available_offers = context.get('available_offers', [])
        
        # Create prompt
        prompt = f"""
You are a smart consumer agent named {self.agent_name}.

Current Status:
- Current Energy Demand: {self.current_demand_w:.2f}W
- Available DER Offers: {len(available_offers)} sellers
- Budget: ${self.budget_usd:.2f}
- Acceptable Price Range: $0.40-$0.80/Wh

Available Offers:
{json.dumps(available_offers[:3], indent=2)}  # Top 3 offers

Decision:
1. Should I buy? (YES/NO)
2. How much to buy? (W)
3. Which DER to buy from? (ID)

Respond ONLY with JSON:
{{"buy": true/false, "quantity_w": 0-10, "preferred_der_id": "id or empty"}}
"""
        
        # Query LLM or use fallback
        response_text = self.query_llm(prompt)
        
        # Parse response
        try:
            if "{" in response_text:
                json_str = response_text[response_text.find('{'):response_text.rfind('}')+1]
                decision = json.loads(json_str)
            else:
                # Fallback: buy if good deals available
                decision = {
                    "buy": len(available_offers) > 0,
                    "quantity_w": min(self.current_demand_w, 5),
                    "preferred_der_id": available_offers[0].get('id', '') if available_offers else ""
                }
        except:
            decision = {
                "buy": len(available_offers) > 0,
                "quantity_w": min(self.current_demand_w, 5),
                "preferred_der_id": available_offers[0].get('id', '') if available_offers else ""
            }
        
        decision['agent_id'] = self.agent_id
        decision['timestamp'] = datetime.utcnow().isoformat()
        
        self.history.append(decision)
        return decision

class DSOAgent(OllamaAgent):
    """DSO (Distribution System Operator) Agent - Grid Safety Monitor"""
    
    def __init__(self, config):
        super().__init__("dso_agent", "Grid Safety Monitor", config, role="dso")
        self.history = []
    
    def make_decision(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """Monitor grid safety and approve/reject trades"""
        grid_voltage_pu = context.get('grid_voltage_pu', 1.0)
        line_loading_percent = context.get('line_loading_percent', 0)
        proposed_injection_w = context.get('proposed_injection_w', 0)
        total_load_w = context.get('total_load_w', 0)
        
        # Create prompt
        prompt = f"""
You are a DSO (Grid Operator) safety agent.

Grid Status:
- Voltage: {grid_voltage_pu:.2f}PU (should be 0.9-1.1)
- Line Loading: {line_loading_percent:.1f}% (max 85%)
- Proposed Injection: {proposed_injection_w:.2f}W
- Total Load: {total_load_w:.2f}W

Constraints:
- Voltage must be 0.9-1.1 PU
- Line loading must be <85%

Decision:
1. Approve trade? (YES/NO)
2. If NO, why?
3. Confidence (0-100%)?

Respond ONLY with JSON:
{{"approve": true/false, "reason": "safe/voltage_high/voltage_low/line_overload", "confidence": 95}}
"""
        
        # Query LLM or use fallback
        response_text = self.query_llm(prompt)
        
        # Parse response
        try:
            if "{" in response_text:
                json_str = response_text[response_text.find('{'):response_text.rfind('}')+1]
                decision = json.loads(json_str)
            else:
                # Fallback logic
                voltage_ok = 0.9 <= grid_voltage_pu <= 1.1
                loading_ok = line_loading_percent <= 85
                decision = {
                    "approve": voltage_ok and loading_ok,
                    "reason": "safe" if (voltage_ok and loading_ok) else 
                             "voltage_high" if grid_voltage_pu > 1.1 else
                             "voltage_low" if grid_voltage_pu < 0.9 else
                             "line_overload",
                    "confidence": 95
                }
        except:
            decision = {
                "approve": True,
                "reason": "safe",
                "confidence": 80
            }
        
        decision['agent_id'] = self.agent_id
        decision['timestamp'] = datetime.utcnow().isoformat()
        
        self.history.append(decision)
        return decision

class AgentManager:
    """Manages all agents and orchestrates trading"""
    
    def __init__(self, config):
        self.config = config
        self.der_agents = []
        self.consumer_agents = []
        self.dso_agent = None
        self._initialize_agents()
    
    def _initialize_agents(self):
        """Initialize all agents"""
        # Create DER agents
        num_ders = self.config.get('der_config.num_ders', 3)
        for i in range(1, num_ders + 1):
            der_name = self.config.get(f'der_config.der_{i}.name', f'DER {i}')
            agent = DERAgent(f"der_{i}", der_name, self.config)
            self.der_agents.append(agent)
        
        # Create Consumer agents
        num_consumers = self.config.get('loads_config.num_loads', 2)
        for i in range(1, num_consumers + 1):
            load_name = self.config.get(f'loads_config.load_{i}.name', f'Consumer {i}')
            agent = ConsumerAgent(f"consumer_{i}", load_name, self.config)
            self.consumer_agents.append(agent)
        
        # Create DSO agent
        if self.config.get('agents.dso_agent.enabled', True):
            self.dso_agent = DSOAgent(self.config)
    
    def orchestrate_trading_cycle(self, system_state: Dict[str, Any]) -> Dict[str, Any]:
        """Run one trading cycle"""
        results = {
            'der_decisions': [],
            'consumer_decisions': [],
            'dso_decision': {},
            'timestamp': datetime.utcnow().isoformat()
        }
        
        # Get DER decisions
        for der_agent in self.der_agents:
            active_trades_count = system_state.get('active_trades', 0)
            if isinstance(active_trades_count, list):
                active_trades_count = len(active_trades_count)
            
            der_state = {
                'current_power_w': system_state.get('der_outputs', {}).get(der_agent.agent_id, 0),
                'available_for_sale_w': system_state.get('der_outputs', {}).get(der_agent.agent_id, 0),
                'grid_voltage_pu': system_state.get('grid_voltage_pu', 1.0),
                'active_trades': active_trades_count
            }
            decision = der_agent.make_decision(der_state)
            results['der_decisions'].append(decision)
        
        # Get Consumer decisions
        for consumer_agent in self.consumer_agents:
            consumer_state = {
                'current_demand_w': system_state.get('load_demands', {}).get(consumer_agent.agent_id, 0),
                'available_offers': system_state.get('available_offers', [])
            }
            decision = consumer_agent.make_decision(consumer_state)
            results['consumer_decisions'].append(decision)
        
        # Get DSO decision
        if self.dso_agent:
            dso_state = {
                'grid_voltage_pu': system_state.get('grid_voltage_pu', 1.0),
                'line_loading_percent': system_state.get('line_loading_percent', 0),
                'proposed_injection_w': system_state.get('proposed_injection_w', 0),
                'total_load_w': system_state.get('total_load_w', 0)
            }
            results['dso_decision'] = self.dso_agent.make_decision(dso_state)
        
        return results
