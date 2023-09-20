from code import compile_command
from urllib.parse import urlencode
import requests
import json
import os
import webbrowser
import base64
import secrets

# import api
import string
import logging
import collections
import pickle

from dotenv import load_dotenv
from pathlib import Path

from flask import (
    abort,
    Flask,
    make_response,
    redirect,
    render_template,
    request,
    session,
    url_for,
)

import spotify
import server_session

env_path = Path(".") / ".env"
load_dotenv(dotenv_path=env_path)

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

Server_Session = None
sc = None


def api_request(api_url, params={}):
    access_token = Server_Session.get_access_token(request.cookies.get("session_id"))

    req_headers = {"Authorization": f"Bearer {access_token}"}

    res = requests.get(api_url, headers=req_headers)
    res_data = res.json()

    if res.status_code != 200:
        app.logger.error(
            "Failed to get profile info: %s",
            res_data.get("error", "No error message returned."),
        )
        abort(res.status_code)

    return res_data


def create_app():
    app = Flask(__name__)
    app.secret_key = secrets.token_urlsafe(32)

    def get_access_token():
        return Server_Session.get_access_token(request.cookies.get("session_id"))

    def get_refresh_token():
        return Server_Session.get_refresh_token(request.cookies.get("session_id"))

    def tokens_exist():
        return Server_Session.token_exists(request.cookies.get("session_id"))

    @app.route("/")
    def index():
        return render_template("index.html")

    @app.route("/<loginout>")
    def login(loginout):
        state = "".join(
            secrets.choice(string.ascii_uppercase + string.digits) for _ in range(16)
        )

        scope = "user-read-private user-read-email playlist-read-private"

        if loginout == "logout":
            payload = {
                "client_id": CLIENT_ID,
                "response_type": "code",
                "redirect_uri": REDIRECT_URI,
                "state": state,
                "scope": scope,
                "show_dialog": True,
            }
        elif loginout == "login":
            payload = {
                "client_id": CLIENT_ID,
                "response_type": "code",
                "redirect_uri": REDIRECT_URI,
                "state": state,
                "scope": scope,
            }
        else:
            abort(404)

        res = make_response(redirect(f"{AUTH_URL}/?{urlencode(payload)}"))
        res.set_cookie("spotify_auth_state", state)
        return res

    @app.route("/callback")
    def callback():
        error = request.args.get("error")
        code = request.args.get("code")
        state = request.args.get("state")
        stored_state = request.cookies.get("spotify_auth_state")

        if state is None or state != stored_state:
            app.logger.error("Error message: %s", repr(error))
            app.logger.error("State mismatch: %s != %s", stored_state, state)
            abort(400)

        access_token, refresh_token = sc.get_tokens(code).values()

        session_id = Server_Session.add_user_token(access_token, refresh_token)

        session["cache_data"] = {"something": "Hello there"}

        res = make_response(redirect(url_for("me")))
        res.set_cookie("session_id", session_id)

        return res

    @app.route("/refresh")
    def refresh():
        refresh_token = get_refresh_token()

        access_token = sc.refresh_token(refresh_token=refresh_token)

        Server_Session.update_user_token(
            request.cookies.get("session_id"),
            access_token=access_token,
        )

        return json.dumps(
            Server_Session.get_user_tokens(request.cookies.get("session_id"))
        )

    @app.route("/me")
    def me():
        if not tokens_exist():
            app.logger.error("No tokens in session.")
            abort(400)

        res_data = sc.me(get_access_token())

        return render_template(
            "me.html",
            data=res_data,
            tokens=session.get("tokens"),
            cache_data=session.get("cache_data"),
        )

    @app.route("/duplicate_songs")
    def duplicate_songs():
        if not tokens_exist():
            app.logger.error("No tokens in session.")
            abort(400)

        data = {}
        cache_data = None

        try:
            with open("playlist_links.pk", "rb") as fi:
                data = pickle.load(fi)

        except FileNotFoundError as e:
            print("file not found, continuing to stuff")
        else:
            try:
                with open("songs.pk", "rb") as fi:
                    cache_data = pickle.load(fi)
            except FileNotFoundError as e:
                print("songs not found despite playlists found")

        if not cache_data:
            cache_data = parse_data(data)

        to_string = print_duplicates(cache_data)
        print("".join(to_string))

        session["cache_data"] = to_string

        return json.dumps(session["cache_data"])

    @app.route("/recache")
    def recache():
        if not tokens_exist():
            app.logger.error("No tokens in session.")
            abort(400)

        _ = parse_data([])

        return redirect(url_for("me"))

    def get_full_data():
        full_data = []
        res_data = {
            "next": URLs["base"].format(endpoint=URLs["me"] + URLs["playlists"])
        }

        while res_data["next"]:
            res_data = api_request(res_data["next"])
            for item in res_data["items"]:
                full_data.append([item["name"], item["tracks"], item["description"]])
        return full_data

    def get_valid_playlists(full_data, cached_links):
        playlist_links = {}
        for playlist_name, playlist_info, description in full_data:
            if (
                playlist_info["total"] < 80
                and playlist_info["total"] >= 10
                and not (
                    "Person" in description
                    or "Archived" in description
                    or "Exempt" in description
                )
                and playlist_name not in cached_links
            ):
                playlist_links[playlist_name] = playlist_info["href"]
        return playlist_links

    def compile_songs(playlist_links):
        cache_data = collections.defaultdict(list)
        for name, link in playlist_links.items():
            song_res = api_request(link)

            for item in song_res["items"]:
                try:
                    cache_data[
                        (item["track"]["name"], item["track"]["artists"][0]["name"])
                    ].append(name)
                except TypeError as e:
                    print("an error has occured\n\n\n\n")
                    print(item)
            while song_res["next"]:
                song_res = api_request(song_res["next"])
                try:
                    cache_data[
                        item["track"]["name"], item["track"]["artists"][0]["name"]
                    ].append(name)
                except TypeError as e:
                    print("an error has occured\n\n\n\n")
                    print(item)
        return cache_data

    def parse_data(cached_links):
        full_data = get_full_data()
        playlist_links = get_valid_playlists(full_data, cached_links)
        cache_data = compile_songs(playlist_links)

        with open("playlist_links.pk", "wb") as fi:
            pickle.dump(playlist_links, fi)

        with open("songs.pk", "wb") as fi:
            pickle.dump(cache_data, fi)

        return cache_data

    def print_duplicates(cache_data):
        to_string = []
        duplicates_exist = False
        for key, value in cache_data.items():
            if len(value) > 1:
                to_string.append(f"{key} appears in {value}\n")
                duplicates_exist = True
        if not duplicates_exist:
            to_string.append("No duplicates found")
        return to_string

    return app


if __name__ == "__main__":
    Server_Session = server_session.Server_Session()
    sc = spotify.Spotify_Client()
    app = create_app()
    app.run(debug=True)
