import ape
import click
import json
import os
import sys
from rich.console import Console as RichConsole
from rich.json import JSON
from scripts.utils import (
    get_all_transactions_for_contract,
    get_transactions_in_block_range,
    get_avg_gas_cost_per_method_for_tx,
    get_calltree,
    parse_as_tree,
    compute_univariate_gaussian_gas_stats_for_txes,
)
from typing import Dict


REGISTRIES = {
    "MAIN_REGISTRY": "0x90E00ACe148ca3b23Ac1bC8C240C2a7Dd9c2d7f5",
    "STABLESWAP_FACTORY": "0xB9fC157394Af804a3578134A6585C0dc9cc990d4",
    "CRYPTOSWAP_REGISTRY": "0x8F942C20D02bEfc377D41445793068908E2250D0",
    "CRYPTOSWAP_FACTORY": "0xF18056Bbd320E96A48e3Fbf8bC061322531aac99",
}
STABLESWAP_GAS_TABLE_FILE = "./stableswap_pools_gas_estimates.json"
RICH_CONSOLE = RichConsole(file=sys.stdout)


def _get_pools(registry: str):
    pools = []
    registry = ape.Contract(registry)
    pool_count = registry.pool_count()
    for i in range(pool_count):
        pool = registry.pool_list(i)
        if pool not in pools:
            pools.append(pool)

    return pools


def _append_gas_table_to_output_file(
    output_file_name: str, pool_addr: str, decoded_gas_table: Dict
):

    # save gas costs to file
    RICH_CONSOLE.log(f"saving gas costs to file [green]{output_file_name}...")
    file_exists = os.path.exists(output_file_name)

    costs = {}
    if file_exists:
        with open(output_file_name, "r") as f:
            try:
                costs = json.load(f)
            except json.decoder.JSONDecodeError:
                pass

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
    name="stableswap-registry",
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
def get_gas_costs_for_stableswap_registry_pools(network, max_transactions):

    # get all pools in the registry:
    RICH_CONSOLE.log("Getting all stableswap pools ...")
    pools = []
    for registry in [REGISTRIES["MAIN_REGISTRY"], REGISTRIES["STABLESWAP_FACTORY"]]:
        pools.extend(_get_pools(registry))
    pools = list(set(pools))
    RICH_CONSOLE.log(f"... found [red]{len(pools)} pools.")

    for pool_addr in pools:

        pool = ape.Contract(pool_addr)

        # get transaction
        txes = list(set(get_all_transactions_for_contract(pool)))

        # truncate list if max_transactions is specified:
        if len(txes) > max_transactions:
            txes = txes[-max_transactions:]

        if len(txes) == 0:
            RICH_CONSOLE.log(f"No transactions found for {pool.address}. Moving on.")
            continue

        # get gas stats:
        gas_stats = compute_univariate_gaussian_gas_stats_for_txes(pool, txes)

        # save gas costs to file
        if gas_stats:
            _append_gas_table_to_output_file(
                STABLESWAP_GAS_TABLE_FILE, pool_addr, gas_stats
            )


@cli.command(
    cls=ape.cli.NetworkBoundCommand,
    name="stableswap",
    short_help=(
        "Get average gas costs for methods in a single pool for txes "
        "in block range `start_block` to `end_block`",
    ),
)
@ape.cli.network_option()
@click.option("--pool", "-p", required=True, help="Pool address", type=str)
@click.option("--start_block", "-s", required=True, help="Start block", type=int)
@click.option("--end_block", "-e", required=True, help="End block", type=int)
def get_gas_costs_for_stableswap_pool(network, pool, start_block, end_block):

    pool = ape.Contract(pool)

    # get all transactions
    RICH_CONSOLE.log(
        f"Getting transactions for pool [red]{pool.address} in range [blue]{start_block} - [blue]{end_block} ..."
    )
    tx_in_block = get_transactions_in_block_range(pool, start_block, end_block)

    if tx_in_block:

        # get gas stats
        gas_stats = compute_univariate_gaussian_gas_stats_for_txes(pool, tx_in_block)

        # save gas costs to file
        if gas_stats:
            _append_gas_table_to_output_file(
                STABLESWAP_GAS_TABLE_FILE, pool.address, gas_stats
            )

            RICH_CONSOLE.print_json(json.dumps(gas_stats, indent=4))

    RICH_CONSOLE.log("[yellow]No gas stats saved.")


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
