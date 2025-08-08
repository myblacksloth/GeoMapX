import os
import sys
import argparse
import logging
from pathlib import Path
from PIL import Image
import piexif
import folium
from folium.plugins import MarkerCluster
from flask import Flask, render_template_string, request
import base64
from io import BytesIO
import tempfile
import ffmpeg
import subprocess
import json
import mimetypes

# Estensioni supportate
SUPPORTED_EXTENSIONS = ['.jpg', '.JPG', '.mov', '.MOV', '.mp4', '.HEIC', '.heic', '.heiv']

# directory per i file temporanei
# tempfile.tempdir = "./temp"
TEMP_DIR = Path("./temp")
TEMP_DIR.mkdir(parents=True, exist_ok=True)
tempfile.tempdir = str(TEMP_DIR)

# ISTRUZIONI: installa exiftool per i metadati e ffmpeg per le miniature
# Linux:   sudo apt install libimage-exiftool-perl ffmpeg
# macOS:   brew install exiftool ffmpeg
# Windows: scarica da https://exiftool.org/ e https://ffmpeg.org/ e aggiungi al PATH

# Template HTML per l'interfaccia web
HTML_TEMPLATE = '''
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Mappa Media</title>
    <style>
        #map { height: 90vh; width: 100%; }
        .search-box { margin: 10px; }
    </style>
</head>
<body>
    <div class="search-box">
        <form method="GET">
            <input type="text" name="q" placeholder="Cerca per nome o descrizione" value="{{ query }}">
            <button type="submit">Cerca</button>
        </form>
    </div>
    <div id="map">{{ map_html|safe }}</div>
</body>
</html>
'''

app = Flask(__name__)

# Logger colorato
class ColoredFormatter(logging.Formatter):
    COLORS = {
        'DEBUG': '\033[94m',     # blu
        'INFO': '\033[92m',      # verde
        'WARNING': '\033[93m',   # giallo
        'ERROR': '\033[91m',     # rosso
        'CRITICAL': '\033[1;91m' # rosso intenso
    }
    RESET = '\033[0m'

    def format(self, record):
        log_color = self.COLORS.get(record.levelname, self.RESET)
        formatted = super().format(record)
        return f"{log_color}{formatted}{self.RESET}"

def setup_colored_logger(name="MediaLogger"):
    logger = logging.getLogger(name)
    logger.setLevel(logging.DEBUG)

    ch = logging.StreamHandler()
    ch.setLevel(logging.DEBUG)

    formatter = ColoredFormatter("[%(levelname)s] %(message)s")
    ch.setFormatter(formatter)

    if not logger.handlers:
        logger.addHandler(ch)

    return logger

logger = setup_colored_logger()

def parse_gps_string(coord_str):
    try:
        parts = coord_str.strip().split()
        deg = float(parts[0])
        minutes = float(parts[2].replace("'", ""))
        seconds = float(parts[3].replace('"', ''))
        direction = parts[4]
        decimal = deg + minutes / 60 + seconds / 3600
        if direction in ['S', 'W']:
            decimal = -decimal
        return decimal
    except Exception as e:
        raise ValueError(f"Errore nel parsing della coordinata '{coord_str}': {e}")

def extract_gps_with_exiftool(file_path):
    try:
        result = subprocess.run(['exiftool', '-j', file_path], capture_output=True, text=True)
        data = json.loads(result.stdout)[0]
        if 'GPSLatitude' in data and 'GPSLongitude' in data:
            lat = parse_gps_string(data['GPSLatitude'])
            lon = parse_gps_string(data['GPSLongitude'])
            return lat, lon
    except Exception as e:
        logger.warning(f"[exiftool] Errore con {file_path}: {e}")
    return None, None

def extract_metadata(file_path):
    metadata = {'file': file_path, 'lat': None, 'lon': None, 'description': ''}

    try:
        lat, lon = extract_gps_with_exiftool(file_path)
        if lat and lon:
            metadata['lat'] = lat
            metadata['lon'] = lon

        result = subprocess.run(['exiftool', '-j', file_path], capture_output=True, text=True)
        data = json.loads(result.stdout)[0]
        metadata['description'] = data.get('Description', '') or data.get('Comment', '')

    except Exception as e:
        logger.error(f"Errore durante la lettura di {file_path}: {e}")

    return metadata

def is_video(file_path):
    mime_type, _ = mimetypes.guess_type(file_path)
    return mime_type and mime_type.startswith("video")

def is_image(file_path):
    mime_type, _ = mimetypes.guess_type(file_path)
    return mime_type and mime_type.startswith("image")

def create_thumbnail_base64(file_path):
    suffix = Path(file_path).suffix.lower()
    mime_type, _ = mimetypes.guess_type(file_path)

    try:
        temp_thumb = tempfile.NamedTemporaryFile(suffix=".jpg", delete=False)
        temp_thumb.close()

        # Se è video, usa ffmpeg
        if mime_type and mime_type.startswith("video"):
            ffmpeg.input(file_path, ss=1).filter('scale', 100, -1).output(
                temp_thumb.name, vframes=1, format='mjpeg', vcodec='mjpeg'
            ).run(quiet=True, overwrite_output=True)

        # Se è immagine ma non JPEG, HEIC, ecc. (PIL non supporta HEIC)
        elif suffix in ['.heic', '.heif', '.HEIC']:
            ffmpeg.input(file_path).filter('scale', 100, -1).output(
                temp_thumb.name, vframes=1, format='mjpeg', vcodec='mjpeg', qscale=2
            ).run(quiet=True, overwrite_output=True)


        # Altrimenti usa PIL
        else:
            with Image.open(file_path) as img:
                img.thumbnail((100, 100))
                img.save(temp_thumb.name, format="JPEG")

        with Image.open(temp_thumb.name) as img:
            buffer = BytesIO()
            img.save(buffer, format='JPEG')
            os.unlink(temp_thumb.name)
            return base64.b64encode(buffer.getvalue()).decode('utf-8')

    except Exception as e:
        logger.error(f"Errore creando la miniatura per {file_path}: {e}")
        return ''


def create_map(media_data, query=''):
    filtered_data = []
    query_lower = query.lower()
    for data in media_data:
        if not data['lat'] or not data['lon']:
            continue
        if not query or query_lower in Path(data['file']).name.lower() or query_lower in str(data['description']).lower():
            filtered_data.append(data)

    map_center = [filtered_data[0]['lat'], filtered_data[0]['lon']] if filtered_data else [0, 0]
    m = folium.Map(location=map_center, zoom_start=2)
    marker_cluster = MarkerCluster().add_to(m)

    for data in filtered_data:
        thumbnail_b64 = create_thumbnail_base64(data['file'])
        popup_html = f'<img src="data:image/jpeg;base64,{thumbnail_b64}"/><br>{Path(data["file"]).name}'
        folium.Marker(
            location=[data['lat'], data['lon']],
            popup=popup_html
        ).add_to(marker_cluster)

    return m._repr_html_()

@app.route('/')
def index():
    query = request.args.get('q', '')
    map_html = create_map(app.config['MEDIA_DATA'], query)
    return render_template_string(HTML_TEMPLATE, map_html=map_html, query=query)

def main():
    parser = argparse.ArgumentParser(description="Visualizzatore multimediale su mappa")
    parser.add_argument('-d', '--directory', type=str, help="Directory dei file multimediali")
    args = parser.parse_args()

    directory = args.directory
    if not directory:
        directory = input("Inserisci il percorso della directory contenente i file multimediali: ")

    directory = Path(directory).expanduser().resolve()
    logger.info(f"Path risolto: {directory}")
    if not directory.exists():
        logger.error("La directory non esiste.")
        sys.exit(1)
    elif not directory.is_dir():
        logger.error("Il percorso non è una directory.")
        sys.exit(1)

    media_files = [f for f in directory.rglob('*') if f.suffix.lower() in SUPPORTED_EXTENSIONS]
    metadata_list = [extract_metadata(str(f)) for f in media_files]

    logger.info(f"Totale file trovati: {len(media_files)}")
    gps_valid = [m for m in metadata_list if m['lat'] and m['lon']]
    logger.info(f"File con GPS validi: {len(gps_valid)}")
    for m in gps_valid:
        logger.debug(f"  ➤ {m['file']} - lat: {m['lat']} lon: {m['lon']} desc: {m['description']}")

    app.config['MEDIA_DATA'] = metadata_list
    app.run(debug=False)

if __name__ == '__main__':
    main()
