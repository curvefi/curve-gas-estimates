import sys

import ape
import click
import pandas as pd
from rich.console import Console as RichConsole

from scripts.utils.call_tree_parser_utils import get_calltree
from scripts.utils.call_tree_parsers import parse_math_calls
from scripts.utils.transactions_getter import get_all_transactions_for_contract

CURVE_CRYPTO_MATH = "0x8F68f4810CcE3194B6cB6F3d50fa58c2c9bDD1d5"
TRICRYPTO2 = "0xD51a44d3FaE010294C616388b506AcdA1bfAAE46"
RICH_CONSOLE = RichConsole(file=sys.stdout)
METHODS_TO_PARSE = ["geometric_mean"]


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
)
@ape.cli.network_option()
@click.option(
    "--max_transactions",
    "-mt",
    default=10000,
    help="Max number of txes",
    type=int,
)
def crypto_math_data_fetcher(network, max_transactions):

    math_contract = ape.project.CurveCryptoMath.at(CURVE_CRYPTO_MATH)
    tricrypto2_contract = ape.Contract(TRICRYPTO2)
    geometric_mean_data = pd.DataFrame(
        columns=["tx", "x0", "x1", "x2", "output"]
    )

    # get transaction
    txes = list(
        set(get_all_transactions_for_contract(tricrypto2_contract, max_transactions))
    )
    if len(txes) > max_transactions:
        txes = txes[:max_transactions]  # truncate to max_transactions

    RICH_CONSOLE.log(
        "[yellow]Getting newton_y and newton_D inputs and outputs ..."
    )
    for txid, tx in enumerate(txes):

        RICH_CONSOLE.log(
            f"for transaction [bold yellow]#{txid} [bold blue]{tx} ..."
        )

        call_tree = get_calltree(tx_hash=tx[1])
        if call_tree:

            parsed_math_io = flatten(
                parse_math_calls(
                    call_tree,
                    math_contract,
                    METHODS_TO_PARSE,
                    CURVE_CRYPTO_MATH,
                )
            )

            for parsed_call_info in parsed_math_io:

                if parsed_call_info["method"] == "geometric_mean":

                    parsed_geometric_mean = {
                        "tx": tx[1],
                        "x0": int(parsed_call_info["input"][0][0]),
                        "x1": int(parsed_call_info["input"][0][1]),
                        "x2": int(parsed_call_info["input"][0][2]),
                        "output": int(parsed_call_info["output"]),
                    }

                    geometric_mean_data = pd.concat(
                        [
                            geometric_mean_data,
                            pd.DataFrame(parsed_geometric_mean, index=[0]),
                        ],
                        ignore_index=True,
                    )

    # save data:
    if not geometric_mean_data.empty:
        RICH_CONSOLE.log("Saving geometric_mean data ...")
        geometric_mean_data.to_csv("geometric_mean_data.csv")
