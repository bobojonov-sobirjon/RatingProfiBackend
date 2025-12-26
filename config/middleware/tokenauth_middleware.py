from channels.middleware import BaseMiddleware
from rest_framework_simplejwt.authentication import JWTAuthentication
from channels.db import database_sync_to_async
from channels.sessions import SessionMiddleware
from django.contrib.auth.models import AnonymousUser
from django.contrib.sessions.models import Session
import jwt
from urllib.parse import parse_qs


@database_sync_to_async
def get_user_from_jwt(token_key):
    try:
        jwt_auth = JWTAuthentication()
        validated_token = jwt_auth.get_validated_token(token_key)
        user = jwt_auth.get_user(validated_token)
        return user
    except jwt.ExpiredSignatureError:
        return AnonymousUser()
    except jwt.InvalidTokenError:
        return AnonymousUser()


@database_sync_to_async
def get_user_from_session(session_key):
    """
    Get user from Django session (for admin panel)
    """
    try:
        session = Session.objects.get(session_key=session_key)
        user_id = session.get_decoded().get('_auth_user_id')
        if user_id:
            from django.contrib.auth import get_user_model
            User = get_user_model()
            return User.objects.get(id=user_id)
    except (Session.DoesNotExist, KeyError, ValueError):
        pass
    return AnonymousUser()


class TokenAuthMiddleware(BaseMiddleware):
    def __init__(self, inner):
        super().__init__(inner)

    async def __call__(self, scope, receive, send):
        token_key = None
        
        # First, try to get token from query string
        query_string = parse_qs(scope.get("query_string", b"").decode())
        token_key = query_string.get("token", [None])[0]
        
        # If not in query string, try to extract from URL path
        # Path might be like /ws/chat/1/TOKEN or /ws/chat/1/token=TOKEN
        # Or /ws/notifications/TOKEN or /ws/notifications/token=TOKEN
        if not token_key:
            path = scope.get("path", "")
            path_parts = [p for p in path.split("/") if p]  # Remove empty strings
            
            # Check if path has format: /ws/chat/1/TOKEN or /ws/chat/1/token=TOKEN
            if len(path_parts) >= 4 and path_parts[0] == "ws" and path_parts[1] == "chat":
                # conversation_id is at index 2, token is at index 3
                if len(path_parts) > 3:
                    potential_token = path_parts[3]
                    # Check if it's in format "token=TOKEN"
                    if potential_token.startswith("token="):
                        token_key = potential_token[6:]  # Remove "token=" prefix
                    # Check if it looks like a JWT token (contains dots and is long enough)
                    elif "." in potential_token and len(potential_token) > 50:
                        token_key = potential_token
            
            # Check if path has format: /ws/notifications/TOKEN or /ws/notifications/token=TOKEN
            elif len(path_parts) >= 3 and path_parts[0] == "ws" and path_parts[1] == "notifications":
                # token is at index 2
                if len(path_parts) > 2:
                    potential_token = path_parts[2]
                    # Check if it's in format "token=TOKEN"
                    if potential_token.startswith("token="):
                        token_key = potential_token[6:]  # Remove "token=" prefix
                    # Check if it looks like a JWT token (contains dots and is long enough)
                    elif "." in potential_token and len(potential_token) > 50:
                        token_key = potential_token
        
        if token_key:
            # Use JWT authentication
            try:
                scope["user"] = await get_user_from_jwt(token_key)
            except Exception as e:
                # If token is invalid/expired, fall back to anonymous user
                # This allows connection to continue (consumer will handle rejection)
                print(f"JWT token validation failed: {e}")
                scope["user"] = AnonymousUser()
        else:
            # For admin panel, AuthMiddlewareStack has already set user from session
            # If user is not in scope yet, it means session auth failed
            # In this case, we keep the user as is (AuthMiddlewareStack will set it)
            if "user" not in scope:
                scope["user"] = AnonymousUser()
        
        return await super().__call__(scope, receive, send)
