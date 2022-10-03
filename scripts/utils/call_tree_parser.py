# inspired from ape > evm-trace
# this is just a functional version of their object oriented call trace parser

import re
import sys
from collections import namedtuple
from typing import Any, Dict, List, Optional

import ape
from ape.api import EcosystemAPI
from ape.exceptions import ContractError, DecodingError
from ape.utils.abi import Struct, parse_type
from ape.utils.trace import (_DEFAULT_INDENT, _DEFAULT_TRACE_GAS_PATTERN,
                             _DEFAULT_WRAP_THRESHOLD, TraceStyles,
                             _MethodTraceSignature)
from eth_abi import decode_abi
from eth_abi.exceptions import InsufficientDataBytes
from eth_utils import humanize_hash, is_hex_address
from ethpm_types import HexBytes
from ethpm_types.abi import MethodABI
from evm_trace import (CallTreeNode, ParityTraceList,
                       get_calltree_from_parity_trace)
from evm_trace.base import CallTreeNode
from evm_trace.display import DisplayableCallTreeNode
from hexbytes import HexBytes
from rich.console import Console as RichConsole
from rich.tree import Tree

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


def get_calltree(tx_hash: str) -> Optional[CallTreeNode]:

    web3 = ape.chain.provider.web3
    raw_trace_list = web3.manager.request_blocking("trace_transaction", [tx_hash])
    parity_trace = ParityTraceList.parse_obj(raw_trace_list)
    tree = get_calltree_from_parity_trace(parity_trace, display_cls=CallInfoParser)

    return tree


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


def parse_math_calls(
    call: CallTreeNode,
    math_contract: ape.Contract,
    methods_to_parse: List[str],
    math_contract_addr: str,
) -> Dict:

    _ecosystem = ape.networks.ecosystems["ethereum"]
    address = _ecosystem.decode_address(call.address)
    selector = call.calldata[:4]
    method = attempt_decode_call_signature(math_contract, selector)
    parsed_math_calls = []

    # we only parse math contracts and ignore failed txes:
    if (
        not call.failed
        and address.lower() == math_contract_addr.lower()
        and method in methods_to_parse
    ):

        # only highlight contract addresses if they are in highlight_contracts
        raw_calldata = call.calldata[4:]

        # get math method name:
        method_abi = math_contract.contract_type.view_methods[selector]

        # get math args:
        input_types = [i.canonical_type for i in method_abi.inputs]  # type: ignore
        raw_input_values = decode_abi(input_types, raw_calldata)
        arguments = [
            _ecosystem.decode_primitive_value(v, ape.utils.abi.parse_type(t))
            for v, t in zip(raw_input_values, input_types)
        ]

        # get returndata:
        return_value = _ecosystem.decode_returndata(method_abi, call.returndata)[0]

        # compile into return dict:
        parsed_math_calls.append(
            {
                "method": method,
                "input": arguments,
                "output": return_value,
                "gas": call.gas_cost,
            }
        )

    for sub_call in call.calls:
        parsed_subcall = parse_math_calls(
            sub_call, math_contract, methods_to_parse, math_contract_addr
        )
        if parsed_subcall:
            parsed_math_calls.append(parsed_subcall)

    return parsed_math_calls


def parse_as_tree(call: CallTreeNode, highlight_contracts: List[str]) -> Tree:
    """
    Create ``rich.Tree`` containing the nodes in a call trace
    for display purposes.

    Args:
        call (``CallTreeNode``): A node object from the ``evm-trace``
            library.

    Returns:
        ``rich.Tree``: A rich tree from the ``rich`` library.
    """
    _ecosystem = ape.networks.ecosystems["ethereum"]
    _chain_manager = (
        ape.networks.ecosystems["ethereum"].networks["mainnet"].chain_manager
    )

    address = _ecosystem.decode_address(call.address)

    # Collapse pre-compile address calls
    address_int = int(address, 16)
    if 1 <= address_int <= 9:
        sub_trees = [parse_as_tree(c) for c in call.calls]
        if len(sub_trees) == 1:
            return sub_trees[0]

        intermediary_node = Tree(f"{address_int}")
        for sub_tree in sub_trees:
            intermediary_node.add(sub_tree)

        return intermediary_node

    # only highlight contract addresses if they are in highlight_contracts
    contract_type = None
    if (
        sum(
            [
                address.lower() == highlight_contract.lower()
                for highlight_contract in highlight_contracts
            ]
        )
        > 0
    ):
        contract_type = _chain_manager.contracts.get(address)
    selector = call.calldata[:4]
    call_signature = ""

    def _dim_default_gas(call_sig: str) -> str:
        # Add style to default gas block so it matches nodes with contract types
        gas_part = re.findall(_DEFAULT_TRACE_GAS_PATTERN, call_sig)
        if gas_part:
            return f"{call_sig.split(gas_part[0])[0]} [{TraceStyles.GAS_COST}]{gas_part[0]}[/]"

        return call_sig

    if contract_type:
        method = None
        contract_name = contract_type.name
        if "symbol" in contract_type.view_methods:
            contract = _chain_manager.contracts.instance_at(address, contract_type)
            try:
                contract_name = contract.symbol() or contract_name
            except ContractError:
                contract_name = contract_type.name

        if selector in contract_type.mutable_methods:
            method = contract_type.mutable_methods[selector]
        elif selector in contract_type.view_methods:
            method = contract_type.view_methods[selector]

        if method:
            raw_calldata = call.calldata[4:]
            arguments = decode_calldata(
                method, raw_calldata, _ecosystem, _chain_manager
            )

            # The revert-message appears at the top of the trace output.
            try:
                return_value = (
                    decode_returndata(
                        method, call.returndata, _ecosystem, _chain_manager
                    )
                    if not call.failed
                    else None
                )
            except (DecodingError, InsufficientDataBytes):
                return_value = "<?>"

            call_signature = str(
                _MethodTraceSignature(
                    contract_name or address,
                    method.name or f"<{selector}>",
                    arguments,
                    return_value,
                    call.call_type,
                    colors=TraceStyles,
                    _indent=_DEFAULT_INDENT,
                    _wrap_threshold=_DEFAULT_WRAP_THRESHOLD,
                )
            )
            if call.gas_cost:
                call_signature += f" [bright_red][{call.gas_cost} gas][/]"

        elif contract_name is not None:
            call_signature = next(call.display_nodes).title  # type: ignore
            call_signature = call_signature.replace(address, contract_name)
            call_signature = _dim_default_gas(call_signature)
    else:
        next_node: Optional[DisplayableCallTreeNode] = None
        try:
            next_node = next(call.display_nodes)
        except StopIteration:
            pass

        if next_node:
            call_signature = _dim_default_gas(next_node.title)

        else:
            # Only for mypy's sake. May never get here.
            call_signature = f"{address}.<{selector.hex()}>"
            if call.gas_cost:
                call_signature = (
                    f"{call_signature} [{TraceStyles.GAS_COST}][{call.gas_cost} gas][/]"
                )

    if call.value:
        eth_value = round(call.value / 10**18, 8)
        if eth_value:
            call_signature += f" [{TraceStyles.VALUE}][{eth_value} value][/]"

    parent = Tree(call_signature, guide_style="dim")
    for sub_call in call.calls:
        parent.add(parse_as_tree(sub_call, highlight_contracts))

    return parent


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
        decoded_values = [decode_value(v, _ecosystem, _chain_manager) for v in value]
        return decoded_values

    elif isinstance(value, Struct):
        decoded_values = {
            k: decode_value(v, _ecosystem, _chain_manager) for k, v in value.items()
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
            contract = _chain_manager.contracts.instance_at(address, contract_type)
            try:
                contract_name = contract.symbol() or contract_name
            except ContractError:
                contract_name = contract_type.name

        return contract_name

    return checksum_address
