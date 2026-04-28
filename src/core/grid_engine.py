"""Grid Engine - PandaPower wrapper for power flow calculations"""
import pandapower as pp
import yaml
from typing import Dict, Any

class GridEngine:
    """
    Wrapper around PandaPower for power flow calculations.
    Loads grid from YAML config and runs power flow.
    """
    
    def __init__(self, grid_profile_path: str):
        self.net = None
        self.grid_profile_path = grid_profile_path
        self.buses = {}
        self.loads = {}
        self.ders = {}
        self._load_grid_profile()
    
    def _load_grid_profile(self):
        """Load grid profile from YAML and create PandaPower network"""
        with open(self.grid_profile_path, 'r') as f:
            profile = yaml.safe_load(f)
        
        # Create empty network
        self.net = pp.create_empty_network()
        
        # Create buses
        for bus_key, bus_data in profile.get('buses', {}).items():
            bus_id = pp.create_bus(
                self.net,
                vn_kv=bus_data['vn_kv'],
                name=bus_data['name']
            )
            self.buses[bus_key] = bus_id
        
        # Create external grid
        for ext_grid_key, ext_grid_data in profile.get('ext_grid', {}).items():
            bus_name = ext_grid_data['bus']
            bus_id = self.buses.get(bus_name)
            pp.create_ext_grid(
                self.net,
                bus=bus_id,
                vm_pu=ext_grid_data.get('vm_pu', 1.0),
                name=ext_grid_data['name']
            )
        
        # Create lines
        for line_key, line_data in profile.get('lines', {}).items():
            from_bus_name = line_data['from_bus']
            to_bus_name = line_data['to_bus']
            from_bus_id = self.buses.get(from_bus_name)
            to_bus_id = self.buses.get(to_bus_name)
            
            pp.create_line_from_parameters(
                self.net,
                from_bus=from_bus_id,
                to_bus=to_bus_id,
                length_km=line_data['length_km'],
                r_ohm_per_km=line_data['r_ohm_per_km'],
                x_ohm_per_km=line_data['x_ohm_per_km'],
                c_nf_per_km=0,
                max_i_ka=line_data['max_i_ka'],
                name=line_data['name']
            )
        
        # Create transformers
        for trafo_key, trafo_data in profile.get('transformers', {}).items():
            hv_bus_name = trafo_data['hv_bus']
            lv_bus_name = trafo_data['lv_bus']
            hv_bus_id = self.buses.get(hv_bus_name)
            lv_bus_id = self.buses.get(lv_bus_name)
            
            pp.create_transformer_from_parameters(
                self.net,
                hv_bus=hv_bus_id,
                lv_bus=lv_bus_id,
                sn_mva=trafo_data['sn_mva'],
                vn_hv_kv=trafo_data['vn_hv_kv'],
                vn_lv_kv=trafo_data['vn_lv_kv'],
                vk_percent=trafo_data['vk_percent'],
                vkr_percent=trafo_data['vkr_percent'],
                pfe_kw=trafo_data['pfe_kw'],
                i0_percent=trafo_data['i0_percent'],
                name=trafo_data['name']
            )
        
        # Create loads (initial)
        for load_key, load_data in profile.get('loads', {}).items():
            bus_name = load_data['bus']
            bus_id = self.buses.get(bus_name)
            
            load_id = pp.create_load(
                self.net,
                bus=bus_id,
                p_mw=load_data['p_mw'],
                q_mvar=load_data['q_mvar'],
                name=load_data['name']
            )
            self.loads[load_key] = load_id
    
    def run_power_flow(self) -> Dict[str, Any]:
        """Run power flow analysis"""
        try:
            pp.runpp(self.net)
            return {
                'converged': self.net.OPF_converged if hasattr(self.net, 'OPF_converged') else True,
                'bus_voltages': self.net.res_bus[['vm_pu']].to_dict(),
                'line_loading': self.net.res_line[['loading_percent']].to_dict(),
                'transformer_loading': self.net.res_trafo[['loading_percent']].to_dict() if len(self.net.res_trafo) > 0 else {},
            }
        except Exception as e:
            return {
                'converged': False,
                'error': str(e),
                'bus_voltages': {},
                'line_loading': {},
                'transformer_loading': {},
            }
    
    def get_bus_voltage(self, bus_name: str) -> float:
        """Get voltage of specific bus in PU"""
        bus_id = self.buses.get(bus_name)
        if bus_id is not None and not self.net.res_bus.empty:
            return self.net.res_bus.loc[bus_id, 'vm_pu']
        return 1.0
    
    def update_der_output(self, bus_id: int, power_mw: float):
        """Update DER output as negative load (generator)"""
        # Remove old DER from this bus if exists
        if bus_id in self.net.load.index:
            existing_loads = self.net.load[self.net.load['bus'] == bus_id]
            for idx in existing_loads.index:
                if 'DER' in self.net.load.loc[idx, 'name']:
                    self.net.load.drop(idx, inplace=True)
        
        # Add DER as negative load
        pp.create_load(
            self.net,
            bus=bus_id,
            p_mw=-power_mw,  # Negative = generation
            q_mvar=0,
            name=f"DER_Bus{bus_id}"
        )
    
    def get_grid_state(self) -> Dict[str, Any]:
        """Get current grid state"""
        return {
            'buses': self.net.bus.to_dict('index') if not self.net.bus.empty else {},
            'lines': self.net.line.to_dict('index') if not self.net.line.empty else {},
            'loads': self.net.load.to_dict('index') if not self.net.load.empty else {},
        }
