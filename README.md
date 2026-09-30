# Reel Splitter

Upload your own 16:9 video, and get it back as 1-minute parts on a 9:16 black (or white)
background, with the title on top and "Part-N" below. Runs on your own machine (VPS or Termux).

## Run

    git clone <your-repo-url> && cd reel-splitter
    ./run.sh

Then open http://127.0.0.1:5000 in a browser.

Needs: ffmpeg and python3 with venv (a font is included)
(Ubuntu: `sudo apt install ffmpeg python3-venv`, Termux: `pkg install ffmpeg python`).

## Opening it from your phone when it runs on a VPS

Best: an SSH tunnel, so nothing is public.

    ssh -L 5000:127.0.0.1:5000 user@your-vps      # then open http://127.0.0.1:5000

Or expose it, but always set a password:

    REEL_PASSWORD=choose-a-strong-one HOST=0.0.0.0 ./run.sh

(The login uses plain HTTP; use the tunnel or put HTTPS in front if you can.)

## Command line only

    python3 reel_splitter.py video.mp4 --title "My Video" --zip

Run `python3 reel_splitter.py -h` for all options. Finished parts are skipped if you re-run.

Use it only with videos you own or have the rights to.
