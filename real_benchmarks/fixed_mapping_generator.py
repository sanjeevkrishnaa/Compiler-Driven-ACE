"""
Fixed Mapping Generator - Maps logical qubits to physical cores with fixed positions.
Generates traffic only for cross-core gate operations.
"""

import json
import networkx as nx
from typing import List, Dict, Any, Tuple, Optional
from splitter import QASMAnalyzer, CircuitSplitter
from qiskit.providers.fake_provider import GenericBackendV2
from mqt.bench import BenchmarkLevel, get_benchmark


class FixedMappingGenerator:
    """
    Maps logical qubits to cores with fixed positions.
    Supports two stride modes:
      - stride=1 (default): Qubit i -> physical slot i (dense packing).
                  Core = physical_slot // qubits_per_core
      - stride=2: Qubits are interleaved across physical slots.
                  First fill odd positions (1, 3, 5, …) then even (0, 2, 4, …).
                  Logical qubit 0 -> slot 1, 1 -> slot 3, 2 -> slot 5, …
                  Once odd slots are exhausted, continue with even: 0, 2, 4, …
    Generates traffic requests only when gates involve qubits in different cores.
    """
    
    def __init__(self, dim_x: int, dim_y: int, qubits_per_core: int, stride: int = 1):
        """
        Initialize the fixed mapping generator.
        
        Args:
            dim_x: Number of cores in x-direction (columns)
            dim_y: Number of cores in y-direction (rows)
            qubits_per_core: Maximum number of qubits per core
            stride: Mapping stride (1 = dense, 2 = interleaved)
        """
        if stride not in (1, 2):
            raise ValueError(f"Unsupported stride {stride}. Must be 1 or 2.")
        self.dim_x = dim_x
        self.dim_y = dim_y
        self.qubits_per_core = qubits_per_core
        self.stride = stride
        self.total_cores = dim_x * dim_y
        self.total_capacity = self.total_cores * qubits_per_core
        
        # Pre-compute the logical-to-physical-slot mapping
        self._slot_map = self._build_slot_map()
    
    def _build_slot_map(self) -> List[int]:
        """
        Build the ordered list of physical slot indices that logical qubits
        will be assigned to, based on the stride.
        
        Returns:
            List where index = logical qubit, value = physical slot number
        """
        total = self.total_capacity
        if self.stride == 1:
            # Dense: logical qubit i -> physical slot i
            return list(range(total))
        else:
            # Stride-2 interleaved: odd slots first, then even slots
            odd_slots = list(range(1, total, 2))    # 1, 3, 5, …
            even_slots = list(range(0, total, 2))   # 0, 2, 4, …
            return odd_slots + even_slots
    
    def qubit_to_core(self, logical_qubit: int) -> int:
        """
        Convert logical qubit number to core number using the stride mapping.
        
        Args:
            logical_qubit: The logical qubit number
            
        Returns:
            Core number (0 to total_cores-1)
        """
        if logical_qubit >= len(self._slot_map):
            raise ValueError(f"Qubit {logical_qubit} exceeds capacity. "
                           f"Max qubits: {self.total_capacity}")
        physical_slot = self._slot_map[logical_qubit]
        core = physical_slot // self.qubits_per_core
        if core >= self.total_cores:
            raise ValueError(f"Qubit {logical_qubit} (slot {physical_slot}) exceeds capacity. "
                           f"Max qubits: {self.total_capacity}")
        return core
    
    def core_to_router_name(self, core: int) -> str:
        """
        Convert core number to router name in format 'router_x_y'.
        
        Args:
            core: Core number
            
        Returns:
            Router name string
        """
        row = core // self.dim_x
        col = core % self.dim_x
        return f"router_{col}_{row}"
    
    def qubit_position_in_core(self, logical_qubit: int) -> int:
        """
        Get the position of a qubit within its core.
        
        Args:
            logical_qubit: The logical qubit number
            
        Returns:
            Position within core (0 to qubits_per_core-1)
        """
        physical_slot = self._slot_map[logical_qubit]
        return physical_slot % self.qubits_per_core
    
    def initialize_mapping(self, num_logical_qubits: int) -> Dict[int, int]:
        """
        Initialize fixed mapping for all logical qubits.
        
        Args:
            num_logical_qubits: Number of logical qubits in the circuit
            
        Returns:
            Dictionary mapping logical_qubit -> core_number
        """
        if num_logical_qubits > self.total_capacity:
            raise ValueError(f"Cannot map {num_logical_qubits} qubits. "
                           f"Total capacity: {self.total_capacity} "
                           f"({self.total_cores} cores × {self.qubits_per_core} qubits/core)")
        
        mapping = {}
        for qubit in range(num_logical_qubits):
            mapping[qubit] = self.qubit_to_core(qubit)
        
        return mapping
    
    def generate_traffic_from_slices(self, slices: List[nx.Graph], 
                                     num_logical_qubits: int,
                                     priority: int = 1,
                                     start_time: float = 0.01,
                                     duration: int = 1) -> List[List[List]]:
        """
        Generate layered traffic patterns from circuit slices.
        Only generates traffic for cross-core two-qubit gates.
        
        Args:
            slices: List of networkx graphs representing circuit layers
            num_logical_qubits: Number of logical qubits
            priority: Priority for all requests (default: 1)
            start_time: Start time for all requests (default: 0.01)
            duration: Duration for all requests (default: 1)
            
        Returns:
            List of layers, each containing traffic requests in format:
            [request_id, src_router, dst_router, priority, start_time, duration]
        """
        # Initialize mapping
        qubit_to_core_map = self.initialize_mapping(num_logical_qubits)
        
        layers = []
        request_id = 0  # Global request counter
        
        for layer_idx, slice_graph in enumerate(slices):
            layer_traffic = []
            
            # Process two-qubit gates (edges in the graph)
            for edge in slice_graph.edges(data=True):
                q1, q2, edge_data = edge
                gate_name = edge_data.get('gate', 'cx')
                
                # Get cores for both qubits
                core1 = qubit_to_core_map[q1]
                core2 = qubit_to_core_map[q2]
                
                # Only generate traffic if qubits are in different cores
                if core1 != core2:
                    src_router = self.core_to_router_name(core1)
                    dst_router = self.core_to_router_name(core2)
                    
                    # Create traffic entry: [request_id, src, dst, priority, time, duration]
                    traffic_entry = [
                        request_id,
                        src_router,
                        dst_router,
                        priority,
                        start_time,
                        duration
                    ]
                    layer_traffic.append(traffic_entry)
                    request_id += 1  # Increment for next request
            
            # Append layer (even if empty - signifies no cross-core requests)
            layers.append(layer_traffic)
        
        return layers
    
    def save_to_json(self, traffic_layers: List[List[List]], 
                     output_file: str,
                     circuit_type: str = "unknown"):
        """
        Save traffic patterns to JSON file with metadata header.
        Format:
        {
          "circuit_type": "qft",
          "num_rows": 4,
          "num_cols": 4,
          "qubits_per_core": 8,
          "stride": 1,
          "layers": [
            [[req_id, src, dst, priority, time, duration], ...],  # Layer 0
            ...
          ]
        }
        
        Args:
            traffic_layers: Traffic layers from generate_traffic_from_slices
            output_file: Output JSON filename
            circuit_type: Name of the quantum circuit benchmark
        """
        output_data = {
            "circuit_type": circuit_type,
            "num_rows": self.dim_y,
            "num_cols": self.dim_x,
            "qubits_per_core": self.qubits_per_core,
            "stride": self.stride,
            "layers": traffic_layers
        }
        with open(output_file, 'w') as f:
            json.dump(output_data, f, indent=2)
    
    def print_mapping_info(self, num_logical_qubits: int):
        """Print mapping information"""
        print(f"Fixed Mapping Configuration (stride={self.stride}):")
        print(f"Grid: {self.dim_x}x{self.dim_y} = {self.total_cores} cores")
        print(f"Qubits per core: {self.qubits_per_core}")
        print(f"Stride: {self.stride}")
        print(f"Total capacity: {self.total_capacity} qubits")
        print(f"\nMapping {num_logical_qubits} logical qubits:")
        
        qubit_to_core_map = self.initialize_mapping(num_logical_qubits)
        
        # Group by core
        core_to_qubits = {}
        for qubit, core in qubit_to_core_map.items():
            if core not in core_to_qubits:
                core_to_qubits[core] = []
            core_to_qubits[core].append(qubit)
        
        for core in sorted(core_to_qubits.keys()):
            router = self.core_to_router_name(core)
            qubits = core_to_qubits[core]
            slots = [self._slot_map[q] for q in qubits]
            print(f"  {router} (Core {core}): Qubits {qubits} -> Slots {slots}")


def example_usage():
    """Example usage with a sample circuit"""
    
    # Circuit parameters
    num_qubits = 64
    benchmark = "qft"
    
    # Grid parameters
    dim_x = 4
    dim_y = 4
    qubits_per_core = 4
    
    # Get benchmark circuit
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
    
    # Analyze and split circuit
    analyzer = QASMAnalyzer(qc_target)
    analysis_result = analyzer.analyze()
    
    splitter = CircuitSplitter()
    slices = splitter.slice_circuit(analysis_result["gates"])
    
    print(f"Circuit Analysis:")
    print(f"  Benchmark: {benchmark}")
    print(f"  Qubits: {analysis_result['num_qubits']}")
    print(f"  Depth: {len(slices)}")
    print()
    
    # Create fixed mapping generator
    mapper = FixedMappingGenerator(dim_x=dim_x, dim_y=dim_y, qubits_per_core=qubits_per_core)
    mapper.print_mapping_info(analysis_result['num_qubits'])
    print()
    
    # Generate traffic
    traffic_layers = mapper.generate_traffic_from_slices(
        slices=slices,
        num_logical_qubits=analysis_result['num_qubits']
    )
    
    # Count statistics
    total_requests = sum(len(layer) for layer in traffic_layers)
    non_empty_layers = sum(1 for layer in traffic_layers if len(layer) > 0)
    
    print(f"Traffic Generation Results:")
    print(f"  Total layers: {len(traffic_layers)}")
    print(f"  Layers with cross-core requests: {non_empty_layers}")
    print(f"  Total cross-core requests: {total_requests}")
    print()
    
    # Save outputs
    json_filename = f"{benchmark}_fixed_{dim_x}x{dim_y}_q{qubits_per_core}_s{mapper.stride}_traffic.json"
    
    mapper.save_to_json(traffic_layers, json_filename, circuit_type=benchmark)
    print(f"Traffic saved to: {json_filename}")
    
    # Show sample traffic
    if total_requests > 0:
        print(f"\nSample traffic entries (first 5):")
        count = 0
        for layer in traffic_layers:
            for entry in layer:
                if count < 5:
                    print(f"  {entry}")
                    count += 1
                else:
                    break
            if count >= 5:
                break


if __name__ == "__main__":
    example_usage()
