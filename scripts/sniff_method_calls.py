import sys

import ape
import click
from rich.console import Console as RichConsole

from scripts.utils.call_tree_parser_utils import get_calltree
from scripts.utils.call_tree_parsers import get_num_method_invokes_in_call_tree
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
    name="scrape",
    short_help=("Gets transactions which read Curve pool states",),
)
@ape.cli.network_option()
@click.option(
    "--contracts",
    "-c",
    required=True,
    type=str,
    help="address of contract who's state is being read in the tx",
    multiple=True,
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
@click.option(
    "--methods",
    "-m",
    default=[
        "get_dy",
        "calc_token_amount",
        "calc_withdraw_one_coin",
    ],
    help="Methods to scrape",
    type=str,
    multiple=True,
)
@click.option(
    "--output_file",
    "-o",
    default="contract_method_call_log.txt",
    type=str,
    help="Text file to write output to",
)
def sniff(network, contracts, max_transactions, max_block, methods, output_file):

    RICH_CONSOLE.log(
        f"[red]MAX BLOCK HEIGHT is set to merge block height: {MERGE_BLOCK_HEIGHT}"
    )

    # get transaction
    txes = []
    for contract in contracts:
        contract = ape.Contract(contract)
        txes.extend(
            list(
                set(
                    get_all_transactions_for_contract(
                        contract, max_transactions, max_block
                    )
                )
            )
        )

    if len(txes) > max_transactions:
        txes = txes[:max_transactions]  # truncate to max_transactions

    sus_txes = []
    for txid, tx in enumerate(txes):

        RICH_CONSOLE.log(
            f"Parsing [bold yellow]#{txid} [bold blue]{tx[1]} [white]at "
            f"block [bold blue]{tx[0]}."
        )
        call_tree = get_calltree(tx_hash=tx[1])

        contract_methods_called = []
        for contract in contracts:
            contract = ape.Contract(contract)
            contract_methods_called = get_num_method_invokes_in_call_tree(
                contract=contract,
                call=call_tree,
                methods_to_check=methods,
            )
        if len(contract_methods_called) > 0:
            RICH_CONSOLE.log(f"[bold green]Detected method(s) call.")
            sus_txes.append((tx[0], tx[1], ", ".join(contract_methods_called)))

    with open(output_file, "w") as f:
        for tx in sus_txes:
            f.write(f"{tx[0]}: {tx[1]} -> ({tx[2]})\n")
