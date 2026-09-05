from request_app import *

class RequestAppLatencyDynamic(RequestAppLatency):
    '''for the time-to-serve (latency) metric

    The RequestApp can only handle one request (for a node) at a time, it cannot handle multiple requests at the same time.
    It can handle multiple requests one by one (no timing overlap between consequtive requests)
    '''

    def __init__(self, node: "QuantumRouterAdaptive"):
        super().__init__(node)
        self.entanglement_timestamps = defaultdict(list)  # reservation: list[float]
        self.latency = defaultdict(float)           # reservation: float
        self.entanglement_fidelities = defaultdict(list)  # reservation: list[float]
        self.completion_callbacks = {}  # Maps request_id to (callback_func, callback_args)
    
    def start(self, responder: str, start_t: int, end_t: int, memo_size: int, fidelity: float, entanglement_number: int = 1, id: int = 0):
        """Method to start the application.

            This method will use arguments to create a request and send to the network.

        Side Effects:
            Will create request for network manager on node.
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

        self.node.reserve_net_resource(responder, start_t, end_t, memo_size, fidelity, entanglement_number, id)

    def set_completion_callback(self, callback_func, request_id: int):
        """
        Register a callback function to be called when this request completes.
        
        Args:
            callback_func: Function to call with (request_id, completion_time) when request completes
            request_id: ID of the request to track
        """
        self.completion_callbacks[request_id] = callback_func

    def get_memory(self, info: "MemoryInfo") -> None:
        """Method to receive entangled memories.

        Will check if the received memory is qualified.
        If it's a qualified memory, the application sets memory to RAW state
        and release back to resource manager.
        The counter of entanglement memories, 'memory_counter', is added.
        Otherwise, the application does not modify the state of memory and
        release back to the resource manager.

        Args:
            info (MemoryInfo): info on the qualified entangled memory.
        """

        if info.state != "ENTANGLED":
            return

        if info.index in self.memo_to_reservation:
            reservation = self.memo_to_reservation[info.index]
            if info.remote_node == reservation.initiator:
                if info.fidelity >= reservation.fidelity:   # the responder
                    self.entanglement_timestamps[reservation].append(self.node.timeline.now())
                    self.entanglement_fidelities[reservation].append(info.fidelity)
                    self.node.resource_manager.update(None, info.memory, MemoryInfo.RAW)
                    self.cache_entangled_path(reservation.path)
                    
                    entanglement_number = len(self.entanglement_timestamps[reservation])
                    if entanglement_number == reservation.entanglement_number:
                        # self.latency[reservation] = self.node.timeline.now() - reservation.start_time
                        # self.node.resource_manager.expire_rules_by_reservation(reservation)
                        log.logger.info(f"Responder {self.node.name}: Request {reservation.identity} completed")
                        self.node.resource_manager.expire_rules_by_reservation(reservation)
                        
                        
                else:
                    log.logger.info(f'Memory={info}, does not meet the fidelity threshold, {reservation}')

            elif info.remote_node == reservation.responder:
                if info.fidelity >= reservation.fidelity: # the initiator
                    self.entanglement_timestamps[reservation].append(self.node.timeline.now())
                    self.entanglement_fidelities[reservation].append(info.fidelity)
                    entanglement_number = len(self.entanglement_timestamps[reservation])

                    log.logger.info(f"Successfully generated entanglement. {reservation}: {entanglement_number}, {info.fidelity:.6f}")
                    self.node.resource_manager.update(None, info.memory, MemoryInfo.RAW)
                    self.cache_entangled_path(reservation.path)
                    self.send_entangled_path(reservation)

                    if entanglement_number == reservation.entanglement_number:
                        # self.latency[reservation] = self.node.timeline.now() - reservation.start_time
                        completion_time = self.node.timeline.now()
                        self.latency[reservation] = completion_time - reservation.start_time
                        self.node.resource_manager.expire_rules_by_reservation(reservation)
                        self.send_expire_rules_message(reservation)

                        
                        # Call completion callback if registered
                        request_id = reservation.identity
                        print(f"Initiator {self.node.name}: Request {request_id} completed at {completion_time} ")

                        if request_id in self.completion_callbacks:
                            callback_func = self.completion_callbacks[request_id]
                            callback_func(request_id, completion_time)
                            # Clean up the callback
                            del self.completion_callbacks[request_id]
                        else:
                            print(f"No callback registered for {request_id}")
                else:
                    log.logger.info(f'Memory={info} has not meet the threshold, {reservation}')
