import os
import requests
from typing import Optional, List
from agno.tools import Toolkit
from agno.utils.log import logger


class BlockscoutTools(Toolkit):
    CHAIN_URLS = {
        "ethereum": os.getenv("BLOCKSCOUT_ETHEREUM_URL", "https://blockscout.com/eth/mainnet/api"),
        "polygon": os.getenv("BLOCKSCOUT_POLYGON_URL", "https://polygon.blockscout.com/api"),
        "ethereum_classic": os.getenv("BLOCKSCOUT_ETC_URL", "https://blockscout.com/etc/mainnet/api"),
        "base": os.getenv("BLOCKSCOUT_BASE_URL", "https://base.blockscout.com/api"),
        "optimism": os.getenv("BLOCKSCOUT_OPTIMISM_URL", "https://optimism.blockscout.com/api"),
    }

    def __init__(self):
        super().__init__(name="blockscout_tools")
        self.api_key = os.getenv("BLOCKSCOUT_API_KEY", "")  # Optional

        self.headers = {
            "Accept": "application/json"
        }

        self.register(self.get_eth_balance)
        self.register(self.get_tx_history)
        self.register(self.get_token_balance)
        self.register(self.get_contract_info)

    def get_base_url(self, chain: str) -> Optional[str]:
        return self.CHAIN_URLS.get(chain.lower())

    def get_eth_balance(self, address: str, chain: str = "ethereum") -> str:
        base_url = self.get_base_url(chain)
        if not base_url:
            return f"Unsupported chain: {chain}"
        url = f"{base_url}?module=account&action=balance&address={address}&tag=latest&apikey={self.api_key}"
        try:
            response = requests.get(url, headers=self.headers)
            response.raise_for_status()
            result = response.json()
            if result["status"] != "1":
                return f"Error fetching balance: {result.get('message', 'Unknown error')}"
            balance_wei = int(result["result"])
            balance_eth = balance_wei / 1e18
            return f"{chain.replace('_', ' ').title()} balance for {address}: {balance_eth:,.6f}"
        except Exception as e:
            logger.error(f"ETH Balance error on {chain}: {e}")
            return f"Error fetching ETH balance: {e}"

    def get_tx_history(self, address: str, chain: str = "ethereum", limit: int = 5) -> str:
        base_url = self.get_base_url(chain)
        if not base_url:
            return f"Unsupported chain: {chain}"
        url = f"{base_url}?module=account&action=txlist&address={address}&sort=desc&apikey={self.api_key}"
        try:
            response = requests.get(url, headers=self.headers)
            response.raise_for_status()
            result = response.json()
            if result["status"] != "1":
                return f"Error fetching transactions: {result.get('message', 'Unknown error')}"
            txs = result["result"][:limit]
            output = f"Recent {limit} transactions on {chain.replace('_', ' ').title()} for {address}:\n"
            for tx in txs:
                eth = int(tx['value']) / 1e18
                output += f"- Hash: {tx['hash'][:10]}... | From: {tx['from']} | To: {tx['to']} | Value: {eth:.6f}\n"
            return output
        except Exception as e:
            logger.error(f"Transaction history error on {chain}: {e}")
            return f"Error fetching transactions: {e}"

    def get_token_balance(self, address: str, contract_address: str, chain: str = "ethereum") -> str:
        base_url = self.get_base_url(chain)
        if not base_url:
            return f"Unsupported chain: {chain}"
        url = f"{base_url}?module=account&action=tokenbalance&contractaddress={contract_address}&address={address}&tag=latest&apikey={self.api_key}"
        try:
            response = requests.get(url, headers=self.headers)
            response.raise_for_status()
            result = response.json()
            if result["status"] != "1":
                return f"Error: {result.get('message', 'Could not fetch token balance.')}"
            raw_balance = int(result["result"])
            return f"Token balance for {address} on {chain.replace('_', ' ').title()} (contract {contract_address}): {raw_balance} units"
        except Exception as e:
            logger.error(f"Token balance error on {chain}: {e}")
            return f"Error fetching token balance: {e}"

    def get_contract_info(self, contract_address: str, chain: str = "ethereum") -> str:
        base_url = self.get_base_url(chain)
        if not base_url:
            return f"Unsupported chain: {chain}"
        url = f"{base_url}?module=contract&action=getsourcecode&address={contract_address}&apikey={self.api_key}"
        try:
            response = requests.get(url, headers=self.headers)
            response.raise_for_status()
            result = response.json()
            if result["status"] != "1" or not result["result"]:
                return f"Contract info for {contract_address} on {chain} not found or not verified."
            contract = result["result"][0]
            name = contract.get("ContractName", "Unknown")
            compiler = contract.get("CompilerVersion", "Unknown")
            return f"Contract {name} at {contract_address} on {chain.replace('_', ' ').title()} (compiled with {compiler}) is {'verified' if contract.get('ABI') else 'unverified'}."
        except Exception as e:
            logger.error(f"Contract info error on {chain}: {e}")
            return f"Error fetching contract info: {e}"
