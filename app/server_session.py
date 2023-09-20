import os
import secrets
from datetime import timedelta

from dotenv import load_dotenv
from itsdangerous import URLSafeSerializer
import redis


load_dotenv()
SECRET_KEY = os.getenv("SIGNATURE_SECRET_KEY")


class Server_Session:
    def __init__(self):
        self.r = redis.Redis()
        self.serializer = URLSafeSerializer(SECRET_KEY, salt="api")

    def generate_ids(self):
        base_session_id = secrets.token_urlsafe(32)
        redis_session_id = "user" + base_session_id
        signed_redis_session_id = self.serializer.dumps(redis_session_id)

        return redis_session_id, signed_redis_session_id

    def add_user_token(self, access_token: str, refresh_token: str) -> str:
        user_info = {
            "access_token": access_token,
            "refresh_token": refresh_token,
        }

        user_id, signed_user_id = self.generate_ids()

        with self.r.pipeline() as pipe:
            pipe.hmset(user_id, user_info)
            pipe.expire(user_id, timedelta(hours=1))
            pipe.execute()

        return signed_user_id

    def update_user_token(
        self, session_id: str, access_token: str = None, refresh_token: str = None
    ):
        original_id = self.deserialize_id(session_id)

        if not original_id:
            return False

        with self.r.pipeline() as pipe:
            if access_token:
                pipe.hset(original_id, "access_token", access_token)

            if refresh_token:
                pipe.hset(original_id, "refresh_token", refresh_token)
            pipe.expire(original_id, timedelta(hours=1))
            pipe.execute()

        return True

    def get_user_tokens(self, session_id):
        original_id = self.deserialize_id(session_id)

        if not original_id:
            return None

        try:
            access_token, refresh_token = self.r.hmget(
                original_id, "access_token", "refresh_token"
            )
        except ValueError as e:
            print("No tokens found for given user id: " + str(e))
            return None, None

        return {
            "access_token": access_token.decode("ascii"),
            "refresh_token": refresh_token.decode("ascii"),
        }

    def get_access_token(self, session_id):
        return self.get_user_tokens(session_id)["access_token"]

    def get_refresh_token(self, session_id):
        return self.get_user_tokens(session_id)["refresh_token"]

    def delete_user_token(self, session_id):
        try:
            original_id = self.serializer.loads(session_id)
        except Exception as e:
            print("Verification failed: " + e)
            return False

        self.r.hdel(original_id, "access_token", "refresh_token")

        return True

    def token_exists(self, session_id):
        original_id = self.deserialize_id(session_id)
        return self.r.exists(original_id) if original_id else False

    def deserialize_id(self, signed_id):
        try:
            original_id = self.serializer.loads(signed_id)
        except Exception as e:
            print("Verification failed: " + e)
            return None

        return original_id
