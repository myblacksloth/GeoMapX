# GeoMapX

- [GeoMapX](#geomapx)
- [Info generali](#info-generali)
- [Requisiti OS da installare](#requisiti-os-da-installare)
    - [Linux](#linux)
    - [MacOs](#macos)
    - [Windows](#windows)
- [Eseguire in ambiente virtuale](#eseguire-in-ambiente-virtuale)
- [Generare eseguibile](#generare-eseguibile)


# Info generali

Mostrare su una mappa tutti i media contenenti dati GPS validi tra gli Exif

# Requisiti OS da installare

1. ffmpeg
2. exiftool

### Linux

```bash
sudo apt install libimage-exiftool-perl ffmpeg
```

### MacOs

```bash
brew install exiftool ffmpeg
```

### Windows

scaricare https://exiftool.org/ e https://ffmpeg.org/ e aggiungere al PATH

# Eseguire in ambiente virtuale

Creare ambiente virtuale

```bash
python3 -m venv .venv
```

Caricare ambiente virtuale

```bash
source .venv/bin/activate
```

Installare i requisiti Python

```bash
pip install --no-cache-dir -r requirements.txt
```

Eseguire (su directory specifica)

```bash
python3 -m src.main -d "./test"
```

Il contenuto sarà visibile tramite browser web all'indirizzo

    http://localohost:5000

# Generare eseguibile

Installare modulo per la compilazione

```bash
pip3 install pyinstaller
```

Generare l'eseguibile

```bash
pyinstaller --onefile --name mappa_media src/main.py
```

Generare eseguibile che non usa la shell

```bash
pyinstaller --onefile --windowed src/main.py
```

------------

&copy; Antonio Maulucci 2025
