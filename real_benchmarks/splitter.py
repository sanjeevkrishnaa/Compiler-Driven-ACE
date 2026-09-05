"""
Get benchmark.
split into src dest and gate.
build a graph based on src and dest, splitting the gates into layers.

further explore how to map the qubits into a backend.
"""

from qiskit.providers.fake_provider import GenericBackendV2
from mqt.bench import BenchmarkLevel, get_benchmark
from qiskit.qasm3 import dumps
from qiskit import QuantumCircuit
import networkx as nx
import sys
import random
from typing import List, Dict, Any, Optional
import json


class QASMAnalyzer:
    def __init__(self, circuit: QuantumCircuit):
        if not isinstance(circuit, QuantumCircuit):
            raise TypeError("Input must be a QuantumCircuit object")
        self.circuit = circuit

    def analyze(self):
        result = {
            "num_qubits": self.circuit.num_qubits,
            "num_clbits": self.circuit.num_clbits,
            "gates": []
        }
        # print(self.circuit)
        for instr, qargs, _ in self.circuit.data:
            if len(qargs) == 1:
                gate_name = instr.name
                qubit_index = self.circuit.find_bit(qargs[0]).index
                result["gates"].append({
                    "gate": gate_name,
                    "gate_type": 1,
                    "qubits": [qubit_index]
                })
            if len(qargs) == 2:
                gate_name = instr.name
                qubit_indices = [self.circuit.find_bit(q).index for q in qargs]
                result["gates"].append({
                    "gate": gate_name,
                    "gate_type": 2,
                    "qubits": qubit_indices
                })
            

        return result


class CircuitSplitter:
    def __init__(self):
        self.slices = []

    def slice_circuit(self, gates):
        """
        Break gates into timeslices using the dynamic Kahn's algorithm 
        while maintaining nx.Graph output format.
        """
        sys.stderr.write(f"number of gates: {len(gates)}\n")
        
        num_gates = len(gates)
        if num_gates == 0:
            return []
        
        # 1. Build dependency graph (Predecessors and Successors)
        predecessors = {i: set() for i in range(num_gates)}
        successors = {i: set() for i in range(num_gates)}
        
        last_used = {}  # qubit -> last gate index that used it
        for idx, gate_info in enumerate(gates):
            for q in gate_info["qubits"]:
                if q in last_used:
                    prev = last_used[q]
                    predecessors[idx].add(prev)
                    successors[prev].add(idx)
                last_used[q] = idx
        
        # 2. Initialize Kahn's Algorithm
        # A gate is 'ready' if all its predecessors have been scheduled
        ready = [i for i in range(num_gates) if not predecessors[i]]
        self.slices = []
        scheduled = set()
        gates_done = 0
        
        # 3. Process slices dynamically
        while ready:
            current_slice_indices = []
            used_qubits = set()
            
            # Identify gates that can fit in the current time slice 
            # (No qubit conflicts within this slice)
            remaining_ready = []
            for idx in ready:
                gate_qubits = set(gates[idx]["qubits"])
                if not used_qubits.intersection(gate_qubits):
                    current_slice_indices.append(idx)
                    used_qubits.update(gate_qubits)
                    scheduled.add(idx)
                else:
                    # If qubit conflict, keep it in the ready pool for the next slice
                    remaining_ready.append(idx)
            
            # Build the nx.Graph for the current slice to match original output format
            g = nx.Graph()
            for idx in current_slice_indices:
                gate_info = gates[idx]
                qpair = gate_info["qubits"]
                gate_name = gate_info["gate"]
                
                if len(qpair) == 1:
                    g.add_node(qpair[0], gate=gate_name)
                elif len(qpair) == 2:
                    g.add_edge(qpair[0], qpair[1], gate=gate_name)
            
            self.slices.append(g)
            
            # Update progress tracking
            gates_done += len(current_slice_indices)
            if gates_done % 1000 < len(current_slice_indices):
                sys.stderr.write(f"{gates_done} gates done\n")
            
            # 4. Update the 'ready' list for the next iteration
            # Find successors of the gates just scheduled that now have all dependencies met
            next_ready = set(remaining_ready)
            for idx in current_slice_indices:
                for succ in successors[idx]:
                    if succ not in scheduled and predecessors[succ].issubset(scheduled):
                        next_ready.add(succ)
            
            ready = sorted(list(next_ready)) # Sorting maintains deterministic behavior

        return self.slices
        
# from qubo paper
class CircuitSplitterGreedy:
    def __init__(self):
        self.slices = []

    def add_gate(self , gate_tuple, gate_name, t):
        if(len(gate_tuple) == 1):
            q1 = gate_tuple[0]
            while True:
                while len(self.slices) <= t:
                    self.slices.append(nx.Graph())

                # check if any edge with q1 exists
                if self.slices[t].has_node(q1) and self.slices[t].degree(q1) > 0:
                    t += 1
                    if len(self.slices) <= t:
                        self.slices.append(nx.Graph())
                    self.slices[t].add_node(q1, gate=gate_name)
                    break

                if self.slices[t].has_node(q1):
                    self.slices[t].nodes[q1]['gate'] = gate_name
                    break

                if t == 0:
                    self.slices[t].add_node(q1, gate=gate_name)
                    break
                t -= 1

        elif (len(gate_tuple) == 2):
            q1, q2 = gate_tuple
            while True:
                while len(self.slices) <= t:
                    self.slices.append(nx.Graph())

                if self.slices[t].has_edge(q1, q2):
                    break

                if q1 in self.slices[t].nodes or q2 in self.slices[t].nodes:
                    t += 1
                    if len(self.slices) <= t:
                        self.slices.append(nx.Graph())
                    self.slices[t].add_edge(q1, q2, gate=gate_name)
                    break
                
                if t == 0:
                    self.slices[t].add_edge(q1, q2, gate=gate_name)
                    break

                t -= 1

    def slice_circuit(self, gates):
        sys.stderr.write(f"number of gates: {len(gates)}\n")
        gates_done=0
        for gate_info in gates:
            qpair = gate_info["qubits"]
            gate_name = gate_info["gate"]
            t = sum(1 for g in self.slices if g.number_of_edges() > 0)
            self.add_gate(tuple(qpair), gate_name, t)
            gates_done+=1
            if gates_done%1000==0:
                sys.stderr.write(f"{gates_done} gates done\n")

        return self.slices     

# class MappingGenerator:
#     def __init__ (self, dim_x, dim_y, qubits_per_node):
#         self.dim_x = dim_x
#         self.dim_y = dim_y
#         self.qubits_per_node = qubits_per_node
#         self.qubit_to_node ={} # store which qubit in which node after each operation
#         self.node_to_qubits = {} # store which nodes have which logical qubits
    
class MappingGenerator:
    def __init__(self, dim_x: int, dim_y: int, qubits_per_node: int):
        self.dim_x = dim_x
        self.dim_y = dim_y
        self.nodes = list(range(dim_x * dim_y))
        self.qubits_per_node = qubits_per_node
        
        # Mapping state - tracks current location of logical qubits
        self.qubit_to_node = {}  # logical_qubit -> node
        self.node_to_qubits = {node: [] for node in self.nodes}  # node -> [logical_qubits]
    
    # need to change. error can be checked determinstically
    def initialize_random_mapping(self, num_logical_qubits: int):
        """Randomly assign logical qubits to nodes, respecting capacity constraints"""
        available_nodes = self.nodes.copy()
        random.shuffle(available_nodes)
        
        for logical_qubit in range(num_logical_qubits):
            # Find a node with available capacity
            placed = False
            for node in available_nodes:
                if len(self.node_to_qubits[node]) < self.qubits_per_node:
                    self.qubit_to_node[logical_qubit] = node
                    self.node_to_qubits[node].append(logical_qubit)
                    placed = True
                    break
            
            if not placed:
                raise ValueError(f"Cannot place logical qubit {logical_qubit}. "
                               f"Not enough capacity in nodes. "
                               f"Total capacity: {len(self.nodes) * self.qubits_per_node}, "
                               f"Required: {num_logical_qubits}")
    
    def get_node_from_qubit(self, logical_qubit: int) -> int:
        """Get current node of a logical qubit"""
        return self.qubit_to_node[logical_qubit]
    
    def move_qubit(self, qubit: int, target_node: int):
        """Move a qubit to a target node (assuming target has space)"""
        current_node = self.qubit_to_node[qubit]
        
        # Update qubit_to_node mapping
        self.qubit_to_node[qubit] = target_node
        
        # Update node_to_qubits mapping
        self.node_to_qubits[current_node].remove(qubit)
        self.node_to_qubits[target_node].append(qubit)
    
    def swap_qubits(self, qubit1: int, qubit2: int):
        """Swap the physical locations of two logical qubits"""
        node1 = self.qubit_to_node[qubit1]
        node2 = self.qubit_to_node[qubit2]
        
        # Update qubit_to_node mapping
        self.qubit_to_node[qubit1] = node2
        self.qubit_to_node[qubit2] = node1
        
        # Update node_to_qubits mapping
        self.node_to_qubits[node1].remove(qubit1)
        self.node_to_qubits[node1].append(qubit2)
        
        self.node_to_qubits[node2].remove(qubit2)
        self.node_to_qubits[node2].append(qubit1)
    
    def has_space(self, node: int) -> bool:
        """Check if a node has available space for another qubit"""
        return len(self.node_to_qubits[node]) < self.qubits_per_node
    
    def find_swap_candidate(self, target_node: int, exclude_qubit: int) -> Optional[int]:
        """Find a qubit in target_node that can be swapped (excluding the specified qubit)"""
        candidates = [q for q in self.node_to_qubits[target_node] if q != exclude_qubit]
        return random.choice(candidates) if candidates else None
    
    def generate_traffic_from_slices(self, slices: List[nx.Graph]) -> List[List[Dict[str, Any]]]:
        """Generate layered traffic patterns from circuit slices"""
        layers = []
        
        for layer_idx, slice_graph in enumerate(slices):
            layer_traffic = []
            
            # Process single-qubit gates (nodes)
            for node in slice_graph.nodes():
                if 'gate' in slice_graph.nodes[node]:
                    gate_name = slice_graph.nodes[node]['gate']
                    logical_qubit = node
                    current_node = self.get_node_from_qubit(logical_qubit)
                    
                    # Single qubit gate - src and dest are the same
                    traffic_entry = {
                        'src': logical_qubit,
                        'dest': logical_qubit,
                        'gate': gate_name,
                        'src_node': current_node,
                        'dest_node': current_node,
                        # 'type': 'single_qubit'
                    }
                    layer_traffic.append(traffic_entry)
            
            # Process two-qubit gates (edges)
            for edge in slice_graph.edges(data=True):
                q1, q2, edge_data = edge
                gate_name = edge_data.get('gate', 'cx')  # default to cx if not specified
                
                node1 = self.get_node_from_qubit(q1)
                node2 = self.get_node_from_qubit(q2)
                
                if node1 == node2:
                    # Both qubits are in the same node - local operation
                    traffic_entry = {
                        'src': q1,
                        'dest': q2,
                        'gate': gate_name,
                        'src_node': node1,
                        'dest_node': node2,
                        # 'type': 'local_two_qubit'
                    }
                    layer_traffic.append(traffic_entry)
                else:
                    # Qubits are in different nodes - need to bring them together
                    # Strategy 1: Check if either node has space for a simple move
                    # Strategy 2: If no space, perform a swap
                    
                    moved = False
                    
                    # Try to move q1 to node2 (where q2 is)
                    if self.has_space(node2):
                        old_q1_node = node1
                        self.move_qubit(q1, node2)
                        
                        # Add move operation to traffic
                        move_traffic = {
                            'src': q1,
                            'dest': q1,  # same qubit, different location
                            'gate': 'swap',
                            'src_node': old_q1_node,
                            'dest_node': node2,
                            # 'type': 'move'
                        }
                        layer_traffic.append(move_traffic)
                        moved = True
                        
                    # Try to move q2 to node1 (where q1 is)
                    elif self.has_space(node1):
                        old_q2_node = node2
                        self.move_qubit(q2, node1)
                        
                        # Add move operation to traffic
                        move_traffic = {
                            'src': q2,
                            'dest': q2,  # same qubit, different location
                            'gate': 'swap',
                            'src_node': old_q2_node,
                            'dest_node': node1,
                            # 'type': 'move'
                        }
                        layer_traffic.append(move_traffic)
                        moved = True
                        node2 = node1  # Update for the gate operation below
                    
                    # If no space available, fall back to swapping
                    if not moved:
                        swap_candidate = self.find_swap_candidate(node2, q2)
                        
                        if swap_candidate is not None:
                            # Perform the swap
                            old_q1_node = node1
                            old_swap_node = node2
                            
                            self.swap_qubits(q1, swap_candidate)
                            
                            # Add swap operation to traffic
                            swap_traffic = {
                                'src': q1,
                                'dest': swap_candidate,
                                'gate': 'swap',
                                'src_node': old_q1_node,
                                'dest_node': old_swap_node,
                                # 'type': 'swap'
                            }
                            layer_traffic.append(swap_traffic)
                            moved = True
                        else:
                            # Last resort: treat as remote operation
                            traffic_entry = {
                                'src': q1,
                                'dest': q2,
                                'gate': gate_name,
                                'src_node': node1,
                                'dest_node': node2,
                                # 'type': 'remote_two_qubit'
                            }
                            layer_traffic.append(traffic_entry)
                            continue  # Skip the local gate operation below
                    
                    # Now both qubits are in the same node - perform the gate operation
                    final_node = self.get_node_from_qubit(q1)  # Both should be in same node now
                    traffic_entry = {
                        'src': q1,
                        'dest': q2,
                        'gate': gate_name,
                        'src_node': final_node,
                        'dest_node': final_node,
                        # 'type': 'post_move_two_qubit' if 'move' in [op.get('type') for op in layer_traffic[-1:]] else 'post_swap_two_qubit'
                    }
                    layer_traffic.append(traffic_entry)
            
            layers.append(layer_traffic)
                    
        return layers
    
    def print_mapping_info(self):
        """Print current qubit to node mapping information"""
        print(f"Grid: {self.dim_x}x{self.dim_y}, Qubits per node: {self.qubits_per_node}")
        print(f"Total nodes: {len(self.nodes)}")
        print("\nCurrent mapping:")
        for node in sorted(self.nodes):
            qubits = self.node_to_qubits[node]
            if qubits:  # Only show nodes with qubits
                print(f"Node {node}: Logical qubits {qubits}")
        print(f"\nQubit to node mapping: {self.qubit_to_node}")


if __name__ == "__main__":
    num_qubits = 64
    benchmark = "qft"

    standard_gates = ["id", "x", "sx", "rz", "cx"]
    backend = GenericBackendV2(num_qubits=num_qubits, basis_gates=standard_gates)
    target = backend.target
    target.description = "Test Target"

    qc_target = get_benchmark(
        benchmark=benchmark,
        level=BenchmarkLevel.NATIVEGATES,
        circuit_size=num_qubits,
        target=target,
        opt_level=0,
    )

    # Analyze the circuit
    analyzer = QASMAnalyzer(qc_target)
    analysis_result = analyzer.analyze()
    print("Analysis Result:")
    print(f"Number of qubits: {analysis_result['num_qubits']}")
    print(f"Number of classical bits: {analysis_result['num_clbits']}")

    # Split the circuit into layers
    splitter = CircuitSplitter()
    slices = splitter.slice_circuit(analysis_result["gates"])
    print(f"\nCircuit depth: {len(slices)}")

    # Create mapping generator and initialize
    mapper = MappingGenerator(dim_x=4, dim_y=4, qubits_per_node=12)
    mapper.initialize_random_mapping(analysis_result['num_qubits'])
    
    print("\nInitial mapping:")
    mapper.print_mapping_info()
    
    # Generate traffic patterns
    layered_traffic = mapper.generate_traffic_from_slices(slices)
    
    print(f"\nGenerated {len(layered_traffic)} traffic layers")
    print(f"Total operations across all layers: {sum(len(layer) for layer in layered_traffic)}")
    
    # Create output similar to TrafficPattern format
    circuit_data = {
        'dim_x': mapper.dim_x,
        'dim_y': mapper.dim_y,
        'qubits_per_node': mapper.qubits_per_node,
        'logical_qubits': analysis_result['num_qubits'],
        'circuit_depth': len(slices),
        'benchmark': benchmark,
        'initial_mapping': dict(mapper.qubit_to_node),
        'patterns': [
            {
                'name': f'circuit_{benchmark}',
                'type': 'layered_circuit',
                'traffic': layered_traffic
            }
        ]
    }
    
    print(f"\nFinal mapping after processing:")
    mapper.print_mapping_info()

    with open(f'{benchmark}_real_random.json', 'w') as f:
        json.dump(circuit_data, f, indent=4)

