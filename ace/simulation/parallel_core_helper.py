def generate_layered_requests(num_layers: int, max_requests_per_layer: int, memo_size: int, 
                              fidelity: float, entanglement_number: int, seed: int = 0) -> list:
    """
    Generates layered requests for a 4x4 mesh network.
    Each layer contains requests with disjoint source-destination cores.
    
    Args:
        num_layers: Number of layers to generate
        requests_per_layer: Maximum number of requests per layer (up to 3 for disjoint cores)
        memo_size: Memory size for each request
        fidelity: Fidelity requirement
        entanglement_number: Number of entanglements needed
        seed: Random seed for reproducibility
        
    Return:
        list of layers, where each layer is a list of requests:
        [
            [(id, src, dst, memo_size, fidelity, entanglement_number), ...],  # Layer 0
            [(id, src, dst, memo_size, fidelity, entanglement_number), ...],  # Layer 1
            ...
        ]
    """
    random.seed(seed)
    
    # Define all nodes in 4x4 grid
    all_nodes = [(i, j) for i in range(4) for j in range(4)]
    
    layers = []
    request_id = 0
    
    for layer_idx in range(num_layers):
        layer_requests = []
        used_cores = set()  # Track cores used in this layer
        
        # Try to create up to requests_per_layer requests with disjoint cores
        attempts = 0
        max_attempts = 100  # Prevent infinite loops
        requests_per_layer = random.randint(1, max_requests_per_layer)
        while len(layer_requests) < requests_per_layer and attempts < max_attempts:
            # Randomly select source and destination
            src_coord = random.choice(all_nodes)
            dst_coord = random.choice(all_nodes)
            
            # Ensure source != destination and cores are not already used
            if (src_coord != dst_coord and 
                src_coord not in used_cores and 
                dst_coord not in used_cores):
                
                src_name = f'router_{src_coord[0]}_{src_coord[1]}'
                dst_name = f'router_{dst_coord[0]}_{dst_coord[1]}'
                
                request = (
                    request_id,
                    src_name,
                    dst_name,
                    memo_size,
                    fidelity,
                    entanglement_number
                )
                
                layer_requests.append(request)
                used_cores.add(src_coord)
                used_cores.add(dst_coord)
                request_id += 1
            
            attempts += 1
        
        if layer_requests:
            layers.append(layer_requests)
            # print(f"Layer {layer_idx}: Generated {len(layer_requests)} requests with disjoint cores")
    
    return layers

def generate_layered_requests_sequential(num_layers: int, memo_size: int,
                                          fidelity: float, entanglement_number: int,
                                          seed: int = 0) -> list:
    return generate_layered_requests(num_layers, 1, memo_size, fidelity, entanglement_number, seed)


def generate_structured_layered_requests_sequential(num_layers: int, memo_size: int,
                                                    fidelity: float, entanglement_number: int,
                                                    seed: int = 0) -> list:
    """
    Generates sequential layered requests (1 request per layer).
    Each request goes from a random node in column 0 to a random node in column 3.
    
    Args:
        num_layers: Number of layers to generate
        memo_size: Memory size for each request
        fidelity: Fidelity requirement
        entanglement_number: Number of entanglements needed
        seed: Random seed for reproducibility
        
    Return:
        list of layers, where each layer has exactly 1 request from col0 to col3
    """
    random.seed(seed)
    
    # Column 0 nodes: (0,0), (1,0), (2,0), (3,0)
    # Column 3 nodes: (0,3), (1,3), (2,3), (3,3)
    col0_nodes = [(i, 0) for i in range(4)]
    col3_nodes = [(i, 3) for i in range(4)]
    
    layers = []
    request_id = 0
    
    for layer_idx in range(num_layers):
        # Pick random source from column 0 and destination from column 3
        src_coord = random.choice(col0_nodes)
        dst_coord = random.choice(col3_nodes)
        
        src_name = f'router_{src_coord[0]}_{src_coord[1]}'
        dst_name = f'router_{dst_coord[0]}_{dst_coord[1]}'
        
        request = (
            request_id,
            src_name,
            dst_name,
            memo_size,
            fidelity,
            entanglement_number
        )
        
        layers.append([request])  # Single request per layer
        # print(f"Layer {layer_idx}: {src_name} -> {dst_name}")
        request_id += 1
    
    return layers



def generate_structured_layered_requests(num_layers: int, memo_size: int, 
                                        fidelity: float, entanglement_number: int, 
                                        seed: int = 0) -> list:
    """
    Generates structured layered requests ensuring exactly 3 disjoint request pairs per layer.
    Uses a more deterministic approach to maximize parallelism.
    
    Strategy: Partition the 4x4 grid into regions and create requests between regions.
    """
    random.seed(seed)
    
    # Define specific non-overlapping pairs for maximum parallelism
    # These are manually crafted to ensure disjoint cores
    pair_templates = [
        # Template 1: Corners
        [
            ((0, 0), (3, 3)),  # Top-left to bottom-right
            ((0, 3), (3, 0)),  # Top-right to bottom-left
            ((1, 1), (2, 2)),  # Middle diagonal
        ],
        # Template 2: Edges to opposite edges
        [
            ((0, 1), (3, 2)),
            ((1, 0), (2, 3)),
            ((0, 2), (3, 1)),
        ],
        # Template 3: Cross patterns
        [
            ((0, 0), (2, 3)),
            ((1, 1), (3, 2)),
            ((2, 0), (0, 3)),
        ],
        # Template 4: Different corners
        [
            ((0, 1), (3, 3)),
            ((1, 0), (2, 3)),
            ((3, 0), (0, 2)),
        ],
        # Template 5: Mixed patterns
        [
            ((0, 0), (3, 2)),
            ((0, 3), (2, 1)),
            ((1, 0), (3, 3)),
        ],
        # Template 6: Vertical spreads
        [
            ((0, 0), (3, 1)),
            ((1, 2), (2, 3)),
            ((0, 3), (3, 0)),
        ],
    ]
    
    layers = []
    request_id = 0
    
    for layer_idx in range(num_layers):
        # Select a template (cycle through them)
        template = pair_templates[layer_idx % len(pair_templates)]
        
        # Optionally shuffle pairs within template for variety
        template_copy = template.copy()
        random.shuffle(template_copy)
        
        layer_requests = []
        for src_coord, dst_coord in template_copy:
            src_name = f'router_{src_coord[0]}_{src_coord[1]}'
            dst_name = f'router_{dst_coord[0]}_{dst_coord[1]}'
            
            request = (
                request_id,
                src_name,
                dst_name,
                memo_size,
                fidelity,
                entanglement_number
            )
            
            layer_requests.append(request)
            request_id += 1
        
        layers.append(layer_requests)
        # print(f"Layer {layer_idx}: {len(layer_requests)} requests - "
        #       f"{[(r[1], r[2]) for r in layer_requests]}")
    
    return layers


def generate_hotspot_layered_requests(num_layers: int, max_requests_per_layer: int, memo_size: int, 
                                      fidelity: float, entanglement_number: int, seed: int = 0) -> list:
    """
    Generates layered requests for a 4x4 mesh network using a hotspot traffic pattern (80-20 rule).
    80% of the traffic is directed to one of the multiple hotspot destinations.

    Args:
        num_layers: Number of layers to generate
        max_requests_per_layer: Maximum number of requests per layer
        memo_size: Memory size for each request
        fidelity: Fidelity requirement
        entanglement_number: Number of entanglements needed
        seed: Random seed for reproducibility

    Return:
        list of layers, where each layer is a list of requests:
        [
            [(id, src, dst, memo_size, fidelity, entanglement_number), ...],  # Layer 0
            [(id, src, dst, memo_size, fidelity, entanglement_number), ...],  # Layer 1
            ...
        ]
    """
    random.seed(seed)

    # Define all nodes in 4x4 grid
    all_nodes = [(i, j) for i in range(4) for j in range(4)]
    hotspots = [(2, 2),(1,1)] #,(1,2),(2,1)]  # Define multiple hotspot nodes

    layers = []
    request_id = 0

    for layer_idx in range(num_layers):
        layer_requests = []
        used_cores = set()  # Track cores used in this layer

        # Try to create up to max_requests_per_layer requests
        attempts = 0
        max_attempts = 100  # Prevent infinite loops
        requests_per_layer = random.randint(1, max_requests_per_layer)
        while len(layer_requests) < requests_per_layer and attempts < max_attempts:
            # Randomly select source and destination
            src_coord = random.choice(all_nodes)
            dst_coord = random.choice(hotspots) if random.random() < 0.8 else random.choice(all_nodes)

            # Ensure source != destination and cores are not already used
            if (src_coord != dst_coord
                and src_coord not in used_cores
                and dst_coord not in used_cores
                ):

                src_name = f'router_{src_coord[0]}_{src_coord[1]}'
                dst_name = f'router_{dst_coord[0]}_{dst_coord[1]}'

                request = (
                    request_id,
                    src_name,
                    dst_name,
                    memo_size,
                    fidelity,
                    entanglement_number
                )

                layer_requests.append(request)
                used_cores.add(src_coord)
                used_cores.add(dst_coord)
                request_id += 1

            attempts += 1

        if layer_requests:
            layers.append(layer_requests)
            # print(f"Layer {layer_idx}: Generated {len(layer_requests)} requests with hotspot traffic")

    return layers

def generate_hotspot_layered_requests_sequential(num_layers: int, memo_size: int, 
                                                 fidelity: float, entanglement_number: int, 
                                                 seed: int = 0) -> list:
    """
    Generates sequential layered requests (1 request per layer) using a hotspot traffic pattern (80-20 rule).
    80% of the traffic is directed to one of the multiple hotspot destinations.

    Args:
        num_layers: Number of layers to generate
        memo_size: Memory size for each request
        fidelity: Fidelity requirement
        entanglement_number: Number of entanglements needed
        seed: Random seed for reproducibility

    Return:
        list of layers, where each layer has exactly 1 request:
        [
            [(id, src, dst, memo_size, fidelity, entanglement_number)],  # Layer 0
            [(id, src, dst, memo_size, fidelity, entanglement_number)],  # Layer 1
            ...
        ]
    """
    return generate_hotspot_layered_requests(num_layers, 1, memo_size, fidelity, entanglement_number, seed)
