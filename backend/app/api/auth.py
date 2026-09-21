"""Auth-facing routes."""

from fastapi import APIRouter

from app.auth.dependencies import AuthenticatedUser, CurrentUser

router = APIRouter(tags=["auth"])


@router.get("/me")
async def read_current_user(user: CurrentUser) -> AuthenticatedUser:
    """The verified caller.

    Depending on `CurrentUser` is what verifies the bearer token against
    Supabase Auth and provisions the caller's `public.users` row, so this is
    also the cheapest way to confirm that chain works end to end.
    """
    return user
