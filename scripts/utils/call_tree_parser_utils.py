# inspired from ape > evm-trace
# this is just a functional version of their object oriented call trace parser

import sys
from collections import namedtuple
from typing import Any, Dict, Optional

import ape
from ape.api import EcosystemAPI
from ape.exceptions import ContractError, DecodingError
from ape.utils.abi import Struct, parse_type
from eth_abi import decode_abi
from eth_abi.exceptions import InsufficientDataBytes
from eth_utils import humanize_hash, is_hex_address
from ethpm_types import HexBytes
from ethpm_types.abi import MethodABI
from evm_trace import (
    CallTreeNode,
    ParityTraceList,
    get_calltree_from_parity_trace,
)
from evm_trace.base import CallTreeNode
from evm_trace.display import DisplayableCallTreeNode
from hexbytes import HexBytes
from rich.console import Console as RichConsole

CallInfo = namedtuple("call", ["address", "gas_cost", "method_id", "calldata"])
RICH_CONSOLE = RichConsole(file=sys.stdout)


class CallInfoParser(DisplayableCallTreeNode):
    @property
    def info(self) -> CallInfo:

        return CallInfo(
            address=self.call.address.hex(),
            gas_cost=self.call.gas_cost,
            method_id=self.call.calldata[:4].hex(),
            calldata=self.call.calldata,
        )


def attempt_decode_call_signature(contract: ape.Contract, selector: str):

    # decode method id (or at least try):
    method = selector.hex()
    if selector in contract.contract_type.mutable_methods:
        method = contract.contract_type.mutable_methods[selector]
        return method.name or f"<{selector}>"
    elif selector in contract.contract_type.view_methods:
        method = contract.contract_type.view_methods[selector]
        return method.name or f"<{selector}>"
    else:
        return method


def get_calltree(tx_hash: str) -> Optional[CallTreeNode]:

    web3 = ape.chain.provider.web3
    raw_trace_list = web3.manager.request_blocking(
        "trace_transaction", [tx_hash]
    )
    parity_trace = ParityTraceList.parse_obj(raw_trace_list)
    tree = get_calltree_from_parity_trace(
        parity_trace, display_cls=CallInfoParser
    )

    return tree


def decode_calldata(
    method: MethodABI,
    raw_data: bytes,
    _ecosystem: EcosystemAPI,
    _chain_manager: ape.managers.chain.ChainManager,
) -> Dict:
    input_types = [i.canonical_type for i in method.inputs]  # type: ignore

    try:
        raw_input_values = decode_abi(input_types, raw_data)
        input_values = [
            decode_value(
                _ecosystem.decode_primitive_value(v, parse_type(t)),
                _ecosystem,
                _chain_manager,
            )
            for v, t in zip(raw_input_values, input_types)
        ]
    except (DecodingError, InsufficientDataBytes):
        input_values = ["<?>" for _ in input_types]

    arguments = {}
    index = 0
    for i, v in zip(method.inputs, input_values):
        name = i.name or f"{index}"
        arguments[name] = v
        index += 1

    return arguments


def decode_returndata(
    method: MethodABI,
    raw_data: bytes,
    _ecosystem: EcosystemAPI,
    _chain_manager: ape.managers.chain.ChainManager,
) -> Any:

    values = [
        decode_value(v, _ecosystem, _chain_manager)
        for v in _ecosystem.decode_returndata(method, raw_data)
    ]

    if len(values) == 1:
        return values[0]

    return values


def decode_value(
    value,
    _ecosystem: EcosystemAPI,
    _chain_manager: ape.managers.chain.ChainManager,
):
    if isinstance(value, HexBytes):
        try:
            string_value = value.strip(b"\x00").decode("utf8")
            return f"'{string_value}'"
        except UnicodeDecodeError:
            # Truncate bytes if very long.
            if len(value) > 24:
                return humanize_hash(value)

            hex_str = HexBytes(value).hex()
            if is_hex_address(hex_str):
                return decode_value(hex_str, _ecosystem, _chain_manager)

            return hex_str

    elif isinstance(value, str) and is_hex_address(value):
        return decode_address(value, _ecosystem, _chain_manager)

    elif value and isinstance(value, str):
        # Surround non-address strings with quotes.
        return f'"{value}"'

    elif isinstance(value, (list, tuple)):
        decoded_values = [
            decode_value(v, _ecosystem, _chain_manager) for v in value
        ]
        return decoded_values

    elif isinstance(value, Struct):
        decoded_values = {
            k: decode_value(v, _ecosystem, _chain_manager)
            for k, v in value.items()
        }
        return decoded_values

    return value


def decode_address(
    address: str,
    _ecosystem: EcosystemAPI,
    _chain_manager: ape.managers.chain.ChainManager,
) -> str:

    # Use name of known contract if possible.
    checksum_address = _ecosystem.decode_address(address)
    contract_type = _chain_manager.contracts.get(checksum_address)
    if contract_type:
        contract_name = contract_type.name
        if "symbol" in contract_type.view_methods:
            contract = _chain_manager.contracts.instance_at(
                address, contract_type
            )
            try:
                contract_name = contract.symbol() or contract_name
            except ContractError:
                contract_name = contract_type.name

        return contract_name

    return checksum_address
