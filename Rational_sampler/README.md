# Rational Audio Resampler

A simple local web application for high-quality rational audio
sample-rate conversion.

This project was developed as **SP18 --- Multi-Rate Audio Resampler**.
The user-facing application uses the simpler name **Rational Audio
Resampler**.

## What it does

The application:

-   accepts WAV audio files
-   displays input audio information
-   lets the user select a target sample rate
-   performs rational sample-rate conversion
-   supports mono and multi-channel audio
-   writes the result as a 16-bit PCM WAV file
-   provides a numerical quality report
-   runs locally in a web browser

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
project. The web application does not modify the resampling algorithm.

## Typical example

For 48 kHz to 16 kHz:

\[ `\frac{f_{out}}{f_{in}}`{=tex} = `\frac{16000}{48000}`{=tex} =
`\frac{1}{3}`{=tex} \]

Therefore:

-   `L = 1`
-   `M = 3`

The final 48 kHz → 16 kHz filter used in the project has:

-   Passband: 6.8 kHz
-   Stopband: 8.0 kHz
-   Transition width: 1.2 kHz
-   Target attenuation: 70 dB
-   Taps: 173
-   Measured stopband: approximately −69.1 dB
-   Passband ripple: approximately 0.0059 dB
-   Group delay: approximately 1.792 ms

## Project files

``` text
Rational_Audio_Resampler/
├── app.py
├── sp18_resampler.py
├── requirements.txt
└── README.md
```

### `app.py`

Streamlit user interface.

It handles:

-   WAV file selection
-   WAV structure validation
-   input information display
-   target sample-rate selection
-   resampling request
-   output information display
-   WAV download
-   numerical quality report
-   simple error handling

### `sp18_resampler.py`

The reusable DSP/resampling backend.

### `requirements.txt`

Python packages required by the application.

### `README.md`

Project documentation and run instructions.

## Requirements

Python 3.10 or newer is recommended.

Install the required packages:

``` bash
pip install -r requirements.txt
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

The application runs locally on the computer. No internet connection is
required for the resampling itself.

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
-   8 kHz target
-   96 kHz target
-   very short valid WAV
-   same input/output sample rate
-   invalid/corrupted WAV files
-   WAV download
-   Light and Dark Streamlit themes

## Design choice: WAV rather than MP3

The current project intentionally uses WAV input and output.

WAV provides direct PCM audio samples and keeps the project focused on
sample-rate conversion. Adding MP3 would require an additional decoding
layer and external codec/runtime considerations, while the core DSP
engine itself does not need MP3 support.

## Project status

The DSP/resampling backend is complete.

The current stage is application testing and final project
packaging/documentation.
