import logging
from time import sleep
from Navidrome import Navidrome
from Spotify import Spotify
import re


class PlaylistDownloader:
    def __init__(self, config: dict, spotify_client: Spotify, navidrome_client: Navidrome):
        self.config = config
        self.logger = logging.getLogger("PlaylistDownloader")
        self.download_path = config['download']["path"]
        self.spotify_client = spotify_client
        self.navidrome_client = navidrome_client

    def sync(self):
        """
        Avvia il processo di sincronizzazione delle playlist.
        """
        while True:
            self.logger.info("Starting playlist download...")
            self.sync_all_playlists()
            self.logger.info("Playlist download completed. Pausing before next run...")
            sleep(self.config["download"].get('pause', 15)*60)  # Pausa in minuti

    def sync_all_playlists(self):
        selected_playlists = self.config["download"].get("selected_playlists", [])
        excluded_playlists = self.config["download"].get("excluded_playlists", [])
        playlists = self.spotify_client.list_user_playlists()
        if isinstance(selected_playlists, bool) and selected_playlists:
            self.logger.info("Syncing all playlists.")
            selected_playlists = [playlist['name'] for playlist in playlists]
        for playlist in playlists:
            if playlist['name'] in excluded_playlists:
                self.logger.debug(f"Skipping excluded playlist: {playlist['name']}")
                continue
            if playlist['name'] in selected_playlists:
                self.logger.info(f"Syncing playlist: {playlist['name']}")
                try:
                    self.sync_this_playlist(playlist)
                except Exception as e:
                    self.logger.error(f"Error syncing playlist {playlist['name']}: {e}", exc_info=True)
                    print(f"❌ Errore durante la sincronizzazione della playlist '{playlist['name']}': {e}")
            else:
                self.logger.info(f"Skipping playlist: {playlist['name']} (not selected)")


    def extract_missing_songs(self, selected_playlist: dict) -> list:
        """
        Estrae le tracce mancanti da una playlist selezionata confrontando le tracce della playlist Spotify
        con quelle presenti in Navidrome.
        Args:
            selected_playlist (dict): Dizionario contenente le informazioni della playlist selezionata.
        Returns:
            list: Lista di tracce (dict) che non sono presenti in Navidrome.
        """
        missing_tracks = []
        # Estrae le informazioni della playlist da Navidrome
        navidrome_playlist = self.select_navidrome_playlist(selected_playlist)
        if not navidrome_playlist or not navidrome_playlist.get('id'):
            print(f"❌ Impossibile creare o trovare la playlist in Navidrome. {navidrome_playlist}")
            self.logger.error("Impossibile creare o trovare la playlist in Navidrome.")
            return []
        n_playlist_info = self.navidrome_client.get_playlist_info(navidrome_playlist['id'])
        track_to_add = []
        tracks = self.spotify_client.get_playlist_tracks(selected_playlist)
        for number, item in enumerate(tracks, start=1):
            try:
                songs_found = self.navidrome_client.search_this_song(item['name'], item['artist'])
                status = "✅" if songs_found else "❌"
                print(f"{number}) {status} {item["search_string"]}")
                if not songs_found:
                    missing_tracks.append(item)
                    self.logger.info(f"Brano mancante - Richiedo download {item['search_string']}")
                else:
                    track_to_add.append(songs_found[0]['id'])
            except Exception as e:
                print(f"Errore nel parsing del brano '{item}': {e}")

        self.navidrome_client.create_playlist(n_playlist_info['name'], n_playlist_info['id'], track_to_add)

        return missing_tracks

    @staticmethod
    def song_in_playlist(navidrome_song: dict, navidrome_playlist: dict) -> bool:
        songs_in_playlist = navidrome_playlist.get('entry', [])
        for playlist_song in songs_in_playlist:
            if playlist_song['id'] == navidrome_song['id']:
                print(f"Brano '{navidrome_song['title']}' di '{navidrome_song['artist']}' già presente nella playlist Navidrome.")
                return True
        print("Brano non presente nella playlist Navidrome.")
        return False

    def import_missing_songs(self, songs: list, navidrome_playlist: dict) -> bool:
        """
        Importa un brano mancante in Navidrome.
        Args:
            songs (list): Dizionario contenente le informazioni della traccia da importare.
            navidrome_playlist (dict): Dizionario contenente le informazioni della playlist Navidrome.
        Returns:
            bool: True se il brano è stato importato con successo, False altrimenti.
        """
        try:
            self.navidrome_client.create_playlist(navidrome_playlist["name"], navidrome_playlist['id'], songs)
            print(f"Brano '{songs['title']}' aggiunto alla playlist '{navidrome_playlist["name"]}'.")
            return True
        except Exception as e:
            print(f"Errore nell'importazione dei brani: {e}")
            self.logger.error(f"Errore nell'importazione dei brani: {e}")
            return False

    def sync_this_playlist(self, selected_playlist: dict) -> list:
            """
            Sincronizza una playlist selezionata da Spotify con Navidrome, scaricando le tracce mancanti.
            Args:
                selected_playlist (dict): Dizionario contenente le informazioni della playlist selezionata.
            Returns:
                list: Lista di tracce (dict) che sono state scaricate.
            """
            self.logger.info(f"Starting synchronization for playlist: {selected_playlist['name']}")
            dir_safe_name = pulisci_nome_cartella(selected_playlist['name'])
            missing_tracks = self.extract_missing_songs(selected_playlist)
            downloads = self.spotify_client.download_songs(missing_tracks, self.download_path, dir_safe_name)
            if downloads:
                print(f"📂 Scaricati {len(downloads)} brani su {len(missing_tracks)} richiesti.")
            else:
                print("❌ Nessun brano scaricato. Tutti i brani erano già presenti in Navidrome.")
            return downloads

    def select_navidrome_playlist(self, spotify_playlist: dict) -> dict:
        """
        Crea una playlist con le tracce mancanti in Navidrome.
        Args:
            spotify_playlist (dict): Dizionario contenente le informazioni della playlist selezionata.
        Returns:
            dict: Le informazioni della playlist Navidrome creata o trovata.
        """
        navidrome_playlists = self.navidrome_client.list_playlists()
        selected_navidrome_playlist = None
        if not spotify_playlist.get('name'):
            print("❌ Playlist Spotify senza nome. Impossibile procedere.")
            self.logger.error("Playlist Spotify senza nome. Impossibile procedere.")
            return {}
        for navidrome_playlist in navidrome_playlists:
            if navidrome_playlist.get('name') == spotify_playlist['name']:
                self.logger.debug(f"Playlist Navidrome esistente: {navidrome_playlist['name']} ({navidrome_playlist['id']})")
                selected_navidrome_playlist = navidrome_playlist
                break
        if not selected_navidrome_playlist:
            print(f"Creazione della nuova playlist Navidrome: {spotify_playlist['name']}")
            self.logger.info(f"Creazione della nuova playlist Navidrome: {spotify_playlist['name']}")
            data = self.navidrome_client.create_playlist(spotify_playlist['name'])
            selected_navidrome_playlist = data.get("subsonic-response", {}).get("playlist", {})

        if not selected_navidrome_playlist or not selected_navidrome_playlist.get('id'):
            print(f"❌ Impossibile creare o trovare la playlist in Navidrome. {selected_navidrome_playlist}")
            self.logger.error("Impossibile creare o trovare la playlist in Navidrome.")
            return {}

        # Verifica se la playlist è pubblica, se non lo è la rende pubblica
        sp_info = self.navidrome_client.get_playlist_info(selected_navidrome_playlist['id'])
        if not sp_info.get('public', False):
            self.navidrome_client.set_playlist_public(selected_navidrome_playlist['id'], True)

        return selected_navidrome_playlist




def pulisci_nome_cartella(dir_name):
    # Rimuove caratteri non autorizzati (mantiene lettere, numeri, spazi, trattini e underscore)
    nome_pulito = re.sub(r'[<>:"/\\|?*]', '', dir_name)
    # Rimuove spazi multipli e trim
    nome_pulito = re.sub(r'\s+', ' ', nome_pulito).strip()
    return nome_pulito