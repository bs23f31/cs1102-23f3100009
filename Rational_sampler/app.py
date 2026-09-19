import os
import tempfile
import struct
from math import gcd
from pathlib import Path

import soundfile as sf
import streamlit as st

from sp18_resampler import SP18Resampler


# ------------------------------------------------------------
# WAV validation
# ------------------------------------------------------------

def validate_wav_structure(path):
    """
    Validate the basic RIFF/WAVE file structure before passing the
    file to the DSP backend.

    In particular, reject files whose RIFF/chunk sizes claim that
    more data exists than is actually present. This catches truncated
    WAV files that libsndfile may otherwise read partially.
    """
    with open(path, "rb") as f:
        data = f.read()

    if len(data) < 12:
        raise ValueError("Invalid WAV file.")

    if data[0:4] != b"RIFF" or data[8:12] != b"WAVE":
        raise ValueError("Invalid WAV file.")

    riff_size = struct.unpack_from("<I", data, 4)[0]
    if riff_size != len(data) - 8:
        raise ValueError("Incomplete or corrupted WAV file.")

    pos = 12
    found_fmt = False
    found_data = False

    while pos + 8 <= len(data):
        chunk_id = data[pos:pos + 4]
        chunk_size = struct.unpack_from("<I", data, pos + 4)[0]
        chunk_start = pos + 8
        chunk_end = chunk_start + chunk_size

        if chunk_end > len(data):
            raise ValueError("Incomplete or corrupted WAV file.")

        if chunk_id == b"fmt ":
            found_fmt = True
        elif chunk_id == b"data":
            found_data = True

        pos = chunk_end + (chunk_size & 1)

    if pos != len(data) or not found_fmt or not found_data:
        raise ValueError("Invalid WAV file.")

    return True


# ------------------------------------------------------------
# Small helpers for the pipeline / rate-grid UI
# ------------------------------------------------------------

COMMON_RATES = [
    ("8 kHz", 8000),
    ("16 kHz", 16000),
    ("22.05 kHz", 22050),
    ("24 kHz", 24000),
    ("32 kHz", 32000),
    ("44.1 kHz", 44100),
    ("48 kHz", 48000),
    ("96 kHz", 96000),
]

# Defaults match SP18Resampler's own constructor defaults, so leaving the
# advanced panel untouched reproduces the exact filter used throughout the
# project report.
DEFAULT_ATTENUATION_DB = 70.0
DEFAULT_PASSBAND_FRACTION = 0.85

# UI-side range limits (tighter than the engine's own 0 < x < 1 / x > 0
# validation) to keep filter order in a sane, fast-to-compute range. As
# passband_fraction -> 1, the transition band -> 0 and the required
# filter order grows without bound, so the upper bound is kept away from 1.
ATTENUATION_MIN, ATTENUATION_MAX, ATTENUATION_STEP = 30.0, 100.0, 1.0
PASSBAND_MIN, PASSBAND_MAX, PASSBAND_STEP = 0.60, 0.95, 0.01


def reduced_ratio(fs_in: int, fs_out: int):
    g = gcd(int(fs_in), int(fs_out))
    return fs_out // g, fs_in // g  # L, M


# ------------------------------------------------------------
# Page configuration
# ------------------------------------------------------------

st.set_page_config(
    page_title="Rational Audio Resampler",
    page_icon="🎚️",
    layout="centered",
)

st.markdown(
    """
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@500;600;700&family=JetBrains+Mono:wght@400;500;600&display=swap');

        :root {
            --bg:        #12151B;
            --panel:     #181C24;
            --panel-2:   #1E232C;
            --line:      #2A3038;
            --text:      #E7E7E4;
            --text-dim:  #868D98;
            --accent:    #F5A623;
            --accent-2:  #E8940C;
            --good:      #5FD9A4;
            --bad:       #F26D6D;
            --mono: 'JetBrains Mono', ui-monospace, SFMono-Regular, Menlo, monospace;
            --sans: 'Space Grotesk', 'Segoe UI', sans-serif;
        }

        html, body, [class*="css"] {
            font-family: var(--sans);
            color: var(--text);
        }

        .stApp {
            background:
                radial-gradient(ellipse 900px 500px at 50% -10%, rgba(245,166,35,0.06), transparent 60%),
                var(--bg);
        }

        .block-container {
            max-width: 760px;
            padding-top: 2.6rem;
            padding-bottom: 4rem;
        }

        /* ---------- Header ---------- */
        .app-eyebrow {
            font-family: var(--mono);
            font-size: 0.75rem;
            color: #988ce8cc;
            letter-spacing: 0.04em;
            margin-top: 0.35rem;
            margin-bottom: 0.35rem;
        }

	.app-title,
	p.app-title,
	div[data-testid="stMarkdownContainer"] .app-title {
    		font-size: 3rem !important;
    		font-weight: 700;
    		line-height: 1.15;
    		margin: 0;
	}

        .app-subtitle {
            color: var(--text-dim);
            margin-top: 0.35rem;
            margin-bottom: 1.6rem;
            font-size: 1rem;
        }

        /* ---------- Signal chain diagram ---------- */
        .chain {
            display: flex;
            align-items: center;
            justify-content: space-between;
            background: var(--panel);
            border: 1px solid var(--line);
            border-radius: 12px;
            padding: 1rem 1.1rem;
            margin-bottom: 2rem;
        }

        .chain-node {
            display: flex;
            flex-direction: column;
            align-items: center;
            gap: 0.4rem;
            flex: 1;
            text-align: center;
        }

        .chain-dot {
            width: 9px;
            height: 9px;
            border-radius: 50%;
            background: var(--line);
            border: 1px solid #3a4049;
            transition: background 0.25s ease, box-shadow 0.25s ease;
        }

        .chain-dot.on {
            background: var(--accent);
            box-shadow: 0 0 10px rgba(245,166,35,0.65);
            border-color: var(--accent);
        }

        .chain-label {
            font-size: 0.72rem;
            color: var(--text-dim);
            line-height: 1.25;
        }

        .chain-link {
            flex: 0.6;
            height: 1px;
            background: linear-gradient(90deg, var(--line), var(--line));
            margin-top: -1.1rem;
        }

        /* ---------- Section headings ---------- */
        .section-heading {
            display: flex;
            align-items: baseline;
            gap: 0.55rem;
            margin-top: 1.9rem;
            margin-bottom: 0.85rem;
        }

        .section-heading .index {
            font-family: var(--mono);
            font-size: 0.78rem;
            color: #988ce8cc;
        }

        .section-heading .title {
            font-size: 1.05rem;
            font-weight: 600;
        }

        /* ---------- Readout panel (LCD-style info) ---------- */
        .readout {
            background: var(--panel);
            border: 1px solid var(--line);
            border-radius: 12px;
            padding: 0.2rem 1.1rem;
        }

        .readout-row {
            display: grid;
            grid-template-columns: 150px 1fr;
            column-gap: 1rem;
            padding: 0.62rem 0;
            border-bottom: 1px solid var(--line);
            align-items: baseline;
        }

        .readout-row:last-child { border-bottom: none; }

        .readout-label {
            font-size: 0.82rem;
            color: var(--text-dim);
        }

        .readout-value {
            font-family: var(--mono);
            font-size: 0.92rem;
            color: var(--text);
        }

        .readout-value.accent { color: var(--accent); }
        .readout-value.good { color: var(--good); }
        .readout-value.bad { color: var(--bad); }

        /* ---------- Ratio preview strip ---------- */
        .ratio-strip {
            display: flex;
            align-items: center;
            justify-content: space-between;
            font-family: var(--mono);
            font-size: 0.85rem;
            color: var(--text-dim);
            background: var(--panel-2);
            border: 1px solid var(--line);
            border-radius: 10px;
            padding: 0.65rem 1rem;
            margin-top: 0.9rem;
            margin-bottom: 1.1rem;
        }

        .ratio-strip .ratio-value {
            color: var(--accent);
            font-weight: 600;
        }

        /* ---------- Badges ---------- */
        .badge {
            display: inline-block;
            font-family: var(--mono);
            font-size: 0.72rem;
            padding: 0.14rem 0.55rem;
            border-radius: 999px;
            border: 1px solid transparent;
        }

        .badge.good { color: var(--good); background: rgba(95,217,164,0.10); border-color: rgba(95,217,164,0.35); }
        .badge.bad  { color: var(--bad);  background: rgba(242,109,109,0.10); border-color: rgba(242,109,109,0.35); }

        /* ---------- Advanced settings note ---------- */
        .adv-note {
            font-size: 0.82rem;
            color: var(--text-dim);
            background: var(--panel-2);
            border: 1px solid var(--line);
            border-left: 3px solid var(--accent);
            border-radius: 8px;
            padding: 0.6rem 0.85rem;
            margin-bottom: 0.9rem;
            line-height: 1.5;
        }

        /* ---------- Streamlit widget restyling ---------- */
        div[data-testid="stFileUploaderDropzone"] {
            background: var(--panel) !important;
            border: 1px dashed var(--line) !important;
            border-radius: 12px !important;
        }

        div[data-testid="stAlert"] {
            background: var(--panel) !important;
            border: 1px solid var(--line) !important;
            border-left: 3px solid var(--bad) !important;
            border-radius: 8px !important;
        }

        div[data-testid="stAlertContentSuccess"] {
            color: var(--good) !important;
        }

        div.stButton > button {
            border-radius: 9px;
            border: 1px solid var(--line);
            background: var(--panel-2);
            color: var(--text);
            font-family: var(--mono);
            font-size: 0.85rem;
            transition: border-color 0.15s ease, color 0.15s ease;
        }

        div.stButton > button:hover {
            border-color: var(--accent);
            color: var(--accent);
        }

        div.stButton > button[kind="primary"] {
            background: #988ce8cc;
            border-color: #988ce8cc;
            color: #1a1300;
            font-weight: 600;
        }

        div.stButton > button[kind="primary"]:hover {
            background: var(--accent-2);
            border-color: var(--accent-2);
            color: #1a1300;
        }

        div[data-testid="stDownloadButton"] {
            margin-top: 0.9rem;
        }

        div[data-testid="stDownloadButton"] button {
            width: 100%;
            border-radius: 9px;
            background: #988ce8cc;
            border-color: #988ce8cc;
            color: #1a1300;
            font-family: var(--mono);
            font-weight: 600;
        }

        div[data-testid="stDownloadButton"] button:hover {
            background: var(--accent-2);
            border-color: var(--accent-2);
        }

        /* Expanders (advanced settings + quality report) */
        div[data-testid="stExpander"] {
            background: var(--panel);
            border: 1px solid var(--line);
            border-radius: 12px;
            overflow: hidden;
            margin-bottom: 0.9rem;
        }

        div[data-testid="stExpander"] summary {
            font-family: var(--mono);
            font-size: 0.85rem;
            color: var(--text);
            background: var(--panel);
            border-bottom: 1px solid var(--line);
        }

        div[data-testid="stExpander"] [data-testid="stExpanderDetails"] {
            background: var(--panel);
        }

        /* Sliders */
        div[data-testid="stSlider"] label p {
            font-family: var(--mono);
            font-size: 0.8rem;
            color: var(--text-dim);
        }

        .report-group-title {
            font-family: var(--mono);
            font-size: 0.72rem;
            letter-spacing: 0.03em;
            color: var(--accent);
            margin-top: 1.1rem;
            margin-bottom: 0.4rem;
        }

        .report-group-title:first-child { margin-top: 0.3rem; }

        .report-row {
            display: grid;
            grid-template-columns: 170px 1fr;
            column-gap: 1rem;
            padding: 0.32rem 0;
            font-size: 0.86rem;
        }

        .report-label { color: var(--text-dim); }
        .report-value { font-family: var(--mono); color: var(--text); }

        footer, #MainMenu { visibility: hidden; }

        .app-footer {
            margin-top: 3rem;
            font-family: var(--mono);
            font-size: 0.72rem;
            color: var(--text-dim);
            text-align: center;
            opacity: 0.65;
        }
    </style>
    """,
    unsafe_allow_html=True,
)


# ------------------------------------------------------------
# Header
# ------------------------------------------------------------

st.markdown('<div class="app-eyebrow">SP18</div>', unsafe_allow_html=True)
st.markdown('<p class="app-title">Rational Audio Resampler</p>', unsafe_allow_html=True)
st.markdown(
    '<div class="app-subtitle">Polyphase sample-rate conversion with a designed anti-alias FIR filter</div>',
    unsafe_allow_html=True,
)

# Signal chain diagram — mirrors the fixed processing order in sp18_resampler.py
_chain_stages = ["Input WAV", "Rational reduction", "Anti-alias FIR", "Polyphase resample", "Output WAV"]
_chain_html = '<div class="chain">'
for i, stage in enumerate(_chain_stages):
    is_on = "on" if "sp18_report" in st.session_state else ""
    _chain_html += (
        f'<div class="chain-node"><div class="chain-dot {is_on}"></div>'
        f'<div class="chain-label">{stage}</div></div>'
    )
    if i < len(_chain_stages) - 1:
        _chain_html += '<div class="chain-link"></div>'
_chain_html += '</div>'
st.markdown(_chain_html, unsafe_allow_html=True)


# ------------------------------------------------------------
# Input Audio
# ------------------------------------------------------------

st.markdown(
    '<div class="section-heading"><span class="index">01</span><span class="title">Input audio</span></div>',
    unsafe_allow_html=True,
)

uploaded_file = st.file_uploader(
    "Choose a WAV file",
    type=["wav"],
    label_visibility="collapsed",
)

input_info = None

if uploaded_file is not None:
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as tmp:
            tmp.write(uploaded_file.getbuffer())
            temp_input_path = tmp.name

        validate_wav_structure(temp_input_path)
        input_info = sf.info(temp_input_path)

        st.markdown(
            f"""
            <div class="readout">
                <div class="readout-row"><div class="readout-label">File</div><div class="readout-value">{uploaded_file.name}</div></div>
                <div class="readout-row"><div class="readout-label">Sample rate</div><div class="readout-value accent">{input_info.samplerate:,} Hz</div></div>
                <div class="readout-row"><div class="readout-label">Channels</div><div class="readout-value">{"Mono" if input_info.channels == 1 else f"Stereo ({input_info.channels} ch)"}</div></div>
                <div class="readout-row"><div class="readout-label">Bit depth</div><div class="readout-value">{input_info.subtype.replace("PCM_", "") + "-bit" if input_info.subtype.startswith("PCM_") else input_info.subtype}</div></div>
                <div class="readout-row"><div class="readout-label">Duration</div><div class="readout-value">{input_info.duration:.2f} s</div></div>
                <div class="readout-row"><div class="readout-label">Samples</div><div class="readout-value">{input_info.frames:,}</div></div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    except Exception:
        input_info = None
        st.error("Could not read audio file. Please select a valid WAV file.")
else:
    st.markdown(
        '<div class="readout" style="padding:1rem 1.1rem;">'
        '<span class="readout-label">Drop a WAV file above to see its sample rate, '
        'channel layout, and duration.</span></div>',
        unsafe_allow_html=True,
    )


# ------------------------------------------------------------
# Resampling controls
# ------------------------------------------------------------

if input_info is not None:
    st.markdown(
        '<div class="section-heading"><span class="index">02</span><span class="title">Target sample rate</span></div>',
        unsafe_allow_html=True,
    )

    if "target_rate" not in st.session_state:
        st.session_state["target_rate"] = 16000

    cols = st.columns(4)
    for i, (label, rate) in enumerate(COMMON_RATES):
        with cols[i % 4]:
            is_selected = st.session_state["target_rate"] == rate
            if st.button(
                label,
                key=f"rate_{rate}",
                type="primary" if is_selected else "secondary",
                use_container_width=True,
            ):
                st.session_state["target_rate"] = rate

    target_rate = st.session_state["target_rate"]
    same_rate = int(input_info.samplerate) == target_rate

    L, M = reduced_ratio(int(input_info.samplerate), target_rate)
    if same_rate:
        direction = "passthrough"
    elif target_rate < input_info.samplerate:
        direction = "downsampling"
    else:
        direction = "upsampling"

    st.markdown(
        f"""
        <div class="ratio-strip">
            <span>{input_info.samplerate:,} Hz → {target_rate:,} Hz</span>
            <span class="ratio-value">L/M = {L}/{M}</span>
            <span>{direction}</span>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # ----------------------------------------------------
    # Advanced filter settings
    # ----------------------------------------------------
    with st.expander("Advanced filter settings", expanded=False):
        st.markdown(
            '<div class="adv-note">These control the anti-alias FIR filter designed inside '
            'the DSP engine before decimation/interpolation. The stopband edge always stays '
            'fixed at the output Nyquist frequency — these settings change the filter\'s '
            'steepness and length, not where aliasing protection begins.</div>',
            unsafe_allow_html=True,
        )

        attenuation_db = st.slider(
            "Target stopband attenuation (dB)",
            min_value=ATTENUATION_MIN,
            max_value=ATTENUATION_MAX,
            value=DEFAULT_ATTENUATION_DB,
            step=ATTENUATION_STEP,
            help="Higher values reject more of the stopband but require a longer filter "
                 "(more taps, more group delay).",
        )

        passband_fraction = st.slider(
            "Passband fraction",
            min_value=PASSBAND_MIN,
            max_value=PASSBAND_MAX,
            value=DEFAULT_PASSBAND_FRACTION,
            step=PASSBAND_STEP,
            help="Fraction of the output Nyquist frequency used as the passband edge. "
                 "Higher values preserve more bandwidth but narrow the transition band, "
                 "which also requires a longer filter.",
        )

        is_default = (
            attenuation_db == DEFAULT_ATTENUATION_DB
            and passband_fraction == DEFAULT_PASSBAND_FRACTION
        )
        if not is_default:
            st.caption(
                f"Using custom filter design ({attenuation_db:.0f} dB, "
                f"{passband_fraction:.2f} passband fraction) — results will differ "
                f"from the project's documented {DEFAULT_ATTENUATION_DB:.0f} dB / "
                f"{DEFAULT_PASSBAND_FRACTION:.2f} default case."
            )

        # ------------------------------------------------
        # Live filter-cost preview
        #
        # Runs the real design_filter() from the DSP engine (not a
        # re-implementation) against the current slider values and the
        # actual input/target sample rates, so the preview always matches
        # what "Resample audio" would actually build. This is a pure
        # preview call: it only designs the filter, it does not touch
        # the uploaded audio.
        # ------------------------------------------------
        try:
            _preview_engine = SP18Resampler(
                attenuation_db=attenuation_db,
                passband_fraction=passband_fraction,
            )
            _, _preview_info, _, _ = _preview_engine.design_filter(
                int(input_info.samplerate), int(target_rate)
            )

            _delta_html = ""
            if not is_default:
                _default_engine = SP18Resampler(
                    attenuation_db=DEFAULT_ATTENUATION_DB,
                    passband_fraction=DEFAULT_PASSBAND_FRACTION,
                )
                _, _default_info, _, _ = _default_engine.design_filter(
                    int(input_info.samplerate), int(target_rate)
                )
                _tap_ratio = _preview_info.taps / _default_info.taps
                _delta_html = (
                    f'<div class="report-row"><div class="report-label">Vs. default filter</div>'
                    f'<div class="report-value">{_tap_ratio:.1f}\u00d7 the taps '
                    f'\u00b7 {_tap_ratio:.1f}\u00d7 the compute</div></div>'
                )

            st.markdown(
                f"""
                <div class="readout" style="margin-top:0.7rem;">
                    <div class="report-row"><div class="report-label">Passband edge</div><div class="report-value">{_preview_info.passband_hz / 1000:.3f} kHz</div></div>
                    <div class="report-row"><div class="report-label">Transition width</div><div class="report-value">{_preview_info.transition_hz / 1000:.3f} kHz</div></div>
                    <div class="report-row"><div class="report-label">Estimated taps</div><div class="report-value">{_preview_info.taps:,}</div></div>
                    <div class="report-row"><div class="report-label">Estimated group delay</div><div class="report-value">{_preview_info.group_delay_ms:.3f} ms</div></div>
                    {_delta_html}
                </div>
                """,
                unsafe_allow_html=True,
            )
            st.caption(
                "Narrower transition width \u2192 more taps \u2192 more compute and more "
                "group delay, for the same target attenuation."
            )
        except Exception:
            pass

    if same_rate:
        st.info(
            f"Input and output sample rates are both {target_rate:,} Hz. "
            "No conversion is required."
        )

    resample_clicked = st.button(
        "Resample audio",
        type="primary",
        use_container_width=True,
        disabled=same_rate,
    )

    # --------------------------------------------------------
    # Resampling
    # --------------------------------------------------------

    if resample_clicked:
        input_suffix = Path(uploaded_file.name).suffix
        input_stem = Path(uploaded_file.name).stem
        rate_label = f"{target_rate / 1000:g}kHz"
        output_name = f"{input_stem}_{rate_label}{input_suffix}"

        output_path = os.path.join(
            tempfile.gettempdir(),
            f"sp18_{output_name}",
        )

        try:
            with st.spinner("Designing filter and resampling..."):
                engine = SP18Resampler(
                    attenuation_db=attenuation_db,
                    passband_fraction=passband_fraction,
                )
                report = engine.resample_file(
                    temp_input_path,
                    output_path,
                    target_rate,
                )

            st.session_state["sp18_report"] = report.to_dict()
            st.session_state["sp18_output_path"] = output_path
            st.session_state["sp18_output_name"] = output_name
            st.rerun()

        except Exception as exc:
            st.session_state.pop("sp18_report", None)
            st.session_state.pop("sp18_output_path", None)
            st.session_state.pop("sp18_output_name", None)
            st.error(f"Resampling failed: {exc}")

        finally:
            try:
                os.remove(temp_input_path)
            except OSError:
                pass


# ------------------------------------------------------------
# Output
# ------------------------------------------------------------

if "sp18_report" in st.session_state:
    report = st.session_state["sp18_report"]
    output_path = st.session_state["sp18_output_path"]
    output_name = st.session_state["sp18_output_name"]

    st.markdown(
        '<div class="section-heading"><span class="index">03</span><span class="title">Output</span></div>',
        unsafe_allow_html=True,
    )

    st.success("Resampling complete")

    st.markdown(
        f"""
        <div class="readout">
            <div class="readout-row"><div class="readout-label">File</div><div class="readout-value">{output_name}</div></div>
            <div class="readout-row"><div class="readout-label">Sample rate</div><div class="readout-value accent">{report["output_sample_rate"]:,} Hz</div></div>
            <div class="readout-row"><div class="readout-label">Channels</div><div class="readout-value">{"Mono" if report["channels"] == 1 else f"Stereo ({report['channels']} ch)"}</div></div>
            <div class="readout-row"><div class="readout-label">Duration</div><div class="readout-value">{report["duration_seconds"]:.2f} s</div></div>
            <div class="readout-row"><div class="readout-label">Samples</div><div class="readout-value">{report["output_samples"]:,}</div></div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    if os.path.exists(output_path):
        with open(output_path, "rb") as output_file:
            st.download_button(
                "Download WAV",
                data=output_file,
                file_name=output_name,
                mime="audio/wav",
                type="primary",
                use_container_width=True,
            )

    # --------------------------------------------------------
    # Quality Report
    # --------------------------------------------------------

    st.markdown(
        '<div class="section-heading"><span class="index">04</span><span class="title">Quality report</span></div>',
        unsafe_allow_html=True,
    )

    with st.expander("Show numerical quality report", expanded=False):
        filt = report.get("filter", {})

        def group_title(title):
            st.markdown(f'<div class="report-group-title">{title}</div>', unsafe_allow_html=True)

        def row(label, value_html):
            st.markdown(
                f'<div class="report-row"><div class="report-label">{label}</div>'
                f'<div class="report-value">{value_html}</div></div>',
                unsafe_allow_html=True,
            )

        group_title("Resampling")
        row("Ratio", f'{report["L"]} / {report["M"]}')
        row("Processing time", f'{report["processing_time_seconds"]:.3f} s')

        if filt:
            spec_met = filt["measured_stopband_db"] <= -(filt["attenuation_target_db"] - 0.5)
            spec_badge = (
                '<span class="badge good">spec met</span>' if spec_met
                else '<span class="badge bad">below target</span>'
            )

            group_title("Filter")
            row("Taps", f'{filt["taps"]:,}')
            row("Passband", f'{filt["passband_hz"] / 1000:g} kHz')
            row("Stopband", f'{filt["stopband_hz"] / 1000:g} kHz')
            row("Transition", f'{filt["transition_hz"] / 1000:g} kHz')
            row("Target attenuation", f'{filt["attenuation_target_db"]:.1f} dB')
            row("Measured stopband", f'{filt["measured_stopband_db"]:.2f} dB &nbsp; {spec_badge}')
            row("Passband ripple", f'{filt["passband_ripple_db"]:.4f} dB')
            row("Group delay", f'{filt["group_delay_ms"]:.3f} ms')

        clip_badge = (
            '<span class="badge bad">clipped</span>' if report["output_clipped"]
            else '<span class="badge good">no clipping</span>'
        )

        group_title("Audio")
        row("Input RMS", f'{report["input_rms"]:.6f}')
        row("Output RMS", f'{report["output_rms"]:.6f}')
        row("Input peak", f'{report["input_peak"]:.6f}')
        row("Output peak", f'{report["output_peak"]:.6f}')
        row("Clipping", clip_badge)

        group_title("Input above stopband")
        row("RMS", f'{report["input_out_of_band_rms"]:.6f}')
        row("Energy fraction", f'{report["input_out_of_band_fraction_percent"]:.4f} %')

st.markdown('<div class="app-footer">Created By Harsh Prajapti</div>', unsafe_allow_html=True)