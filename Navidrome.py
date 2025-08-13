import hashlib
import logging
import random
import string
import requests

class Navidrome:
    def __init__(self, config):
        self.config = config
        self.logger = logging.getLogger("Navidrome")
        self.url = config['navidrome']["url"]
        self.username = config['navidrome']["username"]
        self.salt, self.token = create_navidrome_token(
            config['navidrome']["password"]
        )

    def search_this_song(self, song_title: str, artist: str) -> list:
        endpoint = "rest/search2.view"
        params = {
            "query": f"{artist} {song_title}",
            "songCount": 1
        }
        try:
            data = self.send_request(endpoint, params)
            return data.get("subsonic-response", {}).get("searchResult2", {}).get("song", [])
        except (requests.HTTPError, Exception) as e:
            print(f"Errore nella richiesta a Navidrome: {e}")
            self.logger.error(f"Errore nella richiesta a Navidrome: {e}")
            return []

    def list_playlists(self) -> list:
        """Recupera la lista delle playlist dell'utente da Navidrome.
        Returns:
            list: Lista di dizionari contenenti le informazioni delle playlist.
        """
        endpoint = "rest/getPlaylists.view"
        try:
            data = self.send_request(endpoint)
            return data.get("subsonic-response", {}).get("playlists", {}).get("playlist", [])
        except (requests.HTTPError, Exception) as e:
            print(f"Errore nella richiesta a Navidrome: {e}")
            self.logger.error(f"Errore nella richiesta a Navidrome: {e}")
            return []

    def create_playlist(self, playlist_name: str, playlist_id: str = "", songs: list = None) -> dict:
        """Crea una nuova playlist in Navidrome.

        Args:
            playlist_name (str): Nome della nuova playlist.
            playlist_id (str, opzionale): ID della playlist da aggiornare (se presente).
            songs (list, opzionale): Lista di canzoni da aggiungere alla playlist.

        Returns:
            dict: Risposta JSON della richiesta di creazione o aggiornamento della playlist.
        """
        endpoint = "rest/createPlaylist.view"
        params = {
            "name": playlist_name
        }
        if playlist_id and songs:
            params["playlistId"] = playlist_id
            for song in songs:
                params.setdefault("songId", []).append(song)
            self.logger.info(f"Creazione della nuova playlist: {playlist_name} e aggiungo {len(songs)} canzoni")
        else:
            self.logger.info(f"Creazione della nuova playlist {playlist_name} senza canzoni")
            print(f"Creazione della nuova playlist {playlist_name} senza canzoni")
        try:
            return self.send_request(endpoint, params)
        except (requests.HTTPError, Exception) as e:
            print(f"Errore nella creazione della playlist in Navidrome: {e}")
            self.logger.error(f"Errore nella creazione della playlist in Navidrome: {e}")
            return {}

    def get_playlist_info(self, playlist_id: str) -> dict:
        """Recupera le informazioni di una playlist specifica in Navidrome.
        Args:
            playlist_id (str): ID della playlist da recuperare.
        Returns:
            dict: La risposta JSON della richiesta con le informazioni della playlist.
        """
        endpoint = "rest/getPlaylist.view"
        params = {
            "id": playlist_id
        }
        try:
            data = self.send_request(endpoint, params)
            return data.get("subsonic-response", {}).get("playlist", {})
        except (requests.HTTPError, Exception) as e:
            print(f"Errore nel recupero delle informazioni della playlist in Navidrome: {e}")
            self.logger.error(f"Errore nel recupero delle informazioni della playlist in Navidrome: {e}")
            return {}

    def set_playlist_public(self, playlist_id: str, is_public: bool):
        """
        Imposta la visibilità di una playlist in Navidrome.
        Args:
            playlist_id (str): ID della playlist da modificare.
            is_public (bool): True per rendere la playlist pubblica, False per privata.
        """
        params = {
            "playlistId": playlist_id,
            "public": "true" if is_public else "false"
        }

        response = self.send_request("rest/updatePlaylist", params)

        if response.get("subsonic-response", {}).get("status") == "ok":
            self.logger.info(f"Playlist {playlist_id} impostata come {'pubblica' if is_public else 'privata'}.")
        else:
            self.logger.error(f"Errore nell'impostare la playlist {playlist_id}: {response}")

    def send_request(self, endpoint: str, params: dict = None) -> dict:
        """Invia una richiesta a Navidrome e gestisce gli errori.
        Args:
            endpoint (str): L'endpoint della richiesta.
            params (dict): I parametri della richiesta.
        Returns:
            dict: La risposta JSON della richiesta.
        """
        if params is None:
            params = {}
        url = f"{self.url}/{endpoint}"
        params.update({
            "u": self.username,
            "t": self.token,
            "s": self.salt,
            "v": "1.16.1",
            "c": "spotify_sync",
            "f": "json"
        })
        response = requests.get(url, params=params, timeout=10)
        try:
            response.raise_for_status()
            return response.json()
        except requests.HTTPError as e:
            self.logger.error(f"Errore nella richiesta [{endpoint}] a Navidrome: {e}")
            raise
        except Exception as e:
            self.logger.error(f"Errore durante la richiesta [{endpoint}] a Navidrome: {e}")
            raise



def create_navidrome_token(password: str) -> tuple:
    """
    Genera un token di autenticazione per Navidrome utilizzando una password e un salt casuale.
    Args:
        password (str): La password dell'utente Navidrome.
    Returns:
        tuple: Una tuple contenente il salt generato (str) e il token generato (str).
    """
    salt = ''.join(random.choices(string.ascii_letters + string.digits, k=8))
    token = hashlib.md5((password + salt).encode('utf-8')).hexdigest()
    return salt, token
