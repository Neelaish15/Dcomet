import os
import pandapower as pp

import pandapower.plotting as plot

import matplotlib.pyplot as plt
import socket
import openai

openai.api_key = os.environ.get("OPENAI_API_KEY")

from autogen import register_function
from autogen import AssistantAgent, UserProxyAgent, GroupChat, GroupChatManager


net = pp.create_empty_network()
bus1 = pp.create_bus(net, vn_kv=11, name="Bus 1 (Grid)")

bus2 = pp.create_bus(net, vn_kv=11, name="Bus 2 (11 kV Load)")  

bus3 = pp.create_bus(net, vn_kv=11, name="Bus 3 (Transformer HV)")

bus4 = pp.create_bus(net, vn_kv=0.415, name="Bus 4 (Transformer LV)")
pp.create_ext_grid(net, bus=bus1, vm_pu=1.0, name="DSO Grid Connection")

# Line from Bus 1 to Bus 2 (1 km)

pp.create_line_from_parameters(net, from_bus=bus1, to_bus=bus2, length_km=1,

                               r_ohm_per_km=0.5, x_ohm_per_km=0.1, c_nf_per_km=0,

                               max_i_ka=1, name="Line 1")

# Load at Bus 2 (5 MW, 0.5 MVAr)

pp.create_load(net, bus=bus2, p_mw=5.0, q_mvar=0.5, name="Load at Bus 2")

# Line from Bus 2 to Bus 3 (5 km)

pp.create_line_from_parameters(net, from_bus=bus2, to_bus=bus3, length_km=5,

                               r_ohm_per_km=0.5, x_ohm_per_km=0.1, c_nf_per_km=0,

                               max_i_ka=1, name="Line 2")

# Transformer from Bus 3 to Bus 4 (11 kV to 415 V)

pp.create_transformer_from_parameters(net, hv_bus=bus3, lv_bus=bus4,

                                      sn_mva=2.0, vn_hv_kv=11, vn_lv_kv=0.415,

                                      vk_percent=6, vkr_percent=1.0,

                                      pfe_kw=0.1, i0_percent=0.1,

                                      name="11kV/415V Transformer")

# Load at Bus 4 (1 MW, 0.1 MVAr)

pp.create_load(net, bus=bus4, p_mw=1.0, q_mvar=0.1, name="Load at Bus 4")

# Run power flow

pp.runpp(net)

# Display load flow results in a separate window

#plt.figure("Load Flow Results")

#plt.axis('off')

#results_text = f"Bus Voltages (pu):\\n{net.res_bus[['vm_pu']]}\\n\\nLine Loading (%):\\n{net.res_line[['loading_percent']]}"
results_text = (f"Bus Voltages (pu):\n{net.res_bus[['vm_pu']].to_string(index=True)}"
    f"\n\nLine Loading (%):\n{net.res_line[['loading_percent']].to_string(index=True)}"
)
#plt.text(0.1, 0.5, results_text, fontsize=12)
#print(results_text)
#-----agent part-----

def ExcessPower(value2):
    if value2>512:
        return (f"excess:{value2-512}")
    else:
        return "no excess"
#register_function(ExcessPower, caller_name="DERAgent", executor_name="DERAgent", description="Check if there is excess DER power based on DER voltage")

def lfa(upt):
    return upt
DER_agent = AssistantAgent(
    name="DERAgent",
    system_message="You are a DER agent. Check whenever there is excess DER power by looking at DER current.",
    llm_config={"config_list": [{"model": "gpt-4"}]},
    function_map={"ExcessPower": ExcessPower}
)
DSO_agent = AssistantAgent(
    name="DSOAgent",
    system_message="You are DSO agent. Use tools to report load flow results.",
    llm_config={"config_list": [{"model": "gpt-4"}]},
    function_map={"lfa": lfa}
)
coordinator_agent = UserProxyAgent(
    name="CoordinatorAgent",
    human_input_mode="NEVER",
    system_message="You are the coordinator. Ask DERagent and DSOagent to run tools and make decisions."
)


group_chat = GroupChat(agents=[DER_agent, DSO_agent, coordinator_agent], messages=[])
manager = GroupChatManager(groupchat=group_chat)

#from autogen import ExcessPower
#from autogen import lfa

HOST = '0.0.0.0'  # Listen on all interfaces
PORT = 53614 

print(f"Starting UDP server on {HOST}:{PORT}")
try:
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        s.bind((HOST, PORT))
        #print("Waiting for UDP datagrams...")
        while True:
            data, addr = s.recvfrom(1024)
            received_data = data.decode('utf-8').strip()
            if received_data:
                try:   
                    value1_str, value2_str = received_data.split(',')
                    value1 = int(value1_str)
                    value2 = int(value2_str)
                    print(f"Received from {addr}: DER_Current = {value1}, DER_Voltage = {value2}")
                    #net.bus.loc[net.bus[net.bus.name == "Bus 4 (Transformer LV)"].index, 'vn_kv'] = value2 / 1000  # Convert V to kV
                    net.bus.loc[bus4, 'vm_pu'] = value2 * (415/ 1024)  # Assuming 415V is 1.0 pu
                    #pp.runpp(net)
                    upt=pp.runpp(net)
                    resp = coordinator_agent.initiate_chat(
                        manager,
                        message="DERAgent, notify any excess power. DSOAgent, show power flow results."
                    )
                    
                    
        
                    
    

                    #from autogen import ExcessPower
                    #from autogen import AssistantAgent, UserProxyAgent, GroupChat, GroupChatManager

                    

                    

                    
                    print("Agent responses:")
                    print(resp)
                except ValueError:
                    print(f"Received data from {addr}: {received_data}")
except Exception as e:
    print(f"An error occurred: {e}")
#socket.close()

