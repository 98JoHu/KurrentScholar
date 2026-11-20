# Third-party notices

This source project is MIT-licensed, but bundled distributions contain independent components. Their
licenses remain in force. Before a release, generate the dependency inventory from the exact lock file,
include installed license texts, and review transitive/native components.

| Component | Purpose | License/source |
|---|---|---|
| TrOCR Kurrent (`dh-unibe/trocr-kurrent`) | Handwriting recognition checkpoint | MIT; University of Bern model card; DOI 10.57967/hf/0442 |
| PySide6 / Qt 6 | Desktop UI | LGPL-3.0/GPL/commercial depending component; packaged builds must preserve LGPL notices and relinking rights |
| PyTorch | Local tensor inference | BSD-3-Clause |
| Transformers, Hugging Face Hub, safetensors | Model loading/download | Apache-2.0 |
| pypdfium2 / PDFium | PDF rendering | Apache-2.0 / BSD-style upstream notices |
| OpenCV | Image processing/segmentation | Apache-2.0 |
| Pillow | Image decoding | HPND |
| python-docx | Word export | MIT |

No model weights are committed or embedded in the default installer. The user explicitly downloads only
the pinned safetensors runtime files. This table is an engineering inventory, not a completed legal audit.

