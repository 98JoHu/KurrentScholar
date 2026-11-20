from __future__ import annotations

from pathlib import Path

from PIL import Image

from kurrentscholar.domain import RecognitionResult, geometric_mean


class TrOCRBackend:
    backend_id = "dh-unibe/trocr-kurrent"

    def __init__(self, model_path: str | Path, device: str = "cpu", max_new_tokens: int = 127) -> None:
        self.model_path = Path(model_path)
        self.device = device
        self.max_new_tokens = max_new_tokens
        self._processor = None
        self._model = None

    def load(self) -> None:
        from transformers import TrOCRProcessor, VisionEncoderDecoderModel

        self._processor = TrOCRProcessor.from_pretrained(
            self.model_path, local_files_only=True, trust_remote_code=False
        )
        self._model = VisionEncoderDecoderModel.from_pretrained(
            self.model_path,
            local_files_only=True,
            trust_remote_code=False,
            use_safetensors=True,
        ).to(self.device)
        self._model.eval()

    def recognize_line(self, image: Image.Image) -> RecognitionResult:
        """Recognize one cropped line. Passing a page is a caller error."""
        import torch

        if self._model is None or self._processor is None:
            self.load()
        if image.width < 4 or image.height < 4:
            raise ValueError("Recognition input is too small to contain a text line")
        if image.width * image.height > 25_000_000:
            raise ValueError("Recognition input is too large for a text-line crop")
        pixels = self._processor(images=image.convert("RGB"), return_tensors="pt").pixel_values.to(self.device)
        with torch.inference_mode():
            generated = self._model.generate(
                pixels,
                max_new_tokens=self.max_new_tokens,
                return_dict_in_generate=True,
                output_scores=True,
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
        return RecognitionResult(
            text=text,
            token_ids=token_ids,
            token_probabilities=token_probabilities,
            line_confidence=geometric_mean(token_probabilities),
            truncated=truncated,
        )

