import collections
import requests

import os
from dotenv import load_dotenv

load_dotenv()

CLIENT_ID = os.getenv("CLIENT_ID")
CLIENT_SECRET = os.getenv("CLIENT_SECRET")
SPOTIFY_REDIRECT_URI = os.getenv("REDIRECT_URI")
REDIRECT_URI = "http://localhost:5000/callback"

AUTH_URL = "https://accounts.spotify.com/authorize"
TOKEN_URL = "https://accounts.spotify.com/api/token"
ME_URL = "https://api.spotify.com/v1/me"


URLs = {
    "base": "https://api.spotify.com/v1{endpoint}",
    "playlists": "/playlists",
    "me": "/me",
    "auth": "https://accounts.spotify.com/authorize",
    "token": "https://accounts.spotify.com/api/token",
}


class Spotify_Client:
    def __init__(self):
        self.api_url = "something"

    def get_tokens(self, code):
        payload = {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": REDIRECT_URI,
        }

        res = self.post(TOKEN_URL, data=payload)
        if res.get("error"):
            print(
                "Failed to receive token: %s",
                res.get("error", "No error information received."),
            )
            return None
        return {
            "access_token": res.get("access_token"),
            "refresh_token": res.get("refresh_token"),
        }

    def refresh_access_token(self, refresh_token):
        payload = {
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
        }
        headers = {"Content-Type": "application/x-www-form-urlencoded"}

        refresh_data = self.post(URLs["token"], data=payload, headers=headers)

        return refresh_data.get("access_token")

    def me(self, access_token):
        return self.get(
            access_token=access_token, url=URLs["base"].format(endpoint=URLs["me"])
        )

    def get_full_playlist_data(self, access_token):
        full_data = []
        res_data = {
            "next": URLs["base"].format(endpoint=URLs["me"] + URLs["playlists"])
        }

        while res_data["next"]:
            res_data = self.get(access_token=access_token, url=res_data["next"])
            for item in res_data["items"]:
                full_data.append([item["name"], item["tracks"], item["description"]])
        return full_data

    def get_songs_in_playlists(self, access_token):
        playlists = filter_playlists(self.get_full_playlist_data(access_token))
        playlists_per_song = collections.defaultdict(list)
        for name, link_to_playlist in playlists.items():
            song_res = {"next": link_to_playlist}
            while song_res["next"]:
                song_res = self.get(access_token, song_res["next"])

                for item in song_res["items"]:
                    playlists_per_song[
                        (item["track"]["name"], item["track"]["artists"][0]["name"])
                    ].append(name)

        return (playlists, playlists_per_song)

    def get_song(self, access_token, song_link):
        return self.get(access_token, song_link)

    def get(self, access_token, url, params={}):
        req_headers = {"Authorization": f"Bearer {access_token}"}

        res = requests.get(url, headers=req_headers)
        res_data = res.json()

        return res_data

    def post(self, url, data={}, headers={}):
        res = requests.post(
            url, auth=(CLIENT_ID, CLIENT_SECRET), data=data, headers=headers
        )
        res_data = res.json()

        if res.status_code != 200:
            print(
                "Error, status code != 200: %s",
                res.get("error", "No error information received."),
            )
            return None

        return res_data


def filter_playlists(playlists):
    playlist_links = {}
    for playlist_name, playlist_info, description in playlists:
        if (
            playlist_info["total"] < 80
            and playlist_info["total"] >= 10
            and not (
                "Person" in description
                or "Archived" in description
                or "Exempt" in description
            )
        ):
            playlist_links[playlist_name] = playlist_info["href"]
    return playlist_links
