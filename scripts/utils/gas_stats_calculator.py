import ape
from evm_trace import CallTreeNode
from pandas import DataFrame
from rich.console import Console as RichConsole
import sys
from typing import List, Dict

from .call_tree_parser import (
    attempt_decode_call_signature,
    get_calltree,
)


RICH_CONSOLE = RichConsole(file=sys.stdout)


def compute_univariate_gaussian_gas_stats_for_txes(
    pool: ape.Contract, txes: List[str]
) -> Dict:

    RICH_CONSOLE.log("Fetching gas costs ...")
    gas_costs_for_pool = []
    for tx in txes:
        gas_costs = get_gas_cost_for_contract(pool, tx)
        if gas_costs:
            gas_costs_for_pool.append(gas_costs)

    RICH_CONSOLE.log("... done!")
    df_gas_costs = DataFrame(gas_costs_for_pool)

    gas_table = (
        df_gas_costs.describe()
        .loc[["mean", "std", "min", "max"]]
        .fillna(0)
        .astype(int)
        .to_dict()
    )
    gas_table = {"univariate": gas_table}
    gas_table["count"] = len(txes)

    return gas_table


def get_avg_gas_cost_per_method_for_tx(
    contract: ape.Contract,
    tree: CallTreeNode,
) -> Dict[str, int]:

    call_costs = {}
    for call in tree.display_nodes:

        if call.info.address.lower() != contract.address.lower():
            continue

        # ensure calldata is not empty
        if call.info.method_id == "0x":
            continue

        # decode call signature
        method_name = attempt_decode_call_signature(contract, call.info.method_id)

        if call.info.method_id not in call_costs.keys():
            call_costs[method_name] = [call.info.gas_cost]
            continue

        call_costs[method_name].append(call.info.gas_cost)

    # average gas cost per method
    # warning: this is data compression!!! we only keep the average!
    for method_name, costs in call_costs.items():
        costs = [i for i in costs if i is not None]
        if costs:
            call_costs[method_name] = sum(costs) // len(costs)

    return call_costs


def get_gas_cost_for_contract(contract: ape.Contract, tx_hash: str) -> Dict[str, int]:

    call_tree = get_calltree(tx_hash=tx_hash)
    if call_tree:
        try:
            agg_gas_costs = get_avg_gas_cost_per_method_for_tx(contract, call_tree)
            return agg_gas_costs
        except:
            RICH_CONSOLE.log(
                f"[yellow]Could not get gas cost for contract [red]{contract} at tx [red]{tx_hash}."
            )
            RICH_CONSOLE.print_exception()
            return {}
