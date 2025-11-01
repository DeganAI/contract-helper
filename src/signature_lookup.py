"""
Function Signature Lookup - 4byte.directory integration with caching
"""
import logging
import aiohttp
from typing import Optional, Dict, List
from functools import lru_cache

logger = logging.getLogger(__name__)


class SignatureLookup:
    """Look up function signatures from 4byte.directory"""

    # Common function signatures (cached)
    COMMON_SIGNATURES = {
        "0xa9059cbb": {
            "name": "transfer",
            "signature": "transfer(address,uint256)",
            "params": ["address recipient", "uint256 amount"]
        },
        "0x095ea7b3": {
            "name": "approve",
            "signature": "approve(address,uint256)",
            "params": ["address spender", "uint256 amount"]
        },
        "0x23b872dd": {
            "name": "transferFrom",
            "signature": "transferFrom(address,address,uint256)",
            "params": ["address sender", "address recipient", "uint256 amount"]
        },
        "0x70a08231": {
            "name": "balanceOf",
            "signature": "balanceOf(address)",
            "params": ["address account"]
        },
        "0x18160ddd": {
            "name": "totalSupply",
            "signature": "totalSupply()",
            "params": []
        },
        "0xdd62ed3e": {
            "name": "allowance",
            "signature": "allowance(address,address)",
            "params": ["address owner", "address spender"]
        },
        "0x313ce567": {
            "name": "decimals",
            "signature": "decimals()",
            "params": []
        },
        "0x06fdde03": {
            "name": "name",
            "signature": "name()",
            "params": []
        },
        "0x95d89b41": {
            "name": "symbol",
            "signature": "symbol()",
            "params": []
        },
        # Uniswap V2
        "0x7ff36ab5": {
            "name": "swapExactETHForTokens",
            "signature": "swapExactETHForTokens(uint256,address[],address,uint256)",
            "params": ["uint256 amountOutMin", "address[] path", "address to", "uint256 deadline"]
        },
        "0x38ed1739": {
            "name": "swapExactTokensForTokens",
            "signature": "swapExactTokensForTokens(uint256,uint256,address[],address,uint256)",
            "params": ["uint256 amountIn", "uint256 amountOutMin", "address[] path", "address to", "uint256 deadline"]
        },
        # Uniswap V3
        "0xc04b8d59": {
            "name": "exactInputSingle",
            "signature": "exactInputSingle((address,address,uint24,address,uint256,uint256,uint256,uint160))",
            "params": ["tuple params"]
        },
        # Multicall
        "0xac9650d8": {
            "name": "multicall",
            "signature": "multicall(bytes[])",
            "params": ["bytes[] data"]
        },
    }

    def __init__(self):
        self.api_url = "https://www.4byte.directory/api/v1/signatures/"
        self._cache = {}

    async def lookup_signature(self, function_selector: str) -> Optional[Dict]:
        """
        Look up function signature by 4-byte selector

        Args:
            function_selector: 4-byte hex selector (e.g., "0xa9059cbb")

        Returns:
            Dict with signature info or None
        """
        # Normalize selector
        selector = function_selector.lower()
        if not selector.startswith("0x"):
            selector = "0x" + selector

        # Check common signatures first
        if selector in self.COMMON_SIGNATURES:
            logger.info(f"Found {selector} in common signatures cache")
            return self.COMMON_SIGNATURES[selector]

        # Check local cache
        if selector in self._cache:
            logger.info(f"Found {selector} in lookup cache")
            return self._cache[selector]

        # Query 4byte.directory API
        try:
            async with aiohttp.ClientSession() as session:
                params = {"hex_signature": selector}
                async with session.get(
                    self.api_url,
                    params=params,
                    timeout=aiohttp.ClientTimeout(total=10)
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        if data.get("results"):
                            # Get most common result (first one)
                            result = data["results"][0]
                            signature_info = {
                                "name": self._extract_function_name(result["text_signature"]),
                                "signature": result["text_signature"],
                                "params": self._parse_parameters(result["text_signature"])
                            }

                            # Cache it
                            self._cache[selector] = signature_info
                            logger.info(f"Found {selector} via 4byte.directory: {signature_info['name']}")
                            return signature_info
        except Exception as e:
            logger.error(f"4byte.directory lookup failed for {selector}: {e}")

        logger.warning(f"Could not find signature for {selector}")
        return None

    def _extract_function_name(self, signature: str) -> str:
        """Extract function name from full signature"""
        if "(" in signature:
            return signature.split("(")[0]
        return signature

    def _parse_parameters(self, signature: str) -> List[str]:
        """Parse parameter types from signature"""
        if "(" not in signature or ")" not in signature:
            return []

        params_str = signature[signature.index("(") + 1:signature.rindex(")")]
        if not params_str:
            return []

        # Split by comma, handling nested tuples
        params = []
        depth = 0
        current = ""

        for char in params_str:
            if char == "," and depth == 0:
                if current:
                    params.append(current.strip())
                current = ""
            else:
                if char == "(":
                    depth += 1
                elif char == ")":
                    depth -= 1
                current += char

        if current:
            params.append(current.strip())

        return params

    @staticmethod
    def get_selector(function_signature: str) -> str:
        """
        Calculate function selector from signature

        Args:
            function_signature: e.g., "transfer(address,uint256)"

        Returns:
            4-byte hex selector
        """
        from eth_utils import keccak, to_hex

        # Remove spaces
        sig = function_signature.replace(" ", "")

        # Calculate keccak256
        hash_bytes = keccak(text=sig)

        # Take first 4 bytes
        selector = to_hex(hash_bytes[:4])

        return selector
