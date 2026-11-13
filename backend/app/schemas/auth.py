from pydantic import BaseModel, Field


class NonceRequest(BaseModel):
    address: str = Field(..., min_length=42, max_length=42)


class NonceResponse(BaseModel):
    address: str
    nonce: str
    message: str
    chain_id: int


class VerifyRequest(BaseModel):
    address: str = Field(..., min_length=42, max_length=42)
    message: str
    signature: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    role: str
    address: str
