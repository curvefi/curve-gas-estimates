import json
import os
import sys
from typing import Dict

import ape
import click
from rich.console import Console as RichConsole

from scripts.utils.call_tree_parser_utils import get_calltree
from scripts.utils.call_tree_parsers import parse_as_tree
from scripts.utils.gas_stats_calculator import (
    compute_bimodal_gaussian_gas_stats_for_txes,
    compute_univariate_gaussian_gas_stats_for_txes,
    get_avg_gas_cost_per_method_for_tx, get_gas_cost_for_txes)
from scripts.utils.pool_getter import (get_cryptoswap_registry_pools,
                                       get_stableswap_registry_pools)
from scripts.utils.transactions_getter import get_all_transactions_for_contract

STABLESWAP_GAS_TABLE_FILE = "./stableswap_pools_gas_estimates.json"
CRYPTOSWAP_GAS_TABLE_FILE = "./cryptoswap_pools_gas_estimates.json"
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

    costs[pool_addr] = decoded_gas_table
    with open(output_file_name, "w") as f:
        json.dump(costs, f, indent=4)

    RICH_CONSOLE.log("... saved!")


# ---- writes gas table to file ---- #


def _fetch_costs_and_save(pools, max_transactions, output_file_name, gas_stats_methods):
    # load cache if it exists:
    cached_costs = _load_cache(output_file_name)
    for pool_addr in pools:

        try:
            pool = ape.Contract(pool_addr)
        except ape.exceptions.ChainError:
            RICH_CONSOLE.log(
                f"[red]{pool_addr} is not verified on Etherskem. Moving on."
            )
            continue

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
        if pool.address not in cached_costs or cached_costs[pool.address][
            "max_block"
        ] < max(blocks):

            txes = list(list(zip(*txes))[1])
            df_gas_costs = get_gas_cost_for_txes(pool, txes)

            # get gas stats:
            gas_stats = {}
            has_data = False
            for gas_stats_method in gas_stats_methods:

                gstats = gas_stats_method(df_gas_costs)
                gas_stats_keys = list(gstats.keys())
                if gstats[gas_stats_keys[0]]:
                    has_data = True or has_data
                    gas_stats[gas_stats_keys[0]] = gstats[gas_stats_keys[0]]

            # save gas costs to file
            if has_data:
                gas_stats["min_block"] = min(blocks)
                gas_stats["max_block"] = max(blocks)
                _append_gas_table_to_output_file(output_file_name, pool_addr, gas_stats)
        else:

            RICH_CONSOLE.log("Pool cached with similar gas stats. Moving on.")


@click.group(short_help="Gets average gas costs for contracts")
def cli():
    """
    Command-line helper for fetching historic gas costs
    """


@cli.command(
    cls=ape.cli.NetworkBoundCommand,
    name="pools",
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
@click.option(
    "--pool_type",
    "-pt",
    required=True,
    help="Type of pool to get gas costs for. Must be either stableswap or cryptoswap",
    type=str,
)
def pool_gas_stats(network, max_transactions, pool, pool_type):

    settings = {}
    match pool_type:
        case "stableswap":
            settings["pool_getter"] = [get_stableswap_registry_pools]
            settings["output_file_name"] = [STABLESWAP_GAS_TABLE_FILE]
            settings["statmethods"] = [[compute_univariate_gaussian_gas_stats_for_txes]]
        case "cryptoswap":
            settings["pool_getter"] = [get_cryptoswap_registry_pools]
            settings["output_file_name"] = [CRYPTOSWAP_GAS_TABLE_FILE]
            settings["statmethods"] = [
                [
                    compute_univariate_gaussian_gas_stats_for_txes,
                    compute_bimodal_gaussian_gas_stats_for_txes,
                ]
            ]
        case "all":
            settings = {
                "pool_getter": [
                    get_stableswap_registry_pools,
                    get_cryptoswap_registry_pools,
                ],
                "output_file_name": [
                    STABLESWAP_GAS_TABLE_FILE,
                    CRYPTOSWAP_GAS_TABLE_FILE,
                ],
                "statmethods": [
                    [compute_univariate_gaussian_gas_stats_for_txes],
                    [
                        compute_univariate_gaussian_gas_stats_for_txes,
                        compute_bimodal_gaussian_gas_stats_for_txes,
                    ],
                ],
            }
        case _:
            RICH_CONSOLE.print(
                "[red]Invalid pool type. Must be either stableswap or cryptoswap"
            )
            return

    if settings:

        for i in range(len(settings["pool_getter"])):

            pool_getter = settings["pool_getter"][i]
            output_file_name = settings["output_file_name"][i]
            statmethods = settings["statmethods"][i]

            # get all pools in the registry:
            if not pool:
                pools = pool_getter()
            else:
                pools = [pool]

            _fetch_costs_and_save(
                pools,
                max_transactions,
                output_file_name,
                statmethods,
            )


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
        rich_call_tree = parse_as_tree(
            call_tree,
            [contract.address, "0x8F68f4810CcE3194B6cB6F3d50fa58c2c9bDD1d5"],
        )

        RICH_CONSOLE.log(f"Call trace for [bold blue]'{tx}'[/]")
        RICH_CONSOLE.log(rich_call_tree)
        RICH_CONSOLE.log(f"\nGas consumed per method for [red]'{contract}':")
        gas_cost = get_avg_gas_cost_per_method_for_tx(contract, call_tree)
        RICH_CONSOLE.print_json(json.dumps(gas_cost, indent=4))
