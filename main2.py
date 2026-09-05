from collections import defaultdict
import numpy as np
from sequence.topology.router_net_topo import RouterNetTopo
from sequence.constants import MILLISECOND
import sequence.utils.log as log
from request_app import RequestAppThroughput, RequestAppLatency
from router_net_topo_adaptive import RouterNetTopoAdaptive
from traffic import TrafficMatrix


import random
from itertools import accumulate
from bisect import bisect_left

# Assuming SECOND is a constant, e.g., SECOND = 1_000_000_000_000
SECOND = 10**12

def get_request_queue_mesh(request_time: int, total_time: int, delta: int, memo_size: int, fidelity: float, entanglement_number: int, seed: int = 0) -> list:
    '''
    Generates a queue of requests for a 4x4 mesh network.

    Args:
        request_time (int): The time period for each request (in seconds).
        total_time (int): The total simulation time for all requests (in seconds).
        memo_size (int): The memory size for each request.
        fidelity (float): The fidelity requirement for each request.
        entanglement_number (int): The number of entanglements needed.
        seed (int): The random seed for reproducibility.
        
    Return:
        list: A list of requests, where each request is a tuple:
              (id, src_name, dst_name, start_time_ps, end_time_ps, memo_size, fidelity, entanglement_number)
    '''
    # Define the 4x4 grid of nodes
    nodes = [(i, j) for i in range(4) for j in range(4)]
    
    random.seed(seed)
    
    request_id = 0
    request_queue = []

    num_pairs = int(total_time // request_time)

    for i in range(num_pairs):
        src_coord, dst_coord = random.sample(nodes, 2)
        src_coord, dst_coord = random.sample(nodes, 2)

        src_name = f'router_{src_coord[0]}_{src_coord[1]}'
        dst_name = f'router_{dst_coord[0]}_{dst_coord[1]}'

        start_time = i*request_time + delta
        end_time =  (i+1) * request_time

        request = (
                request_id, 
                src_name, 
                dst_name, 
                round(start_time * SECOND), 
                round(end_time * SECOND), 
                memo_size, 
                fidelity, 
                entanglement_number
            )
        request_queue.append(request)
        request_id += 1

        
    return request_queue

# simulation of mesh/grid topology
def mesh_request_queue():

    network_config = 'config/grid_4x4.json'

    # log_filename = 'log/queue_tts/bottleneck20,qmem=0'
    log_filename = 'log/log'

    network_topo = RouterNetTopoAdaptive(network_config)
    
    tl = network_topo.get_timeline()

    log.set_logger(__name__, tl, log_filename)
    log.set_logger_level('INFO')
    # modules = ['timeline', 'network_manager', 'resource_manager', 'rule_manager', 'generation', 
    #            'purification', 'swapping', 'bsm', 'adaptive_continuous', 'memory_manager']
    modules = ['adaptive_continuous', 'request_app', 'swapping', 'network_manager', 'resource_manager', 'main', 'rule_manager', 'generation', 'swapping', 'purification','reservation']
    # modules = ['adaptive_continuous', 'request_app', 'swap_memory', 'reservation', 'resource_manager', 'rule_manager', 'generation', 'swapping']
    for module in modules:
        log.track_module(module)

    name_to_apps = {}
    for router in network_topo.get_nodes_by_type(RouterNetTopo.QUANTUM_ROUTER):
        app = RequestAppLatency(router)
        name_to_apps[router.name] = app
        # if router.name not in ['router_4', 'router_5']:
        #     router.active = False
        router.adaptive_continuous.has_empty_neighbor = True
        router.adaptive_continuous.update_prob = True

    num_nodes = len(name_to_apps)
    request_queue = get_request_queue_mesh(request_time=0.1, total_time=20, delta=0.01, memo_size=1, fidelity=0.01, entanglement_number=1, seed=0)
    print(request_queue)
    
    for request in request_queue:
        id, src_name, dst_name, start_time, end_time, memo_size, fidelity, entanglement_number = request
        app = name_to_apps[src_name]
        app.start(dst_name, start_time, end_time, memo_size, fidelity, entanglement_number, id)

    tl.init()
    tl.run()

    latency_dict = defaultdict(float)
    fidelity_dict      = defaultdict(list)
    for _, app in name_to_apps.items():
        latency_dict |= app.latency
        fidelity_dict |= app.entanglement_fidelities

    for reservation, latency in sorted(latency_dict.items()):
        fidelity = fidelity_dict[reservation][0]
        print(f'reservation={reservation}, time to serve={latency / MILLISECOND}, fidelity={fidelity:.6f}')


if __name__ == '__main__':
    verbose = True

    mesh_request_queue()
