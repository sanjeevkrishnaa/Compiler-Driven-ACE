"""
Script to renumber requests in a layered request JSON file.
Changes the first number in each request from layer number to sequential request number.
Also removes empty layers.
"""

import json
import sys
import os

def fix_request_numbers(input_file, output_file=None):
    """
    Fix request numbers in layered request JSON file and remove empty layers.
    
    Args:
        input_file: Path to input JSON file
        output_file: Path to output JSON file (if None, overwrites input)
    """
    # Load the JSON file
    print(f"Loading {input_file}...")
    with open(input_file, 'r') as f:
        layered_requests = json.load(f)
    
    print(f"Found {len(layered_requests)} layers (including empty)")
    
    # Renumber requests sequentially and filter out empty layers
    request_id = 0
    total_requests = 0
    non_empty_layers = []
    empty_layer_count = 0
    
    for layer_idx, layer in enumerate(layered_requests):
        if not layer:  # Skip empty layers
            print(f"Layer {layer_idx}: Empty layer, skipping...")
            empty_layer_count += 1
            continue
        
        print(f"Layer {layer_idx}: Renumbering {len(layer)} requests (IDs {request_id} to {request_id + len(layer) - 1})")
        
        # Renumber requests in this layer
        for request in layer:
            # Change the first element (layer number) to request_id
            old_id = request[0]
            request[0] = request_id
            request_id += 1
            total_requests += 1
        
        # Add non-empty layer to new list
        non_empty_layers.append(layer)
    
    print(f"\nRemoved {empty_layer_count} empty layers")
    print(f"Remaining layers: {len(non_empty_layers)}")
    print(f"Total requests renumbered: {total_requests}")
    
    # Save the fixed JSON
    if output_file is None:
        output_file = input_file
    
    print(f"Saving to {output_file}...")
    with open(output_file, 'w') as f:
        json.dump(non_empty_layers, f, indent=4)
    
    print(f"Done! Saved {total_requests} requests across {len(non_empty_layers)} non-empty layers")
    return non_empty_layers


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python fix_request_numbers.py <input_file> [output_file]")
        print("\nExample:")
        print("  python fix_request_numbers.py test/qubit_displacement_1.json")
        print("  python fix_request_numbers.py test/qubit_displacement_1.json test/qubit_displacement_1_fixed.json")
        sys.exit(1)
    
    input_file = sys.argv[1]
    output_file = sys.argv[2] if len(sys.argv) > 2 else None
    
    if not os.path.exists(input_file):
        print(f"ERROR: File {input_file} not found!")
        sys.exit(1)
    
    fix_request_numbers(input_file, output_file)
