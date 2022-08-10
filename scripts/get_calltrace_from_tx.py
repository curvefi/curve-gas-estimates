import ape
from collections import namedtuple
from typing import Dict
from ethpm_types import HexBytes

from evm_trace import ParityTraceList, get_calltree_from_parity_trace
from evm_trace.display import DisplayableCallTreeNode
from evm_trace.base import CallTreeNode


CallInfo = namedtuple("call", ["address", "gas_cost", "method_id"])


class CallInfoParser(DisplayableCallTreeNode):
    @property
    def info(self) -> CallInfo:
        return CallInfo(
            address=self.call.address.hex(),
            gas_cost=self.call.gas_cost,
            method_id=self.call.calldata[:4].hex(),
        )


def get_calltree(tx_hash: str):

    web3 = ape.chain.provider.web3
    raw_trace_list = web3.manager.request_blocking("trace_transaction", [tx_hash])
    parity_trace = ParityTraceList.parse_obj(raw_trace_list)

    return get_calltree_from_parity_trace(parity_trace, display_cls=CallInfoParser)


def get_avg_gas_cost_per_method_for_tx(
    contract: str, tree: CallTreeNode
) -> Dict[str, int]:

    call_costs = {}
    for call in tree.display_nodes:
        if call.info.address.lower() != contract.lower():
            continue

        if call.info.method_id not in call_costs.keys():
            call_costs[call.info.method_id] = [call.info.gas_cost]
            continue

        call_costs[call.info.method_id].append(call.info.gas_cost)

    # average gas cost per method
    for method_id, costs in call_costs.items():
        call_costs[method_id] = sum(costs) // len(costs)

    return call_costs


def get_gas_cost_for_contract(contract: str, tx_hash: str) -> Dict[str, int]:
    call_tree = get_calltree(tx_hash=tx_hash)
    return get_avg_gas_cost_per_method_for_tx(contract, call_tree)
