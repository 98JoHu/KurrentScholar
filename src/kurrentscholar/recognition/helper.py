from __future__ import annotations

import logging
from pathlib import Path

LOGGER = logging.getLogger("KurrentScholar.helper")

INTENT_RESPONSES = {
    "pages": (
        "Use Transcription > Transcribe current page, Transcribe page range…, or Transcribe full "
        "document. A range accepts forms such as 3-5,8. Existing completed lines are preserved, "
        "and new lines appear live while later pages continue."
    ),
    "models": (
        "Open Models > Model Manager. It shows which pinned models are installed, partial or "
        "damaged downloads, and disk use. Select a row to install/repair or remove it. With a "
        "project open, Use for open project safely backs up results before changing models."
    ),
    "export": (
        "Open File > Export and choose plain text, Word, CSV, Excel, or research JSON. Word is best "
        "for reading; CSV/Excel for analysis; JSON preserves the richest provenance and coordinates."
    ),
    "confidence": (
        "Confidence labels are review priorities, not measured accuracy. Use Review > Next uncertain "
        "line, compare each result with the image, correct it, then mark it verified only when checked."
    ),
    "ground_truth": (
        "Correct every detected line on representative reference pages and mark each verified. Then "
        "use Review > Export ground-truth bundle…. The ZIP records reference and target pages, line "
        "crops, labels, source checksum, and base model for external CUDA fine-tuning."
    ),
    "diagnostics": (
        "Open Help > Diagnostic log for the application and crash-log locations. If transcription is "
        "running, cancel it and wait for the current line to finish; completed lines are already saved."
    ),
    "project": (
        "Use File > Open Document to create a .ksproj or File > Open Project to reopen one. If the "
        "source moved, KurrentScholar asks you to relink it and verifies its SHA-256 checksum first."
    ),
    "privacy": (
        "Manuscripts, transcriptions, corrections, projects, and exports remain local. Network access "
        "is used only when you explicitly download a pinned model from Hugging Face."
    ),
    "tutorial": "Open Help > Tutorial to replay the first-start walkthrough.",
    "unknown": (
        "I’m not certain. Check the File, Transcription, Review, Models, View, and Help menus. If "
        "something failed, open Help > Diagnostic log."
    ),
}

CLASSIFIER_PROMPT = """Classify the KurrentScholar help question into exactly one label:
pages, models, export, confidence, ground_truth, diagnostics, project, privacy, tutorial, unknown.
Return only the label, with no explanation."""


class LocalHelpBackend:
    def __init__(self, model_path: str | Path) -> None:
        self.model_path = Path(model_path)
        self._tokenizer = None
        self._model = None

    def load(self) -> None:
        import torch
        from transformers import AutoModelForCausalLM, AutoTokenizer

        LOGGER.info("Loading local helper from %s", self.model_path)
        self._tokenizer = AutoTokenizer.from_pretrained(
            self.model_path, local_files_only=True, trust_remote_code=False
        )
        self._model = AutoModelForCausalLM.from_pretrained(
            self.model_path,
            local_files_only=True,
            trust_remote_code=False,
            use_safetensors=True,
            torch_dtype=torch.float32,
        ).to("cpu")
        self._model.eval()
        LOGGER.info("Local helper ready")

    def answer(self, question: str) -> str:
        import torch

        question = question.strip()
        if not question:
            raise ValueError("Enter a question first.")
        if len(question) > 1_000:
            raise ValueError("Please shorten the question to 1,000 characters.")
        if self._model is None or self._tokenizer is None:
            self.load()
        rule_intent = self._rule_intent(question)
        if rule_intent:
            return INTENT_RESPONSES[rule_intent]
        messages = [
            {"role": "system", "content": CLASSIFIER_PROMPT},
            {"role": "user", "content": question},
        ]
        prompt = self._tokenizer.apply_chat_template(
            messages, tokenize=False, add_generation_prompt=True
        )
        encoded = self._tokenizer(prompt, return_tensors="pt", add_special_tokens=False)
        with torch.inference_mode():
            output = self._model.generate(
                **encoded,
                max_new_tokens=8,
                do_sample=False,
                pad_token_id=self._tokenizer.eos_token_id,
            )
        generated = self._tokenizer.decode(
            output[0, encoded["input_ids"].shape[-1]:], skip_special_tokens=True
        ).strip().lower()
        intent = next((label for label in INTENT_RESPONSES if label in generated), "unknown")
        return INTENT_RESPONSES[intent]

    @staticmethod
    def _rule_intent(question: str) -> str | None:
        text = question.casefold()
        rules = (
            ("ground_truth", ("ground truth", "fine-tun", "finetun", "training bundle")),
            ("diagnostics", ("error", "fail", "hang", "crash", "log", "stuck", "react")),
            ("models", ("model", "download", "install", "remove", "delete", "disk space")),
            ("export", ("export", "word", "excel", "csv", "json", "docx")),
            ("confidence", ("confidence", "uncertain", "verify", "correct", "accuracy")),
            ("pages", ("page", "range", "transcrib")),
            ("project", ("project", ".ksproj", "source", "relink", "open document")),
            ("privacy", ("privacy", "private", "upload", "offline", "internet", "network")),
            ("tutorial", ("tutorial", "walkthrough", "first start")),
        )
        return next((intent for intent, words in rules if any(word in text for word in words)), None)
