"""
Smart Contract Interaction Helper - Decode and encode contract calls

x402-enabled microservice for contract interaction
"""
import logging
import os
from typing import List, Optional, Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from dotenv import load_dotenv

from .signature_lookup import SignatureLookup
from .calldata_decoder import CalldataDecoder
from .function_encoder import FunctionEncoder
from .x402_middleware_dual import X402Middleware

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Initialize FastAPI
app = FastAPI(
    title="Smart Contract Interaction Helper",
    description="Decode and encode smart contract function calls with signature lookup",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Configuration
FREE_MODE = os.getenv("FREE_MODE", "true").lower() == "true"
PAYMENT_ADDRESS = os.getenv("PAYMENT_ADDRESS", "0x01D11F7e1a46AbFC6092d7be484895D2d505095c")
PORT = int(os.getenv("PORT", "8000"))
BASE_URL = os.getenv("BASE_URL", f"http://localhost:{PORT}")

# Initialize services
signature_lookup = SignatureLookup()
calldata_decoder = CalldataDecoder(signature_lookup)
function_encoder = FunctionEncoder()

if FREE_MODE:
    logger.warning("Running in FREE MODE - no payment verification")
else:
    logger.info("x402 payment verification enabled")

logger.info("Contract Helper initialized")
logger.info(f"PORT from environment: {PORT}")
logger.info(f"BASE_URL: {BASE_URL}")

# x402 Payment Middleware
payment_address = PAYMENT_ADDRESS
base_url = BASE_URL.rstrip('/')

app.add_middleware(
    X402Middleware,
    payment_address=payment_address,
    base_url=base_url,
    facilitator_urls=[
        "https://facilitator.daydreams.systems",
        "https://api.cdp.coinbase.com/platform/v2/x402/facilitator"
    ],
    free_mode=FREE_MODE,
)


# Request/Response Models
class DecodeRequest(BaseModel):
    """Decode calldata request"""
    calldata: str = Field(..., description="Hex-encoded calldata to decode")

    class Config:
        json_schema_extra = {
            "example": {
                "calldata": "0xa9059cbb000000000000000000000000742d35Cc6634C0532925a3b844Bc9e7595f0bEb00000000000000000000000000000000000000000000000000de0b6b3a7640000"
            }
        }


class EncodeRequest(BaseModel):
    """Encode function call request"""
    function_signature: str = Field(..., description="Function signature (e.g., 'transfer(address,uint256)')")
    parameters: List[Any] = Field(..., description="Function parameters in order")

    class Config:
        json_schema_extra = {
            "example": {
                "function_signature": "transfer(address,uint256)",
                "parameters": ["0x742d35Cc6634C0532925a3b844Bc9e7595f0bEb0", 1000000000000000000]
            }
        }


class SignatureLookupRequest(BaseModel):
    """Signature lookup request"""
    selector: str = Field(..., description="4-byte function selector (e.g., '0xa9059cbb')")

    class Config:
        json_schema_extra = {
            "example": {
                "selector": "0xa9059cbb"
            }
        }


class InvokeRequest(BaseModel):
    """Unified invoke request"""
    action: str = Field(..., description="Action to perform: 'decode', 'encode', or 'lookup'")
    calldata: Optional[str] = Field(None, description="For decode: hex-encoded calldata")
    function_signature: Optional[str] = Field(None, description="For encode: function signature")
    parameters: Optional[List[Any]] = Field(None, description="For encode: function parameters")
    selector: Optional[str] = Field(None, description="For lookup: 4-byte function selector")

    class Config:
        json_schema_extra = {
            "examples": [
                {
                    "action": "decode",
                    "calldata": "0xa9059cbb000000000000000000000000742d35Cc6634C0532925a3b844Bc9e7595f0bEb00000000000000000000000000000000000000000000000000de0b6b3a7640000"
                },
                {
                    "action": "encode",
                    "function_signature": "transfer(address,uint256)",
                    "parameters": ["0x742d35Cc6634C0532925a3b844Bc9e7595f0bEb0", 1000000000000000000]
                },
                {
                    "action": "lookup",
                    "selector": "0xa9059cbb"
                }
            ]
        }


# API Endpoints
@app.get("/health")
async def health():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "service": "contract-helper",
        "version": "1.0.0",
        "free_mode": FREE_MODE
    }


@app.post(
    "/entrypoints/decode/invoke",
    summary="Decode Transaction Calldata",
    description="Decode transaction calldata into human-readable format with parameter extraction"
)
async def decode_calldata(request: DecodeRequest):
    """
    Decode transaction calldata

    This endpoint:
    - Extracts function selector
    - Looks up function signature from 4byte.directory
    - Decodes parameters using ABI encoding
    - Returns human-readable description

    Returns:
    - Function name and signature
    - Decoded parameters with names and types
    - Human-readable description
    - Raw data if decoding fails

    Useful for:
    - Understanding what a transaction does
    - Debugging contract interactions
    - Analyzing on-chain activity
    - Building transaction explorers
    """
    try:
        logger.info(f"Decoding calldata: {request.calldata[:20]}...")

        result = await calldata_decoder.decode_calldata(request.calldata)

        return result

    except Exception as e:
        logger.error(f"Decode error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Decode failed: {str(e)}")


@app.post(
    "/entrypoints/encode/invoke",
    summary="Encode Function Call",
    description="Encode function call into calldata from signature and parameters"
)
async def encode_function(request: EncodeRequest):
    """
    Encode function call into calldata

    This endpoint:
    - Calculates function selector from signature
    - Encodes parameters using ABI encoding
    - Returns complete calldata ready for transaction

    Returns:
    - Complete calldata (selector + encoded params)
    - Function selector
    - Encoding metadata

    Useful for:
    - Building contract transactions
    - Creating multicalls
    - Batch operations
    - Testing contract interactions
    """
    try:
        logger.info(f"Encoding function: {request.function_signature}")

        result = function_encoder.encode_function_call(
            request.function_signature,
            request.parameters
        )

        if "error" in result:
            raise HTTPException(status_code=400, detail=result["error"])

        return result

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Encode error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Encode failed: {str(e)}")


@app.post(
    "/entrypoints/lookup/invoke",
    summary="Lookup Function Signature",
    description="Look up function signature by 4-byte selector"
)
async def lookup_signature(request: SignatureLookupRequest):
    """
    Look up function signature by selector

    This endpoint:
    - Queries 4byte.directory database
    - Returns function signature and parameter types
    - Includes common function cache for speed

    Returns:
    - Function name
    - Full signature
    - Parameter types

    Useful for:
    - Understanding unknown function selectors
    - Contract reverse engineering
    - Transaction analysis
    - Building decoders
    """
    try:
        logger.info(f"Looking up selector: {request.selector}")

        result = await signature_lookup.lookup_signature(request.selector)

        if not result:
            raise HTTPException(
                status_code=404,
                detail=f"Signature not found for selector: {request.selector}"
            )

        return result

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Lookup error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Lookup failed: {str(e)}")


# Agent Discovery Endpoints
@app.get("/.well-known/agent.json")
async def agent_metadata():
    """Agent metadata for service discovery"""
    return {
        "name": "Smart Contract Interaction Helper",
        "description": "Decode and encode smart contract function calls with automatic signature lookup from 4byte.directory. Perfect for understanding transactions, building contract calls, and analyzing on-chain activity.",
        "url": f"{base_url}/",
        "version": "1.0.0",
        "capabilities": {
            "streaming": False,
            "pushNotifications": False,
            "stateTransitionHistory": True,
            "extensions": [
                {
                    "uri": "https://github.com/google-agentic-commerce/ap2/tree/v0.1",
                    "description": "Agent Payments Protocol (AP2)",
                    "required": True,
                    "params": {"roles": ["merchant"]}
                }
            ]
        },
        "defaultInputModes": ["application/json"],
        "defaultOutputModes": ["application/json"],
        "entrypoints": {
            "decode": {
                "description": "Decode transaction calldata into human-readable format",
                "streaming": False,
                "input_schema": {
                    "$schema": "https://json-schema.org/draft/2020-12/schema",
                    "type": "object",
                    "properties": {
                        "calldata": {"type": "string"}
                    },
                    "required": ["calldata"]
                },
                "output_schema": {
                    "$schema": "https://json-schema.org/draft/2020-12/schema",
                    "type": "object",
                    "properties": {
                        "function_name": {"type": "string"},
                        "signature": {"type": "string"},
                        "parameters": {"type": "array"},
                        "human_readable": {"type": "string"}
                    }
                },
                "pricing": {"invoke": "0.02 USDC"}
            },
            "encode": {
                "description": "Encode function call from signature and parameters",
                "streaming": False,
                "input_schema": {
                    "$schema": "https://json-schema.org/draft/2020-12/schema",
                    "type": "object",
                    "properties": {
                        "function_signature": {"type": "string"},
                        "parameters": {"type": "array"}
                    },
                    "required": ["function_signature", "parameters"]
                },
                "output_schema": {
                    "$schema": "https://json-schema.org/draft/2020-12/schema",
                    "type": "object",
                    "properties": {
                        "calldata": {"type": "string"},
                        "function_selector": {"type": "string"}
                    }
                },
                "pricing": {"invoke": "0.02 USDC"}
            },
            "lookup": {
                "description": "Look up function signature by selector",
                "streaming": False,
                "input_schema": {
                    "$schema": "https://json-schema.org/draft/2020-12/schema",
                    "type": "object",
                    "properties": {
                        "selector": {"type": "string"}
                    },
                    "required": ["selector"]
                },
                "output_schema": {
                    "$schema": "https://json-schema.org/draft/2020-12/schema",
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                        "signature": {"type": "string"},
                        "params": {"type": "array"}
                    }
                },
                "pricing": {"invoke": "0.01 USDC"}
            }
        },
        "payments": [
            {
                "method": "x402",
                "payee": payment_address,
                "network": "base",
                "endpoint": "https://facilitator.daydreams.systems",
                "priceModel": {"default": "0.02"},
                "extensions": {
                    "x402": {"facilitatorUrl": "https://facilitator.daydreams.systems"}
                }
            }
        ]
    }


@app.get("/.well-known/x402")
async def x402_metadata():
    """x402 payment metadata"""
    return {
        "x402Version": 1,
        "accepts": [
            {
                "scheme": "exact",
                "network": "base",
                "maxAmountRequired": "20000",  # 0.02 USDC
                "resource": f"{base_url}/entrypoints/decode/invoke",
                "description": "Decode transaction calldata with signature lookup and parameter extraction",
                "mimeType": "application/json",
                "payTo": payment_address,
                "maxTimeoutSeconds": 30,
                "asset": "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913",  # USDC on Base
            },
            {
                "scheme": "exact",
                "network": "base",
                "maxAmountRequired": "20000",  # 0.02 USDC
                "resource": f"{base_url}/entrypoints/encode/invoke",
                "description": "Encode function call from signature and parameters",
                "mimeType": "application/json",
                "payTo": payment_address,
                "maxTimeoutSeconds": 30,
                "asset": "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913",
            },
            {
                "scheme": "exact",
                "network": "base",
                "maxAmountRequired": "10000",  # 0.01 USDC
                "resource": f"{base_url}/entrypoints/lookup/invoke",
                "description": "Look up function signature by 4-byte selector",
                "mimeType": "application/json",
                "payTo": payment_address,
                "maxTimeoutSeconds": 30,
                "asset": "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913",
            }
        ]
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=PORT)
