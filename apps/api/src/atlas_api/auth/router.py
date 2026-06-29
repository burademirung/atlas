from fastapi import APIRouter, Depends, Request, Response, status

from atlas_api.auth.schemas import LoginIn, RefreshIn, RegisterIn, TokenOut, UserOut
from atlas_api.auth.tokens import TokenService
from atlas_api.db.models import User
from atlas_api.deps import get_current_user, get_token_service, get_user_service
from atlas_api.errors import ProblemException
from atlas_api.users.service import DuplicateEmailError, UserService

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", status_code=status.HTTP_201_CREATED, response_model=UserOut)
async def register(body: RegisterIn, svc: UserService = Depends(get_user_service)) -> UserOut:
    try:
        user = await svc.register(body.email, body.password)
    except DuplicateEmailError as exc:
        raise ProblemException(409, "Email already registered") from exc
    return UserOut(id=user.id, email=user.email)


@router.post("/login", response_model=TokenOut)
async def login(
    body: LoginIn,
    svc: UserService = Depends(get_user_service),
    tokens: TokenService = Depends(get_token_service),
) -> TokenOut:
    user = await svc.authenticate(body.email, body.password)
    if user is None:
        raise ProblemException(401, "Invalid credentials")
    pair = tokens.issue_pair(user.id)
    return TokenOut(access_token=pair.access, refresh_token=pair.refresh)


@router.post("/refresh", response_model=TokenOut)
async def refresh(body: RefreshIn, tokens: TokenService = Depends(get_token_service)) -> TokenOut:
    pair = await tokens.rotate_refresh(body.refresh_token)
    return TokenOut(access_token=pair.access, refresh_token=pair.refresh)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    request: Request,
    _user: User = Depends(get_current_user),
    tokens: TokenService = Depends(get_token_service),
) -> Response:
    claims = tokens.decode(
        request.headers["Authorization"].removeprefix("Bearer "), expected_typ="access"
    )
    await tokens.revoke_access(claims.jti, request.app.state.settings.access_ttl_seconds)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
