import ape
import click
import json
import os
import sys
from rich.console import Console as RichConsole
from scripts.utils import (
    get_all_transactions_for_contract,
    get_transactions_in_block_range,
    get_avg_gas_cost_per_method_for_tx,
    get_calltree,
    parse_as_tree,
    compute_univariate_gaussian_gas_stats_for_txes,
)
from typing import Dict

from scripts.utils.pool_getter import get_stableswap_registry_pools


STABLESWAP_GAS_TABLE_FILE = "./stableswap_pools_gas_estimates.json"
RICH_CONSOLE = RichConsole(file=sys.stdout)


def _load_cache(filename: str):

    costs = {}
    if os.path.exists(filename):
        with open(filename, "r") as f:
            try:
                costs = json.load(f)
            except json.decoder.JSONDecodeError:
                pass

    return costs


def _append_gas_table_to_output_file(
    output_file_name: str, pool_addr: str, decoded_gas_table: Dict
):

    # save gas costs to file
    RICH_CONSOLE.log(f"saving gas costs to file [green]{output_file_name}...")
    costs = _load_cache(output_file_name)

    # we check if pool_addr key exists in the previously cached gas table:
    # if so, then we check if the new gas table has a higher number of transaction
    # count that are used in the stats. If so, then we update the cached gas table.
    if pool_addr not in costs or decoded_gas_table["count"] > costs[pool_addr]["count"]:

        costs[pool_addr] = decoded_gas_table
        with open(output_file_name, "w") as f:
            json.dump(costs, f, indent=4)

        RICH_CONSOLE.log("... saved!")


@click.group(short_help="Gets average gas costs for contracts")
def cli():
    """
    Command-line helper for fetching historic gas costs
    """


# ---- writes to file stableswap_pools_gas_estimates.json---- #


@cli.command(
    cls=ape.cli.NetworkBoundCommand,
    name="stableswap",
    short_help=(
        "Get average gas costs for methods in pool contracts in a registry "
        "in the past `min_transaction` transactions",
    ),
)
@ape.cli.network_option()
@click.option(
    "--max_transactions",
    "-ma",
    required=True,
    help="Minimum number of transactions to use in the calculation",
    type=int,
    default=10000,
)
@click.option(
    "--pool",
    "-p",
    required=False,
    help="Pool address to get gas costs for. If specified, then it does not check registry",
    type=str,
    default="",
)
def stableswap(network, max_transactions, pool):

    # load cache if it exists:
    costs = _load_cache(STABLESWAP_GAS_TABLE_FILE)

    # get all pools in the registry:
    if not pool:
        pools = get_stableswap_registry_pools()
    else:
        pools = [pool]

    for pool_addr in pools:

        pool = ape.Contract(pool_addr)

        # get transaction
        txes = list(set(get_all_transactions_for_contract(pool, max_transactions)))
        if len(txes) == 0:
            RICH_CONSOLE.log(f"No transactions found for {pool.address}. Moving on.")
            continue

        # truncate list if max_transactions is specified:
        if len(txes) > max_transactions:
            txes = txes[-max_transactions:]

        # check if we have cached gas costs for this pool. if we do
        # then we check if the current txes > tx count in cached stats.
        # if so, we update the cached stats:
        blocks = list(list(zip(*txes))[0])
        if (
            pool.address not in costs
            or len(txes) > costs[pool.address]["count"]
            or costs[pool.address]["max_block"] < max(blocks)
        ):

            # get gas stats:
            gas_stats = compute_univariate_gaussian_gas_stats_for_txes(
                pool, list(list(zip(*txes))[1])
            )

            # save gas costs to file
            if gas_stats:
                gas_stats["min_block"] = min(blocks)
                gas_stats["max_block"] = max(blocks)
                _append_gas_table_to_output_file(
                    STABLESWAP_GAS_TABLE_FILE, pool_addr, gas_stats
                )
        else:

            RICH_CONSOLE.log("Pool cached with similar gas stats. Moving on.")


# ---- read only ---- #


@cli.command(
    cls=ape.cli.NetworkBoundCommand,
    name="tx",
    short_help=("Get aggregated gas costs in a tx for a contract"),
)
@ape.cli.network_option()
@click.option("--contractaddr", "-c", required=True, help="Contract address", type=str)
@click.option("--tx", "-t", required=True, help="Transaction hash", type=str)
def get_gas_costs_tx(network, contractaddr, tx):

    contract = ape.Contract(contractaddr)
    call_tree = get_calltree(tx_hash=tx)
    if call_tree:
        rich_call_tree = parse_as_tree(call_tree, [contract.address])

        RICH_CONSOLE.log(f"Call trace for [bold blue]'{tx}'[/]")
        RICH_CONSOLE.log(rich_call_tree)
        RICH_CONSOLE.log(f"\nGas consumed per method for [red]'{contract}':")
        gas_cost = get_avg_gas_cost_per_method_for_tx(contract, call_tree)
        RICH_CONSOLE.print_json(json.dumps(gas_cost, indent=4))
