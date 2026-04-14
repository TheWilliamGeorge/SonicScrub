# SonicScrub
AI-powered application for creating 'clean' versions of music.

AI clean edit creators are a fairly new technology, and most are not very robust and do not produce accurate or high-standard results. SonicScrub fixes these issues by syncing its transcription with lyrics pulled from lyric databases, using the human-written correct lyrics as a 'hard truth' to then align its transcription with. This turns line-by-line lyrics into word-level timing lyrics, allowing for extremely accurate muting.

Simply import an audio file and fill in the song title and artist. Let the AI split the vocal and instrumental track (this could take some time depending on your machine. By default it uses your GPU). It then fetches the lyrics and creates a word-level transcription, or creates its own from the isolated vocal track (although this is far less accurate). Commonly censored words are automatically selected for deletion, and you can add or remove words to be muted. The final track is then created, muting the vocals for any specified words. 

Note that a padding value of 0ms often works best, but occasionally a higher value may be needed. 

---
### I NEED YOUR HELP!

This program is tested and designed primarily to work on my computer (2017 MacBook Pro, 3.1 GHz Quad-Core Intel Core i7, Radeon Pro 560 4 GB, 16 GB 2133 MHz LPDDR3). As such, settings in the code are set up to work on my machine and some are hardcoded for the same purpose. I would be very grateful if you modify this to work on your machine if needed and submit a pull request :)

---

To install requirements, download or git clone this project and run 
```bash 
pip install -r requirements.txt
```
Then 
```bash
python3 main.py
```
to run the app. 

I had difficulty installing llvmlite (a dependency of numba and therefore Whisper, which is used for transcription) for my Intel Mac, so had to install it through homebrew and set some environment variables etc before installing a very specific version through pip. You may need to do the same or change the version number.
