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


class ContractHelperRequest(BaseModel):
    """Unified contract helper request - accepts decode, encode, or lookup params"""
    # Decode params
    calldata: Optional[str] = Field(None, description="Hex-encoded calldata to decode")
    # Encode params
    function_signature: Optional[str] = Field(None, description="Function signature for encoding")
    parameters: Optional[List[Any]] = Field(None, description="Function parameters for encoding")
    # Lookup params
    selector: Optional[str] = Field(None, description="4-byte function selector to lookup")

    class Config:
        json_schema_extra = {
            "examples": [
                {"calldata": "0xa9059cbb000000000000000000000000742d35Cc6634C0532925a3b844Bc9e7595f0bEb00000000000000000000000000000000000000000000000000de0b6b3a7640000"},
                {"function_signature": "transfer(address,uint256)", "parameters": ["0x742d35Cc6634C0532925a3b844Bc9e7595f0bEb0", 1000000000000000000]},
                {"selector": "0xa9059cbb"}
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


@app.post("/entrypoints/contract-helper/invoke")
async def contract_helper_invoke(request: ContractHelperRequest):
    """
    Unified contract helper endpoint

    Automatically detects operation based on provided fields:
    - calldata: Decode transaction calldata
    - function_signature + parameters: Encode function call
    - selector: Lookup function signature
    """
    try:
        # Decode operation
        if request.calldata:
            logger.info(f"Decoding calldata: {request.calldata[:20]}...")
            result = await calldata_decoder.decode_calldata(request.calldata)
            return result

        # Encode operation
        elif request.function_signature and request.parameters is not None:
            logger.info(f"Encoding function: {request.function_signature}")
            result = function_encoder.encode_function_call(request.function_signature, request.parameters)
            if "error" in result:
                raise HTTPException(status_code=400, detail=result["error"])
            return result

        # Lookup operation
        elif request.selector:
            logger.info(f"Looking up selector: {request.selector}")
            result = await signature_lookup.lookup_signature(request.selector)
            if not result:
                raise HTTPException(status_code=404, detail=f"Signature not found for selector: {request.selector}")
            return result

        else:
            raise HTTPException(
                status_code=400,
                detail="Invalid request. Provide either: calldata (decode), function_signature+parameters (encode), or selector (lookup)"
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Contract helper error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Operation failed: {str(e)}")


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
            "contract-helper": {
                "description": "Decode calldata, encode function calls, and lookup signatures. Provide calldata (decode), function_signature+parameters (encode), or selector (lookup)",
                "streaming": False,
                "input_schema": {
                    "$schema": "https://json-schema.org/draft/2020-12/schema",
                    "type": "object",
                    "properties": {
                        "calldata": {"type": "string", "description": "Hex calldata to decode"},
                        "function_signature": {"type": "string", "description": "Function signature to encode"},
                        "parameters": {"type": "array", "description": "Parameters for encoding"},
                        "selector": {"type": "string", "description": "4-byte selector to lookup"}
                    }
                },
                "output_schema": {
                    "$schema": "https://json-schema.org/draft/2020-12/schema",
                    "type": "object"
                },
                "pricing": {"invoke": "0.02 USDC"}
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
                "resource": f"{base_url}/entrypoints/contract-helper/invoke",
                "description": "Decode calldata, encode function calls, and lookup signatures",
                "mimeType": "application/json",
                "payTo": payment_address,
                "maxTimeoutSeconds": 30,
                "asset": "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913",  # USDC on Base
            }
        ]
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=PORT)
