# Adaptive Continuous Protocol (ACP) - Detailed Explanation

## Overview
The Adaptive Continuous Protocol (ACP) pregenerates entangled qubit pairs between neighboring nodes to reduce latency when requests arrive. It works in tandem with routing and reservation systems.

---

## 1. HOW IS IT DECIDED THAT IT'S TIME FOR A NEW PREGENERATION AND WHICH NEIGHBOR TO CHOOSE?

### A. When Pregeneration Happens (PERIODIC)

**Location**: `adaptive_continuous.py`, lines 139-143

```python
def update_probability_table_event(self, elapse):
    self.update_probability_table(elapse)
    process = Process(self.owner.adaptive_continuous, "update_probability_table_event", [elapse])
    event = Event(self.owner.timeline.now() + elapse, process)
    self.owner.timeline.schedule(event)
```

**The `start()` method** (lines 145-175) is called periodically:
- Initial trigger: `node.py` line 88 calls `adaptive_continuous.start_delay(delay=0)`
- After each generation attempt, it schedules another `start()` event with delays:
  - `delay_no_memory` = period // 1000 (when node is out of memory)
  - `delay_select_neighbor_none` = period // 100 (when no neighbor selected)
  - `delay_remote_response` = 3 * delay_no_memory (after receiving response)

**Key Parameter**: `period` (default = 2e11 ps = 0.2 seconds in node.py line 56)
- Set in: `QuantumRouterAdaptive.__init__()` → `period=2e11`
- This controls the reservation duration for each pregenerated pair

### B. Which Neighbor to Choose (PROBABILITY-BASED)

**Location**: `adaptive_continuous.py`, lines 209-222

```python
def select_neighbor(self) -> str:
    '''return the name of the selected neighbor
       The selection algorithm is roulette wheel
    '''
    neighbors = []
    probs = []
    for neighbor, prob in sorted(self.probability_table.items()):
        neighbors.append(neighbor)
        probs.append(prob)
    probs_accumulate = list(accumulate(probs))
    random_number = self.owner.get_generator().random()
    index = bisect_left(probs_accumulate, random_number)
    neighbor = neighbors[index]
    return neighbor
```

**The Probability Table**:
1. **Initialization** (lines 190-206): Equal probability for all neighbors + empty string ('')
2. **Adaptive Updates** (lines 327-383): Called every `period` seconds
   - Analyzes recent request paths from `cache` (stores entanglement paths used)
   - Increases probability (`delta = 0.05`) for neighbors that appear in recent paths
   - If no neighbor used recently, increases probability of '' (do nothing)
   - Normalizes probabilities to sum to 1

**The Cache System** (lines 224-240):
- Stores tuples: `(timestamp, path)` where path is list of nodes
- Updated when requests are served
- Used to identify which neighbors are frequently needed

---

## 2. HOW CAN I MODIFY THE RATE AT WHICH A NEIGHBOR CHOOSES TO PRE-ENTANGLE?

There are **three main parameters** you can modify:

### A. **Modify the Period** (Time between attempts)

**Location**: `node.py` line 56

```python
self.adaptive_continuous = AdaptiveContinuousProtocol(
    self, adaptive_name, adaptive_max_memory, 
    resource_reservation, period=2e11  # <-- CHANGE THIS
)
```

- **Current value**: `2e11` ps = 0.2 seconds
- **Shorter period** → More frequent attempts → More pregeneration
- **Longer period** → Less frequent attempts → Less pregeneration

### B. **Modify the Retry Delays** (After failed attempts)

**Location**: `adaptive_continuous.py` lines 129-132

```python
def update_period(self, period: int) -> None:
    self.period = period
    self.delay_no_memory            = period // 1000  # <-- CHANGE THIS
    self.delay_select_neighbor_none = period // 100   # <-- CHANGE THIS
    self.delay_remote_response      = 3 * self.delay_no_memory  # <-- CHANGE THIS
```

**Current behavior**:
- `delay_no_memory`: Wait period/1000 when out of memory
- `delay_select_neighbor_none`: Wait period/100 when '' is selected
- `delay_remote_response`: Wait 3×(period/1000) after receiving response

**To increase rate**: Reduce these divisors (e.g., `period // 2000` instead of `// 1000`)

### C. **Modify adaptive_max_memory** (Number of concurrent pregenerations)

**Location**: Config file (e.g., `config/grid_4x4_ace_4.json`)

```json
{
  "component_templates": {
    "adaptive_max_memory": 5  // <-- CHANGE THIS
  }
}
```

- **Higher value** → More concurrent pregeneration attempts
- **Lower value** → Fewer concurrent attempts

---

## 3. HOW TO REMOVE PROBABILITY TABLE DEPENDENCY AND ADD COST-BASED LOGIC

### Modifications Needed:

#### Step 1: Add Cost-Aware Selection Method

**Location**: Add to `adaptive_continuous.py` after line 222

```python
def select_neighbor_cost_aware(self, cost_threshold: float) -> str:
    '''Select neighbor based on cost-benefit analysis instead of probability
    
    Args:
        cost_threshold: minimum benefit/cost ratio to justify pregeneration
    
    Returns:
        neighbor name or '' if cost too high
    '''
    # Calculate benefit for each neighbor
    neighbor_benefits = {}
    current_time = self.owner.timeline.now()
    
    for neighbor in self.probability_table.keys():
        if neighbor == '':
            continue
            
        # Calculate benefit based on recent usage
        benefit = 0
        for timestamp, path in self.cache:
            if current_time - timestamp <= self.period:
                if neighbor in path:
                    benefit += 1
        
        # Calculate cost (could be based on channel quality, distance, etc.)
        channel_delay = self.owner.cchannels[neighbor].delay
        cost = channel_delay / 1e12  # Normalize to seconds
        
        # Calculate benefit/cost ratio
        if cost > 0:
            neighbor_benefits[neighbor] = benefit / cost
        else:
            neighbor_benefits[neighbor] = 0
    
    # Select neighbor with best benefit/cost ratio
    if not neighbor_benefits:
        return ''
    
    best_neighbor = max(neighbor_benefits, key=neighbor_benefits.get)
    best_ratio = neighbor_benefits[best_neighbor]
    
    # Only pregenerate if benefit/cost exceeds threshold
    if best_ratio < cost_threshold:
        return ''  # Too expensive, don't pregenerate
    
    return best_neighbor
```

#### Step 2: Add Demand-Based Triggering (Non-Periodic)

**Location**: Replace periodic scheduling in `adaptive_continuous.py` lines 139-143

```python
def update_probability_table_event(self, elapse):
    # Don't schedule next event automatically
    self.update_probability_table(elapse)
    # Remove automatic scheduling:
    # process = Process(self.owner.adaptive_continuous, "update_probability_table_event", [elapse])
    # event = Event(self.owner.timeline.now() + elapse, process)
    # self.owner.timeline.schedule(event)
```

**Add demand-triggered method**:

```python
def trigger_on_demand(self, path: list) -> None:
    '''Trigger pregeneration when a request arrives
    
    Args:
        path: the routing path that was just used
    '''
    # Add to cache
    timestamp = self.owner.timeline.now()
    self.cache.append((timestamp, path))
    
    # Decide whether to pregenerate
    cost_threshold = 0.5  # Configurable threshold
    neighbor = self.select_neighbor_cost_aware(cost_threshold)
    
    if neighbor != '' and self.adaptive_memory_used < self.adaptive_max_memory:
        # Trigger pregeneration
        self.start()
```

#### Step 3: Modify start() to use cost-based selection

**Location**: Replace line 155 in `adaptive_continuous.py`

```python
def start(self) -> None:
    '''start a new "cycle" of the adaptive-continuous protocol
    '''
    # check whether the adaptive protocol has used up its memory quota
    if self.adaptive_memory_used >= self.adaptive_max_memory:
        self.start_delay(delay = self.delay_no_memory)
        return

    # REPLACE THIS LINE:
    # neighbor = self.select_neighbor()
    
    # WITH COST-BASED SELECTION:
    cost_threshold = 0.5  # Make this configurable
    neighbor = self.select_neighbor_cost_aware(cost_threshold)
    
    if neighbor == '':
        log.logger.debug(f'{self.owner.name} selected neighbor None (cost too high)')
        # Don't schedule another start - wait for demand trigger
        return
    
    # ... rest of the method continues as before
```

#### Step 4: Trigger on request arrival

**Location**: `request_app.py` or `request_app_parallel.py`, after path is computed

Add call to trigger pregeneration:

```python
# After a request is served successfully
path = reservation.path
for node_name in path:
    node = self.owner.timeline.get_entity_by_name(node_name)
    if hasattr(node, 'adaptive_continuous'):
        node.adaptive_continuous.trigger_on_demand(path)
```

---

## Summary of Code Locations

| Aspect | File | Lines |
|--------|------|-------|
| Period setting | `node.py` | 56 |
| Start trigger | `adaptive_continuous.py` | 145-175 |
| Neighbor selection | `adaptive_continuous.py` | 209-222 |
| Probability table init | `adaptive_continuous.py` | 190-206 |
| Probability update | `adaptive_continuous.py` | 327-383 |
| Delay parameters | `adaptive_continuous.py` | 129-132 |
| Periodic scheduling | `adaptive_continuous.py` | 139-143 |
| Max memory config | Config JSON files | `adaptive_max_memory` |
| Pregenerated pair matching | `generation.py` | 209-219 |
| Pair usage | `generation.py` | 220-232 |

---

## Key Insights

1. **Current Design**: Periodic + Probability-based
2. **Rate Control**: Adjust `period`, `delays`, and `adaptive_max_memory`
3. **Cost-Aware Design**: Replace probability table with cost-benefit analysis
4. **On-Demand Design**: Trigger on request arrival instead of periodic scheduling
5. **Flexible Threshold**: Use configurable cost threshold to decide when pregeneration is worthwhile
