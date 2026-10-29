import json
import random
from typing import List, Dict, Union, Optional, Set, Any


class TrafficPattern:
    one_qubit_gates = ['h', 'x', 'y', 'z', 's']
    two_qubit_gates = ['cx', 'cz']

    def __init__(self, dim_x: int, dim_y: int, qubits_per_node: int = 1):
        self.dim_x = dim_x
        self.dim_y = dim_y
        self.nodes = list(range(dim_x * dim_y))
        self.qubits_per_node = qubits_per_node
        self.total_qubits = len(self.nodes) * qubits_per_node
        
        # Create qubit to node mapping
        self.qubit_to_node = {}
        self.node_to_qubits = {}
        
        for node in self.nodes:
            qubit_start = node * qubits_per_node
            qubit_end = qubit_start + qubits_per_node
            node_qubits = list(range(qubit_start, qubit_end))
            self.node_to_qubits[node] = node_qubits
            
            for qubit in node_qubits:
                self.qubit_to_node[qubit] = node

    def get_node_from_qubit(self, qubit: int) -> int:
        """Get the node number for a given qubit"""
        return self.qubit_to_node[qubit]
    
    def get_qubits_from_node(self, node: int) -> List[int]:
        """Get all qubits belonging to a node"""
        return self.node_to_qubits[node]
    
    def select_random_qubit_from_node(self, node: int) -> int:
        """Select a random qubit from the given node"""
        return random.choice(self.node_to_qubits[node])

    def _generate_single_pair_with_gate(self, pattern: str, hotspots: Optional[List[int]] = None, 
                                      hotspot_percentage: float = 0.8, 
                                      single_qubit_percentage: float = 0.1) -> Dict[str, Any]:
        # Generate traffic based on node patterns, then map to specific qubits
        
        if random.random() < single_qubit_percentage:
            # Single qubit gate - select random node, then random qubit from that node
            src_node = random.choice(self.nodes)
            src_qubit = self.select_random_qubit_from_node(src_node)
            gate = random.choice(self.one_qubit_gates)
            return {'src': src_qubit, 'dest': src_qubit, 'gate': gate, 
                   'src_node': src_node, 'dest_node': src_node}

        # Two qubit gates - follow pattern on node level, then select qubits
        if pattern == 'uniform':
            src_node = random.choice(self.nodes)
            dest_node = random.choice(self.nodes)
            while src_node == dest_node:
                dest_node = random.choice(self.nodes)
                
        elif pattern == 'transpose':
            src_node = dest_node = 0
            while src_node == dest_node:
                src_node = random.choice(self.nodes)
                i, j = divmod(src_node, self.dim_x)
                dest_node = j * self.dim_x + i
                
        elif pattern == 'hotspot':
            if hotspots is None:
                raise ValueError("Hotspots must be provided for 'hotspot' pattern")
            src_node = random.choice(self.nodes)
            
            if random.random() < hotspot_percentage:
                if len(hotspots) == 1:
                    dest_node = hotspots[0]
                    while src_node == dest_node:
                        src_node = random.choice(self.nodes)
                else:
                    dest_node = random.choice(hotspots)
                    while src_node == dest_node:
                        dest_node = random.choice(hotspots)
                
                if random.random() < 0.5:
                    # Swap src and dest for variety
                    src_node, dest_node = dest_node, src_node
            else:
                non_hotspots = [n for n in self.nodes if n not in hotspots]
                dest_node = random.choice(non_hotspots)
                while src_node == dest_node:
                    dest_node = random.choice(non_hotspots)
        
        elif pattern == 'bit_reversal':
            num_nodes = len(self.nodes)
            src_node = dest_node = 0
            while src_node == dest_node:
                src_node = random.choice(self.nodes)
                if src_node == 0:
                    dest_node = 0
                else:
                    # Reverse all bits of src_node and take mod
                    dest_node = int(bin(src_node)[2:][::-1], 2) % num_nodes

        elif pattern == 'perfect_shuffle':
            num_nodes = len(self.nodes)
            src_node = dest_node = 0
            while src_node == dest_node:
                src_node = random.choice(self.nodes)
                if src_node==0:
                    dest_node=0
                else:
                    # Rotate left by 1 bit and take mod
                    dest_node = ((src_node << 1) | (src_node >> (src_node.bit_length() - 1))) % num_nodes
                
        elif pattern == 'butterfly':
            num_nodes = len(self.nodes)
            src_node = dest_node = 0
            while src_node == dest_node:
                src_node = random.choice(self.nodes)

                # Swap most and least significant bits and take mod
                if src_node == 0:
                    dest_node = 0
                else:
                    bit_len = src_node.bit_length()
                    lsb = src_node & 1  # least significant bit
                    msb = (src_node >> (bit_len - 1)) & 1  # most significant bit
                    
                    # Clear the LSB and MSB, then set them swapped
                    dest_node = src_node & ~1  # clear LSB
                    dest_node = dest_node & ~(1 << (bit_len - 1))  # clear MSB
                    dest_node = dest_node | (msb)  # set LSB to old MSB
                    dest_node = dest_node | (lsb << (bit_len - 1))  # set MSB to old LSB
                    dest_node = dest_node % num_nodes
            
        elif pattern == 'alternate_matrix_complement':
            # i,j to n-i,n-j mapping
            src_node = dest_node = 0
            while src_node == dest_node:
                src_node = random.choice(self.nodes)
                i, j = divmod(src_node, self.dim_x)
                dest_node = (self.dim_x - 1 - i) * self.dim_x + (self.dim_y - 1 - j)
        
        elif pattern == 'complement':
            num_nodes = len(self.nodes)
            src_node = dest_node = 0
            while src_node == dest_node:
                src_node = random.choice(self.nodes)
                # Calculate number of bits needed and create mask
                bits_needed = (num_nodes - 1).bit_length() if num_nodes > 1 else 1
                mask = (1 << bits_needed) - 1
                
                # Bitwise complement and mask the last needed bits
                dest_node = ((~src_node) & mask) % num_nodes
                    

        else:
            raise ValueError(f"Unknown pattern: {pattern}")

        # Now select specific qubits from the chosen nodes
        src_qubit = self.select_random_qubit_from_node(src_node)
        dest_qubit = self.select_random_qubit_from_node(dest_node)
        gate = random.choice(self.two_qubit_gates)
        
        return {'src': src_qubit, 'dest': dest_qubit, 'gate': gate,
               'src_node': src_node, 'dest_node': dest_node}

    def generate_random_traffic_pairs(self, pattern: str, num_pairs: int, 
                                    num_hotspots: Optional[int] = 1) -> List[Dict[str, Any]]:
        """Generate random traffic pairs following the specified pattern"""
        pairs_with_gates = []
        hotspots = None
        
        if pattern == 'hotspot' and num_hotspots is not None and num_hotspots > 0:
            hotspots = random.sample(self.nodes, num_hotspots)
            print(f"Using hotspots: {hotspots}")

        for _ in range(num_pairs):
            pair = self._generate_single_pair_with_gate(pattern, hotspots)
            pairs_with_gates.append(pair)
            
        return pairs_with_gates

    def generate_layered_traffic_pairs(self, pattern: str, max_num_pairs_per_layer: int, 
                                 num_layers: int, num_hotspots: int = 1, hotspot_percentage: float = 0.8) -> List[List[Dict[str, Any]]]:
        """Generate layered traffic with disjoint qubit usage.
        For hotspot pattern: calculates max achievable pairs while maintaining the desired percentage."""
        
        fixed_hotspots = []
        final_max_pairs = max_num_pairs_per_layer
        hotspot_target = non_hotspot_target = 0

        if pattern == 'hotspot':
            fixed_hotspots = random.sample(self.nodes, num_hotspots)
            print(f"Using fixed hotspots for layers: {fixed_hotspots}")
            hotspot_qubits = set()
            for h in fixed_hotspots:
                hotspot_qubits.update(self.node_to_qubits[h])
            available_hotspot_qubits = len(hotspot_qubits)
            
            # Calculate max pairs that can maintain the desired percentage
            max_pairs_for_percentage = int(available_hotspot_qubits / hotspot_percentage)
            final_max_pairs = min(max_num_pairs_per_layer, max_pairs_for_percentage)
            
            # Now calculate targets based on the final max pairs
            hotspot_target = int(final_max_pairs * hotspot_percentage)
            non_hotspot_target = final_max_pairs - hotspot_target
        
                

        layers = []
        for layer_idx in range(num_layers):
            layer = []
            used_qubits: Set[int] = set()
            attempts = 0

            max_attempts = final_max_pairs * 20  # safety
            hotspot_count = 0
            non_hotspot_count = 0

            while len(layer) < final_max_pairs and attempts < max_attempts:
                if pattern == 'hotspot':
                    # Force category if one side hasn't met target
                    if hotspot_count < hotspot_target:
                        candidate = self._generate_single_pair_with_gate(
                            pattern, fixed_hotspots, hotspot_percentage=1.0
                        )
                    elif non_hotspot_count < non_hotspot_target:
                        candidate = self._generate_single_pair_with_gate(
                            pattern, fixed_hotspots, hotspot_percentage=0.0
                        )
                    else:
                        # All targets met, random choice allowed
                        candidate = self._generate_single_pair_with_gate(
                            pattern, fixed_hotspots, hotspot_percentage=hotspot_percentage
                        )
                else:
                    candidate = self._generate_single_pair_with_gate(pattern, fixed_hotspots)

                src_qubit, dest_qubit = candidate['src'], candidate['dest']
                qubits_involved = {src_qubit} if src_qubit == dest_qubit else {src_qubit, dest_qubit}

                if qubits_involved.isdisjoint(used_qubits):
                    layer.append(candidate)
                    used_qubits.update(qubits_involved)

                    if pattern == 'hotspot':
                        if candidate['dest_node'] in fixed_hotspots:
                            hotspot_count += 1
                        else:
                            non_hotspot_count += 1

                attempts += 1

            if len(layer) < final_max_pairs:
                print(f"Warning: Layer {layer_idx} only has {len(layer)} pairs instead of {final_max_pairs}")
                if pattern == 'hotspot':
                    print(f"  Achieved: {hotspot_count} hotspot + {non_hotspot_count} non-hotspot")
                    actual_percentage = hotspot_count / len(layer) if len(layer) > 0 else 0
                    print(f"  Actual hotspot percentage: {actual_percentage:.1%}")

            layers.append(layer)

        return layers


    def print_mapping_info(self):
        """Print qubit to node mapping information"""
        print(f"Grid: {self.dim_x}x{self.dim_y}, Qubits per node: {self.qubits_per_node}")
        print(f"Total nodes: {len(self.nodes)}, Total qubits: {self.total_qubits}")
        print("\nNode to Qubits mapping:")
        for node in sorted(self.nodes):
            qubits = self.node_to_qubits[node]
            print(f"Node {node}: Qubits {qubits}")


# Example usage with multiple qubits per node:
pattern_gen = TrafficPattern(dim_x=4, dim_y=4, qubits_per_node=4)

# Print mapping information
pattern_gen.print_mapping_info()

# Generate traffic patterns
data = {
    'dim_x': 4,
    'dim_y': 4,
    'qubits_per_node': 3,
    'total_qubits': pattern_gen.total_qubits,
    'qubit_to_node_mapping': pattern_gen.qubit_to_node,
    'node_to_qubits_mapping': pattern_gen.node_to_qubits,
    'patterns': [
        {
            'name': 'uniform',
            'type': 'random',
            'traffic': pattern_gen.generate_random_traffic_pairs('uniform', num_pairs=1000)
        },
        {
            'name': 'transpose',
            'type': 'random',
            'traffic': pattern_gen.generate_random_traffic_pairs('transpose', num_pairs=1000)
        },
        {
            'name': 'hotspot',
            'type': 'random',
            'traffic': pattern_gen.generate_random_traffic_pairs('hotspot', 
                                                               num_pairs=10000, 
                                                               num_hotspots=4)
        },
        {
            'name': 'bit_reversal',
            'type': 'random',
            'traffic': pattern_gen.generate_random_traffic_pairs('bit_reversal', num_pairs=1000)
        },
        {
            'name': 'perfect_shuffle',
            'type': 'random',
            'traffic': pattern_gen.generate_random_traffic_pairs('perfect_shuffle', num_pairs=1000)
        },
        {
            'name': 'butterfly',
            'type': 'random',
            'traffic': pattern_gen.generate_random_traffic_pairs('butterfly', num_pairs=1000)
        },
        {
            'name': 'alternate_matrix_complement',
            'type': 'random',
            'traffic': pattern_gen.generate_random_traffic_pairs('alternate_matrix_complement', num_pairs=1000)
        },
        {
            'name': 'complement',
            'type': 'random',
            'traffic': pattern_gen.generate_random_traffic_pairs('complement', num_pairs=1000)
        },
        {
            'name': 'layered_uniform',
            'type': 'layered',
            'traffic': pattern_gen.generate_layered_traffic_pairs('uniform', 
                                                                max_num_pairs_per_layer=128,
                                                                num_layers=9)
        },
        {
            'name': 'layered_bit_reversal',
            'type': 'layered',
            'traffic': pattern_gen.generate_layered_traffic_pairs('bit_reversal',
                                                                max_num_pairs_per_layer=128,
                                                                num_layers=9)
        },
        {
            'name': 'layered_hotspot',
            'type': 'layered', 
            'traffic': pattern_gen.generate_layered_traffic_pairs('hotspot',
                                                                max_num_pairs_per_layer=128,
                                                                num_layers=9,
                                                                num_hotspots=4)
        }
    ]
}

# Save to file
with open('traffic_patterns.json', 'w') as f:
    json.dump(data, f, indent=4)

print(f"\nGenerated traffic patterns saved to traffic_patterns.json")
# print(f"Sample uniform traffic pair: {data['patterns'][0]['traffic'][0]}")
# print(f"Sample layered traffic layer 0: {data['patterns'][1]['traffic'][0][0] if data['patterns'][1]['traffic'] else 'None'}")
