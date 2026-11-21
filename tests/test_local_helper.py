from kurrentscholar.recognition.helper import INTENT_RESPONSES, LocalHelpBackend


def test_local_helper_routes_common_questions_to_curated_answers():
    assert LocalHelpBackend._rule_intent("How do I transcribe pages 3 to 5?") == "pages"
    assert "Transcription >" in INTENT_RESPONSES["pages"]
    assert LocalHelpBackend._rule_intent("Can I delete a downloaded model?") == "models"
    assert "Model Manager" in INTENT_RESPONSES["models"]


def test_local_helper_prioritizes_fine_tuning_over_generic_model_word():
    assert LocalHelpBackend._rule_intent("Can I fine-tune this model with ground truth?") == "ground_truth"
    assert "external CUDA" in INTENT_RESPONSES["ground_truth"]
