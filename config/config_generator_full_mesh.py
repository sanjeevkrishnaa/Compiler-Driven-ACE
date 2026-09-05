"""This module generates JSON config files for networks in a 2D grid (mesh) configuration.

In a grid topology, routers are arranged in a grid pattern where each router is connected 
only to its immediate neighbors (up, down, left, right).

Help information may also be obtained using the `-h` flag.

Args:
    grid_size (int): dimension of the grid (grid_size x grid_size routers).
    memo_size (int): number of memories per node.
    qc_length (float): distance between nodes (in km).
    qc_atten (float): quantum channel attenuation (in dB/m).
    cc_delay (float): classical channel delay (in ms).

Optional Args:
    -d --directory (str): name of the output directory (default tmp)
    -o --output (str): name of the output file (default out.json).
    -s --stop (float): simulation stop time (in s) (default infinity).
    -p --parallel: sets simulation as parallel and requires addition args:
        server ip (str): IP address of quantum manager server.
        server port (int): port quantum manager server is attached to.
        num. processes (int): number of processes to use for simulation.
        sync/async (bool): denotes if timelines should be synchronous (true) or not (false).
        lookahead (int): simulation lookahead time for timelines (in ps).
    -n --nodes (str): path to csv file providing process information for nodes.
"""

import argparse
import json
import os
import pandas as pd
# from sequence.utils.config_generator import add_default_args, get_node_csv, generate_node_procs, generate_nodes, generate_classical, final_config, router_name_func
from sequence.topology.topology import Topology
from sequence.topology.router_net_topo import RouterNetTopo


parser = argparse.ArgumentParser()
parser.add_argument('grid_size', type=int, help='dimension of the grid (grid_size x grid_size routers)')
parser.add_argument('memo_size', type=int, help='number of memories per node')
parser.add_argument('qc_length', type=float, help='distance between nodes (in km)')
parser.add_argument('qc_atten', type=float, help='quantum channel attenuation (in dB/m)')
parser.add_argument('cc_delay', type=float, help='classical channel delay (in ms)')
parser.add_argument('-d', '--directory', type=str, default='tmp', help='name of output directory')
parser.add_argument('-o', '--output', type=str, default='out.json', help='name of output config file')
parser.add_argument('-s', '--stop', type=float, default=float('inf'), help='stop time (in s)')
parser.add_argument('-gf', '--gate_fidelity', type=float, default=1.0, help='gate fidelity')
parser.add_argument('-mf', '--measurement_fidelity', type=float, default=1.0, help='measurement fidelity')
parser.add_argument('-p', '--parallel', nargs=5, help='optional parallel arguments: server ip, server port, num. processes, sync/async, lookahead')
parser.add_argument('-n', '--nodes', type=str, help='path to csv file to provide process for each node')
args = parser.parse_args()

output_dict = {}

# templates
output_dict[Topology.ALL_TEMPLATES] = \
    {
        "perfect_memo": {
            "MemoryArray": {
                "fidelity": 1.0,
                "efficiency": 1.0
            }
        },
        "adaptive_protocol": {
            "MemoryArray": {
                "fidelity": 0.95,
                "efficiency": 0.6,
                "coherence_time": 2
            },
            "adaptive_max_memory": 0,
            "encoding_type": "single_heralded",
            "SingleHeraldedBSM": {
                "detectors": [
                    {
                        "efficiency": 0.95
                    },
                    {
                        "efficiency": 0.95
                    }
                ]
            }
        }
    }

# get csv file
def get_node_csv(node_file) -> dict:
    node_procs = {}

    # TODO: add length/proc assertions
    df = pd.read_csv(node_file)
    for name, group in zip(df['name'], df['group']):
        node_procs[name] = group

    return node_procs

def generate_node_procs(parallel, num_rows, num_cols, naming_func) -> dict:
    """map a node to a process"""
    if parallel:
        num_procs = int(parallel[2])
    else:
        num_procs = 1
    group_size = num_rows * num_cols / num_procs

    node_procs = {}
    for row in range(num_rows):
        for col in range(num_cols):
            node_procs[naming_func(row, col)] = int((row * num_cols + col) // group_size)
            
    
    # for i in range(net_size):
    #     node_procs[naming_func(i)] = int(i // group_size)

    return node_procs


def generate_nodes(node_procs: dict, router_names: str, memo_size: int, template: str = None, gate_fidelity: float = None, measurement_fidelity: float = None) -> list:
    """generate a list of node configs for quantum routers
    """
    nodes = []
    for i, name in enumerate(router_names):
        config = {Topology.NAME: name,
                  Topology.TYPE: RouterNetTopo.QUANTUM_ROUTER,
                  Topology.SEED: i,
                  RouterNetTopo.MEMO_ARRAY_SIZE: memo_size,
                  RouterNetTopo.GROUP: node_procs[name]}
        if template:
            config[Topology.TEMPLATE] = template
        if gate_fidelity:
            config[Topology.GATE_FIDELITY] = gate_fidelity
        if measurement_fidelity:
            config[Topology.MEASUREMENT_FIDELITY] = measurement_fidelity
        nodes.append(config)
    return nodes

def generate_classical(router_names: list, cc_delay: int) -> list:
    cchannels = []
    for node1 in router_names:
        for node2 in router_names:
            if node1 == node2:
                continue
            cchannels.append({Topology.SRC: node1,
                              Topology.DST: node2,
                              Topology.DELAY: cc_delay * 1e9})
    return cchannels

def router_name_func(row,col) -> str:
    """a function that returns the name of the router"""
    return f"router_{int(row)}_{int(col)}"


# get csv file (if present)
# total_routers = args.grid_size * args.grid_size
if args.nodes:
    node_procs = get_node_csv(args.nodes)
else:
    node_procs = generate_node_procs(args.parallel, args.grid_size, args.grid_size, router_name_func)

# generate router nodes
router_names = list(node_procs.keys())
template = 'adaptive_protocol'
nodes = generate_nodes(node_procs, router_names, args.memo_size, template, args.gate_fidelity, args.measurement_fidelity)

# Create a helper function to convert grid coordinates to router name
def get_router_name(row, col):
    return f"router_{row}_{col}"

# generate bsm nodes for grid topology
# In a grid, we connect each router only to its immediate neighbors (up, down, left, right)
bsm_names = []
bsm_connections = []

for row in range(args.grid_size):
    for col in range(args.grid_size):
        current_router = get_router_name(row, col)
        
        # Connect to right neighbor (if exists)
        if col < args.grid_size - 1:
            right_router = get_router_name(row, col + 1)
            bsm_name = f"BSM_{row}_{col}_{row}_{col+1}"
            bsm_names.append(bsm_name)
            bsm_connections.append((current_router, right_router, bsm_name))
        
        # Connect to bottom neighbor (if exists)
        if row < args.grid_size - 1:
            bottom_router = get_router_name(row + 1, col)
            bsm_name = f"BSM_{row}_{col}_{row+1}_{col}"
            bsm_names.append(bsm_name)
            bsm_connections.append((current_router, bottom_router, bsm_name))

bsm_nodes = [{Topology.NAME: bsm_name,
              Topology.TYPE: RouterNetTopo.BSM_NODE,
              Topology.SEED: i,
              RouterNetTopo.TEMPLATE: template}
             for i, bsm_name in enumerate(bsm_names)]

# handle parallel processing groups if enabled
if args.parallel:
    # distribute BSM nodes across groups
    num_groups = int(args.parallel[2])
    for i, bsm_node in enumerate(bsm_nodes):
        bsm_node[RouterNetTopo.GROUP] = i % num_groups

nodes += bsm_nodes
output_dict[Topology.ALL_NODE] = nodes

# generate quantum links and classical channels for each BSM connection
qchannels = []
cchannels = []

for router1, router2, bsm_name in bsm_connections:
    # quantum channels from each router to the BSM node
    qchannels.append({Topology.SRC: router1,
                      Topology.DST: bsm_name,
                      Topology.DISTANCE: args.qc_length * 1000 / 2,
                      Topology.ATTENUATION: args.qc_atten})
    qchannels.append({Topology.SRC: router2,
                      Topology.DST: bsm_name,
                      Topology.DISTANCE: args.qc_length * 1000 / 2,
                      Topology.ATTENUATION: args.qc_atten})
    
    # classical channels between BSM node and routers (bidirectional)
    for router in [router1, router2]:
        cchannels.append({Topology.SRC: bsm_name,
                          Topology.DST: router,
                        #   Topology.DISTANCE: args.qc_length * 1000 / 2,
                          Topology.DELAY: args.cc_delay * 1e9})
        cchannels.append({Topology.SRC: router,
                          Topology.DST: bsm_name,
                        #   Topology.DISTANCE: args.qc_length * 1000 / 2,
                          Topology.DELAY: args.cc_delay * 1e9})

output_dict[Topology.ALL_Q_CHANNEL] = qchannels

# # generate classical links between routers (for routing information)
# for row in range(args.grid_size):
#     for col in range(args.grid_size):
#         current_router = get_router_name(row, col)
        
#         # Connect to right neighbor (if exists)
#         if col < args.grid_size - 1:
#             right_router = get_router_name(row, col + 1)
#             # bsm_name = f"BSM_{row}_{col}_{row}_{col+1}"
#             # bsm_names.append(bsm_name)
#             # bsm_connections.append((current_router, right_router, bsm_name))
#             cchannels.append({Topology.SRC: current_router,
#                               Topology.DST: right_router,
#                             #   Topology.DISTANCE: args.cc_length * 1000 / 2,
#                               Topology.DELAY: args.cc_delay * 1e9})
#             cchannels.append({Topology.SRC: right_router,
#                               Topology.DST: current_router,
#                             #   Topology.DISTANCE: args.cc_length * 1000 / 2,
#                               Topology.DELAY: args.cc_delay * 1e9})
            
            
#         # Connect to bottom neighbor (if exists)
#         if row < args.grid_size - 1:
#             bottom_router = get_router_name(row + 1, col)
#             bsm_name = f"BSM_{row}_{col}_{row+1}_{col}"
#             bsm_names.append(bsm_name)
#             bsm_connections.append((current_router, bottom_router, bsm_name))
#             cchannels.append({Topology.SRC: current_router,
#                               Topology.DST: bottom_router,
#                             #   Topology.DISTANCE: args.cc_length * 1000 / 2,
#                               Topology.DELAY: args.cc_delay * 1e9})
#             cchannels.append({Topology.SRC: bottom_router,
#                               Topology.DST: current_router,
#                             #   Topology.DISTANCE: args.cc_length * 1000 / 2,
#                               Topology.DELAY: args.cc_delay * 1e9})


router_cchannels = generate_classical(router_names, args.cc_delay)
cchannels += router_cchannels
output_dict[Topology.ALL_C_CHANNEL] = cchannels

# write other config options to output dictionary
output_dict["stop_time"] = args.stop * 1e12  # convert to ps
if args.parallel:
    output_dict["parallel"] = {
        "server_ip": args.parallel[0],
        "server_port": int(args.parallel[1]),
        "num_processes": int(args.parallel[2]),
        "sync": args.parallel[3] == "true",
        "lookahead": int(args.parallel[4])
    }

# write final json
path = os.path.join(args.directory, args.output)
output_file = open(path, 'w')
json.dump(output_dict, output_file, indent=4)

# Example usage:
# python config/config_generator_full_mesh.py 4 10 1 0.0002 1 -d config -o grid_4x4.json -s 10 -gf 0.99 -mf 0.99
# python config/config_generator_full_mesh.py 3 10 1 0.0002 1 -d config -o grid_3x3.json -s 10 -gf 0.99 -mf 0.99