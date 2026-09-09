''' the quantum router for adaptive-continuous protocol
'''

import numpy as np
from typing import List
from sequence.topology.node import QuantumRouter, BSMNode
from sequence.network_management.routing import StaticRoutingProtocol
from sequence.kernel.timeline import Timeline
from sequence.network_management.network_manager import NetworkManager
from sequence.utils import log
from sequence.message import Message
from math import inf
from resource_manager import ResourceManagerAdaptive
from reservation import ResourceReservationProtocolAdaptive
from adaptive_continuous import AdaptiveContinuousProtocol
from generation import EntanglementGenerationBadaptive, GenerationMsgType, ShEntanglementGenerationBadaptive

def xyrouting(current: str ,dst: str)->str:
    # Parse source and destination coordinates
    try:
        src_row, src_col = map(int, current.split("_")[1:])
        dst_row, dst_col = map(int, dst.split("_")[1:])
    except Exception as e:
        raise ValueError(f"Invalid node name format: {current} or {dst}") from e

    # Determine next hop using XY routing
    next_node = None
    if src_col != dst_col:
        # Route along row: change column towards dst_col
        step = 1 if dst_col > src_col else -1
        next_col = src_col + step
        next_node = f"router_{src_row}_{next_col}"
    elif src_row != dst_row:
        # Route along column: change row towards dst_row
        step = 1 if dst_row > src_row else -1
        next_row = src_row + step
        next_node = f"router_{next_row}_{src_col}"
    else:
        raise ValueError("Source and destination are the same; no routing needed.")
    return next_node


class QuantumRouterAdaptive(QuantumRouter):
    '''The quantum router customized for the adaptive continuous protocol
    Newly added attributes:
        1) adaptive_continuous (AdaptiveContinuousProtocol)
        2) active (bool): if True, then this node will actively select neighbor; if False, then this node will only respond to neighbor nodes
    '''
    def __init__(self, name: str, tl: Timeline, memo_size: int = 50, seed: int = None, component_templates: dict = None, gate_fidelity: float = 1, measurement_fidelity: float = 1):
        super().__init__(name, tl, memo_size, seed, component_templates, gate_fidelity, measurement_fidelity)
        adaptive_name = f'{self.name}.adaptive_continuous'
        adaptive_max_memory = component_templates['adaptive_max_memory']
        resource_reservation = self.network_manager.protocol_stack[-1]  # reference to the network manager's resource reservation protocol
        self.adaptive_continuous = AdaptiveContinuousProtocol(self, adaptive_name, adaptive_max_memory, resource_reservation, period=2e11) # 0.2 s
        self.active = True
        self.seed = seed
        # print(f"QRA {self.name} created with seed {self.seed}")

    def init_managers(self, memo_arr_name: str):
        '''override QuantumRouter.init_manager()
           init the resource mansger and network manager
        Args:
            memo_arr_name: the name of the memory array
        '''
        # setup resource manager
        resource_manager = ResourceManagerAdaptive(self, memo_arr_name)
        self.set_resource_manager(resource_manager)

        # setup network manager
        swapping_success_rate = 1
        network_manager = NetworkManager(self, [])
        routing_protocol = StaticRoutingProtocol(self, f'{self.name}.StaticRoutingProtocol', {})
        rsvp_protocol = ResourceReservationProtocolAdaptive(self, f'{self.name}.RSVP', memo_arr_name)
        rsvp_protocol.set_swapping_success_rate(swapping_success_rate)
        routing_protocol.upper_protocols.append(rsvp_protocol)
        rsvp_protocol.lower_protocols.append(routing_protocol)
        network_manager.load_stack([routing_protocol, rsvp_protocol])
        self.set_network_manager(network_manager)

    def init(self):
        '''start the Adaptive-continuous protocol
        '''
        if self.active:
            self.adaptive_continuous.init()
            self.adaptive_continuous.start_delay(delay=0)

    def send_message(self, dst: str, msg: "Message", priority=inf) -> None:
        """Route a classical message across the sparse ACE mesh.

        Upstream SeQUeNCe 0.8.1 assumes a direct classical channel to ``dst``.
        ACE topologies only contain neighbor channels, so retain the final
        destination on the message and forward one XY hop at a time.  Message
        subclasses have an instance dictionary even though the base fields use
        slots, which keeps this compatibility behavior local to ACE.
        """
        msg.src = self.name
        msg.dst = dst
        if priority == inf:
            priority = self.timeline.schedule_counter
        next_hop = dst if dst in self.cchannels else xyrouting(self.name, dst)
        if next_hop not in self.cchannels:
            raise ValueError(
                f"No classical channel to {dst} or next hop {next_hop} from {self.name}"
            )
        self.cchannels[next_hop].transmit(msg, self, priority)

    def receive_message(self, src: str, msg: "Message") -> None:
        """Determine what to do when a message is received, based on the msg.receiver
        Args:
            src (str): name of node that sends the message
            msg (Message): the message
        """
        log.logger.info("{} receive message {} from {}".format(self.name, msg, src))

        log.logger.info("{} receive message {} from {}".format(self.name, msg, src))
        # signal to protocol that we've received a message

        destination = getattr(msg, "dst", self.name)
        if self.name != destination:
            # need to forward message
            if destination in self.cchannels: # handle directly connected nodes (needed for bsm nodes)
                self.cchannels[destination].transmit(msg, self, inf)
            else:
                next_node_on_path = xyrouting(self.name, destination)
                if next_node_on_path in self.cchannels:
                    self.cchannels[next_node_on_path].transmit(msg, self, inf)
                else:
                    raise ValueError(
                        f"No classical channel to {destination} or next hop "
                        f"{next_node_on_path} from {self.name}"
                    )
        else:
            if msg.receiver == "network_manager":
                self.network_manager.received_message(src, msg)
            elif msg.receiver == "resource_manager":
                self.resource_manager.received_message(src, msg)
            elif msg.receiver == "adaptive_continuous":
                self.adaptive_continuous.received_message(src, msg)
            else:
                if msg.receiver is None:  # the msg sent by EntanglementGenerationB doesn't have a receiver (A-B not paired)
                    matching = [p for p in self.protocols if type(p) == msg.protocol_type]
                    for p in matching:
                        p.received_message(src, msg)
                else:
                    for protocol in self.protocols:
                        if protocol.name == msg.receiver:
                            protocol.received_message(src, msg)
                            break
                    else: # for the special case of reducing latancy during handshaking and memory re-assignment
                        if msg.msg_type is GenerationMsgType.INFORM_EP:
                            for protocol in self.resource_manager.pending_protocols:  # the EG protocol is still pending (not finished pairing yet)
                                if protocol.name == msg.receiver:
                                    protocol.received_message(src, msg)
                                    break

    def set_seed(self, seed: int) -> None:
        """Set the seed, also set the generator
        
        Args:
            seed (int): the random seed
        """
        self.seed = seed
        self.generator = np.random.default_rng(seed)
    
    def get_seed(self) -> int:
        """Get the seed"""
        return self.seed


class BSMNodeAdaptive(BSMNode):
    """Bell state measurement node.

    This node provides bell state measurement and the EntanglementGenerationB protocol for entanglement generation.
    Creates a SingleAtomBSM object within local components.

    Attributes:
        name (str): label for node instance.
        timeline (Timeline): timeline for simulation.
        eg (EntanglementGenerationB): entanglement generation protocol instance.
    """
    def __init__(self, name: str, timeline: "Timeline", other_nodes: List[str],
                 seed=None, component_templates=None) -> None:
        """Constructor for BSM node.

        Args:
            name (str): name of node.
            timeline (Timeline): simulation timeline.
            other_nodes (List[str]): 2-member list of node names for adjacent quantum routers.
        """
        super().__init__(name, timeline, other_nodes, seed, component_templates)
        if not component_templates:
            component_templates = {}

        # update BSM object's entanglement generation protocol
        bsm_name = name + ".BSM"
        bsm = self.components[bsm_name]
        bsm.detach(self.eg)
        if self.encoding_type == 'single_atom':
            self.eg = EntanglementGenerationBadaptive(self, "{}_eg".format(name), other_nodes)
        elif self.encoding_type == 'single_heralded':
            self.eg = ShEntanglementGenerationBadaptive(self, "{}_eg".format(name), other_nodes)
        else:
            raise ValueError(f'encoding type {self.encoding_type} not supported')
        bsm.attach(self.eg)

    def set_seed(self, seed: int) -> None:
        """Set the seed, also set the generator
        
        Args:
            seed (int): the random seed
        """
        self.seed = seed
        self.generator = np.random.default_rng(seed)
    
    def get_seed(self) -> int:
        """Get the seed"""
        return self.seed
