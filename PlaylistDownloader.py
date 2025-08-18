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
        liked_songs = self.config["download"].get("liked_songs", False)
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


    def extract_missing_songs(self, selected_playlist: dict, remove_duplicates = True) -> list:
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
        track_to_remove = []
        if remove_duplicates:
            track_to_remove.extend(self.remove_duplicates_from_playlist(n_playlist_info))
        spotify_track_list = self.spotify_client.get_playlist_tracks(selected_playlist)
        for number, item in enumerate(spotify_track_list, start=1):
            try:
                songs_found = self.navidrome_client.search_this_song(item)
                selected_song = self.select_song(songs_found, item)
                if not selected_song:
                    # Song to download
                    missing_tracks.append(item)
                    self.logger.info(f"Identificato brano mancante - {item['search_string']}")
                elif not self.song_in_playlist(item, n_playlist_info, strict_search=False) and not self.song_in_playlist(item, n_playlist_info, strict_search=True):
                    # Song to add to the playlist
                    track_to_add.append(selected_song['id'])
                else:
                    self.logger.info(f"Brano già presente nella playlist Navidrome: {item['search_string']}")
            except Exception as e:
                print(f"Errore nel parsing del brano '{item}': {e}")
                self.logger.error(f"Errore nel parsing del brano '{item}': {e}", exc_info=True)
                exit(1)

        self.navidrome_client.add_songs_to_playlist(n_playlist_info['id'], track_to_add, track_to_remove)
        return missing_tracks

    def song_in_playlist(self, spotify_song: dict, navidrome_playlist: dict, strict_search: bool = True) -> bool:
        songs_in_playlist = navidrome_playlist.get('entry', [])
        for navidrome_playlist_song in songs_in_playlist:
            n_isrc = navidrome_playlist_song.get('isrc', [])
            if strict_search:
                if n_isrc and spotify_song['isrc'] == n_isrc[0]:
                    self.logger.debug(f"Match by ISRC: {spotify_song['search_string']}")
                    return True
            else:
                if navidrome_playlist_song['title'] == spotify_song['name'] and navidrome_playlist_song['artist'] == spotify_song['artist']:
                    # Confronto basato su titolo e artista (meno affidabile)
                    return True
        self.logger.info(f"Brano assente dalla playlist Navidrome {spotify_song['name']} -> {navidrome_playlist['name']}")
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

    def select_song(self, n_songs_found: list, sp_song: dict) -> dict:
        """Select the most appropriate song from the search results."""
        if not n_songs_found:
            return {}
        elif len(n_songs_found) == 1:
            if not self.compare_isrc(sp_song, n_songs_found[0]):
                self.logger.info(f"No exact ISRC match found for {sp_song['search_string']}, returning first result.")
            return n_songs_found[0]
        else:
            for n_song in n_songs_found:
                if self.compare_isrc(sp_song, n_song):
                    self.logger.debug(f"Match ISRC found: {n_song['isrc']} for {sp_song['search_string']}")
                    return n_song
            else:
                # TODO fare la ricerca anche per titolo e artista
                self.logger.warning(f"No ISRC match found for {sp_song['search_string']}. "
                                    f"Returning first result: {n_songs_found[0]}")
                return n_songs_found[0]


    def compare_isrc(self, sp_song: dict, nv_song: dict) -> bool:
        """
        Confronta due ISRC e restituisce True se sono uguali, altrimenti False.
        Args:
            sp_isrc (str): ISRC della canzone in Spotify.
            navidrome_isrc (list): lista di ISRC della canzone in Navidrome.
        Returns:
            bool: True se gli ISRC sono uguali, False altrimenti.
        """
        sp_isrc = sp_song['isrc']
        nv_isrc_list = nv_song.get('isrc', [])
        for n_isrc in nv_isrc_list:
            if n_isrc == sp_isrc:
                self.logger.debug(f"Match ISRC trovato: {n_isrc} for {sp_song['search_string']}")
                return True
        self.logger.debug(f"No ISRC match: Navidrome: {nv_isrc_list}, Spotify: {sp_isrc} for {sp_song['search_string']}")
        return False

    def remove_duplicates_from_playlist(self, playlist_info)-> list:
        song_id = []
        song_index_to_remove = []
        for index, song in enumerate(playlist_info.get('entry', [])):
            if song['id'] not in song_id:
                song_id.append(song['id'])
            else:
                self.logger.info(f"Rimozione duplicato: {song['title']} di {song['artist']}")
                song_index_to_remove.append(index)
        return song_index_to_remove

def pulisci_nome_cartella(dir_name):
    # Rimuove caratteri non autorizzati (mantiene lettere, numeri, spazi, trattini e underscore)
    nome_pulito = re.sub(r'[<>:"/\\|?*]', '', dir_name)
    # Rimuove spazi multipli e trim
    nome_pulito = re.sub(r'\s+', ' ', nome_pulito).strip()
    return nome_pulito