import ape
from rich.console import Console as RichConsole
import sys
from typing import List

RICH_CONSOLE = RichConsole(file=sys.stdout)
REGISTRIES = {
    "MAIN_REGISTRY": "0x90E00ACe148ca3b23Ac1bC8C240C2a7Dd9c2d7f5",
    "STABLESWAP_FACTORY": "0xB9fC157394Af804a3578134A6585C0dc9cc990d4",
    "CRYPTOSWAP_REGISTRY": "0x8F942C20D02bEfc377D41445793068908E2250D0",
    "CRYPTOSWAP_FACTORY": "0xF18056Bbd320E96A48e3Fbf8bC061322531aac99",
}


def _get_pools(registry: str):
    pools = []
    registry = ape.Contract(registry)
    pool_count = registry.pool_count()
    for i in range(pool_count):
        pool = registry.pool_list(i)
        if pool not in pools:
            pools.append(pool)

    return pools


def get_stableswap_registry_pools() -> List[str]:
    RICH_CONSOLE.log("Getting all stableswap pools ...")
    pools = []
    for registry in [REGISTRIES["MAIN_REGISTRY"], REGISTRIES["STABLESWAP_FACTORY"]]:
        pools.extend(_get_pools(registry))
    pools = list(set(pools))
    RICH_CONSOLE.log(f"... found [red]{len(pools)} pools.")
    return pools


def get_cryptoswap_registry_pools() -> List[str]:
    RICH_CONSOLE.log("Getting all cryptoswap pools ...")
    pools = []
    for registry in [
        REGISTRIES["CRYPTOSWAP_REGISTRY"],
        REGISTRIES["CRYPTOSWAP_FACTORY"],
    ]:
        pools.extend(_get_pools(registry))
    pools = list(set(pools))
    RICH_CONSOLE.log(f"... found [red]{len(pools)} pools.")
    return pools
