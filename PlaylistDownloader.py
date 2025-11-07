import logging
from time import sleep
from Navidrome import Navidrome, NavidromeException
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


    def analyse_playlist_difference(self, selected_playlist: dict) -> dict:
        """
        Estrae le tracce mancanti da una playlist selezionata confrontando le tracce della playlist Spotify
        con quelle presenti in Navidrome.
        Args:
            selected_playlist (dict): Dizionario contenente le informazioni della playlist selezionata.
        Returns:
            dict: I risultati dell'analisi della playlist.
        """
        playlist_status = {
            "name": selected_playlist['name'],
            "total_tracks": selected_playlist['tracks_total'],
            # Tracks that need to be downloaded from Spotify
            "to_download": [],
            # Tracks that need to be added to the Navidrome playlist
            "to_add": [],
            # Tracks that need to be removed from the Navidrome playlist
            "to_remove": [],
            # Tracks that are already present in Navidrome playlist
            "to_keep": []
        }

        try:
            # Get info
            n_playlist_info = self.get_navidrome_playlist_info(selected_playlist)
            # Remove duplicates
            playlist_status["to_remove"].extend(self.remove_duplicates_from_playlist(n_playlist_info))
            # Compare playlists
            self.compare_playlist_with_spotify(n_playlist_info, selected_playlist, playlist_status)
        except NavidromeException:
            return playlist_status
        self.navidrome_client.add_songs_to_playlist(n_playlist_info['id'], playlist_status["to_add"], playlist_status["to_remove"])
        return playlist_status

    def compare_playlist_with_spotify(self, n_playlist_info, selected_playlist, playlist_status):
        spotify_track_list = self.spotify_client.get_playlist_tracks(selected_playlist)
        # Track Navidrome song IDs that should be kept (matched with Spotify)
        navidrome_songs_to_keep = set()
        
        for number, spotify_song in enumerate(spotify_track_list, start=1):
            matched_navidrome_song = find_song_by_isrc(spotify_song, n_playlist_info)
            if matched_navidrome_song:
                # Skip exact matches - song already in playlist with correct ISRC
                playlist_status["to_keep"].append(spotify_song['id'])
                navidrome_songs_to_keep.add(matched_navidrome_song['id'])
                self.logger.debug(f"Song already in Navidrome by ISRC: {spotify_song['search_string']}")
                continue
            try:
                #Search for possible matches
                songs_found = self.navidrome_client.search_this_song(spotify_song)
                # Select best match
                selected_song = self.select_song(songs_found, spotify_song)
                if not selected_song:
                    # Song not found - download required
                    playlist_status["to_download"].append(spotify_song)
                    self.logger.info(f"Identificato brano mancante - {spotify_song['search_string']}")
                elif not self.song_in_playlist(selected_song, n_playlist_info, playlist_status):
                    # Song not in the playlist
                    playlist_status["to_add"].append(selected_song['id'])
                    navidrome_songs_to_keep.add(selected_song['id'])
                else:
                    playlist_status["to_keep"].append(selected_song['id'])
                    navidrome_songs_to_keep.add(selected_song['id'])
                    self.logger.debug(f"Song already in Navidrome: {spotify_song['search_string']}")
            except Exception as e:
                print(f"Errore nel parsing del brano '{spotify_song}': {e}")
                self.logger.error(f"Errore nel parsing del brano '{spotify_song}': {e}", exc_info=True)
        
        # Identify songs in Navidrome playlist that are not in Spotify and mark for removal
        self.mark_songs_for_removal(n_playlist_info, navidrome_songs_to_keep, playlist_status)

    def mark_songs_for_removal(self, n_playlist_info, navidrome_songs_to_keep, playlist_status):
        """
        Identifies songs in the Navidrome playlist that are not present in the Spotify playlist
        and marks them for removal.
        
        Args:
            n_playlist_info (dict): Information about the Navidrome playlist including its entries.
            navidrome_songs_to_keep (set): Set of Navidrome song IDs that should be kept.
            playlist_status (dict): Dictionary containing playlist status including songs to remove.
        """
        # Get indices already marked for removal (e.g., duplicates)
        already_marked = set(playlist_status["to_remove"])
        
        for index, navidrome_song in enumerate(n_playlist_info.get('entry', [])):
            # Skip if already marked for removal
            if index in already_marked:
                continue
            
            if navidrome_song['id'] not in navidrome_songs_to_keep:
                # This song is in Navidrome but not in Spotify - mark for removal
                playlist_status["to_remove"].append(index)
                self.logger.info(f"Rimozione brano non presente in Spotify: {navidrome_song.get('title', 'Unknown')} di {navidrome_song.get('artist', 'Unknown')}")

    def get_navidrome_playlist_info(self, selected_playlist):
        # Estrae le informazioni della playlist da Navidrome
        navidrome_playlist = self.select_navidrome_playlist(selected_playlist)
        if not navidrome_playlist or not navidrome_playlist.get('id'):
            print(f"❌ Impossibile creare o trovare la playlist in Navidrome. {navidrome_playlist}")
            self.logger.error("Impossibile creare o trovare la playlist in Navidrome.")
            raise NavidromeException("Impossibile creare o trovare la playlist in Navidrome.")
        n_playlist_info = self.navidrome_client.get_playlist_info(navidrome_playlist['id'])
        return n_playlist_info

    def song_in_playlist(self, selected_n_song: dict, navidrome_playlist: dict, playlist_status: dict) -> bool:
        s_id = selected_n_song['id']
        s_title = selected_n_song.get('title')
        s_artist = selected_n_song['artist']
        if s_id in playlist_status["to_keep"]:
            self.logger.debug(f"Song already in playlist: {navidrome_playlist.get('name', "")}")
            return True
        elif s_id in playlist_status["to_add"]:
            self.logger.debug(f"Song will be already added to playlist: {navidrome_playlist.get('name', "")}")
            return True
        else:
            for navidrome_playlist_song in navidrome_playlist.get('entry', []):
                if s_id == navidrome_playlist_song['id']:
                    self.logger.debug(f"Song already in playlist: {navidrome_playlist.get('name', "")}")
                    return True
        self.logger.info(f"Brano {s_title}({s_artist}) assente dalla playlist Navidrome -> {navidrome_playlist.get('name', "")}")
        return False

    def sync_this_playlist(self, selected_playlist: dict) -> dict:
            """
            Synchronizes a selected playlist from Spotify with Navidrome, downloading missing tracks.

            Args:
                selected_playlist (dict): Dictionary containing information about the selected playlist.

            Returns:
                dict: Information about the playlist synchronization, including tracks to download.
            """
            self.logger.info(f"Starting synchronization for playlist: {selected_playlist['name']}")
            # Get playlist info
            playlist_info = self.analyse_playlist_difference(selected_playlist)
            # Download missing songs
            self.download_songs(playlist_info, selected_playlist)
            return playlist_info

    def download_songs(self, playlist_info, selected_playlist):
        dir_safe_name = clean_directory_name(selected_playlist['name'])
        downloads = self.spotify_client.download_songs(playlist_info["to_download"], self.download_path, dir_safe_name)
        if downloads:
            print(f"📂 Scaricati {len(downloads)} brani su {len(playlist_info["to_download"])} richiesti.")
        else:
            print("❌ Nessun brano scaricato. Tutti i brani erano già presenti in Navidrome.")

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
            # No songs found - Required download
            return {}
        elif len(n_songs_found) == 1:
            # Only one song found - return it
            if not isrc_match(sp_song, n_songs_found[0]):
                self.logger.info(f"No exact ISRC match found for {sp_song['search_string']}, returning first result.")
            return n_songs_found[0]
        else:
            # Multiple songs found - try to get the best match
            short_list = self.exact_song_matches(n_songs_found, sp_song)
            if short_list:
                return self.extract_song_best_quality(short_list)
            else:
                self.logger.warning(f"No ISRC match found for {sp_song['search_string']}")
                return self.extract_song_best_quality(n_songs_found)


    def exact_song_matches(self, n_songs_found, sp_song: dict) -> list:
        """Extract a short list of songs matching the isrc"""
        short_list = []
        for n_song in n_songs_found:
            if isrc_match(sp_song, n_song):
                self.logger.debug(f"Match ISRC found: {n_song['isrc']} for {sp_song['search_string']}")
                short_list.append(n_song)
        return short_list

    @staticmethod
    def extract_song_best_quality(n_songs_found):
        return max(n_songs_found, key=evaluate_song_quality)

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

def clean_directory_name(dir_name: str) -> str:
    """
    Cleans the directory name by removing invalid characters and extra whitespace.

    Args:
        dir_name (str): The name of the directory to clean.

    Returns:
        str: The cleaned directory name, safe for use in the filesystem.
    """
    clean_name = re.sub(r'[<>:"/\\|?*]', '', dir_name)
    clean_name = re.sub(r'\s+', ' ', clean_name).strip()
    return clean_name

def find_song_by_isrc(spotify_song: dict, navidrome_playlist: dict) -> dict:
    """
    Trova una canzone nella playlist di Navidrome basandosi sull'ISRC.
    Args:
        spotify_song (dict): Dizionario contenente le informazioni della canzone Spotify.
        navidrome_playlist (dict): Dizionario contenente le informazioni della playlist Navidrome.
    Returns:
        dict: La canzone di Navidrome che corrisponde, o un dizionario vuoto se non trovata.
    """
    for navidrome_song in navidrome_playlist.get('entry', []):
        if isrc_match(spotify_song, navidrome_song):
            return navidrome_song
    return {}

def isrc_already_present(spotify_song: dict, navidrome_playlist: dict) -> bool:
    """
    Verifica se una canzone di Spotify è già presente in una playlist di Navidrome basandosi sull'ISRC.
    Args:
        spotify_song (dict): Dizionario contenente le informazioni della canzone Spotify.
        navidrome_playlist (dict): Dizionario contenente le informazioni della playlist Navidrome.
    Returns:
        bool: True se la canzone è già presente, False altrimenti.
    """
    return bool(find_song_by_isrc(spotify_song, navidrome_playlist))

def isrc_match(spotify_song_info: dict, nv_song_info: list) -> bool:
    """
    Checks if the Spotify song ISRC matches any ISRC in the Navidrome song info.
    Args:
        spotify_song_info (dict): Dictionary containing Spotify song information.
        nv_song_info (list): List containing Navidrome song ISRCs.

    Returns:
        bool: True if there is a match, False otherwise.
    """
    # Check if spotify and navidrome have isrc
    sp_isrc = spotify_song_info.get('isrc')
    nv_isrc_list = nv_song_info.get('isrc')
    if not sp_isrc or not nv_isrc_list:
        return False

    # Verify if any of the navidrome isrc match the spotify isrc
    for n_isrc in nv_isrc_list:
        if n_isrc == sp_isrc:
            return True
    return False

def evaluate_song_quality(song: dict) -> float:
    """
    Calcola un punteggio di qualità in base a bitrate, sampling rate e bit depth.
    """
    bit_rate = song.get("bitRate", 0)
    sampling = song.get("samplingRate", 0)
    bit_depth = song.get("bitDepth", 0)
    suffix = song.get("suffix", "").lower()

    # Base score (normalizzato)
    score = (0.5 * bit_rate) + (0.3 * (sampling / 1000)) + (0.2 * bit_depth)

    # Bonus per formati lossless
    if suffix in ["flac", "wav", "alac"]:
        score *= 1.2  # +20% bonus

    # Penalità per formati molto compressi
    if suffix in ["mp3", "aac"] and bit_rate < 192:
        score *= 0.8

    # Diminishing returns: oltre 48kHz e 24bit, bonus ridotto
    if sampling > 48000:
        score += (48000 / 1000) + ((sampling - 48000) / 2000)
    if bit_depth > 24:
        score += 24 + (bit_depth - 24) * 0.5

    return score
