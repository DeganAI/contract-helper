"""
Calldata Decoder - Decode transaction calldata into human-readable format
"""
import logging
from typing import Dict, List, Optional, Any
from eth_abi import decode
from eth_utils import to_hex

logger = logging.getLogger(__name__)


class CalldataDecoder:
    """Decode transaction calldata"""

    def __init__(self, signature_lookup):
        self.signature_lookup = signature_lookup

    async def decode_calldata(
        self,
        calldata: str,
        known_abi: Optional[List[Dict]] = None
    ) -> Dict:
        """
        Decode transaction calldata

        Args:
            calldata: Hex-encoded calldata (e.g., "0xa9059cbb000...")
            known_abi: Optional ABI if known

        Returns:
            Dict with decoded information
        """
        if not calldata or len(calldata) < 10:
            return {
                "error": "Invalid calldata - too short"
            }

        # Normalize
        if not calldata.startswith("0x"):
            calldata = "0x" + calldata

        # Extract function selector (first 4 bytes)
        function_selector = calldata[:10]
        params_data = calldata[10:]

        # Look up signature
        signature_info = await self.signature_lookup.lookup_signature(function_selector)

        if not signature_info:
            return {
                "function_selector": function_selector,
                "signature": "unknown",
                "raw_params": params_data,
                "decoded": False,
                "warning": "Function signature not found in database"
            }

        # Decode parameters
        try:
            decoded_params = self._decode_parameters(
                params_data,
                signature_info["params"]
            )

            return {
                "function_selector": function_selector,
                "function_name": signature_info["name"],
                "signature": signature_info["signature"],
                "parameters": decoded_params,
                "decoded": True,
                "human_readable": self._format_human_readable(
                    signature_info["name"],
                    decoded_params
                )
            }

        except Exception as e:
            logger.error(f"Failed to decode parameters: {e}")
            return {
                "function_selector": function_selector,
                "function_name": signature_info["name"],
                "signature": signature_info["signature"],
                "raw_params": params_data,
                "decoded": False,
                "error": f"Parameter decoding failed: {str(e)}"
            }

    def _decode_parameters(
        self,
        params_hex: str,
        param_types: List[str]
    ) -> List[Dict]:
        """Decode hex parameters using ABI types"""
        if not params_hex or not param_types:
            return []

        # Remove 0x if present
        if params_hex.startswith("0x"):
            params_hex = params_hex[2:]

        # Convert to bytes
        params_bytes = bytes.fromhex(params_hex)

        # Extract just the types (remove names if present)
        types_only = []
        for param in param_types:
            # Extract type (before space if name is present)
            if " " in param:
                type_part = param.split(" ")[0]
            else:
                type_part = param
            types_only.append(type_part)

        # Decode using eth_abi
        decoded_values = decode(types_only, params_bytes)

        # Build result with names and values
        result = []
        for i, (param, value) in enumerate(zip(param_types, decoded_values)):
            # Parse param name and type
            if " " in param:
                type_part, name_part = param.split(" ", 1)
            else:
                type_part = param
                name_part = f"param{i}"

            result.append({
                "name": name_part,
                "type": type_part,
                "value": self._format_value(type_part, value)
            })

        return result

    def _format_value(self, param_type: str, value: Any) -> Any:
        """Format decoded value for JSON serialization"""
        # Address
        if param_type == "address":
            if isinstance(value, bytes):
                return "0x" + value.hex()
            return value

        # Bytes
        if "bytes" in param_type:
            if isinstance(value, bytes):
                return "0x" + value.hex()
            return value

        # Array
        if "[]" in param_type:
            if isinstance(value, (list, tuple)):
                return [self._format_value(param_type.replace("[]", ""), v) for v in value]
            return value

        # Uint/int
        if "uint" in param_type or "int" in param_type:
            return int(value) if value is not None else 0

        # Bool
        if param_type == "bool":
            return bool(value)

        # String
        if param_type == "string":
            if isinstance(value, bytes):
                return value.decode("utf-8", errors="ignore")
            return str(value)

        # Default
        return value

    def _format_human_readable(
        self,
        function_name: str,
        parameters: List[Dict]
    ) -> str:
        """Format as human-readable description"""
        if not parameters:
            return f"{function_name}()"

        param_strs = []
        for param in parameters:
            value = param["value"]

            # Format based on type
            if param["type"] == "address":
                param_strs.append(f"{param['name']}={value}")
            elif "uint" in param["type"]:
                # Try to format large numbers
                if isinstance(value, int) and value > 1000000000000000000:
                    # Likely wei/gwei amount
                    eth_value = value / 10**18
                    param_strs.append(f"{param['name']}={eth_value:.6f} ({value} wei)")
                else:
                    param_strs.append(f"{param['name']}={value}")
            elif isinstance(value, list):
                param_strs.append(f"{param['name']}=[{len(value)} items]")
            else:
                param_strs.append(f"{param['name']}={value}")

        return f"{function_name}({', '.join(param_strs)})"
