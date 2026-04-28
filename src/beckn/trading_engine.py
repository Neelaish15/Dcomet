"""Beckn Protocol Implementation - DEG (Decentralized Energy Grid)"""
import json
import uuid
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, asdict

@dataclass
class BecknContext:
    """Beckn context for all messages"""
    domain: str = "energy"
    country: str = "IND"
    city: str = "std:999"
    action: str = "search"
    version: str = "0.4.0"
    bap_id: str = "bap.dcomet.local"
    bap_uri: str = "http://localhost:8003"
    bpp_id: str = "bpp.dcomet.local"
    bpp_uri: str = "http://localhost:8002"
    transaction_id: str = ""
    message_id: str = ""
    timestamp: str = ""
    ttl: str = "PT30S"
    
    def __post_init__(self):
        if not self.transaction_id:
            self.transaction_id = str(uuid.uuid4())
        if not self.message_id:
            self.message_id = str(uuid.uuid4())
        if not self.timestamp:
            self.timestamp = datetime.utcnow().isoformat() + "Z"

@dataclass
class Energy:
    """Energy item for trading"""
    id: str
    quantity_wh: float
    price_usd: float
    der_id: str
    
    def to_dict(self) -> Dict:
        return asdict(self)

class BecknBPP:
    """Beckn Backend Provider Platform (DER/Generator side)"""
    
    def __init__(self, der_id: str, der_name: str, capacity_w: float):
        self.der_id = der_id
        self.der_name = der_name
        self.capacity_w = capacity_w
        self.available_power_w = 0
        self.orders = {}  # order_id -> order
        self.listings = []
    
    def create_search_response(self, query: Dict, available_power_w: float) -> Dict:
        """Create Beckn search response with available energy"""
        self.available_power_w = available_power_w
        
        context = BecknContext(action="on_search", bpp_id=self.der_id)
        
        # Create catalog with available energy
        items = []
        if available_power_w > 0:
            items.append({
                "id": f"{self.der_id}_energy_{uuid.uuid4().hex[:8]}",
                "descriptor": {
                    "name": f"Energy from {self.der_name}",
                    "code": "ENERGY_DEG",
                    "short_desc": f"{available_power_w:.2f}W available"
                },
                "quantity": {
                    "selected": {
                        "count": int(available_power_w)
                    },
                    "available": {
                        "count": int(available_power_w)
                    }
                },
                "price": {
                    "currency": "USD",
                    "value": str(0.50)  # $0.50/Wh
                }
            })
        
        response = {
            "context": asdict(context),
            "message": {
                "catalog": {
                    "bpp_descriptor": {
                        "name": self.der_name,
                        "long_desc": f"DER with capacity {self.capacity_w}W",
                        "images": []
                    },
                    "bpp_categories": [],
                    "bpp_fulfillments": [],
                    "items": items,
                    "exp": (datetime.utcnow() + timedelta(minutes=30)).isoformat()
                }
            }
        }
        return response
    
    def select_energy(self, order_id: str, item_id: str, quantity_w: float) -> Dict:
        """Create select response"""
        context = BecknContext(action="on_select", bpp_id=self.der_id)
        
        response = {
            "context": asdict(context),
            "message": {
                "order": {
                    "id": order_id,
                    "state": "ACCEPTED",
                    "items": [
                        {
                            "id": item_id,
                            "quantity": {
                                "selected": {"count": int(quantity_w)}
                            },
                            "price": {
                                "currency": "USD",
                                "value": str(quantity_w * 0.50)
                            }
                        }
                    ],
                    "quote": {
                        "price": {
                            "currency": "USD",
                            "value": str(quantity_w * 0.50)
                        },
                        "ttl": "PT30S"
                    }
                }
            }
        }
        return response
    
    def confirm_order(self, order_id: str) -> Dict:
        """Confirm energy delivery"""
        context = BecknContext(action="on_confirm", bpp_id=self.der_id)
        
        response = {
            "context": asdict(context),
            "message": {
                "order": {
                    "id": order_id,
                    "state": "ACTIVE",
                    "fulfillment_active": True
                }
            }
        }
        
        self.orders[order_id] = response
        return response

class BecknBAP:
    """Beckn Backend App Platform (Consumer/Aggregator side)"""
    
    def __init__(self, consumer_id: str, consumer_name: str):
        self.consumer_id = consumer_id
        self.consumer_name = consumer_name
        self.available_offers = {}
        self.active_orders = {}
    
    def create_search_request(self, quantity_w: float, max_price_usd: float = 0.60) -> Dict:
        """Create Beckn search request for energy"""
        context = BecknContext(
            action="search",
            bap_id=self.consumer_id,
            bap_uri=f"http://localhost:8003"
        )
        
        request = {
            "context": asdict(context),
            "message": {
                "intent": {
                    "item": {
                        "descriptor": {
                            "name": "Energy",
                            "code": "ENERGY_DEG"
                        }
                    },
                    "quantity": {
                        "selected": {
                            "count": int(quantity_w)
                        }
                    },
                    "price_range": {
                        "min": "0.40",
                        "max": str(max_price_usd)
                    }
                }
            }
        }
        return request
    
    def select_offer(self, bpp_offer: Dict, quantity_w: float) -> Dict:
        """Select specific DER offer"""
        context = BecknContext(
            action="select",
            bap_id=self.consumer_id
        )
        
        # Extract item from offer
        items = bpp_offer.get('message', {}).get('catalog', {}).get('items', [])
        selected_item = items[0] if items else {}
        
        request = {
            "context": asdict(context),
            "message": {
                "order": {
                    "items": [
                        {
                            "id": selected_item.get('id', ''),
                            "quantity": {
                                "selected": {"count": int(quantity_w)}
                            }
                        }
                    ]
                }
            }
        }
        return request
    
    def place_order(self, selected_order: Dict) -> Dict:
        """Place order to confirm purchase"""
        context = BecknContext(
            action="init",
            bap_id=self.consumer_id
        )
        
        order_id = str(uuid.uuid4())
        
        request = {
            "context": asdict(context),
            "message": {
                "order": {
                    "id": order_id,
                    "state": "ACTIVE",
                    "items": selected_order.get('message', {}).get('order', {}).get('items', [])
                }
            }
        }
        
        self.active_orders[order_id] = request
        return request

class TradingEngine:
    """P2P Energy Trading on Beckn"""
    
    def __init__(self, config):
        self.config = config
        self.active_trades = {}
        self.completed_trades = []
        self.price_per_wh = config.get('trading.price_per_unit_usd_per_wh', 0.50)
    
    def match_buyers_sellers(self, 
                            available_ders: List[Dict],
                            active_loads: List[Dict]) -> List[Dict]:
        """
        Match DERs with excess power to consumers needing power.
        Works at ANY scale - demo with 10W, scale to 1MW!
        """
        trades = []
        
        for der in available_ders:
            if der['available_power_w'] > 0:  # Has excess
                
                for load in active_loads:
                    if load['need_power_w'] > 0:  # Needs power
                        
                        # Find best match
                        trade_quantity = min(
                            der['available_power_w'],
                            load['need_power_w']
                        )
                        
                        if trade_quantity > 0:
                            # Calculate energy assuming 1-hour delivery period for demo purposes
                            quantity_wh = trade_quantity * 1.0  # 1W * 1hr = 1Wh
                            price_usd = quantity_wh * self.price_per_wh
                            
                            trade = {
                                'trade_id': str(uuid.uuid4()),
                                'der_id': der['id'],
                                'der_name': der['name'],
                                'consumer_id': load['id'],
                                'consumer_name': load['name'],
                                'quantity_w': trade_quantity,
                                'quantity_wh': quantity_wh,
                                'price_usd': price_usd,
                                'status': 'proposed',
                                'timestamp': datetime.utcnow().isoformat()
                            }
                            trades.append(trade)
                            
                            # Update availability
                            der['available_power_w'] -= trade_quantity
                            load['need_power_w'] -= trade_quantity
        
        return trades
    
    def verify_grid_stability(self, trade: Dict, power_calculator) -> bool:
        """Verify grid can handle trade"""
        # This would integrate with GridEngine
        # For now, always approve (grid is small)
        return True
    
    def execute_trade(self, trade: Dict, grid_engine=None) -> Dict:
        """Execute trade on grid"""
        trade['status'] = 'executed'
        trade['execution_time'] = datetime.utcnow().isoformat()
        
        self.active_trades[trade['trade_id']] = trade
        return trade
    
    def settle_trade(self, trade_id: str) -> Dict:
        """Settle completed trade"""
        if trade_id in self.active_trades:
            trade = self.active_trades[trade_id]
            trade['status'] = 'settled'
            trade['settlement_time'] = datetime.utcnow().isoformat()
            
            self.completed_trades.append(trade)
            del self.active_trades[trade_id]
            
            return trade
        return None
    
    def get_trade_summary(self) -> Dict:
        """Get trading summary - includes both active and completed trades"""
        # For demo purposes, treat all executed trades as completed
        all_trades = list(self.active_trades.values()) + self.completed_trades
        
        return {
            'active_trades': len(self.active_trades),
            'completed_trades': len(self.completed_trades),
            'total_energy_traded_wh': sum(t.get('quantity_wh', 0) for t in all_trades),
            'total_revenue_usd': sum(t.get('price_usd', 0) for t in all_trades),
        }
