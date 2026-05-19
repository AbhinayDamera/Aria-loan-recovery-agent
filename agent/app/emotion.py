"""Real-time emotion scoring.

Combines three layers into a single 0-100 stress score, smoothed over a
short window so the dashboard line graph reads gracefully:

  stress = 0.5 * acoustic + 0.35 * semantic + 0.15 * dynamics

Acoustic   — pitch variance, energy, speaking rate, jitter (librosa)
Semantic   — verbal cues from the intent extractor's distress_level
Dynamics   — interruption rate, response latency, turn length
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from typing import Optional

import numpy as np


@dataclass
class EmotionState:
    """Mutable state per active call."""

    window_seconds: float = 3.0
    samples_per_second: int = 2  # update every 500ms

    _acoustic_buffer: deque = field(default_factory=lambda: deque(maxlen=6))
    _semantic_buffer: deque = field(default_factory=lambda: deque(maxlen=6))
    _dynamics_buffer: deque = field(default_factory=lambda: deque(maxlen=6))

    last_score: float = 0.0
    last_acoustic: float = 0.0
    last_semantic: float = 0.0
    last_dynamics: float = 0.0


class EmotionAnalyzer:
    """Compute stress scores from audio frames and conversation events."""

    def __init__(self) -> None:
        self._states: dict[str, EmotionState] = {}

    def state(self, call_id: str) -> EmotionState:
        if call_id not in self._states:
            self._states[call_id] = EmotionState()
        return self._states[call_id]

    def push_audio(self, call_id: str, pcm_chunk: np.ndarray, sample_rate: int = 16000) -> None:
        """Extract acoustic features from a 1s audio chunk and update state.

        TODO: Replace heuristic with wav2vec2-emotion in hours 16–24.
        Current heuristic gives a directionally correct score from energy +
        pitch variance, which is enough for the demo but not production.
        """
        if pcm_chunk.size == 0:
            return

        # Normalize to [-1, 1] floats.
        if pcm_chunk.dtype != np.float32:
            pcm_chunk = pcm_chunk.astype(np.float32) / 32768.0

        rms = float(np.sqrt(np.mean(pcm_chunk**2)))
        # Coarse pitch proxy: zero-crossing rate
        zcr = float(np.mean(np.abs(np.diff(np.sign(pcm_chunk)))) / 2.0)

        # Heuristic mapping → 0-100. Calibrate during testing.
        energy_score = float(np.clip(rms * 800.0, 0, 100))
        pitch_score = float(np.clip(zcr * 1200.0, 0, 100))
        acoustic = 0.6 * energy_score + 0.4 * pitch_score

        s = self.state(call_id)
        s._acoustic_buffer.append(acoustic)
        s.last_acoustic = float(np.mean(s._acoustic_buffer))

    def push_semantic(self, call_id: str, distress_level: int) -> None:
        """Update with the verbal distress reading from intent_extractor."""
        s = self.state(call_id)
        s._semantic_buffer.append(float(distress_level))
        s.last_semantic = float(np.mean(s._semantic_buffer))

    def push_dynamics(
        self,
        call_id: str,
        interruption: bool = False,
        response_latency_ms: Optional[float] = None,
        turn_length_chars: Optional[int] = None,
    ) -> None:
        """Update conversational dynamics signal."""
        score = 0.0
        if interruption:
            score += 40.0
        if response_latency_ms is not None and response_latency_ms > 4000:
            score += 25.0
        if turn_length_chars is not None and turn_length_chars < 8:
            score += 15.0  # one-word answers = disengagement
        score = float(np.clip(score, 0, 100))

        s = self.state(call_id)
        s._dynamics_buffer.append(score)
        s.last_dynamics = float(np.mean(s._dynamics_buffer))

    def score(self, call_id: str) -> float:
        """Return smoothed stress score in [0, 100]."""
        s = self.state(call_id)
        combined = (
            0.50 * s.last_acoustic + 0.35 * s.last_semantic + 0.15 * s.last_dynamics
        )
        # Exponential smoothing toward the previous score to avoid jitter
        smoothed = 0.6 * combined + 0.4 * s.last_score
        s.last_score = float(np.clip(smoothed, 0, 100))
        return s.last_score

    def reset(self, call_id: str) -> None:
        self._states.pop(call_id, None)
