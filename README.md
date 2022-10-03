# Curve Gas Estimates

The gas estimator is a tool that aggregates statistics on gas consumption for each Curve pool contract on mainnet. These estimates are derived from Parity traces of every transaction where the contract emits an event. The final product is a json output file that has information on gas statistics (you can choose the modality of the gaussian statistics used here), as well as the number of transactions that make up the stats and the min and max block ranges where these gas stats are aggregated:

Since this repository is specialised to Curve Finance pools, there are two modalities of gas statistics:

1. Univariate: gas usage has a gaussian distribution
2. Mixed Gaussian / Bimodal: gas usage has a bimodal distribution, with each component its own gaussian model.

The reason for a bimodal gaussian distribution is because there are two gas consumption regimes in Curve Cryptoswap pools: one where the liquidity in the pool is positions very close to where the market is trading at, and one regime (consumes more gas) where the liquidity is further away.

Additionally there are a few debugging tools built in that fetch the trace of a transaction but only decode traces for a single contract (if you only care about one contract in a transaction, then the decoding is much faster).

This is a work in progress, but users can already get estimates for Curve contracts. Bear in mind that getting accurate gas statistics over several thousand transactions takes quite some time. Ideally the user should set the scripts up in a remote server with an Erigon archive node (with debug mode enabled: else you won't get the traces).

# Who should use the Gas Estimator?

If you are a Curve integrator, a DEX aggregator, a researcher/analyst, building at or on Curve, gas optimizoooor, or an MEV searcher who wants accurate gas estimates for their Curve swaps, then this is for you.

The scope of these gas estimates are isolated to mainnet, but the gas usage should be similar for similar contracts across other EVM chains.

The tool offers very simple stats at present. Should there be a need for more accurate modeling of gas usage, then please write an issue detailing your needs and its urgency. If you are a power user of this code and you think you can add a feature that you use on a daily basis to this repository, don't hesitate to submit a pull request from your forked repository.

# How can one use the gas estimator?

## Installation

Requirements:

1. ApeWorx
2. Erigon with Archive node and debug mode enabled

To install the scripts, you'll need python `>3.10.4`. Pyenv is recommended here. After cloning the repo:

```
python -m venv venv
source ./venv/bin/activate
pip install --upgrade pip
pip install -r ./requirements.txt
```

You will also need to set up your `ETHERSCAN_API_KEY` into your environment variables, so `ape-etherscan` can access it to get contract ABIs from Etherscan.

Finally, once you've set up your Erigon node, set up `ape-config.yaml` in the following manner:

```
ethereum:
  default_network: mainnet
  mainnet:
    default_provider: geth

geth:
  ethereum:
    mainnet:
      uri: http://localhost:{your-port-here}
```

## Fetch gas stats

### Single pool

```
> ape run gas_tools pools --max_transactions 1000 --pool_type stableswap --pool 0x4CA9b3063Ec5866A4B82E437059D2C43d1be596F
```

saved output file:

```
{
    "0x4CA9b3063Ec5866A4B82E437059D2C43d1be596F": {
        "univariate": {
            "exchange": {
                "mean": 130126,
                "std": 14684,
                "min": 85958,
                "max": 150079,
                "count": 536
            },
            "remove_liquidity_one_coin": {
                "mean": 129403,
                "std": 12454,
                "min": 101533,
                "max": 157163,
                "count": 226
            },
            "get_dy": {
                "mean": 23712,
                "std": 164,
                "min": 23226,
                "max": 23767,
                "count": 40
            },
            "add_liquidity": {
                "mean": 150148,
                "std": 20711,
                "min": 101980,
                "max": 204157,
                "count": 218
            },
            "get_virtual_price": {
                "mean": 10695,
                "std": 4809,
                "min": 8955,
                "max": 23455,
                "count": 25
            },
            "calc_withdraw_one_coin": {
                "mean": 42581,
                "std": 6196,
                "min": 38581,
                "max": 50581,
                "count": 6
            },
            "coins": {
                "mean": 3201,
                "std": 0,
                "min": 3201,
                "max": 3201,
                "count": 4
            },
            "remove_liquidity": {
                "mean": 142906,
                "std": 11471,
                "min": 119821,
                "max": 154021,
                "count": 20
            },
            "balances": {
                "mean": 1230,
                "std": 0,
                "min": 1230,
                "max": 1230,
                "count": 2
            },
            "ramp_A": {
                "mean": 25184,
                "std": 0,
                "min": 25184,
                "max": 25184,
                "count": 1
            },
            "remove_liquidity_imbalance": {
                "mean": 136085,
                "std": 9872,
                "min": 130385,
                "max": 147485,
                "count": 3
            }
        },
        "min_block": 13352648,
        "max_block": 15344943
    }
}
```

### Entire registries

the argument `pool` for `gas_tools` has three modes: `stableswap`, `cryptoswap` and `all`, which does both stableswap and cryptoswap pool gas estimates.

Set `max_transactions` to ensure that a maximum of `n` transactions are used in the gas stats: if the pool does not have `n` transactions, `gas_tool` will calculate stats on whatever it can find or whatever it thinks it needs. By default, the latest `n` transactions are chosen.

For stableswap:

```
ape run gas_tools pools --max_transactions 100 --pool_type stableswap
```

For cryptoswap:

```
ape run gas_tools pools --max_transactions 100 --pool_type cryptoswap
```

For both stableswap and cryptoswap:

```
ape run gas_tools pools --max_transactions 100 --pool_type all
```

If you want to get stats for a single stableswap or cryptoswap pool:

```
ape run gas_tools pools --max_transactions 100 --pool_type stableswap --pool 0x4CA9b3063Ec5866A4B82E437059D2C43d1be596F
```

By default all stableswap estimates are stored in `./stableswap_pool_gas_estimates.json` and the same for cryptoswap is `./cryptoswap_pool_gas_estimates.json`

### Debug tools

If you want to debug a transaction for a specific contract, use the argument `tx`:

```
ape run gas_tools tx --contractaddr 0x4CA9b3063Ec5866A4B82E437059D2C43d1be596F --tx 0xa57089bbd7a7a4e7b2fb52a5def3ebc7c3c9d8e5806272c8a216c93279f223ce
```

This will return a trace where only the pool contract is decoded. It will also provide average gas costs for each method called in the contract.

### Crypto Math tools

Scripts to fetch Crypto Math. This is specifically interesting for researchers looking into the mathematics of Cryptoswap (tricrypto2). To fetch `newton_y` and `newton_D` inputs and outputs, the cli prompt is:

```
ape run newton_math_tools tricrypto2 --max_transactions 10 --max_block 15537394
```

`max_block` is introduced for researchers who want to start their traversal from a specific block height (say, pre-merge txes). For debugging, the following command is useful:

```
ape run newton_math_tools tx --tx 0xd071cc29a2eede8162a476a4c301aa36bc5dc1f053da3440027a911429f8d08d
```

### License

(c) Curve.Fi, 2022 - All rights reserved.
