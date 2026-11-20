from types import SimpleNamespace

import pytest
from PIL import Image

from kurrentscholar.recognition import trocr
from kurrentscholar.recognition.trocr import TrOCRBackend, configure_cpu_runtime


class FakeMkldnn:
    enabled = True

    @staticmethod
    def is_available():
        return True


class FakeTorchRuntime:
    def __init__(self, intraop=12, interop=4):
        self.intraop = intraop
        self.interop = interop
        self.backends = SimpleNamespace(mkldnn=FakeMkldnn())
        self.set_calls = []

    def get_num_threads(self):
        return self.intraop

    def set_num_threads(self, value):
        self.set_calls.append(value)
        self.intraop = value

    def get_num_interop_threads(self):
        return self.interop


def test_cpu_runtime_limits_oversubscription_to_process_affinity(monkeypatch):
    monkeypatch.delenv("OMP_NUM_THREADS", raising=False)
    monkeypatch.delenv("MKL_NUM_THREADS", raising=False)
    monkeypatch.setattr(trocr, "_available_cpu_count", lambda: 4)
    runtime = FakeTorchRuntime(intraop=12)

    configured = configure_cpu_runtime(runtime)

    assert runtime.set_calls == [4]
    assert configured.available_cpus == 4
    assert configured.intraop_threads == 4
    assert configured.interop_threads == 4
    assert configured.mkldnn_enabled


def test_cpu_runtime_respects_explicit_thread_environment(monkeypatch):
    monkeypatch.setenv("OMP_NUM_THREADS", "3")
    monkeypatch.delenv("MKL_NUM_THREADS", raising=False)
    monkeypatch.setattr(trocr, "_available_cpu_count", lambda: 4)
    runtime = FakeTorchRuntime(intraop=12)

    configured = configure_cpu_runtime(runtime)

    assert runtime.set_calls == []
    assert configured.intraop_threads == 12
    assert configured.explicit_thread_environment


def test_recognition_enables_decoder_cache_and_preserves_scores(monkeypatch, tmp_path):
    torch = pytest.importorskip("torch")

    class FakePixels:
        def to(self, _device):
            return self

    class FakeProcessor:
        tokenizer = SimpleNamespace(all_special_ids=[0, 1, 2])

        def __call__(self, **_kwargs):
            return SimpleNamespace(pixel_values=FakePixels())

        def batch_decode(self, _sequences, skip_special_tokens):
            assert skip_special_tokens
            return ["recognized text"]

    class FakeModel:
        generation_config = SimpleNamespace(eos_token_id=2)

        def __init__(self):
            self.generate_arguments = None

        def generate(self, _pixels, **arguments):
            self.generate_arguments = arguments
            return SimpleNamespace(
                sequences=torch.tensor([[0, 42, 2]]),
                scores=(object(), object()),
            )

        def compute_transition_scores(
            self, _sequences, _scores, _beam_indices, normalize_logits
        ):
            assert normalize_logits
            return torch.log(torch.tensor([[0.81, 0.95]]))

    backend = TrOCRBackend(tmp_path)
    backend._processor = FakeProcessor()
    backend._model = FakeModel()

    result = backend.recognize_line(Image.new("RGB", (100, 20), "white"))

    assert backend._model.generate_arguments["use_cache"] is True
    assert result.text == "recognized text"
    assert result.token_ids == [42]
    assert result.token_probabilities == pytest.approx([0.81])
    assert result.line_confidence == pytest.approx(0.81)
    assert not result.truncated
