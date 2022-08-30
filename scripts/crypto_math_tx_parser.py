import json
import sys
import ape
import click
import collections

from evm_trace.base import CallTreeNode
from eth_abi import decode_abi
from rich.console import Console as RichConsole
from scripts.utils.call_tree_parser import (
    attempt_decode_call_signature,
    get_calltree,
    parse_as_tree,
)
from scripts.utils.transactions_getter import get_all_transactions_for_contract
from typing import Dict, List

CURVE_CRYPTO_MATH = "0x8F68f4810CcE3194B6cB6F3d50fa58c2c9bDD1d5"
RICH_CONSOLE = RichConsole(file=sys.stdout)


def flatten(S):
    # from https://stackoverflow.com/a/12472564
    if S == []:
        return S
    if isinstance(S[0], list):
        return flatten(S[0]) + flatten(S[1:])
    return S[:1] + flatten(S[1:])


def parse_math_calls(
    call: CallTreeNode,
    math_contract: ape.Contract,
    methods_to_parse: List[str],
) -> Dict:

    _ecosystem = ape.networks.ecosystems["ethereum"]
    address = _ecosystem.decode_address(call.address)
    selector = call.calldata[:4]
    method = attempt_decode_call_signature(math_contract, selector)
    parsed_math_calls = []

    # we only parse math contracts and ignore failed txes:
    if (
        not call.failed
        and address.lower() == CURVE_CRYPTO_MATH.lower()
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
        parsed_subcall = parse_math_calls(sub_call, math_contract, methods_to_parse)
        if parsed_subcall:
            parsed_math_calls.append(parsed_subcall)

    return parsed_math_calls


@click.group(short_help="Gets specific information from transactions")
def cli():
    """
    Command-line helper for fetching specific data from txes
    """


@cli.command(
    cls=ape.cli.NetworkBoundCommand,
    name="tx",
    short_help=("Gets crypto math inputs for transactions of a Curve v2 pool",),
)
@ape.cli.network_option()
@click.option(
    "--pool",
    "-p",
    required=False,
    help="Pool address",
    type=str,
)
def crypto_math_data_fetcher(network, pool):

    curve_crypto_math = ape.project.CurveCryptoMath.at(CURVE_CRYPTO_MATH)

    # get transaction
    txes = list(set(get_all_transactions_for_contract(pool, 100000)))
    if len(txes) == 0:
        RICH_CONSOLE.log(f"No transactions found for {pool.address}.")
        return

    for tx in txes:

        call_tree = get_calltree(tx_hash=tx)
        if call_tree:

            for call in call_tree.display_nodes:
                pass


@cli.command(
    cls=ape.cli.NetworkBoundCommand,
    name="tx",
    short_help=("Gets trace for math contract and pool"),
)
@ape.cli.network_option()
@click.option("--contractaddr", "-c", required=True, help="Contract address", type=str)
@click.option("--tx", "-t", required=True, help="Transaction hash", type=str)
def get_gas_costs_tx(network, contractaddr, tx):

    math_contract = ape.project.CurveCryptoMath.at(CURVE_CRYPTO_MATH)
    methods_to_parse = ["newton_y", "newton_D"]
    contract = ape.Contract(contractaddr)
    call_tree = get_calltree(tx_hash=tx)
    if call_tree:
        rich_call_tree = parse_as_tree(call_tree, [contract.address, CURVE_CRYPTO_MATH])

        RICH_CONSOLE.log(f"Call trace for [bold blue]'{tx}'[/]")
        RICH_CONSOLE.log(rich_call_tree)

        parsed_math_io = parse_math_calls(call_tree, math_contract, methods_to_parse)
        parsed_math_io = flatten(parsed_math_io)
        RICH_CONSOLE.print_json(json.dumps(parsed_math_io, indent=4))
