"""
Lightweight ML models for continuous learning in DCOMET agents.
Uses scikit-learn for forecasting and optimization without GPU.
"""
import numpy as np
from collections import deque
from datetime import datetime, timedelta
from sklearn.linear_model import LinearRegression
from sklearn.preprocessing import StandardScaler
import json


class SolarGenerationPredictor:
    """
    Predicts solar generation using time-of-day patterns and exponential smoothing.
    Learns continuously from actual readings.
    """
    def __init__(self, window_hours=24, smoothing_alpha=0.3):
        self.window_hours = window_hours
        self.smoothing_alpha = smoothing_alpha
        self.hourly_patterns = {}  # hour -> [list of readings]
        self.history = deque(maxlen=168)  # 7 days of hourly readings
        self.last_prediction = None
        
    def add_reading(self, timestamp, generation_w):
        """Add actual reading to history for continuous learning."""
        hour = timestamp.hour
        if hour not in self.hourly_patterns:
            self.hourly_patterns[hour] = []
        self.hourly_patterns[hour].append(generation_w)
        self.history.append({'timestamp': timestamp, 'generation_w': generation_w})
    
    def predict_next_hour(self, current_hour):
        """Predict generation for next hour based on historical patterns."""
        if len(self.history) < 3:
            return 5.0  # Default fallback
        
        # Get average for this hour from history
        if current_hour in self.hourly_patterns and len(self.hourly_patterns[current_hour]) > 0:
            hourly_avg = np.mean(self.hourly_patterns[current_hour])
            
            # Exponential smoothing with recent bias
            if self.last_prediction:
                prediction = (self.smoothing_alpha * hourly_avg + 
                             (1 - self.smoothing_alpha) * self.last_prediction)
            else:
                prediction = hourly_avg
        else:
            prediction = np.mean([g['generation_w'] for g in self.history]) if self.history else 5.0
        
        self.last_prediction = prediction
        return max(0, prediction)
    
    def get_confidence(self):
        """Return confidence score (0-1) based on data volume."""
        if len(self.history) < 3:
            return 0.1
        return min(0.95, len(self.history) / 168.0)


class DemandPredictor:
    """
    Predicts consumer demand using time-of-day patterns and linear regression.
    Learns from historical demand data.
    """
    def __init__(self):
        self.hourly_demand = {}  # hour -> [list of demands]
        self.history = deque(maxlen=168)
        self.model = LinearRegression()
        self.scaler = StandardScaler()
        self.is_trained = False
        
    def add_reading(self, timestamp, demand_w):
        """Add actual demand reading."""
        hour = timestamp.hour
        if hour not in self.hourly_demand:
            self.hourly_demand[hour] = []
        self.hourly_demand[hour].append(demand_w)
        self.history.append({'timestamp': timestamp, 'demand_w': demand_w})
        
        # Retrain model every 24 readings
        if len(self.history) % 24 == 0 and len(self.history) >= 24:
            self._train_model()
    
    def _train_model(self):
        """Train linear regression on time-based demand features."""
        if len(self.history) < 4:
            return
        
        X = []
        y = []
        for record in list(self.history)[-24:]:  # Use last 24 hours
            hour = record['timestamp'].hour
            day_of_week = record['timestamp'].weekday()
            X.append([hour, day_of_week])
            y.append(record['demand_w'])
        
        if len(X) >= 4:
            X = np.array(X)
            y = np.array(y)
            self.model.fit(X, y)
            self.is_trained = True
    
    def predict_demand(self, timestamp):
        """Predict demand for given timestamp."""
        if len(self.history) < 3:
            return 2.5  # Default fallback
        
        hour = timestamp.hour
        day_of_week = timestamp.weekday()
        
        if self.is_trained:
            try:
                pred = self.model.predict([[hour, day_of_week]])[0]
                return max(0, pred)
            except:
                pass
        
        # Fallback: use hourly average
        if hour in self.hourly_demand and self.hourly_demand[hour]:
            return np.mean(self.hourly_demand[hour])
        
        return np.mean([r['demand_w'] for r in self.history]) if self.history else 2.5


class PriceOptimizer:
    """
    Learns optimal pricing based on supply-demand ratio and trades volume.
    Uses gradient descent to optimize profit margin.
    """
    def __init__(self, base_price=0.12, learning_rate=0.01):
        self.base_price = base_price
        self.learning_rate = learning_rate
        self.trade_history = deque(maxlen=100)
        self.price_adjustments = []
        
    def add_trade(self, price_usd, quantity_w, accepted):
        """Record trade outcome for learning."""
        self.trade_history.append({
            'price': price_usd,
            'quantity': quantity_w,
            'accepted': accepted
        })
    
    def calculate_optimal_price(self, current_generation_w, demand_w, recent_trades=None):
        """
        Calculate optimal price using supply-demand ratio and recent success rate.
        Physics-based: if supply > demand, lower price; if supply < demand, raise price.
        """
        if recent_trades is None:
            recent_trades = list(self.trade_history)[-10:]
        
        # Supply-demand ratio
        if demand_w > 0:
            ratio = current_generation_w / demand_w
        else:
            ratio = 2.0  # Default: assume oversupply
        
        # Base adjustment on ratio
        if ratio > 1.5:  # Oversupply
            price_adjustment = 0.95
        elif ratio < 0.5:  # Undersupply
            price_adjustment = 1.10
        else:
            price_adjustment = 1.0
        
        # Fine-tune based on recent trade success
        if recent_trades:
            accepted_count = sum(1 for t in recent_trades if t['accepted'])
            success_rate = accepted_count / len(recent_trades)
            
            if success_rate < 0.3:  # Not selling well
                price_adjustment *= 0.95
            elif success_rate > 0.8:  # Selling well, increase price
                price_adjustment *= 1.05
        
        optimal_price = self.base_price * price_adjustment
        return max(0.05, min(0.50, optimal_price))  # Clamp between $0.05-0.50


class GridStateAnalyzer:
    """
    Learns normal grid state patterns for anomaly detection and constraint validation.
    Uses statistical methods for real-time monitoring.
    """
    def __init__(self):
        self.voltage_history = deque(maxlen=100)
        self.frequency_history = deque(maxlen=100)
        self.loading_history = deque(maxlen=100)
        self.mean_voltage = 1.0
        self.std_voltage = 0.02
        self.mean_loading = 0.3
        self.std_loading = 0.15
        
    def add_state(self, voltage_pu, frequency_hz, line_loading_pct):
        """Add grid state measurement."""
        self.voltage_history.append(voltage_pu)
        self.frequency_history.append(frequency_hz)
        self.loading_history.append(line_loading_pct)
        
        # Update running statistics
        if len(self.voltage_history) >= 5:
            self.mean_voltage = np.mean(list(self.voltage_history))
            self.std_voltage = np.std(list(self.voltage_history))
            self.mean_loading = np.mean(list(self.loading_history))
            self.std_loading = np.std(list(self.loading_history))
    
    def is_voltage_ok(self, voltage_pu):
        """Check if voltage is within acceptable range (±5%)."""
        return 0.95 <= voltage_pu <= 1.05
    
    def is_frequency_ok(self, frequency_hz):
        """Check if frequency is within acceptable range (49.5-50.5 Hz)."""
        return 49.5 <= frequency_hz <= 50.5
    
    def is_loading_safe(self, line_loading_pct):
        """Check if loading is within safe limits (< 80%)."""
        return line_loading_pct < 80.0
    
    def get_grid_health_score(self, voltage_pu, frequency_hz, loading_pct):
        """
        Calculate grid health (0-100) for agent decision-making.
        Higher score = safer to inject/consume.
        """
        voltage_score = 100 if self.is_voltage_ok(voltage_pu) else 40
        freq_score = 100 if self.is_frequency_ok(frequency_hz) else 30
        loading_score = max(0, 100 - (loading_pct / 0.8) * 100) if loading_pct < 80 else 20
        
        overall = (voltage_score * 0.3 + freq_score * 0.3 + loading_score * 0.4)
        return overall


class ContinuousLearningManager:
    """
    Central manager for all ML models with continuous learning across cycles.
    Persists and loads model state.
    """
    def __init__(self, state_file=None):
        self.solar_predictor = SolarGenerationPredictor()
        self.demand_predictor = DemandPredictor()
        self.price_optimizer = PriceOptimizer()
        self.grid_analyzer = GridStateAnalyzer()
        self.state_file = state_file or 'logs/ml_model_state.json'
        self.cycle_count = 0
        self.retrain_interval = 24
        self.last_retrain_cycle = 0
        self.drift_score = 0.0
        self.conservative_mode = False
        self.prediction_error_history = deque(maxlen=72)
        self.load_state()
    
    def update_from_cycle(self, cycle_data):
        """Update all models from a trading cycle."""
        timestamp = datetime.now()
        
        # Update generation predictor
        if 'der_generation_w' in cycle_data:
            predicted_generation = self.solar_predictor.predict_next_hour(timestamp.hour)
            self.solar_predictor.add_reading(timestamp, cycle_data['der_generation_w'])
            gen_abs_error = abs(float(cycle_data['der_generation_w']) - float(predicted_generation))
            self.prediction_error_history.append(gen_abs_error)
        
        # Update demand predictor
        if 'consumer_demand_w' in cycle_data:
            self.demand_predictor.add_reading(timestamp, cycle_data['consumer_demand_w'])
        
        # Update grid analyzer
        if all(k in cycle_data for k in ['voltage_pu', 'frequency_hz', 'loading_pct']):
            self.grid_analyzer.add_state(
                cycle_data['voltage_pu'],
                cycle_data['frequency_hz'],
                cycle_data['loading_pct']
            )
        
        # Update price optimizer
        if 'trade_price' in cycle_data and 'trade_quantity' in cycle_data:
            self.price_optimizer.add_trade(
                cycle_data['trade_price'],
                cycle_data['trade_quantity'],
                cycle_data.get('trade_accepted', False)
            )
        
        self.cycle_count += 1

        self._update_drift_state()
        self._maybe_retrain_models()
        
        # Save state every 10 cycles
        if self.cycle_count % 10 == 0:
            self.save_state()

    def _update_drift_state(self):
        if len(self.prediction_error_history) < 12:
            self.drift_score = 0.0
            self.conservative_mode = False
            return

        recent = list(self.prediction_error_history)[-12:]
        baseline = list(self.prediction_error_history)[:-12] or recent
        recent_mean = float(np.mean(recent))
        baseline_mean = float(np.mean(baseline))
        baseline_mean = baseline_mean if baseline_mean > 1e-6 else 1e-6
        self.drift_score = max(0.0, (recent_mean - baseline_mean) / baseline_mean)

        # Conservative policy during high error drift.
        self.conservative_mode = self.drift_score > 0.35

    def _maybe_retrain_models(self):
        should_retrain = (self.cycle_count - self.last_retrain_cycle) >= self.retrain_interval
        if not should_retrain:
            return

        self.demand_predictor._train_model()
        self.last_retrain_cycle = self.cycle_count

    def get_runtime_insights(self):
        return {
            'cycle_count': self.cycle_count,
            'drift_score': round(float(self.drift_score), 6),
            'conservative_mode': self.conservative_mode,
            'solar_prediction_confidence': self.solar_predictor.get_confidence(),
            'demand_model_trained': self.demand_predictor.is_trained,
            'last_retrain_cycle': self.last_retrain_cycle,
            'retrain_interval': self.retrain_interval,
        }
    
    def save_state(self):
        """Persist model state to disk."""
        try:
            state = {
                'cycle_count': self.cycle_count,
                'last_retrain_cycle': self.last_retrain_cycle,
                'drift_score': self.drift_score,
                'conservative_mode': self.conservative_mode,
                'solar_predictor': {
                    'hourly_patterns': {str(k): v for k, v in self.solar_predictor.hourly_patterns.items()},
                    'last_prediction': self.solar_predictor.last_prediction
                },
                'demand_predictor': {
                    'hourly_demand': {str(k): v for k, v in self.demand_predictor.hourly_demand.items()},
                    'is_trained': self.demand_predictor.is_trained
                },
                'timestamp': datetime.now().isoformat()
            }
            with open(self.state_file, 'w') as f:
                json.dump(state, f, indent=2)
        except Exception as e:
            print(f"[WARNING] Failed to save ML model state: {e}")
    
    def load_state(self):
        """Load model state from disk if available."""
        try:
            with open(self.state_file, 'r') as f:
                state = json.load(f)
                self.cycle_count = state.get('cycle_count', 0)
                self.last_retrain_cycle = state.get('last_retrain_cycle', 0)
                self.drift_score = state.get('drift_score', 0.0)
                self.conservative_mode = state.get('conservative_mode', False)
                # Can expand to restore more model details
        except FileNotFoundError:
            pass
        except Exception as e:
            print(f"[WARNING] Failed to load ML model state: {e}")
