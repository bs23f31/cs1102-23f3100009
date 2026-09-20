# Rational Audio Resampler

A simple web application for high-quality rational audio
sample-rate conversion, deployable locally or on Streamlit Cloud.

This project was developed as **SP18 --- Multi-Rate Audio Resampler**.
The user-facing application uses the simpler name **Rational Audio
Resampler**.

**Live demo:** [PASTE YOUR STREAMLIT CLOUD URL HERE]

## What it does

The application:

-   accepts WAV audio files
-   displays input audio information
-   lets the user select a target sample rate from common presets
-   exposes advanced filter design controls (target attenuation,
    passband fraction) with a live preview of the resulting filter
    cost (taps, transition width, group delay) before conversion
-   performs rational sample-rate conversion
-   supports mono and multi-channel audio
-   writes the result as a 16-bit PCM WAV file
-   provides a numerical quality report
-   runs locally in a web browser, or hosted on the internet via
    Streamlit Cloud

No waveform, FFT, spectrogram, or other plots are used in the user
interface.

## Resampling engine

The DSP engine is implemented in `sp18_resampler.py`.

The conversion uses:

1.  rational-rate reduction
2.  anti-alias FIR filter design
3.  polyphase resampling
4.  numerical validation/reporting

The main conversion is based on SciPy's optimized `resample_poly`
implementation with the project's explicitly designed FIR filter.

The DSP engine is treated as the completed/frozen backend for this
project. The web application does not modify the resampling algorithm;
it only exposes the engine's existing `attenuation_db` and
`passband_fraction` constructor parameters through the UI.

## Typical example

For 48 kHz to 16 kHz (the application's default filter settings):

\[ `\frac{f_{out}}{f_{in}}`{=tex} = `\frac{16000}{48000}`{=tex} =
`\frac{1}{3}`{=tex} \]

Therefore:

-   `L = 1`
-   `M = 3`

The default 48 kHz → 16 kHz filter (70 dB target, 0.85 passband
fraction) has:

-   Passband: 6.8 kHz
-   Stopband: 8.0 kHz
-   Transition width: 1.2 kHz
-   Target attenuation: 70 dB
-   Taps: 173
-   Measured stopband: approximately −69.1 dB
-   Passband ripple: approximately 0.0059 dB
-   Group delay: approximately 1.792 ms

These values change if the target sample rate or the advanced filter
settings are changed from their defaults.

## Project files

``` text
Rational_Audio_Resampler/
├── app.py
├── sp18_resampler.py
├── requirements.txt
├── packages.txt
└── README.md
```

### `app.py`

Streamlit user interface.

It handles:

-   WAV file selection
-   WAV structure validation
-   input information display
-   target sample-rate selection
-   advanced filter settings (attenuation, passband fraction) with a
    live filter-cost preview
-   resampling request
-   output information display
-   WAV download
-   numerical quality report
-   simple error handling

### `sp18_resampler.py`

The reusable DSP/resampling backend.

### `requirements.txt`

Python packages required by the application (`streamlit`, `numpy`,
`scipy`, `soundfile`).

### `packages.txt`

System-level package required for deployment (`libsndfile1`), which
`soundfile` depends on. Needed for Streamlit Cloud / Linux hosts that
don't already have it installed; not required for local Windows/macOS
runs, since the `soundfile` wheel bundles it there.

### `README.md`

Project documentation and run instructions.

## Requirements

Python 3.10 or newer is recommended.

Install the required packages:

``` bash
pip install -r requirements.txt
```

On a fresh Linux machine (including most cloud environments), also
install the system library `soundfile` depends on:

``` bash
sudo apt-get install libsndfile1
```

## Run the application

Open a terminal in the project folder and run:

``` bash
streamlit run app.py
```

Streamlit will open the application in the browser, normally at:

``` text
http://localhost:8501
```

Run locally, no internet connection is required for the resampling
itself.

## Deploying (Streamlit Community Cloud)

1.  Push the project folder to a GitHub repository.
2.  On [share.streamlit.io](https://share.streamlit.io), create a new
    app pointing at the repo, the correct branch, and `app.py` as the
    main file path.
3.  Ensure `packages.txt` (containing `libsndfile1`) is present in the
    same folder as `app.py`, so `soundfile` has its system dependency
    available at build time.

## Supported target sample rates

The application provides common target rates including:

-   8 kHz
-   16 kHz
-   22.05 kHz
-   24 kHz
-   32 kHz
-   44.1 kHz
-   48 kHz
-   96 kHz

## Advanced filter settings

Beyond the default 70 dB / 0.85 filter design, the UI exposes:

-   **Target stopband attenuation (dB)** --- how strongly the stopband
    is suppressed.
-   **Passband fraction** --- how much of the output Nyquist frequency
    is used as the passband edge before the transition band begins.

Both are restricted to safe ranges in the UI to avoid excessively long
filters, and a live preview shows the resulting taps, transition
width, and group delay before running the conversion. The stopband
edge itself is always fixed at `min(input rate, output rate) / 2` and
is not affected by either setting.

## Input and output

**Input:** WAV

**Output:** 16-bit PCM WAV

The application supports mono and multi-channel WAV audio.

The output filename is generated from the input filename and target
sample rate, for example:

``` text
a0201.wav
    ↓
a0201_16kHz.wav
```

## Quality report

After conversion, the application can show numerical information
including:

-   rational resampling ratio
-   processing time
-   FIR filter taps
-   passband
-   stopband
-   transition width
-   target attenuation
-   measured stopband attenuation
-   passband ripple
-   group delay
-   input/output RMS
-   input/output peak
-   input/output sample counts
-   clipping status
-   input energy above the stopband

The report is numerical only; no plots are generated.

## Error handling

The application checks the WAV structure before passing the file to the
DSP backend. This includes checks for malformed or incomplete RIFF/WAVE
files.

Examples of invalid input that should be rejected include:

-   empty files
-   non-WAV files renamed with a `.wav` extension
-   corrupted WAV headers
-   truncated WAV files
-   inconsistent RIFF/chunk sizes

## Testing

Testing should cover:

-   normal mono WAV
-   normal stereo WAV
-   48 → 16 kHz
-   48 → 44.1 kHz
-   44.1 → 16 kHz
-   16 → 48 kHz (upsampling / anti-imaging check)
-   8 kHz target
-   96 kHz target
-   very short valid WAV
-   same input/output sample rate
-   invalid/corrupted WAV files
-   custom attenuation / passband fraction values
-   WAV download
-   Light and Dark Streamlit themes

## Design choice: WAV rather than MP3

The current project intentionally uses WAV input and output.

WAV provides direct PCM audio samples and keeps the project focused on
sample-rate conversion. Adding MP3 would require an additional decoding
layer and external codec/runtime considerations (e.g. `ffmpeg`), while
the core DSP engine itself does not need MP3 support to perform
correct resampling.

## Project status

The DSP/resampling backend and web application are complete and
deployed. Remaining work is limited to documentation and optional
future enhancements (see the project report's Future Work section).
