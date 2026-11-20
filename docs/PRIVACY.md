# Privacy and network behavior

Manuscripts, line crops, transcriptions, metadata, annotations, and projects stay on the user's computer.
KurrentScholar has no account system, telemetry, analytics, advertising, crash upload, or cloud inference.

The only built-in network operation is an explicit first-run/model-management action. After confirmation,
Hugging Face Hub downloads the pinned public model revision. It necessarily sends ordinary connection
metadata (such as IP address and request headers) to Hugging Face/CDN infrastructure, but no manuscript
content. Recognition loads with `local_files_only=True`; it does not check for updates.

Projects contain an absolute source path and document SHA-256, so users should inspect a project before
sharing it. Diagnostic messages omit source content by design but may contain local paths. Uninstalling
the application must not remove user-created `.ksproj` files. Removing the separately installed model is
an explicit action.

