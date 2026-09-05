"""Request application for parallel layered experiments.

This module extends RequestAppLatency to support completion callbacks
for parallel request management.
"""

from collections import defaultdict
from typing import TYPE_CHECKING, Callable
import sequence.utils.log as log
from sequence.resource_management.memory_manager import MemoryInfo
from request_app import RequestAppLatency

if TYPE_CHECKING:
    from node import QuantumRouterAdaptive
    from reservation import ReservationAdaptive


class RequestAppLatencyParallel(RequestAppLatency):
    """
    Request application for measuring latency in parallel request scenarios.
    
    Supports completion callbacks to enable coordination between parallel requests.
    """
    
    def __init__(self, node: "QuantumRouterAdaptive"):
        super().__init__(node)
        self.entanglement_timestamps = defaultdict(list)
        self.latency = defaultdict(float)
        self.entanglement_fidelities = defaultdict(list)
        self.completion_callbacks = {}  # Maps request_id to callback function
        self.reservation_approval_callbacks = {}  # Maps request_id to callback for reservation approval
    
    def start(self, responder: str, start_t: int, end_t: int, memo_size: int, 
             fidelity: float, entanglement_number: int = 1, id: int = 0):
        """
        Start the application by creating a network reservation request.
        
        Args:
            responder: Name of the responder node
            start_t: Start time for the reservation
            end_t: End time for the reservation
            memo_size: Number of memory qubits needed
            fidelity: Required fidelity threshold
            entanglement_number: Number of entanglements to generate
            id: Unique identifier for this request
        """
        assert 0 < fidelity <= 1
        assert 0 <= start_t <= end_t
        assert 0 < memo_size
        
        self.responder = responder
        self.start_t = start_t
        self.end_t = end_t
        self.memo_size = memo_size
        self.fidelity = fidelity
        self.entanglement_number = entanglement_number
        self.id = id
        
        self.node.reserve_net_resource(responder, start_t, end_t, memo_size, 
                                      fidelity, entanglement_number, id)
    
    def set_completion_callback(self, callback_func: Callable, request_id: int):
        """
        Register a callback function to be invoked when this request completes.
        
        Args:
            callback_func: Function to call with (request_id, completion_time)
            request_id: ID of the request to track
        """
        self.completion_callbacks[request_id] = callback_func
        log.logger.debug(f"{self.node.name}: Registered completion callback for request {request_id}")
    
    def set_reservation_approval_callback(self, callback_func: Callable, request_id: int):
        """
        Register a callback function to be invoked when reservation is approved.
        
        Args:
            callback_func: Function to call with (request_id, approval_time)
            request_id: ID of the request to track
        """
        self.reservation_approval_callbacks[request_id] = callback_func
        log.logger.debug(f"{self.node.name}: Registered reservation approval callback for request {request_id}")
    
    def get_memory(self, info: "MemoryInfo") -> None:
        """
        Receive and process entangled memories.
        
        Checks if memory meets fidelity requirements and tracks completion.
        Calls completion callback when all requested entanglements are achieved.
        
        Args:
            info: Information about the entangled memory
        """
        if info.state != "ENTANGLED":
            return
        
        if info.index in self.memo_to_reservation:
            reservation = self.memo_to_reservation[info.index]
            
            # RESPONDER SIDE: receives entanglement from initiator
            if info.remote_node == reservation.initiator:
                if info.fidelity >= reservation.fidelity:
                    self.entanglement_timestamps[reservation].append(self.node.timeline.now())
                    self.entanglement_fidelities[reservation].append(info.fidelity)
                    self.node.resource_manager.update(None, info.memory, MemoryInfo.RAW)
                    self.cache_entangled_path(reservation.path)
                    
                    entanglement_number = len(self.entanglement_timestamps[reservation])
                    log.logger.debug(f"{self.node.name} (responder): Request {reservation.identity} "
                                   f"entanglement {entanglement_number}/{reservation.entanglement_number}")
                    
                    if entanglement_number == reservation.entanglement_number:
                        self.node.resource_manager.expire_rules_by_reservation(reservation)
                        log.logger.info(f"{self.node.name} (responder): Request {reservation.identity} completed")
                else:
                    log.logger.info(f'{self.node.name}: Memory fidelity {info.fidelity:.6f} '
                                  f'below threshold {reservation.fidelity}')
            
            # INITIATOR SIDE: receives entanglement from responder
            elif info.remote_node == reservation.responder:
                if info.fidelity >= reservation.fidelity:
                    self.entanglement_timestamps[reservation].append(self.node.timeline.now())
                    self.entanglement_fidelities[reservation].append(info.fidelity)
                    entanglement_number = len(self.entanglement_timestamps[reservation])
                    
                    log.logger.info(f"{self.node.name} (initiator): Request {reservation.identity} "
                                  f"entanglement {entanglement_number}/{reservation.entanglement_number}, "
                                  f"fidelity={info.fidelity:.6f}")
                    
                    self.node.resource_manager.update(None, info.memory, MemoryInfo.RAW)
                    self.cache_entangled_path(reservation.path)
                    self.send_entangled_path(reservation)
                    
                    # Check if all entanglements for this request are complete
                    if entanglement_number == reservation.entanglement_number:
                        completion_time = self.node.timeline.now()
                        self.latency[reservation] = completion_time - reservation.start_time
                        self.node.resource_manager.expire_rules_by_reservation(reservation)
                        self.send_expire_rules_message(reservation)
                        
                        log.logger.info(f"{self.node.name} (initiator): Request {reservation.identity} "
                                      f"COMPLETED at {completion_time}")
                        
                        # Invoke completion callback if registered
                        request_id = reservation.identity
                        if request_id in self.completion_callbacks:
                            log.logger.debug(f"{self.node.name}: Calling completion callback for "
                                           f"request {request_id}")
                            callback_func = self.completion_callbacks[request_id]
                            callback_func(request_id, completion_time)
                            # Clean up callback
                            del self.completion_callbacks[request_id]
                        else:
                            log.logger.warning(f"{self.node.name}: No callback registered for "
                                             f"request {request_id}")
                else:
                    log.logger.info(f'{self.node.name}: Memory fidelity {info.fidelity:.6f} '
                                  f'below threshold {reservation.fidelity}')
    
    def remove_memo_reservation_map(self, index: int) -> None:
        """
        Override to safely remove memo from reservation map.
        Defensive version that checks if key exists before removing.
        
        This handles the case where parallel requests might be trying to
        remove the same memo indices simultaneously.
        
        Args:
            index: The memory index to remove
        """
        # Safely remove only if the key exists
        if index in self.memo_to_reservation:
            self.memo_to_reservation.pop(index)
            log.logger.debug(f"{self.node.name}: Removed memo index {index} from reservation map")
        else:
            # Already removed or never existed - this is OK in parallel scenarios
            log.logger.debug(f"{self.node.name}: Memo index {index} not in reservation map "
                           f"(may have been removed by another request)")
    
    def get_reservation_result(self, reservation: "ReservationAdaptive", result: bool) -> None:
        """
        Override to track reservation approval time.
        This is called when the reservation is approved/rejected.
        
        Args:
            reservation: The reservation that has been processed
            result: Whether the reservation was approved
        """
        # Call parent implementation
        super().get_reservation_result(reservation, result)
        
        # If approved, notify callback with approval time
        if result:
            approval_time = self.node.timeline.now()
            request_id = reservation.identity
            
            log.logger.info(f"{self.node.name}: Reservation {request_id} APPROVED at {approval_time}")
            
            # Invoke reservation approval callback if registered
            if request_id in self.reservation_approval_callbacks:
                log.logger.debug(f"{self.node.name}: Calling reservation approval callback for "
                               f"request {request_id}")
                callback_func = self.reservation_approval_callbacks[request_id]
                callback_func(request_id, approval_time)
                # Clean up callback
                del self.reservation_approval_callbacks[request_id]
            else:
                log.logger.warning(f"{self.node.name}: No reservation approval callback registered for "
                                 f"request {request_id}")
