#!/bin/bash

RSYNC_OPTS=(-avz --delete --exclude='venv' --exclude='__pycache__' --exclude='.git')
SRC="almasena@192.168.1.20:~/almasena-2026/ship_system/"
SRC_FALLBACK="almasena@almasena:~/almasena-2026/ship_system/"
DEST="$HOME/almasena-dev/ship_system/"

echo "Mencoba sinkronisasi ship_system via IP (192.168.1.20)..."

if rsync "${RSYNC_OPTS[@]}" "$SRC" "$DEST"; then
    echo "Sinkronisasi via IP berhasil!"
else
    echo "Koneksi IP gagal. Beralih ke jalur hostname (almasena)..."
    if rsync "${RSYNC_OPTS[@]}" "$SRC_FALLBACK" "$DEST"; then
        echo "Sinkronisasi via Hostname berhasil!"
    else
        echo "Gagal! Kedua jalur (IP dan Hostname) tidak dapat dijangkau."
        exit 1
    fi
fi
