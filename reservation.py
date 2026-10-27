'''Definition of Reservation protocol for the adaptive-continuous protocol
'''

from typing import TYPE_CHECKING, List, Tuple, Dict, Any
from sequence.network_management.reservation import ResourceReservationProtocol, Reservation, ResourceReservationMessage, QCap, RSVPMsgType
from sequence.network_management.reservation import MemoryTimeCard
from sequence.resource_management.rule_manager import Rule
from sequence.network_management.reservation import eg_rule_condition, ep_rule_condition1, ep_rule_condition2, es_rule_conditionB1, es_rule_conditionA, es_rule_conditionB2
from sequence.kernel.event import Event
from sequence.kernel.process import Process
from sequence.resource_management.memory_manager import MemoryInfo
from sequence.resource_management.rule_manager import Arguments
from sequence.entanglement_management.entanglement_protocol import EntanglementProtocol

from execution_events import ADAPTIVE, APPLICATION, Booked, MisRemoved, Unbooked, reservation_serial
from generation import EntanglementGenerationAadaptive, ShEntanglementGenerationAadaptive
from swapping import EntanglementSwappingA_bds, EntanglementSwappingB_bds
from sequence.entanglement_management.swapping import EntanglementSwappingA, EntanglementSwappingB
from purification import BBPSSW_bds
from sequence.entanglement_management.purification.bbpssw_circuit import BBPSSWCircuit

if TYPE_CHECKING:
    from node import QuantumRouterAdaptive



# 1. entanglement generation #

def eg_rule_action1_adaptive(memories_info: List["MemoryInfo"], args: Dict[str, Any]) -> \
                             Tuple[EntanglementGenerationAadaptive | ShEntanglementGenerationAadaptive, List[None], List[None], List[None]]:
    """Action function used by entanglement generation protocol on nodes except the initiator, i.e., index > 0
    """
    memories = [info.memory for info in memories_info]
    memory = memories[0]
    mid = args["mid"]
    path = args["path"]
    index = args["index"]
    from_app_request = args["from_app_request"]
    encoding_type = args["encoding_type"]
    if encoding_type == "single_atom":
        protocol_name = "EGAa." + memory.name
        protocol = EntanglementGenerationAadaptive(None, protocol_name, mid, path[index - 1], memory, from_app_request)
    elif encoding_type == "single_heralded":
        protocol_name = "ShEGAa." + memory.name
        raw_epr_errors = args["raw_epr_errors"]
        protocol = ShEntanglementGenerationAadaptive(None, protocol_name, mid, path[index - 1], memory, from_app_request, raw_epr_errors)
    else:
        raise ValueError(f'encoding type {encoding_type} not supported yet')
    return protocol, [None], [None], [None]


def eg_rule_action2_adaptive(memories_info: List["MemoryInfo"], args: Arguments) -> \
                             Tuple[EntanglementGenerationAadaptive | ShEntanglementGenerationAadaptive, List[str], List["eg_req_func_adaptive"], List[Dict]]:
    """Action function used by entanglement generation protocol on nodes except the responder, i.e., index < len(path) - 1
    """
    mid = args["mid"]
    path = args["path"]
    index = args["index"]
    memories = [info.memory for info in memories_info]
    memory = memories[0]
    from_app_request = args["from_app_request"]
    encoding_type = args["encoding_type"]
    if encoding_type == "single_atom":
        protocol_name = "EGAa." + memory.name
        protocol = EntanglementGenerationAadaptive(None, protocol_name, mid, path[index + 1], memory, from_app_request)
    elif encoding_type == "single_heralded":
        protocol_name = "ShEGAa." + memory.name
        raw_epr_errors = args["raw_epr_errors"]
        protocol = ShEntanglementGenerationAadaptive(None, protocol_name, mid, path[index + 1], memory, from_app_request, raw_epr_errors)
    else:
        raise ValueError(f'encoding type {encoding_type} not supported yet')
    req_args = {"name": args["name"], "reservation": args["reservation"]}
    return protocol, [path[index + 1]], [eg_req_func_adaptive], [req_args]


def eg_req_func_adaptive(protocols: List["EntanglementProtocol"], args: Arguments) -> EntanglementGenerationAadaptive | ShEntanglementGenerationAadaptive:
    """Function used by `eg_rule_action2` function for selecting generation protocols on the remote node
    Args:
        protocols: the waiting protocols (wait for request)
        args: arguments from the node who sent the request
    Return:
        the selected protocol (there could be multiple protocols that satisfy the condition, if so, return the first protocol)
    """
    name = args["name"]
    reservation = args["reservation"]
    for protocol in protocols:
        if (isinstance(protocol, EntanglementGenerationAadaptive | ShEntanglementGenerationAadaptive)
                and protocol.remote_node_name == name
                and protocol.rule.get_reservation() == reservation):
            return protocol


def eg_rule_condition_one_shot(memory_info: "MemoryInfo", manager, args: Arguments):
    """Disable regeneration after a compiler reservation creates its first pair."""
    reservation = args.get("reservation")
    if (getattr(reservation, "compiler_directed", False)
            and reservation.compiler_pair_generated):
        return []
    return eg_rule_condition(memory_info, manager, args)


def eg_rule_condition_request(memory_info: "MemoryInfo", manager, args: Arguments):
    """Start the normal application protocol on an adopted, already-entangled slot."""
    if (args.get("compiler_handoff") and not args.get("handoff_started")
            and memory_info.index in args["memory_indices"]
            and memory_info.state == MemoryInfo.ENTANGLED):
        args["handoff_started"] = True
        return [memory_info]
    result = eg_rule_condition(memory_info, manager, args)
    if result and args.get("compiler_handoff"):
        args["handoff_started"] = True
    return result


# 2. entanglement purification #

def ep_rule_action1_adaptive(memories_info: List["MemoryInfo"], args: Arguments) -> Tuple[BBPSSWCircuit | BBPSSW_bds, List[str], List["ep_req_func1_adaptive"], List[Dict]]:
    """Action function used by BBPSSW protocol on nodes except the initiator node
    """
    encoding_type=args["encoding_type"]
    memories = [info.memory for info in memories_info]
    if encoding_type == "single_atom":
        name = "EP.%s.%s" % (memories[0].name, memories[1].name)
        protocol = BBPSSWCircuit(None, name, memories[0], memories[1])
    elif encoding_type == "single_heralded":
        name = "EP_bds.%s.%s" % (memories[0].name, memories[1].name)
        protocol = BBPSSW_bds(None, name, memories[0], memories[1])

    dsts = [memories_info[0].remote_node]
    req_funcs = [ep_req_func1_adaptive]
    req_args = [{"remote0": memories_info[0].remote_memo, "remote1": memories_info[1].remote_memo}]
    return protocol, dsts, req_funcs, req_args


def ep_rule_action2_adaptive(memories_info: List["MemoryInfo"], args: Arguments) -> Tuple[BBPSSWCircuit | BBPSSW_bds, List[None], List[None], List[None]]:
    """Action function used by BBPSSW protocol on nodes except the responder node
    """
    encoding_type = args['encoding_type']
    memories = [info.memory for info in memories_info]
    if encoding_type == "single_atom":
        name = "EP.%s" % memories[0].name
        protocol = BBPSSWCircuit(None, name, memories[0], None)
    elif encoding_type == "single_heralded":
        name = "EP_bds.%s" % memories[0].name
        protocol = BBPSSW_bds(None, name, memories[0], None)
    return protocol, [None], [None], [None]


def ep_req_func1_adaptive(protocols, args: Arguments) -> BBPSSWCircuit | BBPSSW_bds:
    """Function used by `ep_rule_action1` for selecting purification protocols on the remote node
       Will "combine" two BBPSSW into one BBPSSW

    Args:
        protocols (list): a list of waiting protocols
        args (dict): the arguments
    Return:
        the selected protocol
    """
    remote0 = args["remote0"]
    remote1 = args["remote1"]

    _protocols = []
    for protocol in protocols:
        if not (isinstance(protocol, BBPSSWCircuit) or isinstance(protocol, BBPSSW_bds)):
            continue

        if protocol.kept_memo.name == remote0:
            _protocols.insert(0, protocol)     # 0 is kept
        if protocol.kept_memo.name == remote1:
            _protocols.insert(1, protocol)     # 1 is meas

    if len(_protocols) != 2:
        return None

    protocols.remove(_protocols[1])            # remove the EP_bds for meas
    _protocols[1].rule.protocols.remove(_protocols[1])
    _protocols[1].kept_memo.detach(_protocols[1])
    _protocols[0].meas_memo = _protocols[1].kept_memo  # [0]'s meas is [1]'s kept
    _protocols[0].memories = [_protocols[0].kept_memo, _protocols[0].meas_memo]
    _protocols[0].name = _protocols[0].name + "." + _protocols[0].meas_memo.name
    _protocols[0].meas_memo.attach(_protocols[0])

    return _protocols[0]



# 3. entanglement swapping #

def es_rule_actionA_adaptive(memories_info: List["MemoryInfo"], args: Arguments) -> Tuple[EntanglementSwappingA | EntanglementSwappingA_bds, List[str], List["es_req_func_adaptive"], List[Dict]]:
    """Action function used by EntanglementSwappingA protocol on nodes
    """
    es_succ_prob = args["es_succ_prob"]
    memories = [info.memory for info in memories_info]
    encoding_type = args["encoding_type"]
    
    if encoding_type == "single_atom":
        es_degradation = args["es_degradation"]
        name = "ESA.{}.{}".format(memories[0].name, memories[1].name)
        protocol = EntanglementSwappingA(None, name, memories[0], memories[1], es_succ_prob, es_degradation)
    elif encoding_type == 'single_heralded':
        is_twirled = args['is_twirled']
        name = "ESA_bds.{}.{}".format(memories[0].name, memories[1].name)
        protocol = EntanglementSwappingA_bds(None, name, memories[0], memories[1], es_succ_prob, is_twirled)

    dsts = [info.remote_node for info in memories_info]
    req_funcs = [es_req_func_adaptive, es_req_func_adaptive]
    req_args = [{"target_memo": memories_info[0].remote_memo}, {"target_memo": memories_info[1].remote_memo}]
    return protocol, dsts, req_funcs, req_args


def es_rule_actionB_adaptive(memories_info: List["MemoryInfo"], args: Arguments) -> Tuple[EntanglementSwappingB | EntanglementSwappingB_bds, List[None], List[None], List[None]]:
    """Action function used by EntanglementSwappingB protocol
    """
    memories = [info.memory for info in memories_info]
    memory = memories[0]
    encoding_type = args["encoding_type"]
    if encoding_type == "single_atom":
        protocol = EntanglementSwappingB(None, "ESB." + memory.name, memory)
    elif encoding_type == 'single_heralded':
        protocol = EntanglementSwappingB_bds(None, "ESB_bds." + memory.name, memory)
    return protocol, [None], [None], [None]


def es_req_func_adaptive(protocols: List["EntanglementProtocol"], args: Arguments) -> EntanglementSwappingB_bds | EntanglementSwappingB_bds:
    """Function used by `es_rule_actionA` for selecting swapping protocols on the remote node
    """
    target_memo = args["target_memo"]
    for protocol in protocols:
        if (isinstance(protocol, EntanglementSwappingB | EntanglementSwappingB_bds)
                # and protocol.memory.name == memories_info[0].remote_memo):
                and protocol.memory.name == target_memo):
            return protocol



class ApplicationReservation(Reservation):
    """A reservation made on behalf of one trace request.

    SeQUeNCe's ``Reservation`` compares and hashes on initiator, responder, start, end, size
    and fidelity, and ignores ``identity``.  Two requests with the same endpoints and window are
    then the same reservation to every lookup by equality: ``MemoryTimeCard.remove`` releases
    the first equal one, rule creation picks memories with ``reservation in card.reservations``,
    and the application keys its timestamps and latencies by reservation.  Including the request
    identity makes two requests distinct bookings.  A resubmission has a new window, so it never
    equals the attempt it replaces.

    An application reservation equals only another application reservation, so it can never be
    mistaken for a CGP/ACGP or compiler reservation.
    """

    def __eq__(self, other):
        return (isinstance(other, ApplicationReservation) and super().__eq__(other)
                and self.identity == other.identity)

    def __hash__(self):
        return hash((super().__hash__(), self.identity))


class ReservationAdaptive(Reservation):
    """Tracking of reservation parameters for the network manager.
       Each request will generate a reservation

       Note: the only difference compared with the parant class is a minor change in __str__()
       
    Attributes:
        initiator (str): name of the node that created the reservation request.
        responder (str): name of distant node with witch entanglement is requested.
        start_time (int): simulation time at which entanglement should be attempted.
        end_time (int): simulation time at which resources may be released.
        memory_size (int): number of entangled memory pairs requested.
        path (list): a list of router names from the source to destination
    """

    def __init__(self, initiator: str, responder: str, start_time: int,
                 end_time: int, memory_size: int, fidelity: float, *,
                 compiler_target_request_id: int | None = None,
                 compiler_generation_layer: int | None = None,
                 compiler_target_layer: int | None = None,
                 compiler_strategy: str | None = None):
        """Constructor for the reservation class.

        Args:
            initiator (str): node initiating the request.
            responder (str): node with which entanglement is requested.
            start_time (int): simulation start time of entanglement.
            end_time (int): simulation end time of entanglement.
            memory_size (int): number of entangled memories requested.
            fidelity (float): desired fidelity of entanglement.
        """
        super().__init__(initiator, responder, start_time, end_time, memory_size, fidelity)
        self.compiler_target_request_id = compiler_target_request_id
        self.compiler_generation_layer = compiler_generation_layer
        self.compiler_target_layer = compiler_target_layer
        self.compiler_strategy = compiler_strategy
        # Compiler preparations are one-shot.  Ordinary CGP/ACGP reservations
        # retain their original continuous-generation behavior.
        self.compiler_pair_generated = False

    def __eq__(self, other):
        # Simultaneous preparations on the same edge are different jobs.
        # Base Reservation equality omits the target, which otherwise aliases
        # their timecards, protocol pairing and one-shot completion flags.
        return (isinstance(other, Reservation) and not isinstance(other, ApplicationReservation)
                and super().__eq__(other)
                and self.compiler_target_request_id ==
                    getattr(other, "compiler_target_request_id", None))

    def __hash__(self):
        base = super().__hash__()
        if self.compiler_target_request_id is None:
            return base  # preserve equality/hash compatibility with Reservation
        return hash((base, self.compiler_target_request_id))

    @property
    def compiler_directed(self) -> bool:
        return self.compiler_target_request_id is not None

    def __str__(self) -> str:
        kind = "CompilerPreGeneration" if self.compiler_directed else "AdaptiveContinuous"
        return "|{}; initiator={}; responder={}; start_time={:,}; end_time={:,}; memory_size={}; target_fidelity={}; target_request={}|".format(
                kind, self.initiator, self.responder, int(self.start_time), int(self.end_time),
                self.memory_size, self.fidelity, self.compiler_target_request_id)

    def __repr__(self) -> str:
        return self.__str__()



def describe_reservation(reservation) -> tuple[int, str]:
    """The (request id, kind) that labels a reservation in execution events.

    Application reservations are plain ``Reservation`` objects whose ``identity`` is the
    trace request id.  Adaptive ones (CGP/ACGP and compiler preparations) have no
    request id of their own; a compiler preparation reports the request it targets.
    """
    if isinstance(reservation, ReservationAdaptive):
        target = reservation.compiler_target_request_id
        return (-1 if target is None else target), ADAPTIVE
    return reservation.identity, APPLICATION


def notify_release(owner) -> None:
    """Tell the router's ``release_observer``, if it has one, that a booking was just released.

    A request scheduler uses this to learn when a core can admit more work.  Without an
    observer (every run that does not ask for event-driven admission) this does nothing.
    """
    observer = getattr(owner, "release_observer", None)
    if observer is not None:
        observer(owner.name)


class ObservedTimeCard(MemoryTimeCard):
    """A ``MemoryTimeCard`` that reports bookings and releases to its router's recorder.

    Behaviour is exactly that of ``MemoryTimeCard``.  The only addition is that, when the
    router has a recorder, adding or removing a reservation emits an event, so unobserved
    runs are unaffected.
    """

    def __init__(self, memory_index: int, owner: "QuantumRouterAdaptive") -> None:
        super().__init__(memory_index)
        self._owner = owner

    def add(self, reservation) -> bool:
        added = super().add(reservation)
        recorder = getattr(self._owner, "recorder", None)
        if added and recorder is not None:
            request_id, kind = describe_reservation(reservation)
            recorder.record(Booked(self._owner.timeline.now(), self._owner.name, self.memory_index,
                                   reservation_serial(reservation), request_id, kind, hash(reservation),
                                   reservation.start_time, reservation.end_time))
        return added

    def remove(self, reservation) -> bool:
        recorder = getattr(self._owner, "recorder", None)
        # MemoryTimeCard.remove releases the first stored reservation that *compares equal*,
        # which need not be the object that was passed in.
        stored = (next((item for item in self.reservations if item == reservation), None)
                  if recorder is not None else None)
        removed = super().remove(reservation)
        if removed and recorder is not None:
            now, node = self._owner.timeline.now(), self._owner.name
            if stored is reservation:
                request_id, kind = describe_reservation(stored)
                recorder.record(Unbooked(now, node, self.memory_index, reservation_serial(stored), request_id, kind, "removed"))
            else:
                recorder.record(MisRemoved(now, node, self.memory_index, reservation_serial(reservation), reservation_serial(stored),
                                           describe_reservation(reservation)[0]))
        if removed:
            notify_release(self._owner)
        return removed


class ResourceReservationProtocolAdaptive(ResourceReservationProtocol):
    '''ReservationProtocol for node resources customized for adaptive-continuous protocol
    '''

    def __init__(self, owner: "QuantumRouterAdaptive", name: str, memory_array_name: str):
        super().__init__(owner, name, memory_array_name)
        self.timecards = [ObservedTimeCard(card.memory_index, owner) for card in self.timecards]
        # Local ownership: the reservation object can be shared by endpoints.
        self._reservation_leases = {}
        self.compiler_handoff = True

    def _handoff_candidate(self, reservation):
        if (not self.compiler_handoff or not isinstance(reservation, ApplicationReservation)
                or reservation.memory_size != 1):
            return None
        pair = getattr(reservation, "compiler_handoff_pair", None)
        adaptive = self.owner.adaptive_continuous
        if pair is None:
            neighbor = reservation.responder if self.owner.name == reservation.initiator else reservation.initiator
            if not adaptive.has_ready_compiler_pair(neighbor, reservation.identity, reservation.fidelity):
                return None
            pair = next(p for p in sorted(adaptive.generated_entanglement_pairs)
                        if p[1][0] == neighbor and
                        adaptive.generated_pair_metadata.get(p, {}).get("target_request_id") == reservation.identity)
        memory_name = next((memo for node, memo in pair if node == self.owner.name), None)
        for lease in self._reservation_leases.values():
            if not lease["compiler"] or lease["released"]:
                continue
            if lease["reservation"].compiler_target_request_id != reservation.identity:
                continue
            if not any(m.name == memory_name for m in lease["memories"]):
                continue
            local_pair = pair if pair[0][0] == self.owner.name else (pair[1], pair[0])
            if local_pair not in adaptive.generated_entanglement_pairs:
                return None
            if adaptive.get_fidelity(local_pair) < reservation.fidelity:
                return None
            memory = lease["memories"][0]
            info = self.owner.resource_manager.memory_manager.get_info_by_memory(memory)
            if info.state != MemoryInfo.ENTANGLED:
                return None
            card = self.timecards[info.index]
            if any(r is not lease["reservation"] and
                   max(r.start_time, reservation.start_time) <= min(r.end_time, reservation.end_time)
                   for r in card.reservations):
                return None
            rules = [rule for rule in self.owner.resource_manager.rule_manager.rules
                     if rule.reservation is lease["reservation"]]
            if any(rule.protocols for rule in rules):
                return None
            return pair, lease, card, rules
        return None

    def schedule(self, reservation):
        candidate = self._handoff_candidate(reservation)
        if candidate is None:
            # If the peer already claimed a particular pair, do not substitute
            # another memory after expiry; reject and let normal request retry run.
            if getattr(reservation, "compiler_handoff_pair", None) is not None:
                # A pair may disappear during RSVP flight. Do not leave its
                # now-useless compiler booking blocking fallback until timeout.
                for lease in tuple(getattr(self, "_reservation_leases", {}).values()):
                    if (lease["compiler"] and not lease["released"] and
                            lease["reservation"].compiler_target_request_id == reservation.identity):
                        self.release_reservation(lease["reservation"], "handoff_unavailable")
                return False
            return super().schedule(reservation)
        pair, old, card, rules = candidate
        reservation.compiler_handoff_pair = pair
        old["released"] = True
        for event in old["events"]:
            self.owner.timeline.remove_event(event)
        for rule in rules:
            self.owner.resource_manager.expire(rule)
        # Transfer booking ownership only. Preserve quantum state, generation
        # timestamp, noise, and the original physical memory-expiration event.
        assert card.remove(old["reservation"])
        assert card.add(reservation)
        adaptive = self.owner.adaptive_continuous
        assert adaptive.adaptive_memory_used > 0
        adaptive.adaptive_memory_used -= 1
        self._reservation_leases[id(reservation)] = dict(
            reservation=reservation, memories=old["memories"], events=[],
            compiler=False, released=False, handoff=True)
        # RSVP still performs its real request/approval exchange at both nodes.
        return True

    def push(self, responder: str, start_time: int, end_time: int, memory_size: int, target_fidelity: float,
             entanglement_number: int = 1, identity: int = 0):
        """Receive a reservation request from the application.

        Identical to ``ResourceReservationProtocol.push`` except that the reservation is an
        ``ApplicationReservation``, which carries the request identity in its equality.
        """
        reservation = ApplicationReservation(self.owner.name, responder, start_time, end_time, memory_size,
                                             target_fidelity, entanglement_number, identity)
        if self.schedule(reservation):
            msg = ResourceReservationMessage(RSVPMsgType.REQUEST, self.name, reservation)
            msg.qcaps.append(QCap(self.owner.name))
            self._push(dst=responder, msg=msg)
        else:
            msg = ResourceReservationMessage(RSVPMsgType.REJECT, self.name, reservation, path=[])
            self._pop(msg=msg)

    def _track_reservation_event(self, reservation, event):
        lease = self._reservation_leases.get(id(reservation))
        if lease is not None:
            lease["events"].append(event)
        self.owner.timeline.schedule(event)

    def _load_owned_rules(self, rules, reservation, compiler=False):
        memories = [self.memo_arr[card.memory_index] for card in self.timecards
                    if any(item is reservation for item in card.reservations)]
        lease = self._reservation_leases.get(id(reservation))
        if lease is None or lease["released"]:
            lease = {"reservation": reservation, "memories": memories,
                     "events": [], "compiler": compiler, "released": False}
        self._reservation_leases[id(reservation)] = lease
        self.accepted_reservations.append(reservation)
        for rule in rules:
            event = Event(reservation.start_time,
                          Process(self.owner.resource_manager, "load", [rule]))
            self._track_reservation_event(reservation, event)
        event = Event(reservation.end_time,
                      Process(self, "release_reservation", [reservation, "reservation_expired"]))
        self._track_reservation_event(reservation, event)

    def load_rules(self, rules, reservation):
        """Own timeout events so early completion cannot reset reused memory."""
        self._load_owned_rules(rules, reservation)

    def release_reservation(self, reservation, reason="completed"):
        """Release a local lease once, including its future cleanup events."""
        lease = self._reservation_leases.get(id(reservation))
        if lease is None or lease["released"]:
            return False
        lease["released"] = True
        timeline = self.owner.timeline
        for event in lease["events"]:
            timeline.remove_event(event)
        # Disable generation before returning any of its memories to RAW.
        manager = self.owner.resource_manager
        for rule in list(manager.rule_manager.rules):
            if rule.reservation is reservation:
                manager.expire(rule)
        recorder = getattr(self.owner, "recorder", None)
        held = False
        for card in self.timecards:
            if any(item is reservation for item in card.reservations):
                held = True
                if recorder is not None:
                    request_id, kind = describe_reservation(reservation)
                    recorder.record(Unbooked(timeline.now(), self.owner.name, card.memory_index,
                                             reservation_serial(reservation), request_id, kind, reason))
            card.reservations[:] = [item for item in card.reservations if item is not reservation]
        adaptive = self.owner.adaptive_continuous
        if lease["compiler"]:
            assert adaptive.adaptive_memory_used > 0, "compiler quota released twice"
            adaptive.adaptive_memory_used -= 1
        app = getattr(self.owner, "app", None)
        for memory in lease["memories"]:
            index = manager.memory_manager.get_info_by_memory(memory).index
            if app is not None and app.memo_to_reservation.get(index) is reservation:
                app.memo_to_reservation.pop(index)
            adaptive.note_memory_expiration(memory, reason=reason)
            manager.update(None, memory, MemoryInfo.RAW)
        if held:
            notify_release(self.owner)
        return True

    def release_consumed_compiler_memory(self, memory_name):
        for lease in tuple(self._reservation_leases.values()):
            if lease["compiler"] and not lease["released"] and any(
                    memory.name == memory_name for memory in lease["memories"]):
                return self.release_reservation(lease["reservation"], "consumed")
        return False


    def create_rules_adaptive(self, path: list, reservation: ReservationAdaptive) -> List["Rule"]:
        """Method to create rules for entanglement generation (only) for a successful AC protocol's request.

        Rules are used to direct the flow of information/entanglement in the resource manager.

        Args:
            path (List[str]): list of node names in entanglement path.
            reservation (Reservation): approved reservation.

        Returns:
            List[Rule]: list of rules created by the method.
        """
        rules = []
        memory_indices = []
        for card in self.timecards:  # check which timecard includes the reservation
            if reservation in card.reservations:
                memory_indices.append(card.memory_index)

        index = path.index(self.owner.name)  # the location of this node along the path from initiator to responder
        
        priority = 20
        # create rules for entanglement generation
        if index > 0:
            condition_args = {
                "memory_indices": memory_indices[:reservation.memory_size],
                "reservation": reservation,
            }
            action_args = {"mid": self.owner.map_to_middle_node[path[index - 1]], "path": path, "index": index, "from_app_request": False,
                           "encoding_type": "single_heralded", "raw_epr_errors": [1/3, 1/3, 1/3]}
            rule = Rule(
                priority, eg_rule_action1_adaptive,
                eg_rule_condition_one_shot, action_args, condition_args,
            )
            rules.append(rule)
            priority += 1

        if index < len(path) - 1:
            if index == 0:
                condition_args = {
                    "memory_indices": memory_indices[:reservation.memory_size],
                    "reservation": reservation,
                }
            else:
                condition_args = {
                    "memory_indices": memory_indices[reservation.memory_size:],
                    "reservation": reservation,
                }

            action_args = {"mid": self.owner.map_to_middle_node[path[index + 1]],
                           "path": path, "index": index, "name": self.owner.name, "reservation": reservation, "from_app_request": False,
                           "encoding_type": "single_heralded", "raw_epr_errors": [1/3, 1/3, 1/3]}
            rule = Rule(
                10, eg_rule_action2_adaptive,
                eg_rule_condition_one_shot, action_args, condition_args,
            )
            rules.append(rule)
            priority += 1

        for rule in rules:
            rule.set_reservation(reservation)
        
        return rules


    def load_rules_adaptive(self, rules: List[Rule], reservation: ReservationAdaptive):
        """Method to add AC protocol created rules (EntanglementGeneration only) to resource manager.

        This method will schedule the resource manager to load all rules at the reservation start time.
        The rules will be set to expire at the reservation end time.

        Args:
            rules (List[Rules]): rules to add.
            reservation (Reservation): reservation that created the rules.
        """

        if reservation.compiler_directed:
            self._load_owned_rules(rules, reservation, compiler=True)
            return

        self.accepted_reservations.append(reservation)

        for rule in rules:
            process = Process(self.owner.resource_manager, "load", [rule])
            event = Event(reservation.start_time, process)
            self.owner.timeline.schedule(event)

            process = Process(self.owner.resource_manager, "expire", [rule])
            event = Event(reservation.end_time, process, self.owner.timeline.schedule_counter)
            self.owner.timeline.schedule(event)


        for card in self.timecards:
            if reservation in card.reservations:
                process = Process(self.owner.resource_manager, "update", [None, self.memo_arr[card.memory_index], "RAW"]) # update memory to RAW
                event = Event(reservation.end_time, process, self.owner.timeline.schedule_counter)
                self.owner.timeline.schedule(event)

                process = Process(self.owner.adaptive_continuous, "adaptive_memory_used_minus_one", [self.memo_arr[card.memory_index]])
                event = Event(reservation.end_time, process, self.owner.timeline.schedule_counter)
                self.owner.timeline.schedule(event)


    def create_rules_request(self, path: list, reservation: ReservationAdaptive) -> List["Rule"]:
        """Method to create rules for a successful request.

        Note: Use the RuleAdaptive class for creating entanglement generation protocols

        Rules are used to direct the flow of information/entanglement in the resource manager.

        Args:
            path (List[str]): list of node names in entanglement path.
            reservation (Reservation): approved reservation.

        Returns:
            List[Rule]: list of rules created by the method.
        """

        rules = []
        memory_indices = []
        for card in self.timecards:
            if reservation in card.reservations:
                memory_indices.append(card.memory_index)

        index = path.index(self.owner.name)  # the location of this node along the path from initiator to responder

        priority = 10
        # 1. create rules for entanglement generation
        if index > 0:                  # non initiator
            condition_args = {"memory_indices": memory_indices[:reservation.memory_size],
                              "compiler_handoff": getattr(reservation, "compiler_handoff_pair", None) is not None}
            action_args = {"mid": self.owner.map_to_middle_node[path[index - 1]],
                           "path": path, "index": index, "from_app_request": True,
                           "encoding_type": "single_heralded", "raw_epr_errors": [1/3, 1/3, 1/3]}  # TODO: make 1/3 an input
            rule = Rule(priority, eg_rule_action1_adaptive, eg_rule_condition_request, action_args, condition_args)
            rules.append(rule)
            priority += 1

        if index < len(path) - 1:      # non responder
            if index == 0:
                condition_args = {"memory_indices": memory_indices[:reservation.memory_size],
                                  "compiler_handoff": getattr(reservation, "compiler_handoff_pair", None) is not None}
            else:
                condition_args = {"memory_indices": memory_indices[reservation.memory_size:]}  # the second half

            action_args = {"mid": self.owner.map_to_middle_node[path[index + 1]],
                           "path": path, "index": index, "name": self.owner.name, "reservation": reservation, "from_app_request": True,
                           "encoding_type": "single_heralded", "raw_epr_errors": [1/3, 1/3, 1/3]}
            rule = Rule(priority, eg_rule_action2_adaptive, eg_rule_condition_request, action_args, condition_args)
            rules.append(rule)
            priority += 1

        # 2. create rules for entanglement purification
        if index > 0:                  # non initiator
            condition_args = {"memory_indices": memory_indices[:reservation.memory_size], "reservation": reservation}
            action_args = {"encoding_type": "single_heralded"}
            rule = Rule(priority, ep_rule_action1_adaptive, ep_rule_condition1, action_args, condition_args)
            rules.append(rule)
            priority += 1

        if index < len(path) - 1:      # non responder
            if index == 0:
                condition_args = {"memory_indices": memory_indices, "fidelity": reservation.fidelity}
            else:
                condition_args = {"memory_indices": memory_indices[reservation.memory_size:], "fidelity": reservation.fidelity}

            action_args = {"encoding_type": "single_heralded"}
            rule = Rule(priority, ep_rule_action2_adaptive, ep_rule_condition2, action_args, condition_args)
            rules.append(rule)
            priority += 1

        # 3. create rules for entanglement swapping
        if index == 0:                 # initiator
            condition_args = {"memory_indices": memory_indices, "target_remote": path[-1], "fidelity": reservation.fidelity}
            action_args = {"encoding_type": "single_heralded"}
            rule = Rule(priority, es_rule_actionB_adaptive, es_rule_conditionB1, action_args, condition_args)
            rules.append(rule)
            priority += 1

        elif index == len(path) - 1:   # responder
            action_args = {"encoding_type": "single_heralded"}
            condition_args = {"memory_indices": memory_indices, "target_remote": path[0], "fidelity": reservation.fidelity}
            rule = Rule(priority, es_rule_actionB_adaptive, es_rule_conditionB1, action_args, condition_args)
            rules.append(rule)
            priority += 1

        else:                          # middle nodes
            _path = path[:]
            while _path.index(self.owner.name) % 2 == 0:
                new_path = []
                for i, n in enumerate(_path):
                    if i % 2 == 0 or i == len(_path) - 1:
                        new_path.append(n)
                _path = new_path
            _index = _path.index(self.owner.name)
            left, right = _path[_index - 1], _path[_index + 1]

            condition_args = {"memory_indices": memory_indices, "left": left, "right": right, "fidelity": reservation.fidelity}
            action_args = {"es_succ_prob": self.es_succ_prob, "es_degradation": self.es_degradation, "encoding_type": "single_heralded", "is_twirled": True}
            rule = Rule(priority, es_rule_actionA_adaptive, es_rule_conditionA, action_args, condition_args)
            rules.append(rule)
            priority += 1

            action_args = {"encoding_type": "single_heralded"}
            rule = Rule(priority, es_rule_actionB_adaptive, es_rule_conditionB2, action_args, condition_args)
            rules.append(rule)
            priority += 1

        for rule in rules:
            rule.set_reservation(reservation)

        return rules


    def pop(self, src: str, msg: "ResourceReservationMessage"):
        """Method to receive messages from lower protocols.

        Messages may be of 3 types, causing different network manager behavior:

        1. REQUEST: requests are evaluated, and forwarded along the path if accepted. Otherwise a REJECT message is sent back.
        2. REJECT: any reserved resources are released and the message forwarded back towards the initializer.
        3. APPROVE: rules are created to achieve the approved request. The message is forwarded back towards the initializer.

        Args:
            src (str): source node of the message.
            msg (ResourceReservationMessage): message received.
        
        Side Effects:
            May push/pop to lower/upper attached protocols (or network manager).

        Assumption:
            the path initiator -> responder is same as the reverse path
        """

        if msg.msg_type == RSVPMsgType.REQUEST:
            assert self.owner.timeline.now() < msg.reservation.start_time, f"Current time {self.owner.timeline.now()} must be smaller than reservation start time {msg.reservation.start_time}"
            qcap = QCap(self.owner.name)
            msg.qcaps.append(qcap)
            path = [qcap.node for qcap in msg.qcaps]
            if self.schedule(msg.reservation):   # schedule success
                if self.owner.name == msg.reservation.responder:
                    rules = self.create_rules_request(path, reservation=msg.reservation)
                    self.load_rules(rules, msg.reservation)
                    msg.reservation.set_path(path)
                    new_msg = ResourceReservationMessage(RSVPMsgType.APPROVE, self.name, msg.reservation, path=path)
                    self._pop(msg=msg)
                    self._push(dst=None, msg=new_msg, next_hop=src)
                else:                            # schedule failed
                    self._push(dst=msg.reservation.responder, msg=msg)
            else:
                new_msg = ResourceReservationMessage(RSVPMsgType.REJECT, self.name, msg.reservation, path=path)
                self._push(dst=None, msg=new_msg, next_hop=src)
        elif msg.msg_type == RSVPMsgType.REJECT:
            if not self.release_reservation(msg.reservation, "rejected"):
                for card in self.timecards:
                    card.remove(msg.reservation)
            if msg.reservation.initiator == self.owner.name:
                self._pop(msg=msg)
            else:
                next_hop = self.next_hop_when_tracing_back(msg.path)
                self._push(dst=None, msg=msg, next_hop=next_hop)
        elif msg.msg_type == RSVPMsgType.APPROVE:
            rules = self.create_rules_request(msg.path, msg.reservation)
            self.load_rules(rules, msg.reservation)
            if msg.reservation.initiator == self.owner.name:
                self._pop(msg=msg)
            else:
                next_hop = self.next_hop_when_tracing_back(msg.path)
                self._push(dst=None, msg=msg, next_hop=next_hop)
        else:
            raise Exception("Unknown type of message", msg.msg_type)

    def next_hop_when_tracing_back(self, path: List[str]) -> str:
        '''the next hop when going back from the responder to the initiator

        Args:
            path (List[str]): a list of router names that goes from initiator to responder
        Return:
            str: the name of the next hop
        '''
        cur_index = path.index(self.owner.name)
        assert cur_index >= 1, f'{cur_index} must be larger equal than 1'
        next_hop = path[cur_index - 1]
        return next_hop
