import logging
import os
import spotdl
import spotipy
from spotdl.utils.config import DOWNLOADER_OPTIONS
from spotipy import SpotifyOAuth


class Spotify:

    def __init__(self, config):
        self.config = config
        self.logger = logging.getLogger("Spotify")
        self.sp = self.authenticate(
            config['spotify']['client_id'],
            config['spotify']['client_secret'],
            config['spotify']['redirect_uri']
        )
        self.logger.debug(f"Autenticato spotipy con client_id: {config['spotify']['client_id']}")
        # Remove azlyrics that creates issues (infinite connections)
        downloader_options = DOWNLOADER_OPTIONS
        downloader_options['lyrics_providers']=["genius", "musixmatch"]
        self.downloader = spotdl.Spotdl(
            client_id=config['spotify']["client_id"],
            client_secret=config['spotify']["client_secret"],
            downloader_settings=downloader_options
        )
        self.logger.debug(f"Autenticato spotdl con client_id: {config['spotify']['client_id']}")

    @staticmethod
    def authenticate(client_id: str, client_secret: str, redirect_uri:str  = 'http://127.0.0.1:8888/callback') -> spotipy.Spotify:
        """
        Autentica l\'utente su Spotify utilizzando le credenziali fornite.

        Args:
            client_id (str): ID client Spotify.
            client_secret (str): Segreto client Spotify.
            redirect_uri (str): URI di reindirizzamento per OAuth (default: http://127.0.0.1:8888/callback).

        Returns:
            spotipy.Spotify: Oggetto autenticato per interagire con l\'API Spotify.
        """
        scope = "playlist-read-private playlist-read-collaborative"
        auth_manager = SpotifyOAuth(
            client_id=client_id,
            client_secret=client_secret,
            redirect_uri=redirect_uri,
            scope=scope
        )
        return spotipy.Spotify(auth_manager=auth_manager)


    def list_user_playlists(self) -> list:
        """
        Restituisce la lista delle playlist dell'utente Spotify autenticato.
        Returns:
            list: Una lista di dizionari, ciascuno contenente:
                - 'name': Nome della playlist
                - 'id': ID della playlist
                - 'tracks_total': Numero totale di brani nella playlist
        """
        playlists = []
        results = self.sp.current_user_playlists()

        while results:
            for item in results['items']:
                playlists.append({
                    'name': item['name'],
                    'id': item['id'],
                    'tracks_total': item['tracks']['total']
                })
            if results['next']:
                results = self.sp.next(results)
            else:
                break
        self.logger.debug(f"Estratte {len(playlists)} playlist Spotify.")
        return playlists

    def get_playlist_tracks(self, playlist_info: dict) -> list:
        """
        Restituisce tutte le tracce di una playlist Spotify dato il suo ID.
        Args:
            playlist_info (str): L'ID della playlist Spotify.
        Returns:
            list: Una lista di dizionari, ciascuno contenente:
                - 'name': Nome della traccia
                - 'url': URL Spotify della traccia
                - 'artist': Nome/i dell'artista
                - 'id': ID della traccia
                - 'search_string': Stringa di ricerca formata da artista e titolo
        """
        tracks = []
        results = self.sp.playlist_items(playlist_info['id'], additional_types=['track'])

        while results:
            for item in results['items']:
                track = item.get('track')
                if track:
                    track_name = track['name']
                    track_url = f"https://open.spotify.com/track/{track['id']}"
                    artist_name = ', '.join([artist['name'] for artist in track['artists']])
                    tracks.append({
                        'name': track_name,
                        'isrc': track.get('external_ids', {}).get('isrc', ''),
                        'duration': track['duration_ms'],
                        'album': track['album']['name'],
                        'album_release_date': track['album'].get('release_date', ''),
                        'url': track_url,
                        'artist': artist_name,
                        'id': track['id'],
                        'search_string': f"{artist_name} - {track_name}"
                    })

            if results['next']:
                results = self.sp.next(results)
            else:
                break

        self.logger.debug(f"Estratte {len(tracks)} tracce dalla playlist {playlist_info['name']} [{playlist_info['id']}].")
        return tracks

    def download_songs(self, m_tracks: list, destination_path: str, subdirectory: str = "") -> list:
        """
        Scarica i brani mancanti utilizzando spotdl e li copia nella cartella di destinazione.
        Args:
            m_tracks (list): Lista di dizionari delle tracce da scaricare. Ogni dizionario deve contenere almeno la chiave 'url'.
            destination_path (str): Percorso della cartella dove salvare i brani scaricati.
        Returns:
            list: Lista dei brani scaricati con successo.
        """

        if subdirectory:
            destination_path = os.path.join(destination_path, subdirectory)
        os.makedirs(destination_path, exist_ok=True)
        songs_to_download = self.downloader.search([track['url'] for track in m_tracks])
        downloads = []
        current_dir = os.getcwd()
        try:
            os.chdir(destination_path)
            for song in songs_to_download:
                self.logger.info(f"Requesting download of: {song.name} - {song.artist}")
                try:
                    down, path = self.downloader.download(song)
                    if path:
                        # if self.config['download'].get("keep_cache", False):
                        #     shutil.copy2(path, destination_path)
                        # else:
                        #     shutil.move(path, destination_path)
                        downloads.append(down)
                        print("✅ Download completato.")
                        self.logger.info(f"Download completed: {song.name} - artista: {song.artist}")
                    else:
                        print(f"❌ Impossibile archiviare il file per {song.name} - {song.artist}. Download fallito.")
                        self.logger.warning(f"Impossibile scaricare canzone - titolo: {song.name} - artista: {song.artist} (Forse V.M. 18?)")
                except Exception as e:
                    print(f"❌ Errore durante il download: {e}")
                    self.logger.warning(
                        f"Impossibile scaricare canzone - titolo: {song.name} - artista: {song.artist} [{e}]")
        finally:
            os.chdir(current_dir)
            self.logger.info(f"Scaricate {len(downloads)} canzoni.")
            return downloads

