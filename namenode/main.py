from fastapi import Depends, FastAPI, HTTPException, status

from namenode import auth
from namenode.schemas import Token, UserCreate, UserLogin

app = FastAPI(title="MiniHDFS NameNode")

_users: dict[str, str] = {}


@app.post("/auth/register", status_code=status.HTTP_201_CREATED)
def register(user: UserCreate) -> dict[str, str]:
    if user.username in _users:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username already registered",
        )
    _users[user.username] = auth.hash_password(user.password)
    return {"username": user.username, "message": "User registered successfully"}


@app.post("/auth/login", response_model=Token)
def login(credentials: UserLogin) -> Token:
    hashed = _users.get(credentials.username)
    if hashed is None or not auth.verify_password(credentials.password, hashed):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password",
        )
    token = auth.create_token(credentials.username)
    return Token(access_token=token)


@app.get("/auth/me")
def me(current_user: str = Depends(auth.get_current_user)) -> dict[str, str]:
    return {"username": current_user}
