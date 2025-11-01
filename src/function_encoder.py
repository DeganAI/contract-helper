"""
Function Encoder - Build calldata from function signature and parameters
"""
import logging
from typing import Dict, List, Any
from eth_abi import encode
from eth_utils import keccak, to_hex

logger = logging.getLogger(__name__)


class FunctionEncoder:
    """Encode function calls into calldata"""

    def encode_function_call(
        self,
        function_signature: str,
        parameters: List[Any]
    ) -> Dict:
        """
        Encode function call into calldata

        Args:
            function_signature: e.g., "transfer(address,uint256)"
            parameters: List of parameter values

        Returns:
            Dict with calldata and metadata
        """
        try:
            # Calculate function selector
            selector = self._get_function_selector(function_signature)

            # Extract parameter types
            param_types = self._extract_param_types(function_signature)

            if len(parameters) != len(param_types):
                return {
                    "error": f"Parameter count mismatch: expected {len(param_types)}, got {len(parameters)}"
                }

            # Normalize parameters
            normalized_params = self._normalize_parameters(param_types, parameters)

            # Encode parameters
            encoded_params = encode(param_types, normalized_params)

            # Combine selector + encoded params
            calldata = selector + encoded_params.hex()

            return {
                "calldata": "0x" + calldata,
                "function_selector": "0x" + selector,
                "function_signature": function_signature,
                "parameters": parameters,
                "encoded": True
            }

        except Exception as e:
            logger.error(f"Function encoding failed: {e}")
            return {
                "error": f"Encoding failed: {str(e)}",
                "function_signature": function_signature,
                "parameters": parameters,
                "encoded": False
            }

    def _get_function_selector(self, function_signature: str) -> str:
        """Calculate 4-byte function selector"""
        # Remove spaces
        sig = function_signature.replace(" ", "")

        # Calculate keccak256
        hash_bytes = keccak(text=sig)

        # Take first 4 bytes
        return hash_bytes[:4].hex()

    def _extract_param_types(self, function_signature: str) -> List[str]:
        """Extract parameter types from signature"""
        if "(" not in function_signature or ")" not in function_signature:
            return []

        params_str = function_signature[
            function_signature.index("(") + 1:function_signature.rindex(")")
        ]

        if not params_str:
            return []

        # Split by comma, handling nested types
        types = []
        depth = 0
        current = ""

        for char in params_str:
            if char == "," and depth == 0:
                if current:
                    types.append(current.strip())
                current = ""
            else:
                if char in "([":
                    depth += 1
                elif char in ")]":
                    depth -= 1
                current += char

        if current:
            types.append(current.strip())

        return types

    def _normalize_parameters(
        self,
        param_types: List[str],
        parameters: List[Any]
    ) -> List[Any]:
        """Normalize parameters for encoding"""
        normalized = []

        for param_type, value in zip(param_types, parameters):
            # Address - ensure checksum format
            if param_type == "address":
                if isinstance(value, str):
                    # Remove 0x prefix if present
                    addr = value.lower().replace("0x", "")
                    # Pad to 20 bytes if needed
                    if len(addr) < 40:
                        addr = addr.zfill(40)
                    normalized.append("0x" + addr)
                else:
                    normalized.append(value)

            # Bytes - ensure hex format
            elif "bytes" in param_type:
                if isinstance(value, str):
                    # Remove 0x prefix if present
                    hex_val = value.replace("0x", "")
                    normalized.append(bytes.fromhex(hex_val))
                else:
                    normalized.append(value)

            # Uint/Int - ensure int type
            elif "uint" in param_type or "int" in param_type:
                normalized.append(int(value))

            # Bool
            elif param_type == "bool":
                normalized.append(bool(value))

            # String
            elif param_type == "string":
                normalized.append(str(value))

            # Array
            elif "[]" in param_type:
                if isinstance(value, list):
                    element_type = param_type.replace("[]", "")
                    normalized.append([
                        self._normalize_parameters([element_type], [v])[0]
                        for v in value
                    ])
                else:
                    normalized.append(value)

            # Default
            else:
                normalized.append(value)

        return normalized

    def build_erc20_transfer(self, to_address: str, amount: int) -> str:
        """Helper: Build ERC20 transfer calldata"""
        result = self.encode_function_call(
            "transfer(address,uint256)",
            [to_address, amount]
        )
        return result.get("calldata", "")

    def build_erc20_approve(self, spender_address: str, amount: int) -> str:
        """Helper: Build ERC20 approve calldata"""
        result = self.encode_function_call(
            "approve(address,uint256)",
            [spender_address, amount]
        )
        return result.get("calldata", "")

    def build_erc20_transfer_from(
        self,
        from_address: str,
        to_address: str,
        amount: int
    ) -> str:
        """Helper: Build ERC20 transferFrom calldata"""
        result = self.encode_function_call(
            "transferFrom(address,address,uint256)",
            [from_address, to_address, amount]
        )
        return result.get("calldata", "")
