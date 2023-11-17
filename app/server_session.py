import json
import os
import secrets
from datetime import timedelta
import logging

from itsdangerous import URLSafeSerializer
import redis


SECRET_KEY = os.getenv("SIGNATURE_SECRET_KEY")


class Server_Session:
    def __init__(self):
        self.r = redis.Redis(host='redis', port=6379)
        self.serializer = URLSafeSerializer(SECRET_KEY, salt="api")

    def add_duplicate_user_songs(self, spotify_id:str, songs):
        json_songs = json.dumps(songs)
        user_key = "user:" + spotify_id
        self.r.hset(user_key, "duplicate_songs", json_songs)
        return True

    def get_duplicate_user_songs(self, spotify_id:str):
        user_key = "user:" + spotify_id
        songs = json.loads(self.r.hget(user_key, "duplicate_songs"))
        return songs
    
    def is_cur_user_songs_cached(self, session_id: str) -> bool:
        spotify_id = self.get_spotify_id_from_session_id(session_id)
        user_key = "user:" + spotify_id
        return self.r.hexists(user_key, "duplicate_songs") if user_key else False


    def add_user_token(self, access_token: str, refresh_token: str, spotify_id: str) -> str:
        user_info = {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "spotify_id": spotify_id
        }

        user_id, signed_user_id = self.generate_ids()

        with self.r.pipeline() as pipe:
            pipe.hmset(user_id, user_info)
            pipe.expire(user_id, timedelta(hours=1))
            pipe.execute()

        return signed_user_id

    def update_user_token(
        self, session_id: str, access_token: str = None, refresh_token: str = None
    ) -> bool:
        original_id = self.deserialize_id(session_id)

        if not original_id:
            return False
        spotify_id = self.get_spotify_id_from_session_id(session_id)
        with self.r.pipeline() as pipe:
            if access_token:
                pipe.hset(original_id, "access_token", access_token)

            if refresh_token:
                pipe.hset(original_id, "refresh_token", refresh_token)
            
            pipe.hset(original_id, "spotify_id", spotify_id)

            pipe.expire(original_id, timedelta(hours=1))
            pipe.execute()

        return True

    def get_user_tokens(self, session_id: str) -> dict[str, str]:
        original_id = self.deserialize_id(session_id)

        if not original_id:
            return None

        try:
            access_token, refresh_token, spotify_id = self.r.hmget(
                original_id, "access_token", "refresh_token", "spotify_id"
            )
        except ValueError as e:
            print("No tokens found for given user id: " + str(e))
            return None

        return {
            "access_token": access_token.decode("ascii"),
            "refresh_token": refresh_token.decode("ascii"),
            "spotify_id": spotify_id.decode("ascii")
        }
    
    def get_spotify_id_from_session_id(self, session_id: str) -> str:
        user_tokens = self.get_user_tokens(session_id)
        return user_tokens["spotify_id"] if user_tokens else None


    def get_access_token(self, session_id: str) -> str:
        user_tokens = self.get_user_tokens(session_id)
        return user_tokens["access_token"] if user_tokens else None

    def get_refresh_token(self, session_id: str) -> str:
        user_tokens = self.get_user_tokens(session_id)
        return user_tokens["refresh_token"] if user_tokens else None

    def delete_user_token(self, session_id: str) -> bool:
        original_id = self.deserialize_id(session_id)

        if not original_id:
            return False

        self.r.hdel(original_id, "access_token", "refresh_token", "spotify_id")

        return True

    def token_exists(self, session_id: str) -> bool:
        original_id = self.deserialize_id(session_id)
        return self.r.exists(original_id) if original_id else False

    def generate_ids(self) -> tuple[str, str]:
        base_session_id = secrets.token_urlsafe(32)
        redis_session_id = "session:" + base_session_id
        signed_redis_session_id = self.serializer.dumps(redis_session_id)

        return redis_session_id, signed_redis_session_id

    def deserialize_id(self, signed_id: str) -> str:
        try:
            original_id = self.serializer.loads(signed_id)
        except Exception as e:
            print("Verification failed: " + e)
            return None

        return original_id
