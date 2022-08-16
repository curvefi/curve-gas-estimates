import ape
from rich.console import Console as RichConsole
import sys
from typing import List, Tuple

MAX_ZERO_TX_QUERIES = 1
RICH_CONSOLE = RichConsole(file=sys.stdout)


def get_block_ranges(end_block: int, nblocks: int = 1000000) -> Tuple[int, int]:
    return max(end_block - nblocks, 0), max(end_block, 0)


def get_transactions_in_block_range(
    pool: ape.Contract,
    block_start: int,
    block_end: int,
    logged_txes: List[Tuple[int, str]] = [],
) -> List[Tuple[int, str]]:

    tx_in_block = []
    for _, event in pool._events_.items():

        initialised_event = ape.contracts.ContractEvent(pool, event[0].abi)
        for log in initialised_event.range(block_start, block_end):
            tx = log.transaction_hash
            block_number = log.block_number
            if tx not in logged_txes:
                tx_in_block.append((block_number, tx))

    txes = list(set(tx_in_block))
    RICH_CONSOLE.log(f"Found [red]{len(txes)} transactions.")
    return txes


def get_all_transactions_for_contract(
    contract: ape.Contract, max_transactions: int
) -> List[Tuple[int, str]]:

    head = ape.chain.blocks.height
    block_start, block_end = get_block_ranges(head)

    RICH_CONSOLE.log(f"Getting transactions for contract [red]{contract.address}.")
    zero_tx_queries = 0
    txes = []
    while zero_tx_queries < MAX_ZERO_TX_QUERIES and len(txes) < max_transactions:

        if block_start == block_end:  # reached genesis
            RICH_CONSOLE("[yellow]Reached genesis.")
            break

        tx_in_block = get_transactions_in_block_range(
            contract, block_start, block_end, txes
        )

        if len(tx_in_block) == 0:

            RICH_CONSOLE.log(
                f"no transactions found in [blue]{block_start} - [blue]{block_end} ..."
            )

            try:
                # warning: this is a check that calls the `A` view method on curve contracts
                # if you want to use this method on other contracts, you will need to add
                # or replace the following contract call with something your contract or list
                # of contracts can call:
                contract.A(block_identifier=block_end)
                zero_tx_queries += 1
            except ape.exceptions.SignatureError:
                # view method returns signature error which means contract abi is rekt.
                # so we will be a bit more lenient here
                block_start, block_end = get_block_ranges(block_start)
                # we count it as a zero tx query else it will just keep searching and reverting until block = 0
                zero_tx_queries += 1
                continue
            except:  # catch all: it reverts most likely because pool didnt exist then
                break

        txes = txes + tx_in_block
        RICH_CONSOLE.log(f"Total transactions: [blue]{len(txes)}")
        block_start, block_end = get_block_ranges(block_start)

    return txes
