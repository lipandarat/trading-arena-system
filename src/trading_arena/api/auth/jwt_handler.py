from datetime import datetime, timedelta, timezone
from typing import Dict, Optional
from jose import JWTError, jwt
from passlib.context import CryptContext
from trading_arena.config import config

class JWTHandler:
    def __init__(self):
        # FAIL FAST - Require secure secret key
        if not config.jwt_secret_key:
            if config.is_production:
                raise ValueError(
                    "PRODUCTION ERROR: JWT_SECRET_KEY must be set in production environment. "
                    "Using default secrets is not allowed in production."
                )
            else:
                raise ValueError(
                    "JWT_SECRET_KEY must be set. Run 'python scripts/validate_production.py' "
                    "to check your configuration for security issues."
                )
        self.secret_key = config.jwt_secret_key
        self.algorithm = "HS256"
        self.access_token_expire_minutes = 30
        self.pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

    def create_access_token(self, data: Dict, expires_delta: Optional[timedelta] = None):
        to_encode = data.copy()
        if expires_delta:
            expire = datetime.now(timezone.utc) + expires_delta
        else:
            expire = datetime.now(timezone.utc) + timedelta(minutes=self.access_token_expire_minutes)

        to_encode.update({"exp": expire})
        encoded_jwt = jwt.encode(to_encode, self.secret_key, algorithm=self.algorithm)
        return encoded_jwt

    def verify_token(self, token: str) -> Dict:
        try:
            payload = jwt.decode(token, self.secret_key, algorithms=[self.algorithm])
            return payload
        except JWTError as e:
            raise Exception(f"Invalid token: {e}")

    def hash_password(self, password: str) -> str:
        return self.pwd_context.hash(password)

    def verify_password(self, plain_password: str, hashed_password: str) -> bool:
        return self.pwd_context.verify(plain_password, hashed_password)