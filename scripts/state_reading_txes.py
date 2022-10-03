import sys

import ape
import click
from rich.console import Console as RichConsole

from scripts.utils.call_tree_parsers import (
    get_calltree,
    get_num_method_invokes_in_call_tree,
)
from scripts.utils.transactions_getter import get_all_transactions_for_contract

CURVE_CRYPTO_MATH = "0x8F68f4810CcE3194B6cB6F3d50fa58c2c9bDD1d5"
TRICRYPTO2 = "0xD51a44d3FaE010294C616388b506AcdA1bfAAE46"
MERGE_BLOCK_HEIGHT = 15537394
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
    name="get_state_reading_txes",
    short_help=("Gets transactions which read Curve pool states",),
)
@ape.cli.network_option()
@click.option(
    "--contract",
    "-c",
    required=True,
    type=str,
    help="address of contract who's state is being read in the tx",
)
@click.option(
    "--max_transactions",
    "-mt",
    default=10000,
    help="Max number of txes",
    type=int,
)
@click.option(
    "--max_block",
    "-mb",
    default=MERGE_BLOCK_HEIGHT,
    help="Max block height",
    type=int,
)
def crypto_math_data_fetcher(network, contract, max_transactions, max_block):

    RICH_CONSOLE.log(
        f"[red]MAX BLOCK HEIGHT is set to merge block height: {MERGE_BLOCK_HEIGHT}"
    )

    economic_state_reading_methods = [
        "balances",
        "get_dy",
        "calc_token_amount",
        "calc_withdraw_one_coin",
    ]

    # get transaction
    txes = list(
        set(
            get_all_transactions_for_contract(
                contract, max_transactions, max_block
            )
        )
    )
    if len(txes) > max_transactions:
        txes = txes[:max_transactions]  # truncate to max_transactions

    sus_txes = []
    for txid, tx in enumerate(txes):

        RICH_CONSOLE.log(
            f"for transaction [bold yellow]#{txid} [bold blue]{tx} ..."
        )
        call_tree = get_calltree(tx_hash=tx[1])

        if (
            get_num_method_invokes_in_call_tree(
                call_tree, economic_state_reading_methods, num_calls=0
            )
            > 0
        ):
            RICH_CONSOLE.log(f"[bold green]Transaction reads state")
            sus_txes.append(tx)

    with open("sus_txes.txt", "w") as f:
        for tx in sus_txes:
            f.write(f"{tx[0]}: {tx[1]}")
