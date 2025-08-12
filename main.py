import logging
import os.path
import tomllib
from Navidrome import Navidrome
from PlaylistDownloader import PlaylistDownloader
from Spotify import Spotify

def select_playlist():
    """
        Permette all'utente di selezionare una playlist Spotify, visualizzarne le tracce,
        identificare quelle mancanti in Navidrome e scaricarle nella cartella specificata.

        Il flusso è il seguente:
        \n1. Mostra la lista delle playlist dell'utente.
        \n2. L'utente seleziona una playlist tramite input numerico.
        \n3. Vengono mostrate le tracce della playlist e viene indicato se sono già presenti in Navidrome.
        \n4. Le tracce mancanti vengono scaricate nella directory configurata.

        Returns:
            None
        """
    while True:
        playlists = spotify_client.list_user_playlists()
        print("\n📂 Le tue playlist:\n")
        for idx, playlist in enumerate(playlists):
            print(f"{idx + 1}. {playlist['name']} ({playlist['tracks_total']} brani)")

        # Scelta playlist
        choice = int(input("\nInserisci il numero della playlist da visualizzare: ")) - 1
        if choice == -1:
            print("Uscita dal programma.")
            return None
        elif 0 <= choice < len(playlists):
            selected = playlists[choice]
            print(f"\n🎵 Tracce nella playlist: {selected['name']}\n")
            downloads = downloader.sync_this_playlist(selected)
        else:
            print("Scelta non valida.")

def sync_all_playlists():
    """
    Sincronizza tutte le playlist dell'utente Spotify con Navidrome, scaricando le tracce mancanti.
    """
    playlists = spotify_client.list_user_playlists()
    for playlist in playlists:
        print(f"\n🎵 Sincronizzazione della playlist: {playlist['name']}")
        downloader.sync_this_playlist(playlist)

if __name__ == "__main__":
    with open(os.path.join('Config', 'config.toml'), 'rb') as f:
        config = tomllib.load(f)
    logging.basicConfig(
        level=config["config"].get("log_level", "INFO"),
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        filename=config["config"].get("log_file", "SpotifyImporter.log")
    )
    logging.info(f"Starting SpotifyImporter")
    spotify_client = Spotify(config)
    navidrome_client = Navidrome(config)
    downloader = PlaylistDownloader(config, spotify_client, navidrome_client)
    if not config["download"].get("selected_playlist", []):
        logging.info(f"Manuale playlist selection enabled.")
        select_playlist()
    else:
        logging.info(f"Starting automatic playlist synchronization.")
        downloader.sync()
        logging.info(f"Stopped automatic playlist synchronization.")
    logging.info(f"Finished SpotifyImporter")
    print(f"Finished SpotifyImporter")


