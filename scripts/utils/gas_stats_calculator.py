import ape
from evm_trace import CallTreeNode
import numpy
from pandas import DataFrame
from rich.console import Console as RichConsole
import sys
from sklearn.mixture import GaussianMixture
from typing import List, Dict

from .call_tree_parser import (
    attempt_decode_call_signature,
    get_calltree,
)


RICH_CONSOLE = RichConsole(file=sys.stdout)


def get_gas_cost_for_txes(pool: ape.Contract, txes: List[str]) -> DataFrame:

    RICH_CONSOLE.log("Fetching gas costs ...")
    gas_costs_for_pool = []
    for tx in txes:
        gas_costs = get_gas_cost_for_contract(pool, tx)
        if gas_costs:
            gas_costs_for_pool.append(gas_costs)

    return DataFrame(gas_costs_for_pool)


def compute_univariate_gaussian_gas_stats_for_txes(
    gas_costs_for_pool: DataFrame,
) -> Dict:

    RICH_CONSOLE.log("Computing univariate gas stats ...")

    gas_table = (
        gas_costs_for_pool.describe()
        .loc[["mean", "std", "min", "max", "count"]]
        .fillna(0)
        .astype(int)
        .to_dict()
    )
    return {"univariate": gas_table}


def compute_bimodal_gaussian_gas_stats_for_txes(gas_costs_for_pool: DataFrame) -> Dict:

    RICH_CONSOLE.log("Computing bimodal gaussian gas stats ...")

    gas_table = {}
    for method_name, gas_costs in gas_costs_for_pool.items():

        gas_costs = gas_costs.dropna().to_numpy().reshape(-1, 1)

        if gas_costs.shape[0] < 2:
            RICH_CONSOLE.log(
                f"Not enough txes to compute bimodal gaussian gas stats "
                f"for method: {method_name}. Skipping."
            )
            continue

        bimodal_model_fit = GaussianMixture(n_components=2).fit(gas_costs)

        # min, max:
        gas_table_method = {}
        gas_table_method["min"] = int(min(gas_costs)[0])
        gas_table_method["max"] = int(max(gas_costs)[0])

        # means:
        gas_table_method["mean_low"] = int(bimodal_model_fit.means_[0][0])
        gas_table_method["mean_high"] = int(bimodal_model_fit.means_[1][0])

        # standard deviations:
        covariances = bimodal_model_fit.covariances_
        std = [numpy.sqrt(numpy.trace(covariances[i]) / 2) for i in range(2)]
        gas_table_method["std_low"] = int(std[0])
        gas_table_method["std_high"] = int(std[1])
        gas_table_method["count"] = gas_costs.shape[0]

        gas_table[method_name] = gas_table_method

    return {"bimodal": gas_table}


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
    else:
        return {}
