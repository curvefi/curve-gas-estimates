import ape
from collections import namedtuple
from ethpm_types import HexBytes
from evm_trace.base import CallTreeNode
from evm_trace.display import DisplayableCallTreeNode
from evm_trace import ParityTraceList, get_calltree_from_parity_trace
from rich.console import Console as RichConsole
import sys
from typing import Optional


CallInfo = namedtuple("call", ["address", "gas_cost", "method_id"])
RICH_CONSOLE = RichConsole(file=sys.stdout)


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


def get_calltree(tx_hash: str) -> Optional[CallTreeNode]:

    web3 = ape.chain.provider.web3
    raw_trace_list = web3.manager.request_blocking("trace_transaction", [tx_hash])
    parity_trace = ParityTraceList.parse_obj(raw_trace_list)
    tree = get_calltree_from_parity_trace(parity_trace, display_cls=CallInfoParser)
    return tree


def attempt_decode_call_signature(contract: ape.Contract, method_id: str):

    # decode method id (or at least try):
    try:
        return contract.contract_type.mutable_methods[HexBytes(method_id)].name
    except KeyError:
        try:
            return contract.contract_type.view_methods[HexBytes(method_id)].name
        except KeyError:
            RICH_CONSOLE.print(
                f"Could not decode method id [pink]{method_id} for contract [red]{contract}"
            )
            RICH_CONSOLE.print_exception()
            return method_id
