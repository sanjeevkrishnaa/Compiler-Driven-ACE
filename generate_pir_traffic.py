"""
Generate random and hotspot traffic patterns on a 4x4 mesh network
with Packet Injection Rate (PIR) based start times.

PIR = packets injected per core per millisecond.
  - Each time window is exactly 1 ms.
  - Total time is e.g. 50 ms → 50 windows (0–1 ms, 1–2 ms, …, 49–50 ms).
  - In EACH window, EVERY node generates  int(10 * pir)  requests.
      PIR=0.1 → 1 request/node/window
      PIR=0.2 → 2 requests/node/window
      PIR=0.5 → 5 requests/node/window
  - Start times are drawn uniformly at random within the window.
  - Destinations are sampled per the chosen pattern (random / hotspot).
  - All requests are combined, sorted by start time, and dumped to JSON.

end_time is set very large (100 s); the simulation stops on first success.
"""

import json
import os
import random
from typing import List, Optional
import shutil

SECOND = int(1e12)       # 1 second in picoseconds
MILLISECOND = int(1e9)   # 1 millisecond in picoseconds


def get_4x4_nodes() -> list:
    """Return all 16 node coordinates for a 4x4 mesh."""
    return [(i, j) for i in range(4) for j in range(4)]


def node_name(coord: tuple) -> str:
    """Convert (row, col) coordinate to router name."""
    return f"router_{coord[0]}_{coord[1]}"


def generate_random_traffic(pir: float, total_time_ms: float,
                            window_ms: float = 1.0,
                            memo_size: int = 1, fidelity: float = 0.01,
                            entanglement_number: int = 1,
                            seed: int = 42) -> list:
    """
    Generate random src→dst traffic on a 4x4 mesh.

    Each window of `window_ms` ms, every node injects int(10*pir) requests.
    Start times are uniform-random inside the window.
    Destination is uniform-random among the other 15 nodes.
    end_time is 100 s (very large) so the sim stops on first success.

    Args:
        pir: packet injection rate (packets per core per ms)
        total_time_ms: total simulation traffic time in ms
        window_ms: width of each injection window in ms (default 1.0)

    Returns:
        Sorted list of request tuples:
        (id, src_name, dst_name, start_time_ps, end_time_ps,
         memo_size, fidelity, entanglement_number)
    """
    rng = random.Random(seed)
    nodes = get_4x4_nodes()

    num_windows = int(total_time_ms / window_ms)
    reqs_per_node = int(10 * pir)             # requests per node per window
    end_time_ps = 100 * SECOND                # very large

    requests = []
    for w in range(num_windows):
        window_start_ms = w * window_ms
        window_end_ms = (w + 1) * window_ms
        for node in nodes:
            for _ in range(reqs_per_node):
                # random start time inside [window_start, window_end) ms
                start_ms = rng.uniform(window_start_ms, window_end_ms)
                start_ps = int(round(start_ms * MILLISECOND))

                # random destination (not self)
                dst = node
                while dst == node:
                    dst = rng.choice(nodes)

                requests.append((node_name(node), node_name(dst), start_ps))

    # sort by start time, assign sequential IDs
    # add 6 ms offset to every start time for reservation setup headroom
    offset_ps = int(6 * MILLISECOND)
    requests.sort(key=lambda r: r[2])
    request_list = []
    for idx, (src, dst, st) in enumerate(requests):
        request_list.append((
            idx, src, dst, st + offset_ps, end_time_ps,
            memo_size, fidelity, entanglement_number,
        ))
    return request_list


def generate_hotspot_traffic(pir: float, total_time_ms: float,
                             window_ms: float = 1.0,
                             hotspot_nodes: Optional[List[tuple]] = None,
                             hotspot_probability: float = 0.8,
                             memo_size: int = 1, fidelity: float = 0.01,
                             entanglement_number: int = 1,
                             seed: int = 42) -> list:
    """
    Generate hotspot-destination traffic on a 4x4 mesh.

    Same injection model as generate_random_traffic, but with probability
    `hotspot_probability` the destination is one of the hotspot nodes.

    Args:
        hotspot_nodes: list of (row, col) hotspot coordinates.
                       Defaults to [(1,1), (2,2)].
        hotspot_probability: chance of picking a hotspot as destination.

    Returns:
        Sorted list of request tuples (same format).
    """
    rng = random.Random(seed)
    nodes = get_4x4_nodes()
    if hotspot_nodes is None:
        hotspot_nodes = [(1, 1), (2, 2)]
    non_hotspot_nodes = [n for n in nodes if n not in hotspot_nodes]

    num_windows = int(total_time_ms / window_ms)
    reqs_per_node = int(10 * pir)
    end_time_ps = 100 * SECOND

    requests = []
    for w in range(num_windows):
        window_start_ms = w * window_ms
        window_end_ms = (w + 1) * window_ms
        for node in nodes:
            for _ in range(reqs_per_node):
                start_ms = rng.uniform(window_start_ms, window_end_ms)
                start_ps = int(round(start_ms * MILLISECOND))

                if rng.random() < hotspot_probability:
                    candidates = [h for h in hotspot_nodes if h != node]
                    if not candidates:
                        candidates = [n for n in nodes if n != node]
                else:
                    candidates = [n for n in non_hotspot_nodes if n != node]
                    if not candidates:
                        candidates = [n for n in nodes if n != node]
                dst = rng.choice(candidates)

                requests.append((node_name(node), node_name(dst), start_ps))

    # sort by start time, assign sequential IDs
    # add 6 ms offset to every start time for reservation setup headroom
    offset_ps = int(6 * MILLISECOND)
    requests.sort(key=lambda r: r[2])
    request_list = []
    for idx, (src, dst, st) in enumerate(requests):
        request_list.append((
            idx, src, dst, st + offset_ps, end_time_ps,
            memo_size, fidelity, entanglement_number,
        ))
    return request_list


def save_traffic(request_list: list, filepath: str) -> None:
    """Save request list to a JSON file."""
    os.makedirs(os.path.dirname(filepath) or ".", exist_ok=True)
    with open(filepath, "w") as f:
        json.dump(request_list, f, indent=2)
    print(f"Saved {len(request_list)} requests to {filepath}")


def load_traffic(filepath: str) -> list:
    """Load request list from a JSON file."""
    with open(filepath, "r") as f:
        data = json.load(f)
    return [tuple(r) for r in data]


# ---------------------------------------------------------------------------
# CLI: generate and save traffic files
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    #remove the already existing traffic files to avoid confusion
    shutil.rmtree("test/pir_traffic", ignore_errors=True)
    os.makedirs("test/pir_traffic", exist_ok=True)

    pir_values = [0.1, 0.2, 0.5]
    total_time_ms = 500.0   # 500 ms of simulation traffic
    window_ms = 10.0        # 10 ms window for traffic generation
    seed = 42

    for pir in pir_values:
        # Random traffic
        random_traffic = generate_random_traffic(
            pir=pir, total_time_ms=total_time_ms, window_ms=window_ms, seed=seed
        )
        save_traffic(random_traffic,
                     f"test/pir_traffic/random_pir_{pir}_t{int(total_time_ms)}ms.json")

        # Hotspot traffic
        hotspot_traffic = generate_hotspot_traffic(
            pir=pir, total_time_ms=total_time_ms, window_ms=window_ms, seed=seed,
            hotspot_nodes=[(1, 1), (2, 2)], hotspot_probability=0.8
        )
        save_traffic(hotspot_traffic,
                     f"test/pir_traffic/hotspot_pir_{pir}_t{int(total_time_ms)}ms.json")

    print("\nAll traffic files generated successfully.")
