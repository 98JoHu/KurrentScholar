from __future__ import annotations

import ctypes
import logging
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from PIL import Image

from kurrentscholar.domain import RecognitionResult, geometric_mean

LOGGER = logging.getLogger("KurrentScholar.recognition")


@dataclass(frozen=True, slots=True)
class CpuRuntimeConfiguration:
    available_cpus: int
    intraop_threads: int
    interop_threads: int
    explicit_thread_environment: bool
    mkldnn_enabled: bool


def _available_cpu_count() -> int:
    """Return CPUs available to this process, respecting affinity where possible."""

    process_cpu_count = getattr(os, "process_cpu_count", None)
    if process_cpu_count is not None:
        count = process_cpu_count()
        if count:
            return max(1, int(count))

    sched_getaffinity = getattr(os, "sched_getaffinity", None)
    if sched_getaffinity is not None:
        try:
            return max(1, len(sched_getaffinity(0)))
        except OSError:
            pass

    if os.name == "nt":
        try:
            process_mask = ctypes.c_size_t()
            system_mask = ctypes.c_size_t()
            kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
            process = kernel32.GetCurrentProcess()
            if kernel32.GetProcessAffinityMask(
                process, ctypes.byref(process_mask), ctypes.byref(system_mask)
            ):
                count = int(process_mask.value).bit_count()
                if count:
                    return count
        except (AttributeError, OSError):
            pass

    return max(1, int(os.cpu_count() or 1))


def configure_cpu_runtime(torch_module: Any) -> CpuRuntimeConfiguration:
    """Prevent oversubscription without overriding explicit administrator tuning.

    PyTorch chooses effective defaults for each CPU build. We retain those defaults
    unless they exceed the processors available to this process. Environment-based
    OpenMP/MKL configuration always takes precedence.
    """

    available_cpus = _available_cpu_count()
    explicit = any(os.environ.get(name) for name in ("OMP_NUM_THREADS", "MKL_NUM_THREADS"))
    intraop_threads = int(torch_module.get_num_threads())
    if not explicit and intraop_threads > available_cpus:
        torch_module.set_num_threads(available_cpus)
        intraop_threads = int(torch_module.get_num_threads())
    interop_threads = int(torch_module.get_num_interop_threads())
    mkldnn = getattr(getattr(torch_module, "backends", None), "mkldnn", None)
    mkldnn_enabled = bool(
        mkldnn is not None and mkldnn.is_available() and getattr(mkldnn, "enabled", False)
    )
    return CpuRuntimeConfiguration(
        available_cpus=available_cpus,
        intraop_threads=intraop_threads,
        interop_threads=interop_threads,
        explicit_thread_environment=explicit,
        mkldnn_enabled=mkldnn_enabled,
    )


class TrOCRBackend:
    def __init__(
        self,
        model_path: str | Path,
        device: str = "cpu",
        max_new_tokens: int = 127,
    ) -> None:
        self.model_path = Path(model_path)
        self.device = device
        self.max_new_tokens = max_new_tokens
        self._processor = None
        self._model = None

    def load(self) -> None:
        import torch
        from transformers import TrOCRProcessor, VisionEncoderDecoderModel

        started = time.monotonic()
        if self.device == "cpu":
            runtime = configure_cpu_runtime(torch)
            LOGGER.info(
                "CPU inference runtime: available_cpus=%s intraop_threads=%s "
                "interop_threads=%s explicit_thread_environment=%s mkldnn_enabled=%s "
                "decoder_cache=true",
                runtime.available_cpus,
                runtime.intraop_threads,
                runtime.interop_threads,
                runtime.explicit_thread_environment,
                runtime.mkldnn_enabled,
            )
        LOGGER.info("Loading TrOCR processor from %s", self.model_path)
        self._processor = TrOCRProcessor.from_pretrained(
            self.model_path,
            local_files_only=True,
            trust_remote_code=False,
            use_fast=False,
        )
        LOGGER.info("TrOCR processor loaded; loading model weights on %s", self.device)
        self._model = VisionEncoderDecoderModel.from_pretrained(
            self.model_path,
            local_files_only=True,
            trust_remote_code=False,
            use_safetensors=True,
        ).to(self.device)
        self._model.eval()
        LOGGER.info("TrOCR model ready after %.1f seconds", time.monotonic() - started)

    def recognize_line(self, image: Image.Image) -> RecognitionResult:
        """Recognize one cropped line. Passing a page is a caller error."""
        import torch

        if self._model is None or self._processor is None:
            self.load()
        if image.width < 4 or image.height < 4:
            raise ValueError("Recognition input is too small to contain a text line")
        if image.width * image.height > 25_000_000:
            raise ValueError("Recognition input is too large for a text-line crop")
        started = time.monotonic()
        LOGGER.info("Starting line inference for %sx%s pixels", image.width, image.height)
        pixels = self._processor(images=image.convert("RGB"), return_tensors="pt").pixel_values.to(self.device)
        with torch.inference_mode():
            generated = self._model.generate(
                pixels,
                max_new_tokens=self.max_new_tokens,
                return_dict_in_generate=True,
                output_scores=True,
                # The pinned training configuration disables this, but caching is
                # valid for autoregressive evaluation and avoids recomputing every
                # prior decoder token at each step.
                use_cache=True,
            )
        sequence = generated.sequences[0]
        scores = self._model.compute_transition_scores(
            generated.sequences,
            generated.scores,
            generated.beam_indices if hasattr(generated, "beam_indices") else None,
            normalize_logits=True,
        )[0]
        probabilities = scores.exp().detach().cpu().tolist()
        special = set(self._processor.tokenizer.all_special_ids)
        generated_ids = sequence[-len(probabilities) :].detach().cpu().tolist()
        pairs = [(token, probability) for token, probability in zip(generated_ids, probabilities, strict=True)]
        filtered = [(token, probability) for token, probability in pairs if token not in special]
        token_ids = [token for token, _ in filtered]
        token_probabilities = [float(probability) for _, probability in filtered]
        text = self._processor.batch_decode(generated.sequences, skip_special_tokens=True)[0]
        eos_id = self._model.generation_config.eos_token_id
        truncated = len(probabilities) >= self.max_new_tokens and eos_id not in generated_ids
        LOGGER.info(
            "Line inference finished after %.1f seconds: generated_characters=%s scored_tokens=%s truncated=%s",
            time.monotonic() - started,
            len(text),
            len(token_probabilities),
            truncated,
        )
        return RecognitionResult(
            text=text,
            token_ids=token_ids,
            token_probabilities=token_probabilities,
            line_confidence=geometric_mean(token_probabilities),
            truncated=truncated,
        )

