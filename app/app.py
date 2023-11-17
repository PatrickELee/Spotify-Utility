from urllib.parse import urlencode
import json
import os
import secrets
import encoding
import logging

logging.basicConfig(
    format='%(asctime)s - %(levelname)s - %(message)s', level=logging.DEBUG
)

import string
import pickle

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


CLIENT_ID = os.getenv("CLIENT_ID")
CLIENT_SECRET = os.getenv("CLIENT_SECRET")
SPOTIFY_REDIRECT_URI = os.getenv("REDIRECT_URI")
REDIRECT_URI = "http://localhost:5000/callback"

AUTH_URL = "https://accounts.spotify.com/authorize"
URLs = {
    "base": "https://api.spotify.com/v1{endpoint}",
    "playlists": "/playlists",
    "me": "/me",
    "auth": "https://accounts.spotify.com/authorize",
    "token": "https://accounts.spotify.com/api/token",
}

Server_Session = server_session.Server_Session()
sc = spotify.Spotify_Client()


def create_app():
    app = Flask(__name__)
    app.secret_key = secrets.token_urlsafe(32)

    def get_access_token():
        return Server_Session.get_access_token(request.cookies.get("session_id"))

    def get_refresh_token():
        return Server_Session.get_refresh_token(request.cookies.get("session_id"))
    
    def get_spotify_id():
        return Server_Session.get_spotify_id_from_session_id(request.cookies.get("session_id"))

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
        payload = {
            "client_id": CLIENT_ID,
            "response_type": "code",
            "redirect_uri": REDIRECT_URI,
            "state": state,
            "scope": scope,
            "show_dialog": True,
        }

        if loginout == "logout":
            payload["show_dialog"] = True
        elif loginout != "login":
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
        spotify_id = sc.me(access_token)["id"]

        session_id = Server_Session.add_user_token(access_token, refresh_token, spotify_id)

        res = make_response(redirect(url_for("me")))
        res.set_cookie("session_id", session_id)

        return res

    @app.route("/refresh")
    def refresh():
        refresh_token = get_refresh_token()

        access_token = sc.refresh_access_token(refresh_token=refresh_token)

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

        # tokens = Server_Session.get_user_tokens(request.cookies.get("session_id"))

        return render_template(
            "me.html",
            data=res_data,
            tokens=Server_Session.get_user_tokens(request.cookies.get("session_id")),
            cache_data=Server_Session.get_duplicate_user_songs(get_spotify_id()) if Server_Session.is_cur_user_songs_cached(request.cookies.get("session_id")) else {},
        )

    @app.route("/duplicate_songs")
    def duplicate_songs():
        if not tokens_exist():
            app.logger.error("No tokens in session.")
            abort(400)

        playlists_per_song = {}

        if Server_Session.is_cur_user_songs_cached(request.cookies.get("session_id")):
            playlists_per_song = Server_Session.get_duplicate_user_songs(get_spotify_id())
            logging.info("found in cache")
        else:
            playlists_per_song = parse_data()

        # # to_string = print_duplicates(playlists_per_song)
        # # print("".join(to_string))


        return json.dumps(playlists_per_song)

    @app.route("/recache")
    def recache():
        if not tokens_exist():
            app.logger.error("No tokens in session.")
            abort(400)

        parse_data()

        return redirect(url_for("me"))

    def parse_data():
        playlists, playlists_per_song = sc.get_songs_in_playlists(get_access_token())
        duplicate_songs = get_duplicates(playlists_per_song)
        Server_Session.add_duplicate_user_songs(get_spotify_id(), duplicate_songs)

        return playlists_per_song
    

    def get_duplicates(cache_data):
        duplicates = {}
        for key, value in cache_data.items():
            if len(value) > 1:
                duplicates[key] = value
        return duplicates

    def print_duplicates(cache_data):
        to_string = []
        duplicates_exist = False
        duplicates = {}
        for key, value in cache_data.items():
            if len(value) > 1:
                duplicates[key] = value
                to_string.append(f"{key} appears in {value}\n")
                duplicates_exist = True
        if not duplicates_exist:
            to_string.append("No duplicates found")
        return to_string

    return app


if __name__ == "__main__":
    app = create_app()
    app.run(debug=True)
