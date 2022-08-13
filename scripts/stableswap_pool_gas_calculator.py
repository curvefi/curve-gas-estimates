import ape
import pandas

from eth_abi.exceptions import InsufficientDataBytes, DecodingError

from typing import List, Dict

from scripts.get_calltrace_from_tx import get_gas_cost_for_contract

import sys
from rich.console import Console as RichConsole


MAX_ZERO_TX_QUERIES = 10
RICH_CONSOLE = RichConsole(file=sys.stdout)


def __get_block_ranges(head: int, nblocks: int = 20000):
    return head - nblocks, head


def __get_transactions_in_block_range(
    pool: ape.Contract, block_start: int, block_end: int, logged_txes: List[str] = []
):

    tx_in_block = []
    for _, event in pool._events_.items():

        initialised_event = ape.contracts.ContractEvent(pool, event[0].abi)
        for log in initialised_event.range(block_start, block_end):
            tx = log.transaction_hash
            if tx not in logged_txes:
                tx_in_block.append(tx)

    txes = list(set(tx_in_block))
    RICH_CONSOLE.print(f"Found [red]{len(txes)} transactions.")
    return txes


def __compute_gas_costs_for_txes(pool: ape.Contract, txes: List[str]) -> Dict:

    RICH_CONSOLE.print("Fetching gas costs ...")
    gas_costs_for_pool = []
    for tx in txes:
        gas_costs_for_pool.append(get_gas_cost_for_contract(pool, tx))

    RICH_CONSOLE.print("... done!")
    df_gas_costs = pandas.DataFrame(gas_costs_for_pool)

    gas_table = (
        df_gas_costs.describe()
        .loc[["mean", "std", "min", "max"]]
        .fillna(0)
        .astype(int)
        .to_dict()
    )
    gas_table["count"] = len(txes)
    return gas_table


def _get_gas_table_for_stableswap_pool_in_block_range(
    pool: ape.Contract, block_start: int, block_end: int
) -> Dict:

    # get all transactions
    RICH_CONSOLE.print(
        f"Getting transactions for pool [red]{pool.address} in range [blue]{block_start} - [blue]{block_end} ..."
    )
    tx_in_block = __get_transactions_in_block_range(pool, block_start, block_end)
    if not tx_in_block:
        return {}

    return __compute_gas_costs_for_txes(pool, tx_in_block)


def _get_gas_table_for_stableswap_pool(
    pool: ape.Contract, min_transactions: int
) -> Dict:

    head = ape.chain.blocks.height
    block_start, block_end = __get_block_ranges(head)

    # get all transactions
    RICH_CONSOLE.print(f"Getting transactions for pool [red]{pool.address}.")
    zero_tx_queries = 0
    txes = []
    while len(txes) < min_transactions and zero_tx_queries < MAX_ZERO_TX_QUERIES:

        tx_in_block = __get_transactions_in_block_range(
            pool, block_start, block_end, txes
        )

        if len(tx_in_block) == 0:

            RICH_CONSOLE.print(
                f"no transactions found in [blue]{block_start} - [blue]{block_end} ..."
            )

            try:
                pool.A(block_identifier=block_end)
                zero_tx_queries += 1
            except ape.exceptions.SignatureError:
                # view method returns signature error which means ape cannot figure
                # out the method abi properly. so we will be a bit more lenient here
                block_start, block_end = __get_block_ranges(block_start)
                zero_tx_queries += 1  # we count it as a zero tx query
                continue
            except (InsufficientDataBytes, DecodingError) as e:
                RICH_CONSOLE.print(
                    f"[yellow]Skipping pool [red]{pool.address} since query is probably before pool creation block"
                )
                break

        txes = txes + tx_in_block
        RICH_CONSOLE.print(
            f"Found [blue]{len(tx_in_block)} txes between blocks [blue]{block_start}:[blue]{block_end}. Total: [blue]{len(txes)}"
        )
        block_start, block_end = __get_block_ranges(block_start)

    if len(txes) == 0:
        RICH_CONSOLE.print(
            f"No transactions found between blocks [blue]{block_start}:[blue]{head}. Moving on."
        )
        return {}

    return __compute_gas_costs_for_txes(pool, txes)
