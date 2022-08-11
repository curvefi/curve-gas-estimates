import ape
from collections import namedtuple
from typing import Dict
from ethpm_types import HexBytes

from evm_trace import ParityTraceList, get_calltree_from_parity_trace
from evm_trace.display import DisplayableCallTreeNode
from evm_trace.base import CallTreeNode


CallInfo = namedtuple("call", ["address", "gas_cost", "method_id"])


class DecodeMethodIDError(Exception):
    """Could not decode method id"""


class CallInfoParser(DisplayableCallTreeNode):
    @property
    def info(self) -> CallInfo:
        return CallInfo(
            address=self.call.address.hex(),
            gas_cost=self.call.gas_cost,
            method_id=self.call.calldata[:4].hex(),
        )


def _get_calltree(tx_hash: str):

    web3 = ape.chain.provider.web3
    raw_trace_list = web3.manager.request_blocking("trace_transaction", [tx_hash])
    parity_trace = ParityTraceList.parse_obj(raw_trace_list)

    return get_calltree_from_parity_trace(parity_trace, display_cls=CallInfoParser)


def _attempt_decode_call_signature(contract: ape.Contract, method_id: str):

    # decode method id (or at least try):
    try:
        method_name = contract.contract_type.mutable_methods[HexBytes(method_id)].name
    except KeyError:
        method_name = contract.contract_type.view_methods[HexBytes(method_id)].name
    return method_name


def _get_avg_gas_cost_per_method_for_tx(
    contract: ape.Contract,
    tree: CallTreeNode,
) -> Dict[str, int]:

    call_costs = {}
    for call in tree.display_nodes:

        if call.info.address.lower() != contract.address.lower():
            continue

        # decode call signature
        method_name = _attempt_decode_call_signature(contract, call.info.method_id)

        if call.info.method_id not in call_costs.keys():
            call_costs[method_name] = [call.info.gas_cost]
            continue

        call_costs[method_name].append(call.info.gas_cost)

    # average gas cost per method
    # warning: this is data compression!!! we only keep the average!
    for method_name, costs in call_costs.items():
        call_costs[method_name] = sum(costs) // len(costs)

    return call_costs


def get_gas_cost_for_contract(contract: ape.Contract, tx_hash: str) -> Dict[str, int]:
    call_tree = _get_calltree(tx_hash=tx_hash)
    return _get_avg_gas_cost_per_method_for_tx(contract, call_tree)
