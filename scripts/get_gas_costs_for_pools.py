import os
import ape
import click
from hexbytes import HexBytes
import pandas
import json

from scripts.get_calltrace_from_tx import get_gas_cost_for_contract


REGISTRIES = {
    "MAIN_REGISTRY": "0x90E00ACe148ca3b23Ac1bC8C240C2a7Dd9c2d7f5",
    "STABLESWAP_FACTORY": "0xB9fC157394Af804a3578134A6585C0dc9cc990d4",
    "CRYPTOSWAP_REGISTRY": "0x8F942C20D02bEfc377D41445793068908E2250D0",
    "CRYPTOSWAP_FACTORY": "0xF18056Bbd320E96A48e3Fbf8bC061322531aac99",
}
MAX_ATTEMPTS = 10


def get_pools(registry: str):
    pools = []
    registry = ape.Contract(registry)
    pool_count = registry.pool_count()
    for i in range(pool_count):
        pool = registry.pool_list(i)
        if pool not in pools:
            pools.append(pool)
    return pools


def get_block_ranges(head: int, nblocks: int = 5000):
    return head - nblocks, head


@click.group(short_help="Gets average gas costs for contracts")
def cli():
    """
    Command-line helper for fetching historic gas costs
    """


@cli.command(
    cls=ape.cli.NetworkBoundCommand,
    name="stableswap",
    short_help="Get average gas costs for methods in pool contracts in a registry",
)
@ape.cli.network_option()
@click.option(
    "--min_transactions",
    "-m",
    required=True,
    help="Minimum number of transactions to use in the calculation",
    type=int,
    default=500,
)
def _gas_costs_for_stableswap_pools(network, min_transactions):

    output_file_name = f"stableswap_pools_gas_estimates.json"

    # get all pools in the registry:
    click.echo("Getting all stableswap pools ...")
    pools = []
    for registry in [REGISTRIES["MAIN_REGISTRY"], REGISTRIES["STABLESWAP_FACTORY"]]:
        pools.extend(get_pools(registry))
    pools = list(set(pools))
    click.echo(f"... found {len(pools)} pools.")

    costs = {}
    for pool_addr in pools:

        if pool_addr in costs:
            continue

        pool = ape.Contract(pool_addr)

        # get all transactions
        txes = []
        head = ape.chain.blocks.height
        block_start, block_end = get_block_ranges(head)

        click.echo(f"Getting transactions for pool {pool_addr}.")
        attempts = 0
        while len(txes) < min_transactions and attempts < MAX_ATTEMPTS:

            tx_in_block = []
            for _, event in pool._events_.items():

                initialised_event = ape.contracts.ContractEvent(pool, event[0].abi)
                for log in initialised_event.range(block_start, block_end):
                    tx = log.transaction_hash
                    if tx not in txes:
                        tx_in_block.append(tx)

            if len(tx_in_block) > 0:
                txes = txes + tx_in_block
                click.echo(
                    f"Found {len(tx_in_block)} txes between blocks {block_start}:{block_end}. Total: {len(txes)}"
                )
            block_start, block_end = get_block_ranges(block_start)
            attempts += 1

        if len(txes) == 0:
            click.echo(
                f"No transactions found between blocks {block_start}:{head}. Moving on."
            )
            continue

        # compute gas costs from aggregated txes
        txes = list(set(txes))
        click.echo(f"Found {len(txes)} transactions. Fetching gas costs ...")

        gas_costs_for_pool = []
        for tx in txes:
            gas_costs_for_pool.append(get_gas_cost_for_contract(pool_addr, tx))

        click.echo("... done!")
        df_gas_costs = pandas.DataFrame(gas_costs_for_pool)

        gas_table = (
            df_gas_costs.describe()
            .loc[["mean", "std", "min", "max"]]
            .fillna(0)
            .astype(int)
            .to_dict()
        )

        decoded_gas_table = {}
        for method_signature, gas_data in gas_table.items():
            try:
                method_name = pool.contract_type.mutable_methods[
                    HexBytes(method_signature)
                ].name
                decoded_gas_table[method_name] = gas_data
            except KeyError:
                # warning: we cannot decode so we just ignore it
                # todo: get decoded method name from abi
                continue

        # save gas costs to file
        click.echo("saving gas costs to file ...")
        costs = {}
        if os.path.exists(output_file_name):
            with open(output_file_name, "r") as f:
                costs = json.load(f)

        costs[pool_addr] = decoded_gas_table
        with open(output_file_name, "a") as f:
            json.dump(costs, f, indent=4)
