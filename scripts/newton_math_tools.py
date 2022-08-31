import json
import sys
import ape
import click

import pandas as pd
from rich.console import Console as RichConsole
from scripts.utils.call_tree_parser import (
    get_calltree,
    parse_as_tree,
    parse_math_calls,
)
from scripts.utils.transactions_getter import get_all_transactions_for_contract


CURVE_CRYPTO_MATH = "0x8F68f4810CcE3194B6cB6F3d50fa58c2c9bDD1d5"
TRICRYPTO2 = "0xD51a44d3FaE010294C616388b506AcdA1bfAAE46"
RICH_CONSOLE = RichConsole(file=sys.stdout)
METHODS_TO_PARSE = ["newton_y", "newton_D"]


def flatten(S):
    # from https://stackoverflow.com/a/12472564
    if S == []:
        return S
    if isinstance(S[0], list):
        return flatten(S[0]) + flatten(S[1:])
    return S[:1] + flatten(S[1:])


@click.group(short_help="Gets specific information from transactions")
def cli():
    """
    Command-line helper for fetching specific data from txes
    """


@cli.command(
    cls=ape.cli.NetworkBoundCommand,
    name="tricrypto2",
    short_help=("Gets crypto math inputs for transactions of a Curve v2 pool",),
)
@ape.cli.network_option()
@click.option(
    "--max_transactions", "-mt", default=10000, help="Max number of txes", type=int
)
def crypto_math_data_fetcher(network, max_transactions):

    math_contract = ape.project.CurveCryptoMath.at(CURVE_CRYPTO_MATH)
    tricrypto2_contract = ape.Contract(TRICRYPTO2)

    newton_y_data = pd.DataFrame(
        columns=["tx", "ANN", "gamma", "x0", "x1", "x2", "D", "i", "output"]
    )
    newton_D_data = pd.DataFrame(
        columns=[
            "tx",
            "ANN",
            "gamma",
            "x_unsorted_0",
            "x_unsorted_1",
            "x_unsorted_2",
            "output",
        ]
    )

    # get transaction
    txes = list(
        set(get_all_transactions_for_contract(tricrypto2_contract, max_transactions))
    )

    for tx in txes:
        call_tree = get_calltree(tx_hash=tx[1])
        if call_tree:

            parsed_math_io = flatten(
                parse_math_calls(
                    call_tree, math_contract, METHODS_TO_PARSE, CURVE_CRYPTO_MATH
                )
            )

            for parsed_call_info in parsed_math_io:
                try:
                    if parsed_call_info["method"] == "newton_y":
                        parsed_newton_y = {
                            "tx": tx[1],
                            "ANN": int(parsed_call_info["input"][0]),
                            "gamma": int(parsed_call_info["input"][1]),
                            "x0": int(parsed_call_info["input"][2][0]),
                            "x1": int(parsed_call_info["input"][2][1]),
                            "x2": int(parsed_call_info["input"][2][2]),
                            "D": int(parsed_call_info["input"][3]),
                            "i": int(parsed_call_info["input"][4]),
                            "output": int(parsed_call_info["output"]),
                        }
                        len(parsed_newton_y)
                        newton_y_data = pd.concat(
                            [
                                newton_y_data,
                                pd.DataFrame(parsed_newton_y, index=[0]),
                            ],
                            ignore_index=True,
                        )
                    elif parsed_call_info["method"] == "newton_D":
                        parsed_newton_D = {
                            "tx": tx[1],
                            "ANN": int(parsed_call_info["input"][0]),
                            "gamma": int(parsed_call_info["input"][1]),
                            "x_unsorted_0": int(parsed_call_info["input"][2][0]),
                            "x_unsorted_1": int(parsed_call_info["input"][2][1]),
                            "x_unsorted_2": int(parsed_call_info["input"][2][2]),
                            "output": int(parsed_call_info["output"]),
                        }
                        newton_D_data = pd.concat(
                            [
                                newton_D_data,
                                pd.DataFrame(parsed_newton_D, index=[0]),
                            ],
                            ignore_index=True,
                        )
                except:
                    print(parsed_call_info["input"][2][0])
                    raise

    if not newton_D_data.empty:
        RICH_CONSOLE.log("Saving newton_D data ...")
        newton_D_data.to_csv("newton_D_data.csv")
    if not newton_y_data.empty:
        RICH_CONSOLE.log("Saving newton_y data ...")
        newton_y_data.to_csv("newton_y_data.csv")


@cli.command(
    cls=ape.cli.NetworkBoundCommand,
    name="tx",
    short_help=("Gets inputs and outputs for tricrypto2 math"),
)
@ape.cli.network_option()
@click.option("--tx", "-t", required=True, help="Transaction hash", type=str)
def get_gas_costs_tx(network, tx):

    math_contract = ape.project.CurveCryptoMath.at(CURVE_CRYPTO_MATH)
    call_tree = get_calltree(tx_hash=tx)
    if call_tree:
        rich_call_tree = parse_as_tree(call_tree, [TRICRYPTO2, CURVE_CRYPTO_MATH])

        RICH_CONSOLE.log(f"Call trace for [bold blue]'{tx}'[/]")
        RICH_CONSOLE.log(rich_call_tree)

        parsed_math_io = flatten(
            parse_math_calls(
                call_tree, math_contract, METHODS_TO_PARSE, CURVE_CRYPTO_MATH
            )
        )
        RICH_CONSOLE.print_json(json.dumps(parsed_math_io, indent=4))
