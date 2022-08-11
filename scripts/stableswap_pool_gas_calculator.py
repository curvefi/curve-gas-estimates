import ape
import pandas


from hexbytes import HexBytes

from eth_abi.exceptions import InsufficientDataBytes, DecodingError

from scripts.get_calltrace_from_tx import get_gas_cost_for_contract


MAX_ZERO_TX_QUERIES = 10


def __get_block_ranges(head: int, nblocks: int = 5000):
    return head - nblocks, head


def _get_gas_table_for_stableswap_pool(pool_addr: str, min_transactions: int):

    pool = ape.Contract(pool_addr)

    # get all transactions
    txes = []
    head = ape.chain.blocks.height
    block_start, block_end = __get_block_ranges(head)

    print(f"Getting transactions for pool {pool_addr}.")
    zero_tx_queries = 0
    while len(txes) < min_transactions and zero_tx_queries < MAX_ZERO_TX_QUERIES:

        tx_in_block = []
        for _, event in pool._events_.items():

            initialised_event = ape.contracts.ContractEvent(pool, event[0].abi)
            for log in initialised_event.range(block_start, block_end):
                tx = log.transaction_hash
                if tx not in txes:
                    tx_in_block.append(tx)

        if len(tx_in_block) == 0:

            try:
                pool.A(block_identifier=block_end)
                zero_tx_queries += 1
            except (InsufficientDataBytes, DecodingError) as e:
                print(
                    f"Skipping pool {pool_addr} since query is probably before pool creation block"
                )
                break

        txes = txes + tx_in_block
        print(
            f"Found {len(tx_in_block)} txes between blocks {block_start}:{block_end}. Total: {len(txes)}"
        )
        block_start, block_end = __get_block_ranges(block_start)

    if len(txes) == 0:
        print(f"No transactions found between blocks {block_start}:{head}. Moving on.")
        return {}

    # compute gas costs from aggregated txes
    txes = list(set(txes))
    print(f"Found {len(txes)} transactions. Fetching gas costs ...")

    gas_costs_for_pool = []
    for tx in txes:
        gas_costs_for_pool.append(get_gas_cost_for_contract(pool, tx))

    print("... done!")
    df_gas_costs = pandas.DataFrame(gas_costs_for_pool)

    gas_table = (
        df_gas_costs.describe()
        .loc[["mean", "std", "min", "max"]]
        .fillna(0)
        .astype(int)
        .to_dict()
    )

    return gas_table
