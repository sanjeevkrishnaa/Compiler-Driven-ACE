#!/usr/bin/env python3
"""
Generate traffic patterns using fixed mapping approach.
Usage: python generate_fixed_mapping_traffic.py
"""

from splitter import QASMAnalyzer, CircuitSplitter
from fixed_mapping_generator import FixedMappingGenerator
from qiskit import QuantumCircuit, QuantumRegister
from qiskit.circuit.library import QFT, CDKMRippleCarryAdder, DraperQFTAdder, MCMTVChain
import sys


def generate_traffic_for_benchmark(benchmark: str, 
                                   num_qubits: int,
                                   dim_x: int,
                                   dim_y: int, 
                                   qubits_per_core: int,
                                   stride: int = 1,
                                   output_dir: str = "."):
    """
    Generate traffic patterns for a quantum circuit benchmark using fixed mapping.
    
    Args:
        benchmark: Benchmark name (e.g., 'qft', 'ae', 'dj', etc.)
        num_qubits: Number of qubits in the circuit
        dim_x: Grid width (number of columns)
        dim_y: Grid height (number of rows)
        qubits_per_core: Number of qubits per core
        stride: Mapping stride (1 = dense, 2 = interleaved)
        output_dir: Directory to save output files
    """
    print("="*70)
    print(f"Generating Fixed Mapping Traffic for {benchmark.upper()} (stride={stride})")
    print("="*70)
    
    # Get circuit from Qiskit
    print(f"\n1. Creating quantum circuit...")
    try:
        qc_target = get_circuit_by_name(benchmark, num_qubits)
        print(f"   - Circuit: {qc_target.name}")
        print(f"   - Qubits: {qc_target.num_qubits}")
    except ValueError as e:
        print(f"   ❌ Error: {e}")
        return
    
    # Analyze circuit
    print(f"\n2. Analyzing circuit...")
    analyzer = QASMAnalyzer(qc_target)
    analysis_result = analyzer.analyze()
    
    print(f"   - Qubits: {analysis_result['num_qubits']}")
    print(f"   - Classical bits: {analysis_result['num_clbits']}")
    print(f"   - Total gates: {len(analysis_result['gates'])}")
    
    # Split circuit into layers
    print(f"\n3. Splitting circuit into layers...")
    splitter = CircuitSplitter()
    slices = splitter.slice_circuit(analysis_result["gates"])
    print(f"   - Circuit depth: {len(slices)} layers")
    
    # Create fixed mapping generator
    print(f"\n4. Creating fixed mapping...")
    mapper = FixedMappingGenerator(dim_x=dim_x, dim_y=dim_y, qubits_per_core=qubits_per_core, stride=stride)
    
    print(f"   - Grid: {dim_x}x{dim_y} = {dim_x*dim_y} cores")
    print(f"   - Qubits per core: {qubits_per_core}")
    print(f"   - Stride: {stride}")
    print(f"   - Total capacity: {dim_x*dim_y*qubits_per_core} qubits")
    
    # Check if circuit fits
    if analysis_result['num_qubits'] > dim_x * dim_y * qubits_per_core:
        print(f"\n❌ ERROR: Circuit has {analysis_result['num_qubits']} qubits "
              f"but grid only supports {dim_x*dim_y*qubits_per_core} qubits!")
        return
    
    # Print mapping details
    print(f"\n5. Qubit to Core Mapping:")
    mapper.print_mapping_info(analysis_result['num_qubits'])
    
    # Generate traffic patterns
    print(f"\n6. Generating traffic patterns...")
    traffic_layers = mapper.generate_traffic_from_slices(
        slices=slices,
        num_logical_qubits=analysis_result['num_qubits'],
        priority=1,
        start_time=0.01,
        duration=1
    )
    
    # Statistics
    total_requests = sum(len(layer) for layer in traffic_layers)
    non_empty_layers = sum(1 for layer in traffic_layers if len(layer) > 0)
    empty_layers = len(traffic_layers) - non_empty_layers
    
    print(f"   - Total layers: {len(traffic_layers)}")
    print(f"   - Layers with traffic: {non_empty_layers}")
    print(f"   - Empty layers (local-only operations): {empty_layers}")
    print(f"   - Total cross-core requests: {total_requests}")
    
    # Save to files
    print(f"\n7. Saving output file...")
    
    # JSON file with traffic data (layered format)
    json_filename = f"{output_dir}/{benchmark}_fixed_{dim_x}x{dim_y}_q{qubits_per_core}_s{stride}_traffic.json"
    mapper.save_to_json(traffic_layers, json_filename, circuit_type=benchmark)
    print(f"   ✓ Traffic JSON: {json_filename}")
    

def create_qft_circuit(num_qubits: int) -> QuantumCircuit:
    """Create a QFT circuit using Qiskit's built-in QFT.
    QFT uses exactly num_qubits qubits, so it always fits.
    """
    qft = QFT(num_qubits, do_swaps=True)
    qft.name = 'QFT'
    return qft


def create_cuccaro_adder_circuit(num_qubits: int) -> QuantumCircuit:
    """
    Create a Cuccaro (CDKMRippleCarry) adder circuit using Qiskit's built-in implementation.
    CDKMRippleCarryAdder(n, kind='fixed') uses 2*n + 1 qubits.
    We pick the largest n such that 2*n + 1 <= num_qubits.
    """
    if num_qubits < 3:
        raise ValueError("Cuccaro adder requires at least 3 qubits")
    
    num_state_qubits = (num_qubits - 1) // 2  # largest n with 2n+1 <= num_qubits
    adder = CDKMRippleCarryAdder(num_state_qubits, kind='fixed')
    adder.name = 'Cuccaro_Adder'
    return adder


def create_draper_adder_circuit(num_qubits: int) -> QuantumCircuit:
    """
    Create a Draper (QFT-based) adder circuit using Qiskit's built-in implementation.
    DraperQFTAdder(n, kind='fixed') uses 2*n qubits.
    We pick the largest n such that 2*n <= num_qubits.
    """
    if num_qubits < 2:
        raise ValueError("Draper adder requires at least 2 qubits")
    
    num_state_qubits = num_qubits // 2  # largest n with 2n <= num_qubits
    adder = DraperQFTAdder(num_state_qubits, kind='fixed')
    adder.name = 'Draper_Adder'
    return adder


def create_mcmtv_circuit(num_qubits: int) -> QuantumCircuit:
    """
    Create a Multi-Control Multi-Target V-chain circuit using Qiskit's built-in implementation.
    MCMTVChain(gate, num_ctrl, num_target) uses num_ctrl + num_target + max(num_ctrl - 1, 0) qubits
    (the extra qubits are ancillas for the V-chain decomposition).
    We pick num_ctrl and num_target so the total fits within num_qubits.
    """
    if num_qubits < 3:
        raise ValueError("MCMTV requires at least 3 qubits")
    
    from qiskit.circuit.library import XGate
    
    # Total qubits = num_ctrl + num_target + max(num_ctrl - 1, 0)
    # For num_ctrl >= 2: total = 2*num_ctrl + num_target - 1
    # We want to maximise ctrl and tgt while keeping total <= num_qubits.
    # Fix num_target = 1 (minimum meaningful), solve for num_ctrl:
    #   2*num_ctrl + 1 - 1 <= num_qubits  =>  num_ctrl <= num_qubits // 2
    # Then use remaining qubits for more targets:
    #   num_target = num_qubits - 2*num_ctrl + 1  (if num_ctrl >= 2)
    
    num_ctrl = num_qubits // 3 + 1  # good balance between ctrl and tgt
    # Ensure at least 1 target
    num_target = max(1, num_qubits - 2 * num_ctrl + 1) if num_ctrl >= 2 else num_qubits - 1
    
    # Verify total fits and adjust if needed
    if num_ctrl >= 2:
        total = 2 * num_ctrl + num_target - 1
    else:
        total = num_ctrl + num_target
    
    while total > num_qubits and num_ctrl > 1:
        num_ctrl -= 1
        num_target = max(1, num_qubits - 2 * num_ctrl + 1)
        total = 2 * num_ctrl + num_target - 1
    
    mcmt = MCMTVChain(XGate(), num_ctrl, num_target)
    mcmt.name = 'MCMTV'
    
    assert mcmt.num_qubits <= num_qubits, \
        f"MCMTV circuit has {mcmt.num_qubits} qubits but grid only supports {num_qubits}"
    
    return mcmt


def get_circuit_by_name(circuit_name: str, num_qubits: int) -> QuantumCircuit:
    """Get a quantum circuit by name, fully decomposed into basic gates."""
    circuits = {
        'qft': create_qft_circuit,
        'cuccaro': create_cuccaro_adder_circuit,
        'draper': create_draper_adder_circuit,
        'mcmtv': create_mcmtv_circuit
    }
    
    if circuit_name.lower() not in circuits:
        raise ValueError(f"Unknown circuit: {circuit_name}. Available: {list(circuits.keys())}")
    
    qc = circuits[circuit_name.lower()](num_qubits)
    
    # Decompose until we only have basic 1- and 2-qubit gates
    # Qiskit library circuits are often stored as single high-level gates
    # that QASMAnalyzer cannot parse. We need to decompose them.
    prev_ops = None
    for _ in range(10):  # max 10 rounds of decomposition
        ops = set(qc.count_ops().keys())
        if ops == prev_ops:
            break  # no further decomposition possible
        prev_ops = ops
        # Check if all gates are basic (1 or 2 qubit primitives)
        all_basic = True
        for inst in qc.data:
            if inst.operation.num_qubits > 2:
                all_basic = False
                break
            if inst.operation.name in ('swap',):
                all_basic = False
                break
        if all_basic:
            break
        qc = qc.decompose()
    
    return qc


def main():
    """Main function with example configurations"""
    
    # Circuit types to generate
    circuits = ['qft', 'cuccaro', 'draper', 'mcmtv']
    
    # Grid configurations: (rows, cols)
    grid_configs =  [(2, 1), (2, 2), (4, 4), (4, 8), (8, 8)]
    
    # Fixed qubits per core
    qubits_per_core = 8
    
    # Stride modes to generate
    strides = [1, 2]
    
    # Create output directory
    import os
    output_dir = "traffic_files"
    os.makedirs(output_dir, exist_ok=True)
    
    print("\n" + "="*80)
    print("QUANTUM CIRCUIT TRAFFIC GENERATION")
    print("="*80)
    print(f"Circuits: {circuits}")
    print(f"Grid configurations: {grid_configs}")
    print(f"Qubits per core: {qubits_per_core}")
    print(f"Strides: {strides}")
    print(f"Output directory: {output_dir}/")
    print("="*80 + "\n")
    
    for dim_y, dim_x in grid_configs:  # Note: (row, col) maps to (dim_y, dim_x)
        total_qubits = dim_x * dim_y * qubits_per_core
        
        print(f"\n{'#'*80}")
        print(f"GRID CONFIGURATION: {dim_y}x{dim_x} ({dim_y*dim_x} cores, {total_qubits} total qubits)")
        print(f"{'#'*80}")
        
        for circuit_name in circuits:
            for stride in strides:
                # Use all available qubits for all circuits
                num_qubits = total_qubits
                
                try:
                    generate_traffic_for_benchmark(
                        benchmark=circuit_name,
                        num_qubits=num_qubits,
                        dim_x=dim_x,
                        dim_y=dim_y,
                        qubits_per_core=qubits_per_core,
                        stride=stride,
                        output_dir=output_dir
                    )
                    print(f"\n{'='*70}")
                    print(f"✓ Completed successfully! (stride={stride})")
                    print(f"{'='*70}\n")
                except Exception as e:
                    print(f"\n❌ Error processing {circuit_name} (stride={stride}): {e}")
                    import traceback
                    traceback.print_exc()
                    print()
    
    print("\n" + "="*80)
    print("ALL TRAFFIC GENERATION COMPLETED!")
    print("="*80 + "\n")


if __name__ == "__main__":
    main()
